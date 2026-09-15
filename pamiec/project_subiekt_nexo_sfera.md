---
name: project-subiekt-nexo-sfera
description: "Integracja RM_BAZA z Subiekt nexo PRO idzie przez Sferę (nexo SDK, .NET 8 x64, most w C#) — NIE REST API, NIE pythonnet; NexoRecon zbudowany, brakuje haseł"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3bd503d0-19b5-46b7-a43e-70c121e814bb
  modified: 2026-09-02T17:12:32.500Z
---

Integracja RM_BAZA ↔ **Subiekt nexo PRO** idzie przez **Sferę dla nexo
(nexo SDK)**. Warunki spełnione (02.09.2026): licencja PRO ✅, abonament ✅,
SDK pobrane ✅, **skrypt rozpoznawczy NexoRecon zbudowany i przetestowany ✅**.
Do pierwszego realnego odczytu brakuje tylko haseł (SQL `sa` + login/hasło
użytkownika nexo) — wpisać do `C:\RMPAK_CLIENT\.nexo_sfera.json`, nigdy do repo.

**Gdzie co leży:**
- SDK: `C:\iLogic\Subiekt_nexo_PRO_dokumentacja\SDK` (1,2 GB, wersja 61.1.0.9431 =
  wersja bazy). Link źródłowy: `https://ftp.insert.com.pl/pub/demo/InsERT_nexo/nexoSDK.exe`
  (7-Zip SFX, bez logowania).
- Czytnik dokumentacji: `C:\iLogic\Subiekt_nexo_PRO_dokumentacja\CHM\tools\doc.py` (`tree` / `find` / `read`),
  indeks `sfera_index.tsv`, 82 tys. stron HTML z CHM. Szczegóły: plan, sekcja 9.
- Most: `subiekt_sfera/NexoRecon/` w repo (tylko csproj+Program.cs); bin 549 MB
  w `.gitignore`. Build: `dotnet build -c Release -nowarn:MSB3277`.
- Ściąga API (start, menedżery, encje ModelDanych): plan, sekcja 10.

**Decyzje architektoniczne (uzasadnione, nie otwierać ponownie bez powodu):**
- Most w **C# .NET 8 x64 jako osobny proces**, nie `pythonnet`: Sfera jest tylko
  64-bit, `Security.Core.dll` to C++/CLI wymagający `ijwhost.dll`, build ciągnie
  554 zależności. Przepis `SferaConsoleApp.targets` jest w SDK i działa.
- Tylko `ProductId.Subiekt` w `Polacz` — każdy dodatkowy produkt to osobna licencja PRO.

**Pułapki (kosztowały czas):**
- `hh.exe -decompile` milczy przy ścieżce ze spacjami → kopiować CHM do ścieżki bez spacji.
- Dwie rodziny encji: `InsERT.Moria.Archiwa.*` vs `InsERT.Moria.ModelDanych.*` —
  Sfera używa **ModelDanych**; przy sprawdzaniu pól zawężać breadcrumb.
  (`Dokument.DataWystawienia` jest tylko w Archiwa; w ModelDanych `DataWprowadzenia`.)
- `JednostkaMiaryAsortymentu.Symbol` to metoda, nie właściwość.
- Długie heredoki z apostrofami psują Git Bash w tym środowisku → duże pliki
  pisać narzędziem Write, nie `cat <<EOF`.
- Sfera **istnieje w dwóch odmianach**: GT (COM/32-bit) i nexo (.NET). Twierdzenie
  „Sfera dla nexo nie istnieje" jest FAŁSZYWE. Ślepe tropy już przerobione:
  InsERT API (REST — nexo PRO nie na liście), InsERT mobile (to aplikacja, nie API),
  Easy Nexo Integrator (trzecia firma, ~900 zł, niepotrzebne).

**Why:** plan był dwa razy przepisywany pod błędne założenia (GT, potem REST),
co kosztowało użytkownika realne klikanie po portalu InsERT. Teraz łańcuch
build → ijwhost → Sfera → sieć → SQL jest potwierdzony testem dymnym
(`Login failed for user 'sa'` z celowo złym hasłem = wszystko poza hasłem działa).

**Uruchomiony na żywo 02.09.2026 (baza `Nexo_RM PRODUKCJA`, operator `GKI`) —
kluczowe fakty (szczegóły: plan, sekcja 12):**
- Magazyn prowadzony **bezpośrednio przez FZ/FS** (statusy „Przyjęty/Wydany
  towar"); PZ/WZ/RW wygasły w 2023–24. **ZD nigdy nie używane (0)** — plan
  „RM_BAZA → ZD" to zmiana procesu, wymaga decyzji firmy.
- Stany żywe → Subiekt = źródło prawdy o stanie (rozstrzygnięte).
- 2745 kartotek; **oba systemy używają tego samego formatu numeru rysunku**
  (`013-100.22X`). Z 4425 numerów RM_BAZA kartotekę ma tylko **135 (3 %)**;
  części powtarzalne (`013-100.22X` w 15 projektach) nie mają — reguła
  „kartoteka na żądanie" trafiona.
- Jakość danych: spacje na końcu symboli, `a`/`A`, nazwy w polu numeru
  w RM_BAZA — porównywać TRIM + case-insensitive, filtrować kształt numeru.
- Druga baza `Nexo_RMPAK SPZOO` (185 kartotek, żywa sprzedaż) — **brak konta
  GKI** (tylko GDziedzic, Szef).
- Dwie godziny zjadły literówki O↔0 w hasłach; przy `Login failed` najpierw
  goły test SQL (`SqlConnectionStringBuilder`) — rozdziela hasło od Sfery.
- Odczyt tabel użytkowników/połączeń poza zapytaniem z SDK blokuje
  klasyfikator — nie próbować, pytać użytkownika.

**How to apply:** krok 2 = najpierw decyzja procesowa (ZD czy lista), potem
most z `--json` i komendami `stan` / `kartoteka-utworz` / `zd-utworz`,
testowanymi na KOPII bazy. Przed zmianą planu czytać jego nagłówek
„Historia błędów". Powiązane: [[project-ksef-price-import]].
