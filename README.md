# 🤖 AETHER Discord AI Sentinel (Głos `proceed` + Ciągła Nauka + Publiczny GitHub Workflow)

Inteligentny, dedykowany model AI na Discorda stworzony z myślą o prywatnych serwerach, zintegrowany z **kanałem głosowym (`proceed`)**, **ciągłym uczeniem się z czatu** oraz **bezpieczną, szyfrowaną bazą pamięci (AES-256-GCM)** działającą bez przerw w **darmowym publicznym GitHub Actions Workflow**.

---

## ✨ Główne Funkcje

1. **🎙️ Rozmowy na Żywo na Kanale Głosowym (`proceed`)**:
   - Bot automatycznie dołącza do kanału głosowego `proceed` (lub wskazanego komendą `!dolacz`).
   - Mówi w czasie rzeczywistym krystalicznie czystym, neuronowym polskim głosem (`pl-PL-MarekNeural` przez silnik Microsoft Edge-TTS) bez limitów i bez opłat.
   - Gdy rozmawiasz z nim na czacie lub zadajesz pytanie, odpowiada tekstem i równocześnie wypowiada odpowiedź na kanale głosowym!

2. **🧠 Ciągłe Uczenie Się & Zapamiętywanie ("Kto kim jest")**:
   - Czyta wiadomości na kanale i buduje profile rozmówców (imiona, role, fakty, upodobania).
   - Zna tożsamość **`Szatek_Olo`** (Prezes ZSC, dowódca SZAT).
   - Reaguje na jawne polecenia: `zapamiętaj, że [fakt]`, `pamiętaj: [fakt]`, `zapisz: [fakt]`.
   - Potwierdza naukę reakcją 🧠 pod wiadomością.

3. **🔒 Żelazne Bezpieczeństwo w Publicznym Repozytorium (Zero-Leak)**:
   - Żaden token Discorda ani klucz API nigdy nie znajduje się w kodzie.
   - **Baza Pamięci jest Szyfrowana symetrycznie (`AES-256-GCM`)**: do publicznego repozytorium GitHub commitowany jest wyłącznie plik `knowledge_vault.enc`. Dla każdego w Internecie to losowy ciąg bajtów, którego nie da się podejrzeć bez klucza w Twoich prywatnych GitHub Secrets!

4. **⚡ Niezależny, Dedykowany Model AI ("Osobny Model")**:
   - Zasilany darmowym i potężnym silnikiem Llama 3.3 70B (Groq) lub Gemini 1.5/2.0 Flash, z automatycznym fallbackiem na Pollinations AI.
   - Posiada własną osobowość, poczucie humoru i lojalność wobec dowództwa ZSC.

---

## 🛠️ Instrukcja Wdrożenia w 5 Minut

### Krok 1: Discord Developer Portal
1. Wejdź na [Discord Developer Portal](https://discord.com/developers/applications) i kliknij **New Application** (np. nazwij ją `AETHER AI`).
2. Przejdź do zakładki **Bot**:
   - Zresetuj i skopiuj **Token** bota (będzie potrzebny w GitHub Secrets).
   - W sekcji **Privileged Gateway Intents** zaznacz:
     - ✅ **Presence Intent**
     - ✅ **Server Members Intent**
     - ✅ **Message Content Intent**
3. Przejdź do zakładki **OAuth2** -> **URL Generator**:
   - Zaznacz Scopes: `bot`, `applications.commands`.
   - Zaznacz Bot Permissions:
     - `Send Messages`, `Read Message History`, `Add Reactions`
     - `Connect`, `Speak`, `Use Voice Activity`
   - Skopiuj wygenerowany link i dodaj bota na swój prywatny serwer Discord.
4. Upewnij się, że na Twoim serwerze istnieje kanał głosowy o nazwie **`proceed`** (lub `procced`).

---

### Krok 2: Konfiguracja GitHub Secrets
W swoim repozytorium na GitHubie przejdź do:
**Settings** ➔ **Secrets and variables** ➔ **Actions** ➔ **New repository secret**:

| Nazwa Secretu | Opis | Wymagany? |
| :--- | :--- | :--- |
| `DISCORD_TOKEN` | Token Twojego bota z Discord Developer Portal | **TAK** |
| `VAULT_ENCRYPTION_KEY` | Dowolne Twoje bezpieczne hasło (np. 32 losowe znaki) do szyfrowania bazy AES-256 | **TAK** |
| `GROQ_API_KEY` | Darmowy klucz z [console.groq.com](https://console.groq.com) (dla Llama 3.3 70B) | Opcjonalny (zalecany) |
| `GEMINI_API_KEY` | Darmowy klucz z [Google AI Studio](https://aistudio.google.com) | Opcjonalny |
| `VOICE_CHANNEL_NAME` | Nazwa kanału głosowego (domyślnie: `proceed`) | Opcjonalny |

> [!TIP]
> Jeśli nie podasz klucza `GROQ_API_KEY` ani `GEMINI_API_KEY`, bot automatycznie użyje darmowego silnika Pollinations AI!

---

### Krok 3: Start w GitHub Actions
1. Przejdź w repozytorium do zakładki **Actions**.
2. Wybierz workflow **AETHER Discord AI Runner**.
3. Kliknij **Run workflow** ➔ **Run workflow**.
4. Bot uruchomi się na runnerze Ubuntu, dołączy do Twojego kanału głosowego **`proceed`** i przywita Cię głosem!
5. Workflow automatycznie odnawia się co 5 godzin, zapewniając nieprzerwaną pracę 24/7. Przed każdym restartem zaszyfrowana baza wiedzy `knowledge_vault.enc` jest automatycznie commitowana do repozytorium.

---

## 💬 Komendy na Discordzie

| Komenda | Działanie |
| :--- | :--- |
| `@AETHER [wiadomość]` | Rozmowa z modelem AI (odpowiada tekstem i głosem na kanale) |
| `zapamiętaj, że [fakt]` | Bot trwale zapisuje fakt w zaszyfrowanym Skarbcu Pamięci |
| `!dolacz [kanał]` | Dołącza bota do kanału głosowego (domyślnie `proceed`) |
| `!wyjdz` | Odłącza bota z kanału głosowego |
| `!powiedz [tekst]` | Czyta podany tekst neuronowym polskim głosem |
| `!status` | Pokazuje status połączenia głosowego, statystyki pamięci i szyfrowania |
| `!pomoc` | Wyświetla listę dostępnych funkcji |
