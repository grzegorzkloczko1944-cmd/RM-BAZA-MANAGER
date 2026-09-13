# Kolejność wierszy w arkuszu RM_BAZA — problem do rozstrzygnięcia

**Data:** 2026-09-13
**Status:** ANALIZA — nic nie zmienione w kodzie, czekamy na decyzję
**Pilność:** ⬇ NISKA (13.09.2026) — decyzja: *„alfabetycznie, zgodnie z tym
co teraz jest, więc tutaj nic nie ruszamy"*. Schowek montażowy, który ten
temat wywołał, działa bez tej zmiany — nowe pozycje wchodzą alfabetycznie
i to jest akceptowane. Dokument zostaje jako analiza na przyszłość, gdyby
skakanie wierszy przy edycji zaczęło przeszkadzać.
**Zgłoszenie:** „trzeba by te dodane pozycje doklejać na sam koniec arkusza
aby się nie rozjechał i zablokować w arkuszu przemieszczanie się wierszy gdy
się zmienia nazwa lub numer"

Dokument opisuje **jeden problem o dwóch objawach**. Wszystkie liczby niżej
pochodzą z odczytu kodu i żywych baz, nie z oszacowania.

---

## 1. Objawy

### Objaw A — wiersz ucieka przy zmianie nazwy lub numeru

Użytkownik poprawia nazwę pozycji albo numer rysunku. Wiersz **znika mu
z oczu** i pojawia się kilkadziesiąt pozycji dalej. Przy poprawianiu serii
pozycji trzeba za każdym razem szukać, gdzie wylądowała poprzednia.

### Objaw B — nowa pozycja wpada w środek

Pozycja dołożona do projektu (dziś: ręcznie, z pliku, z Edytora kartotek;
docelowo także **wydana ze schowka montażowego**, gdy nie było jej w BOM-ie)
nie ląduje na końcu, tylko wskakuje tam, gdzie wypadnie alfabetycznie.
Arkusz „rozjeżdża się" — to, co użytkownik miał przed oczami, przesuwa się
o wiersz w dół.

---

## 2. Przyczyna — jedna, wspólna dla obu objawów

Arkusz **nie ma zapisanej kolejności wierszy**. Ustala ją przy każdym
wczytaniu, sortując dane:

```sql
-- database_manager.py:794
ORDER BY drawing_no COLLATE NOCASE, name COLLATE NOCASE, i.id
```

Kolejność jest więc **funkcją treści**: zmienia się treść → zmienia się
miejsce wiersza. Nie ma tu żadnego błędu do naprawienia — tak to zostało
zaprojektowane. Problem polega na tym, że przy edycji i dokładaniu pozycji
to zachowanie przeszkadza.

### Dlaczego zmiana nazwy przesuwa wiersz

`drawing_no` i `name` **nie są kolumnami w bazie** — to wartości wyliczane
w locie, z nadpisania albo z oryginału:

```sql
-- database_manager.py:741-742
COALESCE(NULLIF(i.work_drawing_no,''), i.src_drawing_no) AS drawing_no,
COALESCE(NULLIF(i.work_name,''),       i.src_name)       AS name,
```

Użytkownik, wpisując nazwę w arkuszu, zapisuje `work_name`. To natychmiast
zmienia wartość, po której sortuje `ORDER BY` — i wiersz wędruje. Objaw A
i objaw B to ta sama mechanika widziana z dwóch stron.

---

## 3. Stan faktyczny — co jest w bazach

| fakt | wartość | skąd |
|---|---|---|
| miejsc sortujących arkusz | **1** (`database_manager.py:794`) | grep po repo |
| baz projektów na stanowisku | **64** | `projects/project_*.sqlite` |
| hierarchia pozycji (parent/level) | **BRAK** — lista płaska | `PRAGMA table_info(items)` |

To, że sortowanie jest w jednym miejscu, a lista jest płaska (bez drzewa
podzespołów), sprawia, że zmiana jest technicznie prosta. Trudność leży
gdzie indziej — patrz §5.

### Kandydaci na „stałą kolejność", które JUŻ są w tabeli

| kolumna | project_22 | project_31 | project_28 | werdykt |
|---|---|---|---|---|
| `src_row` | 439/511 wypełnione, 434 różne | 316/389, **170 różnych** | 247/332, 231 różnych | ❌ dziurawa i **niejednoznaczna** — w project_31 prawie połowa wartości się powtarza |
| `rank` | **0/511** | **0/389** | **0/332** | ⚠️ istnieje, ale **nigdzie niewypełniona i nieużywana** |

`src_row` to numer wiersza w pliku źródłowym — nie nadaje się, bo pozycje
dodane ręcznie go nie mają, a przy imporcie z kilku plików numery się
powtarzają.

`rank` jest pustą kolumną w każdej sprawdzonej bazie. Wygląda na
przygotowaną pod dokładnie ten cel i nigdy nieużytą — **przed użyciem
trzeba potwierdzić, że nikt jej nie planuje do czego innego.**

---

## 4. Proponowane rozwiązanie

1. **Wypełnić kolejność raz** — każda istniejąca pozycja dostaje numer
   porządkowy zgodny z tym, jak arkusz wygląda **dzisiaj**.
2. **Sortować po tym numerze**, nie po treści. Zmiana nazwy czy numeru
   przestaje ruszać wiersz (objaw A znika).
3. **Nowe pozycje dostają numer większy od największego** — doklejają się
   na koniec (objaw B znika).

Kluczowa własność: po migracji arkusz wygląda **identycznie jak przed nią**.
Nic nie skacze w dniu wdrożenia; zmienia się tylko to, co dzieje się PÓŹNIEJ.

Do rozstrzygnięcia w ramach tego wariantu: użyć istniejącej kolumny `rank`
czy założyć nową (np. `sort_order`).

---

## 5. Skutki uboczne — to jest sedno decyzji

### 5.1 Arkusz przestanie być posortowany alfabetycznie

Dziś numery rysunków układają się rosnąco **same z siebie**, jako produkt
uboczny sortowania. Po zmianie kolejność będzie „historyczna": tak, jak
pozycje powstawały.

To jest realna strata dla kogoś, kto szuka pozycji wzrokiem, przewijając
listę. Sortowanie kliknięciem w nagłówek nadal będzie działać — ale
przestanie być stanem domyślnym po otwarciu projektu.

**To jest główne pytanie do osoby pracującej na arkuszu codziennie:**
czy alfabetyczna kolejność jest sposobem szukania pozycji, czy tylko
przypadkowym efektem, którego nikt nie używa?

### 5.2 Migracja dotyka 64 baz

Wykona się przy pierwszym otwarciu każdego projektu. Jest jednorazowa
i nieniszcząca — dochodzi wartość w kolumnie, nic nie znika, więc powrót
polega na przywróceniu starego `ORDER BY`.

### 5.3 Pozycje dołożone przestaną sąsiadować z pokrewnymi

Dziś pozycja `2627-100.15` dołożona później trafia obok `2627-100.14`.
Po zmianie wyląduje na końcu, z dala od reszty swojego zespołu. Dla części
dokładanych świadomie („dokładka do BOM-u") to może być gorsze niż obecne
zachowanie.

---

## 5.4 Czy zmiana kolejności rozjedzie powiązania z Subiektem? — NIE

Pytanie zadane wprost: *„jak są przypisywane pozycje z arkusza RM_BAZA do
Subiekta? wypadnie wiersz i wszystko się rozjedzie?"*

**Nie rozjedzie się. Powiązanie nie zna pojęcia „który to wiersz z kolei".**
Są dwa poziomy dopasowania i żaden nie zależy od kolejności:

| poziom | klucz | gdzie |
|---|---|---|
| arkusz ↔ kartoteka Subiekta | **symbol** (numer rysunku) | `dane_z_bom()` buduje mapę `{SYMBOL: …}` — `subiekt_zamowienia.py:289` |
| wewnątrz RM_BAZA (powrót „Zamówiono") | **`bom_ref` = (project_id, item_id)** | `subiekt_zamowienia.py:313` |

`item_id` to klucz główny z bazy — niezmienny, niezależny od sortowania,
nazwy i numeru rysunku. Komentarz w kodzie mówi to wprost:

> „`id` ZAWSZE ostatnie: para (project_id, item_id) to adres wiersza, pod
> który po wysyłce ZD wraca «Zamówiono». Symbol nie wystarczy"

`bom_ref` **nie jest wysyłany do Subiekta** — żyje wyłącznie po stronie
RM_BAZA.

### Co się dzieje, gdy wiersz faktycznie wypadnie

Ten przypadek jest już obsłużony, niezależnie od tej zmiany:

* **pozycja usunięta z BOM-u po wysyłce** — `subiekt_wyslij_zd.py:482`:
  `if stare is None: continue`, z komentarzem „pozycja usunięta z BOM-u
  po wysyłce". Nakładanie ją pomija;
* **wiersz bez `bom_ref`** — awaryjne szukanie po symbolu
  (`_refy_po_symbolu`), a gdy symbol występuje w kilku projektach naraz,
  kod **nie zgaduje**: zostawia flagę i mówi o tym użytkownikowi, zamiast
  odznaczyć coś w cudzym BOM-ie.

**Wniosek:** zmiana sortowania dotyka wyłącznie tego, w jakim porządku
wiersze są rysowane na ekranie. Klucze powiązań zostają nietknięte, więc
ryzyko dla integracji z Subiektem jest zerowe. Cała decyzja sprowadza się
do wygody pracy z arkuszem (§5.1), nie do poprawności danych.

## 5.5 A RFQ? — też bez wpływu, ale przy okazji wyszła osobna luka

Pytanie: *„a RFQ? jedzie po wierszu czy tą samą metodą?"*

**Ani jedno, ani drugie — RFQ ma WŁASNY klucz, inny niż ZD:**

| mechanizm | klucz powiązania | wrażliwy na |
|---|---|---|
| ZD / „Zamówiono" | `bom_ref` = (project_id, **item_id**) | nic — `item_id` jest niezmienne |
| **RFQ / wycena** | **`drawing_number`** + `project_number` | **zmianę numeru rysunku** |

Tabela `rfq_results` w master **nie ma kolumny `item_id`** — powiązanie
z arkuszem idzie po numerze rysunku (`RM_BAZA_v15_MAG_STATS_ORG.py:24142`).

**Dla kolejności wierszy to bez znaczenia** — sortowanie nie zmienia
numerów rysunku, więc RFQ jest tak samo odporne jak ZD.

### ⚠️ Ale: zmiana numeru rysunku zrywa powiązanie z RFQ

To osobna sprawa, niezwiązana z sortowaniem, wyszła przy okazji analizy.

Jeśli pozycja jest **w trakcie wyceny**, a ktoś poprawi jej numer rysunku
w arkuszu, wiersz w `rfq_results` przestaje do czegokolwiek pasować:
kooperanci dalej wyceniają starą pozycję, a arkusz jej nie widzi.

Ten sam rodzaj osierocenia jest już **opisany i zabezpieczony przy
KASOWANIU** pozycji (`RM_BAZA_v15_MAG_STATS_ORG.py:15055`):

> „Kasowanie w RM_BAZA nie usuwa pozycji z portalu — kooperanci dalej ją
> widzą i wyceniają, a wiersz w rfq_results osieroca się po cichu.
> Odwrotny kierunek (portal → RM_BAZA) jest zabezpieczony, ten nie był."

Przy kasowaniu użytkownik dostaje czerwone ostrzeżenie „te pozycje są
w zapytaniach ofertowych". **Przy zmianie numeru rysunku takiego
ostrzeżenia nie ma** — `_pozycje_w_rfq()` jest wołane wyłącznie z procedury
usuwania.

Naturalne domknięcie: to samo ostrzeżenie przy zmianie numeru rysunku
pozycji będącej w aktywnym RFQ. Osobne zadanie, nie część tej decyzji.

---

## 6. Warianty pośrednie

Gdyby pełna zmiana okazała się zbyt szeroka:

| wariant | co daje | czego nie daje |
|---|---|---|
| **A. Stała kolejność** (opisany wyżej) | znikają oba objawy | traci domyślne sortowanie alfabetyczne |
| **B. Sortowanie po ORYGINALE** — `src_drawing_no` zamiast wartości efektywnej | wiersz nie ucieka przy zmianie nazwy (objaw A) | nowe pozycje nadal wpadają w środek (objaw B); pozycje bez oryginału (ręczne) trafiają na jeden koniec |
| **C. Tylko przywracanie widoku** — po edycji arkusz przewija się z powrotem do zmienionego wiersza | wiersz nie ginie z oczu | wiersz nadal się przesuwa, sąsiedztwo się zmienia; nie pomaga na objaw B |
| **D. Nic nie zmieniać** | zero ryzyka | oba objawy zostają; pozycje ze schowka będą wpadać w środek arkusza |

Warianty **B** i **C** są tańsze i odwracalne, ale rozwiązują tylko połowę
problemu — a przy schowku montażowym (pozycje dokładane z magazynu) połowa
to za mało.

---

## 7. Kontekst: skąd to wypłynęło

Przy projektowaniu **schowka montażowego**
([[BUFOR_SCHOWEK_MONTAZOWY.md]]) pojawił się przypadek: monter bierze
element, którego **nie ma w BOM-ie** (smar, elektrody, śruby „z ręki").
Dziś okno wydania oznacza taką pozycję jako „POZA BOM" i zostawia ją tylko
na dokumencie RW. Ustalenie z 13.09.2026: ma **trafiać także do arkusza**.

Bez stałej kolejności każda taka pozycja rozjeżdżałaby arkusz w losowym
miejscu — i stąd to zgłoszenie.

---

## 8. Pytania do rozstrzygnięcia

1. **Czy alfabetyczna kolejność numerów jest komuś potrzebna** jako stan
   domyślny po otwarciu projektu? (§5.1 — to przesądza o całości)
2. Czy pozycje dokładane mają lądować **na końcu**, czy przy pokrewnych?
   (§5.3)
3. Czy kolumna **`rank`** jest wolna, czy zarezerwowana pod coś innego?
   (§3 — jest pusta we wszystkich sprawdzonych bazach)
4. Czy wystarczy wariant **B** (sortowanie po oryginale), skoro jest
   znacznie tańszy? (§6)
