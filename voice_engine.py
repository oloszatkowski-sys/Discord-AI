"""
voice_engine.py - Dwukierunkowy Silnik Głosu i Muzyki (STT pl-PL + DAVE E2EE + TTS Zofia + Testy Muzyczne X sek.)
=================================================================================================================
Odpowiada za:
1. Słuchanie użytkowników na kanale głosowym (Speech-to-Text po polsku `pl-PL`):
   - Odbiór pakietów przez `discord-ext-voice-recv` (`VoiceRecvClient`).
   - Deszyfrowanie warstwy DAVE E2EE (`davey==0.1.7`) dla przychodzących pakietów głosowych.
   - Odporność na uszkodzone ramki Opus (brak crashowania wątku `PacketRouter`).
   - Detekcja końca wypowiedzi (VAD) i transkrypcja mowy w chmurze (`SpeechRecognition` Google `pl-PL`).
2. Mówienie ciepłym głosem neuronowym Polskiego ChatGPT (`pl-PL-ZofiaNeural`):
   - Pre-renderowanie do bezstratnego PCM 48kHz Stereo WAV.
3. Odtwarzanie utworów i fragmentów testowych (np. 10 sekund do sprawdzenia czy to ta piosenka) przez `yt-dlp` + `FFmpeg`.
"""

import os
import re
import time
import wave
import uuid
import struct
import asyncio
from typing import Optional, Dict, Any, Callable, Awaitable, Tuple
import discord
import edge_tts

try:
    import davey
    HAS_DAVEY = True
except ImportError:
    HAS_DAVEY = False

try:
    from discord.ext import voice_recv
    from discord.ext.voice_recv.opus import PacketDecoder
    HAS_VOICE_RECV = True
except ImportError:
    HAS_VOICE_RECV = False

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False

try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False

DEFAULT_WARM_VOICE = "pl-PL-ZofiaNeural"
TEMP_AUDIO_DIR = "temp_audio"


# --- PATCH DAVE E2EE DLA ODBIORU GŁOSU (discord-ext-voice-recv) ---
if HAS_VOICE_RECV:
    _orig_decode_packet = PacketDecoder._decode_packet

    def _dave_safe_decode_packet(self, packet):
        """
        Odszyfrowuje warstwę DAVE E2EE (davey) przed dekodowaniem Opus i chroni wątek
        PacketRouter przed jakimkolwiek wyjątkiem OpusError.
        """
        if self._decoder is None:
            return packet, b"\x00" * 3840
        try:
            if packet and getattr(packet, "decrypted_data", None):
                opus_data = bytes(packet.decrypted_data)
                if HAS_DAVEY:
                    vc = getattr(self.sink, "voice_client", None)
                    conn = getattr(vc, "_connection", None) if vc else None
                    dave_sess = getattr(conn, "dave_session", None) if conn else None
                    user_id = self._cached_id or (vc._get_id_from_ssrc(self.ssrc) if vc else None)
                    if dave_sess is not None:
                        if user_id:
                            try:
                                opus_data = dave_sess.decrypt(int(user_id), davey.MediaType.audio, opus_data)
                            except Exception:
                                pass
                        elif vc and getattr(vc, "channel", None):
                            # Kryptograficzna identyfikacja mówiącego (gdy Szatek był już na kanale przed botem i brak ramki SPEAKING)
                            for m in vc.channel.members:
                                if getattr(m, "bot", False):
                                    continue
                                try:
                                    dec = dave_sess.decrypt(int(m.id), davey.MediaType.audio, opus_data)
                                    if dec:
                                        opus_data = dec
                                        self._cached_id = m.id
                                        if hasattr(vc, "_add_ssrc"):
                                            try:
                                                vc._add_ssrc(self.ssrc, m.id)
                                            except Exception:
                                                pass
                                        print(f"[VOICE_DAVE] 🔑 Powiązano mikrofon SSRC {self.ssrc} z: {m.display_name} (ID: {m.id})")
                                        break
                                except Exception:
                                    continue
                pcm = self._decoder.decode(opus_data, fec=False)
                return packet, pcm
            return packet, b"\x00" * 3840
        except Exception:
            # Zwróć 20ms ciszy zamiast przerywać wątek nasłuchiwania
            return packet, b"\x00" * 3840

    PacketDecoder._decode_packet = _dave_safe_decode_packet


def sanitize_text_for_speech(text: str) -> str:
    """Oczyszcza tekst dla syntezatora mowy, usuwając emoji, linki i komendy techniczne."""
    if not text:
        return ""
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"<@!?\d+>|<@&\d+>", "", text)
    text = re.sub(r"`m![^`]+`", "", text)
    text = re.sub(r"[\*`#_~>]", "", text)
    text = re.sub(
        r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\ud83c-\ud83e][\ud000-\udfff]|[\ufe30-\ufe4f\uff00-\uffef]|1️⃣|2️⃣|3️⃣|4️⃣",
        " ",
        text
    )
    text = text.replace("„", "").replace("”", "").replace('"', "")
    text = text.replace("–", ", ").replace("—", ", ").replace("➔", " to ")

    sentences = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    clean_parts = []
    total_len = 0
    for s in sentences:
        s_clean = s.strip()
        if not s_clean:
            continue
        if total_len + len(s_clean) < 280:
            clean_parts.append(s_clean)
            total_len += len(s_clean)
        else:
            break

    result = " ".join(clean_parts).strip()
    return result or text[:220].strip()


def _compute_pcm_rms(pcm_bytes: bytes) -> float:
    """Oblicza średnią głośność (amplitudę) bufora 16-bit PCM, aby odróżnić mowę od ciszy."""
    if not pcm_bytes or len(pcm_bytes) < 400:
        return 0.0
    step = 64
    samples = []
    for i in range(0, len(pcm_bytes) - 2, step):
        val = struct.unpack_from("<h", pcm_bytes, i)[0]
        samples.append(abs(val))
    return (sum(samples) / len(samples)) if samples else 0.0


class DiscordVoiceEngine:
    def __init__(self, voice_name: str = DEFAULT_WARM_VOICE):
        self.voice_name = voice_name or DEFAULT_WARM_VOICE
        self.voice_client: Optional[discord.VoiceClient] = None
        self.speech_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._stt_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Callback wywoływany po rozpoznaniu mowy użytkownika na kanale głosowym: async def cb(member, text)
        self.on_voice_command_callback: Optional[Callable[[discord.Member, str], Awaitable[None]]] = None

        # Bufory audio per użytkownik: user_id -> {"member": member, "chunks": [bytes], "last_ts": float, "start_ts": float}
        self._user_audio_buffers: Dict[int, Dict[str, Any]] = {}
        self._is_playing_music: bool = False

        os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)

    def set_voice_command_callback(self, callback: Callable[[discord.Member, str], Awaitable[None]]):
        """Rejestruje funkcję obsługującą rozpoznaną mowę użytkownika na kanale głosowym."""
        self.on_voice_command_callback = callback

    def start_worker(self, loop: asyncio.AbstractEventLoop):
        """Uruchamia asynchroniczne workery odtwarzania mowy (TTS) oraz nasłuchiwania (STT)."""
        self._loop = loop
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = loop.create_task(self._process_queue())
        if self._stt_task is None or self._stt_task.done():
            self._stt_task = loop.create_task(self._stt_monitor_loop())

    async def connect(self, channel: discord.VoiceChannel) -> bool:
        """Dołącza bota do kanału głosowego z aktywnym nasłuchiwaniem (VoiceRecvClient)."""
        try:
            guild_vc = channel.guild.voice_client
            if guild_vc:
                self.voice_client = guild_vc
                if guild_vc.is_connected():
                    if guild_vc.channel.id == channel.id:
                        self._ensure_listening()
                        return True
                    print(f"[VOICE_ENGINE] Przenoszenie z '{guild_vc.channel.name}' do '{channel.name}'...")
                    await guild_vc.move_to(channel)
                    await asyncio.sleep(0.4)
                    self._ensure_listening()
                    return True
                else:
                    try:
                        await guild_vc.disconnect(force=True)
                    except Exception:
                        pass

            print(f"[VOICE_ENGINE] Łączenie z kanałem głosowym '{channel.name}' (ID: {channel.id})...")
            if HAS_VOICE_RECV:
                self.voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient, reconnect=True, timeout=20.0)
            else:
                self.voice_client = await channel.connect(reconnect=True, timeout=20.0)

            conn = getattr(self.voice_client, "_connection", None)
            wait_dave = 0.0
            while conn and getattr(conn, "dave_protocol_version", 0) > 0 and not getattr(conn, "can_encrypt", False) and wait_dave < 3.0:
                await asyncio.sleep(0.15)
                wait_dave += 0.15
            if conn:
                print(f"[VOICE_ENGINE] 🔒 Status DAVE E2EE: v={getattr(conn, 'dave_protocol_version', 0)}, can_encrypt={getattr(conn, 'can_encrypt', False)}")

            self._ensure_listening()
            return True
        except Exception as e:
            print(f"[VOICE_ENGINE] Błąd połączenia z kanałem {channel.name}: {e}")
            return False

    def _ensure_listening(self):
        """Uruchamia odbiór pakietów głosowych użytkowników na kanale (STT Listener)."""
        if not HAS_VOICE_RECV or not self.voice_client or not self.voice_client.is_connected():
            return
        try:
            if hasattr(self.voice_client, "is_listening") and not self.voice_client.is_listening():
                sink = voice_recv.BasicSink(self._on_incoming_voice_packet)
                self.voice_client.listen(sink)
                print("[VOICE_ENGINE] 👂 Nasłuchiwanie głosu użytkowników na kanale (STT pl-PL) AKTYWNE!")
        except Exception as e:
            print(f"[VOICE_ENGINE] Ostrzeżenie przy uruchamianiu nasłuchiwania: {e}")

    def _on_incoming_voice_packet(self, user: Optional[discord.Member], data: Any):
        """Odbiera zdekodowane ramki PCM 48kHz Stereo od mówiącego użytkownika."""
        pcm = getattr(data, "pcm", None)
        if not pcm:
            return

        # Jeśli user nie został jeszcze rozwiązany przez router, dopasuj go po SSRC lub członkach kanału
        if user is None and self.voice_client and getattr(self.voice_client, "channel", None):
            pkt = getattr(data, "packet", None)
            ssrc = getattr(pkt, "ssrc", None)
            uid_mapped = self.voice_client._get_id_from_ssrc(ssrc) if (ssrc and hasattr(self.voice_client, "_get_id_from_ssrc")) else None
            if uid_mapped:
                user = self.voice_client.guild.get_member(uid_mapped)
            if user is None:
                humans = [m for m in self.voice_client.channel.members if not getattr(m, "bot", False)]
                # Preferuj Szatka jeśli jego SSRC nie było zmapowane
                for h in humans:
                    if "szatek" in (h.display_name or h.name).lower():
                        user = h
                        break
                if user is None and humans:
                    user = humans[0]

        if user is None or getattr(user, "bot", False):
            return

        now = time.monotonic()
        uid = user.id
        buf = self._user_audio_buffers.get(uid)
        if buf is None:
            self._user_audio_buffers[uid] = {
                "member": user,
                "chunks": [pcm],
                "start_ts": now,
                "last_ts": now
            }
        else:
            buf["chunks"].append(pcm)
            buf["last_ts"] = now
            buf["member"] = user

    async def _stt_monitor_loop(self):
        """Monitoruje bufory głosowe użytkowników i po wykryciu końca wypowiedzi uruchamia STT po polsku."""
        while True:
            await asyncio.sleep(0.20)
            try:
                if not self._user_audio_buffers:
                    continue

                now = time.monotonic()
                ready_uids = []
                for uid, buf in list(self._user_audio_buffers.items()):
                    silence_dur = now - buf["last_ts"]
                    total_dur = buf["last_ts"] - buf["start_ts"]
                    # Szybsza reakcja: 0.80s ciszy lub 10s ciągłej wypowiedzi
                    if silence_dur >= 0.80 or total_dur >= 10.0:
                        ready_uids.append(uid)

                for uid in ready_uids:
                    buf = self._user_audio_buffers.pop(uid, None)
                    if not buf:
                        continue
                    raw_pcm = b"".join(buf["chunks"])
                    member = buf["member"]
                    # Obniżony próg długości (~0.18s) oraz RMS (25.0), aby łapać nawet krótkie i ciche słowa Szatka
                    if len(raw_pcm) < 34000:
                        continue
                    rms = _compute_pcm_rms(raw_pcm)
                    if rms < 25.0:
                        continue

                    asyncio.create_task(self._transcribe_and_dispatch(member, raw_pcm))
            except Exception as e:
                print(f"[VOICE_ENGINE] Błąd w pętli STT: {e}")

    async def _transcribe_and_dispatch(self, member: discord.Member, raw_pcm: bytes):
        """Wzmacnia cichy mikrofon (Auto-Gain Control), zamienia na tekst po polsku (pl-PL) i przekazuje do Polskiego ChatGPT."""
        if not HAS_SR:
            return
        import array
        wav_path = os.path.join(TEMP_AUDIO_DIR, f"stt_{uuid.uuid4().hex[:8]}.wav")
        try:
            def _save_and_recognize() -> Optional[str]:
                pcm_to_write = raw_pcm
                try:
                    # Auto-Gain Control (AGC): wzmocnij cichy mikrofon (np. Szatka) do poziomu studyjnego!
                    samples = array.array("h", raw_pcm)
                    max_peak = max((abs(x) for x in samples[::4]), default=0)
                    if 15 < max_peak < 18000:
                        gain = min(26000.0 / max_peak, 14.0)
                        samples = array.array("h", (max(-32767, min(32767, int(x * gain))) for x in samples))
                        pcm_to_write = samples.tobytes()
                except Exception:
                    pass

                with wave.open(wav_path, "wb") as wf:
                    wf.setnchannels(2)
                    wf.setsampwidth(2)
                    wf.setframerate(48000)
                    wf.writeframes(pcm_to_write)

                recognizer = sr.Recognizer()
                with sr.AudioFile(wav_path) as source:
                    audio_data = recognizer.record(source)
                return recognizer.recognize_google(audio_data, language="pl-PL")

            loop = asyncio.get_running_loop()
            recognized_text = await loop.run_in_executor(None, _save_and_recognize)
            if recognized_text and len(recognized_text.strip()) >= 2:
                clean_txt = recognized_text.strip()
                print(f"[VOICE_STT] 🎙️ Usłyszano od {member.display_name}: '{clean_txt}'")
                if self.on_voice_command_callback:
                    await self.on_voice_command_callback(member, clean_txt)
        except sr.UnknownValueError:
            # Szum lub niezrozumiałe mruknięcie – ignoruj
            pass
        except Exception as e:
            print(f"[VOICE_STT] Ostrzeżenie transkrypcji: {e}")
        finally:
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception:
                    pass

    async def disconnect(self):
        """Bezpiecznie odłącza bota z kanału głosowego."""
        try:
            self._is_playing_music = False
            if self.voice_client:
                await self.voice_client.disconnect(force=True)
            self.voice_client = None
        except Exception as e:
            print(f"[VOICE_ENGINE] Błąd odłączania: {e}")

    def is_connected(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_connected())

    def stop_audio(self):
        """Zatrzymuje aktualnie odtwarzaną muzykę lub mowę na kanale głosowym."""
        self._is_playing_music = False
        if self.voice_client and self.voice_client.is_connected() and self.voice_client.is_playing():
            self.voice_client.stop()

    async def play_music_preview(self, song_query: str, duration_sec: Optional[int] = None) -> bool:
        """
        Dodaje utwór muzyczny do głównej kolejki audio (odtwarzany zaraz po zapowiedzi głosowej TTS!),
        pobierając go z SoundCloud / Deezer CDN / iTunes CDN / YouTube.
        """
        if not self.is_connected():
            return False

        await self.speech_queue.put({
            "type": "MUSIC",
            "query": song_query,
            "duration_sec": duration_sec
        })
        print(f"[VOICE_MUSIC] 📥 Dodano utwór do kolejki odtwarzania: '{song_query}' (czas: {duration_sec or 'całość'}s)")
        return True

    def _resolve_music_stream_sync(self, song_query: str) -> Optional[Tuple[str, str]]:
        """
        Wyszukuje bezpośredni strumień audio (100% odporne na blokady IP GitHub Actions):
        1. SoundCloud (scsearch1 przez yt-dlp - pełne utwory bez blokad botów)
        2. Deezer Public API (błyskawiczny MP3 z CDN)
        3. iTunes Search API (błyskawiczny M4A z CDN Apple)
        4. YouTube (ytsearch1 fallback)
        """
        import urllib.request
        import urllib.parse
        import json

        # 1. Próba Deezer Public API (0.15s, krystaliczny MP3 CDN)
        try:
            q_enc = urllib.parse.quote(song_query)
            req = urllib.request.Request(
                f"https://api.deezer.com/search?q={q_enc}&limit=1",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
                if data.get("data"):
                    item = data["data"][0]
                    preview_url = item.get("preview")
                    title = f"{item.get('title', song_query)} - {item.get('artist', {}).get('name', '')}".strip(" -")
                    if preview_url:
                        return preview_url, title
        except Exception as e:
            print(f"[VOICE_MUSIC] Deezer fallback info: {e}")

        # 2. Próba iTunes Search API (0.15s, M4A CDN)
        try:
            q_enc = urllib.parse.quote(song_query)
            req = urllib.request.Request(
                f"https://itunes.apple.com/search?term={q_enc}&media=music&limit=1",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
                if data.get("results"):
                    item = data["results"][0]
                    preview_url = item.get("previewUrl")
                    title = f"{item.get('trackName', song_query)} - {item.get('artistName', '')}".strip(" -")
                    if preview_url:
                        return preview_url, title
        except Exception as e:
            print(f"[VOICE_MUSIC] iTunes fallback info: {e}")

        # 3. Próba SoundCloud oraz YouTube przez yt-dlp
        if HAS_YTDLP:
            for prefix in ["scsearch1", "ytsearch1"]:
                try:
                    ydl_opts = {
                        "format": "bestaudio/best",
                        "noplaylist": True,
                        "quiet": True
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(f"{prefix}:{song_query}", download=False)
                        entry = info["entries"][0] if ("entries" in info and info["entries"]) else info
                        if entry and entry.get("url"):
                            return entry["url"], entry.get("title", song_query)
                except Exception:
                    pass

        return None

    async def enqueue_speech(self, text: str):
        """Dodaje oczyszczony tekst do kolejki syntezy mowy."""
        clean_speech = sanitize_text_for_speech(text)
        if not clean_speech or len(clean_speech) < 2:
            return

        if self.speech_queue.qsize() > 10:
            try:
                self.speech_queue.get_nowait()
                self.speech_queue.task_done()
            except Exception:
                pass

        print(f"[VOICE_ENGINE] 📥 Dodano do kolejki mowy: '{clean_speech}'")
        await self.speech_queue.put(clean_speech)

    async def _process_queue(self):
        """Pobiera elementy z kolejki (mowę TTS lub utwory muzyczne), konwertuje do WAV 48kHz stereo i odtwarza po kolei."""
        while True:
            item = await self.speech_queue.get()
            mp3_path = None
            wav_path = None
            try:
                wait_conn = 0.0
                while not self.is_connected() and wait_conn < 3.0:
                    await asyncio.sleep(0.2)
                    wait_conn += 0.2

                if not self.is_connected():
                    continue

                # Poczekaj na zakończenie poprzedniego dźwięku
                wait_prev = 0.0
                while self.voice_client and self.voice_client.is_connected() and self.voice_client.is_playing() and wait_prev < 45.0:
                    await asyncio.sleep(0.15)
                    wait_prev += 0.15

                uid = uuid.uuid4().hex[:8]
                wav_path = os.path.join(TEMP_AUDIO_DIR, f"clean_{uid}.wav")

                # A. ODTWARZANIE UTWORU MUZYCZNEGO LUB TESTU X SEKUND
                if isinstance(item, dict) and item.get("type") == "MUSIC":
                    song_query = item.get("query", "")
                    duration_sec = item.get("duration_sec")
                    loop = asyncio.get_running_loop()
                    stream_info = await loop.run_in_executor(None, self._resolve_music_stream_sync, song_query)
                    if not stream_info or not stream_info[0]:
                        print(f"[VOICE_MUSIC] ❌ Nie znaleziono strumienia dla: '{song_query}'")
                        continue

                    stream_url, track_title = stream_info
                    play_dur = int(duration_sec) if duration_sec else 30
                    print(f"[VOICE_MUSIC] 🎵 Konwersja i odtwarzanie na VC: '{track_title}' ({play_dur}s)")

                    convert_cmd = [
                        "ffmpeg", "-y",
                        "-i", stream_url,
                        "-vn",
                        "-t", str(play_dur),
                        "-ar", "48000",
                        "-ac", "2",
                        "-c:a", "pcm_s16le",
                        "-af", "volume=0.82",
                        wav_path
                    ]
                    proc = await asyncio.create_subprocess_exec(
                        *convert_cmd,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL
                    )
                    await proc.communicate()

                    if os.path.exists(wav_path) and self.voice_client and self.voice_client.is_connected():
                        self._is_playing_music = True
                        source = discord.FFmpegPCMAudio(wav_path)
                        self.voice_client.play(source)
                        await asyncio.sleep(0.2)
                        elapsed = 0.0
                        while self.voice_client and self.voice_client.is_connected() and self.voice_client.is_playing() and elapsed < (play_dur + 5.0):
                            await asyncio.sleep(0.2)
                            elapsed += 0.2
                        self._is_playing_music = False
                        print(f"[VOICE_MUSIC] ✅ Zakończono odtwarzanie utworu '{track_title}' ({elapsed:.1f}s).")

                        if duration_sec:
                            await self.enqueue_speech(
                                f"Minęło {duration_sec} sekund testu utworu {track_title}! I jak, to jest ta piosenka, o którą Ci chodziło?"
                            )
                    continue

                # B. ODTWARZANIE MOWY TTS (Ciepły głos Zofii)
                text = str(item)
                mp3_path = os.path.join(TEMP_AUDIO_DIR, f"tts_{uid}.mp3")

                communicate = edge_tts.Communicate(text, self.voice_name, rate="+2%", pitch="+0Hz")
                await communicate.save(mp3_path)

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

                if os.path.exists(wav_path) and self.voice_client and self.voice_client.is_connected():
                    print(f"[VOICE_ENGINE] ▶️ Odtwarzanie na VC: '{text}'")
                    source = discord.FFmpegPCMAudio(wav_path)
                    self.voice_client.play(source)

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
