"""
voice_engine.py - Silnik Głosu i Rozmów na Kanale Głosowym Discord (Edge-TTS + FFmpeg)
======================================================================================
Odpowiada za:
1. Dołączanie do kanałów głosowych Discorda (np. dedykowany kanał "proceed").
2. Krystalicznie czystą, neuronową syntezę polskiej mowy (edge-tts pl-PL-MarekNeural).
3. Płynne odtwarzanie wypowiedzi bota z kolejki audio (zero nakładania się dźwięku).
4. Automatyczne czyszczenie tymczasowych buforów audio.
"""

import os
import asyncio
import uuid
from typing import Optional
import discord
import edge_tts

DEFAULT_VOICE = "pl-PL-MarekNeural"  # Wyrazisty, naturalny polski głos neuronowy
TEMP_AUDIO_DIR = "temp_audio"


class DiscordVoiceEngine:
    def __init__(self, voice_name: str = DEFAULT_VOICE):
        self.voice_name = voice_name
        self.voice_client: Optional[discord.VoiceClient] = None
        self.speech_queue: asyncio.Queue = asyncio.Queue()
        self.is_playing = False
        self._worker_task: Optional[asyncio.Task] = None

        os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

    def start_worker(self, loop: asyncio.AbstractEventLoop):
        """Uruchamia asynchronicznego workera kolejki odtwarzania audio."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = loop.create_task(self._process_queue())

    async def connect(self, channel: discord.VoiceChannel) -> bool:
        """Dołącza bota do wskazanego kanału głosowego (np. 'proceed')."""
        try:
            if self.voice_client and self.voice_client.is_connected():
                if self.voice_client.channel.id == channel.id:
                    return True
                await self.voice_client.move_to(channel)
                return True

            self.voice_client = await channel.connect(reconnect=True, timeout=20.0)
            return True
        except Exception as e:
            print(f"[VOICE_ENGINE] Błąd połączenia z kanałem {channel.name}: {e}")
            return False

    async def disconnect(self):
        """Bezpiecznie odłącza bota z kanału głosowego."""
        try:
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect()
            self.voice_client = None
        except Exception as e:
            print(f"[VOICE_ENGINE] Błąd odłączania: {e}")

    def is_connected(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_connected())

    async def enqueue_speech(self, text: str):
        """Dodaje tekst do kolejki syntezy i odtwarzania na kanale głosowym."""
        clean_text = text.strip()
        if not clean_text:
            return

        # Usuwamy formatowanie markdown (gwiazdki, backticki), które brzmią nienaturalnie przy czytaniu
        clean_text = clean_text.replace("*", "").replace("`", "").replace("#", "").replace("_", "")
        await self.speech_queue.put(clean_text)

    async def _process_queue(self):
        """Asynchroniczny proces pobierający teksty z kolejki i odtwarzający je po kolei."""
        while True:
            text = await self.speech_queue.get()
            try:
                if not self.is_connected():
                    continue

                # 1. Wygeneruj plik audio MP3 za pomocą Edge-TTS
                audio_filename = os.path.join(TEMP_AUDIO_DIR, f"speech_{uuid.uuid4().hex[:8]}.mp3")
                communicate = edge_tts.Communicate(text, self.voice_name)
                await communicate.save(audio_filename)

                # 2. Odtwórz w Discordzie przez FFmpeg
                if self.voice_client and self.voice_client.is_connected():
                    play_done_event = asyncio.Event()

                    def after_playing(err):
                        if err:
                            print(f"[VOICE_ENGINE] Błąd podczas odtwarzania audio: {err}")
                        play_done_event.set()

                    source = discord.FFmpegPCMAudio(audio_filename)
                    # Ustawienie optymalnej głośności
                    audio_source = discord.PCMVolumeTransformer(source, volume=1.1)
                    self.voice_client.play(audio_source, after=after_playing)

                    # Czekaj na zakończenie odtwarzania
                    await play_done_event.wait()

                # 3. Usuń plik tymczasowy
                if os.path.exists(audio_filename):
                    os.remove(audio_filename)

            except Exception as e:
                print(f"[VOICE_ENGINE] Wyjątek podczas syntezy mowy: {e}")
            finally:
                self.speech_queue.task_done()
