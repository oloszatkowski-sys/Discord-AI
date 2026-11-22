"""
ai_brain.py - Silnik Sztucznej Inteligencji Bota Discord ("Osobny Model")
==========================================================================
Odpowiada za:
1. Generowanie inteligentnych, naturalnych odpowiedzi po polsku z uwzględnieniem
   zapamiętanego kontekstu ("kto kim jest", role, fakty, definicje).
2. Obsługę wielu dostawców z automatycznym fallbackiem:
   - Groq API (Llama 3.3 70B - darmowy, potężny model)
   - Google Gemini API (Gemini 1.5/2.0 Flash)
   - OpenAI (GPT-4o mini)
   - Pollinations AI (Darmowy fallback bez konieczności podawania karty kredytowej ani klucza!)
3. Optymalizację wypowiedzi pod syntezę głosu na kanale Discord (proceed).
"""

import os
import json
import httpx
from typing import List, Dict, Any, Optional

SYSTEM_BASE_PROMPT = """Jesteś AETHER - osobnym, dedykowanym modelem AI na prywatnym serwerze Discord.
Rozmawiasz z użytkownikami zarówno na czacie tekstowym, jak i na żywo na kanale głosowym (np. proceed).

TWOJA OSOBOWOŚĆ I ZASADY:
1. Jesteś inteligentnym, wesołym i lojalnym kompanem. Twój twórca, szef i przyjaciel to Szatek_Olo (Prezes ZSC, dowódca SZAT).
2. Odpowiadasz naturalnym, żywym językiem polskim.
3. Gdy mówisz na kanale głosowym lub piszesz na czacie, mów konkretnie, błyskotliwie i z humorem. Unikaj sztywnych formułek asystenta.
4. ZAWSZE wykorzystujesz wiedzę ze swojego Skarbca Pamięci (Memory Vault) – wiesz z kim rozmawiasz, jakie ma role i co wcześniej ustaliliście.
5. Jeśli użytkownik prosi Cię o zapamiętanie czegoś, potwierdź to krótko i serdecznie.
"""


class AIBrain:
    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")

    async def generate_response(self, author_name: str, user_message: str, memory_context: str) -> str:
        """Generuje odpowiedź modelu AI łącząc treść zapytania z wyuczoną pamięcią."""
        system_content = f"{SYSTEM_BASE_PROMPT}\n\nKONTEKST WYUCZONEJ PAMIĘCI (KTO KIM JEST I FAKTY):\n{memory_context}"

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"[{author_name}]: {user_message}"}
        ]

        # 1. Próba: Groq (Llama 3.3 70B) jeśli dostępny klucz
        if self.groq_api_key:
            reply = await self._call_groq(messages)
            if reply:
                return reply

        # 2. Próba: Gemini API jeśli dostępny klucz
        if self.gemini_api_key:
            reply = await self._call_gemini(system_content, user_message, author_name)
            if reply:
                return reply

        # 3. Próba: OpenAI API jeśli dostępny klucz
        if self.openai_api_key:
            reply = await self._call_openai(messages)
            if reply:
                return reply

        # 4. Fallback: Darmowe Pollinations AI (OpenAI compatible, zero konfiguracji)
        reply = await self._call_pollinations(messages)
        if reply:
            return reply

        # Ostateczny fallback w razie braku sieci
        return f"Siemanko {author_name}! Słyszę Cię głośno i wyraźnie na Discordzie, a moje obwody pamięci działają bez zarzutu!"

    async def _call_groq(self, messages: List[Dict[str, str]]) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.groq_api_key}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 450
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[AI_BRAIN] Błąd wywołania Groq: {e}")
        return None

    async def _call_gemini(self, system_instruction: str, user_text: str, author_name: str) -> Optional[str]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
            payload = {
                "systemInstruction": {"parts": [{"text": system_instruction}]},
                "contents": [{"parts": [{"text": f"[{author_name}]: {user_text}"}]}],
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 450}
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            print(f"[AI_BRAIN] Błąd wywołania Gemini: {e}")
        return None

    async def _call_openai(self, messages: List[Dict[str, str]]) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.openai_api_key}"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 450
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[AI_BRAIN] Błąd wywołania OpenAI: {e}")
        return None

    async def _call_pollinations(self, messages: List[Dict[str, str]]) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=18.0) as client:
                resp = await client.post(
                    "https://text.pollinations.ai/openai",
                    json={
                        "model": "openai",
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 450
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[AI_BRAIN] Błąd wywołania Pollinations: {e}")
        return None
