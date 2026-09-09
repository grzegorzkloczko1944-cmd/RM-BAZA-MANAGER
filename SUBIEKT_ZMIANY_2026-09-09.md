# Subiekt — zmiany 09.09.2026

Dzień o jednym temacie: **kto jest właścicielem ilości** na dokumencie ZK.
Zaczęło się od incydentu (BOM rozjechał się z ZK, a system o tym milczał),
skończyło na działającej edycji ilości z okna Projekt / Aktualizacja.

Poprzedni dzień: [SUBIEKT_ZMIANY_2026-09-08.md](SUBIEKT_ZMIANY_2026-09-08.md).
Analiza problemu i decyzje: [ANALIZA_ZK_DWA_ZRODLA_PRAWDY.md](ANALIZA_ZK_DWA_ZRODLA_PRAWDY.md).

---

## 1. Punkt wyjścia: dwa źródła prawdy

Użytkownik dołożył BOM (`2627-650.11ZZ Transporterek_OUT.xlsx`), RM_BAZA
zsumowała ilości, a okno potwierdzenia pokazało **„25 BEZ ZMIAN"** i
„dopisze 0 poz.". Zapis nie przeniósł niczego. Cytat:

> „cała zmiana przebiega po cichu. USER nawet nie wie co zrobił"

Przyczyna była w moście: `naZk` to był `HashSet<string>` **samych symbolów**,
więc 4 i 10 były dla niego tym samym stanem. Zapis pomijał istniejące pozycje
(`if (juzNaZk.Contains(...)) continue;`) — robił rzecz słuszną („nie dublujmy"),
ale z zupełnie złego powodu i bez słowa.

Diagnoza użytkownika przecięła szukanie winnego w arytmetyce:

> „o kurwa, mam dwa źródła prawdy"

---

## 2. Model docelowy — likwidacja drugiego źródła

Zamiast uzgadniać dwa stany, **usuwamy drugi**. Rozjazd nie jest rozwiązywany —
przestaje być możliwy.

- **„Ilość BOM"** — wartość konstrukcyjna, własność RM_BAZA / Inventora.
- **„Ilość (zam.)"** — wartość dokumentowa, **własność Subiekta**.

To nie są dwie kopie tej samej liczby, tylko dwie różne informacje. Rozjazd
między nimi nie jest błędem: BOM mówi, ile wynika z konstrukcji, ZK — ile
faktycznie zamówiono.

> Model „RM_BAZA po zasiewie tylko czyta" był wcześniej **umową**, której nic
> nie egzekwowało. Blokada zamienia ją we właściwość systemu.

Pełne uzasadnienie, warianty odrzucone i pytania otwarte:
[ANALIZA_ZK_DWA_ZRODLA_PRAWDY.md](ANALIZA_ZK_DWA_ZRODLA_PRAWDY.md).

---

## 3. Co weszło do kodu

### 3.1. Most widzi ilości, nie tylko symbole

`CzytajPozycjeZk()` zwraca `{symbol → ilość}` (typ `PozycjaDokumentu`, sumuje
powtórzony symbol). Nowy rodzaj kroku `zk-poz` ze statusami:

| Status | Kiedy |
|---|---|
| `do-uzupelnienia` / `do-zmniejszenia` | suchy przebieg — co zapis zrobi |
| `ilosc-uzupelniona` / `ilosc-zmniejszona` | po zapisie — co zrobił |
| `roznica-ilosci-pominieta` | rozjazd, którego zapis nie tknął |

Status `bez-zmian` przestał kłamać: przy rozjeździe mówi wprost, ile pozycji
ma inną ilość niż BOM.

### 3.2. Blokada klucza po zasiewie

Kolumny `subiekt_symbol` i `subiekt_zasiew_at` w tabeli `items` (migracja
`_migrate_project_schema`). Stawia je `subiekt_projekt.zapisz_zasiew()` po
udanym zapisie.

Pozycja, która ma kartotekę w Subiekcie, nie pozwala zmienić **klucza
dopasowania** — bo zmiana rozspójniłaby powiązanie i przy kolejnym zasiewie
powstałby **duplikat kartoteki**:

| Rodzaj pozycji | Klucz | Co zablokowane |
|---|---|---|
| z numerem rysunku | numer rysunku | numer (nazwa zostaje — to opis) |
| **znormalizowana** | symbol z nazwy | **nazwa** (z niej powstaje symbol) |

> Ślad musi być **trwały**: słownik w pamięci znika po restarcie i nie byłoby
> z czego odtworzyć blokady.

### 3.3. Cache ilości — dla stanowisk BEZ Subiekta

Nie każdy ma dostęp do Subiekta. **Cache'em jest PLIK PROJEKTU**: stanowisko
z mostem odświeża „Ilość (zam.)" i zapisuje, reszta czyta zwykły plik z dysku
sieciowego i pracuje jak dotąd.

- nowy tryb mostu **`zk-ilosci`** (`ZkIlosci.cs`) — czysty odczyt ilości z ZK,
- `_zapisz_ilosci_z_subiekta()` wołane **przy BRANIU locka** (nie przy
  zwalnianiu: tam user czeka na zakończenie pracy, a tu i tak czeka na
  wczytanie projektu),
- brak mostu **nie blokuje** pracy — `_find_exe()` sprawdzane przed próbą,
  więc stanowisko bez Subiekta nie czeka ~19 s na proces, który nie wstanie.

> **Wydajność:** odczyt MUSI iść przez stały most. Pomiar: zimny start
> **18,6 s**, ciepły most **0,3 s**.

### 3.4. Edycja ilości w oknie Projekt / Aktualizacja

Dwuklik w kolumnę „Ilość" → wpisujesz **ilość docelową** (nie mnożnik).

- **złożenie (KT)** — przelicza **całe swoje poddrzewo** kaskadowo
  (`ilosci_z_drzewa`, rekurencja z ochroną przed cyklem),
- **główne złożenie** — zablokowane (jego ilość to liczba budowanych maszyn),
- **detal wewnątrz złożenia** — zablokowany, ilość wynika z rodzica,
- **pozycja spoza drzewa** — ustawiana pojedynczo.

Skład czytany **z SUBIEKTA** (`drzewo_z_subiekta`, tryb mostu `komplet`),
nie z pliku OUT: projekt zakładamy z OUT, ale po zasiewie właścicielem
struktury jest Subiekt.

Ilości w oknie startują z **żywego ZK**, nie z arkusza (`bazowe_ilosci`).
Precedencja: **BOM < ZK < edycja usera**.

### 3.5. Zapis ilości — trzy rzeczy MUSZĄ być razem

Najtrudniejsza część dnia. `Zapisz()` zwracał `true`, raport mówił „ustawiono 1",
a dokument zostawał na 2. Trzy niezależne przyczyny naraz:

1. **`UstawIlosc` to metoda ROZSZERZAJĄCA** (`PozycjaExtensions.UstawIlosc(PozycjaDokumentu, decimal)`,
   statyczna) — szukanie jej na instancji trafiało w co innego.
2. **`ob.Przelicz()` przed `ob.Zapisz()`** — bez tego zmiana się nie utrwala
   (tak robi przykład SDK `FakturowanieWydan.cs`).
3. **Konsolidacja wierszy** — ten sam symbol bywał na ZK w **kilku wierszach**
   (pozostałość po wcześniejszej wersji „dopisz różnicę"). Ustawienie tylko
   pierwszego nie zmieniało sumy. Teraz: pierwszy := ilość docelowa, reszta
   wyzerowana (`Usun` na kolekcji pozycji **nie istnieje**).

Diagnostyka pokazała `przed=1` przy sumie 2 — dopiero to naprowadziło na
zdublowane wiersze, zamiast czwartej rundy zgadywania.

> ⚠️ **Skutek uboczny:** `ZK 1/CENTRALA/2026` ma ~20 wierszy z ilością **0**
> (te zdublowane, wyzerowane). Sumy się zgadzają, ale w GUI Subiekta widać
> puste wiersze — do ręcznego wyczyszczenia. Przy nowych projektach to nie powstanie.

### 3.6. Kolumna „Typ / Źródło" w arkuszu

Nowa kolumna (indeks 22, **doklejona na końcu** — indeksy 0-21 są zaszyte
w kilkunastu miejscach kodu). Pokazuje rolę pozycji: `KT` / `TW` /
`Składnik KT <symbol>`. Liczona z drzewka projektu, cache per projekt
(odczyt z dysku sieciowego).

---

## 4. Wariant 1 — ODRZUCONY po testach

Rozważaliśmy, żeby na ZK szedł **sam komplet**, bez płaskich składników
(zgodnie z tym, jak Subiekt jest zaprojektowany). Nowy tryb diagnostyczny
**`zapotrzebowanie-test`** (`ZapotrzebowanieTest.cs`, czysty odczyt) rozstrzygnął:

- `ZapotrzebowanieNaAsortyment()` **NIE rozwija kompletów** — zwróciła 209
  pozycji, w tym **26 KOMPLETÓW**. Czyli zapotrzebowanie na części stoi
  **wyłącznie na płaskich wierszach TW**, które most dopisuje obok kompletu.
- `IKalkulatorZapotrzebowania` (jedyna alternatywa, z `ObslugaKompletow =
  ZamowSkladniki`) **jest nieosiągalny ze Sfery**:
  `InvalidOperationException: IInjectionScope ... cannot be constructed`.
- Zagnieżdżenia są realne: **6 z 28** kompletów zawiera inny komplet.

**Wniosek:** usunięcie składników z ZK wyzerowałoby zapotrzebowanie, nie dając
nic w zamian. Struktura ZK zostaje bez zmian.

> Dowiedzieliśmy się tego **testem za darmo**, zamiast odkryć brak
> zapotrzebowania na produkcji. Tryb zostaje w moście — przyda się, gdyby
> nowa wersja Sfery udostępniła kalkulator.

---

## 5. GUI — rzeczy, które psuły pracę

### 5.1. Okna na złym monitorze

**`messagebox` to natywny dialog Tk** — sam ustala pozycję względem monitora
GŁÓWNEGO, a `parent=` tego **nie zmienia**. Stanowisko ma trzy monitory
(pulpit od `x=-2560` do `x=2560`), więc komunikat z okna na bocznym ekranie
wyskakiwał na środkowym.

Nowa funkcja `subiekt_projekt.komunikat(rodzic, tytul, tresc, rodzaj, pytanie)`
— własne okno z `wysrodkuj()`. Podmienione **wszystkie 22 wywołania**
w `subiekt_projekt.py`, plus import w Edytorze kartotek.

Test: rodzic na `x=-1792`, komunikat na `x=-1506` — ten sam monitor.

### 5.2. Drzewko żyjące własnym życiem

> „porozwijałem drzewka to tak mają zostać a nie żyją swoim życiem"

Pierwsze podejście (odtwarzanie rozwinięć po ścieżkach symboli) było
**przekombinowane**: po zmianie ilości pozycja może zniknąć z planu albo
zmienić rodzica, więc część ścieżek nie pasowała.

Teraz zapamiętujemy **decyzję**, nie stan: klikasz „⊞ Rozwiń wszystko"
i drzewko zostaje rozwinięte po każdej przebudowie.

### 5.3. Raport po zapisie jak okno potwierdzenia

Wąski `messagebox` urywał listę na 12 pozycjach („… i 8 więcej"), więc tego,
co się faktycznie zmieniło, nie dało się doczytać bez zaglądania do logu.
`_okno_raportu()` — kafelki z licznikami + tabela pozycja po pozycji,
nagłówek zielony albo czerwony.

---

## 6. Edytor kartotek

- **Przycisk „Z pliku…"** (dawniej „Z projektu…" — była to zaślepka bez
  implementacji). Dwa formaty, z ważnym rozróżnieniem:

  | Format | Matka |
  |---|---|
  | **CSV** (płaskie złożenie) | **dodawana z nazwy pliku** — w wierszach jej nie ma |
  | **XLSX** (`*_OUT.xlsx`, drzewko) | **już jest w środku**, wychodzi jako korzeń |

  Wczytanie **dokłada** do istniejącej struktury — można złożyć całość
  z kilku plików.

- **Pole „Położenie"** (regał / półka) na karcie **Podstawowe**, obok
  Symbol/Nazwa/Rodzaj. To **ta sama zmienna** co pole na karcie Magazyn —
  wpis w jednym miejscu widać w drugim.

- **Fokus przy nowej pozycji na NAZWĘ**, nie na symbol: symbol ma już wartość
  roboczą („NOWA-01") i nadaje się go przyciskiem „Auto" **z nazwy**.

---

## 7. Pułapki, które kosztowały czas

- **`print` pod `pythonw.exe` przepada** — nie ma konsoli. Cichy `except`
  z samym `print` znaczy, że błąd znika bez śladu (tak przepadł pierwszy zapis
  znacznika zasiewu). Stąd `_log_techniczny()` → `C:\RMPAK_CLIENT\subiekt_logi\subiekt_projekt.log`.
- **Stały most czyta listę symboli z klucza `symbols`**, nie `symbole`
  (`ServerHost.cs:375`).
- **`Treeview` z `show="tree headings"`** — numeracja `identify_column` myli;
  porównywać po NAZWIE kolumny (`tree.column(kol, "id")`).
- **Read-back po zapisie robić ze ŚWIEŻEGO procesu** (`NexoRecon.exe zk-ilosci`),
  nie przez stały most — najpierw wykluczyć cache jednej sesji Sfery.
- **„Pusty raport" bywa poprawny.** Dwa razy zgłoszony jako błąd, a za każdym
  razem plan był identyczny z ZK. Diagnoza: log zapisu
  (`subiekt_historia/projekt_<id>_*.json`) + read-back ZK.

---

## 8. Pliki

| Plik | Co |
|---|---|
| `subiekt_projekt.py` | edycja ilości w oknie, `komunikat()`, `pobierz_ilosci_zk`, `drzewo_z_subiekta`, `zapisz_zasiew`, okno raportu |
| `RM_BAZA_v15_MAG_STATS_ORG.py` | blokada klucza i „Ilość (zam.)", cache ilości przy locku, kolumna „Typ / Źródło", migracja schematu |
| `subiekt_edytor_gui.py` | „Z pliku…" (CSV/XLSX), pole Położenie, fokus na nazwę |
| `subiekt_sfera/NexoRecon/Projekt.cs` | `UstawIlosc` + `Przelicz()` + konsolidacja wierszy, `CzytajPozycjeZk` |
| `subiekt_sfera/NexoRecon/ZkIlosci.cs` | **nowy** tryb `zk-ilosci` — odczyt ilości z ZK |
| `subiekt_sfera/NexoRecon/ZapotrzebowanieTest.cs` | **nowy** tryb `zapotrzebowanie-test` — diagnostyka kompletów |
| `ANALIZA_ZK_DWA_ZRODLA_PRAWDY.md` | **nowy** — analiza problemu, warianty, decyzje |

> Po zmianach w moście: `dotnet build -c Release`. Uwaga: `_find_exe()` sprawdza
> **`bin/Release`** jako pierwszy — build Debug nie wystarczy.

---
---

# Część druga — dzień roboczy (13:00–20:33)

Powyższa część opisuje pracę nocną (do 04:03). Reszta dnia poszła w innym
kierunku: zaczęła się od zgłoszenia „nie mam połączenia z RM_BAZA", a
skończyła na trzecim etapie pracy z elementami handlowymi.

Kolejność chronologiczna, bo jedno wynikało z drugiego.

---

## 9. „Nie mam połączenia" — diagnoza, która wykluczyła oczywiste

Zgłoszenie: RM_BAZA traci połączenie, podejrzenie o RM_TRAY „siejący" w LAN.

Zmierzone, **nie zgadnięte**:

| Podejrzany | Werdykt |
|---|---|
| RM_TRAY sieje w sieci | **nie** — zero socketów/HTTP, tylko SMB; timery 500 ms i 2 s są lokalne, skan chatu co 10 s to 25 plików = 3 ms |
| sieć / SMB | **zdrowa** — 0 zdarzeń w dzienniku SMB przez 48 h, ping do `nic` 1–5 ms, master otwiera się w 16 ms |
| podwójne procesy RM_BAZA i RM_TRAY | **nie duplikaty** — PyInstaller onefile (bootloader 2 MB + właściwy proces 70/99 MB), potwierdzone przez `_MEI*` i `runtime_tmpdir=None` |
| `journal_mode=delete` na masterze | **zamierzone** — WAL po SMB się rozpada; journal i chwilowy lock to normalne zachowanie |

Prawdziwe przyczyny były dwie i obie inne, niż zakładano — patrz niżej.

> **Wniosek:** przy „nie ma połączenia" najpierw dziennik SMB i log mostu,
> dopiero potem kod. Trzy z czterech hipotez odpadły w 10 minut.

---

## 10. Crash `0xc0000005` — `close()` na dzielonym połączeniu

Cztery twarde crashe w ciągu dnia (dumpy w `%LOCALAPPDATA%\CrashDumps`,
Event Log 1000, moduł `sqlite3.dll` / `python314.dll`) — bez wyjątku Pythona,
więc niewidoczne w logach aplikacji.

**Mechanizm.** Wszystkie połączenia mają `check_same_thread=False`, a
`master_con` dzieli ~20 wątków. `_safe_ensure_master_alive` odpala watchdoga
w wątku z timeoutem **3 s**, ale reconnect ma `busy_timeout` **5 s**. Przy
locku GUI porzuca wątek i pracuje dalej, a porzucony wątek 2 s później
**zamyka to samo połączenie** → use-after-free w SQLite.

**Naprawa:** `_retire_master_con()` / `_retire_project_con()` — zrzucenie
referencji **bez `close()`**. CPython zamknie połączenie, gdy ostatni wątek
przestanie go używać, we własnym wątku. Podmienione 5 miejsc w managerze
i 4 w GUI; reconnect pod nieblokującą blokadą.

Test: 6 wątków SELECT + wątek retire/connect + watchdog przez 6 s →
**4830 odczytów, 0 błędów, brak AV**.

> **Zasada:** nigdy `master_con.close()` / `project_con.close()` poza
> `close_all()` i świadomym zamknięciem projektu.

---

## 11. Bramka wersji `.exe` i sesje klientów

Userzy pracowali na binarkach sprzed naprawy watchdoga (07.09, `2cf4473`).
Przy `journal_mode=delete` jeden taki klient blokuje mastera wszystkim,
a sam ścina się do READ-ONLY. Nie było jak sprawdzić, kto na czym siedzi.

**`client_version.py` (nowy)** — dwa mechanizmy:

* **Bramka startu.** Porównanie własnego `.exe` z wzorcem na
  `Y:/RMPAK_CLIENT/` (rozmiar + mtime, nie hash — 127 MB przez SMB przy
  każdym starcie to za dużo). Przestarzały → dialog z samo-aktualizacją
  (rename działającego `.exe` na `.old`, `copy2`, rollback przy błędzie).
  **Nie blokuje:** pracy ze źródeł, buildu deweloperskiego nowszego niż
  serwerowy, braku wzorca, `ui.version_gate=false`.
* **Heartbeat sesji.** Tabela `client_sessions` w masterze (host, user,
  build, PID, `last_seen`), UPSERT w istniejącym ticku heartbeatu locków.
  **Własne krótkie połączenie**, nigdy `master_con` — tick chodzi w wątku
  roboczym. Okno: Narzędzia → „Sesje klientów".

**Efekt tego samego dnia:** o 13:13 ośmiu użytkowników pobrało nową wersję
i pokazało się w tabeli z identycznym `build_id`.

Spec (`RM_BAZA_v15_MAG.spec`) dostał **automatyczną publikację** na
`Y:/RMPAK_CLIENT/` po każdym buildzie: poprzednia wersja → `backup dd-mm-rrrr`,
`copy2` (mtime musi przetrwać — bramka na nim polega), kontrola rozmiaru.

---

## 12. Wydajność okna Projekt / Aktualizacja — 20x

Zgłoszenie „wczytuje w chuj czasu". Pomiary funkcji pokazywały ~1 s i
**rozjeżdżały się z rzeczywistością** — rozstrzygnął dopiero profil `py-spy`
z żywej sesji.

### 12.1. Mapowania: 37 s → 0 s

`py-spy` wskazał `subiekt_mapowania.py:189` — **37–41 s w każdym wątku
`_dry_run_worker`**, przy 0,5 s na całą odpowiedź mostu.

Po każdym podglądzie leciało `put_many` z 354 wpisami postaci
**`symbol → ten sam symbol`**, a baza mapowań leży na `Y:` w trybie
`DELETE`. W tabeli 830 wierszy, z czego **702 to takie puste pary**
przepisywane w kółko.

Pytanie użytkownika rozstrzygnęło to lepiej niż optymalizacja:

> „a na chuj? nie wystarczy wczytać dokładnie tych komórek co trzeba?"

Zapisujemy teraz **tylko kartoteki świeżo założone**; `put_many` robi
jedno połączenie i jeden commit (było: `put()` w pętli, czyli `makedirs` +
`connect` + 3x PRAGMA + SELECT + INSERT + commit + close **na każdy wpis**).

### 12.2. Most: podgląd 12,3 s → 0,6 s, zapis 13,2 s → 3,5 s

Trzy razy ten sam wzorzec — pytanie Sfery w pętli, choć odpowiedź już była
w pamięci:

| Co | Ile zapytań | Naprawa |
|---|---|---|
| skład kompletów w podglądzie | 49 x `asort.Znajdz()` | jeden przelot LINQ (wzorzec z `Komplet.cs`) |
| „czy kartoteka istnieje" | 354 + składniki x `WyszukajPoSymbolu()` | odczyt z mapy `luzne` |
| symbol pozycji przy budowie ZK | 354 x `Znajdz()` | `RealnySymbol()` z mapy |

Do tego zapis **przepisywał skład 49 kompletów, które się nie zmieniły** —
choć podgląd już to wiedział i pisał „skład identyczny". Porównanie
wyniesione do wspólnego `SkladTakiSam()`.

Wynik porównany **krok po kroku** ze starym mostem: 405 kroków, identyczne.

---

## 13. Most a aktualizacja Subiekta — awaria i naprawa u źródła

Po uruchomieniu Subiekta baza zaktualizowała się do **61.1.1.9471**, a most
miał biblioteki **61.1.0.9431**. Sfera odmawia połączenia przy różnicy wersji,
więc most startował, odpowiadał na `ping`, ale **nigdy nie osiągał `ready`**.
Objaw: przejęcie locka wisiało (stos: `_czekaj_na_gotowosc` ← `pobierz_ilosci_zk`
← `acquire_lock`, w wątku GUI).

Na maszynie były **trzy kopie bibliotek, wszystkie stare**: `bin/Release`
(06.09), `C:\iLogic\Subiekt\Bin` (06.09), dokumentacja SDK z konfigu (04.08).

**Naprawa (wybrany wariant „a"):**

1. **Most nie wozi już własnych bibliotek** — `InsERT.*` usunięte z
   `ReferenceCopyLocalPaths`. To było kluczowe i nieoczywiste: .NET ładuje
   bibliotekę z katalogu aplikacji **zanim** odezwie się hook
   `AssemblyLoadContext.Resolving`, więc żadne wykrywanie nie miało szans.
   Wyjście builda: ~590 MB → 206 MB.
2. **`SdkLoader` szuka instalacji Subiekta** —
   `%LOCALAPPDATA%\InsERT\Deployments\Nexo\<nazwa+hash>\Binaries`. Nazwa
   zawiera bazę i hash, więc **szukamy**, nie wpisujemy na sztywno; katalog
   jest aktualizowany w miejscu, więc wersja jest zgodna z bazą **z definicji**.
   Konfigowy `sdkBin` wygrywa tylko, gdy wskazuje biblioteki co najmniej
   tak świeże.

Sprawdzone: `Sfera 61.1.1.9471 → Zalogowano operatora: GKI`, katalog czyta
3547 kartotek.

> **Dlaczego to ważne dla userów:** oni dostają tylko 5 plików bez bibliotek,
> więc braliby je z `C:\iLogic\Subiekt\Bin` (06.09) i trafiliby na tę samą
> awarię. Teraz znajdą własną instalację Subiekta.

---

## 14. Etap 3: „Dopasowanie kartotek Subiekta"

Ciąg pracy z elementami handlowymi ułożył się w trzy etapy:

```
1. scalanie zapisów      „UCFL 201" / „UCFL-201" / „UCFL201" → jeden kod
2. scalanie podobnych    człowiek rozstrzyga duplikaty
3. TO OKNO               kanoniczny kod → konkretne Id kartoteki Subiekta
```

Nowe pliki: **`subiekt_dopasowanie.py`** (logika) + **`subiekt_dopasowanie_gui.py`**
(okno). Zastąpiły wcześniejszą, prostszą próbę z tego samego dnia.

### 14.1. Naprawiony błąd klasyfikacji

Stare `dopasuj_katalog()` robiło `setdefault`, czyli przy kilku kartotekach
o tym samym znormalizowanym symbolu brało **pierwszą z brzegu**. Pomiar na
katalogu (3547 kartotek): **45 kolizji po symbolu, 130 po nazwie**.

Projekt 3000 od razu pokazał dwa prawdziwe duplikaty w Subiekcie:
`KM 4-M20 x 1` vs `KM4-M20x1`, `SGS-M10x1 25` vs `SGS-M10x125`.
Najlepszy przykład z nazw: **`Uszczelka clamp VITON` to TRZY różne kartoteki**
(DN10 K=34, DN10 K=50,5, DN20 K=34).

Indeks trzyma teraz **listy**, a niejednoznaczność idzie do człowieka.

### 14.2. Reguły automatu (bez fuzzy)

| | Warunek | Stan |
|---|---|---|
| A | jest globalne mapowanie | zapamiętane |
| B | dokładnie 1 kartoteka po kluczu | dokładny symbol (zielone) |
| C | dokładnie 1 po nazwie | do potwierdzenia (żółte) |
| D | więcej niż jedna | niejednoznaczne (decyzja) |
| E | nic | brak kartoteki |

Podobieństwo może **najwyżej ustawiać kolejność** kandydatów w wyszukiwarce —
nigdy niczego nie przypina. Podstawa: pomiar z 04.09 (`subiekt_podobne.py`),
389 fałszywych par przy nazwach.

### 14.3. Klucz: kod, a gdy go nie ma — nazwa

Zasada użytkownika, która naprawiła realną lukę:

> „jeśli nie ma kodu znormalizowany w bazie — to pracujemy na nazwie;
> jeśli ma kod i nazwę to pracujemy na kodzie"

Pozycje bez numeru rysunku dostają symbol wyliczony przez `symbol_z_nazwy()` —
obcięty do 13 znaków, bez spacji (`rolka SITI 8010235` → `rolkaSITI8010`).
**Takiego ciągu nie ma nigdzie**, więc szukanie po nim to gwarantowane zero
trafień. Stąd też kolumna „Nr rysunku" w oknie **zostaje pusta**, gdy numeru
nie ma — zamiast udawać kod, którego nie ma w bazie.

### 14.4. Stan „odrzucone" (nowa tabela)

Bez niego „Odepnij" było bezużyteczne: automat przy następnym otwarciu
przypinał tę samą błędną kartotekę, bo reguła „symbol == symbol" nadal
zachodziła. Tabela `odrzucone_dopasowania` w bazie mapowań.

### 14.5. Wyszukiwarka po członach

`6004 rS` szukane dosłownie nie trafiało w nic, choć w katalogu jest
`SS 6004 2RS` — te same człony, inna kolejność i przedrostek. Teraz każdy
człon musi wystąpić w symbolu albo nazwie; trafienia w **symbol** idą pierwsze.

---

## 15. Arkusz — kolory i kolumny

* **Kolumny „Nazwa" i „Opis"** przeniesione zaraz za „Nr rysunku". Dla pozycji
  bez numeru to nazwa jest tożsamością, więc czytanie „numer → nazwa" musi być
  pod ręką. Opis (`work_desc`/`src_desc`) nie był dotąd pokazywany wcale —
  a bywa jedyną rzeczą odróżniającą dwie pozycje o tej samej nazwie
  („wykonać z PP", „LEWY / PRAWY").
* **Zielona komórka „Nr rysunku"** = pozycja jest na ZK. Źródłem `order_qty`
  w pliku projektu — lokalnie, **zero zapytań do mostu**; działa też na
  stanowiskach bez Subiekta. Świadomie nie „ma kartotekę": w zasianym
  projekcie kartotekę ma wszystko (361/361), więc kolor nic by nie mówił.
* **Ciemniejsza zieleń** = na ZK **i** numer nadpisany ręcznie. Bez tego
  szare tło nadpisania wygrywało i informacja o ZK ginęła akurat na
  pozycjach poprawianych ręcznie.

Trzy błędy wykryte przy okazji tego kolorowania:

1. Blok kolorujący stał **za** `if not data: return`, gdzie `data` to mapa
   alarmów — pozycje bez alarmu (większość) nigdy nie dostawały koloru.
2. Blok pozycji bibliotecznych **wymuszał `bg=GRAY_BG`** przy niebieskiej
   czcionce, kasując ustalone wcześniej tło.
3. Zieleń rejestrowana w `_cells_special_bg` sprawiała, że **podświetlenie
   zaznaczonego wiersza omijało komórkę numeru** — ten zbiór jest dla
   alarmów, które mają zostać widoczne; znacznik do niego nie należy.

---

## 16. Odrzucone i cofnięte

Rzeczy świadomie **niewdrożone** — zapisane, żeby nie wracać do nich bez powodu:

* **Wpisywanie danych z Subiekta do BOM-u** (`9757a58`, cofnięte w `2613015`).
  Funkcja wpisywała symbol i nazwę kartoteki do kolumn arkusza i ustawiała
  `subiekt_symbol`, włączając blokadę edycji. Werdykt: *„nie chcę tego, to za
  zbyt skomplikowane"*. Z tego commita przywrócona została **tylko** naprawa
  wyszukiwarki (`c4f7a0c`).
* **Migracja mastera na WAL/TRUNCATE** — odrzucona; `journal_mode=delete` jest
  świadomym wyborem, bo WAL po SMB przy wielu piszących się rozpada.
* **Refaktor warstwy połączeń SQLite** (połączenie per wątek + `write()`
  context manager) — odłożony. Docelowo komunikacja przejdzie na **HTTP**;
  nie ma sensu robić dwóch migracji.

Przy okazji: w tabeli mapowań siedzą wpisy `auto` z czasów luźniejszego
dopasowania — **`WWP-06-30-06 → 99`**, **`TULEJA → 027-100.01`** (numer rysunku
cudzego detalu). Dlatego cokolwiek zapisuje do BOM-u, musi brać dane z
**klasyfikacji okna**, nie z surowej tabeli.

---

## 17. Pliki — część druga

| Plik | Co |
|---|---|
| `client_version.py` | **nowy** — bramka wersji `.exe`, heartbeat `client_sessions`, samo-aktualizacja |
| `subiekt_dopasowanie.py` | **nowy** — klasyfikacja A–E, indeks list (nie `setdefault`), `odrzucone_dopasowania` |
| `subiekt_dopasowanie_gui.py` | **nowy** — okno etapu 3: zakładki stanów, kandydaci, wyszukiwarka |
| `database_manager.py` | `_retire_master_con` / `_retire_project_con` zamiast `close()` |
| `subiekt_mapowania.py` | `put_many` — jedno połączenie, jeden commit |
| `subiekt_projekt.py` | decyzje dla każdego pustego złożenia, kolumny Nazwa/Opis, `zapisz_mapowania` bez trywialnych wpisów |
| `subiekt_stany.py` | `wysrodkuj` — brak rozmiaru = sama pozycja (koniec okien 1x1) |
| `subiekt_sfera/NexoRecon/SdkLoader.cs` | biblioteki z instalacji Subiekta |
| `subiekt_sfera/NexoRecon/NexoRecon.csproj` | `InsERT.*` nie trafiają do wyjścia |
| `subiekt_sfera/NexoRecon/Projekt.cs` | jeden przelot składu, `RealnySymbol`, `SkladTakiSam`, raport pozycji dopisanych na ZK |
| `RM_BAZA_v15_MAG.spec` | automatyczna publikacja `.exe` na `Y:/RMPAK_CLIENT/` |

---

## 18. Wnioski

**Pomiar bije intuicję.** Trzy razy tego dnia diagnoza z „patrzenia w kod"
rozminęła się z rzeczywistością, a rozstrzygał dopiero pomiar: `py-spy` na
żywej sesji (mapowania 37 s), log mostu (`cmd=projekt` 13 s vs 0,5 s podglądu),
Event Log (moduł winny crasha bez WinDbg).

**Kopia bibliotek to dług.** Każda statyczna kopia SDK żyje własnym życiem,
a baza aktualizuje się sama. Rozwiązaniem nie było odświeżenie kopii, tylko
**usunięcie jej** i wskazanie źródła.

**Niejednoznaczność musi być widoczna.** `setdefault` w indeksie katalogu przez
miesiące po cichu wybierał pierwszą kartotekę z brzegu — 45 kolizji po symbolu
i 130 po nazwie, o których nikt nie wiedział.

**Pytanie użytkownika bywa lepszym rozwiązaniem niż optymalizacja.** Zamiast
przyspieszać zapis 354 wpisów — nie zapisywać ich wcale.
