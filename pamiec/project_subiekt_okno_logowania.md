---
name: project_subiekt_okno_logowania
description: "Okno logowania do Subiekta (Ustawienia) — haslo ADMIN odblokowuje narzedzie, nie role; pulapki icacls i flagi mostu"
metadata: 
  node_type: memory
  type: project
  originSessionId: 834ab505-1a4e-4f62-bb02-1b4871507207
  modified: 2026-09-06T15:14:24.097Z
---

**Ustawienia → 🔗 Połączenie z Subiektem… (ADMIN)** — `subiekt_polaczenie_gui.py`
+ `subiekt_konfig.py` (commit `f187c38`, 06.09.2026). Powstało, bo dane logowania
trzeba było wpisywać wprost w `C:\RMPAK_CLIENT\.nexo_sfera.json`, a użytkownik
zakłada RM_BAZA u kolejnych userów.

## Model dostępu — hasło ADMIN-a odblokowuje NARZĘDZIE, nie rolę

Administrator siada na stanowisku **zalogowanym na zwykłego usera**, podaje swoje
hasło, konfiguruje Subiekta i odchodzi. Sesja RM_BAZA **ani na moment** nie zmienia
użytkownika — `current_user_role` nietknięte, żadnego przelogowania.

Hasło pytane przy **każdym otwarciu**, także gdy sesja jest już na ADMIN
(„zamknięcie narzędzia i ponowne otwarcie — znowu hasło ADMIN"). Wyjątek dla roli
oznaczałby, że na stanowisku admina okno stoi otworem przy hasłach Subiekta.

Weryfikacja jak przy zmianie użytkownika w RM_BAZA: sha256 wobec `password_hash`
z tabeli `users` w master.sqlite (wzorzec: `on_user_selected`). Żadnej własnej
kryptografii, żadnego osobnego hasła.

## Trzy przyciski

| | |
|---|---|
| Testuj połączenie | na KOPII w `%TEMP%`; test po zapisie = literówka nadpisuje działającą konfigurację |
| Zapisz i zaloguj | zapis + **restart mostu** — most czyta konfigurację raz, przy starcie procesu |
| Wyloguj | kasuje SAME hasła (serwer/baza/loginy zostają) + ubija most |

## ⚠️ Pułapki, które kosztowały rundy na produkcji

**`icacls` potrafi zamknąć plik przed właścicielem.** Reguła budowana
z `os.environ['USERNAME']`, a ta zmienna bywa pusta → `MONGO\:(F)`, czyli nadanie
praw NIKOMU, przy zdjętym dziedziczeniu (`/inheritance:r`). Most dostawał
`UnauthorizedAccessException`, plik był nieczytelny nawet dla mnie. Ratunek:
`icacls <plik> /reset` (z PowerShella — Git Bash zamienia `/reset` na ścieżkę!).
Zabezpieczenia: nazwa z `getpass.getuser()`, brak nazwy = nie ruszamy uprawnień,
SYSTEM po SID `*S-1-5-18` (nazwa zależy od języka Windows), **weryfikacja odczytu
po zmianie** z cofnięciem. Plik tymczasowy do testu — `zawez=False`, bo most to
osobny proces.

**`_most_niedostepny` żyje do końca procesu RM_BAZA.** Jedna nieudana próba i kolejne
starty w ogóle nie ruszają — poprawienie złego hasła nic nie daje bez restartu
aplikacji. Stąd `subiekt_bridge.pozwol_na_ponowna_probe()`.

**Zmiany w kodzie Pythona wymagają restartu RM_BAZA** — moduły są zaimportowane
w pamięci. Dwa razy z rzędu widziałem „ten sam błąd mimo poprawki", zanim to
zauważyłem.

**Cyrylica w nazwach zmiennych.** Wkradło się `działа` z U+0430 — kod działa
(obie linie używają tej samej nazwy), ale to mina. Wykrywanie:
`any(0x400<ord(c)<0x500 for c in tekst)`.

Świadomie **BEZ szyfrowania haseł**: klucz musiałby leżeć obok, więc dawałoby to
złudzenie bezpieczeństwa kosztem diagnostyki. Ochrona = uprawnienia pliku, który
leży poza repo.

**How to apply:** Ścieżka konfiguracji TYLKO z `subiekt_konfig.CONFIG_PATH` — była
powtórzona w trzech miejscach ([[project_subiekt_stan_05_09_2026]]). Testując
„Wyloguj" pamiętaj, że kasuje hasła — kopie zostają w `%TEMP%\subiekt_cfg_*`
do czasu sprzątnięcia. Patrz [[project_subiekt_most_stan_serwera]],
[[feedback_start_rm_baza]].
