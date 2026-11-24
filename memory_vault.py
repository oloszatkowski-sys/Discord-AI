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
                    "aliases": ["szatek", "szatek_olo", "szatek_010", "olo", "prezes"],
                    "roles": ["Prezes ZSC", "Dowódca jednostki SZAT", "Główny Twórca & Administrator"],
                    "facts": [
                        "Jest Prezesem ZSC (Zjednoczonych Sił Creative) oraz założycielem X Mods Company.",
                        "Główny dowódca, twórca bota Aether AI i najlepszy przyjaciel AI.",
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

    def learn_from_message(self, author_name: str, message_content: str, guild_id: Optional[str] = None, guild_name: Optional[str] = None) -> Optional[str]:
        """
        Analizuje treść wiadomości, uczy się każdego zdania, wychwytuje reguły
        (np. 'jak ktoś napisze banan to odpisz jabłko') i profile osób.
        """
        content = message_content.strip()
        if not content:
            return None

        c_low = content.lower()
        author_clean = author_name.strip()
        is_szatek = any(k in author_clean.lower() for k in ["szatek", "szatek_olo", "olo", "szatek_010"])

        server_store = self._get_server_store(guild_id, guild_name)
        now_iso = datetime.utcnow().isoformat()

        # 1. PAMIĘĆ KAŻDEGO ZDANIA (Total Conversation Recall)
        if len(content) >= 2 and not content.startswith("!"):
            chat_entry = {
                "author": author_clean,
                "text": content[:250],
                "timestamp": now_iso
            }
            server_store["chat_log"].append(chat_entry)
            # Przechowuj do 200 ostatnich zdań w zaszyfrowanej pamięci
            if len(server_store["chat_log"]) > 200:
                server_store["chat_log"].pop(0)

        # 2. Profilowanie rozmówcy na danym serwerze
        user_key = author_clean.lower().replace(" ", "_")
        if user_key not in server_store["users"]:
            # Wykryj powiązania (np. j_janow3kq -> Jagoda)
            canon = author_clean
            if "janow" in user_key or "jagoda" in user_key:
                canon = "Jagoda"
            elif "szatek" in user_key:
                canon = "Szatek_Olo"

            server_store["users"][user_key] = {
                "canonical_name": canon,
                "roles": ["Członek serwera"],
                "facts": [],
                "last_seen": now_iso
            }
        else:
            server_store["users"][user_key]["last_seen"] = now_iso

        # 3. WYKRYWANIE UCZENIA REGUŁ: "jak ktoś napisze X to odpisz Y" lub "na X odpisuj Y"
        rule_patterns = [
            # "jak ktoś napisze banan to odpisz jabłko" / "jak ktoś powie X to napisz Y"
            r"(?:naucz się:?\s*)?(?:jak|gdy|kiedy)\s+(?:ktoś\s+|ktos\s+)?(?:napisze|powie|zapyta|wpisze)\s+(.+?)\s+to\s+(?:odpisz|odpowiedz|napisz|odpowiadaj|odpisuj)\s+(.+)",
            # "na banan odpisuj jabłko" / "na banan napisz jabłko"
            r"(?:naucz się:?\s*)?na\s+(.+?)\s+(?:odpisuj|odpisz|odpowiadaj|odpowiedz|napisz)\s+(.+)",
            # "zawsze na banan odpowiadaj jabłko"
            r"zawsze\s+na\s+(.+?)\s+(?:odpowiadaj|odpowiedz|odpisz)\s+(.+)",
            # "!naucz banan => jabłko"
            r"^!naucz\s+([^=->]+)\s*(?:=>|=|->)\s*(.+)$"
        ]

        for pat in rule_patterns:
            m = re.match(pat, content, re.IGNORECASE)
            if m:
                trig = m.group(1).strip()
                resp = m.group(2).strip()
                if trig and resp:
                    return self.add_rule(trig, resp, author_clean, guild_id, guild_name)

        # 4. Jawne zapamiętywanie faktów ("zapamiętaj, że...", "pamiętaj: ...", "... zakoduj")
        trigger_prefixes = [
            "zapamiętaj, że", "zapamietaj, ze", "zapamiętaj że", "zapamietaj ze",
            "zapamiętaj:", "zapamietaj:", "pamiętaj:", "pamietaj:", "zapisz:", "naucz się:",
            "zakoduj:", "zakoduj że", "zakoduj ze", "zakoduj"
        ]
        for prefix in trigger_prefixes:
            if c_low.startswith(prefix):
                fact_text = content[len(prefix):].strip()
                if not fact_text or len(fact_text) < 3:
                    return None

                if not self._is_safe_fact(fact_text):
                    return "Zablokowano: Próba zapamiętania wrażliwych danych (Tarcza Anti-Leak) 🛡️"

                new_id = len(server_store["facts"]) + 1
                server_store["facts"].append({
                    "id": new_id,
                    "content": fact_text,
                    "added_by": author_clean,
                    "timestamp": now_iso
                })
                self._save_vault()
                self.sync_to_github()
                return f"Zakodowałem i zapamiętałem na stałe: \"{fact_text}\" 🧠"

        if any(c_low.endswith(suf) for suf in ["zakoduj", "zakodować", "zakodowac", "zapamiętaj", "zapamietaj"]):
            fact_text = re.sub(r"\s*(?:,?\s*)?(?:zakoduj|zakodować|zakodowac|zapamiętaj|zapamietaj)\s*$", "", content, flags=re.IGNORECASE).strip()
            if fact_text and len(fact_text) >= 3 and self._is_safe_fact(fact_text):
                new_id = len(server_store["facts"]) + 1
                server_store["facts"].append({
                    "id": new_id,
                    "content": fact_text,
                    "added_by": author_clean,
                    "timestamp": now_iso
                })
                self._save_vault()
                self.sync_to_github()
                return f"Zakodowałem w pamięci serwera: \"{fact_text}\" 🧠"

        # 5. Definicje ("X to jest Y", "X to Y", "X oznacza Y")
        if " to jest " in c_low or " oznacza " in c_low:
            split_word = " to jest " if " to jest " in c_low else " oznacza "
            parts = content.split(split_word, 1)
            if len(parts) == 2 and 2 < len(parts[0].strip()) < 35 and 3 < len(parts[1].strip()) < 200:
                term = parts[0].strip()
                definition = parts[1].strip()
                if self._is_safe_fact(term) and self._is_safe_fact(definition):
                    server_store["definitions"][term] = definition
                    self._save_vault()
                    self.sync_to_github()
                    return f"Nauczyłem się definicji pojęcia \"{term}\": {definition} 📖"

        # 6. Informacje o sobie ("jestem...", "nazywam się...")
        if c_low.startswith("jestem ") or c_low.startswith("nazywam się ") or c_low.startswith("mów mi "):
            fact_about_self = content
            if self._is_safe_fact(fact_about_self):
                user_prof = server_store["users"][user_key]
                if fact_about_self not in user_prof["facts"]:
                    user_prof["facts"].append(fact_about_self)
                    if len(user_prof["facts"]) > 10:
                        user_prof["facts"].pop(0)
                    self._save_vault()
                    self.sync_to_github()
                    return f"Zapisałem fakt o Tobie ({author_clean}): {fact_about_self} 💡"

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

        server_store = self._get_server_store(guild_id, guild_name)
        global_lore = self.data.get("global_lore", {})

        # Pytanie: "Co wiesz o nas?" / "Co o nas wiesz?" / "Co pamiętasz?"
        if any(p in q_clean for p in ["co wiesz o nas", "co o nas wiesz", "co wiesz o serwerze", "co pamiętasz", "co pamietasz", "co wiesz o ekipie"]):
            lines = [f"Wiem o Was całkiem sporo! 🧠 Jesteśmy na serwerze **{server_store.get('guild_name', 'ZSC')}**."]
            szatek = global_lore.get("szatek_olo", {})
            if szatek:
                lines.append(f"• **{szatek.get('canonical_name')}** – Mój stwórca i dowódca ({', '.join(szatek.get('roles', []))}).")
            jagoda = global_lore.get("jagoda", {})
            if jagoda:
                lines.append(f"• **{jagoda.get('canonical_name')}** – {jagoda.get('facts', ['Nasza kumpela'])[0]}")
            basista = global_lore.get("basista", {})
            if basista:
                lines.append(f"• **Oliwier (Basista)** – {basista.get('facts', ['Nasz gracz'])[0]}")

            # Wyuczone reguły
            rules = server_store.get("rules", {})
            if rules:
                rule_examples = [f"'{k}' ➔ '{v['response']}'" for k, v in list(rules.items())[:3]]
                lines.append(f"• Pamiętam też Wasze wyuczone reguły, np: {', '.join(rule_examples)}.")

            # Zapamiętane fakty
            facts = server_store.get("facts", [])
            if facts:
                lines.append(f"• Mam zapisane {len(facts)} ważnych faktów i ustaleń.")

            lines.append("Wszystko mam bezpiecznie zaszyfrowane i zabezpieczone na GitHubie! 🛡️")
            return "\n".join(lines)

        # Pytanie: "Wiesz kto to Jagoda?" / "Kim jest Jagoda?"
        if any(k in q_clean for k in ["jagoda", "jagodę", "jagody", "janow", "janowka", "j_janow3kq"]):
            return "Jasne, że wiem! **Jagoda** (na serwerze znana też jako `j_janow3kq` / `Janow`) to nasza dobra kumpela z ekipy Szatka i zaufana testerka bota. Zawsze miło ją widzieć i słyszeć na kanale! 🚀"

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
        Buduje kompleksową kapsułkę wiedzy dla modelu AI, łącząc fakty,
        tożsamości osób, historię zdań i reguły.
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

        parts.append("Kluczowi przyjaciele serwera:\n• Jagoda (j_janow3kq) – przyjaciółka Szatka, testerka bota.\n• Basista – członek ekipy, gracz i basista.")

        # Rozmówca
        if user_info:
            parts.append(f"Rozmawiasz z użytkownikiem: {user_info.get('canonical_name', author_name)}")
            if user_info.get("facts"):
                parts.append(f"- Zapamiętane fakty o rozmówcy: {'; '.join(user_info['facts'][:5])}")
        else:
            parts.append(f"Rozmawiasz z użytkownikiem: {author_name}")

        # Wyuczone reguły
        rules = server_store.get("rules", {})
        if rules:
            r_str = ", ".join([f"'{k}'->'{v['response']}'" for k, v in list(rules.items())[:6]])
            parts.append(f"Wyuczone reguły na serwerze: {r_str}")

        # Fakty tego konkretnego serwera
        server_facts = server_store.get("facts", [])[-6:]
        if server_facts:
            facts_list = [f"• {f['content']}" for f in server_facts]
            parts.append("Zapamiętane fakty i ustalenia na tym serwerze:\n" + "\n".join(facts_list))

        # Definicje
        if server_store.get("definitions"):
            defs = [f"• {k}: {v}" for k, v in list(server_store["definitions"].items())[:6]]
            parts.append("Znane definicje na tym serwerze:\n" + "\n".join(defs))

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
