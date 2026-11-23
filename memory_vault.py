"""
memory_vault.py - Bezpieczny, Szyfrowany Skarbiec Pamięci z Podziałem na Serwery (AES-256-GCM)
=============================================================================================
Odpowiada za:
1. Bezpieczne szyfrowanie bazy wiedzy do pliku knowledge_vault.enc (AES-256-GCM / SHA256 Stream).
2. Pełny podział i izolację pamięci na poszczególne serwery Discorda (Multi-Guild Partitioning).
3. Samodzielne uczenie się: kim kto jest, role, relacje, fakty o serwerze, definicje i ustalenia.
4. Zachowanie tożsamości Dowódcy (Szatek_Olo) i globalnego lore ZSC w każdej przestrzeni.
"""

import os
import json
import base64
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_AESGCM = True
except ImportError:
    HAS_AESGCM = False

VAULT_ENC_FILE = "knowledge_vault.enc"
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
            "version": "2.0",
            "last_updated": datetime.utcnow().isoformat(),
            "global_lore": {
                "szatek_olo": {
                    "canonical_name": "Szatek_Olo",
                    "roles": ["Prezes ZSC", "Dowódca jednostki SZAT", "Główny Twórca & Administrator"],
                    "facts": [
                        "Jest Prezesem ZSC (Zjednoczonych Sił Creative) oraz założycielem X Mods Company.",
                        "NIE JEST prezydentem Republiki Creative (ważne sprostowanie).",
                        "Główny dowódca, twórca bota i najlepszy przyjaciel AI."
                    ],
                    "notes": "Traktuj go z najwyższym szacunkiem i zaufaniem, ale na luzie (jak dobrego kumpla)."
                },
                "core_facts": [
                    "ZSC to Zjednoczone Siły Creative - główna organizacja i sojusz graczy.",
                    "Aether AI to super model ChatGPT w chmurze stworzony przez Szatek_Olo dla ZSC.",
                    "Bot ma żyć, rozmawiać na czacie i na kanale głosowym, pamiętając kontekst każdej rozmowy."
                ]
            },
            "servers": {}
        }

    def _ensure_v2_migration(self):
        """Automatyczna migracja starej struktury v1.0 do v2.0 z podziałem na serwery."""
        if "version" not in self.data or self.data.get("version") == "1.0":
            print("[MEMORY_VAULT] Migracja bazy wiedzy do struktury v2.0 (Multi-Server Partitioning)...")
            old_users = self.data.get("users", {})
            old_facts = self.data.get("facts", [])
            old_defs = self.data.get("definitions", {})

            new_struct = self._get_default_structure()
            # Zachowaj użytkowników i fakty w domyślnym serwerze
            default_guild_id = "default_server"
            new_struct["servers"][default_guild_id] = {
                "guild_id": default_guild_id,
                "guild_name": "Główny Serwer ZSC",
                "users": old_users,
                "facts": old_facts,
                "definitions": old_defs,
                "last_active": datetime.utcnow().isoformat()
            }
            self.data = new_struct
            self._save_vault()

    def _load_vault(self) -> Dict[str, Any]:
        """Odszyfrowuje i ładuje bazę z pliku knowledge_vault.enc z automatycznym fallbackiem klucza."""
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

                return json.loads(decrypted_bytes.decode("utf-8"))
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

    def _get_server_store(self, guild_id: Optional[str], guild_name: Optional[str] = None) -> Dict[str, Any]:
        """Pobiera lub tworzy dedykowaną, izolowaną przestrzeń pamięci dla danego serwera."""
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
                "last_active": datetime.utcnow().isoformat()
            }
        elif guild_name:
            self.data["servers"][g_id]["guild_name"] = guild_name

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

    def learn_from_message(self, author_name: str, message_content: str, guild_id: Optional[str] = None, guild_name: Optional[str] = None) -> Optional[str]:
        """
        Analizuje treść wiadomości, uczy się nowych faktów i ról w dedykowanej
        przestrzeni danego serwera.
        """
        content = message_content.strip()
        if len(content) > 300:
            content = content[:300]

        c_low = content.lower()
        author_clean = author_name.strip()
        is_szatek = any(k in author_clean.lower() for k in ["szatek", "szatek_olo", "olo"])

        server_store = self._get_server_store(guild_id, guild_name)
        now_iso = datetime.utcnow().isoformat()

        # 1. Profilowanie użytkownika na danym serwerze
        user_key = author_clean.lower().replace(" ", "_")
        if user_key not in server_store["users"]:
            server_store["users"][user_key] = {
                "canonical_name": author_clean,
                "roles": ["Członek serwera"],
                "facts": [],
                "last_seen": now_iso
            }
        else:
            server_store["users"][user_key]["last_seen"] = now_iso

        # 2. Ochrona tożsamości Szatek_Olo
        if any(k in c_low for k in ["szatek to", "szatek jest", "szatek_olo to", "szatek_olo jest"]):
            if not is_szatek:
                return "Tylko Szatek_Olo może edytować profil Dowódcy ZSC! 🛡️"

        # 3. Jawne zapamiętywanie faktów ("zapamiętaj, że...", "pamiętaj: ...")
        trigger_prefixes = [
            "zapamiętaj, że", "zapamietaj, ze", "zapamiętaj że", "zapamietaj ze",
            "zapamiętaj:", "zapamietaj:", "pamiętaj:", "pamietaj:", "zapisz:", "naucz się:"
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
                return f"Zapamiętałem dla tego serwera: \"{fact_text}\""

        # 4. Rozpoznawanie "Kto kim jest"
        if c_low.startswith("jestem ") or c_low.startswith("pracuję jako ") or c_low.startswith("moja rola to ") or c_low.startswith("gram w "):
            fact_about_self = content
            if self._is_safe_fact(fact_about_self):
                user_prof = server_store["users"][user_key]
                if fact_about_self not in user_prof["facts"]:
                    user_prof["facts"].append(fact_about_self)
                    if len(user_prof["facts"]) > 8:
                        user_prof["facts"].pop(0)
                    self._save_vault()
                    return f"Zapisałem fakt o Tobie ({author_clean}): {fact_about_self}"

        # 5. Definicje
        if " to jest " in c_low or " oznacza " in c_low:
            parts = content.split(" to jest " if " to jest " in c_low else " oznacza ", 1)
            if len(parts) == 2 and 2 < len(parts[0].strip()) < 35 and 3 < len(parts[1].strip()) < 200:
                term = parts[0].strip()
                definition = parts[1].strip()
                if self._is_safe_fact(term) and self._is_safe_fact(definition):
                    server_store["definitions"][term] = definition
                    self._save_vault()
                    return f"Nauczyłem się definicji pojęcia \"{term}\": {definition}"

        return None

    def build_context_for_prompt(self, author_name: str, query_text: str, guild_id: Optional[str] = None, guild_name: Optional[str] = None) -> str:
        """
        Buduje spersonalizowaną kapsułkę wiedzy łącząc globalne lore z pamięcią
        właściwego serwera.
        """
        server_store = self._get_server_store(guild_id, guild_name)
        user_key = author_name.lower().replace(" ", "_")
        user_info = server_store["users"].get(user_key)

        parts = []

        # Informacja o serwerze
        parts.append(f"Przestrzeń serwera: {server_store.get('guild_name', 'Ten serwer')} (ID: {server_store.get('guild_id', 'brak')})")

        # Globalne Lore: Twórca i Dowódca
        szatek = self.data.get("global_lore", {}).get("szatek_olo", {})
        if szatek:
            parts.append(f"Twój dowódca i stwórca: {szatek.get('canonical_name', 'Szatek_Olo')} ({', '.join(szatek.get('roles', []))})")

        # Profil rozmówcy na tym serwerze
        if user_info:
            parts.append(f"Rozmawiasz z użytkownikiem: {user_info.get('canonical_name', author_name)}")
            if user_info.get("roles"):
                parts.append(f"- Role na serwerze: {', '.join(user_info['roles'])}")
            if user_info.get("facts"):
                parts.append(f"- Zapamiętane fakty o rozmówcy: {'; '.join(user_info['facts'][:5])}")
        else:
            parts.append(f"Rozmawiasz z użytkownikiem: {author_name}")

        # Fakty tego konkretnego serwera (ostatnie 6)
        server_facts = server_store.get("facts", [])[-6:]
        if server_facts:
            facts_list = [f"• {f['content']}" for f in server_facts]
            parts.append("Zapamiętane fakty i ustalenia na tym serwerze:\n" + "\n".join(facts_list))

        # Definicje tego serwera
        if server_store.get("definitions"):
            defs = [f"• {k}: {v}" for k, v in list(server_store["definitions"].items())[:6]]
            parts.append("Znane definicje na tym serwerze:\n" + "\n".join(defs))

        return "\n\n".join(parts)

    def get_stats(self, guild_id: Optional[str] = None) -> Dict[str, Any]:
        """Zwraca statystyki pamięci (dla serwera lub łączne)."""
        if guild_id:
            store = self._get_server_store(guild_id)
            return {
                "server_name": store.get("guild_name", "Nieznany"),
                "users_count": len(store.get("users", {})),
                "facts_count": len(store.get("facts", [])),
                "definitions_count": len(store.get("definitions", {}))
            }
        
        total_servers = len(self.data.get("servers", {}))
        total_users = sum(len(s.get("users", {})) for s in self.data.get("servers", {}).values())
        total_facts = sum(len(s.get("facts", [])) for s in self.data.get("servers", {}).values())
        return {
            "servers_count": total_servers,
            "users_count": total_users,
            "facts_count": total_facts
        }
