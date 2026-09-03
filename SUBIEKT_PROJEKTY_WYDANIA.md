# Projekty RM_BAZA w Subiekcie — wydania i zapotrzebowanie

> **Status:** ustalenia z rozmowy 03.09.2026, nic jeszcze nie zaimplementowane.
> Dokument uzupełnia [`SUBIEKT_INTEGRACJA_PLAN.md`](SUBIEKT_INTEGRACJA_PLAN.md)
> (tam: kanał integracji, API Sfery, most NexoRecon, wyniki rozpoznania).
> Tu: **jak powiązać pozycje Subiekta z projektami RM_BAZA i wydawać na projekt.**

## 1. Problem

RM_BAZA prowadzi projekty i BOM-y. Subiekt prowadzi magazyn i **nie ma pojęcia
„projekt"** — sprawdzone w SDK: nie istnieje encja `Projekt` ani `Zlecenie`
(są tylko zlecenia produkcyjne ZPM/ZPR — montowanie kompletów, 0 sztuk w bazie).

Pytanie brzmi: jak wydać oring z magazynu „na projekt 2222" tak, żeby dało się
potem powiedzieć, co poszło na który projekt.

**Trudność, która wywraca proste rozwiązania:** elementy handlowe (oringi, śruby,
łożyska) przewijają się przez **wiele projektów naraz**. Kartoteka `OR-26X2 FKM`
należy do wszystkich projektów jednocześnie — to po prostu *ten oring*.

## 2. Rozważone i odrzucone

### 2.1 Uwagi na dokumencie — działa, ale nie skaluje

Stan faktyczny (03.09.2026): pole `Dokumenty.Uwagi` jest wypełnione w **628
dokumentach**, w tym **8 faktur sprzedaży ma sam numer projektu** (`2115`,
`2328`, `2341`, `2401`, `2457`, `2460`, `2509`, `2550`). Dzisiejsze
`RW 1/09/2026` ma w Uwagach `2453`.

Czyli sposób jest już w użyciu — ale:

* **Uwagi są na dokumencie, nie na pozycji** → jedno RW = jeden projekt.
  Wydanie oringów na trzy projekty wymaga trzech dokumentów albo wpisu
  `2222/2453/2601`, przy którym **ginie informacja, ile sztuk poszło gdzie**.
* To wolny tekst — nikt nie pilnuje formatu (`2453` vs `proj. 2453` vs
  `2453 Ceramizator`), więc filtrowanie z czasem zawodzi.

Szukanie po Uwagach **działa**: w Subiekcie przez filtrowanie F8 (opisane
w `SDK/F8_filtrowanie_przy_pomocy_wyrazen.pdf`), kolumnę „Uwagi" na liście
i widoki robocze (cecha PRO); z RM_BAZA zwykłym `LIKE` po `Dokumenty.Uwagi`.

**Werdykt:** dobre na doraźne oznaczanie detali robionych pod jeden projekt.
Nie nadaje się do elementów handlowych dzielonych między projekty.

### 2.2 Pole własne na pozycji dokumentu — poprawne, ale to tylko etykieta

Tabela `PozycjeDokumentu_PolaWlasnePozycjaDokumentu_Adv2` **istnieje i jest
pusta** — miejsce wolne. Pola własne **zaawansowane w wersji 2**; ⚠️ ważne:
wersja 2 **nie wymaga** podmiany `InsERT.Moria.ModelDanych.dll` na tę
z `Deployments\...\Binaries` (tego wymaga dopiero wersja 1) — most działa bez zmian.

Rozwiązuje granulację (1 pozycja = 1 projekt), ale:

* wymaga konfiguracji w Subiekcie (Konfiguracja → Pola własne),
* ktoś musi je **wypełniać** — Subiekt sam nic z niego nie liczy,
* to nadal notatka: brak pilnowania ilości, brak realizacji, brak zapotrzebowania.

Proste pola własne (`PolaWlasne1..8`) są **tylko dla `Asortyment` i `Podmiot`** —
nie dla pozycji dokumentu. Na kartotece numer projektu i tak nie ma sensu
(ten sam detal w wielu projektach), ale te 8 pól to dobre miejsce na
**symbol dostawcy** (patrz sekcja 5).

### 2.3 Słownik własny z listą projektów — odrzucone na teraz

Pole własne może być referencją do **słownika własnego** (`ISlownikiWlasne`,
`PozycjaSlownikaWlasnego` z `Id`/`Wartosc`/`Aktywna`) — wtedy w Subiekcie jest
**lista rozwijana**, nie wpisywanie z palca. Zamknięte projekty oznacza się
`Aktywna = false`: znikają z listy, zostają w historii.

**Koszt:** drugie źródło prawdy o tym, jakie projekty istnieją, plus
synchronizacja RM_BAZA → Subiekt. Plan ostrzega przed tym wprost (sekcja 5,
przypadek `rfq_portal_url`). Wracamy do tego, jeśli okaże się, że wpisywanie
ręczne faktycznie się rozjeżdża.

### 2.4 Kategorie dokumentów — nie

23 kategorie (`Zakup`, `Wydanie`, `Montaż`…). Jedna etykieta na cały dokument,
płaska lista — przy dziesiątkach projektów zrobi się śmietnik.

## 3. ROZWIĄZANIE: ZK (zamówienie od klienta) jako „lista projektu"

**Zamiast oznaczać pozycje etykietą, importujemy listę pozycji projektu jako
dokument ZK.** Subiekt traktuje ZK jako obiekt biznesowy i sam liczy realizację.

```
RM_BAZA: BOM projektu 2222
      │  eksport listy pozycji
      ▼
Subiekt: ZK „projekt 2222"  (pozycje + ilości)
      │
      ├─ co da się wydać teraz      → ZestawieniePozycjiGotowychDoWydania()
      ├─ czego brakuje              → ZapotrzebowanieNaAsortyment()
      ├─ RW/WZ jednym kliknięciem   → WypelnijNaPodstawieZK(...)
      ├─ ile już wydano             → IloscDoRealizacji, StanRealizacjiZamowienia
      └─ braki → zamówienie do dostawcy (zbiorcze przetwarzanie ZK na ZD)
```

**Dlaczego to bije poprzednie warianty:**

| | Uwagi | pole własne | **ZK** |
|---|---|---|---|
| jeden detal w wielu projektach | ✗ | ✓ | **✓** |
| Subiekt pilnuje, ile wydano | ✗ | ✗ | **✓** |
| wydanie jednym kliknięciem | ✗ | ✗ | **✓** |
| widać braki do zamówienia | ✗ | ✗ | **✓** |
| wymaga konfiguracji w Subiekcie | ✗ | ✓ | **✗** |

Uwagi i pole własne to **etykieta**, którą trzeba samemu obsłużyć.
ZK to **mechanizm** — nic nie budujemy, korzystamy z gotowego.

**Metody potwierdzone w API** (`IZamowieniaOdKlientow`, wersja 61.1.0.9431):
`UtworzZamowienieOdKlienta`, `ZapotrzebowanieNaAsortyment`,
`ZestawieniePozycjiGotowychDoWydania`; realizacja przez
`WypelnijNaPodstawieZK(zamowienia[], zrodlo, ParametryGrupowania…)`
z `MetodaGrupowaniaPozycji` (`BezKonsolidacji` /
`KonsolidacjaWJednostceMiaryICenie` / `KonsolidacjaBezWzgleduNaJednostkeMiary`).
Przykłady: `SDK\Przyklady\PrzykladyRealizacjiDokumentow` oraz rozdział
„Realizacje dokumentów" w `InsERT.nexo.Sfera.chm`.

**Numer projektu** wchodzi w `Tytul` albo `Uwagi` **na ZK** — i to wystarcza,
bo dalej wszystko wisi na zamówieniu, nie na pojedynczych pozycjach.

## 4. DO ROZSTRZYGNIĘCIA PRZED KODEM

- [x] **Podmiot na ZK — rozstrzygnięte 03.09.2026: RMPAK.** RM_BAZA jest
      klientem (produkcja własna) — zgodne z historycznymi RW, które mają
      podmiot „RMPAK SPÓŁKA Z O.O.".
- [x] **Dzisiejsze `RW 1/09/2026` bez pozycji — wyjaśnione: to były testy.**
      Nie dokument w trakcie, nie błąd — świadomy test kogoś w firmie.
- [ ] **Czy wracacie do wystawiania RW — TAK, ale to nie jest tylko
      przełącznik.** Ostatnie realne RW przed testowym z 03.09.2026: lipiec
      2023. **Powód porzucenia RW nie był techniczny ani procesowy — magazynier
      po prostu robił wydania na karteczkach**, bo wypełnianie dokumentu
      w Subiekcie było wolniejsze/mniej wygodne niż kartka, i nikt tego nie
      egzekwował. Przez dwa lata nie bolało, bo nikt nie potrzebował realnych
      danych „co poszło z magazynu na który projekt" — dopóki nie zaczęła
      powstawać ta integracja.
      ⚠️ **Konsekwencja dla projektu: samo przywrócenie mechanizmu RW go nie
      utrwali.** Jeśli droga „otwieram ZK projektu → RW" będzie dla
      magazyniera wolniejsza albo bardziej kłopotliwa niż kartka, za pół roku
      wrócą karteczki — tylko teraz z integracją, która cicho pokazuje
      nieaktualne dane (dokładnie to ryzyko, przed którym ostrzega sekcja
      o cache w planie integracji). **Dlatego „RW jednym kliknięciem z ZK"
      (`WypelnijNaPodstawieZK`) to nie tylko wygoda funkcjonalna, tylko
      wymaganie UX konieczne do adopcji:** ścieżka od „otwieram ZK projektu"
      do „RW wystawione" musi być realnie krótsza i mniej kłopotliwa niż
      napisanie czegoś na kartce, inaczej mechanizm zaprojektowany poprawnie
      w dokumentacji będzie martwy w praktyce tak samo jak poprzednie RW.
- [x] **Kopia bazy do testów — rozstrzygnięte 03.09.2026.** Dwa środowiska
      testowe: Subiekt demo instalowany w domu do prac offline, oraz
      w firmie realna „baza widmo" w Subiekcie, jeszcze nieużywana
      produkcyjnie — bezpieczne miejsce do testów zapisu przed dotknięciem
      `Nexo_RM PRODUKCJA`.
- [x] **Co z pozycjami bez kartoteki — rozstrzygnięte 03.09.2026: obie opcje
      zaimplementowane.** Eksport BOM-u do Subiekta ma teraz dwa tryby: z
      automatycznym zakładaniem brakujących kartotek („kartoteka na żądanie",
      plan sekcja 4) i bez zakładania (ZK obejmuje tylko to, co już istnieje
      w Subiekcie) — wybór zależny od kontekstu użycia.

## 5. Zespoły spawane (kilka pozycji = jedna pozycja) — kartoteka typu Komplet

**Problem, inny niż projekt→pozycje:** kilka blach wchodzi w skład jednego
zespawanego detalu (np. „Wspornik spawany 013-100.220" = 4 blachy). To pytanie
o **strukturę pozycji**, nie o przypisanie do projektu — obie sprawy się
zazębiają, ale rozwiązuje je inny mechanizm Subiekta.

**Rozwiązanie: kartoteka `RodzajAsortymentu` = komplet.** Potwierdzone w SDK
(wersja 61.1.0.9431):

- Rodzaj kartoteki sprawdza się/ustawia przez `RodzajeAsortymentowExtensions.CzyKomplet(RodzajAsortymentu)`.
- Skład kompletu: interfejs `ISkladnikiKompletu` (właściwość `Wszystkie`,
  metoda `Dodaj(Asortyment)`) na jednostce miary asortymentu.
- Każdy składnik to encja `SkladnikKompletu` (`InsERT.Moria.ModelDanych`):
  `Komplet` (do którego kompletu należy), `Skladnik` (jaki towar), `Ilosc`,
  `JednostkaMiaryAsortymentu`, `BlokujIlosc`, `Cena`, `Wartosc`.
- Zdefiniowane błędy walidacji przy zapisie (warto obsłużyć, most i tak
  pokaże treść wyjątku): brak zdefiniowanych składników
  (`NieZdefiniowanoSkladnikowKompletuBlad`), składnik z niedozwoloną
  jednostką miary (`NiedozwolonaJednostkaMiarySkladnikuKompletuBlad`),
  komplet zawierający sam siebie pośrednio
  (`SkladnikKompletuZawieraObecnyKompletBlad`), usunięty składnik
  (`KompletZawieraUsunieteAsortymentyBlad`), brak stanu dla składnika przy
  rozchodzie (`BrakAsortymentuDlaSkladnikaKompletuBlad`).

**Efekt praktyczny:** na FS/WZ/RW wybiera się jedną pozycję — komplet
(„Wspornik spawany") — Subiekt sam rozchodowuje z magazynu wszystkie blachy
składowe wg zdefiniowanej receptury. Na dokumencie i w ZK widać jedną linię,
nie cztery.

**Roboczogodziny spawania jako składnik kompletu.** `RodzajAsortymentu` ma
pięć wartości (`CzyTowar`, `CzyUsluga`, `CzyKomplet`, `CzyOpakowanie`,
`CzyDodatkowaOplata`) — nie ma osobnego rodzaju „robocizna”: wprowadza się ją
jak w klasycznym Subiekcie, jako kartotekę rodzaju **Usługa** (np. „Spawanie”,
jednostka miary „rbg”). `ISkladnikiKompletu.Dodaj(Asortyment, Ilosc, ...)`
przyjmuje dowolny `Asortyment` — bez ograniczenia do towarów — więc usługa
wchodzi do składu kompletu tak samo jak blachy: „Wspornik spawany” = 4×blacha
+ 0,5 rbg „Spawanie”. Przy rozchodzie z magazynu usługa nie ma stanu
magazynowego do pilnowania (nie wywoła `BrakAsortymentuDlaSkladnikaKompletuBlad`),
ale **wchodzi do kalkulacji ceny/kosztu kompletu** jeśli tak skonfigurowana —
to sposób na wliczenie robocizny w cenę wyrobu bez osobnego dokumentu
produkcyjnego.

**Jak to się kleji z ZK/projektami (sekcja 3):** kartoteka-komplet wchodzi do
BOM-u projektu jak każda inna pozycja z kartoteką — na ZK dla projektu 2222
jest jedna linia „Wspornik spawany”, rozbicie na blachy obsługuje sam Subiekt
przy realizacji. RM_BAZA nie musi duplikować składu kompletu, chyba że
zajdzie potrzeba sprawdzania stanów blach składowych z poziomu RM_BAZA —
to osobna, na razie nieotwarta decyzja.

**Alternatywa cięższa, na razie nie wybrana:** ZPM/ZPR (zlecenie produkcyjne —
montowanie kompletów) — formalny dokument produkcyjny z osobnym rozchodem
składników i przyjęciem wyrobu. W bazie produkcyjnej firmy 0 sztuk w historii
(patrz [[project-subiekt-nexo-sfera]]) — realna zmiana procesu, nie tylko
techniczna decyzja. Komplet (bez ZPM) wystarcza do samego „te blachy razem
tworzą tę pozycję”; ZPM miałby sens dopiero, gdyby chcieli Państwo formalnie
rozliczać zużycie materiału per partia produkcyjna.

**Do rozstrzygnięcia, jeśli wchodzimy w ten kierunek:** czy komplet zakłada
RM_BAZA przy eksporcie BOM-u (analogicznie do „kartoteka na żądanie" z
sekcji 4), czy zakładanie kompletów zostaje ręczne w Subiekcie, a RM_BAZA
tylko z nich korzysta jako z gotowych pozycji.

**Automatyczne wykrywanie `Z`/`ZZ` → komplet.** RM_BAZA już ma wszystko, co
do tego potrzebne — nic nowego nie trzeba liczyć:

- **Klasyfikacja typu** jest już gotowa: `normalize_type_label()` (z opisu
  w Excelu) i `infer_type_from_drawing_no()` (z sufiksu numeru rysunku,
  `import_bom.py`) rozpoznają `X` / `XX` / `Z` / `ZZ` automatycznie.
- **Hierarchia (co jest składnikiem czego)** jest już policzona: arkusz
  „DRZEWKO TEKST” (`find_assembly_tree_rows()`) daje dla każdego węzła
  `poziom`, `typ` i `sciezka` (segmenty numerów rysunków od korzenia).
  Dzieci danego węzła to po prostu wiersze, których `sciezka` kończy się
  jego numerem rysunku, o jeden poziom głębiej.

Reguła eksportu do Subiekta, oparta wyłącznie na już istniejących danych:

| Typ węzła | Co robi eksport |
|---|---|
| `X`, `XX` | zwykła kartoteka-towar (liść drzewa, brak składników) |
| `Z` | kartoteka-komplet; składniki = jego dzieci w drzewie (+ opcjonalnie usługa-robocizna) |
| `ZZ` | kartoteka-komplet; składniki = jego dzieci w drzewie — mogą być `Z` (**komplet w komplecie**) albo od razu `X`/`XX` |

⚠️ **Nazewnictwo NIE opisuje poziomu w drzewie — sprawdzone na żywych danych
(03.09.2026).** Reguła „`ZZ` składa się z `Z`, `Z` z `X`/`XX`" jest fałszywa:

* „2558 Olmaj Wciskarka": wszystkie 7 modułów `ZZ` zawiera **bezpośrednio**
  blachy `X`/`XX` (np. `2558-300.22ZZ` to 11 blach wprost), a `Z` to płytkie
  złożenia po 1–3 detale.
* „2607 Platyn" (`V:\2607 Platyn\2607-000.00ZZ Platyn_OUT.xlsx`): **`ZZ`
  zawiera `ZZ`** — 23 takie zagnieżdżenia, drzewo na 4 poziomy
  (`2607-000.00ZZ > 2607-200.30ZZ > 2607-200.27ZZ > 013-100.22X`).
  Realne relacje rodzic→dziecko: `ZZ→X/XX` 172, `ZZ→STANDARD` 126,
  `ZZ→ZZ` 23, `ZZ→Z` 20, `Z→X/XX` 35. **Firma zgłasza projekty do 6 poziomów.**

Stąd dwie twarde konsekwencje dla implementacji:

1. **Skład kompletu bierze się z faktycznych dzieci w drzewie**, jakiegokolwiek
   są typu — nigdy z założenia o typie.
2. **Kolejność zapisu musi być sortowaniem topologicznym** (najgłębsze
   komplety pierwsze), a nie „`Z` przed `ZZ`" — bo `ZZ` bywa składnikiem `ZZ`.
   Ograniczanie rekurencji stałą głębokością też odpada; pilnuje się cyklu
   (ten sam symbol na własnej ścieżce), nie liczby poziomów.

`ISkladnikiKompletu.Dodaj(Asortyment, Ilosc, JednostkaMiaryAsortymentu)` nie
ogranicza typu składnika, więc komplet-w-komplecie jest wprost dozwolony w
SDK — jedyne co pilnuje walidacja (`SkladnikKompletuZawieraObecnyKompletBlad`)
to cykl (komplet zawierający pośrednio sam siebie), nie samo zagnieżdżenie.
Zapis nadal pojedynczo, symbol po symbolu, zgodnie z regułą z kroku 12
przepływu (`SUBIEKT_PRZEPLYW_OPIS.md`) — dla `ZZ` trzeba zapisać najpierw
składowe `Z` (i ich składowe `X`/`XX`), dopiero potem sam moduł, żeby
składniki istniały w Subiekcie w chwili tworzenia kompletu nadrzędnego.

**Subiekt nie ma widoku drzewa BOM-u.** SDK nie ma żadnej klasy ani widoku
typu „struktura kompletu” — jedyne trafienie na „drzewo” w API to ogólny
błąd walidacji `DrzewaZaGlebokieDrzewoBlad` (limit głębokości drzewa danych
w ogóle, nie coś specyficznego dla kompletów). To, co Subiekt realnie
pokazuje w oknie kartoteki-kompletu, to **płaska lista składników**
(`ISkladnikiKompletu.Wszystkie`) — jeśli komplet zawiera inny komplet, na
liście widać jedną linię (np. „Złożenie Z-013”), bez rozwinięcia jego
własnych składników w tym samym widoku; żeby zobaczyć pełne drzewo trzeba
by rekurencyjnie otwierać kartotekę każdego składnika-kompletu osobno.
**Wniosek:** wielopoziomowe drzewo BOM (`ZZ → Z → X/XX`) zostaje domeną
RM_BAZA (arkusz „DRZEWKO TEKST” już to ma) — nie ma sensu duplikować tej
wizualizacji w Subiekcie, wystarczy poprawnie zapisać strukturę składników
przy eksporcie.

## 6. Na marginesie: symbole dostawców (osobny temat, ten sam mechanizm)

Przy imporcie faktur zakupowych Subiekt dopasowuje pozycje do kartotek m.in.
po **symbolu, jakim posługuje się dostawca** (`WyszukajPoSymboluDostawcy`,
`SymboleDlaPodmiotu`). Wypełnienie tego raz dla powtarzalnych dostawców
znacząco podnosi skuteczność automatycznego importu e-Faktur
(Subiekt ma go wbudowanego — `ObslugaImportuEFaktur`,
`WypelnijNaPodstawieDokumentuElektronicznego`, `WyszukajNiezafakturowanePrzyjecia`,
`WyszukajAsortyment`). **Nie trzeba tego pisać w RM_BAZA.**

## 7. Implementacja (03.09.2026)

Zaimplementowane — **nieuruchomione jeszcze na żywej bazie** (most nie ma
haseł w tym środowisku; kod przetestowany na realnych BOM-ach offline):

| plik | rola |
|---|---|
| `subiekt_sfera/NexoRecon/Projekt.cs` | tryb `projekt` mostu: kartoteki → komplety → ZK. **Jedyne miejsce, które zapisuje do Subiekta.** Bez `--zapisz` to suchy przebieg. |
| `subiekt_projekt.py` | okno „Załóż projekt w Subiekcie": drzewo BOM z typami, podgląd co powstanie, zapis po potwierdzeniu |
| `subiekt_mapowania.py` | globalna tabela `numer rysunku → kartoteka` (`Y:\RM_BAZA\subiekt_mapowania.sqlite`) — warstwa pośrednicząca z sekcji „Zapamiętanie skojarzenia" planu |

**Zabezpieczenia przy zapisie na bazę produkcyjną:** zawsze najpierw suchy
przebieg; potwierdzenie mówiące wprost, ile kartotek/kompletów powstanie i że
ZK da się usunąć, a kartotek nie; log każdego kroku do
`C:\RMPAK_CLIENT\subiekt_logi\` (bez niego nie dałoby się posprzątać po błędzie);
kartoteki zakładane pojedynczo, nie masową pętlą.

**Mapowania** działają jak filtr przed siecią (plan, sekcja „Dlaczego to nie
zwalnia kroku 2"): trafienie lokalne = mikrosekundy, dopiero brak trafienia
idzie do Sfery. Ręczne skojarzenie użytkownika nie jest nadpisywane przez
automat — to świadoma decyzja człowieka, automat mógłby ją cofnąć.

**Pułapka wyłapana przy testach:** kolumny `*_over` w bazie projektu
(`name_over`, `order_qty_over`…) to **flagi nadpisania** (INTEGER 0/1), nie
wartości. Wzięte jako źródło nazwy/ilości dawały nazwę „0" i **ilość 0 na ZK**.
Kanoniczna kolejność w RM_BAZA to `COALESCE(order_qty, work_qty, src_qty)`.
Ten sam błąd był w `subiekt_stany.py` — poprawiony przy okazji.

## 8. Następny krok

**Suchy przebieg** (bez zapisu): bierze BOM projektu, dopasowuje pozycje do
kartotek Subiekta i pokazuje, jakie ZK by powstało — ile pozycji, które mają
kartotekę, których brakuje, jakie ilości. Dopiero po obejrzeniu tego —
zapis, i to najpierw na kopii bazy.
