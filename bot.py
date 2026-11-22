"""
bot.py - Główny Program Bota AI na Discordzie z Obsługą Kanału Głosowego (proceed)
==================================================================================
Funkcjonalności:
1. Ciągłe uczenie się i zapamiętywanie (Memory Vault) – czyta wiadomości, zapamiętuje kto kim jest,
   role, relacje i definicje, szyfrując bazę algorytmem AES-256 (zero wycieków w publicznym repo).
2. Rozmowy głosowe – dołącza do kanału głosowego (np. 'proceed') i mówi naturalnym, neuronowym
   polskim głosem w czasie rzeczywistym.
3. Osobny model AI – unikalny charakter, humor, wierność ZSC i Szatek_Olo.
"""

import os
import sys
import asyncio
from typing import Optional
import discord
from discord.ext import commands
from dotenv import load_dotenv

from memory_vault import MemoryVault
from voice_engine import DiscordVoiceEngine
from ai_brain import AIBrain

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
TARGET_VOICE_CHANNEL = os.getenv("VOICE_CHANNEL_NAME", "proceed")
AUTO_JOIN_VOICE = os.getenv("AUTO_JOIN_VOICE", "true").lower() in ("true", "1", "yes")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

memory_vault = MemoryVault()
voice_engine = DiscordVoiceEngine(voice_name=os.getenv("TTS_VOICE", "pl-PL-MarekNeural"))
ai_brain = AIBrain()


async def find_voice_channel(guild: discord.Guild, target_name: str) -> Optional[discord.VoiceChannel]:
    """Wyszukuje kanał głosowy po nazwie (np. 'proceed' lub 'procced')."""
    target_clean = target_name.strip().lower()
    for vc in guild.voice_channels:
        vc_name = vc.name.lower()
        if target_clean in vc_name or vc_name in target_clean:
            return vc
    return None


@bot.event
async def on_ready():
    print(f"[DISCORD_BOT] Zalogowano pomyślnie jako: {bot.user} (ID: {bot.user.id})")
    print(f"[DISCORD_BOT] Serwery: {[g.name for g in bot.guilds]}")
    stats = memory_vault.get_stats()
    print(f"[DISCORD_BOT] Pamięć załadowana: {stats['users_count']} użytkowników, {stats['facts_count']} faktów, {stats['definitions_count']} definicji.")

    # Uruchom asynchronicznego workera odtwarzania mowy
    voice_engine.start_worker(bot.loop)

    # Ustawienie statusu bota
    activity = discord.Activity(type=discord.ActivityType.listening, name="proceed • !pomoc")
    await bot.change_presence(status=discord.Status.online, activity=activity)

    # Automatyczne dołączanie do kanału głosowego 'proceed'
    if AUTO_JOIN_VOICE:
        for guild in bot.guilds:
            vc = await find_voice_channel(guild, TARGET_VOICE_CHANNEL)
            if vc:
                print(f"[DISCORD_BOT] Dołączam do kanału głosowego: {vc.name} na serwerze {guild.name}...")
                connected = await voice_engine.connect(vc)
                if connected:
                    print(f"[DISCORD_BOT] Połączono z kanałem głosowym: {vc.name}!")
                    await voice_engine.enqueue_speech("Melduję gotowość na kanale proceed! Czuwam, słucham i uczę się z Wami.")
                break


@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return

    author_name = message.author.display_name or message.author.name
    content = message.content.strip()

    # 1. CIĄGŁE UCZENIE SIĘ: Analizuj każdą wiadomość na kanale
    if len(content) > 2:
        learned_confirmation = memory_vault.learn_from_message(author_name, content)
        if learned_confirmation:
            try:
                await message.add_reaction("🧠")
            except Exception:
                pass

    # 2. Obsługa komend bota (np. !pomoc, !dolacz, !wyjdz)
    if content.startswith("!"):
        await bot.process_commands(message)
        return

    # 3. Kiedy bot ma odpowiedzieć w konwersacji?
    is_mentioned = bot.user in message.mentions
    is_reply_to_bot = (
        message.reference
        and message.reference.resolved
        and message.reference.resolved.author == bot.user
    )
    is_dm = isinstance(message.channel, discord.DMChannel)
    bot_names = ["aether", "bot", "ai", "mordo", "żołnierz"]
    contains_name = any(name in content.lower() for name in bot_names)

    should_respond = is_mentioned or is_reply_to_bot or is_dm or (contains_name and len(content) > 5)

    if should_respond:
        async with message.channel.typing():
            # Usuń wzmiankę o bocie z zapytania
            clean_query = content.replace(f"<@{bot.user.id}>", "").strip()
            if not clean_query:
                clean_query = "Siema, co tam?"

            # Pobierz kontekst pamięci ("kto kim jest" + fakty)
            memory_ctx = memory_vault.build_context_for_prompt(author_name, clean_query)

            # Generuj odpowiedź z dedykowanego modelu AI
            reply = await ai_brain.generate_response(author_name, clean_query, memory_ctx)

            # Wyślij odpowiedź na czacie tekstowym
            await message.reply(reply, mention_author=False)

            # JEŚLI BOT JEST NA KANALE GŁOSOWYM: wypowiedz tę odpowiedź na głos!
            if voice_engine.is_connected():
                await voice_engine.enqueue_speech(reply)


@bot.command(name="dolacz", aliases=["join", "proceed"])
async def cmd_join(ctx: commands.Context, *, channel_name: Optional[str] = None):
    """Dołącza bota do kanału głosowego (domyślnie 'proceed' lub kanał autora)."""
    target_vc = None

    if channel_name:
        target_vc = await find_voice_channel(ctx.guild, channel_name)
    elif ctx.author.voice and ctx.author.voice.channel:
        target_vc = ctx.author.voice.channel
    else:
        target_vc = await find_voice_channel(ctx.guild, TARGET_VOICE_CHANNEL)

    if not target_vc:
        await ctx.send(f"❌ Nie znalazłem kanału głosowego `{channel_name or TARGET_VOICE_CHANNEL}`. Upewnij się, że kanał istnieje lub wejdź na kanał głosowy.")
        return

    connected = await voice_engine.connect(target_vc)
    if connected:
        await ctx.send(f"🔊 Połączono z kanałem głosowym **{target_vc.name}**! Możemy rozmawiać.")
        await voice_engine.enqueue_speech(f"Siemanko {ctx.author.display_name}! Wszedłem na kanał {target_vc.name}.")
    else:
        await ctx.send(f"❌ Nie udało się połączyć z kanałem `{target_vc.name}`. Sprawdź uprawnienia bota (Connect, Speak).")


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
    """Mówi podany tekst na kanale głosowym."""
    if not voice_engine.is_connected():
        await ctx.send("⚠️ Najpierw zaproś mnie na kanał głosowy komendą `!dolacz`!")
        return

    await voice_engine.enqueue_speech(text)
    await ctx.message.add_reaction("🗣️")


@bot.command(name="status")
async def cmd_status(ctx: commands.Context):
    """Wyświetla status bota, pamięci i kanału głosowego."""
    stats = memory_vault.get_stats()
    voice_state = "🔊 Połączony (" + voice_engine.voice_client.channel.name + ")" if voice_engine.is_connected() else "🔇 Rozłączony"

    embed = discord.Embed(title="🛡️ Status AETHER AI Sentinel", color=0x3a86ff)
    embed.add_field(name="🎙️ Kanał Głosowy", value=voice_state, inline=True)
    embed.add_field(name="🧠 Baza Użytkowników", value=f"{stats['users_count']} profili", inline=True)
    embed.add_field(name="📚 Zapamiętane Fakty", value=f"{stats['facts_count']} faktów", inline=True)
    embed.add_field(name="🔒 Szyfrowanie Bazy", value="AES-256-GCM (Zero-Leak)", inline=True)
    embed.add_field(name="⚡ Głos TTS", value=voice_engine.voice_name, inline=True)
    embed.set_footer(text="Działa w GitHub Workflow • ZSC 2026")
    await ctx.send(embed=embed)


@bot.command(name="pomoc", aliases=["help"])
async def cmd_help(ctx: commands.Context):
    """Pomoc i lista komend."""
    msg = """**🤖 Komendy AETHER AI Discord:**
• `!dolacz [kanał]` – Dołącza do kanału głosowego (domyślnie `proceed`)
• `!wyjdz` – Opuszcza kanał głosowy
• `!powiedz [tekst]` – Wypowiada tekst neuronowym polskim głosem na kanale
• `!status` – Raport stanu bota, pamięci i połączenia głosowego
• `zapamiętaj, że [fakt]` – Zapisuje na stałe nowy fakt w zaszyfrowanym Skarbcu Pamięci!
• Rozmawiaj ze mną oznaczając mnie `@AETHER` lub pytając na kanale!"""
    await ctx.send(msg)


def main():
    if not DISCORD_TOKEN:
        print("[CRITICAL] Brak zmiennej DISCORD_TOKEN! Skonfiguruj GitHub Secrets lub plik .env.")
        sys.exit(1)

    print("[DISCORD_BOT] Uruchamianie AETHER Discord AI Sentinela...")
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
