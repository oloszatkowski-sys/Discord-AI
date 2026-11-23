"""
voice_engine.py - Silnik Ciepłego Głosu i Rozmów Głosowych (Edge-TTS ZofiaNeural + FFmpeg)
========================================================================================
Odpowiada za:
1. Ciepły, naturalny, ludzki głos neuronowy w stylu ChatGPT (pl-PL-ZofiaNeural).
2. Płynne odtwarzanie audio bez nakładania się i bez błędów 'Already playing'.
3. Automatyczne dołączanie i przełączanie między kanałami głosowymi Discorda.
"""

import os
import asyncio
import uuid
import re
from typing import Optional
import discord
import edge_tts

# Najcieplejszy, najbardziej naturalny i empatyczny polski głos neuronowy (odpowiednik głosu ChatGPT)
DEFAULT_WARM_VOICE = "pl-PL-ZofiaNeural"
TEMP_AUDIO_DIR = "temp_audio"


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
        """Dołącza bota do wskazanego kanału głosowego lub przenosi go, jeśli już jest połączony."""
        try:
            if self.voice_client and self.voice_client.is_connected():
                if self.voice_client.channel.id == channel.id:
                    return True
                print(f"[VOICE_ENGINE] Przenoszenie z '{self.voice_client.channel.name}' do '{channel.name}'...")
                await self.voice_client.move_to(channel)
                return True

            print(f"[VOICE_ENGINE] Łączenie z kanałem głosowym '{channel.name}' (ID: {channel.id})...")
            self.voice_client = await channel.connect(reconnect=True, timeout=20.0)
            return True
        except Exception as e:
            print(f"[VOICE_ENGINE] Błąd połączenia z kanałem {channel.name}: {e}")
            return False

    async def disconnect(self):
        """Bezpiecznie odłącza bota z kanału głosowego."""
        try:
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect(force=True)
            self.voice_client = None
        except Exception as e:
            print(f"[VOICE_ENGINE] Błąd odłączania: {e}")

    def is_connected(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_connected())

    async def enqueue_speech(self, text: str):
        """Dodaje tekst do kolejki syntezy z ciepłym głosem."""
        clean_text = text.strip()
        if not clean_text:
            return

        # Ograniczenie długości pojedynczej wypowiedzi dla płynności rozmowy (max 350 znaków)
        if len(clean_text) > 350:
            clean_text = clean_text[:347] + "..."

        if self.speech_queue.qsize() > 6:
            print("[VOICE_ENGINE] Kolejka audio pełna – pomijam wypowiedź.")
            return

        # Oczyszczenie formatowania markdown
        clean_text = clean_text.replace("*", "").replace("`", "").replace("#", "").replace("_", "").replace("~", "")
        clean_text = re.sub(r"<@!?\d+>", "", clean_text).strip()
        if clean_text:
            await self.speech_queue.put(clean_text)

    async def _process_queue(self):
        """Pobiera teksty z kolejki i odtwarza je po kolei ciepłym głosem."""
        while True:
            text = await self.speech_queue.get()
            audio_filename = None
            try:
                if not self.is_connected():
                    await asyncio.sleep(0.5)
                    continue

                # Czekaj jeśli aktualnie coś jeszcze jest odtwarzane
                while self.voice_client and self.voice_client.is_connected() and self.voice_client.is_playing():
                    await asyncio.sleep(0.15)

                # 1. Wygeneruj ciepły głos neuronowy za pomocą Edge-TTS
                audio_filename = os.path.join(TEMP_AUDIO_DIR, f"warm_{uuid.uuid4().hex[:8]}.mp3")
                # pl-PL-ZofiaNeural ma wyjątkowo ciepłe, naturalne i przyjazne brzmienie
                communicate = edge_tts.Communicate(text, self.voice_name, rate="+3%", pitch="+0Hz")
                await communicate.save(audio_filename)

                # 2. Odtwórz w Discordzie przez FFmpeg
                if self.voice_client and self.voice_client.is_connected():
                    play_done_event = asyncio.Event()

                    def after_playing(err):
                        if err:
                            print(f"[VOICE_ENGINE] Błąd odtwarzania FFmpeg: {err}")
                        play_done_event.set()

                    source = discord.FFmpegPCMAudio(audio_filename, options="-vn")
                    audio_source = discord.PCMVolumeTransformer(source, volume=1.15)
                    self.voice_client.play(audio_source, after=after_playing)

                    await play_done_event.wait()

            except Exception as e:
                print(f"[VOICE_ENGINE] Wyjątek podczas syntezy ciepłego głosu: {e}")
            finally:
                if audio_filename and os.path.exists(audio_filename):
                    try:
                        os.remove(audio_filename)
                    except Exception:
                        pass
                self.speech_queue.task_done()
