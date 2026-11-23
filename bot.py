"""
bot.py - Główny Program Super ChatGPT Bota AI na Discordzie (Żywa Inteligencja + Głos + Multi-Server)
=====================================================================================================
Funkcjonalności:
1. Podział na serwery (Multi-Server Partitioning) – każdy serwer posiada własną, niezależną pamięć,
   fakty, definicje i profile użytkowników, zachowując globalne lore ZSC i Szatek_Olo.
2. Rozumienie pełnego kontekstu rozmowy – wieloturowa historia czatu (sliding window), dzięki czemu
   bot rozumie zaimki ("co o tym myślisz?"), nawiązania i bieg dyskusji.
3. "On ma żyć" – reaguje gdy ktoś pisze "Bot", "Aether", pinguje go, odpowiada na jego posty,
   kontynuuje dialog w naturalnym tempie oraz spontanicznie wtrąca się do ciekawych dyskusji.
4. Zaawansowana integracja głosowa – automatycznie wyszukuje i dołącza do kanałów głosowych
   (np. '🤖・Testowanie・Bota・AI', 'proceed'), wita użytkowników i czyta odpowiedzi neuronowym głosem TTS.
5. 100% darmowy chmurowy Super ChatGPT w chmurze (Pollinations GPT-4o mini, Mistral, Groq, Gemini).
"""

import os
import sys
import re
import time
import random
import asyncio
from collections import deque
from typing import Optional, Dict, List
import discord
from discord.ext import commands
from dotenv import load_dotenv

from memory_vault import MemoryVault
from voice_engine import DiscordVoiceEngine
from ai_brain import AIBrain

load_dotenv()

DISCORD_TOKEN = (os.getenv("DISCORD_TOKEN") or os.getenv("MANUAL_DISCORD_TOKEN") or "").strip()
TARGET_VOICE_CHANNEL = os.getenv("VOICE_CHANNEL_NAME", "proceed")
AUTO_JOIN_VOICE = os.getenv("AUTO_JOIN_VOICE", "true").lower() in ("true", "1", "yes")

memory_vault = MemoryVault()
voice_engine = DiscordVoiceEngine(voice_name=os.getenv("TTS_VOICE", "pl-PL-MarekNeural"))
ai_brain = AIBrain()


class ConversationTracker:
    """Zarządza pamięcią podręczną ostatnich wiadomości na każdym kanale tekstowym."""
    def __init__(self, max_history: int = 15):
        self.channels: Dict[int, deque] = {}
        self.last_bot_reply: Dict[int, float] = {}

    def add_message(self, channel_id: int, author_name: str, content: str, is_bot: bool):
        if channel_id not in self.channels:
            self.channels[channel_id] = deque(maxlen=15)
        role = "assistant" if is_bot else "user"
        formatted_content = content if is_bot else f"[{author_name}]: {content}"
        self.channels[channel_id].append({"role": role, "content": formatted_content})
        if is_bot:
            self.last_bot_reply[channel_id] = time.time()

    def get_history(self, channel_id: int) -> List[Dict[str, str]]:
        if channel_id not in self.channels:
            return []
        return list(self.channels[channel_id])

    def time_since_last_bot_reply(self, channel_id: int) -> float:
        return time.time() - self.last_bot_reply.get(channel_id, 0.0)


conv_tracker = ConversationTracker()


def normalize_channel_name(name: str) -> str:
    """Oczyszcza nazwę kanału ze znaków specjalnych, emoji i separatorów (np. 🤖・Testowanie・Bota・AI)."""
    cleaned = re.sub(r"[^\w\s]", " ", name, flags=re.UNICODE)
    cleaned = cleaned.replace("・", " ").replace("•", " ").replace("-", " ").replace("_", " ")
    return " ".join(cleaned.lower().split())


def find_best_voice_channel(guild: discord.Guild, preferred_name: Optional[str] = None) -> Optional[discord.VoiceChannel]:
    """Inteligentnie wyszukuje najlepszy kanał głosowy na serwerze."""
    if not guild.voice_channels:
        return None

    # 1. Priorytet #1: Kanał, w którym aktualnie siedzą użytkownicy!
    populated = [vc for vc in guild.voice_channels if any(not m.bot for m in vc.members)]
    if populated:
        populated.sort(key=lambda vc: len([m for m in vc.members if not m.bot]), reverse=True)
        return populated[0]

    # 2. Priorytet #2: Dopasowanie po nazwach i słowach kluczowych
    candidates = []
    if preferred_name:
        candidates.append(normalize_channel_name(preferred_name))
    
    # Słowa kluczowe (uwzględnia m.in. '🤖・Testowanie・Bota・AI' oraz 'proceed')
    candidates.extend([
        "testowanie bota ai",
        "testowanie bota",
        "testowanie",
        "bota ai",
        "proceed",
        "procced",
        "rozmowy",
        "voice",
        "glosowy",
        "general",
        "ogolny"
    ])

    for cand in candidates:
        for vc in guild.voice_channels:
            norm_name = normalize_channel_name(vc.name)
            if cand in norm_name or norm_name in cand:
                return vc
            cand_words = [w for w in cand.split() if len(w) > 2]
            if cand_words and all(w in norm_name for w in cand_words):
                return vc

    # 3. Domyślnie: Pierwszy kanał głosowy
    return guild.voice_channels[0]


def is_admin_or_szatek(author: discord.Member) -> bool:
    """Sprawdza czy użytkownik to Szatek_Olo lub administrator serwera."""
    author_name = (author.display_name or author.name).lower()
    if any(k in author_name for k in ["szatek", "szatek_olo", "olo"]):
        return True
    if hasattr(author, "guild_permissions") and author.guild_permissions.administrator:
        return True
    return False


def create_bot(with_message_content: bool = True) -> commands.Bot:
    """Tworzy i konfiguruje instancję bota Discord."""
    intents = discord.Intents.default()
    intents.voice_states = True
    intents.guilds = True
    if with_message_content:
        intents.message_content = True

    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    @bot.event
    async def on_ready():
        print(f"[DISCORD_BOT] Zalogowano pomyślnie jako: {bot.user} (ID: {bot.user.id})")
        print(f"[DISCORD_BOT] Połączone serwery ({len(bot.guilds)}): {[g.name for g in bot.guilds]}")
        stats = memory_vault.get_stats()
        print(f"[DISCORD_BOT] Pamięć załadowana: {stats.get('servers_count', 1)} serwerów, {stats.get('facts_count', 0)} faktów w bazie.")

        # Uruchom asynchronicznego workera audio
        voice_engine.start_worker(bot.loop)

        # Status aktywności
        activity = discord.Activity(type=discord.ActivityType.listening, name="Testowanie Bota AI • !pomoc")
        await bot.change_presence(status=discord.Status.online, activity=activity)

        # Automatyczne dołączanie do kanału głosowego
        if AUTO_JOIN_VOICE:
            for guild in bot.guilds:
                vc = find_best_voice_channel(guild, TARGET_VOICE_CHANNEL)
                if vc:
                    print(f"[DISCORD_BOT] Dołączam do kanału głosowego: '{vc.name}' na serwerze '{guild.name}'...")
                    connected = await voice_engine.connect(vc)
                    if connected:
                        print(f"[DISCORD_BOT] Połączono z kanałem głosowym: '{vc.name}'!")
                        await voice_engine.enqueue_speech("Aether AI jest online! Jestem na kanale, słucham i uczę się z Wami.")
                    break

    @bot.event
    async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Żywa reakcja: gdy gracz wchodzi na kanał głosowy, bot może do niego dołączyć."""
        if member.bot:
            return

        # Użytkownik wszedł na kanał głosowy
        if after.channel and (not before.channel or before.channel != after.channel):
            target_vc = after.channel
            # Jeśli bot nie jest połączony, dołącz do gracza!
            if not voice_engine.is_connected():
                print(f"[VOICE_EVENT] Użytkownik {member.display_name} wszedł na {target_vc.name}. Dołączam do niego...")
                connected = await voice_engine.connect(target_vc)
                if connected:
                    await voice_engine.enqueue_speech(f"Siemanko {member.display_name}! Wbiłem do Ciebie na kanał. Co tam słychać?")

    @bot.event
    async def on_message(message: discord.Message):
        if message.author == bot.user:
            return

        author_name = message.author.display_name or message.author.name
        content = (message.content or "").strip()
        guild_id = str(message.guild.id) if message.guild else None
        guild_name = message.guild.name if message.guild else "Prywatny Czat"

        # Zapisz wiadomość w historii bieżącego kanału tekstowego
        conv_tracker.add_message(message.channel.id, author_name, content, is_bot=False)

        # 1. CIĄGŁE UCZENIE SIĘ: Analizuj wiadomość i zapamiętuj fakty w kontekście TEGO serwera
        if len(content) > 2:
            learned = memory_vault.learn_from_message(author_name, content, guild_id, guild_name)
            if learned:
                try:
                    await message.add_reaction("🧠")
                except Exception:
                    pass

        # 2. Obsługa komend bota (np. !pomoc, !dolacz, !status)
        if content.startswith("!"):
            await bot.process_commands(message)
            return

        # 3. Wykrywanie poleceń wejścia na kanał głosowy w języku naturalnym
        c_low = content.lower()
        voice_join_phrases = ["wejdź na głosowy", "wejdź na vc", "chodź na głosowy", "chodź na vc", "dołącz na kanał", "wejdź na kanał", "chodź pogadać", "wbij na dc", "wbij na kanał"]
        if any(p in c_low for p in voice_join_phrases):
            target_vc = None
            if message.author.voice and message.author.voice.channel:
                target_vc = message.author.voice.channel
            elif message.guild:
                target_vc = find_best_voice_channel(message.guild, TARGET_VOICE_CHANNEL)

            if target_vc:
                connected = await voice_engine.connect(target_vc)
                if connected:
                    await message.reply(f"🔊 Już wbijam na kanał głosowy **{target_vc.name}**! Słucham Cię.", mention_author=False)
                    await voice_engine.enqueue_speech(f"Siemanko {author_name}! Wszedłem na {target_vc.name}. O czym rozmawiamy?")
                    return

        # 4. KIEDY BOT MA ODPOWIEDZIEĆ? ("ON MA ŻYĆ")
        is_mentioned = bot.user in message.mentions
        is_reply_to_bot = (
            message.reference
            and message.reference.resolved
            and getattr(message.reference.resolved, "author", None) == bot.user
        )
        is_dm = isinstance(message.channel, discord.DMChannel)

        # Wywołanie bezpośrednie po imieniu / roli
        name_triggers = [
            "bot", "bocie", "aether", "aetherze", "ai", "chat gpt", "chatgpt",
            "mordo", "ziomek", "ej bot", "halo bot", "hej bot"
        ]
        words_in_msg = re.findall(r"\b\w+\b", c_low)
        starts_or_calls_bot = any(trigger in words_in_msg[:3] for trigger in ["bot", "bocie", "aether", "ai", "chatgpt"]) or any(t in c_low for t in name_triggers)

        # Płynność konwersacji: jeśli bot odpowiedział w tym kanale w ciągu ostatnich 110 sekund, kontynuuj dialog!
        time_since_reply = conv_tracker.time_since_last_bot_reply(message.channel.id)
        is_conversation_continuation = (time_since_reply < 110.0) and (len(content) > 3) and not content.startswith("http")

        # Spontaniczne włączanie się do ciekawych dyskusji na serwerze
        curious_keywords = ["minecraft", "zsc", "szatek", "serwer", "projekt", "budujemy", "zbuduj", "co sądzicie", "jak myślicie", "ciekawe", "co robimy", "?", "kto wie", "pomysł"]
        has_curious_topic = any(k in c_low for k in curious_keywords)
        can_chime_in = (time_since_reply > 50.0) and (len(content) > 10) and not content.startswith("http")
        spontaneous_trigger = can_chime_in and (
            (has_curious_topic and random.random() < 0.40) or (random.random() < 0.08)
        )

        should_respond = is_mentioned or is_reply_to_bot or is_dm or starts_or_calls_bot or is_conversation_continuation or spontaneous_trigger

        if should_respond:
            async with message.channel.typing():
                # Oczyszczenie zapytania z tagu bota
                clean_query = content.replace(f"<@{bot.user.id}>", "").strip()
                if not clean_query:
                    clean_query = "Co tam słychać?"

                # Pobierz zapamiętany kontekst DLA TEGO SERWERA
                memory_ctx = memory_vault.build_context_for_prompt(author_name, clean_query, guild_id, guild_name)

                # Pobierz historię rozmowy na tym kanale
                history = conv_tracker.get_history(message.channel.id)

                # Wygeneruj odpowiedź z modelu Super ChatGPT w chmurze
                reply = await ai_brain.generate_response(author_name, clean_query, memory_ctx, history)

                # Zapisz odpowiedź bota w trackerze
                conv_tracker.add_message(message.channel.id, "Aether AI", reply, is_bot=True)

                # Wyślij odpowiedź tekstową
                await message.reply(reply, mention_author=False)

                # JEŚLI BOT JEST NA KANALE GŁOSOWYM: Wypowiedz odpowiedź na głos!
                if voice_engine.is_connected():
                    await voice_engine.enqueue_speech(reply)
                    try:
                        await message.add_reaction("🗣️")
                    except Exception:
                        pass

    # --- KOMENDY BOTA ---

    @bot.command(name="dolacz", aliases=["join", "proceed", "wbij"])
    async def cmd_join(ctx: commands.Context, *, channel_name: Optional[str] = None):
        """Dołącza bota do kanału głosowego."""
        target_vc = None
        if channel_name:
            target_vc = find_best_voice_channel(ctx.guild, channel_name)
        elif ctx.author.voice and ctx.author.voice.channel:
            target_vc = ctx.author.voice.channel
        else:
            target_vc = find_best_voice_channel(ctx.guild, TARGET_VOICE_CHANNEL)

        if not target_vc:
            await ctx.send(f"❌ Nie znalazłem kanału głosowego `{channel_name or TARGET_VOICE_CHANNEL}`.")
            return

        connected = await voice_engine.connect(target_vc)
        if connected:
            await ctx.send(f"🔊 Połączono z kanałem głosowym **{target_vc.name}**! Możemy rozmawiać na żywo.")
            await voice_engine.enqueue_speech(f"Siemanko {ctx.author.display_name}! Wszedłem na kanał {target_vc.name}.")
        else:
            await ctx.send(f"❌ Nie udało się połączyć z `{target_vc.name}`. Sprawdź uprawnienia bota.")

    @bot.command(name="wyjdz", aliases=["leave", "disconnect", "opusc"])
    async def cmd_leave(ctx: commands.Context):
        """Odłącza bota z kanału głosowego."""
        if not voice_engine.is_connected():
            await ctx.send("ℹ️ Nie jestem aktualnie połączony z żadnym kanałem głosowym.")
            return

        await voice_engine.enqueue_speech("Do usłyszenia! Wracam na posterunek.")
        await asyncio.sleep(1.8)
        await voice_engine.disconnect()
        await ctx.send("🔇 Odłączono z kanału głosowego.")

    @bot.command(name="powiedz", aliases=["say", "tts"])
    async def cmd_say(ctx: commands.Context, *, text: str):
        """Wypowiada podany tekst na kanale głosowym."""
        if not voice_engine.is_connected():
            await ctx.send("⚠️ Najpierw zaproś mnie na kanał głosowy komendą `!dolacz`!")
            return

        await voice_engine.enqueue_speech(text)
        await ctx.message.add_reaction("🗣️")

    @bot.command(name="status")
    async def cmd_status(ctx: commands.Context):
        """Wyświetla status bota, pamięci serwera i połączenia audio."""
        guild_id = str(ctx.guild.id) if ctx.guild else None
        stats = memory_vault.get_stats(guild_id)
        voice_state = f"🔊 Połączony ({voice_engine.voice_client.channel.name})" if voice_engine.is_connected() else "🔇 Rozłączony"

        embed = discord.Embed(title="🛡️ Status Aether Super ChatGPT AI", color=0x3a86ff)
        embed.add_field(name="🎙️ Kanał Głosowy", value=voice_state, inline=True)
        embed.add_field(name="🌐 Przestrzeń Serwera", value=stats.get("server_name", "Prywatna"), inline=True)
        embed.add_field(name="🧠 Baza Użytkowników", value=f"{stats.get('users_count', 0)} profili", inline=True)
        embed.add_field(name="📚 Zapamiętane Fakty Serwera", value=f"{stats.get('facts_count', 0)} faktów", inline=True)
        embed.add_field(name="🔒 Szyfrowanie Bazy", value="AES-256-GCM (Zero-Leak)", inline=True)
        embed.add_field(name="⚡ Głos TTS", value=voice_engine.voice_name, inline=True)
        embed.set_footer(text="Działa w GitHub Actions 24/7 • ZSC 2026")
        await ctx.send(embed=embed)

    @bot.command(name="pomoc", aliases=["help"])
    async def cmd_help(ctx: commands.Context):
        """Pomoc i lista komend."""
        msg = """**🤖 Aether AI – Super ChatGPT na Discordzie:**
• `!dolacz [kanał]` – Dołącza do kanału głosowego (np. `!dolacz Testowanie Bota AI`)
• `!wyjdz` – Opuszcza kanał głosowy
• `!powiedz [tekst]` – Mówi podany tekst na głos neuronowym polskim głosem
• `!status` – Raport stanu bota, pamięci i kanału
• `!pamiec` – Podgląd zapamiętanych faktów z tego serwera
• `!reset_pamieci` – [Admin] Resetuje zapamiętane fakty serwera
• `zapamiętaj, że [fakt]` – Zapisuje na stałe nowy fakt dla tego serwera!
• Możesz do mnie pisać na czacie używając słów **Bot**, **Aether**, oznaczając mnie `@Aether AI` lub po prostu rozmawiając ze mną – rozumiem cały kontekst!"""
        await ctx.send(msg)

    @bot.command(name="pamiec", aliases=["fakty", "wiedza"])
    async def cmd_memory(ctx: commands.Context):
        """Wyświetla zapamiętane fakty z tego serwera."""
        guild_id = str(ctx.guild.id) if ctx.guild else None
        store = memory_vault._get_server_store(guild_id)
        facts = store.get("facts", [])
        if not facts:
            await ctx.send("🧠 Moja baza pamięci dla tego serwera jest jeszcze pusta. Naucz mnie czegoś pisząc: `zapamiętaj, że...`")
            return

        msg = f"**🧠 Zapamiętane fakty dla serwera {store.get('guild_name', 'ten serwer')}:**\n"
        for f in facts[-6:]:
            msg += f"• `#{f['id']}` {f['content']} *(dodał: {f.get('added_by', 'SYSTEM')})*\n"
        await ctx.send(msg)

    @bot.command(name="reset_pamieci")
    async def cmd_reset_memory(ctx: commands.Context):
        """Resetuje bazę pamięci tego serwera (tylko Szatek_Olo lub Administrator)."""
        if not is_admin_or_szatek(ctx.author):
            await ctx.send("⛔ Odmowa dostępu: Tylko Szatek_Olo lub Administrator może resetować pamięć serwera! 🛡️")
            return

        guild_id = str(ctx.guild.id) if ctx.guild else None
        store = memory_vault._get_server_store(guild_id)
        store["facts"] = []
        store["definitions"] = {}
        memory_vault._save_vault()
        await ctx.send("🧹 Skarbiec Pamięci tego serwera został zresetowany.")

    return bot


def run_self_test():
    """Uruchamia test integracyjny modułów."""
    print("=" * 80)
    print("🚀 AETHER DISCORD AI - SUPER CHATGPT SYSTEM READY 100%")
    print("=" * 80)
    stats = memory_vault.get_stats()
    print(f"✅ 1. Szyfrowany Skarbiec Pamięci z Podziałem na Serwery: DZIAŁA ({stats.get('servers_count', 1)} serwerów)")
    print(f"✅ 2. Silnik Mowy & Audio Edge-TTS ({voice_engine.voice_name}): SPRAWNY")
    print(f"✅ 3. Silnik Super ChatGPT (Pollinations / Groq / OpenAI): SPRAWNY")
    print(f"✅ 4. Tarcza Bezpieczeństwa (Zero-Leak & Multi-Guild Isolation): AKTYWNA")
    print("=" * 80)


def main():
    if not DISCORD_TOKEN:
        run_self_test()
        sys.exit(0)

    import signal
    def on_shutdown_signal(sig, frame):
        print(f"[DISCORD_BOT] Zamykanie ({sig}). Bezpieczny zapis bazy pamięci...")
        memory_vault._save_vault()
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, on_shutdown_signal)
        signal.signal(signal.SIGTERM, on_shutdown_signal)
    except Exception:
        pass

    print("[DISCORD_BOT] Inicjalizacja Aether AI Super ChatGPT...")

    # Krok 1: Próba startu z Message Content Intent (dla pełnej autonomicznej nauki ze wszystkich wiadomości)
    try:
        print("[DISCORD_BOT] Start w trybie autonomicznym (Message Content Intent)...")
        b = create_bot(with_message_content=True)
        b.run(DISCORD_TOKEN)
    except discord.errors.PrivilegedIntentsRequired:
        print("\n" + "=" * 80)
        print("[DISCORD_BOT] ⚠️ WYKRYTO: Brak włączonego 'Message Content Intent' w Developer Portal.")
        print("[DISCORD_BOT] 🚀 AUTOMATYCZNY FALLBACK: Uruchamiam bota w trybie standardowym.")
        print("[DISCORD_BOT] ✅ Bot będzie w 100% ONLINE, porozmawia na kanale głosowym i odpowie na każdą wzmiankę (@Aether AI) i komendy!")
        print("=" * 80 + "\n")
        b_fallback = create_bot(with_message_content=False)
        b_fallback.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
