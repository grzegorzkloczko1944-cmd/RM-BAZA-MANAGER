# Integracja RM_BAZA ↔ Subiekt nexo PRO — opis przepływu informacji

> Opis narracyjny na podstawie `SUBIEKT_INTEGRACJA_PLAN.md` (stan 03.09.2026, commit e527874).
> Wersja wizualna (karty, kolory per system): https://claude.ai/code/artifact/6baee5e9-2fc7-4be8-8341-277a4041aa0e

## Zasada nadrzędna

Z Subiektem rozmawia wyłącznie **RM_BAZA**. RM_RFQ nigdy nie łączy się z Subiektem,
nie zna Sfery, nie ma danych logowania i nie tworzy w nim żadnych dokumentów.
RM_RFQ nie tworzy i nie wysyła nawet samego zamówienia do dostawcy — jego rola
kończy się na zebraniu i rozstrzygnięciu ofert. Właściwe zamówienie zawsze
tworzy i wysyła RM_BAZA, niezależnie czy poprzedziło je RFQ, czy nie. Dzięki
temu w całej architekturze istnieje dokładnie jeden punkt, który może cokolwiek
zapisać w Subiekcie.

## Krok 1 — Start w projekcie/BOM (RM_BAZA)

Użytkownik zaznacza w arkuszu BOM detale do rozliczenia — cały BOM projektu
naraz (typowo ok. 300 pozycji) albo mniejsze, ręczne zaznaczenie; mechanizm
działa tak samo niezależnie od liczby wierszy. Po PPM → „Sprawdź w Subiekcie"
okno otwiera się natychmiast, a zapytanie do Subiekta leci w tle, w osobnym
wątku. Wzorzec UX jest świadomie skopiowany z istniejącego okna „Wyślij do RFQ".

## Krok 2 — Sprawdź w Subiekcie, odczyt (RM_BAZA → Subiekt)

Dla każdego numeru rysunku most C#/Sfera wykonuje punktowe zapytanie
(`WyszukajPoSymbolu`), sprawdzając czy istnieje kartoteka i jaki jest aktualny
stan magazynowy. Zanim zapytanie poleci do Subiekta, RM_BAZA najpierw sprawdza
lokalną tabelę mapowań — trafienie następuje lokalnie, w mikrosekundach, bez
ruchu sieciowego. Dopiero brak trafienia uruchamia zapytanie sieciowe. Wynik
trafia do okna w trzech grupach: „mają kartotekę" (zaznaczone domyślnie),
„brak kartoteki — do założenia" (zaznaczone, ale nic jeszcze nie zapisuje) oraz
„nie da się dopasować" (odznaczone i wyszarzone — pozycje bez kształtu numeru
rysunku, np. „Przygotowanie powietrza").

Dlaczego przez Sferę, a nie SQL: struktura bazy nexo nie jest publicznym,
stabilnym kontraktem InsERT i może się zmienić między wersjami bez ostrzeżenia.
Sfera jest oficjalnie wspieranym kanałem, dotyczy to obu kierunków — także
odczytu.

## Krok 2b — Ręczne dopasowanie po podobnej nazwie (RM_BAZA, na żądanie)

Dla pozycji z sekcji „brak kartoteki" albo „nie da się dopasować" dostępny jest
jeden wspólny przycisk pod listą — „Szukaj podobnych w Subiekcie" — działający
na aktualnym zaznaczeniu. SDK Sfery nie ma zapytania „podobna nazwa", więc
dopasowanie fuzzy (część wspólna słów / odległość Levenshteina) działa lokalnie,
na liście asortymentu ściągniętej raz do pamięci na całą sesję okna. User
dostaje 3–5 najbardziej podobnych kandydatów i wybiera właściwą kartotekę albo
potwierdza „żadna z tych, załóż nową".

Powód: część detali mogła zostać założona w Subiekcie ręcznie, zanim istniała
reguła „symbol = numer rysunku" — bez tego kroku dopasowanie 1:1 po symbolu
(krok 2) tego nie wyłapie i utworzy duplikat kartoteki. Wskazana ręcznie
kartoteka trafia do **globalnej** tabeli mapowań RM_BAZA (nie per projekt) —
następny projekt z tym samym numerem rysunku znajdzie skojarzenie od razu.
Nazwa/opis detalu z BOM nigdy nie są nadpisywane danymi z Subiekta — źródłem
prawdy dla danych konstrukcyjnych pozostaje RM_BAZA.

## Krok 3 — Rozlicz potrzebę (RM_BAZA)

Dla każdej pozycji z kartoteką liczone są cztery wartości: **potrzeba**
(ile trzeba na projekt), **dostępne** (co pokazuje Subiekt jako stan),
**ze stanu** (ile realnie da się pokryć z magazynu) i **kupić** (reszta).
To jeszcze nie rezerwacja ani zapis — sam plan do przejrzenia. Przykład:
projekt potrzebuje 20 sztuk, na magazynie jest 12 — wynik to 12 sztuk ze
stanu i 8 sztuk do kupienia.

## Krok 4 — Decyzja użytkownika (RM_BAZA)

**A) ZE STANU** → RM_BAZA musi zabezpieczyć ilość w Subiekcie: albo
zadysponować/zarezerwować, albo od razu wykonać właściwe wydanie na projekt.
**B) DO KUPIENIA** → dwie równoległe ścieżki: zamówienie bezpośrednie
(krok 10) albo wysyłka do ofertowania w RM_RFQ (krok 6). Przed samym zapisem
RM_BAZA i tak ponownie sprawdza stan na żywo tuż przed operacją ze skutkiem —
nigdy nie działa w ciemno na starych danych z cache.

Otwarte: dokładny mechanizm zabezpieczenia stanu (rezerwacja vs od razu
wydanie) jest świadomie nierozstrzygnięty — dziś firma w ogóle nie używa
rezerwacji (`zadysponowane = 0` w całej bazie).

## Krok 6 — Wyślij pozycje do ofertowania (RM_BAZA → RM_RFQ)

RM_BAZA przekazuje do RM_RFQ pozycje „do kupienia": ilości, numery
rysunków/specyfikacje, oczekiwany termin dostawy. To wyłącznie akcja „wyślij
do ofertowania" — na tym etapie nic jeszcze nie jest zamówieniem.

Po co osobny system: RM_RFQ ma już własny, dojrzały mechanizm zapytań
ofertowych — magic-link dla kooperantów, sealed bid, obsługa plików
i powiadomień. Duplikowanie tego w RM_BAZA byłoby marnotrawstwem.

## Krok 7 — Zapytania i oferty (RM_RFQ ↔ Kooperanci)

RM_RFQ wysyła zapytania (z ilościami, rysunkami i załącznikami) do wybranych
kooperantów przez portal z linkiem magicznym. Kooperanci odpowiadają: oferta
z ceną i terminem, albo odmowa, ewentualnie uwagi do pozycji.

## Krok 8 — Porównanie i rozstrzygnięcie (RM_RFQ)

RM_RFQ zestawia nadesłane oferty — ceny, terminy, odmowy — użytkownik wybiera
zwycięską ofertę. To ostatni krok, w którym RM_RFQ jeszcze samodzielnie
decyduje o czymkolwiek związanym z zakupem.

## Krok 9 — Wynik ofertowania → RM_BAZA (RM_RFQ → RM_BAZA)

Zwracany kontrakt danych to **wynik ofertowania**, świadomie nie „zamówienie":
co najmniej `rfq_id`, `rfq_item_id`, `offer_id`, `supplier_id`,
`drawing_number`, ilość, zaoferowana cena (opcjonalna), waluta,
`lead_time_days` lub konkretny termin, status rozstrzygnięcia. Kanał zwrotny
to istniejący mechanizm synchronizacji RM_RFQ↔RM_BAZA. Świadomie brak w tym
kontrakcie pól `order_number` czy `order_date` — RM_RFQ ich nie nadaje, bo
w tym momencie właściwe zamówienie jeszcze nie istnieje.

Dlaczego nie „zamówienie": wcześniejsza wersja planu nazywała ten zwrot
„zamówieniem" — mylące, sugerowało że RM_RFQ tworzy realny dokument zakupowy.
Ostateczne rozstrzygnięcie: RM_RFQ nigdy nie tworzy dokumentu zamówienia
w żadnej formie — przekazuje wyłącznie surowe dane, z których dopiero RM_BAZA
(krok 11) buduje właściwe zamówienie.

## Krok 10 — Zamów bez RFQ, ścieżka alternatywna (RM_BAZA)

Dla pozycji, które nie idą przez pełny proces ofertowy: RM_BAZA pozwala
wybrać dostawcę, ilość i termin bezpośrednio. Cena może być znana z góry,
uzgodniona telefonicznie, albo nieznana i ustalana „wg faktury" po dostawie.

## Krok 11 — Utworzenie i wysłanie zamówienia (RM_BAZA)

Wspólny punkt zbiegu obu ścieżek (wynik z RFQ albo dane zakupu bezpośredniego).
RM_BAZA w jednym miejscu:
1. scala wynik z projektem/BOM,
2. ustala finalnego dostawcę i warunki handlowe,
3. tworzy właściwe zamówienie i nadaje mu `order_number`,
4. zapisuje `order_date` i wylicza/zapisuje `pickup_date`,
5. **wysyła zamówienie do dostawcy**,
6. rozwiązuje mapowanie `drawing_number → kartoteka Subiekta`,
7. zakłada brakującą kartotekę na żądanie, jeśli symbol spełnia reguły kształtu numeru,
8. opcjonalnie — jeśli firma zdecyduje się na tę formę procesu — tworzy ZD przez Sferę,
9. jeśli ZD nie jest używane, zapisuje stan „zamówiono u dostawcy" po swojej
   stronie i czeka na FZ jako potwierdzenie fizycznego przyjęcia.

Dlaczego to jeden krok, nie dwa równoległe: niezależnie od źródła (RFQ czy
zakup bezpośredni), zamówienie ma dokładnie jednego właściciela i jeden
moment powstania — to jedyne miejsce, z którego mogą wychodzić operacje
zapisu do Subiekta.

## Krok 12 — Zapis do Subiekta (RM_BAZA → Subiekt)

Przez most C#/Sferę: założenie brakującej kartoteki towaru — najpierw
`WypelnijNaPodstawieSzablonu(DaneDomyslne.Towar)` (inaczej brakuje domyślnej
jednostki miary), potem `Symbol` = numer rysunku dokładnie jak w RM_BAZA,
`Nazwa` z BOM, jednostka „szt". Zapis leci pojedynczo, symbol po symbolu, z
potwierdzeniem — nigdy jako masowa pętla bez limitu w jednej transakcji.
Opcjonalnie, jeśli zapadnie taka decyzja procesowa, tworzone jest też ZD
(`IZamowieniaDoDostawcow.UtworzNaPodstawieZapotrzebowania`).

Dlaczego pojedynczo, nie masowo: zakładanie kartotek to jedyne miejsce
w procesie, gdzie koszt zależy od tego, CO piszemy, nie od rozmiaru Subiekta
(w przeciwieństwie do odczytu w kroku 2).

## Krok 13 — Sygnał zwrotny: FZ / ruch magazynowy (Subiekt → RM_BAZA)

FZ (faktura zakupu) ze statusem „Przyjęty towar i odebrane usługi" = faktyczne
przyjęcie towaru od dostawcy na magazyn — **nie** samo złożenie zamówienia.
Odczyt może być na żywo albo z cache, zawsze ze znacznikiem czasu; menedżer po
stronie Sfery to `sfera.DokumentyZakupu()` filtrowane po statusie ze skutkiem
przyjęcia.

Dlaczego FZ, nie PZ/WZ/RW: rozpoznanie na żywej bazie produkcyjnej
(02.09.2026) pokazało, że klasyczne dokumenty magazynowe wygasły w firmie:
PZ ostatni raz 11.2023, WZ 09.2024, RW 07.2023 — magazyn dziś jest prowadzony
bezpośrednio przez faktury zakupu (FZ = przyjęcie) i sprzedaży (FS = wydanie).

## Krok 14 — Realizacja i monitoring (RM_BAZA)

RM_BAZA pokazuje dla każdej pozycji projektu trzy niezależne stany naraz:
**ze stanu** (wydane z magazynu), **zamówiono u dostawcy** (zamówienie
z kroku 11 utworzone i wysłane, opcjonalnie potwierdzone przez ZD) i
**przyszło od dostawcy** (FZ ze skutkiem magazynowym przyjęcia). Wizualnie
ma to wyglądać jak istniejąca kolumna WYCENA z integracji RFQ: krótki
prefiks, kolor, klik pokazujący szczegóły — dostawca, numer zamówienia,
data zamówienia, termin odbioru, data przyjęcia.

Dlaczego trzy stany, nie jeden „dostarczono": „zamówiono" i „przyszło" to
zupełnie różna informacja dla planowania produkcji — zlanie ich w jeden
status ukryłoby, czy towar fizycznie już jest w firmie, czy tylko istnieje
zobowiązanie zakupowe.

## W skrócie

RM_BAZA zarządza projektem, decyzją zakupową i właściwym zamówieniem.
RM_RFQ zbiera i rozstrzyga oferty. Kooperanci odpowiadają na zapytania.
Subiekt prowadzi kartoteki, dokumenty i rzeczywisty stan magazynowy.
**RM_RFQ nigdy nie omija RM_BAZA w drodze do Subiekta ani do dostawcy.**

## Świadomie otwarte pytania

- **Zabezpieczenie stanu magazynowego** — jak nie dopuścić, żeby dwa projekty
  naraz uznały te same sztuki na stanie za swoje, skoro firma dziś w ogóle nie
  używa mechanizmu rezerwacji w Subiekcie (`zadysponowane = 0`).
- **ZD czy proces bez ZD** — zamówienia do dostawców nigdy nie były używane
  w historii firmy (zero sztuk), więc ich wprowadzenie byłoby realną zmianą
  procesu, nie tylko techniczną.
- **Realny czas odpytywania ~300 symboli** — szacunek 15–30 s to niepomierzone
  przypuszczenie, wymaga pomiaru w warunkach firmowych.
- **Polityka cache** — punkt wyjścia: cache po typie operacji (przeglądanie =
  cache + znacznik czasu, zapis = zawsze weryfikacja na żywo), nie ostateczna
  decyzja.
- **Wizualny wskaźnik dopasowania w arkuszu BOM** — jak pokazać różnicę
  między dopasowaniem automatycznym, ręcznym (fuzzy) a brakiem dopasowania.
- **Algorytm fuzzy-match** — próg podobieństwa i biblioteka nieustalone.
