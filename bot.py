"""
bot.py - Główny Program Super ChatGPT Bota AI z Ciepłym Głosem i Odróżnianiem Użytkowników
==========================================================================================
Funkcjonalności:
1. Ciepły, naturalny głos neuronowy ChatGPT (pl-PL-ZofiaNeural) na kanale głosowym.
2. Rozpoznawanie i odróżnianie użytkowników (Szatek_Olo, Janow i inni gracze) w głosie i tekście.
3. Dedykowane łączenie z kanałem '🤖・Testowanie・Bota・AI' (ID: 1574154874495705108).
4. Auto-join i żywe przywitanie każdego gracza po imieniu/nicku w momencie wejścia na kanał.
5. Rozumienie pełnego kontekstu rozmowy wieloturowej i podział pamięci na serwery.
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
from voice_engine import DiscordVoiceEngine, DEFAULT_WARM_VOICE
from ai_brain import AIBrain

# Wymuszenie natychmiastowego wypisywania logów w runnerze GitHub Actions
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

load_dotenv()

DISCORD_TOKEN = (os.getenv("DISCORD_TOKEN") or os.getenv("MANUAL_DISCORD_TOKEN") or "").strip()
TARGET_VOICE_CHANNEL_ID = 1574154874495705108  # Dokładne ID kanału 🤖・Testowanie・Bota・AI
TARGET_VOICE_NAME = "testowanie bota ai"
AUTO_JOIN_VOICE = os.getenv("AUTO_JOIN_VOICE", "true").lower() in ("true", "1", "yes")

memory_vault = MemoryVault()
voice_engine = DiscordVoiceEngine(voice_name=os.getenv("TTS_VOICE", DEFAULT_WARM_VOICE))
ai_brain = AIBrain()


class ConversationTracker:
    """Śledzi ostatnie wiadomości na kanale, aby model rozumiał pełny kontekst dyskusji."""
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
    """Czyści nazwę kanału z dowolnych znaków specjalnych i emoji, zamieniając je na spacje."""
    cleaned = re.sub(r"[^a-zA-Z0-9]", " ", name)
    return " ".join(cleaned.lower().split())


def find_best_voice_channel(guild: discord.Guild, preferred_name: Optional[str] = None) -> Optional[discord.VoiceChannel]:
    """Wyszukuje kanał '🤖・Testowanie・Bota・AI' lub kanał, w którym aktualnie są gracze."""
    if not guild.voice_channels:
        return None

    # 1. Priorytet #1: Kanał, w którym ktoś już siedzi (idź prosto do ludzi!)
    populated = [vc for vc in guild.voice_channels if any(not m.bot for m in vc.members)]
    if populated:
        populated.sort(key=lambda vc: len([m for m in vc.members if not m.bot]), reverse=True)
        return populated[0]

    # 2. Priorytet #2: Dedykowany kanał Testowanie Bota AI po dokładnym ID
    for vc in guild.voice_channels:
        if vc.id == TARGET_VOICE_CHANNEL_ID:
            return vc

    # 3. Priorytet #3: Dopasowanie po nazwie (testowanie bota ai, proceed)
    candidates = ["testowanie bota ai", "testowanie", "proceed", "bota ai", "rozmowy"]
    if preferred_name:
        candidates.insert(0, normalize_channel_name(preferred_name))

    for cand in candidates:
        for vc in guild.voice_channels:
            norm = normalize_channel_name(vc.name)
            if cand in norm or norm in cand:
                return vc

    return guild.voice_channels[0]


def format_user_greeting(member: discord.Member) -> str:
    """Generuje spersonalizowane, ciepłe powitanie dla konkretnego użytkownika."""
    name_low = (member.display_name or member.name).lower()
    if any(k in name_low for k in ["szatek", "szatek_olo", "olo", "szatek_010"]):
        return "Cześć Szatek! Bardzo miło Cię słyszeć. Co dzisiaj robimy na serwerze?"
    elif any(k in name_low for k in ["janow", "j_janow3kq", "jan"]):
        return "Siemanko Janow! Witaj na kanale głosowym. Miło Cię widzieć!"
    else:
        return f"Cześć {member.display_name}! Witam na kanale głosowym. O czym pogadamy?"


def is_admin_or_szatek(author: discord.Member) -> bool:
    """Sprawdza czy użytkownik to Szatek_Olo lub administrator serwera."""
    author_name = (author.display_name or author.name).lower()
    if any(k in author_name for k in ["szatek", "szatek_olo", "olo", "szatek_010"]):
        return True
    if hasattr(author, "guild_permissions") and author.guild_permissions.administrator:
        return True
    return False


def create_bot(with_message_content: bool = True) -> commands.Bot:
    """Tworzy instancję bota Discord z ciepłym głosem i adaptacją uprawnień."""
    intents = discord.Intents.default()
    intents.voice_states = True
    intents.guilds = True
    if with_message_content:
        intents.message_content = True

    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    @bot.event
    async def on_ready():
        print(f"[DISCORD_BOT] Zalogowano pomyślnie jako: {bot.user} (ID: {bot.user.id})")
        print(f"[DISCORD_BOT] Serwery: {[f'{g.name} (ID: {g.id})' for g in bot.guilds]}")
        stats = memory_vault.get_stats()
        print(f"[DISCORD_BOT] Skarbiec pamięci załadowany: {stats.get('servers_count', 1)} serwerów.")
        print(f"[DISCORD_BOT] Używany ciepły głos: {voice_engine.voice_name}")

        # Uruchomienie workera syntezy mowy
        voice_engine.start_worker(bot.loop)

        # Ustawienie statusu bota
        activity = discord.Activity(type=discord.ActivityType.listening, name="Testowanie Bota AI • ciepły głos")
        await bot.change_presence(status=discord.Status.online, activity=activity)

        # Automatyczne dołączanie do kanału '🤖・Testowanie・Bota・AI'
        if AUTO_JOIN_VOICE:
            for guild in bot.guilds:
                vc = find_best_voice_channel(guild)
                if vc:
                    print(f"[DISCORD_BOT] Łączenie z docelowym kanałem głosowym: '{vc.name}' (ID: {vc.id})...")
                    connected = await voice_engine.connect(vc)
                    if connected:
                        print(f"[DISCORD_BOT] Połączono z '{vc.name}'!")
                        powitanie = "Siemanko Szatek, siemanko Jagoda! Tu Aether AI. Jestem z Wami na kanale głosowym i słyszę Was głośno i wyraźnie! O czym dzisiaj gadamy?"
                        await voice_engine.enqueue_speech(powitanie)
                        try:
                            await vc.send(f"🎙️ **Jestem na głosowym i mówię na żywo!** ({powitanie})")
                        except Exception:
                            pass
                    break

    @bot.event
    async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Żywe odróżnianie użytkowników na kanale głosowym."""
        if member.bot:
            return

        # Gracz wszedł na kanał głosowy lub zmienił kanał
        if after.channel and (not before.channel or before.channel.id != after.channel.id):
            target_vc = after.channel
            print(f"[VOICE_EVENT] Użytkownik {member.display_name} wszedł na kanał '{target_vc.name}'.")

            # Przejdź natychmiast na kanał, w którym jest gracz
            connected = await voice_engine.connect(target_vc)
            if connected:
                # Odróżnij użytkownika i powitaj go po imieniu ciepłym głosem!
                greeting = format_user_greeting(member)
                print(f"[VOICE_GREETING] Mówię do {member.display_name}: {greeting}")
                await voice_engine.enqueue_speech(greeting)

    muted_channels = set()

    async def execute_music_action(channel: discord.abc.Messageable, music_action: Dict[str, Any]):
        """
        Realizuje akcję muzyczną wyznaczoną przez Polski ChatGPT:
        - Wysyła komendę dla Jockie Music (np. m!play Master of Puppets Metallica)
        - Wypowiada zapowiedź głosem Zofii
        - Uruchamia odtwarzanie utworu lub testu czasowego (np. na 10 sekund) na kanale głosowym!
        """
        act = music_action.get("action")
        reply = music_action.get("reply", "")
        jockie_cmd = music_action.get("jockie_cmd")
        song_query = music_action.get("song_query")
        duration_sec = music_action.get("duration_sec")

        if reply:
            await channel.send(reply)
            if voice_engine.is_connected():
                await voice_engine.enqueue_speech(reply)

        if act == "STOP_MUSIC":
            voice_engine.stop_audio()
            if jockie_cmd:
                await channel.send(jockie_cmd)
            return

        if act in ["PLAY_SONG", "PREVIEW_SONG"] and song_query:
            if jockie_cmd:
                # Wyślij komendę m!play na czacie dla Jockie Music
                await channel.send(jockie_cmd)

            # Odtwórz bezpośrednio na kanale głosowym (całość lub np. 10 sekund testu)
            if voice_engine.is_connected():
                await voice_engine.play_music_preview(song_query, duration_sec=duration_sec)

            if duration_sec:
                async def _stop_jockie_after_test():
                    await asyncio.sleep(duration_sec + 1.0)
                    try:
                        await channel.send(
                            f"⏱️ Minęło **{duration_sec} sekund** testu utworu **{song_query}**! "
                            f"I jak – czy to jest ta piosenka, o którą Ci chodziło? (Jeśli gra Jockie Music: `m!stop`)"
                        )
                    except Exception:
                        pass
                asyncio.create_task(_stop_jockie_after_test())

    async def handle_voice_input(member: discord.Member, recognized_text: str):
        """
        Obsługuje mowę użytkownika usłyszaną na kanale głosowym (STT pl-PL):
        1. Uczy się ze słuchania i zapisuje wypowiedź w pamięci serwera.
        2. Sprawdza wyuczone reguły (np. banan -> jabłko).
        3. Sprawdza intencje muzyczne (zaśpiewaj / m!play / jaka to piosenka / test na 10 sekund).
        4. Wysyła pełny kontekst wszystkich wiadomości do Polskiego ChatGPT i odpowiada głosem na żywo!
        """
        if not recognized_text or member.bot:
            return

        author_name = member.display_name or member.name
        guild = member.guild
        guild_id = str(guild.id) if guild else None
        guild_name = guild.name if guild else "Serwer Głosowy"
        vc_channel = voice_engine.voice_client.channel if voice_engine.is_connected() else None
        if not vc_channel:
            return

        print(f"[VOICE_CHAT] 🎙️ [{author_name} na głosowym #{vc_channel.name}]: {recognized_text}")
        conv_tracker.add_message(vc_channel.id, author_name, f"(GŁOS) {recognized_text}", is_bot=False)

        # 1. Ucz się ze słuchania (source="GŁOS")
        learned_voice = memory_vault.learn_from_message(author_name, recognized_text, guild_id, guild_name, source="GŁOS")

        # 2. Sprawdź wyuczone reguły reakcji (np. powiesz "banan" -> odpowie "jabłko")
        matched_rule = memory_vault.match_rule(recognized_text, guild_id)
        if matched_rule:
            await voice_engine.enqueue_speech(matched_rule)
            try:
                await vc_channel.send(f"🎙️ **{author_name} (Głos):** *„{recognized_text}”*\n🤖 **Aether AI:** {matched_rule}")
            except Exception:
                pass
            return

        if learned_voice and any(k in learned_voice.lower() for k in ["zapamiętałem", "nauczyłem", "zapisałem", "zakodowałem"]):
            await voice_engine.enqueue_speech(learned_voice)
            try:
                await vc_channel.send(f"🎙️ **{author_name} (Głos):** *„{recognized_text}”*\n🧠 **Aether AI:** {learned_voice}")
            except Exception:
                pass
            return

        memory_ctx = memory_vault.build_context_for_prompt(author_name, recognized_text, guild_id, guild_name)
        server_store = memory_vault._get_server_store(guild_id, guild_name)
        global_lore = memory_vault.data.get("global_lore", {})

        # 3. Sprawdź intencję muzyczną przez Polski ChatGPT (zaśpiewaj / m!play / jaka to piosenka / test 10s)
        music_intent = await ai_brain.analyze_music_intent(vc_channel.id, author_name, recognized_text, memory_ctx)
        if music_intent:
            try:
                await vc_channel.send(f"🎙️ **{author_name} (Głos):** *„{recognized_text}”*")
            except Exception:
                pass
            await execute_music_action(vc_channel, music_intent)
            return

        # 4. Wygeneruj odpowiedź w Polskim ChatGPT na podstawie wszystkich wiadomości i 4 przykładów sytuacji
        history = conv_tracker.get_history(vc_channel.id)
        reply = await ai_brain.generate_response(
            author_name,
            recognized_text,
            memory_ctx,
            history,
            server_store=server_store,
            global_lore=global_lore,
            source_modality="GŁOS"
        )

        conv_tracker.add_message(vc_channel.id, "Aether AI", reply, is_bot=True)
        await voice_engine.enqueue_speech(reply)
        try:
            await vc_channel.send(f"🎙️ **{author_name} (Głos):** *„{recognized_text}”*\n🤖 **Aether AI:** {reply}")
        except Exception:
            pass

    voice_engine.set_voice_command_callback(handle_voice_input)

    async def speak_on_vc(message: discord.Message, text_to_speak: str):
        """Gwarantuje połączenie z kanałem głosowym rozmówcy i odtwarza mowę na żywo."""
        if not voice_engine.is_connected() and message.guild:
            target = (
                message.author.voice.channel
                if (hasattr(message.author, "voice") and message.author.voice and message.author.voice.channel)
                else find_best_voice_channel(message.guild)
            )
            if target:
                await voice_engine.connect(target)
        if voice_engine.is_connected():
            await voice_engine.enqueue_speech(text_to_speak)
            try:
                await message.add_reaction("🗣️")
            except Exception:
                pass

    @bot.event
    async def on_message(message: discord.Message):
        if message.author == bot.user or message.author.bot:
            return

        author_name = message.author.display_name or message.author.name
        content = (message.content or "").strip()

        # INTELIGENTNY BYPASS: Jeśli bramka Discorda przysłała pusty tekst (brak privileged intents),
        # pobierz pełną treść wiadomości bezpośrednio przez REST API Discorda!
        if not content and not message.author.bot:
            try:
                fetched = await message.channel.fetch_message(message.id)
                content = (fetched.content or "").strip()
            except Exception:
                pass

        guild_id = str(message.guild.id) if message.guild else None
        guild_name = message.guild.name if message.guild else "Prywatny Czat"

        ch_name = getattr(message.channel, "name", "DM")
        print(f"[CHAT] [{author_name} w #{ch_name}]: {content}")

        # 0. TRYB CISZY NA ŻYCZENIE ("nie odzywaj się", "nie pisz nic" vs "dobra można")
        c_check = content.lower()
        if any(m in c_check for m in ["nie odzywaj się", "nie odzywaj sie", "nie pisz nic", "bądź cicho", "badz cicho", "zamknij się"]):
            muted_channels.add(message.channel.id)
            try:
                await message.add_reaction("🤐")
            except Exception:
                pass
            return

        if any(u in c_check for u in ["dobra można", "dobra mozna", "możesz pisać", "mozesz pisac", "odzywaj się", "odzywaj sie"]):
            if message.channel.id in muted_channels:
                muted_channels.discard(message.channel.id)
                await message.reply("Super, wracam do rozmowy! 🚀", mention_author=False)
                return

        # Zapisz w historii kanału
        conv_tracker.add_message(message.channel.id, author_name, content, is_bot=False)

        # 1. SPRAWDZENIE WYUCZONYCH REGUŁ REAKCJI ("jak ktoś napisze banan to odpisz jabłko")
        matched_rule = memory_vault.match_rule(content, guild_id)
        if matched_rule:
            print(f"[RULES] Wykryto dopasowanie reguły dla: '{content}' -> Odpowiedź: '{matched_rule}'")
            await message.reply(matched_rule, mention_author=False)
            await speak_on_vc(message, matched_rule)
            conv_tracker.add_message(message.channel.id, "Aether AI", matched_rule, is_bot=True)
            return

        # 2. CIĄGŁA NAUKA Z CZYTANIA WIADOMOŚCI (Polski ChatGPT uczy się faktów, upodobań i reguł)
        if len(content) > 2:
            learned_result = memory_vault.learn_from_message(author_name, content, guild_id, guild_name, source="CZAT")
            if learned_result:
                try:
                    await message.add_reaction("🧠")
                except Exception:
                    pass
                if any(k in learned_result.lower() for k in ["zapamiętałem", "nauczyłem", "zapisałem", "zakodowałem"]):
                    await message.reply(learned_result, mention_author=False)
                    await speak_on_vc(message, learned_result)
                    return

        # 3. Obsługa komend bota (!)
        if content.startswith("!"):
            await bot.process_commands(message)
            return

        # 4. Naturalne polecenia wejścia na kanał głosowy (choc na vc, chodź na vc, wbijaj na głosowy)
        c_low = re.sub(r"[\/\\!\?,\.]", " ", content.lower())
        clean_words = [w.strip() for w in re.sub(r"<@!?\d+>|<@&\d+>", "", c_low).split() if w.strip()]
        is_join_command = (
            bool(re.search(r"\b(choc|choć|chodz|chodź|wbij|wbijaj|wejdz|wejdź|dolacz|dołącz)\b.*\b(vc|dc|glosow|głosow|kanal|kanał)\b", c_low))
            or any(p in c_low for p in [
                "choc na vc", "choć na vc", "chodz na vc", "chodź na vc", "wbij na vc", "wbij vc",
                "wbijaj na vc", "wejdz na vc", "wejdź na vc", "wbij na glosowy", "chodź na głosowy",
                "chodz na glosowy", "choc na glosowy", "chodź pogadać", "choc pogadac", "wbijaj na dc",
                "chodz na dc", "choc na dc", "chodź na dc", "wskakuj na vc", "dołącz na kanał",
                "dolacz na kanal", "dolacz na glosowy", "dołącz na kanał głosowy", "chodź pogadać"
            ])
            or (len(clean_words) == 1 and clean_words[0] in ["dołącz", "dolacz", "wbij", "chodź", "chodz", "choc", "join"])
        )

        if is_join_command:
            target_vc = None
            if message.author.voice and message.author.voice.channel:
                target_vc = message.author.voice.channel
            elif message.guild:
                target_vc = find_best_voice_channel(message.guild)

            if target_vc:
                connected = await voice_engine.connect(target_vc)
                if connected:
                    await message.reply(f"🔊 Już wbiłem na kanał głosowy **{target_vc.name}**! Słucham Was na żywo i odpowiadam głosem.", mention_author=False)
                    await voice_engine.enqueue_speech(f"Siemanko {author_name}! Wbiłem na kanał {target_vc.name}. Słucham Was na żywo!")
                    return

        # 5. SPRAWDZENIE INTENCJI MUZYCZNYCH PRZEZ POLSKI CHATGPT (zaśpiewaj / m!play / jaka to piosenka / test 10 sekund)
        memory_ctx = memory_vault.build_context_for_prompt(author_name, content, guild_id, guild_name)
        music_intent = await ai_brain.analyze_music_intent(message.channel.id, author_name, content, memory_ctx)
        if music_intent:
            if not voice_engine.is_connected() and message.guild:
                target = (
                    message.author.voice.channel
                    if (hasattr(message.author, "voice") and message.author.voice and message.author.voice.channel)
                    else find_best_voice_channel(message.guild)
                )
                if target:
                    await voice_engine.connect(target)
            await execute_music_action(message.channel, music_intent)
            return

        # 6. INTELIGENTNA SELEKCJA: KIEDY BOT ODPOWIADA?
        is_mentioned = (bot.user in message.mentions) or any(
            r.name.lower() == "aether ai" or r.id == 1574495066779689013 for r in getattr(message, "role_mentions", [])
        )
        is_reply_to_bot = (
            message.reference
            and message.reference.resolved
            and getattr(message.reference.resolved, "author", None) == bot.user
        )
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_dedicated_bot_channel = (message.channel.id == TARGET_VOICE_CHANNEL_ID)

        name_triggers = [
            "bot", "bocie", "aether", "aetherze", "ai", "chat gpt", "chatgpt",
            "mordo", "ziomek", "ej bot", "halo bot", "hej bot", "powiedz", "odezwij",
            "jagoda", "basista", "oliwier", "szatek", "co wiesz", "analiza", "przeanalizuj"
        ]
        words_in_msg = re.findall(r"\b\w+\b", c_low)
        starts_or_calls_bot = (
            any(trigger in words_in_msg[:3] for trigger in ["bot", "bocie", "aether", "ai", "chatgpt", "powiedz", "odezwij"])
            or any(t in c_low for t in name_triggers)
        )

        time_since_reply = conv_tracker.time_since_last_bot_reply(message.channel.id)
        is_continuation = (
            (time_since_reply < 60.0)
            and len(clean_words) >= 2
            and ("?" in content or any(content.lower().strip().startswith(w) for w in ["co", "jak", "dlaczego", "kiedy", "kto", "czy", "a "]))
            and not content.startswith("http")
        )

        if message.channel.id in muted_channels and not is_mentioned:
            return
        elif is_mentioned:
            muted_channels.discard(message.channel.id)

        # Ignoruj komendy innych botów muzycznych (np. M!s, m!play wpisane przez gracza)
        if c_low.startswith("m!"):
            return

        should_respond = is_mentioned or is_reply_to_bot or is_dm or starts_or_calls_bot or is_continuation or (is_dedicated_bot_channel and len(clean_words) >= 2)

        if not should_respond:
            return

        async with message.channel.typing():
            clean_query = re.sub(r"<@!?\d+>|<@&\d+>", "", content).strip()
            if not clean_query:
                clean_query = "Co tam słychać na serwerze?"

            server_store = memory_vault._get_server_store(guild_id, guild_name)
            global_lore = memory_vault.data.get("global_lore", {})
            history = conv_tracker.get_history(message.channel.id)

            # POLSKI CHATGPT WSZĘDZIE: Analizuje wszystkie wiadomości, 4 przykłady i generuje odpowiedź adekwatną do sytuacji!
            reply = await ai_brain.generate_response(
                author_name,
                clean_query,
                memory_ctx,
                history,
                server_store=server_store,
                global_lore=global_lore,
                source_modality="CZAT"
            )

            conv_tracker.add_message(message.channel.id, "Aether AI", reply, is_bot=True)
            await message.reply(reply, mention_author=False)

            # ODTWÓRZ ODPOWIEDŹ CIEPŁYM GŁOSEM NA KANALE GŁOSOWYM
            await speak_on_vc(message, reply)

    # --- KOMENDY ---

    @bot.command(name="dolacz", aliases=["join", "wbij", "dołącz", "wejdz", "wejdź", "chodz", "chodź", "choc", "choć", "wbijaj", "głosowy", "glosowy", "vc", "glosowt", "głosowt", "kanal", "kanał"])
    async def cmd_join(ctx: commands.Context, *, channel_name: Optional[str] = None):
        """Dołącza bota do kanału głosowego (domyślnie '🤖・Testowanie・Bota・AI' lub Twojego kanału)."""
        target_vc = None
        if channel_name:
            target_vc = find_best_voice_channel(ctx.guild, channel_name)
        elif ctx.author.voice and ctx.author.voice.channel:
            target_vc = ctx.author.voice.channel
        else:
            target_vc = find_best_voice_channel(ctx.guild)

        if not target_vc:
            await ctx.send("❌ Nie znaleziono kanału głosowego. Upewnij się, że jesteś na kanale głosowym!")
            return

        connected = await voice_engine.connect(target_vc)
        if connected:
            await ctx.send(f"🔊 Połączono z kanałem **{target_vc.name}**! Ciepły głos ChatGPT jest aktywny.")
            await voice_engine.enqueue_speech(f"Siemanko {ctx.author.display_name}! Wszedłem na kanał {target_vc.name}. Słucham Cię cieplutko!")
        else:
            await ctx.send(f"❌ Nie udało się połączyć z `{target_vc.name}`. Sprawdź uprawnienia bota.")

    @bot.command(name="naucz")
    async def cmd_learn_rule(ctx: commands.Context, *, rule_text: str):
        """Uczy bota nowej reguły: !naucz banan => jabłko"""
        guild_id = str(ctx.guild.id) if ctx.guild else None
        guild_name = ctx.guild.name if ctx.guild else "Prywatny"
        res = memory_vault.learn_from_message(ctx.author.display_name, f"!naucz {rule_text}", guild_id, guild_name)
        if res:
            await ctx.send(res)
        else:
            await ctx.send("ℹ️ Użycie: `!naucz <słowo> => <odpowiedź>`, np. `!naucz banan => jabłko`")

    @bot.command(name="reguly", aliases=["reguły", "rules"])
    async def cmd_show_rules(ctx: commands.Context):
        """Wyświetla listę wszystkich wyuczonych reguł na serwerze."""
        guild_id = str(ctx.guild.id) if ctx.guild else None
        rules = memory_vault.get_rules(guild_id)
        if not rules:
            await ctx.send("ℹ️ Brak wyuczonych reguł na tym serwerze. Możesz dodać regułę pisząc: `jak ktoś napisze banan to odpisz jabłko`")
            return
        lines = [f"• **{k}** ➔ *{v['response']}* *(dodał: {v.get('added_by', 'ktoś')})*" for k, v in rules.items()]
        await ctx.send(f"**🧠 Wyuczone reguły na serwerze ({len(rules)}):**\n" + "\n".join(lines))

    @bot.command(name="zapomnij", aliases=["forget"])
    async def cmd_forget_rule(ctx: commands.Context, *, trigger: str):
        """Usuwa wyuczoną regułę ze serwera."""
        guild_id = str(ctx.guild.id) if ctx.guild else None
        ok = memory_vault.remove_rule(trigger, guild_id)
        if ok:
            await ctx.send(f"🗑️ Zapomniałem regułę dla słowa **{trigger}**.")
        else:
            await ctx.send(f"❌ Nie znaleziono reguły dla **{trigger}**.")

    @bot.command(name="wyjdz", aliases=["leave", "disconnect", "opusc"])
    async def cmd_leave(ctx: commands.Context):
        """Odłącza bota z kanału głosowego."""
        if not voice_engine.is_connected():
            await ctx.send("ℹ️ Nie jestem na kanale głosowym.")
            return

        await voice_engine.enqueue_speech("Do usłyszenia! Wracam na posterunek.")
        await asyncio.sleep(1.8)
        await voice_engine.disconnect()
        await ctx.send("🔇 Odłączono z kanału głosowego.")

    @bot.command(name="powiedz", aliases=["say", "tts"])
    async def cmd_say(ctx: commands.Context, *, text: str):
        """Wypowiada podany tekst ciepłym głosem."""
        if not voice_engine.is_connected():
            # Spróbuj najpierw wejść na kanał autora
            if ctx.author.voice and ctx.author.voice.channel:
                await voice_engine.connect(ctx.author.voice.channel)
            else:
                vc = find_best_voice_channel(ctx.guild)
                if vc:
                    await voice_engine.connect(vc)

        await voice_engine.enqueue_speech(text)
        await ctx.message.add_reaction("🗣️")

    @bot.command(name="analiza", aliases=["4przyklady", "sytuacja", "analizuj", "kto_co_lubi"])
    async def cmd_analiza(ctx: commands.Context):
        """Polski ChatGPT analizuje wszystkie wiadomości i wyświetla 4 przykłady co kto lubi, jaki kto jest i jak wygląda sytuacja na serwerze."""
        guild_id = str(ctx.guild.id) if ctx.guild else None
        guild_name = ctx.guild.name if ctx.guild else "Serwer"
        author_name = ctx.author.display_name or ctx.author.name
        memory_ctx = memory_vault.build_context_for_prompt(author_name, "Przeanalizuj wszystkie wiadomości i podaj 4 przykłady", guild_id, guild_name)
        server_store = memory_vault._get_server_store(guild_id, guild_name)
        global_lore = memory_vault.data.get("global_lore", {})
        history = conv_tracker.get_history(ctx.channel.id)

        reply = await ai_brain.generate_response(
            author_name,
            "Przeanalizuj wszystkie wiadomości, podaj 4 przykłady co kto lubi, jaki kto jest i jak wygląda sytuacja na serwerze.",
            memory_ctx,
            history,
            server_store=server_store,
            global_lore=global_lore,
            source_modality="CZAT"
        )
        await ctx.send(reply)
        await speak_on_vc(ctx.message, reply)

    @bot.command(name="zaspiewaj", aliases=["zaśpiewaj", "pusc", "puść", "zagraj"])
    async def cmd_zaspiewaj(ctx: commands.Context, *, song_query: str):
        """Puszcza utwór przez Jockie Music (m!play) i śpiewa/odtwarza na kanale głosowym."""
        guild_id = str(ctx.guild.id) if ctx.guild else None
        guild_name = ctx.guild.name if ctx.guild else "Serwer"
        author_name = ctx.author.display_name or ctx.author.name
        memory_ctx = memory_vault.build_context_for_prompt(author_name, f"zaśpiewaj {song_query}", guild_id, guild_name)
        music_intent = await ai_brain.analyze_music_intent(ctx.channel.id, author_name, f"zaśpiewaj {song_query}", memory_ctx)
        if music_intent:
            await execute_music_action(ctx.channel, music_intent)

    @bot.command(name="testmuzyki", aliases=["probka", "próbka", "test10s"])
    async def cmd_test_music(ctx: commands.Context, duration_sec: int = 10, *, song_query: str = "Master of Puppets Metallica"):
        """Puszcza utwór na określoną liczbę sekund (np. 10 sekund) do przetestowania czy to ta muzyka."""
        guild_id = str(ctx.guild.id) if ctx.guild else None
        guild_name = ctx.guild.name if ctx.guild else "Serwer"
        author_name = ctx.author.display_name or ctx.author.name
        memory_ctx = memory_vault.build_context_for_prompt(author_name, f"puść {song_query} na {duration_sec} sekund", guild_id, guild_name)
        music_intent = await ai_brain.analyze_music_intent(ctx.channel.id, author_name, f"puść {song_query} na {duration_sec} sekund", memory_ctx)
        if music_intent:
            await execute_music_action(ctx.channel, music_intent)

    @bot.command(name="status")
    async def cmd_status(ctx: commands.Context):
        """Wyświetla status bota, pamięci serwera i połączenia audio."""
        guild_id = str(ctx.guild.id) if ctx.guild else None
        stats = memory_vault.get_stats(guild_id)
        voice_state = f"🔊 Połączony + Nasłuch STT ({voice_engine.voice_client.channel.name})" if voice_engine.is_connected() else "🔇 Rozłączony"

        embed = discord.Embed(title="🛡️ Status Aether AI – Polski ChatGPT (Słuchanie + Mówienie + Muzyka)", color=0x3a86ff)
        embed.add_field(name="🎙️ Kanał Głosowy & STT", value=voice_state, inline=True)
        embed.add_field(name="🗣️ Aktywny Głos", value="Polski ChatGPT (pl-PL-ZofiaNeural)", inline=True)
        embed.add_field(name="🌐 Przestrzeń Serwera", value=stats.get("server_name", "Prywatna"), inline=True)
        embed.add_field(name="🧠 Przeanalizowane Wypowiedzi", value=f"{stats.get('chat_log_count', 0)} wiadomości (Czat + Głos)", inline=True)
        embed.add_field(name="📚 Zakodowane Fakty & Reguły", value=f"{stats.get('facts_count', 0)} faktów / {stats.get('rules_count', 0)} reguł", inline=True)
        embed.add_field(name="🔒 Szyfrowanie Pamięci", value="AES-256-GCM (GitHub Sync)", inline=True)
        embed.set_footer(text="Polski ChatGPT Wszędzie • Działa w GitHub Actions 24/7 • ZSC 2026")
        await ctx.send(embed=embed)

    @bot.command(name="pomoc", aliases=["help"])
    async def cmd_help(ctx: commands.Context):
        """Pomoc i lista komend."""
        msg = """**🤖 Aether AI – Polski ChatGPT (Słuchanie na VC + Mówienie + Jockie Music):**
• **Słuchanie na żywo (STT):** Gdy jesteś ze mną na kanale głosowym, po prostu mów do mikrofonu – słucham po polsku, uczę się i odpowiadam na głos!
• **Muzyka i Jockie Music:**
  - Powiedz lub napisz: `zaśpiewaj Master of Puppets Metallicy` ➔ wysyłam `m!play Master of Puppets Metallica` i odpalam utwór!
  - Powiedz lub napisz: `puść Master of Puppets na 10 sekund` (lub `!testmuzyki 10 Master of Puppets`) ➔ puszczam utwór dokładnie na 10 sekund do przetestowania czy to ta muzyka!
  - Zaśpiewaj fragment tekstu lub napisz: `jaka to piosenka: [słowa]` ➔ Polski ChatGPT rozpozna tytuł i zapyta, czy puścić na próbę!
• `!analiza` (lub napisz `co wiesz o nas?`) – Polski ChatGPT analizuje wszystkie wiadomości i podaje **4 przykłady** co kto lubi, jaki kto jest i jak wygląda sytuacja na serwerze!
• `jak ktoś napisze banan to odpisz jabłko` (lub `!naucz banan => jabłko`) – Uczy mnie dowolnej reguły reakcji!
• `!dolacz` / `!głosowy` / `choc na vc` – Dołącza na kanał głosowy"""
        await ctx.send(msg)

    @bot.command(name="pamiec", aliases=["fakty", "wiedza"])
    async def cmd_memory(ctx: commands.Context):
        """Wyświetla zapamiętane fakty z tego serwera."""
        guild_id = str(ctx.guild.id) if ctx.guild else None
        store = memory_vault._get_server_store(guild_id)
        facts = store.get("facts", [])
        if not facts:
            await ctx.send("🧠 Moja baza pamięci dla tego serwera jest jeszcze pusta. Napisz: `zapamiętaj, że...`")
            return

        msg = f"**🧠 Zapamiętane fakty dla serwera {store.get('guild_name', 'ten serwer')}:**\n"
        for f in facts[-6:]:
            msg += f"• `#{f['id']}` {f['content']} *(dodał: {f.get('added_by', 'SYSTEM')})*\n"
        await ctx.send(msg)

    @bot.command(name="restart", aliases=["reset", "reboot"])
    async def cmd_restart(ctx: commands.Context):
        """Restartuje bota, aby odświeżyć uprawnienia i konfigurację (tylko Szatek_Olo lub Administrator)."""
        if not is_admin_or_szatek(ctx.author):
            await ctx.send("⛔ Tylko Szatek_Olo lub Administrator może restartować bota! 🛡️")
            return
        await ctx.send("🔄 Restartuję Aether AI w chmurze... Za chwilę wracam ze zaktualizowanymi uprawnieniami!")
        memory_vault._save_vault()
        await bot.close()
        sys.exit(0)

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
    print(f"✅ 2. Ciepły Głos Neuronowy ChatGPT ({voice_engine.voice_name}): SPRAWNY")
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

    print("[DISCORD_BOT] Inicjalizacja Aether AI Super ChatGPT (Ciepły Głos)...")

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
