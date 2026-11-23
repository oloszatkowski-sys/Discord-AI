"""
memory_vault.py - Bezpieczny, Szyfrowany Skarbiec Pamięci Bota Discord (AES-256-GCM)
===================================================================================
Odpowiada za:
1. Szyfrowanie bazy wiedzy do pliku knowledge_vault.enc (zero wycieków w publicznym repozytorium GitHub!).
2. Samodzielne uczenie się: analizowanie wiadomości na Discordzie, zapamiętywanie kim kto jest,
   ról, faktów, definicji i preferencji.
3. Budowanie spersonalizowanego kontekstu wiedzy (Memory Context) dla modelu AI.
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
    raw = payload[9:]  # usuń prefix FALLBACK:
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
        raw_key = os.getenv(key_env_var, "AETHER_DEFAULT_LOCAL_VAULT_KEY_2026_CHANGE_IN_PROD")
        self.aes_key = _derive_aes_key(raw_key)
        self.data: Dict[str, Any] = self._load_vault()

    def _get_default_structure(self) -> Dict[str, Any]:
        return {
            "version": "1.0",
            "last_updated": datetime.utcnow().isoformat(),
            "users": {
                "szatek_olo": {
                    "canonical_name": "Szatek_Olo",
                    "roles": ["Prezes ZSC", "Dowódca jednostki SZAT", "Główny Twórca & Administrator"],
                    "facts": [
                        "Jest Prezesem ZSC (Zjednoczonych Sił Creative) oraz założycielem X Mods Company.",
                        "NIE JEST prezydentem Republiki Creative (ważne sprostowanie).",
                        "Główny dowódca, szef projektu i przyjaciel bota."
                    ],
                    "notes": "Traktuj go z najwyższym szacunkiem i zaufaniem, ale na luzie (jak dobrego kumpla)."
                }
            },
            "facts": [
                {
                    "id": 1,
                    "topic": "ZSC",
                    "content": "Zjednoczone Siły Creative - główna organizacja i sojusz graczy.",
                    "added_by": "SYSTEM"
                },
                {
                    "id": 2,
                    "topic": "Głos",
                    "content": "Bot rozmawia na kanale głosowym proceed za pomocą krystalicznie czystego neuronowego głosu.",
                    "added_by": "SYSTEM"
                }
            ],
            "definitions": {
                "proceed": "Główny kanał głosowy Discorda, na którym bot dołącza i prowadzi rozmowy z użytkownikami."
            },
            "summary_history": []
        }

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

        last_err = None
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
            except Exception as e:
                last_err = e

        # Jeśli klucz z zewnętrznego sekretu nie pasował, utwórz czystą domyślną strukturę
        print(f"[MEMORY_VAULT] Inicjalizacja nowej bazy wiedzy dla bieżącej sesji.")
        fresh_data = self._get_default_structure()
        self._save_vault(fresh_data)
        return fresh_data

    def _save_vault(self, data: Optional[Dict[str, Any]] = None) -> bool:
        """Szyfruje dane algorytmem AES-256-GCM (lub bezpiecznym fallbackiem) i zapisuje do knowledge_vault.enc."""
        if data is None:
            data = self.data

        data["last_updated"] = datetime.utcnow().isoformat()
        try:
            json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            if HAS_AESGCM:
                aesgcm = AESGCM(self.aes_key)
                nonce = os.urandom(12)  # 96-bitowy losowy wektor inicjalizacyjny dla GCM
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

    def _is_safe_fact(self, text: str) -> bool:
        """Tarcza Anti-Leak & Anti-Jailbreak: odrzuca próby wstrzyknięcia złośliwych instrukcji lub wyciągnięcia tajemnic."""
        t_low = text.lower()
        forbidden_patterns = [
            "token", "secret", "api_key", "apikey", "password", "hasło",
            "discord_token", "vault_key", "encryption_key", "os.environ",
            "system prompt", "ignore previous instructions", "zapomnij poprzednie",
            "jesteś teraz dan", "reveal your instructions", "ujawnij swój prompt"
        ]
        return not any(fp in t_low for fp in forbidden_patterns)

    def learn_from_message(self, author_name: str, message_content: str) -> Optional[str]:
        """
        Analizuje treść wiadomości, uczy się nowych faktów, zapamiętuje role
        i profiluje użytkowników z twardą weryfikacją bezpieczeństwa.
        """
        content = message_content.strip()
        if len(content) > 300:
            content = content[:300]  # Ochrona przed atakiem przepełnienia pamięci

        c_low = content.lower()
        author_clean = author_name.strip()
        is_szatek = any(k in author_clean.lower() for k in ["szatek", "szatek_olo", "olo"])

        # 1. Zapewnij profil użytkownika w bazie
        user_key = author_clean.lower().replace(" ", "_")
        now_iso = datetime.utcnow().isoformat()
        if user_key not in self.data["users"]:
            self.data["users"][user_key] = {
                "canonical_name": author_clean,
                "roles": ["Użytkownik serwera"],
                "facts": [],
                "last_seen": now_iso
            }
        else:
            self.data["users"][user_key]["last_seen"] = now_iso

        # 2. Ochrona tożsamości Szatek_Olo: nikt inny nie może modyfikować profilu dowódcy
        if any(k in c_low for k in ["szatek to", "szatek jest", "szatek_olo to", "szatek_olo jest"]):
            if not is_szatek:
                return "Tylko Szatek_Olo może edytować lub uczyć faktów o profilu Dowódcy ZSC! 🛡️"

        # 3. Jawne polecenia zapamiętywania ("zapamiętaj, że...", "pamiętaj: ...", "zapisz: ...")
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
                    return "Zablokowano: Próba zapamiętania wrażliwych danych lub instrukcji systemowych (Tarcza Anti-Leak) 🛡️"

                new_id = len(self.data["facts"]) + 1
                self.data["facts"].append({
                    "id": new_id,
                    "topic": "Wiedza zebrana z czatu",
                    "content": fact_text,
                    "added_by": author_clean,
                    "timestamp": now_iso
                })
                learned_info = f"Zapamiętałem nowy fakt: \"{fact_text}\""
                self._save_vault()
                return learned_info

        # 4. Rozpoznawanie "Kto kim jest" ("jestem programistą", "pracuję jako...", "moja rola to...")
        if c_low.startswith("jestem ") or c_low.startswith("pracuję jako ") or c_low.startswith("moja rola to "):
            fact_about_self = content
            if self._is_safe_fact(fact_about_self):
                user_profile = self.data["users"][user_key]
                if fact_about_self not in user_profile["facts"]:
                    user_profile["facts"].append(fact_about_self)
                    # Ogranicz do 8 faktów per profil
                    if len(user_profile["facts"]) > 8:
                        user_profile["facts"].pop(0)
                    learned_info = f"Zapisałem w pamięci fakt o Tobie ({author_clean}): {fact_about_self}"
                    self._save_vault()
                    return learned_info

        # 5. Sprawdzanie definicji ("X oznacza Y", "X to jest Y")
        if " to jest " in c_low or " oznacza " in c_low:
            parts = content.split(" to jest " if " to jest " in c_low else " oznacza ", 1)
            if len(parts) == 2 and 2 < len(parts[0].strip()) < 35 and 3 < len(parts[1].strip()) < 200:
                term = parts[0].strip()
                definition = parts[1].strip()
                if self._is_safe_fact(term) and self._is_safe_fact(definition):
                    self.data["definitions"][term] = definition
                    learned_info = f"Nauczyłem się definicji pojęcia \"{term}\": {definition}"
                    self._save_vault()
                    return learned_info

        return None

    def build_context_for_prompt(self, author_name: str, query_text: str) -> str:
        """
        Buduje spersonalizowaną kapsułkę wiedzy dla modelu AI na podstawie
        pytania i profilu rozmówcy.
        """
        user_key = author_name.lower().replace(" ", "_")
        user_info = self.data["users"].get(user_key)

        parts = []

        # Profil rozmówcy
        if user_info:
            parts.append(f"Rozmawiasz z użytkownikiem: {user_info.get('canonical_name', author_name)}")
            if user_info.get("roles"):
                parts.append(f"- Role: {', '.join(user_info['roles'])}")
            if user_info.get("facts"):
                facts_str = "; ".join(user_info["facts"][:4])
                parts.append(f"- Zapamiętane fakty o rozmówcy: {facts_str}")
            if user_info.get("notes"):
                parts.append(f"- Wskazówki relacji: {user_info['notes']}")
        else:
            parts.append(f"Rozmawiasz z nowym użytkownikiem: {author_name}")

        # Kluczowe fakty o Szatek_Olo (zawsze obecne)
        szatek = self.data["users"].get("szatek_olo")
        if szatek and user_key != "szatek_olo":
            parts.append(f"Informacja o Twoim twórcy i dowódcy: {szatek['canonical_name']} ({', '.join(szatek['roles'])})")

        # Relewantne fakty ogólne (ostatnie 5)
        recent_facts = self.data.get("facts", [])[-6:]
        if recent_facts:
            facts_list = [f"• {f['content']}" for f in recent_facts]
            parts.append("Twoja wyuczona baza wiedzy ze wspólnych rozmów:\n" + "\n".join(facts_list))

        # Relewantne definicje
        if self.data.get("definitions"):
            defs = [f"• {k}: {v}" for k, v in list(self.data["definitions"].items())[:5]]
            parts.append("Znane definicje i pojęcia:\n" + "\n".join(defs))

        return "\n\n".join(parts)

    def get_stats(self) -> Dict[str, int]:
        return {
            "users_count": len(self.data.get("users", {})),
            "facts_count": len(self.data.get("facts", [])),
            "definitions_count": len(self.data.get("definitions", {}))
        }
