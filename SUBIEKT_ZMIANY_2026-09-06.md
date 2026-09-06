# Subiekt — przebudowa z 6 września 2026

Dzień pracy, w którym powstał stały most Sfery i zmieniło się wszystko, co
z niego korzysta. Ten plik zbiera **co się zmieniło, dlaczego i czego nie
wolno cofnąć**. Szczegóły samego mostu: `SUBIEKT_STALY_MOST_PLAN.md`.

Zakres: 36 commitów, `e3547ed..52d2296`.

---

## 1. Główna zmiana: stały most

**Było:** każde kliknięcie uruchamiało `NexoRecon.exe`, który logował się do
Sfery od zera. ~10 s narzutu na operację, niezależnie od tego, ile danych
faktycznie wracało.

**Jest:** `NexoRecon.exe server` startuje raz, loguje się raz i obsługuje
kolejne komendy przez tę samą sesję.

| Operacja | Stare CLI | Most |
|---|---:|---:|
| kontrahenci | 14 368 ms | **104 ms** |
| stan | 14 135 ms | **296 ms** |
| stan-pozycji | 13 951 ms | **233 ms** |
| magazyn | 14 218 ms | **753 ms** |
| dokumenty | 14 343 ms | **873 ms** |
| katalog (2. raz) | ~13 500 ms | **8–50 ms** |

Pomiary z bazy demo (M-OLD, 247 kartotek). W firmie liczby będą inne — 3444
kartoteki i SQL na serwerze — ale **narzut startowy znika niezależnie od
rozmiaru bazy**, a przez sieć zysk będzie większy niż lokalnie: logowanie do
Sfery to nie jedno zapytanie, tylko cała sekwencja.

### Architektura

```
RM_BAZA (Python)
    │  subiekt_bridge.call(...)
    │  TCP 127.0.0.1:51273, 4B długości LE + UTF-8 JSON
    ▼
NexoRecon.exe server
    │  wątek per klient → kolejka FIFO → JEDEN worker
    ▼
Sfera nexo → SQL
```

**Jeden worker na sesję**, bo obiekty Sfery nie są bezpieczne wielowątkowo.
Wątki TCP nigdy nie dotykają uchwytu — wkładają żądania do kolejki i czekają.

`ping` i `status` **omijają kolejkę**, więc odpowiadają także wtedy, gdy worker
mieli ciężki odczyt albo wisi na reconnect.

### Co powstało

| Plik | Rola |
|---|---|
| `subiekt_sfera/NexoRecon/NexoSession.cs` | cykl życia sesji: `Connect` / `Reconnect` / `CzyZywa` |
| `subiekt_sfera/NexoRecon/CommandDispatcher.cs` | mapa tryb → handler, wspólna dla CLI i servera |
| `subiekt_sfera/NexoRecon/ServerHost.cs` | TCP, kolejka, worker, log wydajności |
| `subiekt_sfera/NexoRecon/Rozpoznanie.cs` | domyślny tryb raportu (CLI-only) |
| `subiekt_bridge.py` | klient: `call`, autostart, fallback, aktualizacja binarki |
| `subiekt_sfera/bridge_test.py` | klient testowy, `python bridge_test.py bench` |
| `subiekt_panel.py` | panel narzędzi z kaflami |

**Handlery C# nie były zmieniane.** Server materializuje plik tymczasowy na
`--out` i przechwytuje `Console.Out`, więc kontrakt „plan z pliku, JSON do
pliku" został nienaruszony.

**Każdy moduł Pythona zachowuje starą ścieżkę CLI jako fallback** — awaria
mostu nie zatrzymuje pracy, tylko spowalnia.

---

## 2. Czego nie wolno cofnąć

### Zapisy nie są ponawiane automatycznie

Tryby zapisujące (`zd`, `kartoteka`, `projekt`, `rw`, `termin`, `zd-usun`,
`progi`, `dostawcy`, `symbole`, `kartoteka-usun`) po zerwanej sesji **nie są
powtarzane**. Wraca `UNKNOWN_COMMIT_STATE`, bo most nie wie, czy operacja
przeszła. Ślepe ponowienie to duplikat ZD albo kartoteki.

Wyjątek jest jeden i celowy: gdy sesja padła **przed** startem handlera
(wykryte w pre-checku), nic się nie wykonało — wtedy wraca `SESSION_LOST`
z `retryable=true` i Python ponawia raz. Ta gwarancja trzyma się tylko
dlatego, że `SESSION_LOST` wraca **wyłącznie** z pre-checku.

### `progi` łamie prostą regułę READ/WRITE

Bez `--plan` to odczyt, z planem zapis. Dlatego `CommandDispatcher.CzyZapis`
traktuje go osobno, zamiast wnioskować z flagi `--zapisz`.

### Nasłuch tylko na 127.0.0.1

Nigdy `IPAddress.Any`. Most nie ma prawa wyjść do LAN.

### Mutex per użytkownik Windows

`Local\RMPAK_NEXO_BRIDGE_<user>`, nie `Global\` — na terminalu kilka sesji
może mieć własne stanowiska.

---

## 3. Uśpienie komputera i restart SQL

Proces mostu przeżywa uśpienie, ale sesja Sfery — nie. Reconnect uruchamiany
dopiero po wyjątku miał dwie wady: wyjątek z martwej sesji potrafi przyjść po
timeoucie TCP (kilkadziesiąt sekund), a dla zapisu pad „gdzieś w handlerze"
jest niejednoznaczny.

Dlatego worker **sprawdza sesję przed handlerem**, gdy od ostatniej komendy
minęło ponad 60 s (`UpewnijSieZeSesjaZyje`):

| Sytuacja | Odpowiedź | Python |
|---|---|---|
| sesja żywa | komenda idzie normalnie | — |
| martwa, reconnect OK | komenda na nowej sesji (~15 s raz) | — |
| martwa, reconnect FAIL | `SESSION_LOST` — **nic nie ruszyło** | ponawia raz po 3 s |
| padła **w trakcie** zapisu | `UNKNOWN_COMMIT_STATE` | nigdy nie ponawia |

Próg 60 s: uśpienie trwa dłużej, klik-klik w oknie mieści się poniżej, więc
normalna praca nie płaci za sprawdzenie (kosztuje ~19 ms).

**Sprawdzone na żywo z zatrzymanym SQL Serverem:**

```
SQL stop  → session_check DEAD → reconnect_FAIL ×2 → SESSION_LOST
SQL start → session_check DEAD → reconnect_ok ms=7693 → dane po 8,5 s
```

Czas do błędu przy leżącym SQL: **~2 min** — `Polacz()` wisi ~45 s na timeoucie
sterownika, dwie próby. To timeout sterownika, nie mostu.

---

## 4. Dystrybucja binarki

**Userzy uruchamiają RM_BAZA z `.exe`** (PyInstaller) — nie mają Pythona,
źródeł `.cs` ani dotneta. Nie zbudują mostu u siebie.

Przycisk w panelu robi więc to, co ma sens w danym miejscu (rozstrzyga
`sys.frozen`):

| Gdzie | Przycisk | Co robi |
|---|---|---|
| ze źródeł (deweloper) | 🔨 Zbuduj teraz | `dotnet build` |
| z `.exe` (stanowiska) | ⬇ Pobierz most | kopiuje z serwera |

### Struktura `C:\iLogic\SUBIEKT`

```
Bin\                            1,1 GB  SDK Sfery (656 plików)
Narzedzia\                      5,5 MB  targets do budowania
MOST\                           590 KB  ← TO kopiujesz na serwer
    NexoRecon.exe, .dll, .deps.json, .runtimeconfig.json
    wersja.json                         protokół + data + sha
dotnet-sdk-8.0.424-win-x64.exe  216 MB  kompilator (tylko dla budującego)
CZYTAJ_TO.txt                           instrukcja
```

**`MOST`, nie `bin`** — `bin` to katalog bibliotek SDK Sfery w tym samym
folderze. Osobny podfolder, bo pobieranie z korzenia ciągnęłoby przez sieć
1,3 GB przy każdej aktualizacji, a SDK zmienia się tylko przy aktualizacji
nexo i wgrywa się na stanowisko **raz**.

### Ścieżka na serwerze

Szukana automatycznie pod **Y:, Z:, X:, V:** (`\RMPAK_CLIENT\Subiekt\MOST`),
bo ten sam zasób bywa zamapowany pod różnymi literami. Gdyby był gdzie
indziej — **Ustawienia → Konfiguracja ścieżek → „Folder mostu Subiekta"**
(zapisywane jako `paths.bridge_dir`). Puste = szukaj automatycznie.

`wersja.json` niesie numer protokołu. **Binarka niezgodna z klientem nie
zostanie skopiowana** — lepiej stary działający most niż nowy, który nie
rozumie zapytań.

---

## 5. Panel narzędzi zamiast menu

Menu podawało dziewięć nazw bez kontekstu: nie było widać, co czyta, a co
**zapisuje do produkcyjnej bazy**, ani ile jest do zamówienia.

Panel (lewy klik na „📦 SUBIEKT") pokazuje kafle w trzech obszarach, z
etykietą `ODCZYT` / `ZAPIS` i żywym licznikiem:

```
Stany projektu    34 pozycji w projekcie
Magazyn           27 kartotek ze stanem
Zamówienia ZD     15 pozycji do zamówienia · 37 już zamówionych
Dokumenty         28 dokumentów · 4 ZD do realizacji
```

Liczniki są możliwe **dopiero od stałego mostu** — wcześniej każdy kosztowałby
~10 s. Liczą się w tle, panel otwiera się natychmiast (~1,8 s do pełnych
danych).

**Trójkąt ostrzegawczy tylko przy operacjach nieodwracalnych** (Załóż projekt,
Nowa kartoteka). Gdyby miały go wszystkie zapisy, nie znaczyłby nic — „Powiąż
dostawców" cofa się jednym kliknięciem, a scalanie robi backup.

Nagłówek niesie **stan mostu z liczbą logowań** (`logins > 1` = sesja wstawała
ponownie; inaczej restarty dzieją się po cichu).

**Stare menu zostaje pod prawym klawiszem.**

---

## 6. Wysyłka ZD — cztery poprawki

### Otwarcie draftu ≠ wysłanie

Program zapisywał ślad wysyłki i oznaczał pozycje jako ZAMÓWIONE **zaraz po
otwarciu wiadomości w Outlooku**. Wystarczyło zamknąć okno bez kliknięcia
Wyślij, żeby ZD wyglądało na wysłane, a pozycje na zamówione.

```
było:  otwarcie draftu → wysłano + zamówiono
jest:  otwarcie draftu → przygotowano
       potwierdzenie   → wysłano + zamówiono
```

Odrzucona alternatywa: wykrycie zdarzenia `Send` przez Outlook COM. Byłoby bez
pytania, ale kruche — `mailto` takiego zdarzenia nie ma, a Outlook bywa
zablokowany polityką. Człowiek i tak fizycznie klika Wyślij.

**Zapis terminu zostaje przed otwarciem maila** i to jest słuszne: user ma się
dowiedzieć o nieudanym zapisie, zanim obieca dostawcy termin, którego ZD nie
zna.

### Jeden zły załącznik nie przewraca wysyłki

Cały blok Outlooka — `Dispatch`, nagłówki, treść **i pętla załączników** —
siedział w jednym `try`. Jeden plik, którego `Attachments.Add` nie przyjmuje
(zajęty, ścieżka UNC, dziwna nazwa), gubił Outlooka, formatowanie i wszystkie
załączniki naraz; wysyłka spadała na `mailto:` z zakodowanym URL-em.

Teraz każdy załącznik ma własny `try`, a odrzucone wracają jako lista i okno
pokazuje je z nazwami.

### Treść i podpis

Lista pozycji **usunięta z treści** — przy kilkunastu pozycjach zalewała maila,
a komplet jest w załączonym PDF-ie.

Podpis niesie **imię, nazwisko, e-mail i telefon** z tego samego źródła co
zapytanie ofertowe (`employees` w `rm_manager.sqlite`). Wcześniej stało tam
samo `display_name` z `master.sqlite`, czyli u części kont po prostu „ADMIN".

> ⚠️ `employees` siedzi w **rm_manager.sqlite**, nie w `master.sqlite` — tam są
> tylko `users` do logowania.

### Odświeżanie po wysyłce

Przegląd dokumentów odświeża listę po **potwierdzonej** wysyłce. Okno Zamówień
celowo bez tego: jego lista to zapotrzebowanie, a przeładowanie skasowałoby
zaznaczenia potrzebne do kolejnego ZD.

---

## 7. Okno „Załóż projekt" — ostrzeżenia

### Rozjazd numerów RM_BAZA ↔ drzewko

Skład kompletu powstaje ze złączenia **dwóch źródeł**: typ Z/ZZ i numery z bazy
projektu, a „co wchodzi w co" z arkusza `DRZEWKO TEKST` w pliku `*_OUT.xlsx`
na V:. Złączenie idzie **wyłącznie po numerze rysunku**.

Gdy numer się rozjedzie, składnik wypadał po cichu — komplet powstawał
**niepełny**, ale ze statusem „utworzony". Teraz okno pokazuje pełną listę
z podziałem na przyczyny:

| Przyczyna | Co zrobić |
|---|---|
| **ukryta** — jest w projekcie, tylko schowana | odkryj w arkuszu |
| **nieznana** — nie ma jej pod tym numerem | popraw w Inventorze, przeimportuj |

Lista jest kopiowalna (TSV do Excela) i niesie nazwy, nie same numery.

### Brak drzewka

Gdy drzewko się nie wczyta (brak folderu na V:, brak arkusza), **nie powstaje
żaden komplet** — pozycje Z/ZZ dostają `pominiety-brak-skladnikow`. Powód był
raportowany tylko w pasku statusu, gdzie ginął; teraz trafia do potwierdzenia
zapisu.

### Potwierdzenie zapisu

Rozdziela **trwałe** (kartoteki, komplety — zostają w Subiekcie) od
**odwracalnego** (ZK — da się usunąć). Gdy nic trwałego nie powstaje, mówi to
wprost zamiast wypisywać zera.

---

## 8. Znalezione przy okazji

Błędy, które istniały wcześniej i wyszły podczas pracy:

**`RuntimeBinderException` w RW.** `RozchodWewnetrznyBO` nie ma `PodajBledy()`.
Kod pytał o przyczynę odrzucenia zapisu i sam się wywalał, **przykrywając
prawdziwy powód**. Wywołanie wyglądało na zabezpieczone (`Bezp(rw.PodajBledy)`
ma try/catch), ale konwersja `dynamic → Func` leci **przed** wejściem do
`Bezp`.

**Pole `zapisano` kłamało.** Mówiło „czy proszono o zapis", nie „czy się udał"
— odrzucone RW raportowało `zapisano: true` przy `numer: null`.

**Legenda z emoji.** Okno Stany liczyło kategorie symbolami (✅ ⚠ ❌), a tabela
koduje status **kolorem tła wiersza**. Nie dało się powiązać jednego z drugim.

**Wyciek `%TEMP%`.** 185 katalogów po trzech dniach. Dwie przyczyny: moduły
tworzą `mkdtemp` i nie sprzątają (16 miejsc), a most zostawiał katalog
`plan.json` przy **każdej** komendzie z planem. Most naprawiony u źródła
(jeden katalog na żądanie, kasowany w `finally`), moduły — sprzątaniem
starszych niż doba przy starcie mostu.

**Klasa `ZamowieniaWindow` rozbita na pół.** Wyciągając funkcję do poziomu
modułu wstawiłem ją w środek klasy — 22 metody wypadły poza nią, `_build_ui`
wywalało się przed `_load_async` i okno nigdy nie ładowało danych.

---

## 9. Pułapki, o których trzeba pamiętać

**`DETACHED_PROCESS` zabijał most.** Bez konsoli `Console.OutputEncoding`
rzuca `IOException` i proces ginął z `0xE0434352`, **zanim cokolwiek
zalogował**. Ręcznie z konsoli działał bez zarzutu. Dlatego każdy komunikat
w `ServerHost` idzie przez `Powiedz()`, które zawsze pisze też do logu.

**Most trzyma plik `NexoRecon.exe`.** Przed `dotnet build` trzeba go
zatrzymać, inaczej `MSB3027 „plik jest zablokowany"`. Przycisk „Zbuduj teraz"
robi to sam.

**Brak builda po `git pull` jest niewidoczny.** Stara binarka nie zna trybu
`server`, ale **nie zgłasza błędu** — traktuje go jak brak trybu i wypisuje
raport rozpoznawczy do niewidocznego okna, kończąc kodem 0. Python schodzi na
fallback CLI i wszystko działa, tylko wolno. Dlatego RM_BAZA sprawdza datę
binarki wobec `ServerHost.cs` i pokazuje okienko z przyciskiem.

**Kolizja nazw `Magazyn`.** Encja SDK vs handler `Magazyn.cs` — wewnątrz
`namespace NexoRecon` wygrywa handler. `Rozpoznanie.cs` używa aliasu
`MagazynSfera`.

**Panel i okno konkurują o jedną kolejkę.** Skutek uboczny stałego mostu:
wątek liczący liczniki potrafi trzymać most zajęty, a wtedy okno otwarte
kliknięciem czeka i wygląda, jakby się nie ładowało. Wątek sprawdza znacznik
`_przerwane` między zapytaniami. Przy starym CLI problem by nie wystąpił — za
cenę 10 s na operację.

---

## 10. Wieloużytkownikowość

Środowisko: **każdy user na swoim PC, każdy z własnym kontem nexo** — czyli
założenie z sekcji 2 planu. Port 51273 i mutex są lokalne, więc stanowiska
sobie nie przeszkadzają.

Dwa ryzyka specyficzne dla stałej sesji zostały sprawdzone:

1. **Czy długożyjąca sesja widzi zmiany innych?** TAK. Sesja z 17-minutowym
   uptime natychmiast zobaczyła RW wystawione przez inny proces (257 → 256).
   Sfera nie cachuje stanów. To był największy nierozpoznany problem — gdyby
   cachowała, ludzie widzieliby nieaktualne stany cały dzień.
2. **Wyścig o tę samą pozycję?** Subiekt odrzuca RW ponad dostępny stan.
   Drugi user dostaje odmowę, nie ujemny stan.

**Gdzie leżą realne limity:** licencje Sfery (20 stałych sesji zamiast krótkich
— do sprawdzenia przed rozesłaniem), blokady numeracji dokumentów przy
równoczesnych zapisach, wersja SQL Server (Express: 1 rdzeń, 1,4 GB RAM,
10 GB bazy).

**Uwaga o terminalu:** gdyby kilku userów pracowało na jednej maszynie (RDP),
stały port 51273 byłby konfliktem. Przy PC per user problemu nie ma.

---

## 11. Wdrożenie

### Nowe stanowisko

1. Skopiuj `C:\iLogic\SUBIEKT` (SDK Sfery + instalka .NET + `MOST\`)
2. Zainstaluj .NET SDK, jeśli `dotnet --version` nie działa *(tylko tam, gdzie budujesz)*
3. Sprawdź, że `.nexo_sfera.json` ma konto **tego** operatora i **serwer**, nie `localhost`
4. Uruchom RM_BAZA → panel SUBIEKT → „Pobierz most"

### Aktualizacja mostu

**U budującego:** `git pull` → „Zbuduj teraz" → skopiuj `bin\Release\*` do
`C:\iLogic\SUBIEKT\MOST\` → zaktualizuj `wersja.json` → wgraj `MOST\` na serwer.

**U userów:** panel SUBIEKT → „Pobierz most".

### Kontrola

```
Panel SUBIEKT → stan mostu: ONLINE, „Logowań do Sfery: 1"
Log: C:\RMPAK_CLIENT\subiekt_logi\bridge_RRRRMMDD.log
```

`logins` ma zostać na `1` przez cały dzień pracy.

### Powrót

```
git revert <commit>
```
plus kopia binarki `NexoRecon.dll.dziala-20260906` w `bin/Release`.

---

## 12. Co zostało

- **Benchmark w firmie** (sekcja 33 planu) — na 3444 kartotekach i SQL na
  serwerze. Rozstrzygnie, czy cache jest potrzebny; na demo wygląda, że nie.
- **Licencje Sfery** — czy 20 stałych sesji mieści się w tym, co macie.
- **Ilość dostarczona z Subiekta** — czy Sfera daje powiązanie PZ → ZD →
  projekt. Jeśli tak, można czytać wprost i nie potrzeba tabeli odroczonych
  zapisów. Jeśli nie — tabela musi trzymać **wartość łączną, nie przyrost**,
  bo `INSERT OR REPLACE` nadpisuje i druga dostawa w trakcie locka
  skasowałaby pierwszą.
- **`projekt` i `dostawcy`** — jedyne tryby zapisujące sprawdzone tylko
  w trybie podglądu.
