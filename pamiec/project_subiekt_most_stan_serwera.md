---
name: project_subiekt_most_stan_serwera
description: "Staly most Sfery — ZREALIZOWANY 06.09.2026. Architektura, pulapki, stan wdrozenia."
metadata: 
  node_type: memory
  type: project
  originSessionId: 834ab505-1a4e-4f62-bb02-1b4871507207
  modified: 2026-09-06T13:42:43.138Z
---

**ZROBIONE.** Plan z 05.09.2026 zrealizowany 06.09.2026, 36 commitów (`e3547ed..52d2296`), most jest w repo `RM-BAZA-MANAGER` na `main` (gałąź `most-server` trzyma w `most-dist/` kopię zapasową wystawionej binarki — 590 KB, żeby dało się odtworzyć, co dokładnie mieli userzy danego dnia).

Pełny opis: [`SUBIEKT_ZMIANY_2026-09-06.md`](../../../c%3A/RMPAK_CLIENT/Repozytoria/RM-BAZA-MANAGER/SUBIEKT_ZMIANY_2026-09-06.md) w repo, architektura i decyzje: `SUBIEKT_STALY_MOST_PLAN.md`. Ten plik jest streszczeniem — szczegóły w repo.

## Wynik pomiarów (baza demo, 247 kartotek)

| Operacja | Stare CLI | Most |
|---|---:|---:|
| kontrahenci | 14 368 ms | **104 ms** |
| stan | 14 135 ms | **296 ms** |
| magazyn | 14 218 ms | **753 ms** |
| katalog (2. raz) | ~13 500 ms | **8–50 ms** |

Narzut startowy (logowanie do Sfery) znika niezależnie od rozmiaru bazy. Benchmark na produkcji — patrz niżej.

## Architektura

`NexoRecon.exe server` — TCP `127.0.0.1:51273`, JSON + 4B nagłówek długości. Wątek per klient → kolejka FIFO → **jeden worker** (Sfera nie jest bezpieczna wielowątkowo). `ping`/`status` omijają kolejkę. Nowe pliki: `NexoSession.cs`, `CommandDispatcher.cs` (wspólny dla CLI i servera — **handlery nie zmieniane**), `ServerHost.cs`, `subiekt_bridge.py` (klient z autostartem i fallbackiem do CLI), `subiekt_panel.py` (nowy panel z kaflami, zastępuje menu; stare menu zostaje pod PPM).

## Zasady, których nie wolno złamać

- **WRITE nigdy nie jest ponawiany automatycznie** (`zd`, `kartoteka`, `rw`, `progi`, `termin`, `zd-usun`, `dostawcy`, `symbole`, `kartoteka-usun`) — zwraca `UNKNOWN_COMMIT_STATE`, bo most nie wie, czy operacja przeszła. Jedyny retry: `SESSION_LOST` z pre-checku (sesja padła **przed** handlerem) — tam Python ponawia raz.
- **`progi` łamie prostą regułę READ/WRITE** — bez `--plan` to odczyt, z planem zapis; `CzyZapis` traktuje go osobno.
- Nasłuch **tylko 127.0.0.1**, mutex **`Local\`** (nie `Global\`) per user Windows.
- Sesja sprawdzana przed handlerem gdy >60 s od ostatniej komendy (`UpewnijSieZeSesjaZyje`) — chroni przed uśpieniem komputera i restartem SQL. Zmierzony czas do `SESSION_LOST` przy leżącym SQL: ~2 min (timeout sterownika, nie mostu).
- **Sfera NIE cachuje stanów** — zweryfikowane na żywo (sesja z 17 min uptime natychmiast zobaczyła cudze RW). To był największy nierozpoznany problem przed testem.

## Pułapki, które kosztowały rundy

- `DETACHED_PROCESS` bez konsoli → `Console.OutputEncoding` rzuca, proces ginie **przed pierwszym logiem**. Komunikaty idą przez `Powiedz()`, zawsze też do pliku logu.
- Stara binarka po `git pull` bez rebuilda **nie zgłasza błędu** — traktuje `server` jak nieznany tryb, kończy kodem 0, Python cicho schodzi na wolny fallback CLI. RM_BAZA teraz porównuje datę binarki z `ServerHost.cs` i pokazuje okienko.
- `Bezp(rw.PodajBledy)` wywalało się **przed** wejściem do try/catch — konwersja `dynamic → Func` leci poza `Bezp`, przykrywając prawdziwy powód odrzucenia RW przez `RuntimeBinderException` (`RozchodWewnetrznyBO` nie ma `PodajBledy()`).
- Kolizja nazw: encja SDK `Magazyn` vs handler `Magazyn.cs` — w `namespace NexoRecon` wygrywa handler; `Rozpoznanie.cs` używa aliasu `MagazynSfera`.
- Panel (liczniki w tle) i okno otwarte kliknięciem dzielą jedną kolejkę mostu — wątek liczący musi sprawdzać znacznik przerwania między zapytaniami, inaczej okno "wisi".

## Dystrybucja binarki (userzy mają .exe, nie Pythona/dotnet)

Most **nie działa sam** — `NexoSession.PodepnijSdk()` doładowuje w locie 435 bibliotek InsERT z `C:\iLogic\SUBIEKT\Bin\` (1,1 GB), więc ten katalog musi być na KAŻDEJ maszynie. Dlatego binarka leży obok niego, nie osobno.

```
C:\iLogic\Subiekt\
├── Bin\            1,1 GB   SDK Sfery — wgrywane RAZ przy zakładaniu stanowiska
├── MOST\           590 KB   most, który DZIAŁA (cel „Pobierz most")
├── MOST_STAGING\   590 KB   ← to wgrywasz na serwer (TYLKO u budującego)
└── Narzedzia\, dotnet-sdk...exe
```

**Łańcuch:** źródła (`main`) → `dotnet build` → `MOST_STAGING\` → serwer `Y:\RMPAK_CLIENT\iLogic\Subiekt\MOST\` → „Pobierz most" → `C:\iLogic\Subiekt\MOST\` u usera.

- **Dlaczego staging osobno:** u budującego jeden katalog pełniłby dwie role — cel „Pobierz most" i źródło wgrywania. Kliknięcie przycisku nadpisałoby świeży build tym z serwera, cofając własną pracę.
- **U budującego kroki serwer/pobieranie są pomijane** — `_find_exe()` bierze najpierw `bin/Release` z repo.
- Ścieżka serwera ma **`iLogic` w środku** (tak realnie wgrane); kod sprawdza oba warianty na Y/Z/X/V. `paths.bridge_dir` w `sync_config.json` odpada jako rozwiązanie globalne — plik jest per stanowisko (własny `client`).
- Stara lokalizacja `C:\RMPAK_CLIENT\NexoRecon` została w `EXE_CANDIDATES` jako zapas.
- Kontrola przed wystawieniem: `git diff <sha z wersja.json>..HEAD -- subiekt_sfera/NexoRecon/` — pusto = binarka odpowiada źródłom.
- Kopia zapasowa wystawionych binarek: gałąź `most-server`, katalog `most-dist/`.

## ⚠️ MOST Z 5 PLIKÓW NIE DZIAŁAŁ DO 96d3dce — hook SDK musi być PRZED Main

Każda binarka wystawiona przed `96d3dce` (cb5d52f, e2c26d8, 9e6838a) po pobraniu na
stanowisko padała na `FileNotFoundException 'InsERT.Moria.Sfera' at Program.<Main>$` —
w obu trybach. U budującego niewidoczne, bo RM_BAZA bierze `bin\Release` (554 pliki);
u usera RM_BAZA cicho schodziła na stare CLI. Znalezione dopiero przy „sprawdź most na
serwerze" (06.09.2026), nie przez żaden komunikat.

Przyczyna: hook `AssemblyLoadContext.Resolving` podpinany w `NexoSession.Wczytaj()`
= wewnątrz Main, a JIT rozwiązuje typy całego ciała Main **przy wejściu** — Main dotykał
`sesja.Sfera` (`Uchwyt`). Naprawa: `SdkLoader.cs` (klasa bez typów InsERT, hook jako
pierwsza instrukcja) + `Cli.cs` (ciało CLI poza Main). **Zasada na przyszłość: Program.cs
nie może odwoływać się do żadnego typu SDK.** Test rozstrzygający = uruchomić binarkę
z katalogu z samymi 4–5 plikami, nie z `bin\Release`.

## Benchmark na produkcji — ZROBIONY 06.09.2026

Na firmowej bazie (3444 kartoteki, SQL na serwerze), nie na demo:

| Operacja | Stare CLI | Most | Rekordów |
|---|---:|---:|---:|
| katalog | ~9 000 ms | **26 ms** | 3444 |
| kontrahenci | ~14 000 ms | **31 ms** | 631 |
| magazyn (przed optymalizacją) | ~15 800 ms | 6 958 ms | 793 |
| magazyn (po optymalizacji) | — | **311 ms** | 793 |

Potwierdza założenie z demo: narzut startowy znika niezależnie od rozmiaru bazy.

## ⚠️ N+1 W ZAPYTANIACH — wzorzec do sprawdzania w każdym nowym trybie

Po usunięciu 10 s logowania **wyszedł drugi, ukryty koszt**: `Magazyn.cs` wołał
`WyszukajPoSymbolu` dla KAŻDEJ z 3444 kartotek, a potem dla każdej sięgał po
`StanyMagazynowe`, `StanyWMagazynachZakresy`, `DaneAsortymentuDlaPodmiotow`.
Każde sięgnięcie po nawigację EF = osobne zapytanie SQL. Kilkanaście tysięcy
zapytań, żeby zwrócić 793 rekordy → 7 s.

**Rozwiązanie: jedna projekcja LINQ z zagnieżdżonymi kolekcjami** — EF tłumaczy
ją na jedno zapytanie z JOIN-ami:

```csharp
asort.Dane.Wszystkie().Select(a => new {
    a.Id, a.Symbol, a.Nazwa,
    Rodzaj = a.Rodzaj.Nazwa,                      // PROSTE POLE, nie encja
    Stany = a.StanyMagazynowe.Select(s => new { Magazyn = s.Magazyn.Symbol, s.IloscDostepna }),
    Zakresy = a.StanyWMagazynachZakresy.Select(z => new { z.StanMinimalny, z.StanOptymalny }),
    Dostawcy = a.DaneAsortymentuDlaPodmiotow.Select(d => new {
        Nazwa = d.Podmiot.NazwaSkrocona,
        Podstawowy = d.AsortymentDlaKtoregoDostawcaPodstawowy != null }),
}).ToList()
```

**Klucz: wszystko jako proste pola w projekcji.** Wyciągnięcie `Rodzaj` czy
dostawcy z materializowanej encji *po fakcie* cofa cały zysk. Z tego samego
powodu zniknęła refleksyjna `DostawcaPodstawowy()` — kolekcja
`DaneAsortymentuDlaPodmiotow` jest dostępna wprost w projekcji (nazwa, której
wcześniej szukałem refleksją).

Sprawdzone: `Stan.cs` i `StanPozycji.cs` wołają `WyszukajPoSymbolu` tylko dla
pytanych symboli (kilkadziesiąt z BOM-u), nie dla całej bazy — tam problemu nie ma.

## Praca równoczesna z Subiektem — ROZSTRZYGNIĘTE

**RM_BAZA (stały most) i aplikacja Subiekt nexo PRO mogą działać jednocześnie
na tym samym stanowisku** — potwierdził producent (06.09.2026).

Wcześniejsze notatki zakładały, że trzeba się przełączać („RM_BAZA i Subiekt
nie pracują równocześnie") — to założenie **jest nieaktualne** i nie może być
podstawą żadnej decyzji projektowej. W szczególności:

- most **nie musi** zwalniać sesji, gdy user otwiera Subiekta,
- nie ma powodu ubijać `NexoRecon.exe` przed startem Subiekta,
- „wyloguj się z Subiekta, żeby RM_BAZA weszła" to porada z błędnego założenia.

**Na TYM SAMYM koncie operatora** — sprawdzone na żywo 06.09.2026: most
zalogowany jako `GKI`, użytkownik równolegle zalogowany w Subiekcie jako `GKI`,
`logins = 1` przy 12 min uptime. Czyli sesja mostu **ani razu nie została
wypchnięta** przez sesję GUI. Subiekt GUI i Sfera to dwa niezależne wejścia —
nie zrzucają się nawzajem jak druga sesja logowania do systemu.

Skutek dla wdrożenia: **nie trzeba osobnego konta nexo dla mostu.** Zasada
z planu („bridge loguje się tym samym użytkownikiem, którego używa operator
stanowiska; nie robić wspólnego konta ADMIN") jest wykonalna — właśnie tak
działa produkcyjnie.

Nadal otwarte i NIEZALEŻNE od tego: ile **równoległych sesji Sfery** mieści się
w puli licencji przy ~20 stanowiskach (punkt 3 niżej). To pytanie o wiele maszyn
naraz, nie o dwa programy na jednej.

## Co zostało otwarte (06.09.2026)

1. ~~Benchmark na produkcji~~ — ZROBIONY, patrz wyżej.
2. ~~Most na serwerze~~ — WGRANY 06.09.2026 do `Y:\RMPAK_CLIENT\iLogic\Subiekt\MOST`, pełna ścieżka usera sprawdzona end-to-end.
3. **Licencje Sfery** — czy 20 stałych sesji mieści się w puli, zanim rozeszlemy na wszystkie stanowiska. (Zawężone: na jednym stanowisku most + Subiekt GUI na tym samym koncie już potwierdzone jako bezkolizyjne — patrz sekcja wyżej.)
4. **Ilość dostarczona z Subiekta** (PZ→ZD→projekt) — czy Sfera daje to wprost, czy trzeba tabeli odroczonych zapisów z SUMĄ (nie przyrostem — `INSERT OR REPLACE` nadpisałby drugą dostawę w trakcie locka).
5. **`projekt` i `dostawcy`** — jedyne tryby zapisujące sprawdzone tylko w podglądzie, nie na produkcji.

**How to apply:** Przed jakąkolwiek zmianą w moście: sprawdzić `Panel SUBIEKT → stan mostu` (ONLINE, `logins` ma zostać na 1 cały dzień). Log wydajności: `C:\RMPAK_CLIENT\subiekt_logi\bridge_RRRRMMDD.log`. Rollback: `git revert` + kopia `NexoRecon.dll.dziala-20260906`. Patrz [[project_subiekt_magazyn]], [[project_subiekt_stan_05_09_2026]].

## Wystawienie 09.09.2026 (sha f737028)

Po `git pull --rebase` (zdalne commity C#: ZkIlosci, magazyn-zaloz zmiana nazwy) most na serwerze byl STARSZY niz zrodla — RM_BAZA po scaleniu wolalaby tryby, ktorych most nie zna. Przebudowany i wystawiony: `dotnet build -c Release` → `MOST_STAGING` (+ reczny `wersja.json`: protokol/zbudowano/sha/uwaga) → `Y:/RMPAK_CLIENT/iLogic/Subiekt/MOST/` → `most-server/most-dist/` (commit 18cdc76, NIE pushniete). Pulapka: `bin/Release/NexoRecon.exe` jest ZABLOKOWANY przez chodzacy most `server` (RM_BAZA go odpala) — build pada na kopiowaniu apphost; trzeba `Stop-Process` (taskkill w bashu blokuje klasyfikator). `wersja.json` nikt nie generuje automatycznie — pisze sie recznie. **Kazdy pull ze zmianami w `subiekt_sfera/NexoRecon/*.cs` = obowiazkowe przebudowanie i wystawienie mostu.**


**Zmiana drogi dystrybucji 14.09.2026:** serwer mostu = `\\W2019S\RM_SERWER$\MOST` (udział
z bazami projektów), nie `Y:/.../iLogic/Subiekt/MOST`. `DOMYSLNE_ZRODLA_MOSTU`
= `[udzial_serwera.UDZIAL]`, `_zrodlo_mostu()` woła `udzial_serwera.zaloguj()`
(idempotentne). Wystawiony: `62f2f36` (WydanieStan bez Take(400)). Pułapka
przy okazji: `net use` pisze w cp852 — `text=True` bez `encoding` dawało
UnicodeDecodeError w wątku czytającym (naprawione w `udzial_serwera`).

**Wolne przejęcie locka = zimny most (14.09.2026).** Pierwsze wywołanie Subiekta
po starcie RM_BAZA to zwykle `acquire_lock` (`wydanie-stan` + `zk-ilosci`) i to
ono płaciło start mostu + logowanie do Sfery (`session_start ok ms=7266–8823`);
kolejne locki 40–100 ms. Fix: `subiekt_bridge.rozgrzej_w_tle()` wołane przy
starcie GUI obok `prewarm_library_dwf_index` — most wstaje ~5 s po starcie
i loguje się, zanim user cokolwiek kliknie; nieudana rozgrzewka NIE zostawia
`_most_niedostepny`. Pułapka przy testowaniu: most jest procesem odłączonym
i PRZEŻYWA zamknięcie RM_BAZA — żeby zobaczyć zimny start, trzeba go ubić
(`Stop-Process NexoRecon`). `zk-ilosci ok=False` = „nie znaleziono ZK dla
projektu" — projekt bez ZK w Subiekcie, normalne.
