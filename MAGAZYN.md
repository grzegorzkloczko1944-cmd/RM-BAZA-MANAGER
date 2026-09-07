# Magazyn nr 2 — start od nowa

**Nazwa nowego magazynu w Subiekcie: `Magazyn`** (symbol/nazwa magazynu nr 2, ustalone 07.09.2026).

Stan na 2026-09-07. Kontekst: `SUBIEKT PODWÓJNE POZYCJE DO NAPRAWY.md` (naprawa
zdublowanych składników kompletów, wykonana tego samego dnia).

## Co już zrobione

**MAG wyzerowany do zera** przez tryb `rw` mostu (`NexoRecon.exe`):

- 787 kartotek, 11 996,52 szt. → 0. Kartoteki, indeksy, komplety, ceny,
  historia zakupów — nietknięte, zeszedł tylko stan.
- Dokumenty: RW 4/09/2026 … RW 10/09/2026 (7 dokumentów, w tym osobno
  towary w partiach po 200 i osobno 43 komplety).
- Otwarte ZD na MAG usunięte przez użytkownika (m.in. ZD 7/09/2026).
- Progi zamawiania wyzerowane — była tylko jedna kartoteka z progiem
  (`015-100.13`, min 40/opt 60), teraz min=0, opt=null.
- Po drodze wykryta i naprawiona osobna usterka: kartoteka `35/35/1,5`
  (RURA KWADRATOWA) miała spację wiodącą w symbolu w bazie Subiekta —
  niewidoczna w polu edycji, widoczna jako wcięcie na liście Asortymentu.
  Poprawiona ręcznie w Subiekcie. Cały most trimuje symbole, więc taki
  błąd trzeba naprawiać w Subiekcie, nie przez `NexoRecon.exe symbole`.

## Decyzja: magazyn nr 2

Excel `C:\iLogic\magazyn 28.05.2026.xlsx` — inwentaryzacja z 2026-05-28,
**1410 wierszy / 1238 unikalnych symboli** — to są **stany startowe
magazynu nr 2** (MAG ma zostać pusty, tak jak jest teraz).

### Sprawdzenie pokrycia (07.09.2026, tryb `stan --symbols-file`)

| | liczba |
|---|---|
| symboli w Excelu | 1238 |
| istnieje w Subiekcie (dopasowanie dokładne) | 1214 |
| **brak w Subiekcie w ogóle** | **24** |
| duplikaty tego samego symbolu w arkuszu | 17 (34 wiersze) |
| wiersze bez symbolu (Id=0 lub puste) | 9 |
| wiersze bez ilości (Dostępne puste) | 6 |
| wiersze z ilością tekstową, nie liczbą (`"2,9mb"`, `"10mb"`) | 2 |

24 brakujące symbole wypisane na nowym arkuszu **„Brak w Subiekcie"**
w tym samym pliku Excel (dodane 07.09.2026) — do ręcznej decyzji, czy to
literówki, towar nieaktualny, czy trzeba założyć nowe kartoteki.

## Do ustalenia / następne kroki

- [ ] Co z 24 brakującymi symbolami — patrz arkusz „Brak w Subiekcie".
- [ ] Co z 17 zduplikowanymi symbolami w arkuszu głównym (dwa wiersze,
      różne ilości/opisy pod tym samym symbolem — np. `019-100.02`,
      `011-100.49`) — zsumować, czy to błąd źródła?
- [ ] 9 wierszy bez symbolu — z opisu (np. "Obsada mix", "Tarcza 350") nie
      da się jednoznacznie dopasować do kartoteki.
- [ ] 6 wierszy bez ilości i 2 z ilością w metrach tekstem — wymagają
      ręcznej decyzji o liczbie.
- [ ] **Mechanizm wgrania nie istnieje jeszcze w moście.** `rw` (rozchód)
      jest gotowy i sprawdzony na tej samej operacji zerowania. Do
      wgrania stanów startowych na magazyn nr 2 potrzeba **przyjęcia
      (PW)** — tryb, którego most obecnie nie ma. Do ustalenia z
      użytkownikiem, zanim zacznie się pisać kod.
- [ ] Magazyn nr 2 musi najpierw istnieć w Subiekcie (symbol magazynu) —
      nie sprawdzone, czy już jest założony.

---

## Pole „Położenie" (Regał/Półka) — rozpoznanie 07.09.2026

### Problem

W starym modelu magazynu obsługa się rozjechała. Dotyczy głównie **elementów
znormalizowanych**. Jak wyglądają dane w Excelu:

| kolumna | co tam realnie jest | problem |
|---|---|---|
| **Symbol** | numer katalogowy elementu znormalizowanego | przeważnie **wystarczy do zamówienia** — to jest dobre źródło |
| **Nazwa** | opis własny magazyniera | **niekompletny** — nie zawiera wszystkich danych z Symbolu, z samej Nazwy nie da się zamówić |
| **Opis** | położenie: Regał/Półka (`R1/P6`, `R22/P4`) | dane wciśnięte w pole nie do tego przeznaczone |
| **Projekt** | numer projektu | ✅ pozycje mają to już w Subiekcie / RM_BAZA |

### Ustalenie: standardowego pola „Położenie" w Subiekcie NIE MA

Sprawdzone w `SDK/Dokumentacja_bazy_danych_nexo.htm`. Istnieją dwa pola
`Lokalizacja`, ale **żadne nie nadaje się**:

- `Lokalizacja` na asortymencie — `nvarchar(256)`, opis wprost:
  **„Dla przyszłych zastosowań"**. Zarezerwowane przez InsERT, brak w GUI.
- `Lokalizacja` na pozycji dokumentu przyjęcia — `nvarchar(128)`,
  „Opis lokalizacji na magazynie". To **pozycja dokumentu**, nie kartoteka.

### Rozwiązanie: proste pola własne asortymentu (`PolaWlasne1..8`)

Potwierdzone w `SDK/Przyklady/nexoPolaWlasne2/`:

- `Asortyment` **ma** proste pola własne — `IProstePolaWlasne.MaProstePolaWlasne<Asortyment>()`
- odczyt/zapis przez `IPolaWlasneAdv2Accessor`:
  - `PobierzWartoscTypuTekst(nazwaPola)`
  - `UstawWartoscTypuTekst(nazwaPola, wartosc)`
- `PobierzProstePolaWlasne<Asortyment>()` zwraca `Id`, `Nazwa`, `Widoczne`
- ⚠️ Pola własne **wersji 2 NIE wymagają** podmiany `InsERT.Moria.ModelDanych.dll`
  (tego wymaga dopiero wersja 1) — most działa bez zmian w dystrybucji.
- ⚠️ Wymaga jednorazowej **konfiguracji w Subiekcie**: Konfiguracja → Pola własne.

### DECYZJE (07.09.2026)

- **Jedno pole tekstowe „Położenie"**, wartość w formacie `R22/P4` —
  tak jak w Excelu, bez rozbijania na Regał/Półka. Dane przenoszą się 1:1,
  bez parsowania. Świadomy kompromis: wypisanie wszystkiego z jednego
  regału wymaga szukania po fragmencie tekstu, nie sortowania po kolumnie.
- **Używamy gotowego zapasowego slotu**, nie zakładamy nowego pola —
  potwierdzone, że jest ich 8 i wszystkie wolne (patrz niżej). Bierzemy
  **PoleWlasne1**.

### SPRAWDZONE (07.09.2026, tryb `pola-wlasne`, nowy w moście)

Dopisany do `NexoRecon` tryb diagnostyczny `pola-wlasne` (tylko odczyt,
plik `PolaWlasne.cs`), uruchomiony na produkcji:

```
MaProstePolaWlasne(Asortyment) = True
PoleWlasne1..8 — WSZYSTKIE 8 wolne (nazwa = identyfikator techniczny,
                 Widoczne: false — nic nie jest jeszcze skonfigurowane)
zaawansowane pola własne — pusto (zgodne z SUBIEKT_PROJEKTY_WYDANIA.md 2.2)
```

Czyli: **żadnego pola własnego nie trzeba zakładać przez API** — bierzemy
gotowy wolny slot `PoleWlasne1`. Pytanie „czy Sfera pozwala tworzyć
definicje pól" stało się nieistotne dla tego zadania.

### DECYZJA: Położenie per kartoteka wystarczy (07.09.2026)

**MAG (magazyn nr 1) zostaje martwy** po uruchomieniu magazynu nr 2 —
tylko historia, bez żywych stanów. Żyje wyłącznie magazyn nr 2. Więc jedno
Położenie na kartotece (bez rozbicia per magazyn) w pełni wystarcza —
problem nie występuje. Ten punkt jest tym samym ZAMKNIĘTY.

### Do zrobienia

- [ ] Nazwać `PoleWlasne1` jako „Położenie" w Subiekcie (Konfiguracja →
      Pola własne) i ustawić `Widoczne = true`, żeby był widoczny w GUI.
- [ ] Dopisać do mostu ZAPIS wartości pola własnego — `PolaWlasne.cs` ma
      dziś tylko odczyt metadanych. Potrzebny `IPolaWlasneAdv2Accessor`
      (`PobierzWartoscTypuTekst` / `UstawWartoscTypuTekst`), tak jak w
      przykładzie SDK `OdczytIZapisWartosciPolWlasnychNowySposob.cs`.
- [ ] Dopisać do mostu odczyt+zapis pola własnego (nowy tryb albo
      rozszerzenie `kartoteka-edytuj` / `magazyn`).
- [ ] Nauczyć RM_BAZA czytać i edytować to pole.
- [ ] Przenieść położenia z kolumny „Opis" Excela do pola własnego
      (1214 pozycji ma dopasowanie do kartotek).

### Osobny wątek do rozstrzygnięcia później

**Numer katalogowy elementu znormalizowanego.** Dziś siedzi w Symbolu i
przeważnie wystarcza do zamówienia, ale Nazwa go nie duplikuje, więc przy
zamawianiu z Nazwy brakuje danych. Do przemyślenia, czy numer katalogowy
nie powinien mieć **własnego pola** (kolejne pole własne), niezależnego od
Symbolu — wtedy Symbol może być wewnętrzny, a numer katalogowy pełny.
Patrz też `SUBIEKT_PROJEKTY_WYDANIA.md` sekcja 5 (symbol dostawcy w polach
własnych).

---

## Magazyn nr 2 założony (07.09.2026)

**Symbol/Nazwa: `Magazyn`.** Utworzony przez most, tryb `magazyn-zaloz`
(nowy, plik `subiekt_sfera/NexoRecon/MagazynZaloz.cs`), podpięty pod
jedyną jednostkę organizacyjną w systemie: `RMPRODUKCJADZIERZGOWSKI,KŁOCZKOS`.
Potwierdzone odczytem: status `istnieje`.

### Pułapka po drodze: dwie różne "jednostki organizacyjne" w SDK

- `InsERT.Moria.Kadry.Duze.IJednostkiOrganizacyjne` — DZIAŁ kadrowy
  (`JednostkaOrganizacyjnaGr`: Nazwa, JednostkaNadrzedna… **brak Symbol,
  brak NIP**). Mimo najbardziej oczywistej nazwy — to NIE to.
- `InsERT.Moria.ModelOrganizacyjny` (`ICentrale.Znajdz()` — zawsze jedna
  w systemie; `IOddzialy.Dane.Wszystkie()`) — CENTRALA/ODDZIAŁ firmy,
  klasa `JednostkaOrganizacyjna` z podklasami `Centrala`/`Oddzial`. **To**
  jest wymagane przez `Magazyn.Dane.JednostkiOrganizacyjne` (musi mieć
  ≥1, inaczej `Zapisz()` odrzuca z komunikatem o braku jednostki).
- Właściwości (`Symbol`, `Nazwa`) nie są jednolicie dostępne na typie
  bazowym mimo że dokumentacja SDK je tam wypisuje — kompilator wymagał
  `dynamic` na `Centrala`/`Oddzial` osobno.
- **Pole NIP nie jest bezpośrednio na tym obiekcie** — dopasowanie
  zadziałało dopiero po Symbolu (`RMPRODUKCJADZIERZGOWSKI,KŁOCZKOS`), nie
  po NIP-ie.

### Tryb `magazyn-zaloz` (nowy w moście)

```
NexoRecon.exe magazyn-zaloz --plan=p.json [--out=w.json] [--zapisz]
```
plan.json: `{"symbol":..,"nazwa":..,"opis":..,"jednostka":".."}` —
`jednostka` to Symbol/Nazwa/NIP dopasowywane po kolei, dokładne dopasowanie
(TRIM, bez wielkości liter). Świadomie wąski zakres — tylko
Symbol/Nazwa/Opis/JednostkiOrganizacyjne; `MagazynGlowny`,
`MagazynProdukcji`, `MagazynPrzyjec`, `MagazynWydan` i inne ustawienia
biznesowe zostają do ręcznego dostrojenia w GUI Subiekta.

### Do zrobienia

- [ ] Dostroić magazyn w GUI Subiekta (MagazynGlowny? MagazynPrzyjec?
      MagazynWydan? — to trzeba kliknąć świadomie, tryb tego nie ustawia).
- [ ] Kod trybu nie jest jeszcze commitowany.

### Wyjaśnienie: "Magazyn ma asortyment jak MAG" — to nie jest błąd

Zgłoszone 07.09.2026: w oknie Asortyment, po przełączeniu na magazyn
"Magazyn", widać te same ~787 kartotek co na MAG.

To poprawne zachowanie Subiekta, nie kopiowanie danych. Kartoteka
asortymentu (śruba, komplet…) jest JEDNA, wspólna dla całej firmy —
magazyny nie mają osobnych katalogów towarów. Lista "Asortyment"
filtrowana na magazyn pokazuje wszystkie kartoteki uprawnione do bycia na
tym magazynie, niezależnie od tego, czy tam coś leży.

Zweryfikowane trybem `magazyn --tylko-niezerowe` zaraz po założeniu:
**0 pozycji w całej bazie** — żaden magazyn (ani MAG, ani "Magazyn") nie
ma realnego stanu > 0. Kartoteki są wspólne, stany magazynowe są od zera,
tak jak zamierzone.

---

## Punkt 4: jakość danych + Symbol/Nazwa/Opis — ZAMKNIĘTY (07.09.2026)

### Oczyszczanie (etap 1)

| krok | wynik |
|---|---|
| wierszy w źródle (Arkusz1) | 1410 |
| pominięte (brak symbolu) | 9 |
| pominięte (brak ilości / ilość tekstowa w metrach) | 8 |
| duplikaty scalone (suma ilości) | 16 grup |
| **finalnych pozycji** | **1376** |
| suma sztuk | 24 373 |

### Przeniesienie Symbol → Nazwa, Nazwa → Opis (etap 2)

Zasada ustalona z użytkownikiem: **Symbol elementów znormalizowanych
NIE JEST ruszany** — etykiety z kodem CODE128 są już wydrukowane. Sprawdzono
CODE128: obsługuje pełny ASCII, jedyny realny problem to polskie
diakrytyki — znaleziony i poprawiony 1 przypadek (`2430 ząbki` → `2430 zabki`).

Numery rysunków RM (wzorzec `PREFIKS-NNN.NN[sufiks]`, prefiks może być
literowy jak `DUO-`, `ZS4R-`, `STD-` — ustalone z użytkownikiem, że to
też są numery rysunków RM, nie elementy znormalizowane) — **486 pozycji,
całkowicie nietknięte**.

Dla pozostałych 890 „elementów znormalizowanych", finalna reguła
(po korekcie użytkownika — kolejność ma być Symbol jako pierwszy człon,
bo etykiety z Symbolem są już wydrukowane i to on ma być rozpoznawalny
jako pierwszy):

**Nazwa = Symbol + reszta oryginalnej Nazwy** (po odcięciu rozpoznanego
rodzaju produktu z przodu; reszta doklejana ZAWSZE, nawet jeśli częściowo
powtarza dane z Symbolu — np. wymiar), **Opis = rodzaj produktu** (np.
„Oring”, „Łożysko kulkowe zwykłe”, „Pasek zębaty”, „Płytka łącznika pasa”).

Przykłady:
- `T5-590/16` (Nazwa oryg. „Pasek zębaty T5x590x16mm") →
  Nazwa: `T5-590/16 T5x590x16mm`, Opis: `Pasek zębaty`
- `61906 RS` (Nazwa oryg. „Łożysko kulkowe zwykłe 30x47x9 ( 6906 )") →
  Nazwa: `61906 RS 30x47x9 ( 6906 )`, Opis: `Łożysko kulkowe zwykłe`
- `OR-7X1 EPDM` (Nazwa oryg. = sam Symbol, brak słowa rodzajowego) →
  Nazwa: `OR-7X1 EPDM` (bez zmian), Opis: `Oring`

Automatyczne dopasowanie per kategoria (578 poz. z 890) + osobna ręczna
ocena pozostałych 213 (120 dopasowanych regułą, 93 zostawione bez zmian —
tam gdzie Nazwa niosła prawdziwy dodatkowy kod producenta, np. `507909`/
`KP001`, `265111-C6`/`ESP.110-EH-C6`, albo dane były zbyt niejednoznaczne,
np. format ze średnikami w 4 pozycjach „Przepust;Øotw.mont:...”).

⚠️ Po drodze była błędna pośrednia wersja (Nazwa=Symbol BEZ reszty,
z próbą wycinania „nadmiarowego" tekstu z Opisu) — odrzucona przez
użytkownika i cofnięta. Finalna reguła to ta opisana wyżej.

**Kod numeryczny magazynowy (99 poz., np. Festo)** — Symbol to czysto
numeryczny identyfikator, a jedyny prawdziwy numer katalogowy producenta
jest w Nazwie (`Siłownik ESNU-20-20-P-A-MA`) — **zostawione bez zmian**,
bo reguła "Nazwa=Symbol" zniszczyłaby jedyne miejsce z danymi do zamówienia.

### Wynik końcowy

| grupa | liczba | akcja |
|---|---|---|
| numery rysunków RM | 486 | bez zmian |
| znormalizowane, wzorzec automatyczny | 578 | Nazwa=Symbol, Opis=rodzaj |
| znormalizowane, ocenione ręcznie — pasuje | 120 | Nazwa=Symbol, Opis=rodzaj |
| znormalizowane, ocenione ręcznie — inny kod/niepewne | 93 | bez zmian |
| kod numeryczny (Festo i podobne) | 99 | bez zmian |

**698 z 1376 pozycji dostaje nową Nazwę/Opis**, pozostałe 678 zostaje
nietknięte (brak pewności co do bezpiecznego przekształcenia).

Wynik zapisany do `C:\iLogic\magazyn 28.05.2026.xlsx`, nowy arkusz
**„Import do Magazynu"** (1376 wierszy: Symbol, Nazwa do wgrania, Opis do
wgrania, Ilość, Położenie, Stan min./opt., kolumna Akcja pokazująca która
reguła zadziałała, Nazwa oryginalna tam gdzie się zmieniła).

Ślad roboczy w `C:\RMPAK_CLIENT\`: `import_finalny.json` →
`import_finalny_v4.json` (kolejne etapy), `do_recznej_obrobki.json` +
`obrob_reczne.py` (213 ręcznych decyzji z uzasadnieniem w kodzie).

### Do zrobienia

- [ ] Punkt 3 (tryb PW w moście) wciąż nie istnieje — bez niego arkusz
      „Import do Magazynu” nie wejdzie do Subiekta.
- [ ] 24 pozycje bez kartoteki w Subiekcie (arkusz „Brak w Subiekcie”) —
      decyzja użytkownika nadal otwarta: założyć kartoteki czy pominąć.

---

## ⚠️ KRYTYCZNE: RM_BAZA i domyślne ZD widzą tylko "MAG" (07.09.2026)

Odkryte przy pytaniu "co widzi RM_BAZA, który magazyn". Symbol `MAG` jest
**zaszyty na sztywno** w dwóch miejscach, nie czytany z żadnej konfiguracji:

- `subiekt_magazyn_gui.py:50` — `MAGAZYN = "MAG"`. Cały moduł magazynowy
  RM_BAZA (okno stanów, progi, ZD na skład, RW) operuje wyłącznie na tym.
  Komentarz w kodzie: *"Firma ma jeden towarowy — ten sam, którego używa
  Zd.cs, gdy ZD nie ma magazynu."*
- `subiekt_sfera/NexoRecon/Zd.cs:219` — `.FirstOrDefault(m => m.Symbol == "MAG")`,
  domyślny magazyn dla ZD gdy dokument go nie wskazuje.

**KOREKTA (07.09.2026, po sprawdzeniu na działającym RM_BAZA):**
stała `MAGAZYN` dotyczy **wyłącznie zapisów**, nie odczytu:

| funkcja | używa MAG? | skutek |
|---|---|---|
| odczyt stanów (`pobierz_magazyn`, ~linia 100) | **NIE** | ✅ działa — tryb `magazyn` SUMUJE wszystkie magazyny, okno pokazuje dane z „Magazyn" |
| zapis progów (~linia 118) | TAK, `--magazyn={MAGAZYN}` | ⚠️ progi idą na pusty MAG |
| tworzenie RW (~linia 134) | TAK, `magazyn=MAGAZYN` domyślnie | ⚠️ RW zdejmuje z MAG |

Czyli **przeglądanie stanów działa od ręki** po migracji (potwierdzone:
RM_BAZA pokazuje 1353 pozycje z magazynu „Magazyn"). Do poprawy są tylko
ścieżki zapisu: progi, RW i domyślny magazyn ZD.

### DECYZJA (07.09.2026)

Poczekać z przepięciem — najpierw dokończyć wgranie inwentaryzacji
(arkusz "Import do Magazynu") przez tryb `pw`, przepięcie `MAG`→`Magazyn`
w obu miejscach zrobić jako osobny, świadomy krok na końcu.

### Do zrobienia (po wgraniu danych)

- [ ] Zmienić `MAGAZYN = "MAG"` na `"Magazyn"` w `subiekt_magazyn_gui.py`
      (sam plik .py, restart RM_BAZA wystarczy — nie wymaga przebudowy .exe
      jeśli uruchamiane ze źródła; jeśli z .exe, wymaga przebudowy RM_BAZA).
- [ ] Zmienić `"MAG"` na `"Magazyn"` w `Zd.cs:219`, przebudować most.
- [ ] Sprawdzić, czy są jeszcze inne twarde odwołania do `"MAG"` w kodzie
      (znaleziono też `UWAGI_MAGAZYN = "MAGAZYN"` w dwóch plikach — to inny,
      niezwiązany znacznik tekstowy w Uwagach dokumentów, nie symbol magazynu,
      nazwa tylko przypadkiem podobna — NIE mylić przy zmianach).

---

## MIGRACJA WYKONANA (07.09.2026)

Magazyn nr 2 („Magazyn") uruchomiony z danymi z inwentaryzacji 28.05.2026.

| krok | wynik |
|---|---|
| kartoteki założone (brakujące w Subiekcie) | **24** |
| stan przyjęty na magazyn „Magazyn" | **1353 kartoteki, 24 366 szt.** |
| dokumenty PW | **PW 2–8/09/2026** (7 dokumentów, partie po 200) |
| nazwy + opisy zaktualizowane | **703** |
| rozbieżności Excel↔Subiekt rozstrzygnięte przez użytkownika | **11 zmienionych, 12 zostawionych** |
| **regały zapisane w `PoleWlasne1`** | **1367** |
| błędy | **0** |

### Nie weszło (świadomie)

- **`576410`** (Płyta zaślepka VABB-B10-20-E) — rodzaj **„Usługa"** w Subiekcie,
  usługi nie mają stanu magazynowego. PW przyjęło pozycję do dokumentu, ale
  stan się nie utworzył. Do decyzji: zmienić rodzaj na Towar, czy zostawić.
- **9 pozycji bez położenia** w Excelu — nie dostały wpisu w `PoleWlasne1`.
- **12 rozbieżności nazw** — użytkownik zdecydował zostawić wersję z Subiekta
  (m.in. `T5-210/10` gdzie Excel miał śmieciową nazwę „1", `319941` ANPS-20,
  `014-100.03/04` z zamienionymi nazwami — patrz arkusz „Rozbieznosci do decyzji").

### ⚠️ Zapis pól własnych — pułapka SDK

Proste pola własne (`PoleWlasne1..8`) zapisuje się **wprost na encji**:
`Asortyment.PolaWlasne.PoleWlasne1` (typ `PolaWlasneAsortyment`).

**NIE** przez `UtworzPolaWlasneAdv2Accessor` — ten obsługuje pola
**zaawansowane v2**, których ta baza nie ma i rzuca wtedy:
*„Dla encji 'Asortyment' nie zdefiniowano zaawansowanych pól własnych
w wersji 2"* (sprawdzone na produkcji 07.09.2026).

Dodatkowo: `UtworzPolaWlasneAdv2Accessor` to metoda **rozszerzenia**, więc
nie da się jej wywołać na argumencie `dynamic` (błąd kompilacji CS1973) —
trzeba rzutować `ob.Dane` na `InsERT.Moria.ModelDanych.Asortyment`.

### Nowe tryby w moście (do commita)

- **`pw`** (`Pw.cs`) — przychód wewnętrzny, lustrzane odbicie `Rw.cs`.
  Nie zakłada kartotek, dopisuje stan istniejącym po Symbolu.
- **`pola-wlasne --plan=... --zapisz`** (`PolaWlasne.cs`) — zapis wartości
  prostego pola własnego na kartotekach. Bez planu = odczyt metadanych.
- **`magazyn-zaloz`** (`MagazynZaloz.cs`) — zakłada magazyn.

### Nadal do zrobienia

- [ ] **Przepiąć RM_BAZA i `Zd.cs` z „MAG" na „Magazyn"** — patrz sekcja
      wyżej. Bez tego okno magazynowe RM_BAZA pokazuje pusty magazyn.
- [ ] Zdecydować co z `576410` (rodzaj Usługa).
- [ ] Nazwać `PoleWlasne1` jako „Położenie" w Subiekcie (Konfiguracja →
      Pola własne) i ustawić widoczność — dane już tam są, ale pole nie ma
      etykiety w GUI.
- [ ] Kod mostu (`Pw.cs`, `PolaWlasne.cs`, `MagazynZaloz.cs`, zmiany
      w `CommandDispatcher.cs`) **nie jest commitowany**.
