# RMPAK — produkcja detali: PW / RW

**Data:** 2026-09-09
**Temat:** przepływ detali produkowanych wewnętrznie przez RMPAK — kalkulacja → PW → RW
**Dotyczy:** `RM_BAZA_SUBIEKT_PRZEPLYW_PRODUKCJI_RMPAK_v2.md`
**Status:** ustalenia z rozmowy — obowiązują tam, gdzie różnią się od v2

v2 opisuje przepływ w całości i pozostaje w mocy. Ten dokument zbiera
rozstrzygnięcia, stan faktyczny kodu i poprawki do v2. **Gdzie oba się
różnią, obowiązuje ten.**

---

## 1. Punkt wyjścia

W RM_BAZA istnieje **Kalkulator RMPAK** (`rmpak_calculator.py`, 874 linie).

Kalkulator pokazuje listę pozycji produkcyjnych projektu, tworzoną na
podstawie dostawcy, z kolumnami: numer rysunku, nazwa, ilość, status, czas,
materiał, dodatkowe koszty, stawka, cena/szt., wartość partii, dostawca.
Pozwala wyliczyć i zapisać cenę detalu.

Na dziś istnieją dwa oznaczenia dostawcy — `RMPAK` i `RMPAK+`. Docelowo ma
pozostać **jeden: `RMPAK`**, a różnica „materiał cięty / półprodukt" zostaje
jako **tryb kalkulacji**, nie drugi dostawca.

> **Tryb technologiczny nie jest dostawcą.**

W kodzie ten podział JUŻ istnieje: `calc_mode` (`cut` / `semi`,
`rmpak_calculator.py:43`) obok `rmpak_cut_id` / `rmpak_semi_id`. Migracja to
jedno zdanie: pozycje z `RMPAK+` przestawić na `RMPAK`, tryb czytać
z `calc_mode`.

---

## 2. Najważniejsze rozstrzygnięcie: BOM, nie ZK

Dla produkcji własnej **nie używamy ZK jako źródła ilości**. Źródłem jest
**PROJEKT / BOM**.

### Dlaczego

ZK to zamówienie do kontrahenta — znaczy „zamawiam u kogoś". RMPAK jest
producentem i nie zamawia u siebie. Wpisywanie własnych detali na ZK po to,
żeby przechować ilość, to używanie dokumentu handlowego jako magazynu na dane
produkcyjne. Skutki: zapotrzebowanie i raporty zakupowe pokazują własne
detale jako coś do kupienia, a rozróżnienie „kupione vs zrobione" znika
z Subiekta.

PW jest dokumentem przychodu z produkcji. Jego ilość to „ile sztuk
wytworzyliśmy", co wynika z projektu. Nie z zamówienia, którego nie ma
i nie powinno być.

Argument praktyczny, mocniejszy od porządku pojęciowego: **przy ilości z ZK
PW nigdy by nie powstało.** Własne detale nie trafiają na ZK, więc
`order_qty` byłoby puste dla całej listy RMPAK i „Wystaw PW" nie miałoby
czego pokazać.

### Zgodność z zasadą „jedno źródło prawdy dla ilości"

Zasada nie jest naruszona — dotyczy pozycji KUPOWANYCH, gdzie Subiekt jest
właścicielem ilości, bo tylko on wie, ile realnie zamówiono. Dla pozycji
PRODUKOWANYCH właścicielem jest projekt, bo nikt inny tej liczby nie zna.
Jedna reguła, zależna od toru:

```text
Dostawca ≠ RMPAK          Dostawca = RMPAK
    → tor zakupowy            → tor produkcji własnej
    → ZK / Subiekt            → BOM / projekt
```

---

## 3. Dwa niezależne tory

```text
                         BOM PROJEKTU
                              │
             ┌────────────────┴────────────────┐
             ▼                                 ▼
      PRODUKCJA WŁASNA                      ZAKUP
      Dostawca = RMPAK                 Dostawca ≠ RMPAK
             │                                 │
             ▼                                 ▼
     Kalkulator RMPAK                         ZK
             │
             ▼
            PW  ──read-back──►
             │
             ▼
            RW  ──read-back──►
             │
             ▼
       projekt / maszyna
```

ZK nie bierze udziału w torze produkcji własnej.

---

## 4. Szkic magazyniera

Magazynier rozpisał proces odręcznie (`C:\iLogic\Kalkulator.jpg`):

```text
KALKULATOR RMPAK → wybór detalu → uzupełnienie materiału/czasu
    → ZAPISZ CENĘ/SZT. → SUBIEKT → PW
      „w cenach i ilościach zawartych w projekcie" + uwaga z nr projektu
    → SUBIEKT → RW
      „na wcześniejszy dokument PW" + uwaga z nr projektu
```

Kluczowe zdanie: **„PW w cenach i ilościach zawartych w projekcie"**.
Wynika z niego jednoznacznie:

```text
CENA PW   → z Kalkulatora RMPAK
ILOŚĆ PW  → z projektu / BOM        (nie z ZK)
```

Sformułowanie jest poprawne merytorycznie, nie tylko potocznie — pokrywa się
z §2.

Druga część — **„RW na wcześniejszy dokument PW"** — znaczy, że RW nie wraca
po ilości do BOM-u ani do ZK, tylko bazuje na potwierdzonym PW.

---

## 5. Znaczenie „Zapisz cenę/szt."

Przycisk oznacza wyłącznie **zapis kalkulacji ceny detalu w RM_BAZA**.

Nie oznacza: wykonania detalu, przyjęcia na magazyn, wystawienia PW ani
zapisu czegokolwiek do Subiekta. Kalkulację można poprawiać wielokrotnie
przed wystawieniem dokumentu magazynowego.

To sedno całego rozdzielenia: **kalkulacja jest odwracalna, dokument
magazynowy nie.**

---

## 6. Jedna partia

Założenie: produkcja idzie jedną partią. Nie wdrażamy produkcji częściowej.

```text
1 projekt → 1 kompletna partia RMPAK → 1 PW → 1 RW
```

Pełny przebieg:

```text
RM_BAZA — projekt
    ↓ lista pozycji Dostawca = RMPAK
Kalkulator RMPAK
    ↓ wyliczenie cen → Zapisz cenę/szt.
wszystkie ceny gotowe
    ↓
Wystaw PW → Subiekt — PW → read-back / kontrola
    ↓
Wystaw RW (z potwierdzonego PW) → Subiekt — RW → read-back / kontrola
    ↓
proces RMPAK zakończony
```

---

## 7. Lista produkcyjna

Nie tworzymy drugiej listy. **Istniejąca lista Kalkulatora RMPAK JEST listą
produkcyjną projektu.** Powstaje na podstawie dostawcy: dziś `RMPAK` +
`RMPAK+`, docelowo samo `RMPAK`.

---

## 8. Filtr GUI nie może zmieniać PW

Kalkulator ma filtry widoku („Tylko niedostarczone", szukanie, zakres cen),
więc user może widzieć część listy.

> **PW nie może być tworzone z aktualnie widocznych wierszy Treeview.**

Treeview to tylko widok. Źródłem dokumentu PW jest **pełna lista pozycji
projektu z bazy**, `WHERE Dostawca = RMPAK` (przejściowo `RMPAK + RMPAK+`).

---

## 9. Detale RMPAK a ZK

Pozycje produkcji własnej **nie trafiają jako pozycje dokumentu ZK**.

### Co jest produkcją własną — dwie drogi

```text
1. Dostawca = RMPAK / RMPAK + materiał   → nasze (dowolny typ, także TW)
2. Złożenie Z/ZZ BEZ wskazanego dostawcy → nasze
```

Punkt 2 wynika z tego, jak firma pracuje: **RMPAK z elementów TW składa ZZ**,
więc złożenie z definicji powstaje przez składanie, a składamy u siebie.
Pustego pola przy komplecie nie czytamy jako „nie wiadomo" — znaczy ono, że
nikt tego nie dostarcza, bo robimy to sami.

**Wyjątek — zespół kupowany gotowy:** gdy przy złożeniu wpisano REALNEGO
dostawcę (np. MAJA), zostaje na ZK. To świadoma decyzja człowieka wyrażona
w polu, które już istnieje i już znaczy „kto to dostarcza" — nie dokładamy
drugiego mechanizmu obok.

Skala na projekcie 22 (484 pozycji w planie):

```text
produkcja własna   84   = 43 detale TW + 41 złożeń
na ZK             400   w tym 9 złożeń kupowanych gotowych (dostawca MAJA)
```

Reguła mieszka w `subiekt_produkcja.czy_produkcja_wlasna()` — jedno miejsce,
żeby nie rozjechała się między oknem projektu a kalkulatorem.

Ale krytyczne zastrzeżenie: **nie wolno usuwać ich z pełnego planu
projektu / BOM**, bo mogą być składnikami kompletów KT.

```text
PEŁNY PLAN PROJEKTU
       ├──► kartoteki + składy KT   →  RMPAK ZOSTAJE (drzewko pełne)
       ├──► pozycje ZK              →  RMPAK POMIJAMY
       └──► pozycje PW              →  tylko RMPAK, ilość z projektu
```

**Filtr RMPAK stosujemy dopiero przy tworzeniu pozycji dokumentu ZK.
Nie przy budowie planu ani składów KT.**

### Dlaczego to bezpieczne — sprawdzone w kodzie

Obawa „ZK będzie miało niepełne KT" jest nietrafiona. W `Projekt.cs` skład
kompletu i pozycje ZK to dwie różne ścieżki:

* `Skladniki` → budowa kartoteki KT w Subiekcie (drzewko)
* `Pozycje.Dodaj(sym, ilosc)` → wiersze na dokumencie ZK

Na ZK idą wszystkie pozycje planu PŁASKO — komplety i detale jako osobne
wiersze. Skład służy wyłącznie do zbudowania kartoteki, nie do zamówienia.

Gdyby jednak wyciąć detale RMPAK z `plan.Pozycje`, zniknęłyby też ze składu
kompletów — dokładnie ten błąd, który naprawiały `4270403` i `d5174c2`.
Stąd zastrzeżenie powyżej.

### Stan faktyczny — WDROŻONE

`read_project_items()` czyta `supplier_id` i ustawia flagę `produkcja_wlasna`,
która wędruje przez plan do mostu jako `PozPlan.ProdukcjaWlasna`. `Projekt.cs`
pomija te pozycje **wyłącznie w pętli dodającej wiersze na dokument ZK**
(linia ~449) — budowa kartotek i składów kompletów dzieje się w osobnej pętli
znacznie wyżej (~150–320) i filtra tam nie ma.

Sprawdzone na projekcie 22: złożenia produkcji własnej zostają w planie
z pełnym składem, więc drzewko w Subiekcie się nie rozpada.

---

## 10. PW

PW jest zbiorczym przyjęciem produkcji własnej.

```text
PW — projekt 2641

2641-100.10    10 szt. × cena kalkulacyjna
2641-100.20     4 szt. × cena kalkulacyjna
2641-110.01     2 szt. × cena kalkulacyjna
```

```text
symbol       → z projektu
ilość        → z projektu / BOM
cena/szt.    → z Kalkulatora RMPAK
uwagi        → numer projektu, np. „RM_BAZA — PROJEKT 2641"
```

### PW przyjmuje TW, nie KT

RMPAK z elementów TW składa ZZ — czyli z towarów robi u siebie komplet.
W Subiekcie odwzorowuje to kartoteka KT, której stan **wynika ze stanu
składników**; własnego stanu komplet nie ma.

Dlatego na PW idą **wyłącznie pozycje TW (STANDARD / X / XX)**. Złożenia
Z/ZZ są pomijane: przyjęcie kompletu obok jego części znaczyłoby przyjęcie
tego samego dwa razy.

Skala na projekcie 22 (507 pozycji, 59 produkcji własnej):

```text
STANDARD (TW)  43   → na PW
Z / ZZ (KT)    16   → pomijane, powstają ze składników
```

Komplet nadal ma pełny skład w Subiekcie — filtr ZK (§9) celowo nie rusza
budowy kartotek ani składów.

### Cena jako snapshot

Cena na PW jest stanem z chwili wystawienia. Gdy kalkulacja zmieni się
później z 90 na 97 PLN, **starego PW nie zmieniamy**.

---

## 11. RW

RW powstaje **z wcześniejszego potwierdzonego PW**. Nie budujemy go ponownie
z aktualnego BOM-u ani z ZK.

```text
PW: 2641-100.10 ×10, 2641-100.20 ×4
        ↓ staje się źródłem
RW: 2641-100.10 ×10, 2641-100.20 ×4
```

Dzięki temu PW i RW nie rozjadą się, nawet jeśli ktoś później zmieni dane
projektu.

---

## 12. GUI

Do istniejącego Kalkulatora RMPAK dokładamy tylko sekcję:

```text
DOKUMENTY PRODUKCJI — SUBIEKT

PW: —                    RW: —

[ WYSTAW PW ]            [ WYSTAW RW ]
```

Stany przycisków:

| Stan | PW | RW | Wystaw PW | Wystaw RW |
|---|---|---|---|---|
| przed | — | — | aktywny | nieaktywny |
| po PW | PW 123/2026 | — | nieaktywny / pokaż istniejący | aktywny |
| po RW | PW 123/2026 | RW 87/2026 | nieaktywny | nieaktywny — PROCES ZAKOŃCZONY |

---

## 13. Bezpieczeństwo zapisu do Subiekta

Każdy zapis:

```text
1. odczyt stanu przed
2. pokazanie planu użytkownikowi
3. świadome potwierdzenie
4. zapis
5. read-back
6. porównanie
7. sukces dopiero po zgodności
```

**Nie wolno:**

* milcząco pomijać pozycji — dotyczy KAŻDEJ ścieżki, nie tylko ZK,
* uznawać operacji za udaną tylko dlatego, że nie było wyjątku,
* automatycznie tworzyć drugiego PW/RW po timeout.

Pozycja RMPAK pominięta na ZK musi być WIDOCZNA w raporcie ze statusem
w rodzaju „produkcja własna — pomijam na ZK". Inaczej user zobaczy, że
z 30 pozycji dopisało się 22, i nie będzie wiedział dlaczego.

### Wykrywanie duplikatu — po Id, nie po tekście

v2 §11/§17 proponuje szukanie istniejącego PW po markerze w `Uwagi`
(`RM_BAZA | PROJEKT=2641 | PW`). To kruche — zawiedzie, gdy ktoś edytuje
uwagi ręcznie w Subiekcie.

**Lepszy wzorzec, już stosowany w tym repo:** `ce8cf4a` („Dziennik wysyłek
kluczowany Id dokumentu zamiast numerem") i `013d98a` („tryb dokumenty
zwraca Id dokumentu"). Zapisywać **Id dokumentu**; marker w uwagach
traktować jako pomoc dla człowieka, nie jako klucz.

---

## 14. Kartoteka w Subiekcie

Jeżeli detal RMPAK nie ma kartoteki:

* nie wolno go cicho pominąć,
* przed PW ma być twarda informacja,
* kartotekę można założyć z poziomu Kalkulatora RMPAK.

**Nie ma potrzeby dodawania detalu RMPAK na ZK** — to wynika z §2.

### Stan faktyczny

`okno_nowa_kartoteka(parent, symbol, nazwa, rodzaj, po_zapisie)`
(`subiekt_asortyment.py:96`) jest gotowe i podpięte już w czterech miejscach
tym samym wzorcem — m.in. `subiekt_projekt.py:2640`,
`subiekt_zamowienia.py:1745`. W kalkulatorze wystarczy to samo, z wypełnionym
symbolem i nazwą z zaznaczonej pozycji.

Kontrola przed PW powinna nie tylko mówić „brak kartoteki", ale dawać
przycisk „Załóż" przy każdej takiej pozycji — inaczej user krąży między
oknami.

Wejście „Dodaj asortyment" w głównym oknie
(`RM_BAZA_v15_MAG_STATS_ORG.py:30304`) **zostaje bez zmian**.

### Uwaga historyczna

W trakcie rozmowy padła słuszna uwaga: „dodać do kartoteki to jedna, ale
trzeba też wrzucić na ZK" — bo przy ilości z ZK sama kartoteka niczego nie
załatwiała. Po ustaleniu §2 (ilość z projektu) ten krok **odpada**.

---

## 15. Blokada drugiego PW — miękka, nie twarda

Proces normalny: `1 projekt = 1 PW = 1 RW`. Produkcji częściowej nie
implementujemy.

Ale jeżeli wyjątkowo trzeba dorobić detal po PW, system nie może prowadzić
usera w ślepą uliczkę. Normalnie:

```text
PW już istnieje → pokaż istniejący dokument
```

Ewentualna korekta powinna wymagać świadomego działania. Twarde „nie da się"
skończy się wystawianiem PW ręcznie w Subiekcie — i utratą kontroli.

---

## 16. Cena w moście — brakuje, do dołożenia

**Stan faktyczny:** `Pw.cs` ISTNIEJE (214 linii), jest zarejestrowany
w `CommandDispatcher.cs` (tryby `pw` i `rw`), ale NIE przyjmuje ceny:

```csharp
internal record PozPlan(string? Symbol, decimal Ilosc);   // Pw.cs:211
```

Do rozszerzenia o `decimal? Cena` plus ustawienie jej na pozycji dokumentu
w Sferze.

### PW powstało do czego innego

Obecne `Pw.cs` napisano pod inwentaryzację magazynu nr 2 i **pomija pozycje
bez kartoteki**. Dla produkcji RMPAK to zła domyślna — detal bez kartoteki
ma być twardym błędem przed PW, nie cichym pominięciem (§13, §14).

### Kto mnoży

Do rozstrzygnięcia: czy RM_BAZA wysyła cenę i ilość, a Subiekt liczy
wartość. Przy zaokrągleniach `10 × 90,005` może dać inny grosz niż RM_BAZA
i read-back fałszywie zaalarmuje. **Propozycja:** porównywać cenę i ilość,
wartość tylko informacyjnie.

---

## 17. Do technicznego sprawdzenia przed wdrożeniem

### 17.1. Kanoniczne pole ilości projektu

Trzeba wskazać, które pole RM_BAZA jest właściwą ilością produkcyjną.
Dla RMPAK **nie używamy `order_qty`**.

`read_project_items` czyta dziś `COALESCE(order_qty, work_qty, src_qty)`
(`subiekt_projekt.py:150`) — dla PW to ZŁA kolejność, bo `order_qty` jest
pierwsze. Dla pozycji RMPAK czytać `COALESCE(work_qty, src_qty)`
z pominięciem `order_qty`.

### 17.2. Cena na pozycji PW przez Sferę

Małym testem sprawdzić, jak poprawnie ustawić cenę pozycji PW.
**To jedyne miejsce, gdzie nie ma pewności, czy Sfera pozwoli** — musi być
zweryfikowane PRZED budowaniem GUI, żeby nie powstało pod założenie, które
nie przejdzie.

Zmiana kolejności wobec v2 §29: Etap 3 pkt 8 („obsługa PW w moście") ma być
**pierwszy**, nie trzeci.

### 17.3. Magazyn

`Pw.cs` przyjmuje `"magazyn": "MASTER"` w planie. Trzeba ustalić:

* na który magazyn trafia PW produkcji RMPAK,
* z którego magazynu wykonywane jest RW.

Do rozstrzygnięcia z magazynierem przed Etapem 2.

---

## 18. Sekcje v2 do skrócenia lub usunięcia

* **§24 `Produkcja.cs`** — niepotrzebny nowy plik. Rozszerzyć istniejące
  `Pw.cs` / `Rw.cs`, inaczej powstaną dwie ścieżki do tego samego typu
  dokumentu.
* **§2 wielki schemat ASCII** — powiela §30 i §27. Trzy diagramy tego samego
  przepływu to trzy miejsca do aktualizacji.
* **§4.2–4.4 i §20.3 (`RMPAK+`)** — cztery sekcje o jednym; patrz §1 tutaj.
* **§6 kalkulator materiału** — już zaimplementowany
  (`material_calculator.py`, 272 linie). Sekcja opisuje stan istniejący
  jako plan.

---

## 19. Co w v2 jest dobre i zostaje

* **§7** — rozdzielenie „Zapisz cenę/szt." od PW.
* **§4.5** — filtr widoku ≠ źródło dokumentu. Najważniejszy punkt v2.
* **§15** — RW z potwierdzonego PW, nie z BOM-u.
* **§12/§26** — read-back. Ten sam wzorzec co `de944c0` („zd-usun weryfikuje
  usunięcie zamiast ufać `Usun()`").
* **§14** — cena na PW jako snapshot.

---

## 20. Ostateczny model

```text
                          RM_BAZA / BOM
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
       POZYCJE KUPOWANE               DOSTAWCA = RMPAK
              │                               │
              ▼                               ▼
             ZK                       KALKULATOR RMPAK
                                              │ cena/szt.
                                              ▼
                                             PW
                                              │ read-back
                                              ▼
                                             RW
                                              │ read-back
                                              ▼
                                       PROJEKT / MASZYNA
```

---

## 21. Wszystkie ustalenia w jednym miejscu

| Temat | Ustalenie |
|---|---|
| Źródło ilości RMPAK | **projekt / BOM**, nie ZK |
| RMPAK na ZK | **nie** — nie zamawiamy u siebie |
| RMPAK w składzie KT | **tak, zostaje** — drzewko pełne |
| Co jest produkcją własną | dostawca RMPAK **albo** złożenie Z/ZZ bez wskazanego dostawcy |
| Złożenie kupowane gotowe | wpisz realnego dostawcę przy Z/ZZ → wraca na ZK |
| Filtr RMPAK | tylko przy pozycjach ZK, nigdy przy budowie planu |
| Raport ZK | pominięte pozycje RMPAK muszą być widoczne |
| Cena PW | z Kalkulatora RMPAK; `Pw.cs` wymaga rozszerzenia o `Cena` |
| Ilość PW | z projektu — `COALESCE(work_qty, src_qty)`, bez `order_qty` |
| Co wchodzi na PW | **tylko TW** (STANDARD/X/XX); złożenia Z/ZZ pomijane — KT powstaje ze składników |
| RW | z potwierdzonego PW, **bez wpisywania ceny** |
| Wartość RW | **koszt magazynowy** — liczy go Subiekt z ceny przyjęcia (nie cena netto, ta zostaje 0) |
| Lista produkcyjna | istniejąca lista Kalkulatora RMPAK |
| Filtry GUI | nie wpływają na zawartość PW |
| Brak kartoteki | zakładać z kalkulatora; krok „wrzuć na ZK" **odpada** |
| Duplikat dokumentu | wykrywać po **Id**, nie po tekście w `Uwagi` |
| Produkcja częściowa | nie wdrażamy |
| Liczba PW/RW | normalnie 1 PW + 1 RW; blokada **miękka** |
| RMPAK+ | stan przejściowy; docelowo jeden `RMPAK` |
| Półprodukt | tryb kalkulacji (`calc_mode`), nie osobny dostawca |
| Zapis do Subiekta | plan → potwierdzenie → zapis → read-back |
| Kolejność prac | most/cena **najpierw**, GUI potem |
