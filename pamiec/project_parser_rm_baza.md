---
name: project-parser-rm-baza
description: "Parser_RM_BAZA - wykrywanie anomalii cenowych elementów handlowych, read-only, GUI tksheet"
metadata: 
  node_type: memory
  type: project
  originSessionId: 32263a47-f8b3-44e1-8aaf-deccc5584315
---

Zbudowano `Parser_RM_BAZA.py` + `Parser_RM_BAZA_gui.py` (2026-07-05) - samodzielny,
READ-ONLY skrypt wykrywający anomalie cenowe elementów handlowych (klasa STANDARD/
ZNORMALIZOWANE) w bazie RM_BAZA, celowo trzymany poza `RM_BAZA_v15_MAG_STATS_ORG.py`
(26k linii), żeby nie ryzykować produkcyjnego kodu.

**Krytyczne: dwie różne ścieżki bazy istnieją na dysku, tylko jedna jest żywa.**
- `C:\RMPAK_CLIENT\RM_MANAGER\RM_BAZA\` - **właściwa, żywa baza**, ta którą czyta
  RM_BAZA GUI na co dzień. Parser_RM_BAZA MUSI używać tej ścieżki.
- `C:\RMPAK_CLIENT\RM_BAZY\RM_BAZA\` - inna, nieaktualna kopia (mylące podobieństwo
  nazw - "RM_BAZY" liczba mnoga vs "RM_MANAGER"). Użycie tej ścieżki dało realny bug:
  parser pokazywał cenę dla pozycji, która w żywej bazie ma `price_pln IS NULL`.
  Patrz też [[reference_db_paths]] (ta pamięć dotyczy innej pary ścieżek dla
  master.sqlite/projects - **zweryfikuj obie przy każdym użyciu**, bo w tym repo
  wielokrotnie mylono podobne ścieżki na dysku).

**Kolumna `price_pln` w tabeli `items` to CENA JEDNOSTKOWA (za 1 szt.)**, nie wartość
całej pozycji - potwierdzone w `RM_BAZA_v15_MAG_STATS_ORG.py:3234`
(`SUM(price_pln * COALESCE(order_qty, work_qty, src_qty, 1))`). Wcześniej błędnie
założono odwrotnie i dzielono przez ilość - to psuło wynik (podwójnie zaniżało ceny).

**Grupowanie nazw - dwa tryby, żeby nie mieszać wymiarów produktu z wariantami:**
- Nazwy opisowe (np. "Łożysko 6004 INOX") - fuzzy matching (Jaccard po tokenach) +
  osobny tag wariantu (INOX/2RS/nierdzewne jako synonimy).
- Kody katalogowe FESTO/SMC (np. "DFM-20-40-P-A-GF", wzorzec: litery + 2+ liczby na
  POCZĄTKU nazwy, regex kotwiczony inaczej łapał fałszywe fragmenty w środku zdań
  typu "zakres 36-39") - dopasowanie DOKŁADNE całego kodu z wymiarami, bez fuzzy.
  Różne wymiary (DFM-20-40 vs DFM-20-20) to różne, nieporównywalne produkty.

Elementy klasy `WAREHOUSE` (project_type) są jawnie pomijane - to projekty magazynowe,
nieistotne dla analizy cenowej elementów handlowych w maszynach.

Wynik na żywej bazie (2026-07-05): 293 pozycji z cenami, 262 grupy, 7 grup z
odchyleniem ceny jednostkowej ≥1.4x od mediany grupy - realne kandydatury do
ręcznej weryfikacji (część to prawdopodobnie pomyłki operatora przy wpisywaniu
ceny/ilości, nie tylko wahania rynkowe).
