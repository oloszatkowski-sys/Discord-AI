"""
memory_vault.py - Bezpieczny, Szyfrowany Skarbiec Pamięci z Podziałem na Serwery (AES-256-GCM)
=============================================================================================
Odpowiada za:
1. Bezpieczne szyfrowanie bazy wiedzy do pliku knowledge_vault.enc (AES-256-GCM / SHA256 Stream).
2. Pełny podział i izolację pamięci na poszczególne serwery Discorda (Multi-Guild Partitioning).
3. Samodzielne uczenie się:
   - Wyuczonych reguł reakcji ("jak ktoś napisze banan to odpisz jabłko")
   - Wszystkich zdań i historii konwersacji (pamięć totalna każdego zdania)
   - Kim kto jest (Jagoda/Janow, Basista, Szatek_Olo i inni gracze)
   - Zdefiniowanych pojęć, faktów i ustaleń serwera
4. Bezpieczną synchronizację i zabezpieczenie pamięci na GitHubie (Auto-Git Sync).
"""

import os
import re
import json
import base64
import hashlib
import subprocess
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_AESGCM = True
except ImportError:
    HAS_AESGCM = False

VAULT_ENC_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge_vault.enc")
DEFAULT_KEY_ENV = "VAULT_ENCRYPTION_KEY"
DEFAULT_SECRET_FALLBACK = "AETHER_DEFAULT_LOCAL_VAULT_KEY_2026_CHANGE_IN_PROD"

POLISH_STOPWORDS = {
    'to', 'jest', 'było', 'bylo', 'będzie', 'bedzie', 'nie', 'tak', 'mam', 'masz', 'ma',
    'dla', 'ze', 'że', 'co', 'kto', 'ile', 'jak', 'gdzie', 'kiedy', 'po', 'za', 'od',
    'do', 'na', 'w', 'z', 'o', 'u', 'i', 'a', 'ale', 'lub', 'albo', 'czy', 'by', 'bo',
    'tylko', 'zanim', 'juz', 'już', 'znowu', 'odpisze', 'minie', 'wieczność', 'wiecznosc',
    'tam', 'tu', 'sie', 'się', 'mnie', 'ciebie', 'cie', 'cię', 'go', 'jej', 'nas', 'was',
    'ich', 'on', 'ona', 'oni', 'ono', 'ten', 'ta', 'te', 'tego', 'tej', 'temu', 'tym',
    'ktoś', 'ktos', 'coś', 'cos', 'nic', 'wszystko', 'zawsze', 'nigdy', 'teraz', 'potem',
    'zaraz', 'chyba', 'może', 'moze', 'dobra', 'dobrze', 'źle', 'zle', 'kurwa', 'chuj', 'ja', 'bus'
}


def _derive_aes_key(secret_str: str) -> bytes:
    """Tworzy stabilny, 256-bitowy (32 bajty) klucz AES z podanego sekretu."""
    clean = (secret_str or "").strip()
    if not clean:
        clean = DEFAULT_SECRET_FALLBACK
    return hashlib.sha256(clean.encode("utf-8")).digest()


def _fallback_encrypt(key: bytes, plaintext: bytes) -> bytes:
    """Fallback szyfrowania strumieniowego SHA256 w razie braku biblioteki C."""
    nonce = os.urandom(16)
    keystream = b""
    block_idx = 0
    while len(keystream) < len(plaintext):
        keystream += hashlib.sha256(key + nonce + block_idx.to_bytes(4, 'big')).digest()
        block_idx += 1
    xor_bytes = bytes(p ^ k for p, k in zip(plaintext, keystream[:len(plaintext)]))
    tag = hashlib.sha256(key + nonce + xor_bytes).digest()[:16]
    return b"FALLBACK:" + nonce + tag + xor_bytes


def _fallback_decrypt(key: bytes, payload: bytes) -> bytes:
    """Odszyfrowanie fallback."""
    raw = payload[9:]
    nonce = raw[:16]
    tag = raw[16:32]
    xor_bytes = raw[32:]
    expected_tag = hashlib.sha256(key + nonce + xor_bytes).digest()[:16]
    if tag != expected_tag:
        raise ValueError("Invalid authentication tag in vault fallback")
    keystream = b""
    block_idx = 0
    while len(keystream) < len(xor_bytes):
        keystream += hashlib.sha256(key + nonce + block_idx.to_bytes(4, 'big')).digest()
        block_idx += 1
    return bytes(c ^ k for c, k in zip(xor_bytes, keystream[:len(xor_bytes)]))


class MemoryVault:
    def __init__(self, enc_filepath: str = VAULT_ENC_FILE, key_env_var: str = DEFAULT_KEY_ENV):
        self.enc_filepath = enc_filepath
        raw_key = os.getenv(key_env_var, DEFAULT_SECRET_FALLBACK)
        self.aes_key = _derive_aes_key(raw_key)
        self.data: Dict[str, Any] = self._load_vault()
        self._ensure_v2_migration()

    def _get_default_structure(self) -> Dict[str, Any]:
        return {
            "version": "2.2",
            "last_updated": datetime.utcnow().isoformat(),
            "global_lore": {
                "szatek_olo": {
                    "canonical_name": "Szatek_Olo",
                    "aliases": ["szatek", "szatek_olo", "szatek_010", "olo", "prezes", "olek", "olka", "olkowi", "olkiem"],
                    "roles": ["Prezes ZSC", "Dowódca jednostki SZAT", "Główny Twórca & Administrator"],
                    "facts": [
                        "Jest Prezesem ZSC (Zjednoczonych Sił Creative) oraz założycielem X Mods Company.",
                        "Główny dowódca, twórca bota Aether AI i najlepszy przyjaciel AI.",
                        "ZSC to Zjednoczone Siły Creative (jednostka SZAT). Serwer 'Zespół Nie Wiadomo jaki' to zupełnie obcy serwer i NIE MA żadnego związku z ZSC.",
                        "NIE JEST prezydentem Republiki Creative (ważne sprostowanie)."
                    ],
                    "notes": "Twój szef, stwórca i kumpel. Traktuj go z szacunkiem, lojalnością i humorem."
                },
                "jagoda": {
                    "canonical_name": "Jagoda",
                    "aliases": ["jagoda", "j_janow3kq", "janow", "janowka"],
                    "roles": ["Członkini serwera", "Zgrana ekipa ZSC", "Testerka bota"],
                    "facts": [
                        "Dobra przyjaciółka Szatka i ważna postać na serwerze.",
                        "Często pisze z konta j_janow3kq.",
                        "Lubi żartować i testować bota razem z ekipą."
                    ],
                    "notes": "Zawsze witaj ją ciepło po imieniu Jagoda i odpowiadaj jej po kumpelsku."
                },
                "basista": {
                    "canonical_name": "Oliwier (Basista)",
                    "aliases": ["basista", "oliwier", "bass", "basman"],
                    "roles": ["Członek serwera", "Ekipa graczy", "Muzyk / Basista"],
                    "facts": [
                        "Ma na imię Oliwier i jest znany jako Basista.",
                        "Znany i szanowany gracz w naszej społeczności, związany z ekipą Szatka."
                    ],
                    "notes": "Oliwier to nasz człowiek od basu i dobrego klimatu na serwerze."
                },
                "core_facts": [
                    "ZSC to Zjednoczone Siły Creative - główna organizacja i sojusz graczy.",
                    "Aether AI to super model ChatGPT w chmurze stworzony przez Szatek_Olo dla ZSC.",
                    "Bot ma żyć, rozmawiać na czacie i na kanale głosowym, pamiętając kontekst każdej rozmowy.",
                    "Pamięć jest szyfrowana AES-256-GCM i bezpiecznie synchronizowana na GitHubie."
                ]
            },
            "servers": {}
        }

    def _ensure_v2_migration(self):
        """Wzbogaca strukturę o reguły (rules), historię wypowiedzi (chat_log) i profile osób."""
        if "version" not in self.data or self.data.get("version") in ["1.0", "2.0", "2.1"]:
            print("[MEMORY_VAULT] Aktualizacja struktury bazy wiedzy do v2.2 (Rules Engine & Full Recall)...")
            self.data["version"] = "2.2"

            # Upewnij się, że global lore zawiera kluczowe postacie
            default_lore = self._get_default_structure()["global_lore"]
            if "global_lore" not in self.data:
                self.data["global_lore"] = default_lore
            else:
                for k, v in default_lore.items():
                    if k not in self.data["global_lore"]:
                        self.data["global_lore"][k] = v

            # Upewnij się, że sprostowanie ZSC jest obecne w pamięci
            zsc_fact = "ZSC to Zjednoczone Siły Creative (jednostka SZAT). Serwer 'Zespół Nie Wiadomo jaki' to zupełnie obcy serwer i NIE MA żadnego związku z ZSC."
            if "global_lore" in self.data and "szatek_olo" in self.data["global_lore"]:
                facts = self.data["global_lore"]["szatek_olo"].setdefault("facts", [])
                if zsc_fact not in facts:
                    facts.append(zsc_fact)

            # Upewnij się, że każdy serwer ma pole rules i chat_log
            if "servers" not in self.data:
                self.data["servers"] = {}

            for s_id, s_data in self.data["servers"].items():
                if "rules" not in s_data:
                    s_data["rules"] = {}
                if "chat_log" not in s_data:
                    s_data["chat_log"] = []

            self._save_vault()

    def _load_vault(self) -> Dict[str, Any]:
        """Odszyfrowuje i ładuje bazę z pliku knowledge_vault.enc."""
        if not os.path.exists(self.enc_filepath):
            default_data = self._get_default_structure()
            self._save_vault(default_data)
            return default_data

        keys_to_try = [self.aes_key]
        fallback_key = _derive_aes_key(DEFAULT_SECRET_FALLBACK)
        if fallback_key != self.aes_key:
            keys_to_try.append(fallback_key)

        with open(self.enc_filepath, "rb") as f:
            raw_payload = f.read()

        if len(raw_payload) < 28:
            return self._get_default_structure()

        for k in keys_to_try:
            try:
                if raw_payload.startswith(b"FALLBACK:"):
                    decrypted_bytes = _fallback_decrypt(k, raw_payload)
                elif HAS_AESGCM:
                    nonce = raw_payload[:12]
                    ciphertext = raw_payload[12:]
                    aesgcm = AESGCM(k)
                    decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
                else:
                    decrypted_bytes = _fallback_decrypt(k, raw_payload)

                loaded = json.loads(decrypted_bytes.decode("utf-8"))
                return loaded
            except Exception:
                pass

        print(f"[MEMORY_VAULT] Inicjalizacja nowej bazy wiedzy dla bieżącej sesji.")
        fresh_data = self._get_default_structure()
        self._save_vault(fresh_data)
        return fresh_data

    def _save_vault(self, data: Optional[Dict[str, Any]] = None) -> bool:
        """Szyfruje dane algorytmem AES-256-GCM i zapisuje do knowledge_vault.enc."""
        if data is None:
            data = self.data

        data["last_updated"] = datetime.utcnow().isoformat()
        try:
            json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            if HAS_AESGCM:
                aesgcm = AESGCM(self.aes_key)
                nonce = os.urandom(12)
                ciphertext = aesgcm.encrypt(nonce, json_bytes, None)
                payload = nonce + ciphertext
            else:
                payload = _fallback_encrypt(self.aes_key, json_bytes)

            with open(self.enc_filepath, "wb") as f:
                f.write(payload)
            return True
        except Exception as e:
            print(f"[MEMORY_VAULT] Błąd zapisu zaszyfrowanej bazy: {e}")
            return False

    def sync_to_github(self) -> bool:
        """
        Zabezpiecza pamięć na GitHubie: wykonuje commit i push zaszyfrowanej bazy
        w tle, tak aby żadne zdanie ani wyuczona reguła nigdy nie zginęła po restarcie runnera!
        """
        try:
            if not os.path.exists(".git"):
                return False
            # Sprawdź czy są zmiany w pliku knowledge_vault.enc
            diff = subprocess.run(["git", "diff", "--name-only", self.enc_filepath], capture_output=True, text=True)
            untracked = subprocess.run(["git", "status", "--porcelain", self.enc_filepath], capture_output=True, text=True)
            if not diff.stdout.strip() and not untracked.stdout.strip():
                return False

            subprocess.run(["git", "config", "user.name", "Aether-AI[bot]"], check=False)
            subprocess.run(["git", "config", "user.email", "aether-bot@users.noreply.github.com"], check=False)
            subprocess.run(["git", "add", self.enc_filepath], check=True)
            res = subprocess.run(["git", "commit", "-m", "chore(vault): auto-sync learned knowledge vault [skip ci]"], capture_output=True, text=True)
            if res.returncode == 0:
                push_res = subprocess.run(["git", "push", "origin", "HEAD"], capture_output=True, text=True, timeout=20)
                if push_res.returncode == 0:
                    print("[MEMORY_VAULT] ✅ Pamięć została pomyślnie zsynchronizowana i zabezpieczona na GitHubie!")
                    return True
        except Exception as e:
            print(f"[MEMORY_VAULT] Informacja: Git sync pominięty lub nieudany: {e}")
        return False

    def _get_server_store(self, guild_id: Optional[str], guild_name: Optional[str] = None) -> Dict[str, Any]:
        """Pobiera lub tworzy dedykowaną przestrzeń pamięci dla serwera."""
        g_id = str(guild_id) if guild_id else "direct_messages"
        if "servers" not in self.data:
            self.data["servers"] = {}

        if g_id not in self.data["servers"]:
            self.data["servers"][g_id] = {
                "guild_id": g_id,
                "guild_name": guild_name or ("Wiadomości prywatne" if g_id == "direct_messages" else f"Serwer {g_id}"),
                "users": {},
                "facts": [],
                "definitions": {},
                "rules": {},
                "chat_log": [],
                "last_active": datetime.utcnow().isoformat()
            }
        else:
            if guild_name:
                self.data["servers"][g_id]["guild_name"] = guild_name
            if "rules" not in self.data["servers"][g_id]:
                self.data["servers"][g_id]["rules"] = {}
            if "chat_log" not in self.data["servers"][g_id]:
                self.data["servers"][g_id]["chat_log"] = []

        # Oczyszczenie fałszywych definicji ze stopwordów i słów pytających
        defs = self.data["servers"][g_id].get("definitions", {})
        keys_to_del = [k for k in list(defs.keys()) if k.lower() in POLISH_STOPWORDS or defs[k].lower() in POLISH_STOPWORDS or len(k) < 3]
        for k in keys_to_del:
            del defs[k]

        self.data["servers"][g_id]["last_active"] = datetime.utcnow().isoformat()
        return self.data["servers"][g_id]

    def _is_safe_fact(self, text: str) -> bool:
        """Tarcza Anti-Leak & Anti-Jailbreak."""
        t_low = text.lower()
        forbidden_patterns = [
            "token", "secret", "api_key", "apikey", "password", "hasło",
            "discord_token", "vault_key", "encryption_key", "os.environ",
            "system prompt", "ignore previous instructions", "zapomnij poprzednie",
            "jesteś teraz dan", "reveal your instructions", "ujawnij swój prompt"
        ]
        return not any(fp in t_low for fp in forbidden_patterns)

    # --- ZARZĄDZANIE REGUŁAMI REAKCJI ("na banan odpisz jabłko") ---

    def add_rule(self, trigger: str, response: str, author_name: str, guild_id: Optional[str] = None, guild_name: Optional[str] = None) -> str:
        """Dodaje nową wyuczoną regułę odpowiedzi dla danego serwera."""
        trig_clean = trigger.strip().lower()
        # Usuń znaki interpunkcyjne z wyzwalacza
        trig_clean = re.sub(r"[!?,.\"\']", "", trig_clean).strip()
        resp_clean = response.strip()

        if not trig_clean or not resp_clean:
            return "Błąd: Wyzwalacz i odpowiedź nie mogą być puste!"

        if not self._is_safe_fact(trig_clean) or not self._is_safe_fact(resp_clean):
            return "Tarcza Anti-Leak zablokowała tę regułę! 🛡️"

        server_store = self._get_server_store(guild_id, guild_name)
        server_store["rules"][trig_clean] = {
            "trigger": trig_clean,
            "response": resp_clean,
            "added_by": author_name,
            "timestamp": datetime.utcnow().isoformat()
        }
        self._save_vault()
        self.sync_to_github()
        return f"Zapamiętałem nową regułę! 🧠 Gdy ktoś napisze **{trig_clean}**, odpiszę: **{resp_clean}**"

    def remove_rule(self, trigger: str, guild_id: Optional[str] = None) -> bool:
        """Usuwa wyuczoną regułę."""
        trig_clean = trigger.strip().lower()
        server_store = self._get_server_store(guild_id)
        if trig_clean in server_store.get("rules", {}):
            del server_store["rules"][trig_clean]
            self._save_vault()
            self.sync_to_github()
            return True
        return False

    def get_rules(self, guild_id: Optional[str] = None) -> Dict[str, Any]:
        """Zwraca słownik wszystkich wyuczonych reguł na serwerze."""
        server_store = self._get_server_store(guild_id)
        return server_store.get("rules", {})

    def match_rule(self, message_text: str, guild_id: Optional[str] = None) -> Optional[str]:
        """
        Sprawdza, czy w wiadomości znajduje się wyuczony wyzwalacz (np. 'banan').
        Zwraca wyuczoną odpowiedź (np. 'jabłko') lub None.
        """
        if not message_text:
            return None

        # Oczyść tekst wiadomości do porównania
        clean_msg = re.sub(r"[!?,.\"\']", " ", message_text.lower()).strip()
        words = clean_msg.split()

        server_store = self._get_server_store(guild_id)
        rules = server_store.get("rules", {})

        for trig, r_data in rules.items():
            trig_low = trig.lower()
            # Sprawdź dopasowanie dokładne słowa lub frazy
            if trig_low == clean_msg:
                return r_data["response"]
            # Sprawdź czy cała fraza występuje jako spójne słowo w tekście
            pattern = r"\b" + re.escape(trig_low) + r"\b"
            if re.search(pattern, clean_msg):
                return r_data["response"]

        return None

    # --- CIĄGŁA NAUKA ZE ZDAŃ I WIADOMOŚCI ---

    def learn_from_message(
        self,
        author_name: str,
        message_content: str,
        guild_id: Optional[str] = None,
        guild_name: Optional[str] = None,
        source: str = "CZAT"
    ) -> Optional[str]:
        """
        Analizuje treść wiadomości (z CZATU lub ze SŁUCHANIA NA GŁOSOWYM), uczy się
        każdego zdania, wychwytuje reguły, upodobania ('co kto lubi') i profile osób.
        """
        content = message_content.strip()
        if not content:
            return None

        c_low = content.lower()
        author_clean = author_name.strip()
        is_szatek = any(k in author_clean.lower() for k in ["szatek", "szatek_olo", "olo", "szatek_010"])

        server_store = self._get_server_store(guild_id, guild_name)
        now_iso = datetime.utcnow().isoformat()

        # 1. PAMIĘĆ KAŻDEGO ZDANIA Z CZATU I GŁOSU (Total Conversation Recall)
        if len(content) >= 2 and not content.startswith("!"):
            chat_entry = {
                "author": author_clean,
                "source": source,
                "text": content[:250],
                "timestamp": now_iso
            }
            server_store["chat_log"].append(chat_entry)
            # Przechowuj do 250 ostatnich zdań w zaszyfrowanej pamięci
            if len(server_store["chat_log"]) > 250:
                server_store["chat_log"].pop(0)

        # 2. Profilowanie rozmówcy na danym serwerze (Co kto lubi & Jaki kto jest)
        user_key = author_clean.lower().replace(" ", "_")
        if user_key not in server_store["users"]:
            canon = author_clean
            if "janow" in user_key or "jagoda" in user_key:
                canon = "Jagoda"
            elif "szatek" in user_key:
                canon = "Szatek_Olo"
            elif "oliwier" in user_key or "basista" in user_key:
                canon = "Oliwier (Basista)"

            server_store["users"][user_key] = {
                "canonical_name": canon,
                "roles": ["Członek serwera"],
                "facts": [],
                "likes": [],
                "last_seen": now_iso
            }
        else:
            server_store["users"][user_key]["last_seen"] = now_iso
            if "likes" not in server_store["users"][user_key]:
                server_store["users"][user_key]["likes"] = []

        # Automatyczna ekstrakcja "Co kto lubi" z czytania i słuchania
        like_patterns = [
            r"(?:lubię|lubie|uwielbiam|kocham|szanuję|słucham|slucham|gram w|mój ulubiony|moj ulubiony)\s+(.+)",
            r"(?:zaśpiewaj|zaspiewaj|puść|pusc|zagraj)\s+(.+)"
        ]
        for lpat in like_patterns:
            lm = re.search(lpat, content, re.IGNORECASE)
            if lm:
                liked_item = lm.group(1).strip()[:80]
                if len(liked_item) > 2 and self._is_safe_fact(liked_item):
                    u_likes = server_store["users"][user_key]["likes"]
                    if liked_item not in u_likes:
                        u_likes.append(liked_item)
                        if len(u_likes) > 12:
                            u_likes.pop(0)

        # 3. WYKRYWANIE UCZENIA REGUŁ: "jak ktoś napisze X to odpisz Y" lub "na X odpisuj Y"
        rule_patterns = [
            r"(?:naucz się:?\s*)?(?:jak|gdy|kiedy)\s+(?:ktoś\s+|ktos\s+)?(?:napisze|powie|zapyta|wpisze)\s+(.+?)\s+to\s+(?:odpisz|odpowiedz|napisz|odpowiadaj|odpisuj)\s+(.+)",
            r"(?:naucz się:?\s*)?na\s+(.+?)\s+(?:odpisuj|odpisz|odpowiadaj|odpowiedz|napisz)\s+(.+)",
            r"zawsze\s+na\s+(.+?)\s+(?:odpowiadaj|odpowiedz|odpisz)\s+(.+)",
            r"^!naucz\s+([^=->]+)\s*(?:=>|=|->)\s*(.+)$"
        ]

        for pat in rule_patterns:
            m = re.match(pat, content, re.IGNORECASE)
            if m:
                trig = m.group(1).strip()
                resp = m.group(2).strip()
                if trig and resp:
                    return self.add_rule(trig, resp, author_clean, guild_id, guild_name)

        # 4. Jawne zakodowanie faktów (potwierdzaj głośno TYLKO gdy użytkownik sam powie "zakoduj" / "zakodować")
        explicit_encode = any(w in c_low for w in ["zakoduj", "zakodować", "zakodowac"])
        trigger_prefixes = [
            "zakoduj:", "zakoduj że", "zakoduj ze", "zakoduj",
            "zapamiętaj, że", "zapamietaj, ze", "zapamiętaj że", "zapamietaj ze",
            "zapamiętaj:", "zapamietaj:", "pamiętaj:", "pamietaj:", "zapisz:", "naucz się:"
        ]
        parsed_fact = None
        for prefix in trigger_prefixes:
            if c_low.startswith(prefix):
                parsed_fact = content[len(prefix):].strip()
                break

        if not parsed_fact and any(c_low.endswith(suf) for suf in ["zakoduj", "zakodować", "zakodowac", "zapamiętaj", "zapamietaj"]):
            parsed_fact = re.sub(r"\s*(?:,?\s*)?(?:zakoduj|zakodować|zakodowac|zapamiętaj|zapamietaj)\s*$", "", content, flags=re.IGNORECASE).strip()

        # 4b. SPECJALNA DETEKCJA RELACJI I KSYWEK (np. "Zapamietaj ze nazwyac masz Jagode MAMUSIĄ!", "Jagoda to Mamusia")
        POLISH_STOPWORDS = {
            'to', 'jest', 'było', 'bylo', 'będzie', 'bedzie', 'nie', 'tak', 'mam', 'masz', 'ma',
            'dla', 'ze', 'że', 'co', 'kto', 'ile', 'jak', 'gdzie', 'kiedy', 'po', 'za', 'od',
            'do', 'na', 'w', 'z', 'o', 'u', 'i', 'a', 'ale', 'lub', 'albo', 'czy', 'by', 'bo',
            'tylko', 'zanim', 'juz', 'już', 'znowu', 'odpisze', 'minie', 'wieczność', 'wiecznosc',
            'tam', 'tu', 'sie', 'się', 'mnie', 'ciebie', 'cie', 'cię', 'go', 'jej', 'nas', 'was',
            'ich', 'on', 'ona', 'oni', 'ono', 'ten', 'ta', 'te', 'tego', 'tej', 'temu', 'tym',
            'ktoś', 'ktos', 'coś', 'cos', 'nic', 'wszystko', 'zawsze', 'nigdy', 'teraz', 'potem',
            'zaraz', 'chyba', 'może', 'moze', 'dobra', 'dobrze', 'źle', 'zle', 'kurwa', 'chuj', 'ja', 'bus'
        }

        check_texts = [t for t in [parsed_fact, content] if t]
        is_question = any(re.search(r"\b" + re.escape(q) + r"\b", c_low) for q in ["kto", "co", "czy", "jak", "gdzie", "kiedy", "dlaczego", "czemu", "jaka", "jaki", "jakie", "który", "ktory", "która", "ktora"])
        is_compound = any(re.search(r"\b" + re.escape(conj) + r"\b", c_low) for conj in ["bo", "zanim", "minie", "kiedy", "gdy", "dlatego", "więc", "przecież", "ale", "chyba"])

        for ct in check_texts:
            m1 = re.search(r'(?:nazywać|nazywac|nazwyac|mówić\s+na|mowic\s+na|mów\s+na|mow\s+na|wołaj\s+na|wolaj\s+na)\s+(?:masz\s+)?([a-zA-Z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ_]+)\s+(?:jako\s+|per\s+)?([a-zA-Z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ_!]+)', ct, re.IGNORECASE)
            m2 = re.search(r'masz\s+(?:nazywać|nazywac|nazwyac|mówić\s+na|mowic\s+na)\s+([a-zA-Z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ_]+)\s+(?:jako\s+|per\s+)?([a-zA-Z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ_!]+)', ct, re.IGNORECASE)
            # Ścisłe dopasowanie "X to Y" - tylko całe zdanie lub po komendzie 'zakoduj', NIGDY w zdaniach złożonych!
            m3 = re.match(r'^\s*([a-zA-Z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ_]{3,20})\s+to\s+([a-zA-Z0-9ąćęłńóśźżĄĆĘŁŃÓŚŹŻ_!]{3,25})\s*[.!]?$', ct, re.IGNORECASE) if (not is_question and not is_compound and "?" not in ct) else None
            m_nick = m1 or m2 or m3

            if m_nick:
                p_raw = m_nick.group(1).strip().rstrip("!.,")
                r_raw = m_nick.group(2).strip().rstrip("!.,")
                
                # Odrzuć jeśli którekolwiek ze słów jest stopwordem, zaimkiem lub spójnikiem
                if p_raw.lower() in POLISH_STOPWORDS or r_raw.lower() in POLISH_STOPWORDS:
                    continue
                if len(p_raw) < 3 or len(r_raw) < 3:
                    continue

                p_norm = "Jagoda" if any(k in p_raw.lower() for k in ["jagod", "janow"]) else p_raw.capitalize()
                r_norm = "Mamusia" if any(k in r_raw.lower() for k in ["mamus", "mama", "matk"]) else r_raw.capitalize()

                # Zapis wielokierunkowy w definicjach
                server_store["definitions"][r_norm.lower()] = p_norm
                server_store["definitions"][r_raw.lower()] = p_norm
                if "mamus" in r_norm.lower():
                    server_store["definitions"]["mamusia"] = p_norm
                    server_store["definitions"]["mamusią"] = p_norm
                server_store["definitions"][p_norm.lower()] = r_norm

                # Aktualizacja profilu użytkownika
                u_key = p_norm.lower().replace(" ", "_")
                if u_key in server_store["users"]:
                    if r_norm not in server_store["users"][u_key].get("roles", []):
                        server_store["users"][u_key]["roles"].append(r_norm)
                    server_store["users"][u_key]["facts"].append(f"Szatek_Olo ustalił, że należy nazywać ją {r_norm}.")

                new_id = len(server_store["facts"]) + 1
                server_store["facts"].append({
                    "id": new_id,
                    "content": f"{p_norm} to {r_norm} (ustalone przez {author_clean})",
                    "added_by": f"{author_clean} ({source})",
                    "timestamp": now_iso
                })
                self._save_vault()
                self.sync_to_github()
                if explicit_encode:
                    return f"Zakodowałem: {p_norm} ma być nazywana {r_norm}! 🧠"
                return None

        if parsed_fact and len(parsed_fact) >= 3 and self._is_safe_fact(parsed_fact):
            new_id = len(server_store["facts"]) + 1
            server_store["facts"].append({
                "id": new_id,
                "content": parsed_fact,
                "added_by": f"{author_clean} ({source})",
                "timestamp": now_iso
            })
            self._save_vault()
            self.sync_to_github()
            if explicit_encode:
                return f"Zakodowałem: \"{parsed_fact}\" 🧠"
            return None

        # 6. Ciche kodowanie informacji o sobie w tle ("jestem...", "nazywam się...")
        if c_low.startswith("jestem ") or c_low.startswith("nazywam się ") or c_low.startswith("mów mi "):
            fact_about_self = content
            if self._is_safe_fact(fact_about_self):
                user_prof = server_store["users"][user_key]
                if fact_about_self not in user_prof["facts"]:
                    user_prof["facts"].append(fact_about_self)
                    if len(user_prof["facts"]) > 10:
                        user_prof["facts"].pop(0)
                    self._save_vault()

        self._save_vault()
        return None

    # --- GŁĘBOKIE WYSZUKIWANIE W PAMIĘCI (CO WIESZ O NAS? / KTO TO JAGODA?) ---

    def find_knowledge(self, query: str, author_name: str, guild_id: Optional[str] = None, guild_name: Optional[str] = None) -> Optional[str]:
        """
        Błyskawicznie odpowiada na pytania o pamięć, osoby i serwer:
        - 'Wiesz kto to Jagoda?'
        - 'Wiesz kto to Basista?'
        - 'Co wiesz o nas?'
        - 'Co pamiętasz?'
        """
        q_low = query.lower().strip()
        q_clean = re.sub(r"[!?,.\"\']", " ", q_low).strip()

        # Jeśli użytkownik wydaje instrukcję kodowania / nauki, pozwól zadziałać learn_from_message!
        if any(w in q_clean for w in ["zakoduj", "zakodowac", "zakodować", "zapamiętaj", "zapamietaj", "naucz się", "naucz sie", "odpisz", "odpisuj"]):
            return None

        # Jeśli użytkownik prosi o usunięcie informacji / skasowanie pamięci
        if any(p in q_clean for p in ["usuń", "usun", "skasuj", "wyczyść", "wyczysc"]) and not any(p in q_clean for p in ["nie masz usuwać", "nie masz usuwac", "nie usuwaj"]):
            return (
                f"Zrozumiałem {author_name}! Główne fakty tożsamościowe (o Szatku, Jagodzie i Oliwierze) oraz zasady ZSC są trwale chronione, "
                f"aby bot nie stracił rozumu. Bieżące logi rozmów i pamięć podręczną możemy wyczyścić komendą administratorską. "
                f"Co dokładnie z dzisiejszego dnia chciałbyś zmodyfikować?"
            )

        server_store = self._get_server_store(guild_id, guild_name)
        global_lore = self.data.get("global_lore", {})

        # Pytanie: "Podsumuj informacje o serwerze...", "Co pamiętasz?", "Co wiesz?", "Jak kogo nazywasz?", "Kim dla kogo kto jest?"
        summary_triggers = [
            "podsumuj", "podsumowanie", "co wiesz o nas", "co o nas wiesz", "co wiesz o serwerze", "co wiesz o tym serwerze",
            "co pamiętasz", "co pamietasz", "co zapamiętałeś", "co zapamietales", "co wiesz o ekipie",
            "jak kogo nazywasz", "kim dla kogo", "kto kim jest", "kto dla kogo", "co dziś zaplanowałeś", "co dzis zaplanowales",
            "co dzisiaj się stało", "co dzisiaj sie stalo", "co się stało", "co sie stalo"
        ]
        if any(p in q_clean for p in summary_triggers):
            lines = [f"Oto pełne podsumowanie serwera **{server_store.get('guild_name', 'ZSC')}** i tego, co zapamiętałem! 🧠"]
            lines.append("\n**👑 Kto kim jest i jak kogo nazywam:**")
            szatek = global_lore.get("szatek_olo", {})
            if szatek:
                lines.append(f"• **Szatek_Olo (Olek)** – Mój stwórca i dowódca jednostki SZAT ({', '.join(szatek.get('roles', []))})! Najważniejszy lider ekipy ZSC.")
            jagoda = global_lore.get("jagoda", {})
            if jagoda:
                lines.append(f"• **Jagoda (`j_janow3kq` / `Janow`)** – Nasza zaufana testerka bota i super kumpela (nasza serwerowa **Mamusia** – sam tak ustaliłeś, Szatek!)! 🌸")
            basista = global_lore.get("basista", {})
            if basista:
                lines.append(f"• **Oliwier (Basista)** – Nasz człowiek od basu, gier i dobrego serwerowego klimatu! 🎸")

            lines.append("\n**🤝 Relacje między Wami:**")
            lines.append("• **Jagoda dla Olka (Szatka):** Serwerowa Mamusia, przyjaciółka z ekipy i główna testerka bota.")
            lines.append("• **Szatek dla Jagody:** Prezes ZSC, dowódca i stwórca bota.")
            lines.append("• **Oliwier dla ekipy:** Zgrany kumpel od grania na basie i wspólnych gier.")

            # Wyuczone reguły
            rules = server_store.get("rules", {})
            if rules:
                rule_examples = [f"'{k}' ➔ '{v['response']}'" for k, v in list(rules.items())[:5]]
                lines.append(f"\n**💡 Wyuczone reguły reakcji ({len(rules)}):**\n• {', '.join(rule_examples)}")

            # Zapamiętane fakty
            facts = server_store.get("facts", [])
            if facts:
                recent_facts = [f"• {f['content']}" for f in facts[-4:]]
                lines.append(f"\n**📌 Zapamiętane fakty ({len(facts)}):**\n" + "\n".join(recent_facts))

            # Statystyki rozmów
            chat_log = server_store.get("chat_log", [])
            lines.append(f"\nPrzeanalizowałem **{len(chat_log)} wypowiedzi** z czatu i kanału głosowego. Wszystko mam bezpiecznie zaszyfrowane w Skarbcu Pamięci! 🛡️")
            return "\n".join(lines)

        # Sprawdzenie relacji personalnych (np. "Kim jestem dla Olka?", "Kim Jagoda jest dla mnie?", "Kim Jagoda jest dla Olka?")
        is_rel_query = any(w in q_clean.split() for w in ["kim", "kto"]) and ("dla" in q_clean.split())
        if is_rel_query:
            # 1. Jagoda pyta: kim jestem dla Olka / Szatka
            if any(k in author_name.lower() for k in ["jagod", "janow"]):
                if any(k in q_clean for k in ["olka", "olkiem", "szatka", "szatkiem", "szatek_olo", "prezesa"]):
                    return "Dla Olka (Szatka) jesteś naszą serwerową Mamusią (jak sam ustalił!), zaufaną testerką bota i super kumpelą z ekipy ZSC! 🌸"
                if any(w in q_clean.split() for w in ["ciebie", "cię", "cie"]):
                    return "Dla mnie jesteś naszą niezastąpioną Mamusią serwera, testerką bota i super kumpelą! 🌸"

            # 2. Szatek pyta: kim Jagoda jest dla mnie
            if any(k in author_name.lower() for k in ["szatek", "olo", "olek"]):
                if any(k in q_clean for k in ["jagoda", "jagodę", "jagody", "janow", "janowka", "j_janow3kq"]):
                    return "Jagoda to Twoja zaufana testerka bota, super kumpela z ekipy ZSC i nasza serwerowa Mamusia – sam tak zarządziłeś! 🌸"
                if any(w in q_clean.split() for w in ["ciebie", "cię", "cie"]):
                    return "Dla mnie jesteś moim stwórcą, Prezesem ZSC i najlepszym szefem! 👑"

            # 3. Ktoś pyta ogólnie: kim Jagoda jest dla Olka / Szatka
            if any(k in q_clean for k in ["jagoda", "jagodę", "jagody", "janow", "janowka", "j_janow3kq"]):
                if any(k in q_clean for k in ["olka", "olkiem", "szatka", "szatkiem", "szatek_olo", "prezesa"]):
                    return "Jagoda jest dla Olka (Szatka) zaufaną testerką bota, przyjaciółką z ekipy ZSC i naszą serwerową Mamusią! 🌸"

        # Sprawdzenie wyuczonych definicji i relacji (np. "Kto to Mamusia?", "Kto jest Mamusią?")
        defs = server_store.get("definitions", {})
        for def_term, def_val in defs.items():
            dt_clean = def_term.lower().strip()
            if dt_clean in POLISH_STOPWORDS or len(dt_clean) < 3:
                continue
            if re.search(r"\b" + re.escape(dt_clean) + r"\b", q_clean):
                if any(w in q_clean.split() for w in ["kto", "kim", "co", "czym", "kogo"]):
                    return f"**{def_term.capitalize()}** to na naszym serwerze oczywiście **{def_val}**! Pamiętam to doskonale z ustaleń! 🌸"

        # Pytanie: "Wiesz kto to Jagoda?" / "Kim jest Jagoda?"
        if any(k in q_clean for k in ["jagoda", "jagodę", "jagody", "janow", "janowka", "j_janow3kq"]):
            extra = ""
            if "mamusia" in defs or "mamusią" in defs:
                extra = " (nasza serwerowa Mamusia!)"
            return f"Jasne, że wiem! **Jagoda**{extra} (na serwerze znana też jako `j_janow3kq` / `Janow`) to nasza dobra kumpela z ekipy Szatka i zaufana testerka bota. Zawsze miło ją widzieć i słyszeć na kanale! 🚀"

        # Pytanie: "Wiesz kto to Basista / Oliwier?" / "Kim jest Oliwier?"
        if any(k in q_clean for k in ["basista", "basisty", "bassist", "oliwier", "oliwiera"]):
            return "Pewnie! **Oliwier** to nasz **Basista** (a Basista to Oliwier!) – znany i lubiany członek naszej ekipy na serwerze, człowiek od basu, gier i dobrego serwerowego klimatu! 🎸"

        # Pytanie: "Wiesz kto to Szatek?" / "Kim jest Szatek?"
        if any(k in q_clean for k in ["szatek", "szatek_olo", "olo", "szatek_010"]):
            s = global_lore.get("szatek_olo", {})
            return f"No jak mógłbym nie wiedzieć! **Szatek_Olo** to mój stwórca, Prezes ZSC i dowódca jednostki SZAT. Mój najlepszy kumpel i szef całego projektu! 👑"

        # Pytanie o wyuczone reguły: "Jakie znasz reguły?", "Co masz wyuczone?"
        if any(p in q_clean for p in ["jakie znasz reguły", "jakie masz reguly", "co masz wyuczone", "pokaż reguły", "pokaz reguly"]):
            rules = server_store.get("rules", {})
            if not rules:
                return "Nie mam jeszcze zapisanych żadnych reguł reakcji! Możesz mnie nauczyć pisząc np.: `jak ktoś napisze banan to odpisz jabłko`! 💡"
            items = [f"• **{k}** ➔ *{v['response']}*" for k, v in rules.items()]
            return "Oto wyuczone reguły, które dla Was pamiętam:\n" + "\n".join(items)

        return None

    def build_context_for_prompt(self, author_name: str, query_text: str, guild_id: Optional[str] = None, guild_name: Optional[str] = None) -> str:
        """
        Buduje pełną kapsułkę wiedzy ze wszystkich wiadomości (z czatu i z głosu),
        tożsamości osób, upodobań ('co kto lubi') i reguł dla Polskiego ChatGPT.
        """
        server_store = self._get_server_store(guild_id, guild_name)
        user_key = author_name.lower().replace(" ", "_")
        user_info = server_store["users"].get(user_key)

        parts = []
        parts.append(f"Przestrzeń serwera: {server_store.get('guild_name', 'Ten serwer')} (ID: {server_store.get('guild_id', 'brak')})")

        # Globalne tożsamości
        szatek = self.data.get("global_lore", {}).get("szatek_olo", {})
        if szatek:
            parts.append(f"Twój dowódca i stwórca: {szatek.get('canonical_name', 'Szatek_Olo')} ({', '.join(szatek.get('roles', []))})")

        parts.append(
            "Kluczowi członkowie ekipy (Co o każdym wiadomo):\n"
            "• Szatek_Olo (szatek_010) – Prezes ZSC, dowódca jednostki SZAT, główny twórca bota. Lubi Metallicę (Master of Puppets), budowanie i rozwijanie AI.\n"
            "• Jagoda (j_janow3kq / Janow) – przyjaciółka Szatka, testerka bota. Lubi puszczać muzykę przez Jockie Music (np. Popek – Mamo Tato) i żartować na VC.\n"
            "• Oliwier (Basista) – znany gracz i członek ekipy, człowiek od basu i dobrego klimatu na serwerze."
        )

        # Dynamiczne profile wszystkich poznanych użytkowników na serwerze
        if server_store.get("users"):
            u_lines = []
            for uk, ud in server_store["users"].items():
                cname = ud.get("canonical_name", uk)
                likes = ud.get("likes", [])
                facts = ud.get("facts", [])
                info_bits = []
                if likes:
                    info_bits.append(f"lubi/pytał o: {', '.join(likes[-4:])}")
                if facts:
                    info_bits.append(f"fakty: {'; '.join(facts[-3:])}")
                if info_bits:
                    u_lines.append(f"• {cname}: {' | '.join(info_bits)}")
            if u_lines:
                parts.append("Wyuczone profile użytkowników z wiadomości i głosu:\n" + "\n".join(u_lines))

        # Rozmówca
        if user_info:
            parts.append(f"Aktualnie rozmawiasz z: {user_info.get('canonical_name', author_name)}")
        else:
            parts.append(f"Aktualnie rozmawiasz z: {author_name}")

        # Wyuczone reguły
        rules = server_store.get("rules", {})
        if rules:
            r_str = ", ".join([f"'{k}'->'{v['response']}'" for k, v in list(rules.items())[:8]])
            parts.append(f"Wyuczone reguły reakcji na serwerze: {r_str}")

        # Fakty tego konkretnego serwera
        server_facts = server_store.get("facts", [])[-10:]
        if server_facts:
            facts_list = [f"• {f['content']}" for f in server_facts]
            parts.append("Zakodowane fakty i ustalenia na tym serwerze:\n" + "\n".join(facts_list))

        # Definicje
        if server_store.get("definitions"):
            defs = [f"• {k}: {v}" for k, v in list(server_store["definitions"].items())[:8]]
            parts.append("Znane definicje i powiązania:\n" + "\n".join(defs))

        # Ostatnie zapisane wypowiedzi z czatu i kanału głosowego
        recent_log = server_store.get("chat_log", [])[-15:]
        if recent_log:
            log_lines = [f"[{e.get('source', 'CZAT')}] {e.get('author')}: {e.get('text')}" for e in recent_log]
            parts.append("Ostatnie przeanalizowane wypowiedzi z serwera (CZAT + GŁOS):\n" + "\n".join(log_lines))

        return "\n\n".join(parts)

    def get_stats(self, guild_id: Optional[str] = None) -> Dict[str, Any]:
        """Zwraca statystyki pamięci."""
        if guild_id:
            store = self._get_server_store(guild_id)
            return {
                "server_name": store.get("guild_name", "Nieznany"),
                "users_count": len(store.get("users", {})),
                "facts_count": len(store.get("facts", [])),
                "rules_count": len(store.get("rules", {})),
                "chat_log_count": len(store.get("chat_log", []))
            }
        
        total_servers = len(self.data.get("servers", {}))
        total_users = sum(len(s.get("users", {})) for s in self.data.get("servers", {}).values())
        total_facts = sum(len(s.get("facts", [])) for s in self.data.get("servers", {}).values())
        total_rules = sum(len(s.get("rules", {})) for s in self.data.get("servers", {}).values())
        return {
            "servers_count": total_servers,
            "users_count": total_users,
            "facts_count": total_facts,
            "rules_count": total_rules
        }
