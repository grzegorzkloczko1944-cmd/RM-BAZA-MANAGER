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
4. ~~**ZK** — agregacja po `id_subiekt` w budowaniu zapotrzebowania.~~
   **✅ ZROBIONE 14.09.2026.** `subiekt_projekt.pozycje_polproduktow(pozycje)`
   + `pozycje.extend(...)` w `build_plan` — półprodukty dokładane PO
   zbudowaniu pozycji, bo liczą się z ich ilości. Agregacja po `id_subiekt`
   (4+3+2 = 9 → jedna pozycja na ZK), rozbicie „skąd 9" zostaje w polu
   `polprodukt_dla` (tylko do wyświetlenia).
   Pominięte: kartoteka, która JUŻ jest pozycją BOM-u (ten sam symbol bywa
   samodzielny i składnikiem) — inaczej liczyłaby się dwa razy.
   Brak serwera nie blokuje zapisu projektu: półproduktów po prostu nie ma.
   Most: suchy przebieg potwierdza `kartoteka … istnieje` (kupowany towar,
   nic nie zakładamy) i `zk … do-utworzenia`.
5. ~~**Znacznik w kolumnie Δ**~~ **✅ ZROBIONE 14.09.2026.** `_ma_polprodukt`
   — zbiór kluczy wczytywany JEDNYM `polprodukty_many()` przed pętlą wierszy
   (obok `rfq_by_drawing`), znacznik 🛒 doklejany w `delta_disp` po `●`.
   Brak serwera nie blokuje arkusza: znacznika po prostu nie ma.
   Okno powiązania po zapisie potwierdza i zamyka się, a arkusz odświeża się
   callbackiem `po_zmianie` — inaczej znacznik pojawiałby się dopiero przy
   następnym odświeżeniu i user nie wiedział, czy powiązanie weszło.

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

## Wiersz półproduktu w arkuszu (dodane 14.09.2026)

⚠️ **Luka w pierwotnym planie.** Plan przewidywał tylko znacznik 🛒 na
rysunku-rodzicu, więc półprodukt trafiał na ZK, ale w BOM-ie nie miał
wiersza: logistyk widział na zamówieniu towar, którego nie ma w arkuszu,
„Ilość (zam.)" nie miała gdzie się pokazać, a „Ilość dostarczonych"
i odczyt wydań z Subiekta nie miały do czego się przypiąć.

Decyzja użytkownika: **wiersz ma być** — to zmienia ilości BOM-u tylko
w „płaskiej gałęzi", która nie ma wpływu na drzewko.

`subiekt_polprodukt_bom.zsynchronizuj(con, project_id, pozycje)`:

* wiersz `is_manual=1` — SPOZA DRZEWKA, jak pozycje ręczne i ze schowka;
  Inventor go nie zna, więc „Przelicz" korzeni go nie dotyka;
* nazwa z kartoteki Subiekta, **numer pusty** (to towar handlowy, nie
  rysunek), symbol kartoteki w `subiekt_symbol`, ilość z relacji;
* notatka `półprodukt do: 2609-100.07 (3 szt.)` — mówi, skąd ta ilość;
* ⚠️ rozpoznanie własnego wiersza idzie po `subiekt_symbol`, NIE po nazwie:
  wiersz zakłada się z nazwą kartoteki w polu nazwy, więc szukanie po
  samym symbolu nie trafiało we własny wpis i każde wywołanie dokładało
  DUPLIKAT (złapane testem 14.09.2026);
* aktualizuje tylko wiersze z własną notatką — cudzego „Ilość (zam.)"
  nie nadpisuje.

**Edycja zablokowana** (`_wiersz_polproduktu` + warunek w `on_cell_edited`,
przed pozostałymi blokadami): numer, nazwa i obie ilości. Właścicielem tych
pozycji jest Subiekt i relacja — ręczna zmiana nazwy zerwałaby powiązanie
z kartoteką, a ilość i tak zostałaby nadpisana przy najbliższym zapisie
projektu. Komunikat kieruje do PPM „Powiąż półprodukt…" na rysunku-rodzicu.

## Okno powiązania — zasady (14.09.2026, po testach użytkownika)

* **NIC nie zapisuje się samo.** „Powiąż", „Zmień ilość" i „Usuń" odkładają
  zmianę do BUFORA w pamięci — górna tabela pokazuje ją na żółto ze znacznikiem
  „← nowy / zmiana / do usunięcia". Do bazy idzie dopiero **„Zapisz"**, jedną
  paczką. Zamknięcie okna z niezapisanym buforem pyta, czy porzucić.
* **„Zapisz" robi CAŁĄ procedurę**, bez pytań pośrednich: relacje → wiersze
  w arkuszu (`po_zmianie`) → ilości na ZK. Most ustawia ilość WPROST
  (`UstawIlosc`), więc zmniejszenie „na 1 detal" obniża też pozycję na ZK.
* **Okno NIE jest modalne** — bez `grab_set()`, arkusz działa równolegle.
* **Kopiowanie do schowka** z obu list: Ctrl+C, Ctrl+A i menu pod PPM
  („Kopiuj symbol" / „Kopiuj symbol i nazwę") — symbole kartotek przepisuje
  się do Subiekta i do maili.
* Komunikat przy braku zaznaczenia mówi wprost o **DOLNEJ** liście: w oknie
  są dwie tabele i user miał zaznaczony wiersz w górnej.

## Pozycje z ZK → arkusz (brakujący mechanizm, 14.09.2026)

⚠️ **Tego w kodzie NIE BYŁO.** `_zapisz_ilosci_z_subiekta` szło po wierszach
ARKUSZA i pytało, ile jest na ZK — pozycja obecna na zamówieniu, ale bez
wiersza w BOM-ie, nie miała jak się pojawić. Istniał tylko kierunek
„arkusz → sprawdź ilość na ZK". Półprodukty są pierwszym przypadkiem, gdy na
ZK trafia coś, czego w BOM-ie nie ma, więc luka wyszła dopiero teraz.

`_dopisz_pozycje_z_zk(con, ilosci, trafione, teraz)` — wołane na końcu
`_zapisz_ilosci_z_subiekta`, czyli **przy przejmowaniu locka** (zwykłym
i wymuszonym). Dotyczy KAŻDEJ pozycji z ZK, nie tylko półproduktów —
dopisana ręcznie w Subiekcie też się pojawi. Nazwy kartotek jednym
`query_stock`, wiersz `is_manual=1`, numer pusty, symbol w `subiekt_symbol`,
notatka `z zamówienia ZK`. Raport z listą — nic po cichu.

### Znacznik pochodzenia 📦 w kolumnie Δ

Decyzja użytkownika: **znacznik pochodzenia ma być w Δ**, tak jak 🛒.

```
  0 🛒     pod tą pozycją jest ZAKUP półfabrykatu (rysunek-rodzic)
  0 📦     ta pozycja PRZYSZŁA z Subiekta — arkusz jej nie prowadzi
```

`_czy_z_subiekta(item)` to **jedna reguła** dla znacznika i dla filtra
wysyłki, żeby user widział dokładnie to, co jest pomijane: `is_manual=1`
+ BRAK numeru rysunku + `subiekt_symbol` + ślad pochodzenia (symbol znany
z relacji półproduktów albo notatka `z zamówienia ZK`).

⚠️ **Sam `subiekt_symbol` NIE wystarcza** — ma go 213 z 218 pozycji projektu
3500, bo dostaje go każdy detal zasiany do Subiekta. „Symbol bez numeru" też
nie: to 51 pozycji ZNORMALIZOWANYCH (łożyska, paski), które zamawiamy
normalnie. Bez śladu pochodzenia warunek odsiewał też ręcznie dodaną pozycję
`3333`, która wcześniej normalnie szła na ZK.

### ⛔ Ochrona przed zapętleniem

Wiersz dopisany z ZK ma **pusty numer rysunku**, więc `build_plan` policzyłby
mu symbol z NAZWY (`symbol_z_nazwy`): `M3 Z28 koło wrzeciona` → `M3Z28kolowrze`
— **inny niż prawdziwa kartoteka** `2430-300.57`. Most założyłby DRUGĄ
kartotekę obok istniejącej i dopisał ją na ZK, przy każdym przebiegu.

`read_project_items` pomija więc wiersze z `notes = 'z zamówienia ZK'`
oraz `notes LIKE 'półprodukt%'`: **pozycje pochodzące z Subiekta nie wracają
do Subiekta**. Półprodukty i tak liczą się osobno, z relacji.
Sprawdzone: trzy kolejne `build_plan` dają identyczny wynik.

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
