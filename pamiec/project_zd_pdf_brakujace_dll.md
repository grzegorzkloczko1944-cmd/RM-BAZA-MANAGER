---
name: project_zd_pdf_brakujace_dll
description: "PDF zamowienia ZD nie powstawal — Stimulsoft szuka 7 bibliotek InsERT OBOK NexoRecon.exe, hook SdkLoader ich nie lapie; naprawione recznie 15.09.2026, csproj NIE poprawiony"
metadata: 
  node_type: memory
  type: project
  originSessionId: 58f9b752-f127-4b24-a83d-09f1cb22b23c
  modified: 2026-09-15T14:17:16.501Z
---

**Objaw:** wysyłka ZD robi maila z rysunkami, ale **bez PDF-a zamówienia**.
Żadnego błędu w oknie — tylko dyskretne `brak PDF zamówienia: …` w pasku
stanu okna wysyłki. Most odpowiadał normalnie na wszystko inne (logowanie,
odczyt ZD, NIP, dostawca) — padał wyłącznie eksport.

**Prawdziwa przyczyna (15.09.2026):** silnik wydruku **Stimulsoft** ładuje
biblioteki InsERT-u **z katalogu obok `NexoRecon.exe`**, a nie przez hook
`AssemblyResolve` z `SdkLoader.cs`. Hook dostaje szansę tylko wtedy, gdy .NET
sam nie znajdzie pliku — Stimulsoft go omija. `Eksport()` **nie rzuca
wyjątku**, po prostu nic nie zapisuje.

Brakowało **7 bibliotek** (dołożone z `C:\iLogic\SUBIEKT\Bin\`):
```
InsERT.Moria.Narzedzia.dll          InsERT.Moria.ModelDanych.dll
InsERT.Mox.Core.dll                 InsERT.Moria.PolaWlasne.dll
InsERT.Moria.API.dll                InsERT.Mox.EntityFramework.Core.dll
InsERT.Mox.EntityFrameworkSupport.dll
```

**Jak to zdiagnozować w 2 minuty** (zamiast zgadywać — tak poszło za pierwszym
razem i kosztowało godzinę):
```powershell
NexoRecon.exe wydruk-recon "--numery=ZD 11/09/2026" "--out=%TEMP%\r.json"
```
i czytać pole **`bledy_wydruku`** — Sfera mówi wprost
`Could not find file '...\InsERT.X.dll'`. Doładowywać po jednej w pętli,
aż `pdf_powstal: true` (7 iteracji).

⚠️ **`WydrukRecon.cs` linia ~310 robiła `.ToString()` na `List<string>`** —
raport pokazywał `System.Collections.Generic.List'1[System.String]` zamiast
treści, czyli JEDYNĄ informację o przyczynie. Poprawione 15.09.2026
(rozwijanie `IEnumerable`). Bez tej poprawki diagnostyka jest ślepa.

**How to apply:**
- ✅ **ZAŁATWIONE (f7bd51c + 4cb4609, 15.09.2026) — DZIEWIĘĆ bibliotek, nie 7.**
  Poza siedmioma InsERT-a potrzebne są **`Stimulsoft.Base` i `Stimulsoft.Report`**
  (sam silnik wydruku). Dwa miejsca zakładają dowiązania:
  `csproj` → `DowiazBibliotekiWydruku` + `dowiaz_biblioteki_wydruku.ps1` (build),
  oraz `SdkLoader.Podepnij()` → `ZadbajOBibliotekiWydruku()` (**start mostu**,
  w katalogu, w którym most realnie stoi).
- ⚠️⚠️ **TESTOWAĆ NA KATALOGU Z SAMYM MOSTEM, NIE W `bin\Release`.** Build
  kopiuje tam biblioteki Stimulsoftu, więc u budującego PDF działa zawsze —
  a na stanowisko jedzie **5 plików** (`NexoRecon.exe` + `.dll` + 2 `.json`
  + `wersja.json`) do `C:\iLogic\Subiekt\MOST`. Tak przeoczyłem brak
  Stimulsoftu: build był poprawny, a PDF na stanowisku dalej nie powstawał.
  Symulacja: skopiować te 4 pliki do pustego katalogu i tam uruchomić.
- Dlatego most **zakłada dowiązania sam przy starcie** — każde stanowisko ma
  własne SDK Sfery (most i tak dociąga z niego 435 bibliotek), więc źródło
  jest na miejscu. Pliki o zgodnym rozmiarze i czasie zostawia, więc kolejne
  starty nic nie robią i dwa mosty naraz nie kasują sobie plików.
- Hardlink **nie wymaga admina**, symlink WYMAGA (`New-Item -ItemType
  SymbolicLink` → „Administrator privilege required"). Działa tylko w obrębie
  jednego wolumenu; przy SDK na innym dysku skrypt schodzi na kopię.
- ❌ **PRÓBOWANE I NIE DZIAŁA — nie powtarzać:** `AssemblyLoadContext.`
  `Resolving`, `AppDomain.CurrentDomain.AssemblyResolve` (z `Assembly.LoadFrom`)
  oraz `APP_PATHS` w `runtimeconfig.json`. Wszystkie trzy bez efektu, bo
  Stimulsoft **nie ładuje przez .NET** — skleja ścieżkę jako tekst i czyta
  plik z dysku. Dlatego plik MUSI fizycznie być obok `.exe`.
- ⚠️ **NIE dopisywać ich po prostu do kopiowania w csproj.** Target
  `NieKopiujBibliotekInsERT` usuwa je ŚWIADOMIE (komentarz w csproj, linie
  32-50): kopia zostaje na starej wersji, baza aktualizuje się sama przy
  starcie Subiekta, i wtedy most startuje, odpowiada na ping, ale **nigdy nie
  osiąga ready** — RM_BAZA wisi na przejęciu locka (zdarzyło się 09.09.2026).
  Do tego .NET ładuje z katalogu aplikacji ZANIM odezwie się hook, więc
  wykrywanie nowszej wersji przestaje działać.
- **Obecny stan = mina:** te 7 plików to zamrożone 61.1.1.9471. Po
  aktualizacji Subiekta wrócą objawy z 09.09. Właściwe rozwiązanie: nauczyć
  most podsuwać te biblioteki Stimulsoftowi **z instalacji Subiekta**
  (zgodne z bazą), nie kopią. Decyzja użytkownika: odłożone, PDF miał działać
  od razu.
- **Nie mylić z „Sesja Sfery padła"** — to osobna awaria tego samego dnia
  (most wisiał od 14:19 z martwą sesją po utracie NAS-a). Ubicie procesu
  NIE naprawiło PDF-a; przyczyny są niezależne. Patrz [[project_nas_nic_poswiadczenia]].
- Trwały most wstaje sam przy starcie RM_BAZA (`rozgrzej_w_tle()`, commit
  3e1dec4 z 14.09) — start Sfery kosztuje ~9-11 s, więc tak ma być.
- ✅ **NAPRAWIONE (commit 15c3f61, 15.09.2026):** most zostawał martwy po
  nieudanej odbudowie sesji — „Sesja Sfery padła" przy każdej operacji aż do
  ręcznego ubicia procesu. Dwie przyczyny: `Connect()` nie wołał `Rozlacz()`
  po nieudanym `Polacz()`/`ZalogujOperatora()` (trupy rosły do 1,3 GB RAM),
  a `_ostatniaAktywnosc` zostawała świeża po porażce, więc przez minutę nikt
  sesji nie sprawdzał. Teraz cofana do `MinValue` — następna komenda próbuje
  od razu.
- Outlook potrafi rzucić `-2147352567 … "a dialog box is open"` przy dopinaniu
  załączników, mimo że okno wiadomości POWSTAJE poprawnie. Sprawdzić okno,
  zanim uzna się to za awarię.
- Kontekst mostu: [[project_subiekt_most_stan_serwera]], [[project_subiekt_wysylka_zd]].
