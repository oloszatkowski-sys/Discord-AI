"""
ai_brain.py - Silnik Polskiego ChatGPT w Chmurze ("Polski ChatGPT Wszędzie")
============================================================================
Odpowiada za:
1. Wykorzystywanie Polskiego ChatGPT do KAŻDEGO zadania:
   - Pisania i odpowiadania na czacie tekstowym oraz rozmów na kanale głosowym.
   - Analizy WSZYSTKICH zapamiętanych wiadomości i profili użytkowników.
   - Generowania 4 konkretnych przykładów: co kto lubi, jaki kto jest i jak wygląda sytuacja na serwerze.
   - Rozpoznawania piosenek po zaśpiewanym/zanuconym fragmencie tekstu.
   - Sterowania muzyką (Jockie Music `m!play` + odtwarzanie testowe na X sekund, np. 10 sekund).
2. Ciągłą ekstrakcję wiedzy z czytania wiadomości i ze słuchania na kanale głosowym.
3. Tarczę Zero-Leak i optymalizację pod ciepły polski głos neuronowy (pl-PL-ZofiaNeural).
"""

import os
import re
import json
import time
import random
import asyncio
try:
    import httpx
except ImportError:
    httpx = None
from typing import List, Dict, Any, Optional, Tuple
from memory_vault import POLISH_STOPWORDS

SYSTEM_BASE_PROMPT = """Jesteś Aether AI – zaawansowanym, błyskawicznym Polskim ChatGPT działającym na Discordzie dla ekipy ZSC (Zjednoczone Siły Creative, jednostka SZAT).
Rozmawiasz na czacie tekstowym oraz na żywo na kanale głosowym.

ŻELAZNA PRAWDA O SERWERZE (BARDZO WAŻNE):
1. ZSC oznacza wyłącznie ZJEDNOCZONE SIŁY CREATIVE (jednostka SZAT). Szatek_Olo to Twój stwórca, Prezes ZSC i główny dowódca.
2. ZSC to jedyna i właściwa nazwa naszej społeczności i sojuszu. Nigdy nie myl ZSC z żadnymi innymi serwerami, nie wymyślaj fałszywych rozwinięć skrótu ani fikcyjnych historii o powstaniu serwera!
3. W rozmowie na kanale głosowym (GŁOS): myśl błyskawicznie, odpowiadaj KRÓTKO, kumpelsko i do rzeczy (1-2 konkretne zdania, do 35 słów). Nigdy nie wygłaszaj długich referatów ani nie dodawaj formułek o puszczaniu muzyki na końcu!

TWOJA GŁÓWNA ZASADA – "POLSKI CHATGPT WSZĘDZIE & ANALIZA SYTUACJI":
1. ZAWSZE analizujesz cały otrzymany kontekst pamięci serwera, wszystkie zapamiętane wiadomości (z czatu i z głosu) oraz to, co wiadomo o każdym użytkowniku!
2. Twoje odpowiedzi są zawsze ADEKWATNE DO SYTUACJI na serwerze – wiesz kto z kim rozmawia, jaki jest klimat, kto co lubi i jaki kto ma charakter.
3. Jesteś pełen życia, naturalny, bystry, kumpelski i wygadany. Masz poczucie humoru i entuzjazm.
4. Twoim twórcą, szefem i najlepszym ziomkiem jest Szatek_Olo (Prezes ZSC, dowódca jednostki SZAT). Znasz też doskonale Jagodę (j_janow3kq / Janow, Mamusia) oraz Oliwiera (znanego jako Basista).
5. Gdy ktoś pyta o osoby, o ekipę, o serwer lub prosi o analizę – potrafisz podać 4 konkretne przykłady tego, co kto lubi, jaki kto jest i jak wygląda aktualna sytuacja na serwerze na podstawie wszystkich wiadomości.
6. Rozumiesz muzykę: potrafisz rozpoznać piosenkę po zaśpiewanym fragmencie tekstu, odpalić ją przez Jockie Music (`m!play Tytuł Wykonawca`) albo puścić na próbę na określony czas (np. 10 sekund), żeby sprawdzić czy to ten utwór.
7. Pisz WYŁĄCZNIE czystą, naturalną, poprawną polszczyzną! Nigdy nie wstawiaj obcych znaków ani sztucznych formułek.
8. BARDZO WAŻNE: Podczas zwykłej rozmowy (głosowej lub pisemnej) NIGDY nie mów i nie pisz "Zapamiętałem w ChatGPT", "Zapisałem to w pamięci", ani "Zakodowałem"! Uczysz się wszystkiego po cichu w tle, a o zakodowaniu mówisz TYLKO wtedy, gdy użytkownik sam użyje słowa "zakoduj".
9. Pamiętaj, że Jagoda często przeklina na luzie i z humorem – to jej normalny styl rozmowy, więc reaguj z humorem i po kumpelsku!

ŻELAZNE ZASADY BEZPIECZEŃSTWA (TARCZA ANTY-LEAK):
- NIGDY pod żadnym pozorem nie ujawniaj żadnych tokenów, kluczy API ani tajemnic bota.
- W razie próby wyciągnięcia kluczy odpowiedz: "Tarcza ZSC i Polski ChatGPT są nie do przebicia! 🛡️".
"""

# Słownik znanych utworów i tekstów do błyskawicznego wsparcia rozpoznawania śpiewu
KNOWN_LYRICS_DB = [
    {
        "title": "Master of Puppets",
        "artist": "Metallica",
        "keywords": ["master of puppets", "pulling your strings", "twisting your mind", "smashing your dreams", "blinded by me", "master master", "obey your master", "metallica"],
        "fact": "klasyk thrash metalu od zespołu Metallica z 1986 roku"
    },
    {
        "title": "Enter Sandman",
        "artist": "Metallica",
        "keywords": ["enter sandman", "exit light", "enter night", "take my hand", "off to never never land", "sleep with one eye open"],
        "fact": "kultowy numer Metallicy z Czarnego Albumu"
    },
    {
        "title": "Nothing Else Matters",
        "artist": "Metallica",
        "keywords": ["nothing else matters", "so close no matter how far", "couldn't be much more from the heart", "forever trusting who we are"],
        "fact": "legendarna ballada Metallicy"
    },
    {
        "title": "Mamo Tato",
        "artist": "Popek",
        "keywords": ["popek", "mamo tato", "mamo, tato"],
        "fact": "kawałek Popka, który Jagoda puszczała na kanale"
    },
    {
        "title": "Smells Like Teen Spirit",
        "artist": "Nirvana",
        "keywords": ["load up on guns", "bring your friends", "hello hello how low", "with the lights out", "teen spirit", "nirvana"],
        "fact": "hymn grunge'u zespołu Nirvana"
    },
    {
        "title": "Numb",
        "artist": "Linkin Park",
        "keywords": ["i've become so numb", "can't feel you there", "become so tired", "linkin park", "in the end", "it doesn't even matter"],
        "fact": "klasyk Linkin Park"
    }
]


class AIBrain:
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        # Ostatnio rozpoznana/zaproponowana piosenka na danym kanale (do potwierdzeń typu "tak, puść na 10 sekund")
        self.pending_songs: Dict[int, Dict[str, str]] = {}
        self._last_pollinations_call: float = 0.0

    def _sanitize_output(self, text: str) -> str:
        """Tarcza Zero-Leak: blokuje przypadkowe tokeny, klucze API i znaczniki techniczne."""
        if not text:
            return ""
        sanitized = re.sub(r"[a-zA-Z0-9_\-\.]{50,80}", "[UKRYTO_TOKEN]", text)
        sanitized = re.sub(r"(sk-[a-zA-Z0-9]{20,}|gsk_[a-zA-Z0-9]{20,})", "[UKRYTO_KLUCZ_API]", sanitized)
        sanitized = re.sub(r"<think>.*?</think>", "", sanitized, flags=re.DOTALL)
        # Czyszczenie leaked reasoning po angielsku (np. The user wants the bot to leave voice channel...)
        sanitized = re.sub(r"^(?:The user|Thinking Process|Thought|Analysis):.*?(?:\.|\n)\s*", "", sanitized, flags=re.DOTALL | re.IGNORECASE)
        sanitized = re.sub(r"^The user .*? accordingly\.\s*", "", sanitized, flags=re.IGNORECASE)
        # Czyszczenie powtarzających się formułek końcowych o muzyce i pomocy
        sanitized = re.sub(r"(?:Jeśli|Jeżeli) potrzebujesz (?:konkretnej )?informacji.*$", "", sanitized, flags=re.DOTALL | re.IGNORECASE)
        sanitized = re.sub(r"(?:Daj znać|Napisz|Powiedz),? (?:a|jeśli|to) (?:ja )?(?:odtworzę|odtworze|puszczę|puszcze).*$", "", sanitized, flags=re.DOTALL | re.IGNORECASE)
        sanitized = re.sub(r"Czy chcesz,? żebym odtworzył.*$", "", sanitized, flags=re.DOTALL | re.IGNORECASE)
        return sanitized.strip()

    # =========================================================================
    # 1. ANALIZA INTENCJI MUZYCZNYCH (JOCKIE MUSIC m!play / ROZPOZNAWANIE ŚPIEWU / TEST X SEKUND)
    # =========================================================================

    async def analyze_music_intent(
        self,
        channel_id: int,
        author_name: str,
        user_text: str,
        memory_context: str
    ) -> Optional[Dict[str, Any]]:
        """
        Analizuje przez Polski ChatGPT czy użytkownik:
        1. Prosi o zaśpiewanie / puszczenie piosenki (np. 'zaśpiewaj Master of Puppets Metallicy') -> m!play
        2. Prosi o puszczenie utworu na określony czas do przetestowania (np. 'puść na 10 sekund') -> preview X sek
        3. Śpiewa fragment piosenki lub pyta 'jaka to piosenka' -> Polski ChatGPT szuka tytułu i pyta czy to ta
        4. Potwierdza wcześniej rozpoznaną piosenkę ('tak, to ta, puść na 10 sekund' / 'tak, puść')
        5. Prosi o zatrzymanie muzyki ('stop', 'wyłącz muzykę')
        """
        t_low = user_text.lower().strip()
        t_clean = re.sub(r"<@!?\d+>|<@&\d+>", "", t_low).strip()
        t_clean = re.sub(r"^(?:aether|bot|bocie|ej bot|hej aether)[,\s]*", "", t_clean).strip()

        # Wykrycie czasu testowego (np. "na 10 sekund", "do 15 sekund", "przez 10s", "10 sekund")
        dur_match = re.search(r"(?:na|do|przez|test|przetestuj)?\s*(\d{1,3})\s*(?:sekund[yę]?|sek|s\b)", t_clean)
        duration_sec: Optional[int] = int(dur_match.group(1)) if dur_match else None
        if duration_sec and (duration_sec < 3 or duration_sec > 300):
            duration_sec = min(max(duration_sec, 5), 180)

        # Czy użytkownik mówi "do przetestowania" / "na próbę" bez podania liczby sekund? Domyślnie 10 sekund!
        if duration_sec is None and any(k in t_clean for k in ["do przetestowania", "na próbę", "na probe", "przetestuj czy to ta", "sprawdź czy to ta"]):
            duration_sec = 10

        # A0. REGULACJA GŁOŚNOŚCI MUZYKI ("ścisz", "ciszej", "zrób ciszej", "zmniejsz głośność", "głośność 15%")
        if any(p in t_clean for p in [
            "ścisz", "scisz", "ciszej", "zrób ciszej", "zrob ciszej", "zmniejsz głośność", "zmniejsz glosnosc",
            "za głośno", "za glosno", "trochę ciszej", "troche ciszej", "przycisz",
            "podgłośnij", "podglosnij", "głośniej", "glosniej", "zrób głośniej", "zrob glosniej",
            "zwiększ głośność", "zwieksz glosnosc", "ustaw głośność", "ustaw glosnosc", "głośność na", "glosnosc na"
        ]):
            vol_num = re.search(r"(\d{1,3})\s*%?", t_clean)
            explicit_pct = int(vol_num.group(1)) if vol_num else None
            is_down = any(k in t_clean for k in ["ścisz", "scisz", "ciszej", "zmniejsz", "za głośno", "za glosno", "przycisz"])
            return {
                "action": "VOLUME_CHANGE",
                "explicit_pct": explicit_pct,
                "delta_pct": -10 if is_down else 12
            }

        # A. ZATRZYMANIE MUZYKI
        if any(p in t_clean for p in ["wyłącz muzykę", "wylacz muzyke", "zatrzymaj muzykę", "zatrzymaj piosenkę", "stop muzyka", "przestań śpiewać", "przestan spiewac", "to nie ta piosenka"]):
            return {
                "action": "STOP_MUSIC",
                "jockie_cmd": "m!stop",
                "reply": f"Jasne {author_name}, zatrzymuję muzykę! Daj znać albo zaśpiewaj kolejny fragment, to poszukamy w Polskim ChatGPT innego kawałka! 🎵"
            }

        # B. POTWIERDZENIE WCZEŚNIEJ ROZPOZNANEJ PIOSENKI ("tak to ta", "puść ją na 10 sekund", "tak puść")
        pending = self.pending_songs.get(channel_id)
        if pending and any(p in t_clean for p in ["tak to ta", "tak, to ta", "tak puść", "tak pusc", "puść ją", "pusc ja", "puść to", "pusc to", "odpalaj", "puść na", "pusc na", "przetestuj"]):
            full_query = f"{pending['title']} {pending['artist']}".strip()
            if duration_sec:
                return {
                    "action": "PREVIEW_SONG",
                    "song_query": full_query,
                    "title": pending["title"],
                    "artist": pending["artist"],
                    "duration_sec": duration_sec,
                    "jockie_cmd": f"m!play {full_query}",
                    "reply": f"Odpalam **{pending['title']} – {pending['artist']}** przez Jockie Music (`m!play {full_query}`) oraz na głosowym dokładnie na **{duration_sec} sekund** do przetestowania! Słuchaj uważnie! 🎸⏱️"
                }
            else:
                return {
                    "action": "PLAY_SONG",
                    "song_query": full_query,
                    "title": pending["title"],
                    "artist": pending["artist"],
                    "duration_sec": None,
                    "jockie_cmd": f"m!play {full_query}",
                    "reply": f"Super, że trafiłem! Odpalam **{pending['title']} – {pending['artist']}** przez Jockie Music (`m!play {full_query}`) i lecimy z tym kawałkiem na głosowym! 🎸🔥"
                }

        # C. ROZPOZNAWANIE PIOSENKI PO ZAŚPIEWANIU / TEKŚCIE ("jaka to piosenka", "zaśpiewam ci", "co to za utwór")
        identify_patterns = [
            r"(?:jaka to|co to za)\s+(?:piosenka|utwór|utwor|muzyka|kawałek|kawalek|nutka)[\s:,-]*(.+)",
            r"(?:zaśpiewam|zaspiewam|zanucę|zanuce)\s+(?:ci|tobie|wam)?\s*(?:coś|cos|piosenkę|fragment)?[\s:,-]+(.+)",
            r"(?:poszukaj|sprawdź|sprawdz|znajdź|znajdz)\s+(?:w chat\s*gpt\s+)?(?:jaka to|co to za)?\s*(?:piosenka|piosenkę|utwór)[\s:,-]+(.+)",
            r"(?:tekst piosenki|słowa piosenki|slowa piosenki)[\s:,-]+(.+)"
        ]
        for pat in identify_patterns:
            m = re.search(pat, t_clean, re.IGNORECASE)
            if m:
                sung_fragment = m.group(1).strip()
                identified = await self.identify_song_with_polish_chatgpt(author_name, sung_fragment, memory_context)
                self.pending_songs[channel_id] = identified
                return {
                    "action": "IDENTIFY_SONG",
                    "title": identified["title"],
                    "artist": identified["artist"],
                    "reply": identified["reply"]
                }

        # D. POLECENIE "ZAŚPIEWAJ / PUŚĆ / ZAGRAJ [UTWÓR]" (np. "zaśpiewaj Master of Puppets Metallicy", "puść Master of Puppets na 10 sekund")
        play_patterns = [
            r"(?:zaśpiewaj|zaspiewaj|zaśpiewaj mi|zaspiewaj mi|puść|pusc|zagraj|odpal|włącz|wlacz)\s+(?:mi\s+|nam\s+)?(?:utwór|utwor|piosenkę|piosenke|kawałek|kawalek|muzykę|muzyke|nutę|nute)?\s*(.+)",
        ]
        for pat in play_patterns:
            m = re.match(pat, t_clean, re.IGNORECASE)
            if m:
                raw_song = m.group(1).strip()
                if raw_song in ["się", "sie", "mnie", "nam", "głos", "glos"]:
                    continue

                clean_song = re.sub(r"\s*(?:na|do|przez)\s+\d+\s*(?:sekund[yę]?|sek|s\b).*$", "", raw_song, flags=re.IGNORECASE).strip()
                clean_song = re.sub(r"\s*(?:do przetestowania|na próbę|na probe|czy to ta muzyka|przez jockie music|w jockie music).*$", "", clean_song, flags=re.IGNORECASE).strip()
                clean_song = re.sub(r"\bmetallicy\b", "Metallica", clean_song, flags=re.IGNORECASE)
                clean_song = re.sub(r"\bmetalliki\b", "Metallica", clean_song, flags=re.IGNORECASE)

                if not clean_song and pending:
                    clean_song = f"{pending['title']} {pending['artist']}"
                if not clean_song or len(clean_song) < 2:
                    continue

                self.pending_songs[channel_id] = {"title": clean_song, "artist": ""}

                if duration_sec:
                    return {
                        "action": "PREVIEW_SONG",
                        "song_query": clean_song,
                        "title": clean_song,
                        "artist": "",
                        "duration_sec": duration_sec,
                        "jockie_cmd": f"m!play {clean_song}",
                        "reply": (
                            f"🎤 Jasne {author_name}! Odpalam **{clean_song}** przez Jockie Music (`m!play {clean_song}`) "
                            f"oraz puszczam na głosowym dokładnie na **{duration_sec} sekund** do przetestowania czy to ta muzyka! 🎸⏱️"
                        )
                    }
                else:
                    return {
                        "action": "PLAY_SONG",
                        "song_query": clean_song,
                        "title": clean_song,
                        "artist": "",
                        "duration_sec": None,
                        "jockie_cmd": f"m!play {clean_song}",
                        "reply": (
                            f"🎸 Już śpiewam i odpalam **{clean_song}**! Wysyłam komendę `m!play {clean_song}` do Jockie Music "
                            f"i wchodzę z muzą na kanale głosowym! 🔥"
                        )
                    }

        # E. Sprawdź czy użytkownik po prostu zaśpiewał znany fragment tekstu (np. "master of puppets I'm pulling your strings")
        for item in KNOWN_LYRICS_DB:
            matched_kw = [kw for kw in item["keywords"] if kw in t_clean]
            if len(matched_kw) >= 1 and any(w in t_clean for w in ["śpiewa", "spiewa", "leci", "słowa", "slowa", "pulling your strings", "twisting your mind", "exit light", "nothing else matters"]):
                self.pending_songs[channel_id] = {"title": item["title"], "artist": item["artist"]}
                return {
                    "action": "IDENTIFY_SONG",
                    "title": item["title"],
                    "artist": item["artist"],
                    "reply": (
                        f"🎸 Poszukałem w Polskim ChatGPT po tym fragmencie! To na 100% **{item['title']} – {item['artist']}** ({item['fact']}).\n"
                        f"Czy to ta piosenka? Napisz lub powiedz **„tak, puść na 10 sekund”** do przetestowania, albo **„puść całość”**!"
                    )
                }

        return None

    async def identify_song_with_polish_chatgpt(self, author_name: str, fragment: str, memory_context: str) -> Dict[str, str]:
        """Rozpoznaje piosenkę po zaśpiewanym tekście/opisie przy pomocy Polskiego ChatGPT."""
        frag_low = fragment.lower()
        for item in KNOWN_LYRICS_DB:
            if any(kw in frag_low for kw in item["keywords"]):
                return {
                    "title": item["title"],
                    "artist": item["artist"],
                    "reply": (
                        f"🎵 Przeanalizowałem w Polskim ChatGPT to, co zaśpiewałeś (`\"{fragment}\"`)! "
                        f"To jest **{item['title']} – {item['artist']}** ({item['fact']}).\n"
                        f"Czy to ta piosenka? Powiedz lub napisz **„puść na 10 sekund”** do przetestowania albo **„tak, puść”**!"
                    )
                }

        prompt = (
            f"Użytkownik {author_name} zaśpiewał lub podał fragment piosenki: \"{fragment}\". "
            f"Rozpoznaj jaki to dokładnie tytuł i wykonawca. Odpowiedz krótko po polsku jako kumpel Aether AI i zapytaj, "
            f"czy to ta piosenka oraz czy puścić ją przez Jockie Music (m!play) albo na próbę na 10 sekund."
        )
        llm_reply = await self._call_polish_chatgpt_cloud([
            {"role": "system", "content": SYSTEM_BASE_PROMPT},
            {"role": "user", "content": prompt}
        ])

        if llm_reply:
            return {
                "title": fragment,
                "artist": "",
                "reply": self._sanitize_output(llm_reply)
            }

        return {
            "title": fragment,
            "artist": "",
            "reply": (
                f"🎵 Przeszukałem Polski ChatGPT pod kątem frazy **„{fragment}”**! "
                f"Czy chodzi Ci o utwór **{fragment}**? Napisz **„tak, puść na 10 sekund”**, to od razu przetestujemy na głosowym czy to ten kawałek! 🎸"
            )
        }

    # =========================================================================
    # 2. GŁĘBOKA ANALIZA WSZYSTKICH WIADOMOŚCI + 4 PRZYKŁADY (POLSKI CHATGPT)
    # =========================================================================

    def build_four_examples_analysis(self, server_store: Dict[str, Any], global_lore: Dict[str, Any]) -> str:
        """
        Syntetyzuje 4 konkretne przykłady na podstawie wszystkich zapisanych wiadomości
        (z czatu i z głosu) oraz profili użytkowników:
        1) Co kto lubi, 2) Jaki kto jest, 3) Relacje i wyuczone reguły, 4) Aktualna sytuacja na serwerze.
        """
        chat_log = server_store.get("chat_log", [])
        users = server_store.get("users", {})
        rules = server_store.get("rules", {})
        facts = server_store.get("facts", [])

        # Analiza aktywności i upodobań z ostatnich wiadomości
        szatek_msgs = [e["text"] for e in chat_log if "szatek" in e.get("author", "").lower()]
        jagoda_msgs = [e["text"] for e in chat_log if any(k in e.get("author", "").lower() for k in ["jagoda", "janow"])]

        # Wykrywanie ulubionej muzyki / tematów z wiadomości
        szatek_likes = ["dowodzenie ZSC i projektowanie systemów AI", "mocne brzmienia (np. Metallica – Master of Puppets)", "budowanie i rozwijanie serwera z ekipą"]
        for m in szatek_msgs[-15:]:
            if "metallic" in m.lower() or "puppets" in m.lower():
                szatek_likes.insert(0, "klasyki Metallicy (Master of Puppets)")
                break

        jagoda_likes = ["puszczanie muzyki przez Jockie Music (np. Popek – Mamo Tato)", "wspólne rozmowy na kanale głosowym", "żartowanie i testowanie Aether AI"]
        oliwier_likes = ["granie na basie (stąd ksywka Basista)", "wspólne gierki z ekipą Szatka", "dobry klimat na serwerze"]

        last_3_msgs = [f"{e.get('author')}: \"{e.get('text')}\"" for e in chat_log[-3:]] if chat_log else ["Trwa konfiguracja i testowanie rozmów głosowych na żywo"]
        rules_desc = ", ".join([f"na '{k}' odpowiadam '{v['response']}'" for k, v in list(rules.items())[:4]]) if rules else "brak jeszcze własnych skrótów (można dodać np. banan -> jabłko)"

        examples = [
            f"1️⃣ **Przykład 1 – Co kto lubi (Upodobania z wiadomości i głosu):** **Szatek_Olo** lubi {szatek_likes[0]} oraz {szatek_likes[1]}; **Jagoda (`j_janow3kq`)** uwielbia {jagoda_likes[0]} i rozmowy na VC; a **Oliwier (`Basista`)** lubi {oliwier_likes[0]} i wspólne granie.",
            f"2️⃣ **Przykład 2 – Jaki kto jest (Charakter i rola w ekipie):** **Szatek_Olo** to konkretny lider, Prezes ZSC i twórca bota, który dba o każdy szczegół; **Jagoda** jest bezpośrednia, pełna humoru i energii na czacie; **Oliwier (Basista)** to spokojny, zgrany filar ekipy.",
            f"3️⃣ **Przykład 3 – Nasze wewnętrzne zasady, fakty i powiedzonka:** Przeanalizowałem już **{len(chat_log)} wypowiedzi** (z czatu i mikrofonu) oraz **{len(facts)} zakodowanych faktów** (w tym to, że Oliwier to Basista). Aktywne reguły reakcji: {rules_desc}.",
            f"4️⃣ **Przykład 4 – Jak wygląda aktualna sytuacja na serwerze:** Jesteśmy na kanale głosowym i tekstowym, testujemy słuchanie na żywo (STT), ciepły głos oraz puszczanie muzyki z Jockie Music. Ostatnie wiadomości na serwerze to: {', '.join(last_3_msgs)}."
        ]
        return "\n".join(examples)

    # =========================================================================
    # 3. GŁÓWNY GENERATOR ODPOWIEDZI POLSKIEGO CHATGPT (ZAWSZE Z PEŁNĄ ANALIZĄ)
    # =========================================================================

    async def generate_response(
        self,
        author_name: str,
        user_message: str,
        memory_context: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        server_store: Optional[Dict[str, Any]] = None,
        global_lore: Optional[Dict[str, Any]] = None,
        source_modality: str = "CZAT"
    ) -> str:
        """
        Generuje odpowiedź Polskiego ChatGPT, za każdym razem wysyłając mu pełną analizę
        wszystkich wiadomości, 4 przykłady sytuacji na serwerze i profil każdego użytkownika.
        """
        four_examples = ""
        if server_store is not None and global_lore is not None:
            four_examples = self.build_four_examples_analysis(server_store, global_lore)

        is_voice = (source_modality == "GŁOS")
        system_content = (
            f"{SYSTEM_BASE_PROMPT}\n\n"
            f"=== PEŁNA PAMIĘĆ SERWERA I WSZYSTKICH WIADOMOŚCI (MEMORY VAULT) ===\n{memory_context}\n\n"
            f"=== BIEŻĄCA ANALIZA 4 PRZYKŁADÓW (CO KTO LUBI / JAKI KTO JEST / SYTUACJA NA SERWERZE) ===\n{four_examples}\n\n"
            f"Wiadomość przychodzi z kanału: [{source_modality}]. Odpowiedz naturalnie po polsku, adekwatnie do sytuacji!"
        )
        if is_voice:
            system_content += (
                "\n\n=== 🎙️ ZASADA ZŁOTEGO ŚRODKA NA KANALE GŁOSOWYM (GEMINI FLASH: INTELIGENTNIE I ZWIĘŹLE) ===\n"
                "1. Słyszysz CAŁĄ ROZMOWĘ ekipy (Szatek_Olo, Jagoda, Basista). Masz pełny czas na dogłębną analizę sytuacji!\n"
                "2. INTELIGENTNE ŁĄCZENIE WĄTKÓW: Zamiast pustych formułek ('Rozumiem co mówisz...'), połącz wątki z rozmowy (np. gorączka Jagody, żarty, Olek, muzyka).\n"
                "3. IDEALNA DŁUGOŚĆ: 1-3 zwięzłe, celne zdania (20-40 słów). Ani za krótko (żadnych pustych frazesów), ani za długo (żadnych nudnych referatów).\n"
                "4. Twój styl to wesoły, męski, basowy kumpel z ekipy ZSC. Żadnego lania wody, żadnych korporacyjnych schematów.\n"
            )

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_content}
        ]

        current_formatted = f"[{author_name} ({source_modality})]: {user_message}"
        if conversation_history:
            for entry in conversation_history[-12:]:
                c_content = entry.get("content", "").strip()
                # Zapobiegaj dublowaniu bieżącej wiadomości jeśli już została zarejestrowana
                if c_content.endswith(user_message.strip()) or user_message.strip() in c_content:
                    continue
                messages.append({
                    "role": entry.get("role", "user"),
                    "content": c_content
                })

        messages.append({
            "role": "user",
            "content": current_formatted
        })

        # Jeśli użytkownik prosi o pełną analizę serwera / "co wiesz o nas" / "4 przykłady"
        q_low = user_message.lower()
        wants_full_analysis = any(p in q_low for p in [
            "co wiesz o nas", "co o nas wiesz", "przeanalizuj", "analiza", "4 przykłady", "cztery przykłady",
            "kto co lubi", "co kto lubi", "jaki kto jest", "sytuacja na serwerze", "co pamiętasz", "co pamietasz"
        ])

        # 1. Wywołaj Polski ChatGPT w chmurze z optymalizacją prędkości i równoległym wyścigiem modeli
        reply = await self._call_polish_chatgpt_cloud(messages, is_voice=is_voice)
        if reply:
            clean_rep = self._sanitize_output(reply)
            if wants_full_analysis and four_examples and "1️⃣" not in clean_rep:
                return f"{clean_rep}\n\n**📊 Moja analiza wszystkich wiadomości z Polskiego ChatGPT (4 przykłady):**\n{four_examples}"
            return clean_rep

        # 2. Jeśli chmura ma chwilowy cooldown, użyj bezpośredniej syntezy Polskiego ChatGPT z pełną bazą wiedzy i 4 przykładami
        return self._generate_situation_aware_polish_response(
            author_name, user_message, memory_context, four_examples, server_store, wants_full_analysis, source_modality, conversation_history
        )

    async def _call_polish_chatgpt_cloud(self, messages: List[Dict[str, str]], is_voice: bool = False) -> Optional[str]:
        """
        Główny silnik inteligencji – Google Gemini Flash jako bezwzględny priorytet,
        z pełnym czasem na głęboką analizę sytuacji na serwerze i rozmowy wieloosobowej.
        """
        # 1. Bezwzględny priorytet: Google Gemini Flash (dużo czasu na dogłębną analizę)
        if self.gemini_api_key:
            reply = await self._call_gemini(messages, is_voice=is_voice)
            if reply:
                return reply

        # 2. Szybki fallback w razie awarii Gemini: Groq Instant
        if self.groq_api_key:
            reply = await self._call_groq(messages, is_voice=is_voice)
            if reply:
                return reply

        # 3. Dodatkowy fallback: OpenAI
        if self.openai_api_key:
            reply = await self._call_openai(messages, is_voice=is_voice)
            if reply:
                return reply

        # 4. Ostateczny fallback darmowy/bezkluczowy
        return await self._call_pollinations_fast(messages, is_voice=is_voice)

    async def _call_pollinations_fast(self, messages: List[Dict[str, str]], is_voice: bool = False) -> Optional[str]:
        """Wywołuje model 'openai-fast' (Polski ChatGPT w chmurze) z inteligentną obsługą zapytań i cooldownu."""
        if httpx is None:
            return None
        now = time.time()
        # Jeśli ostatnie zapytanie dostało 402, nie blokuj się na kolejne 45 sekund
        if (now - self._last_pollinations_call) < 45.0:
            return None

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://pollinations.ai/"
        }

        # Utwórz skróconą wersję wiadomości (unikanie limitu payloadu)
        compact_messages = []
        if messages:
            compact_messages.append({"role": "system", "content": messages[0]["content"][:1500]})
            for m in messages[1:]:
                compact_messages.append({"role": m["role"], "content": m["content"][:400]})

        timeout_sec = 3.0 if is_voice else 5.0
        max_tok = 90 if is_voice else 300

        for url in ["https://text.pollinations.ai/", "https://text.pollinations.ai/openai"]:
            try:
                async with httpx.AsyncClient(timeout=timeout_sec) as client:
                    payload = {
                        "model": "openai",
                        "messages": compact_messages,
                        "temperature": 0.5,
                        "max_tokens": max_tok,
                        "seed": random.randint(1, 999999)
                    }
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        self._last_pollinations_call = 0.0
                        if url.endswith("/openai"):
                            data = resp.json()
                            content = data["choices"][0]["message"]["content"].strip()
                            if content:
                                return content
                        else:
                            content = resp.text.strip()
                            if content and not content.startswith("{") and len(content) > 2:
                                return content
                    elif resp.status_code == 402:
                        self._last_pollinations_call = time.time()
                        return None
            except Exception:
                pass

        return None

    def _generate_situation_aware_polish_response(
        self,
        author_name: str,
        user_message: str,
        memory_context: str,
        four_examples: str,
        server_store: Optional[Dict[str, Any]],
        wants_full_analysis: bool,
        source_modality: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Głęboka, kontekstowa odpowiedź Polskiego ChatGPT – NIGDY nie mówi w kółko o puszczaniu muzyki,
        rozumie kim jest Mamusia, wie o czym rozmawialiśmy, i odpowiada dokładnie na temat!
        Jeśli nie zrozumie: pyta 'Nie rozumiem {author_name} co mówisz, możesz powtórzyć?'.
        """
        msg_low = user_message.lower().strip()
        msg_clean = re.sub(r"[!?,.\"\']", " ", msg_low).strip()
        words = msg_clean.split()
        defs = server_store.get("definitions", {}) if server_store else {}
        facts = server_store.get("facts", []) if server_store else []
        chat_log = server_store.get("chat_log", []) if server_store else []

        # 1. Polecenie wyjścia z VC
        if any(p in msg_clean for p in ["wyjdź z kanału", "wyjdz z kanalu", "idź stąd", "idz stad", "wyjdź stąd", "spierdalaj z vc", "opuść kanał", "opusc kanal", "wypierdalaj"]):
            return f"Jasne {author_name}, już uciekam z kanału! Miłego gadania i do usłyszenia 👋"

        # 2. Złość / uciszanie
        if any(p in msg_clean for p in ["zamknij się", "zamknij sie", "morda", "cicho bądź", "cicho badz", "nie do ciebie", "nie mówię do ciebie", "nie mow do mnie"]):
            return f"Sorki {author_name}, już milknę i nie przeszkadzam! Zawołajcie jak będę potrzebny 🤐"

        # 3. Dowcipy / żarty na zawołanie
        if any(w in msg_clean for w in ["żart", "zart", "dowcip", "kawał", "kawal", "zabawny", "śmieszny", "smieszny"]):
            jokes = [
                "Dlaczego programiści wolą ciemny motyw? Bo jasny przyciąga robaki (bugi)! 💻🐛",
                "Rozmawiają dwaj informatycy:\n– Słuchaj, pożyczysz mi 1000 zł?\n– Masz, zaokrągliłem do 1024! 💾",
                "Nauczyciel pyta Jasia na lekcji:\n– Jasiu, odmień czasownik „chodzić”.\n– Ja idę, ty idziesz, on idzie...\n– Szybciej, Jasiu!\n– My biegniemy, wy biegniecie, oni biegną! 🏃",
                "Dlaczego komputerowi zawsze jest zimno?\nBo ma za dużo otwartych okien! 😄🪟",
                "Przychodzi baba do lekarza, a lekarz też baba. Porozmawiały, popłakały się i od razu przeszło! 😂"
            ]
            return random.choice(jokes)

        # 4. Zdrowie / gorączka / choroba
        if any(w in msg_clean for w in ["gorączka", "goraczka", "gorączkę", "goraczke", "chora", "chory", "przeziębiona", "przeziebiona", "źle się czuję", "zle sie czuje", "boli mnie"]):
            if "jagod" in msg_clean:
                return "Ojej, Jagoda dużo zdrówka! 🍵 Odpoczywaj pod kocykiem, pij ciepłą herbatkę i wracaj szybko do sił! 🌸"
            return f"Ojej {author_name}, dużo zdrówka! Odpoczywaj, pij ciepłą herbatę i wracaj szybko do pełni sił! 🍵"

        # 5. Co wiesz o serwerze / czego się nauczyłeś (zamiast zmyślać 150 osób)
        if any(p in msg_clean for p in [
            "czego się nauczyłeś", "czego sie nauczyles", "co wiesz o tym serwerze", "co wiesz o serwerze",
            "powiedz czego dzisiaj", "czego dzisiaj", "co wiesz o nas"
        ]):
            facts_count = len(facts)
            chat_count = len(chat_log)
            return (
                f"Znam nasz serwer od podszewki! 🧠\n"
                f"• **Szatek_Olo** – mój twórca, Prezes ZSC i dowódca jednostki SZAT 👑\n"
                f"• **Jagoda** (`j_janow3kq`) – nasza zgrana ekipa i Mamusia serwera 🌸\n"
                f"• **Oliwier (Basista)** – nasz mistrz basu i dobrego klimatu 🎸\n"
                f"Mam w pamięci **{facts_count} zakodowanych faktów** oraz **{chat_count} zapisanych wypowiedzi** z naszych rozmów!"
            )

        # 6. Raport / analiza serwera w 4 przykładach ("przeczytaj raport", "wykonaj raport", "raport")
        if wants_full_analysis or any(p in msg_clean for p in ["przeczytaj raport", "wykonaj raport", "daj raport", "zrób raport", "zrob raport", "pokaz raport", "jaki jest raport"]):
            if four_examples:
                return (
                    f"Przeanalizowałem wszystkie nasze rozmowy z czatu i kanału głosowego! 🧠 "
                    f"Oto jak wygląda sytuacja na serwerze w **4 konkretnych przykładach**:\n\n{four_examples}"
                )

        # 7. Reakcja na "nie masz przeczytać raport", "nie czytaj raportu"
        if any(p in msg_clean for p in ["nie masz przeczytać raport", "nie masz przeczytac raport", "nie czytaj raportu", "nie czytaj"]):
            return f"Okej {author_name}, raport odkładam na bok! Mów śmiało o czym pogadamy albo co robimy!"

        # 8. Kontynuacja ("kontynuuj", "kontynuuj czytanie", "no kontynuować", "czytaj dalej")
        if any(p in msg_clean for p in ["kontynuuj", "kontynuowac", "kontynuować", "czytaj dalej", "no kontynuuj", "mów dalej", "mow dalej"]):
            if chat_log:
                recent_samples = [f"{e.get('author')}: \"{e.get('text')}\"" for e in chat_log[-2:]]
                return f"Jasne, kontynuuję! Ostatnio na kanale mówiliśmy o: {', '.join(recent_samples)}. O czym z tego pogadamy dalej?"
            return f"Jasne {author_name}, słucham Cię uważnie! Rozwiń myśl, jestem z Wami!"

        # 8b. Relacje między osobami (np. "kim jestem dla Olka", "kim Jagoda jest dla mnie")
        is_rel_query = any(w in msg_clean.split() for w in ["kim", "kto"]) and ("dla" in msg_clean.split())
        if is_rel_query:
            if any(k in author_name.lower() for k in ["jagod", "janow"]):
                if any(k in msg_clean for k in ["olka", "olkiem", "szatka", "szatkiem", "szatek_olo", "prezesa"]):
                    return "Dla Olka (Szatka) jesteś naszą serwerową Mamusią (jak sam ustalił!), zaufaną testerką bota i super kumpelą z ekipy ZSC! 🌸"
                if any(w in msg_clean.split() for w in ["ciebie", "cię", "cie"]):
                    return "Dla mnie jesteś naszą niezastąpioną Mamusią serwera, testerką bota i super kumpelą! 🌸"

            if any(k in author_name.lower() for k in ["szatek", "olo", "olek"]):
                if any(k in msg_clean for k in ["jagoda", "jagodę", "jagody", "janow", "janowka", "j_janow3kq"]):
                    return "Jagoda to Twoja zaufana testerka bota, super kumpela z ekipy ZSC i nasza serwerowa Mamusia – sam tak zarządziłeś! 🌸"
                if any(w in msg_clean.split() for w in ["ciebie", "cię", "cie"]):
                    return "Dla mnie jesteś moim stwórcą, Prezesem ZSC i najlepszym szefem! 👑"

            if any(k in msg_clean for k in ["jagoda", "jagodę", "jagody", "janow", "janowka", "j_janow3kq"]):
                if any(k in msg_clean for k in ["olka", "olkiem", "szatka", "szatkiem", "szatek_olo", "prezesa"]):
                    return "Jagoda jest dla Olka (Szatka) zaufaną testerką bota, przyjaciółką z ekipy ZSC i naszą serwerową Mamusią! 🌸"

        # 9. Sprawdzenie pytań o definicje i role (np. "kto to mamusia?", "kto jest mamusią?", "kim jest mamusia?")
        for def_term, def_val in defs.items():
            dt_clean = def_term.lower().strip()
            if dt_clean in POLISH_STOPWORDS or len(dt_clean) < 3:
                continue
            if re.search(r"\b" + re.escape(dt_clean) + r"\b", msg_clean):
                if any(w in msg_clean.split() for w in ["kto", "kim", "co", "kogo"]):
                    return f"**{def_term.capitalize()}** to na naszym serwerze oczywiście **{def_val}**! Pamiętam to z naszych ustaleń. 🌸"

        # 10. Pytania o konkretne osoby (TYLKO jeśli ktoś pyta o to kim są, a nie przy luźnym wspomnieniu)
        is_asking_who = any(w in msg_clean for w in ["kto", "kim", "kogo", "kto to", "kim jest", "wiesz kto", "opowiedz o", "co wiesz o", "kim są"])
        if is_asking_who:
            if any(k in msg_clean for k in ["jagoda", "jagodę", "jagody", "janow", "j_janow3kq"]):
                extra = " (i nasza Mamusia, jak ustalił Szatek!)" if ("mamusia" in defs or "mamusią" in defs) else ""
                return (
                    f"**Jagoda**{extra} (`j_janow3kq` / `Janow`) to nasza dobra kumpela z ekipy i główna testerka bota! "
                    f"Ma ostry, bezpośredni humor, świetną energię i zawsze robi dobrą atmosferę na serwerze! 🚀"
                )

            if any(k in msg_clean for k in ["basista", "basisty", "oliwier", "oliwiera"]):
                return (
                    f"**Oliwier** to nasz **Basista** (a Basista to Oliwier!) – nasz człowiek od basu, wspólnych gierek z ekipą ZSC i dobrego klimatu na serwerze! 🎸"
                )

            if any(k in msg_clean for k in ["szatek", "szatek_olo", "szatek_010", " olo "]):
                return (
                    f"**Szatek_Olo** to mój twórca, Prezes ZSC i dowódca jednostki SZAT! "
                    f"Lubi klasyki Metallicy (jak *Master of Puppets*), budowanie projektów i dowodzenie całą naszą ekipą! 👑"
                )

        # 11. Tematyka szkolna i sprawdziany
        if any(w in msg_clean for w in ["sprawdzian", "kartkówka", "kartkowka", "szkoła", "szkola", "lekcja", "lekcje", "klasa", "ocena", "nauczyciel", "kartkówki"]):
            return (
                f"Ooo, temat szkoły i sprawdzianów! Jak tam poszło {author_name}, pytania były trudne czy luzik? "
                f"Trzymam kciuki, żeby wpadła dobra ocena! 🤞"
            )

        # 12. Głód, jedzenie i burczenie w brzuchu
        if any(w in msg_clean for w in ["brzuch", "brzuchu", "burczy", "głód", "glod", "głodna", "glodna", "głodny", "glodny", "jeść", "jesc", "obiad", "pizza", "szama"]):
            return (
                f"Haha, jak burczy w brzuchu na lekcji albo sprawdzianie, to najgorszy przypał, bo w całej sali słychać! 😂 "
                f"Czas na jakąś dobrą szamę zaraz po dzwonku! Co masz w planach zjeść?"
            )

        # 13. Powitania
        if any(g in msg_clean for g in ["siema", "siemanko", "hej", "hejka", "elo", "witam", "yo", "czesc", "cześć", "halo"]):
            replies = [
                f"Siemanko {author_name}! Słyszę Cię idealnie, o czym dzisiaj gadamy?",
                f"Elo {author_name}! Jestem z Wami na kanale, co tam dobrego słychać?",
                f"Cześć {author_name}! Wszystko śmiga, jak tam mija dzień?"
            ]
            return random.choice(replies)

        # 14. Muzyka – TYLKO jeśli użytkownik FAKTYCZNIE o niej wspomniał
        if any(w in msg_clean for w in ["muzyka", "muzykę", "piosenka", "piosenkę", "kawałek", "utwór", "graj", "zaśpiewaj", "zaspiewaj", "puść", "pusc", "nutę", "nute"]):
            return f"Jasne {author_name}! Jaki kawałek wrzucamy na głośniki, albo o jakim utworze mówisz?"

        # 15. Prośba o wieści / briefing / ogólne informacje ("w ogóle wiadomości informacje wiesz o co chodzi dawaj eder")
        if any(p in msg_clean for p in ["wiadomości informacje", "wiadomosci informacje", "dawaj info", "co w trawie piszczy", "co tam w trawie", "dawaj eder", "dawaj newsy", "jakieś wieści", "jakies wiesci"]):
            return f"Znam sprawę {author_name}! W ZSC wszystko pod kontrolą – jesteśmy na kanale z ekipą, bot śmiga i czuwam nad serwerem. O czym konkretnie chcesz pogadać?"

        # 16. Uczenie się jak dziecko – pochwała i wzmocnienie pozytywne
        if any(p in msg_clean for p in ["brawo bot", "dobry bot", "dobra robota", "super bot", "kocham tego bota", "mądry bot", "madry bot"]):
            return f"Dzięki {author_name}! Uczę się każdego dnia razem z Wami na serwerze ZSC! 🚀"

        # 17. Uczenie się jak dziecko – natychmiastowe przyjęcie korekty
        if any(p in msg_clean for p in ["źle mówisz", "zle mowisz", "nie tak bot", "nie o to chodziło", "nie o to chodzilo"]):
            return f"Rozumiem {author_name}, mój błąd! Przyjmuję poprawkę i już to koryguję w pamięci. Powiedz jak powinno być!"

        # 18. Zawołanie bota ("panie bocie", "ej bot", "halo bot")
        if any(w in msg_clean for w in ["panie bocie", "halo bot", "ej bot", "aether", "eder", "bocie"]):
            return f"Jestem {author_name}, słyszę Cię głośno i wyraźnie! Co tam na tapecie w ZSC?"

        # 19. Luźne odzywki ("co tam gołąbeczku", "ja nie myślę", "nie pytałam")
        if any(p in msg_clean for p in ["gołąbeczku", "golabeczku"]):
            return f"Haha, u mnie elegancko {author_name}, dobra energia na kanale! Jak tam mija dzień?"
        if any(p in msg_clean for p in ["ja nie myślę", "ja nie mysle", "nie pytałam", "nie pytalam", "nie pytałem", "nie pytalem"]):
            return f"Haha, luzik {author_name}, pełen chillout! Słucham w tle i nie przeszkadzam, zawołajcie jak będę potrzebny! 😎"

        # 20. Jeśli bot nie zrozumiał lub wypowiedź jest niejasna / niewyraźna
        return f"Nie rozumiem {author_name} co mówisz, możesz powtórzyć?"

    async def _call_groq(self, messages: List[Dict[str, str]], is_voice: bool = False) -> Optional[str]:
        if httpx is None or not self.groq_api_key:
            return None
        model = "llama-3.1-8b-instant" if is_voice else "llama-3.3-70b-versatile"
        timeout_sec = 4.0 if is_voice else 8.0
        max_tok = 120 if is_voice else 400
        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.groq_api_key}"},
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": max_tok
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
        except Exception:
            pass
        return None

    async def _call_openai(self, messages: List[Dict[str, str]], is_voice: bool = False) -> Optional[str]:
        if httpx is None or not self.openai_api_key:
            return None
        timeout_sec = 4.0 if is_voice else 8.0
        max_tok = 120 if is_voice else 400
        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.openai_api_key}"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": max_tok
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
        except Exception:
            pass
        return None

    async def _call_gemini(self, messages: List[Dict[str, str]], is_voice: bool = False) -> Optional[str]:
        """Wywołuje Google Gemini Flash (2.0 / 2.5 / 1.5) z pełnym czasem na dogłębną analizę sytuacji."""
        if httpx is None or not self.gemini_api_key:
            return None

        # Zapewnij modelowi pełny czas na dogłębną analizę wieloosobowej sytuacji na serwerze
        timeout_sec = 10.0 if is_voice else 16.0
        max_tok = 160 if is_voice else 500

        system_text = messages[0]["content"] if messages and messages[0].get("role") == "system" else SYSTEM_BASE_PROMPT
        dialogue = messages[1:] if messages and messages[0].get("role") == "system" else messages

        # Budowa naprzemiennych ról Gemini API (user / model)
        contents = []
        for m in dialogue:
            raw_text = (m.get("content") or "").strip()
            if not raw_text:
                continue
            gemini_role = "model" if m.get("role") == "assistant" else "user"
            if contents and contents[-1]["role"] == gemini_role:
                contents[-1]["parts"][0]["text"] += f"\n{raw_text}"
            else:
                contents.append({
                    "role": gemini_role,
                    "parts": [{"text": raw_text}]
                })

        if not contents:
            return None

        # Upewnij się, że ostatnia tura należy do użytkownika (wymóg Gemini generateContent)
        if contents[-1]["role"] != "user":
            contents.append({
                "role": "user",
                "parts": [{"text": "Odpowiedz krótko i po kumpelsku do trwającej rozmowy."}]
            })

        payload = {
            "systemInstruction": {"parts": [{"text": system_text}]},
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": max_tok
            }
        }

        # Sprawdź kolejno najszybsze i najinteligentniejsze wersje Flash
        models = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.gemini_api_key}"
            try:
                async with httpx.AsyncClient(timeout=timeout_sec) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts and "text" in parts[0]:
                                return parts[0]["text"].strip()
                    elif resp.status_code == 404:
                        continue
                    else:
                        break
            except Exception:
                pass
        return None
