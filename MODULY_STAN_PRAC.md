# Moduły w RM_BAZA — stan prac (2026-08-12)

Dokument roboczy: co zostało zrobione, co zostaje otwarte i gdzie dokładnie
w kodzie leżą kluczowe miejsca. Do wznowienia pracy w kolejnej sesji.

---

## 1. Problem wyjściowy

Urządzenie składa się z **modułów** (= numery katalogów z rysunkami, trzycyfrowe:
`100`, `300`, `900`). Do każdego modułu należą rysunki i części handlowe.

Potrzeba: wiedzieć **ile detali idzie na poszczególny moduł**, nie tylko sumę na
całe urządzenie.

Stan przed pracami:
- **WAREHOUSE** — format `11(2)x2, 22(1)x2, 33(1)` wpisywany **ręcznie**
- **MACHINE** — sam numer katalogu (`100`, `300`), bez ilości; 4231 z 5774 pozycji

---

## 2. Skąd biorą się moduły

Moduł = trzycyfrowy numer katalogu, wyznaczany przez importer na dwa sposoby:

| Źródło | Przykład | Funkcja |
|---|---|---|
| numer RMPAK | `2556-720.04ZZ` → `720` | `katalog_from_rmpak_number()` |
| nazwa folderu | `Rysunki 900 2556` → `900` | `katalog_for_path()` |

Moduły w strukturze rysunków mają sufiks **`ZZ`** (złożenia). Importer buduje
z nich drzewko (ROOT → moduły → podmoduły → detale).

**Ważne:** numer katalogu to lokalna konwencja numeracji w projekcie, **nie**
globalny identyfikator. `100` w projekcie A i `100` w projekcie B to inny
fizyczny moduł. Dlatego odrzucono pomysł wspólnego katalogu modułów w
`master.sqlite` — sklejałby rzeczy niepowiązane.

Dane: 53 unikalne nazwy modułów, 35 powtarza się między projektami
(`100` w 37 projektach) — to skutek konwencji numeracji, nie współdzielenia.

---

## 3. ZROBIONE: importer V17

**Plik:** `C:\RMPAK_CLIENT\Repozytoria\NOW\RM_IMPORT_V17_MOD.py`
(kopia V16, który pozostaje nietknięty jako produkcyjny)

**Commit:** `69e3d2d` w repo `NOW`, wypchnięty na GitHub
**Build:** `NOW\dist\RM_IMPORT_V17_MOD.exe` — onefile, 113,5 MB

### Format wyjściowy w kolumnie „Katalog" (arkusz ZBIORCZY)

```
900(2)x3,950(1)
```

- `(n)` — ile detali na **jeden egzemplarz** modułu
- `xN` — ile razy moduł występuje w urządzeniu (**pomijane gdy N == 1**)

Format zgodny z parserem, którego RM_BAZA już używa w WAREHOUSE:
regex `([^(]+)\s*\((\d+)\)(?:x(\d+))?`

### Zmiany w kodzie

| Miejsce | Co |
|---|---|
| `format_katalog_with_qty()`, `_fmt_num()` | budowanie zapisu z ilościami |
| `compute_total_quantities()` | `module_counts` — krotność każdego modułu ZZ |
| `compute_total_quantities()` | `per_katalog` per pozycja `{katalog: [ilość_na_moduł, krotność]}` |
| sekcja ZNORMALIZOWANE | `katalog_set` (zbiór — gubił ilości) → `katalog_qty` (słownik sumujący) |
| zapis do arkusza | fallback na starą wartość gdy pozycja nie leży pod ZZ |

**Kluczowy wzór:** `ilość_na_moduł = qty_total detalu / qty_total modułu`
(oba to iloczyny wzdłuż tej samej ścieżki, więc dzielenie zostawia iloczyn
ilości **poniżej** modułu).

Zmiana **addytywna** — `total` liczy się jak dotąd, całość w `try/except`.

### Błąd znaleziony przez test

Pierwsza wersja brała **pierwszy** moduł ZZ ze ścieżki — a pierwszy to zawsze
ROOT (całe urządzenie, `2556-000.00ZZ`). Efekt: wszystko wpadało do katalogu
`000` i sumowało się w jeden worek (`{'000': [7.0, 1.0]}`).

Poprawione na **ostatni ZZ przed elementem** = bezpośredni moduł nadrzędny.

### Przy okazji: limit pola CSV

`csv.field_size_limit` nigdy nie było ustawiane (też w V16). Plik z polem
dłuższym niż 131072 znaki wywalał cały import („field larger than field limit").
Podniesione do maksimum platformy, z fallbackiem `2**31-1` (na Windows
`sys.maxsize` przepełnia C long).

### Testy

- format: mnożnik 1 pomijany, sortowanie rosnąco, ułamki, zero pomijane
- drzewko syntetyczne: detal w dwóch modułach → `900(2)x3,950(1)`
- zagnieżdżenie **ZZ > ZZ > ZZ**: podmoduł `900(3)x2`, detal `950(4)x6`
  (4 × 6 = 24 = ilość całkowita — zgadza się)
- realny projekt 2407 Nanochem: `100(2)`, `100(4)` — poprawnie, `x` nie
  występuje bo moduł jest jeden i występuje raz

---

## 4. ZROBIONE: RM_BAZA

**Plik:** `RM_BAZA_v15_MAG_STATS_ORG.py` — **NIEZACOMMITOWANE**

Okazało się, że potrzebne były **tylko dwie linijki** — reszta mechanizmu już
działała dla obu trybów:

| Element | Stan przed | Zmiana |
|---|---|---|
| wyświetlanie modułu w tabeli | działało (wartość bez modyfikacji) | — |
| filtr modułów | działał (kod jawnie obsługuje oba formaty) | — |
| przycisk filtra | widoczny w MACHINE | — |
| **symbol `●` przy wielu modułach** | tylko WAREHOUSE | **włączone dla obu** |

Zmienione dwa miejsca (tabela + eksport), żeby zachować spójność:
`_display_items_in_sheet()` (~6000) i eksport (~25957).

### Zabezpieczenie przed regresją

Symbol `●` pojawia się **tylko gdy moduły mają ilości w nawiasach**:

```python
if modul_disp and ',' in modul_disp and '(' in modul_disp:
```

Bez warunku na `(` 35 istniejących pozycji w `project_22` (stary format
`300,600`) straciłoby widoczną ilość, nic nie zyskując. Zweryfikowane na
wszystkich bazach: **0 pozycji zmienia wygląd**. Nowe zachowanie włączy się
samo po reimporcie importerem V17.

### Czego NIE zmieniono (decyzje użytkownika)

- **przeliczanie Ilości BOM po edycji modułu** — zostaje tylko w WAREHOUSE
- **`menu_aktualizuj_bom` i `menu_import_modul`** — dalej ignorują kolumnę
  „Katalog" (komentarz „NIE UŻYWAMY — importujemy z wpisaną nazwą")
- **okno statystyk cenowych** — obcięcie do samej nazwy modułu jest tam
  pożądane (grupowanie)

### Schemat SQLite — bez zmian

Kolumny `src_modul` / `work_modul` **już istnieją** w bazach MACHINE
(58 z 61; brakujące `project_5`, `project_10`, `project_49` dostaną je
automatycznie przy otwarciu projektu).

**Żadnej migracji, żadnego skryptu na danych.**

---

## 5. OTWARTE — do rozstrzygnięcia przy wznowieniu

### 5a. Kierunek zależności Moduł ↔ Ilość BOM

Stan dzisiaj — **niespójny między trybami**:

| Kierunek | WAREHOUSE | MACHINE |
|---|---|---|
| edycja modułu → przelicza Ilość BOM | tak (~10675) | nie |
| edycja Ilości BOM → aktualizuje moduł | tak (~10645, tylko przy jednym module) | nie |

**Rekomendacja:** moduł = źródło, ilość = wynik. Ilość jest pochodną tego, co
idzie na moduły, więc:
- moduł → ilość: automatycznie
- ilość → moduł: tylko przy jednym module (przy wielu nie da się zgadnąć, do
  którego przypisać zmianę — stąd sensowny symbol `●`)

**Decyzja użytkownika: zostawiamy jak jest na razie.**

### 5b. Mnożnik ignorowany przy przeliczaniu

W `menu` przeliczania (~10677) suma bierze **tylko ilość z nawiasu**:

```python
qty = int(match.group(2))   # group(3) = mnożnik JEST IGNOROWANY
total_qty += qty
```

Dla `900(2)x3` policzy **2**, nie 6.

Dotyczy to **istniejącego WAREHOUSE** — tam mnożniki wpisywano ręcznie i chyba
traktowano informacyjnie. Ale w modelu „moduł występuje 3 razy" na urządzenie
idzie 6 sztuk.

**Ryzyko:** jeśli włączy się przeliczanie w MACHINE bez naprawy tego, ilości
będą **zaniżone** wszędzie tam, gdzie moduł się powtarza — importer V17 liczy
poprawnie, a RM_BAZA by to psuła przy ręcznej edycji.

Zmiana wspólnego kodu wpłynie też na WAREHOUSE — trzeba sprawdzić, czy
istniejące dane magazynowe na tym nie ucierpią.

### 5c. Wiersze samych modułów ZZ — ROZWIĄZANE (2026-08-12)

**Problem:** podzespół ZZ o krotności > 1 (np. „Zespół rolki" występujący 106×)
dostawał format `200(106)` — liczony względem modułu NADRZĘDNEGO (Transporter,
krotność 1). Detale POD nim dostawały `200(1)x106` (liczone względem Zespołu
rolki, krotność 106). Ten sam BOM (106), dwa różne zapisy → mylące.

**Fix (importer, `compute_total_quantities` ~3824):** jeśli element SAM jest
modułem ZZ o własnej krotności > 1, liczymy go względem WŁASNEJ krotności:
`qty_na_modul = total / krotnosc_wlasna`, `xN = krotnosc_wlasna`. Efekt:
Zespół rolki → **`200(1)x106`**, spójnie z detalami pod nim. Root modułu (1×)
i pozycje 1× zostają bez mnożnika. `totals[num]["total"]` nietknięte — zmiana
dotyczy tylko warstwy prezentacji `per_katalog`.

Zweryfikowane: drzewko ZZ>ZZ>ZZ → `900(1)x2`, `950(1)x6`, detal `950(4)x6`
(4×6=24 ✓). Moduł/root o krotności 1 → nadal `(n)` bez `xN`.

### 5d. Weryfikacja na większych danych — ZALICZONE (2026-08-12)

Potwierdzone na realnym **project_78** („2641 4 mass etykieciarka z transporterem
rolkowym", MACHINE). Moduł 200 (Transporter): podzespół „Zespół rolki"
(`2641-200.03ZZ`) występuje 106×, pod nim Rolka i Oś (`200.01`/`200.02`).
Mnożnik `x106` policzony poprawnie (`1 × 106 = 106` = BOM). Pozostałe pozycje
`200.xx` leżą wprost pod modułem 200 (1×) → `(n)` bez mnożnika. **Format `xN`
potwierdzony na prawdziwych danych.**

---

## 6. Znalezione przy okazji (poza tematem modułów)

- **Usunięto 2 uszkodzone pliki** z `RM_BAZA\projects`:
  `project_22_before_restore_20260430_115718.sqlite` i `..._120131.sqlite`
  — oba po 454 KB, wypełnione samymi zerami, nie były bazami SQLite.
- **`2407-500.055X Spięcie pasa.csv`** w projekcie Nanochem to **nie CSV**,
  tylko plik OLE2 (stary format Office, 1,4 MB, 616 711 bajtów zerowych)
  zapisany z rozszerzeniem `.csv`. Wywala import. Do usunięcia/zmiany
  rozszerzenia po stronie danych.
- Rozważane, ale **odrzucone**: osobne tabele `modules` / `item_modules`
  i katalog modułów w `master.sqlite` — niepotrzebne, skoro numer katalogu
  jest lokalny dla projektu, a format tekstowy wystarcza i jest już parsowany.

---

## 7. Kluczowe miejsca w kodzie

### Importer (`NOW\RM_IMPORT_V17_MOD.py`)

| Linia | Co |
|---|---|
| ~60 | podniesienie `csv.field_size_limit` |
| ~344 | `_fmt_num()` |
| ~355 | `format_katalog_with_qty()` |
| ~3740 | `module_counts` — krotności modułów ZZ |
| ~3800 | `per_katalog` w strukturze `totals` |
| ~3815 | wyznaczenie modułu (ostatni ZZ) + dzielenie |
| ~3890 | sekcja ZNORMALIZOWANE — `katalog_qty` |
| ~4020 | zapis kolumny Katalog do arkusza |

### RM_BAZA (`RM_BAZA_v15_MAG_STATS_ORG.py`)

| Linia | Co |
|---|---|
| ~3563 | okno statystyk — obcięcie do nazwy modułu (celowo, grupowanie) |
| ~6000 | `_display_items_in_sheet()` — symbol `●` **[ZMIENIONE]** |
| ~10645 | edycja Ilości BOM → aktualizacja modułu (tylko WAREHOUSE) |
| ~10677 | edycja modułu → przeliczenie `work_qty` (tylko WAREHOUSE, **ignoruje mnożnik**) |
| ~12266 | `menu_import_bom` — **czyta** „Katalog" → `src_modul` |
| ~14087 | `menu_aktualizuj_bom` — **ignoruje** („NIE UŻYWAMY") |
| ~15512 | `menu_dodaj_bom` — **czyta** |
| ~16303 | `menu_import_modul` — **ignoruje** („NIE UŻYWAMY") |
| ~21528 | edytor modułów z mnożnikami (mnożniki tylko z lockiem) |
| ~25957 | eksport — symbol `●` **[ZMIENIONE]** |

### Funkcje pomocnicze RM_BAZA

- `_get_all_moduls_from_project()` — zbiera moduły do filtra, **obsługuje oba
  formaty** (z nawiasami i bez)
- `_get_multipliers_from_database()` — wczytuje mnożniki do
  `self.modul_multipliers`, ale **ta zmienna nie jest nigdzie używana
  w obliczeniach** (3 wystąpienia: deklaracja, przypisanie, log)

---

## 8. Następny krok

1. ~~Przepuścić przez importer V17 projekt z powtarzającym się modułem~~ —
   ZROBIONE, project_78 (2641), punkt 5d zaliczony.
2. ~~Ujednolicić wiersze samych modułów ZZ~~ — ZROBIONE, punkt 5c, format
   `(1)xN` (repo NOW, `RM_IMPORT_V17_MOD.py`).
3. **Reimport project_78 przez nowy importer V17** i sprawdzenie w RM_BAZA
   MACHINE — czy Zespół rolki pokazuje teraz `200(1)x106` i czy `●` działa.
4. Dopiero potem wracać do decyzji z punktów 5a i 5b.

**Stan repo:** zmiany w `RM_BAZA_v15_MAG_STATS_ORG.py` są **niezacommitowane**.
Importer V17 jest zacommitowany i wypchnięty (`69e3d2d` w repo `NOW`).
