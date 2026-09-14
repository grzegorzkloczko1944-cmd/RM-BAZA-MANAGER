# Półprodukty zakupowe pod rysunki — plan

Stan: **krok 1 (relacja) ZROBIONY 14.09.2026** — tabela, operacje serwera
i funkcje klienta gotowe i przetestowane (28 asercji, 0 błędów, na domowym
RM_SERWER). Kroki 2–5 (PPM, kalkulator, ZK, znacznik 🛒) — do zrobienia.

⚠️ **Wdrożenie: serwer PRZED buildem `.exe`** — nowy klient woła operacje
`map-polprodukt*`, których stary serwer nie zna.

## Problem

Część detali powstaje z **kupionego półfabrykatu**, nie z surowego materiału.
Rysunek `2621-100.61 — Koło 5M_40 fi38` opisuje detal wykonany z gotowego koła
zębatego 5M/40 pod pasek 25 mm, które kupujemy i dopiero obrabiamy (otwór
Ø38 H8). Dziś RM_BAZA nie wie, że pod tym rysunkiem kryje się zakup — logistyk
musi o tym pamiętać sam, a kalkulator nie ma skąd wziąć kosztu materiału.

Potrzebne są dwie rzeczy naraz, z jednego powiązania:

```
                  RELACJA (trwała, globalna)
       2621-100.61  ←──  powstaje z  ──→  KOLO-5M-40-25 (id 18452), 1 szt/detal
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
         KALKULATOR                      PROJEKT / ZK
     koszt materiału =              potrzeba = ilość detali
     cena półproduktu × 1           × ilość na sztukę
```

## Decyzje

| pytanie | decyzja | dlaczego |
|---|---|---|
| Kto jest właścicielem kartoteki półproduktu? | **Subiekt** | jedno źródło prawdy o towarze; RM_BAZA nie buduje drugiego świata magazynowego |
| Kto jest właścicielem relacji? | **RM_BAZA** | to wiedza konstrukcyjna („z czego powstaje detal"), nie magazynowa |
| Detal jako komplet (Z/ZZ) ze składnikiem? | **NIE — zamknięte** | patrz niżej |
| Pola własne Subiekta jako nośnik? | **NIE** (tylko jako ślad dla człowieka) | patrz niżej |
| Klucz relacji | **numer rysunku** | spójne z tabelą `mapowania`; konstruktor myśli numerami |
| Kto przypisuje | **konstruktor, PPM w arkuszu głównym** | wie z rysunku, robi raz; logistyk widzi wynik |

### ⛔ Dlaczego NIE komplet

Kuszące: Subiekt sam rozliczyłby zużycie koła przy wydaniu detalu. Odpada
z trzech powodów, każdy wystarczający:

1. **Typ kartoteki ustawia się przy ZAKŁADANIU** (`szablony.DaneDomyslne.Komplet`,
   `Kartoteka.cs:63`). Detale z zasiewu są TW — „awans" na komplet oznacza
   nową kartotekę.
2. **Detal figuruje już na ZK, RW i w historii dokumentów.** Podmiana kartoteki
   to rozjazd drzewek — dokładnie to, czego pilnuje panel „Decyzje" i
   `subiekt_zlozenia_gui`.
3. **Ten sam symbol bywa jednocześnie samodzielny i składnikiem**
   (`ANALIZA_ZK_DWA_ZRODLA_PRAWDY.md`, 6D.2b). Jako komplet traci to
   rozróżnienie, a ZK dostaje dwa źródła ilości dla jednej pozycji.

Obie kartoteki zostają TW i niezależne. Zużycia Subiekt nie rozlicza sam —
i nie musi, bo prawda o tym, co z czego powstaje, żyje w RM_BAZA.

### ⚠️ Dlaczego NIE pola własne

Most je obsługuje (`PolaWlasne.cs`, `PoleWlasne1` = położenie magazynowe,
2–8 wolne i edytowalne w `subiekt_edytor_gui`). Ale jako **źródło prawdy** się
nie nadają:

* **tekst zamiast `id`** — logistyk zmienia symbol kartoteki i relacja cicho
  pęka; `id` jest stabilne, symbol nie;
* **brak miejsca na ilość na sztukę** — `18452|1.000` w jednym polu to
  parsowanie przy każdym odczycie, a pole jest w GUI Subiekta edytowalne
  dla każdego;
* **odczyt = przelot przez Sferę** (setki ms, przy zimnej sesji ~9 s) zamiast
  ~20 ms z bazy mapowań. Kalkulator ma podpowiadać natychmiast.

Dopuszczalne jako **jednokierunkowy ślad dla człowieka**: przy zapisie relacji
dopisać w polu własnym kartoteki półproduktu `detale: 2621-100.61, 2740-100.12`,
żeby magazynier widział w Subiekcie, po co to koło leży. Nadpisywane przy
każdym zapisie — jeśli ktoś je zmieni, nic się nie psuje.

## Gdzie trzymać relację

**Baza mapowań na serwerze** — `C:\Apps\RM_SERWER\dane\subiekt_mapowania.sqlite`,
operacje z prefiksem `map-`. Ta sama, która trzyma dziś 863 mapowania
„numer rysunku → jego kartoteka".

Nowa tabela **obok** istniejących, nie zamiast:

| tabela | relacja |
|---|---|
| `mapowania` (jest) | numer rysunku → **jego własna** kartoteka |
| `aliasy_scalen` (jest) | stary symbol → kartoteka po scaleniu |
| **`polprodukty`** (nowa) | numer rysunku → kartoteka **półfabrykatu** + ilość |

Dlaczego nie gdzie indziej:

* **nie `items`** — ta tabela jest PER PROJEKT. Relacja ma być globalna:
  powiązanie zrobione w projekcie 2621 musi działać w 2740, inaczej kalkulator
  nie wyceni nowego projektu.
* **nie master** — inne przeznaczenie (projekty, użytkownicy, dostawcy).
* **nie osobny plik** — piąta baza do routingu i backupu bez powodu.

Infrastruktura już stoi: routing po prefiksie (`rm_serwer._polaczenie`),
migracje przy starcie, backup dzienny, klient (`subiekt_mapowania.py`).

### Schemat

```sql
CREATE TABLE IF NOT EXISTS polprodukty (
    numer_rysunku  TEXT NOT NULL,   -- klucz jak w `mapowania`: TRIM + wielkie litery
    id_subiekt     INTEGER NOT NULL,-- kartoteka półproduktu — ŹRÓDŁO POWIĄZANIA
    symbol         TEXT,            -- cache do wyświetlania; prawdą jest id
    nazwa          TEXT,            -- cache
    ilosc_na_szt   INTEGER NOT NULL DEFAULT 1,   -- SZTUKI, całkowite
    kto            TEXT,
    kiedy          TEXT NOT NULL,
    uwagi          TEXT,
    PRIMARY KEY (numer_rysunku, id_subiekt)
);
CREATE INDEX IF NOT EXISTS idx_polprodukt_subiekt ON polprodukty(id_subiekt);
```

⚠️ `ilosc_na_szt` jest **CAŁKOWITA** (decyzja 14.09.2026: *„sztuka to sztuka,
nic nie dzielimy"*). Kupujemy N sztuk półproduktu na 1 detal — zwykle 1.
Nie ułamki: docinany wałek to zakup CAŁEGO wałka, a nie 0,3 sztuki. Gdyby
kiedyś pojawił się materiał liczony metrami, będzie to inny mechanizm
(materiał ≠ półprodukt), nie zmiana typu tej kolumny.

Klucz złożony, nie sam `numer_rysunku`: **jeden rysunek może mieć więcej niż
jeden półprodukt** (dziś rzadko, ale struktura ma tego nie blokować — np.
detal z dwóch kupionych części). Indeks po `id_subiekt` dla pytania odwrotnego:
„w których rysunkach używane jest to koło".

⚠️ `symbol` i `nazwa` to **cache do wyświetlania**, nie klucz. Przy odczycie
sprawdzać, czy kartoteka o tym `id` nadal istnieje; gdy symbol się zmienił —
odświeżyć cache, nie zrywać relacji.

### Co przechowujemy, a czego NIE

Półprodukt ma w Subiekcie: **id, nazwę, opis, cenę, stan magazynowy i ilość
dostępną**. Rozróżnienie jest kluczowe:

| dane | gdzie | dlaczego |
|---|---|---|
| `id_subiekt`, `ilosc_na_szt` | **w relacji** (trwale) | to jest sama relacja — czego nie ma nigdzie indziej |
| `symbol`, `nazwa` | w relacji, ale jako **cache** | żeby arkusz pokazał coś sensownego bez pytania Subiekta; przy rozbieżności wygrywa Subiekt |
| **opis, cena, stan, dostępne, zarezerwowane** | **NIE przechowywać** — czytać na żywo | zmieniają się co godzinę; kopia w RM_BAZA po dniu kłamie |

Wyjątek, jedyny: **cena w ZAPISANEJ wycenie** (`calc_semi_price`). Tam
utrwalenie jest celowe — wycena sprzed pół roku ma pokazywać cenę z chwili
kalkulacji, nie dzisiejszą.

Most zwraca te dane gotowe, trybem `magazyn` / `stan` (`Magazyn.cs`):

```
Symbol, Nazwa, Opis, CenaEwidencyjna
Stany[]:   Magazyn, IloscDostepna, IloscZadysponowana   (zarezerwowana)
Zakresy[]: StanMinimalny, StanOptymalny
```

`subiekt_stany.query_stock(symbole)` woła to jednym żądaniem dla listy pozycji
— nie pytać per rysunek w pętli, tylko raz dla całego arkusza.

Okno podglądu relacji (po kliknięciu w pozycję) pokazuje wtedy:

```
Półprodukt zakupowy

  Symbol:     KOLO-5M-40-25          ← cache, odświeżany
  Nazwa:      Koło zębate 5M Z40 szer. 25
  Opis:       (z Subiekta, na żywo)
  Na detal:   1 szt.                 ← z relacji

  Cena:       42,00 zł               ┐
  Stan:       6 szt.                 ├ na żywo z Subiekta
  Dostępne:   4 szt.                 │  (2 zarezerwowane)
  Potrzeba projektu: 9 szt.          ┘

  [ Zmień powiązanie ]  [ Otwórz w Subiekcie ]
```

⚠️ **Do zapotrzebowania liczy się „dostępne", nie „stan"**. Stan 6 przy
2 zarezerwowanych znaczy, że do wzięcia są 4 — reszta jest już komuś
przypisana. `IloscZadysponowana` to właśnie ta rezerwacja.

### Operacje serwera

W `rm_serwer_operacje.py`, obok pozostałych `map-*`:

```
ODCZYT
  map-polprodukt           numer_rysunku            → wiersze dla jednego rysunku
  map-polprodukty-many     numery_json              → dla listy (json_each, jak map-get-many)
  map-polprodukt-gdzie     id_subiekt               → w których rysunkach użyty
ZAPIS
  map-polprodukt-zapisz    numer_rysunku, id_subiekt, symbol, nazwa,
                           ilosc_na_szt, kto, kiedy, uwagi   (UPSERT)
  map-polprodukt-usun      numer_rysunku, id_subiekt
```

Klucze normalizuje WOŁAJĄCY (`subiekt_mapowania._key`), jak przy `map-get` —
serwer nie normalizuje, żeby nie było dwóch różnych reguł.

## Wejście dla konstruktora

Menu PPM w arkuszu głównym (`popup_menu_add_command`, ok. linii 2344–2350):

```
Powrót do BOM
Pokaż złożenie
Karta pozycji (Subiekt, złożenie)
Powiąż półprodukt…            ← NOWE
Wyślij do RFQ
…
```

Okno: **ponownie użyć** `subiekt_scalanie_gui._szukaj_w_subiekcie`
(`subiekt_scalanie_gui.py:1087`) — szuka kartoteki po symbolu i nazwie, zwraca
`id` + symbol + nazwę. Dołożyć tylko pole **„ilość na 1 detal"** (domyślnie 1).

Dla pozycji BEZ numeru rysunku (ZNORMALIZOWANE) klucz liczyć tą samą regułą
co w dopasowaniu — `subiekt_projekt.symbol_z_nazwy` / `rozroznij_symbol` —
inaczej ten sam detal miałby tu inny klucz niż w pozostałych oknach.

## Kalkulator — wpiąć się w to, co JEST

⚠️ **Nie budować drugiego mechanizmu.** `items` ma już kolumny dodawane przez
`rmpak_calculator._ensure_calc_columns`:

```
calc_mode            tryb wyceny
calc_semi_price      cena półfabrykatu        ← JEST
calc_semi_name       nazwa półfabrykatu       ← JEST (tekst!)
calc_semi_supplier_id  dostawca               ← JEST
```

Czyli tryb półfabrykatu istnieje, ale trzyma **nazwę i cenę**, bez `id`
kartoteki. Do zrobienia:

1. dołożyć kolumnę **`calc_semi_subiekt_id`** (INTEGER) do listy w
   `_ensure_calc_columns`;
2. przy otwarciu kalkulatora dla pozycji: odczytać `map-polprodukt` po numerze
   rysunku i **podpowiedzieć** półprodukt (id, symbol, ilość);
3. **cenę pobrać z Subiekta na bieżąco** (`katalog` / karta pozycji), nie
   z relacji;
4. ⚠️ **przy ZAPISIE wyceny utrwalić cenę z chwili kalkulacji** w
   `calc_semi_price`. Wycena sprzed pół roku nie może się zmienić dlatego,
   że dziś koło kosztuje inaczej.

## ZK — agregacja po `id_subiekt`

Mechanizm ZK już działa i **nie wymaga przebudowy**: `subiekt_projekt` liczy
zapotrzebowanie z BOM-u, pomija detale robione u siebie (po dostawcy),
porównuje z żywym stanem ZK z Subiekta i **USTAWIA ilość** zamiast dopisywać
kolejne linie. Półprodukty wchodzą w ten sam przepływ.

Zasada: **relacja należy do zapotrzebowania projektu, nie do ZK.** Logistyk
dodaje/ogląda półprodukt niezależnie od tego, czy ZK już istnieje.

```
dla każdej pozycji BOM:
    jeśli ma półprodukt(y):
        dla każdego:  potrzeba = ilość_pozycji × ilosc_na_szt

grupuj po id_subiekt, sumuj        ← JEDNA pozycja na ZK, nie linia per rysunek
```

Przykład — trzy rysunki, jedno koło:

```
2621-100.61   4 szt. → KOLO-5M-40-25 × 1 = 4
2621-100.72   3 szt. → KOLO-5M-40-25 × 1 = 3
2621-140.20   2 szt. → KOLO-5M-40-25 × 1 = 2
                                     ────────
na ZK jedna pozycja:  KOLO-5M-40-25    9 szt.
```

Rozbicie „skąd 9 szt." zostaje **w RM_BAZA** (okno/podpowiedź), do Subiekta
idzie jedna zbiorcza pozycja. Bez tego ZK miałby trzy linie tego samego towaru.

⚠️ **Potrzeba ≠ do kupienia.** Od zapotrzebowania odjąć to, co już leży
na magazynie — liczone z **`IloscDostepna`**, nie ze stanu (stan 6 przy
2 zarezerwowanych daje 4 do wzięcia):

```
potrzeba projektu:   9 szt.
dostępne w magazynie: 4 szt.
już na ZK:           0 szt.
─────────────────────────────
do kupienia:         5 szt.
```

To ta sama zasada, którą stosuje okno „Zamówienia do dostawców" (kolumny
`Potrzeba / Na stanie / Rezerw. / Ze stanu / Kupić`) — półprodukty mają
wejść w istniejący mechanizm, nie obok niego.

## Kolejność wdrożenia

1. ~~**Relacja** — tabela + operacje serwera + funkcje w `subiekt_mapowania.py`~~
   **✅ ZROBIONE 14.09.2026.** Tabela `polprodukty` + indeks (migracje bazy
   mapowań); operacje `map-polprodukt`, `map-polprodukty-many`,
   `map-polprodukt-gdzie`, `map-polprodukt-zapisz`, `map-polprodukt-usun`,
   `map-polprodukt-przepnij`, `map-polprodukt-usun-po-scaleniu`; klient:
   `polprodukty()`, `polprodukty_many()`, `polprodukt_gdzie()`,
   `zapisz_polprodukt()`, `usun_polprodukt()`.
   Przy scalaniu kartotek `zapisz_scalenie` przepina też relacje — w TEJ SAMEJ
   transakcji, bez osobnego ostrzeżenia (zgodnie z sekcją „Kartoteka
   półproduktu nie znika"). Kolizja (rysunek ma już relację do celu)
   rozwiązana: `UPDATE OR IGNORE` + sprzątnięcie resztek po martwym `id`.
   ⚠️ `zapisz_scalenie` liczy teraz wynik **po nazwie operacji**, nie po
   pozycji w batchu (`wyniki[1::3]` przestało być prawdą po dołożeniu
   dwóch operacji półproduktów).
2. ~~**Wejście** — PPM „Powiąż półprodukt…" + okno wyboru + ilość na sztukę.~~
   **✅ ZROBIONE 14.09.2026.** `subiekt_polprodukt_gui.py` (nowy moduł):
   sekcja „Z czego powstaje ten detal" (powiązane + Zmień ilość / Usuń)
   i wyszukiwarka kartotek z polem „ile sztuk na 1 detal".
   W arkuszu: PPM „Powiąż półprodukt…" → `powiaz_polprodukt()`, klucz liczony
   tym samym `COALESCE` co `show_position_card`.
   ⚠️ Metody z okna scalania NIE dało się użyć ponownie — `_szukaj_w_subiekcie`
   i `_okno_szukania` są zrośnięte z jego stanem (`self.tree`, `self._katalog`,
   `self._subiekt`, `_refill`). Wspólne jest to, co samodzielne:
   `subiekt_scalanie.wczytaj_katalog_subiekta()` (cache z dysku → okno otwiera
   się natychmiast, pobranie z mostu w tle tylko gdy cache pusty)
   i `norm_kod()` do filtrowania.
   Blokada: nie można powiązać rysunku z kartoteką o tym samym symbolu —
   to ten sam detal, nie półprodukt.
3. **Kalkulator** — `calc_semi_subiekt_id`, podpowiedź, cena z Subiekta,
   utrwalenie przy zapisie.
4. **ZK** — agregacja po `id_subiekt` w budowaniu zapotrzebowania.
5. **Znacznik w kolumnie Δ** — patrz niżej.

## Widoczność w arkuszu: znacznik w Δ, ZERO nowych kolumn

⚠️ **Nie dokładamy żadnej kolumny.** Arkusz ma 67 kolumn i tksheet już przy
nich niedomaga (decyzja 14.09.2026). Informacja „ta pozycja ma półprodukt"
idzie **znacznikiem w istniejącej komórce Δ**, obok wyświetlanej wartości.

Kolumna Δ już działa dokładnie tym wzorcem (`RM_BAZA:8193-8212`):

```
PRODUKCJA:   delta + " ●"   gdy pozycja ręczna
WAREHOUSE:   samo "●"       gdy pozycja ręczna (delta bez sensu dla magazynu)
```

Dokładamy drugi znacznik — **🛒** (koszyk = „pod tym rysunkiem jest zakup"):

```
  0            zwykła pozycja
  0 ●          pozycja ręczna
  0 🛒         ma półprodukt
  0 ● 🛒       ręczna + ma półprodukt
  🛒           WAREHOUSE, ma półprodukt
```

Kolejność stała: `delta` → `●` → `🛒`. Znacznik dopisywany tak samo jak `●`,
czyli w `delta_disp`, bez ruszania szerokości kolumny.

**Skąd wiadomo, że pozycja ma półprodukt:** jedno zapytanie
`map-polprodukty-many` dla całego arkusza przy odświeżeniu (jak `get_many`
w dopasowaniu), wynik trzymany w pamięci jako zbiór numerów rysunku. Nie
pytać per wiersz.

**Szczegóły po kliknięciu** — okno podglądu relacji (sekcja „Co przechowujemy")
otwierane z PPM, z żywymi danymi z Subiekta. W arkuszu zostaje sam znacznik.

## Kartoteka półproduktu nie znika

Rozważane wcześniej ostrzeżenie „kartoteka zniknęła z Subiekta" jest
**niepotrzebne** (decyzja 14.09.2026): półprodukt to **zwykłe TW w kartotece
Subiekta**, takie samo jak każdy inny towar handlowy. Nic z nim się nie dzieje
— nie jest tworzony ani kasowany przez RM_BAZA, żyje własnym życiem jak
łożysko czy pasek.

Jedyny realny przypadek to **scalenie duplikatów** przez edytor kartotek —
a to obsługuje mechanizm, który już istnieje: `aliasy_scalen` leżą w TEJ SAMEJ
bazie, obok `polprodukty`. Przy scalaniu przepiąć `id_subiekt` tak samo, jak
`zapisz_scalenie` przepina dziś `mapowania` (`map-przepnij-symbol`). Jedna
linia w tej samej transakcji, bez osobnego ostrzeżenia dla użytkownika.
