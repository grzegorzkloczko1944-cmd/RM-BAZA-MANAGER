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
