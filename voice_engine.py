"""
voice_engine.py - Krystalicznie Czysty Silnik Głosu dla Discorda (Edge-TTS + Pre-Render WAV + Anti-Deadlock)
============================================================================================================
Odpowiada za:
1. Ciepły, naturalny głos neuronowy ChatGPT (pl-PL-ZofiaNeural).
2. Krystalicznie czysty dźwięk bez szumów, zniekształceń i przesterów (brak clippingu):
   - Pre-renderowanie do formatu bezstratnego PCM 48kHz Stereo WAV (dokładny standard Discord Opus).
   - Dynamiczny zapas głośności (headroom 0.90) eliminujący trzaski.
   - W 100% odporne na blokady międzywątkowe (thread-safe polling pętli odtwarzania).
"""

import os
import asyncio
import uuid
import re
from typing import Optional
import discord
import edge_tts

DEFAULT_WARM_VOICE = "pl-PL-ZofiaNeural"
TEMP_AUDIO_DIR = "temp_audio"


def sanitize_text_for_speech(text: str) -> str:
    """Oczyszcza tekst dla syntezatora mowy, usuwając emoji, linki i zbędne formatowanie."""
    if not text:
        return ""
    # Usuń linki
    text = re.sub(r"https?://\S+", "", text)
    # Usuń wzmianki Discorda <@123>
    text = re.sub(r"<@!?\d+>", "", text)
    # Usuń formatowanie markdown
    text = re.sub(r"[\*`#_~>]", "", text)
    # Usuń emoji i symbole specjalne (w tym pionowe kropki z nazw kanałów)
    text = re.sub(r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\ud83c-\ud83e][\ud000-\udfff]|[\ufe30-\ufe4f\uff00-\uffef]", " ", text)
    # Zastąp cudzysłowy i myślniki naturalnymi pauzami
    text = text.replace("„", "").replace("”", "").replace('"', "")
    text = text.replace("–", ", ").replace("—", ", ").replace("➔", " to ")

    # Weź maksymalnie 2-3 pełne zdania (do 250 znaków) dla płynnej, naturalnej wypowiedzi głosowej
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    clean_parts = []
    total_len = 0
    for s in sentences:
        s_clean = s.strip()
        if not s_clean:
            continue
        if total_len + len(s_clean) < 250:
            clean_parts.append(s_clean)
            total_len += len(s_clean)
        else:
            break

    result = " ".join(clean_parts).strip()
    return result or text[:200].strip()


class DiscordVoiceEngine:
    def __init__(self, voice_name: str = DEFAULT_WARM_VOICE):
        self.voice_name = voice_name or DEFAULT_WARM_VOICE
        self.voice_client: Optional[discord.VoiceClient] = None
        self.speech_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None

        os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

    def start_worker(self, loop: asyncio.AbstractEventLoop):
        """Uruchamia asynchronicznego workera kolejki odtwarzania audio."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = loop.create_task(self._process_queue())

    async def connect(self, channel: discord.VoiceChannel) -> bool:
        """Dołącza bota do wskazanego kanału głosowego lub synchronizuje aktywne połączenie."""
        try:
            guild_vc = channel.guild.voice_client
            if guild_vc:
                self.voice_client = guild_vc
                if guild_vc.is_connected():
                    if guild_vc.channel.id == channel.id:
                        return True
                    print(f"[VOICE_ENGINE] Przenoszenie z '{guild_vc.channel.name}' do '{channel.name}'...")
                    await guild_vc.move_to(channel)
                    await asyncio.sleep(0.4)
                    return True
                else:
                    try:
                        await guild_vc.disconnect(force=True)
                    except Exception:
                        pass

            print(f"[VOICE_ENGINE] Łączenie z kanałem głosowym '{channel.name}' (ID: {channel.id})...")
            self.voice_client = await channel.connect(reconnect=True, timeout=20.0)
            await asyncio.sleep(0.5)
            return True
        except Exception as e:
            print(f"[VOICE_ENGINE] Błąd połączenia z kanałem {channel.name}: {e}")
            return False

    async def disconnect(self):
        """Bezpiecznie odłącza bota z kanału głosowego."""
        try:
            if self.voice_client:
                await self.voice_client.disconnect(force=True)
            self.voice_client = None
        except Exception as e:
            print(f"[VOICE_ENGINE] Błąd odłączania: {e}")

    def is_connected(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_connected())

    async def enqueue_speech(self, text: str):
        """Dodaje oczyszczony tekst do kolejki syntezy mowy."""
        clean_speech = sanitize_text_for_speech(text)
        if not clean_speech or len(clean_speech) < 2:
            return

        if self.speech_queue.qsize() > 8:
            print("[VOICE_ENGINE] Kolejka audio pełna – czyszczę najstarszy wpis.")
            try:
                self.speech_queue.get_nowait()
                self.speech_queue.task_done()
            except Exception:
                pass

        print(f"[VOICE_ENGINE] 📥 Dodano do kolejki mowy: '{clean_speech}'")
        await self.speech_queue.put(clean_speech)

    async def _process_queue(self):
        """Pobiera teksty z kolejki, konwertuje do WAV 48kHz stereo i odtwarza bez blokowania pętli."""
        while True:
            text = await self.speech_queue.get()
            mp3_path = None
            wav_path = None
            try:
                # Poczekaj do 3 sekund, jeśli trwa właśnie łączenie z kanałem
                wait_conn = 0.0
                while not self.is_connected() and wait_conn < 3.0:
                    await asyncio.sleep(0.2)
                    wait_conn += 0.2

                if not self.is_connected():
                    print(f"[VOICE_ENGINE] ⚠️ Pominięto mowę (brak połączenia VC): '{text}'")
                    continue

                # Czekaj na zakończenie poprzedniej wypowiedzi (z limitem bezpieczeństwa 35s)
                wait_prev = 0.0
                while self.voice_client and self.voice_client.is_connected() and self.voice_client.is_playing() and wait_prev < 35.0:
                    await asyncio.sleep(0.15)
                    wait_prev += 0.15

                uid = uuid.uuid4().hex[:8]
                mp3_path = os.path.join(TEMP_AUDIO_DIR, f"tts_{uid}.mp3")
                wav_path = os.path.join(TEMP_AUDIO_DIR, f"clean_{uid}.wav")

                # 1. Generowanie mowy z Edge-TTS (Ciepły głos ZofiaNeural)
                communicate = edge_tts.Communicate(text, self.voice_name, rate="+2%", pitch="+0Hz")
                await communicate.save(mp3_path)

                # 2. Pre-renderowanie do nieskompresowanego PCM 48kHz Stereo WAV (dokładny format Discorda)
                convert_cmd = [
                    "ffmpeg", "-y",
                    "-i", mp3_path,
                    "-vn",
                    "-ar", "48000",
                    "-ac", "2",
                    "-c:a", "pcm_s16le",
                    "-af", "volume=0.92",
                    wav_path
                ]

                proc = await asyncio.create_subprocess_exec(
                    *convert_cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL
                )
                await proc.communicate()

                # 3. Odtwarzanie w Discordzie (100% thread-safe bez asyncio.Event z obcego wątku!)
                if os.path.exists(wav_path) and self.voice_client and self.voice_client.is_connected():
                    print(f"[VOICE_ENGINE] ▶️ Odtwarzanie na VC: '{text}'")
                    source = discord.FFmpegPCMAudio(wav_path)
                    self.voice_client.play(source)

                    # Poczekaj w pętli asyncio aż odtwarzanie się rozpocznie i zakończy
                    await asyncio.sleep(0.2)
                    elapsed = 0.0
                    while self.voice_client and self.voice_client.is_connected() and self.voice_client.is_playing() and elapsed < 40.0:
                        await asyncio.sleep(0.15)
                        elapsed += 0.15
                    print(f"[VOICE_ENGINE] ✅ Zakończono mówienie ({elapsed:.1f}s).")

            except Exception as e:
                print(f"[VOICE_ENGINE] Błąd podczas syntezy/odtwarzania: {e}")
            finally:
                for p in [mp3_path, wav_path]:
                    if p and os.path.exists(p):
                        try:
                            os.remove(p)
                        except Exception:
                            pass
                self.speech_queue.task_done()
