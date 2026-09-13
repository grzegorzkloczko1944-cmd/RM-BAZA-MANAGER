# Schowek → RW: algorytm wystawiania

**Data:** 2026-09-13
**Status:** WDROŻONE 13.09.2026 — kod w `subiekt_schowek_bom.py`
i `subiekt_schowek_gui.py`; §9 to sprostowanie po pierwszym prawdziwym wydaniu
**Zastępuje:** wcześniejsze koncepcje z `source='warehouse'`, tabelą
pośrednią `schowek_wydane_pozycje` w master i osobną kategorią „pozycje
magazyniera" — **wszystkie wyrzucone jako niepotrzebne**

---

## 0. Dla czytającego z zewnątrz — kontekst w pięciu zdaniach

**Schowek montażowy** to bufor między monterem a dokumentem RW. Monterzy
biorą element, oddają bo nie pasuje, biorą inny — robienie dokumentu na
każdy taki ruch jest bez sensu księgowo i nikt nie zdąży tego klikać.
Schowek zbiera ruchy w ciągu dnia, a do Subiekta idzie **jedno RW
z bilansem netto** (wziął i oddał tego samego dnia = zero śladu).

Ten dokument opisuje **wyłącznie moment rozliczenia**: co się dzieje
z pozycjami w chwili wystawiania RW. Sam bufor opisuje
[[BUFOR_SCHOWEK_MONTAZOWY.md]].

Kluczowe tło: po wystawieniu RW schowek **DOPISUJE wydane ilości do
„Ilość dostarczonych"** w arkuszu. Algorytm dba więc o to, żeby istniał
wiersz, do którego da się je dopisać.

> ⚠️ **Sprostowanie z 13.09.2026.** Pierwsza wersja tego dokumentu
> zakładała, że „Ilość dostarczonych" jest CZYTANA z Subiekta i wystarczy
> zapewnić istnienie wiersza. **To założenie było błędne** — takiego
> odczytu w kodzie nie ma, `delivered_qty` jest zwykłym polem bazy
> projektu. Wyszło przy pierwszym prawdziwym wydaniu: RW powstało
> w Subiekcie, a arkusz się nie zmienił. Patrz §9.

---

## 1. Zasada

Przy rozliczeniu schowka jedyne pytanie o pozycję brzmi:

> **Czy jej SYMBOL występuje już w kolumnie „Nr rysunku" tego projektu?**

* **TAK** → nie ruszamy BOM-u, tylko dokładamy pozycję do RW.
* **NIE** → najpierw dokładamy wiersz do RM_BAZA, potem RW.

`SYMBOL` to numer rysunku **albo kod kreskowy** — jedno i drugie mieszka
w tej samej kolumnie „Nr rysunku".

### Dlaczego to wystarcza

Po potwierdzonym RW schowek **dopisuje wydane ilości do „Ilość
dostarczonych"** (§9). Wystarczy więc zapewnić, że istnieje wiersz, do
którego da się je dopisać — nic więcej nie trzeba synchronizować.

**Nie oznaczamy, że pozycję dodał magazynier.** Po operacji to jest zwykła
pozycja projektu — następnym razem ten sam detal zostanie znaleziony po
numerze i drugi wiersz już nie powstanie. To samo w sobie eliminuje potrzebę
kategorii „magazynowe".

---

## 2. Przebieg

```text
SCHOWEK
   │
   ▼
dla każdej pozycji:
SYMBOL = numer rysunku LUB kod kreskowy
   │
   ▼
Szukaj SYMBOLU w kolumnie „Nr rysunku" projektu RM_BAZA
   │
   ├────────────── JEST ──────────────┐
   │                                  │
   │                           NIE DODAJEMY WIERSZA
   │                                  │
   │                                  ▼
   │                         dodaj pozycję do RW
   │                         w Subiekcie pod projekt
   │                                  │
   │                                  ▼
   │                    RM_BAZA dopisuje wydane ilości
   │                                  │
   │                                  ▼
   │                     „Ilość dostarczonych" się zwiększa
   │
   └────────────── NIE MA ────────────┐
                                      │
                              DODAJ NOWY WIERSZ
                              do RM_BAZA
                                      │
                         Nr rysunku = SYMBOL
                         nazwa = nazwa detalu
                         pozostałe dane wg reguł
                                      │
                                      ▼
                              dodaj pozycję do RW
                              w Subiekcie pod projekt
                                      │
                                      ▼
                      RM_BAZA dopisuje wydane ilości
                                      │
                                      ▼
                         „Ilość dostarczonych" się zgadza
```

---

## 3. Przykład

Projekt ma:

| Nr rysunku | Nazwa | Ilość dostarczonych |
|---|---|---|
| 2627-100.01 | Wspornik | 3 |
| 5901234567890 | Klej | 1 |
| 2627-200.04 | Tuleja | 0 |

W schowku magazyniera:

```text
2627-100.01      +2
5901234567890    +1
4012345678901    +3
```

Pierwsze dwa **istnieją** → tylko RW, żadnych nowych wierszy:

```text
2627-100.01      RW +2
5901234567890    RW +1
```

`4012345678901` **nie istnieje** → najpierw nowy wiersz na końcu arkusza:

```text
4012345678901    [nazwa detalu]     0
```

potem RW +3, a po nim dopisanie ilości:

```text
4012345678901    [nazwa detalu]     3
```

---

## 4. Trzy twarde zabezpieczenia

### 4.1 Porównanie po TRIM + case-insensitive

Nie porównywać surowych stringów. Symbol wpisany ręcznie i zeskanowany
mogą różnić się spacją albo wielkością liter, a wtedy powstałby drugi
wiersz na ten sam detal.

✅ **Gotowe do użycia** — dokładnie takie porównanie robi już walidacja
duplikatów przy ręcznym dodawaniu pozycji
(`RM_BAZA_v15_MAG_STATS_ORG.py:11895`):

```sql
WHERE project_id = ?
  AND ( LOWER(TRIM(COALESCE(work_drawing_no, ''))) = LOWER(TRIM(?))
     OR LOWER(TRIM(COALESCE(src_drawing_no,  ''))) = LOWER(TRIM(?)) )
```

Sprawdzane są **oba** pola — bo „Nr rysunku" w arkuszu to wartość
efektywna: `COALESCE(NULLIF(work_drawing_no,''), src_drawing_no)`.

### 4.2 Ponowne sprawdzenie tuż przed dodaniem wiersza

Między zbudowaniem listy a zapisem ktoś mógł dodać tę pozycję (drugi
magazynier, import, Edytor kartotek). Sprawdzenie z §4.1 powtarzamy
**bezpośrednio przed** `INSERT`, w tej samej transakcji.

### 4.3 ⛔ ZAPIS DO SUBIEKTA IDZIE DOPIERO PO POTWIERDZENIU PRZEZ RM_BAZA

**To jest reguła nadrzędna całego algorytmu.**

Wydanie z Subiekta **nigdy nie może pojawić się wcześniej** niż rekord, do
którego ma się przypiąć. Odwrotna kolejność dałaby okno czasowe, w którym
arkusz pokazuje ilość „znikąd" albo gubi ją przy odczycie.

```text
1. sprawdź symbol w BOM-ie              (§4.1)
2. brakujące → zapisz wiersz            (§4.2 — sprawdź jeszcze raz)
3. RM_BAZA POTWIERDZA zapis  ← BRAMKA
4. dopiero teraz: zatwierdź RW w Subiekcie
5. read-back + odświeżenie arkusza
```

Brak potwierdzenia z kroku 3 = **RW nie powstaje**. Nie „powstaje i
naprawimy później" — nie powstaje.

⚠️ **Potwierdzenie NIE oznacza „musi być lock".** Potwierdzeniem jest
udany zapis w JEDNYM z dwóch miejsc:

| sytuacja | gdzie ląduje wiersz | co potwierdza |
|---|---|---|
| lock wolny albo nasz | baza projektu | zapis do bazy projektu |
| lock trzyma ktoś inny | **tabela tymczasowa w master.sqlite** | **zapis do master** |

W obu wypadkach RW powstaje normalnie — bo w obu wiersz na pewno już
istnieje (albo w projekcie, albo w poczekalni, z której arkusz go nałoży).
Brak locka **nie blokuje wydania**; blokuje je dopiero nieudany zapis
w którymkolwiek z tych dwóch miejsc. Szczegóły: §4.4.

### 4.4 Gdy lock trzyma ktoś inny — wiersz idzie do master.sqlite

Zapis nowego wiersza wymaga locka projektu (RM_BAZA pracuje na kopii
lokalnej). Gdy lock trzyma ktoś inny, nowej pozycji nie da się zapisać
od razu — a mimo to magazynier musi móc rozliczyć schowek.

Rozwiązanie: **wiersz ląduje w tabeli pośredniej w master.sqlite**, tym
samym wzorcem, którym wysyłka ZD odkłada „Zamówiono"
(`zd_zamowione_pozycje`, opisane w `subiekt_wyslij_zd.py:215-229`):

```text
lock wolny albo NASZ
   └─→ zapis wprost do bazy projektu  →  potwierdzenie  →  RW

lock trzyma KTOŚ INNY
   └─→ zapis do master.sqlite         →  potwierdzenie  →  RW
        (tabela pośrednia)                    │
                                              ▼
                            arkusz nakłada wiersz przy „Przejmij Lock",
                            na świeżej kopii lokalnej — dokładnie jak
                            _naloz_zamowienia_zd()
```

Potwierdzeniem z §4.3 jest w tym wypadku **udany zapis do master** — bo od
tej chwili wiersz na pewno powstanie, najpóźniej przy następnym przejęciu
projektu. Dopiero wtedy wolno wystawić RW.

Zasady przejęte z mechanizmu ZD, bo są tam już sprawdzone:

* wiersz z master kasuje `release_lock` **po udanym wgraniu kopii** na
  serwer — „Anuluj" ani padnięcie sieci go nie gubi;
* nakładanie jest **idempotentne** — powtórka nic nie psuje;
* przy nakładaniu obowiązuje **granica czasowa** (`_zd_bufor_do`): master
  jest wspólny, więc między nałożeniem a wgraniem kopii ktoś może dołożyć
  swój wpis. Kasowanie „wszystkiego dla project_id" zabrałoby cudzy świeży
  wpis — błąd wykryty przy ZD 08.09.2026.

⚠️ Przy nakładaniu obowiązuje **ta sama walidacja duplikatu** co w §4.1:
między odłożeniem a przejęciem locka ktoś mógł dodać tę pozycję ręcznie.

---

## 5. Kolejność nowych wierszy — NIC NIE ZMIENIAMY

**Decyzja 13.09.2026: zostaje sortowanie alfabetyczne, tak jak jest dziś.**

Nowy wiersz pojawi się tam, gdzie wypadnie po numerze rysunku
(`database_manager.py:794` — `ORDER BY drawing_no, name, id`), a nie na
końcu arkusza. Wcześniejszy pomysł „doklejać na końcu" **wycofany**.

Co to oznacza w praktyce: pozycja `4012345678901` wyląduje między
`2627-…` a resztą numerycznych, a nie pod spodem. Dla algorytmu bez
znaczenia — powiązanie idzie po numerze rysunku i `item_id`, nie po
pozycji wiersza (patrz `PROBLEM_KOLEJNOSC_WIERSZY_ARKUSZA.md` §5.4).

**Zysk:** odpada migracja 64 baz projektów, nowa kolumna porządkowa
i ryzyko, że komuś zniknie alfabetyczna kolejność, po której szuka pozycji.
Temat stałej kolejności zostaje otwarty w tamtym dokumencie, ale **nie jest
blokerem dla schowka**.

---

## 6. Czego NIE robimy

* ❌ `source='warehouse'` ani żadnego znacznika „pozycja magazyniera"
* ❌ tabeli pośredniej dla **wydanych ILOŚCI** — „Ilość dostarczonych"
  czyta się z Subiekta, nic tam nie odkładamy
* ❌ wpisywania ilości wydanych do BOM-u

Tabela pośrednia w master dotyczy **wyłącznie nowych WIERSZY** odłożonych
pod cudzym lockiem (§4.4) — to co innego niż odkładanie ilości.

---

## 7. Dane nowego wiersza — ROZSTRZYGNIĘTE (13.09.2026)

| pole | wartość | skąd |
|---|---|---|
| **Nr rysunku** | SYMBOL ze schowka | to, co magazynier zeskanował |
| **Nazwa** | **nazwa / symbol z kartoteki Subiekta** | `subiekt_stany.query_stock` |
| **Magazyn** | zawsze `MASTER` | **jest jeden magazyn** |
| Ilość dostarczonych | nie wpisujemy | czytane z Subiekta po RW |

Nazwa bierze się z Subiekta, nie z tego, co magazynier widział na ekranie —
Subiekt jest właścicielem kartoteki, więc jego nazwa jest tą właściwą.

### Jeden magazyn — MASTER

Potwierdzone 13.09.2026: w firmie jest **jeden magazyn**. To zamyka przy
okazji wpis z `TODO_OKNO_WYDANIA.md` o nieużywanym parametrze `magazyn`
w trybie `wydanie-stan` — sumowanie „globalne" jest poprawne, bo nie ma
czego mieszać. Parametr można usunąć z sygnatury albo zostawić
z komentarzem, że przy jednym magazynie nie ma znaczenia.

---

### Wartości domyślne nowego wiersza

**Ilość = 0.** Nie zgadujemy — Subiekt wypełni poprawną wartość przy
najbliższym odczycie, bo „Ilość dostarczonych" i tak stamtąd pochodzi.
Pozostałe pola (typ pozycji, materiał, dostawca) zostają puste: pozycja
weszła spoza BOM-u, więc nie mamy o niej żadnej wiedzy konstrukcyjnej,
a wpisanie czegokolwiek byłoby zmyślaniem.

---

## 8. Do rozstrzygnięcia

1. **Czy pokazać przejście przez poczekalnię** (§4.4). Rekomendacja:
   pokazywać TYLKO wtedy, gdy faktycznie się zdarzyło — cisza w normalnym
   przypadku, jedno zdanie w wyjątkowym:

   ```text
   ✓ Wystawiono RW 143/MASTER/2026

   ℹ 1 nowa pozycja (4012345678901) pojawi się w arkuszu, gdy projekt
     przejmie ktoś z lockiem — teraz trzyma go Kowalski.
   ```

   Bez tego magazynier zajrzy do arkusza, nie znajdzie swojej pozycji
   i uzna, że coś nie zadziałało.

*Pytanie o lock — rozstrzygnięte, patrz §4.4: wiersz idzie do master
i RW powstaje normalnie.*

---

## 9. „Ilość dostarczonych" — zapis, nie odczyt (sprostowanie 13.09.2026)

### Co się okazało przy pierwszym wydaniu

Test na żywo: pozycja `2627-200.12`, projekt 3500. **RW powstało
w Subiekcie, ale arkusz się nie zmienił.**

Algorytm zadziałał poprawnie — pozycja była już w BOM-ie (wiersz 476), więc
zgodnie z §1 nie dopisywał wiersza, tylko wystawił RW. Zawiodło założenie:

> „Ilość dostarczonych" jest CZYTANA z Subiekta

**Takiego odczytu nie ma.** `delivered_qty` to zwykłe pole bazy projektu,
wypełniane ręcznie albo przez stary skaner. Okno wydania ma nawet komentarz,
że **celowo** go nie rusza (`subiekt_wydanie_gui.py:19`), bo dla niego
oznacza „dostarczono od dostawcy".

### Decyzja: wydane idzie do odebranych

Użytkownik: *„A — no przecież wydane to ma iść do odebrane"*.

Z punktu widzenia PROJEKTU to jeden fakt: **detal dotarł i można go
montować**. Nieważne, czy przyjechał od dostawcy, czy wyszedł z magazynu —
jedna kolumna, jeden sens. Rozdzielanie tego na dwa pola byłoby księgowym
rozróżnieniem bez wartości dla osoby patrzącej na arkusz.

### Jak to działa

Po **potwierdzonym** RW (nigdy przed) `BOM.dopisz_wydane()`:

```sql
UPDATE items
   SET delivered_qty = COALESCE(delivered_qty, 0) + ?,
       delivered_updated_at = ?, updated_at = ?
 WHERE id = ?
```

* **DODAJE, nie nadpisuje** — ta sama pozycja bywa wydawana kilka razy,
  a część mogła wcześniej przyjść od dostawcy; nadpisanie skasowałoby tamto.
* `delivered_updated_at` aktualizowane tak samo jak przy każdym innym
  zapisie tego pola (`database_manager.py:861`).
* Pozycja, której nie ma w BOM-ie, jest pomijana — nie ma gdzie dopisać.

### Bez locka: mówimy o tym wprost

Baza projektu bez locka jest READ-ONLY, więc dopisanie się nie uda.
Magazynier dostaje wtedy komunikat:

```text
RW 143/MASTER/2026 powstało, towar zszedł ze stanu.

„Ilość dostarczonych" w arkuszu NIE została zwiększona, bo projekt nie
jest przejęty. Przejmij lock i popraw ręcznie albo wystawiaj wydania przy
przejętym projekcie.
```

Świadomie NIE zapisujemy tego po cichu w próżnię — magazynier zajrzy do
arkusza, zobaczy niezmienioną liczbę i musi wiedzieć dlaczego.

⚠️ **Do rozważenia:** nowe WIERSZE mają poczekalnię w master (§4.4),
a dopisanie ILOŚCI jej nie ma. Przy wydaniu bez locka arkusz zostaje
z nieaktualną liczbą do ręcznej poprawki. Gdyby to zaczęło przeszkadzać,
ten sam wzorzec poczekalni obsłużyłby i ilości.
