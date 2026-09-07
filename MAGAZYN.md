# Magazyn nr 2 — uruchomienie od zera

Stan na 2026-09-07. Cała operacja wykonana na **produkcyjnej** bazie Subiekta
(`Nexo_RM PRODUKCJA`, serwer 192.168.100.4) w jeden dzień, bez błędów.

Kontekst wcześniejszy: `SUBIEKT PODWÓJNE POZYCJE DO NAPRAWY.md` (naprawa
zdublowanych składników kompletów, wykonana tego samego dnia rano).

---

## 1. Po co to było

Stary magazyn `MAG` narastał latami bez dyscypliny. Stany rozjechały się
z półką, a magazynier trzymał położenie (regał/półka) w polu **Opis**
kartoteki — razem z czym popadnie. Decyzja: zacząć od nowa na czystym
magazynie, z danymi z inwentaryzacji fizycznej z 28.05.2026.

**Nazwa nowego magazynu: `Magazyn`.**

---

## 2. Wynik końcowy

| co | ile |
|---|---|
| kartoteki założone (brakujące w Subiekcie) | **24** |
| stan przyjęty na magazyn „Magazyn" | **1353 kartoteki, 24 366 szt.** |
| dokumenty PW | **PW 2–8/09/2026** (7 dokumentów) |
| nazwy + opisy zaktualizowane | **703** |
| rozbieżności Excel↔Subiekt rozstrzygnięte ręcznie | 11 zmienionych / 12 zostawionych |
| położenia (regał/półka) w `PoleWlasne1` | **1367** |
| stare położenia wyczyszczone z pola Opis | **618** (489 + 129) |
| **błędy** | **0** |

Stary `MAG`: wyzerowany (787 kartotek, 11 996,52 szt. → 0), dokumenty
RW 4–10/09/2026.

---

## 3. Przebieg — kolejność kroków

Kolejność ma znaczenie: każdy krok zależy od poprzedniego.

### 3.1. Wyzerowanie starego MAG

Tryb `rw` (rozchód wewnętrzny), partiami po 200 pozycji. Towary i komplety
osobno — żeby ewentualny problem z kompletami nie wywalił całości.

```
NexoRecon.exe rw --plan=rw_1.json --zapisz --out=w.json
```

**Nie ma trybu „wyzeruj stany"** i nie może być — stan w Subiekcie to wynik
dokumentów, nie pole do nadpisania. RW zdejmuje stan, a kartoteki, indeksy,
historię i komplety zostawia nietknięte.

Co się sprawdziło w praktyce:

- **Brak ceny ewidencyjnej NIE blokuje RW.** 767 z 787 pozycji miało
  `CenaEwidencyjna: 0.0` i Subiekt przyjął każdą — mimo że komentarz
  w `Rw.cs` wymienia to jako częstą przyczynę odmowy.
- **Komplety schodzą jako komplety**, nie rozbijają się na składniki.
- Kartoteka z **otwartym ZD** pokazuje się dalej w `--tylko-niezerowe`,
  nawet ze stanem 0.0 — to zamówienie, nie stan.

### 3.2. Założenie magazynu

Tryb **`magazyn-zaloz`** (nowy, `MagazynZaloz.cs`).

```
NexoRecon.exe magazyn-zaloz --plan=m.json --zapisz --out=w.json
```
```json
{ "symbol": "Magazyn", "nazwa": "Magazyn", "opis": "...",
  "jednostka": "RMPRODUKCJADZIERZGOWSKI,KŁOCZKOS" }
```

⚠️ **Subiekt odrzuca zapis magazynu bez jednostki organizacyjnej** —
patrz sekcja 6.1 (pułapka dwóch różnych „jednostek").

### 3.3. Oczyszczenie danych z Excela

Źródło: `magazyn 28.05.2026.xlsx`, arkusz `Arkusz1` — 1410 wierszy.

| krok | wynik |
|---|---|
| pominięte: brak symbolu | 9 |
| pominięte: brak ilości lub ilość tekstowa (`"2,9mb"`, `"10mb"`) | 8 |
| duplikaty scalone (suma ilości) | 16 grup |
| **finalnie** | **1376 pozycji, 24 373 szt.** |

Decyzje użytkownika przy duplikatach: sumujemy ilości pod jednym symbolem,
także tam gdzie ten sam symbol oznaczał różne warianty (prawy/lewy, trzy
kolory poliuretanu) — symbol był używany jako kod rodziny, nie pojedynczej
części.

### 3.4. Porównanie z bazą i założenie brakujących kartotek

```
NexoRecon.exe stan --symbols-file=symbole.txt --out=w.json
```

1352 z 1376 istniało (dopasowanie dokładne). **24 brakowało** — założone
trybem `kartoteka`.

⚠️ Tryb `kartoteka` przyjmuje **jedną kartotekę na wywołanie**, więc trzeba
pętli. Każde uruchomienie to osobny start Sfery (~10 s), czyli ~4 min na 24
pozycje. Skrypt: `zaloz_kartoteki.py` (w `C:\RMPAK_CLIENT\`).

### 3.5. Wypchnięcie stanów

Tryb **`pw`** (nowy, `Pw.cs`) — przychód wewnętrzny, partiami po 200.

```
NexoRecon.exe pw --plan=pw_1.json --zapisz --out=w.json
```
```json
{ "pozycje": [ {"symbol":"011-100.49", "ilosc": 3} ],
  "uwagi": "Stany startowe magazynu nr 2 - inwentaryzacja 28.05.2026",
  "magazyn": "Magazyn" }
```

**Kartoteki są wspólne dla magazynów** — PW nie zakłada nowych, tylko
dopisuje stan istniejącym, po Symbolu. To była wyraźna decyzja: *„te pozycje
są z magazynu wyciągnięte… a w nowym magazynie one dalej będą tymi samymi
pozycjami, bo mają te same symbole"*.

### 3.6. Nazwy i opisy

Tryb `kartoteka-edytuj` (istniejący; przyjmuje **całą listę naraz**,
w odróżnieniu od `kartoteka`).

Zasada ustalona z użytkownikiem:

> **Nazwa = Symbol + reszta oryginalnej Nazwy**, **Opis = rodzaj produktu**

Symbol jest pierwszym członem Nazwy, bo etykiety z kodem CODE128 są już
wydrukowane i to Symbol ma być rozpoznawalny od razu. Reszta doklejana
zawsze, nawet jeśli częściowo powtarza dane z Symbolu.

| Symbol | Nazwa oryginalna | → Nazwa | → Opis |
|---|---|---|---|
| `T5-590/16` | Pasek zębaty T5x590x16mm | `T5-590/16 T5x590x16mm` | `Pasek zębaty` |
| `61906 RS` | Łożysko kulkowe zwykłe 30x47x9 ( 6906 ) | `61906 RS 30x47x9 ( 6906 )` | `Łożysko kulkowe zwykłe` |
| `OR-7X1 EPDM` | OR-7X1 EPDM *(sama = Symbol)* | `OR-7X1 EPDM` | `Oring` |

Zastosowane do **703 pozycji**. Pozostałe zostawione bez zmian:

- **486 numerów rysunków RM** (wzorzec `PREFIKS-NNN.NN[sufiks]`, prefiks może
  być literowy: `DUO-`, `ZS4R-`, `STD-`, `NS-`, `PA-`, `OB01-`) — te mają
  własne, poprawne nazewnictwo i nie są elementami znormalizowanymi.
- **99 kodów numerycznych** (Festo i podobne) — Symbol to czysto numeryczny
  kod magazynowy, a jedyny prawdziwy numer katalogowy producenta jest
  w Nazwie (`Siłownik ESNU-20-20-P-A-MA`). Reguła „Nazwa=Symbol"
  zniszczyłaby jedyne miejsce z danymi do zamówienia.
- **93 pozycje** ocenione ręcznie jako zbyt niejednoznaczne.

### 3.7. Rozbieżności Excel ↔ Subiekt

⚠️ **Nie każda różnica nazwy to nasza zmiana.** Po odjęciu 703 świadomych
zmian zostały **23 rozbieżności istniejące od początku**, gdzie Excel bywał
**gorszy** od Subiekta:

- `T5-210/10` — Subiekt: `Pasek zębaty T5 210x10mm`, Excel: **`1`** (śmieć)
- `319941` — Subiekt: `ANPS-20`, Excel: `Główka cięgła M12 GZ prawa` (inny towar)
- `014-100.03` / `014-100.04` — **zamienione nazwy** („duży 1" ↔ „duży 2")
- `576421`, `8025354` — Subiekt ma pełniejszy opis Festo, Excel obcięty

Rozstrzygnięte przez użytkownika w arkuszu **„Rozbieznosci do decyzji"**
(kolumna DECYZJA: `SUBIEKT` / `EXCEL` / własna nazwa): **11 zmienionych,
12 zostawionych**.

### 3.8. Położenia (regał/półka)

Tryb **`pola-wlasne --plan --zapisz`** (nowy, `PolaWlasne.cs`), partiami
po 300 → **1367 pozycji**.

```
NexoRecon.exe pola-wlasne --plan=regaly_1.json --zapisz --out=w.json
```
```json
{ "pole": "PoleWlasne1",
  "pozycje": [ {"symbol":"011-100.49", "wartosc":"R5/P1"} ] }
```

**Subiekt nie ma standardowego pola na położenie.** W bazie są dwa pola
`Lokalizacja`, ale żadne się nie nadaje:
- na asortymencie — opis wprost: *„Dla przyszłych zastosowań"* (zarezerwowane
  przez InsERT, brak w GUI),
- na pozycji dokumentu przyjęcia — to pozycja dokumentu, nie kartoteka.

Użyte więc **proste pole własne `PoleWlasne1`** (8 slotów, wszystkie były
wolne). Format wartości `R22/P4` — jeden ciąg, bez rozbijania na regał/półkę.

### 3.9. Czyszczenie starych położeń z pola Opis

Po wszystkim okazało się, że **618 pozycji** miało w polu Opis stare
położenie — dokładnie ten problem, od którego zaczynaliśmy:

- **489** w formacie `Reg 20.4`
- **129** okrojonych resztek: `Reg` (115), `Reg.` (12), `Re 20.1`, `Regał 22/P3`

Istotne: **291 z tych 489 pokazywało NIEAKTUALNE miejsce** (np. Opis
`Reg 20.4`, a rzeczywiste położenie `R21/P4`) — towar został przełożony,
a stary Opis o tym nie wiedział. Czyszczenie usunęło mylącą informację.

**Jedna pozycja świadomie zostawiona:** kartoteka `8741127` ma w Opisie
`8743246` — inny numer niż jej Symbol, może być kodem powiązanego wariantu.
Nie kasujemy czegoś, czego nie rozumiemy.

Stan końcowy Opisów: **717 z rodzajem produktu**, **636 pustych**.

---

## 4. Co nie weszło (świadomie)

- **`576410`** (Płyta zaślepka VABB-B10-20-E) — rodzaj **„Usługa"**
  w Subiekcie. Usługi nie mają stanu magazynowego: PW przyjęło pozycję do
  dokumentu, ale stan się nie utworzył — **bez błędu**. Do decyzji: zmienić
  rodzaj na Towar, czy zostawić.
- **9 pozycji** bez położenia w Excelu — nie dostały wpisu w `PoleWlasne1`.
- **22 pozycje** z ilością 0 — kartoteki istnieją, nie ma czego przyjmować.

---

## 5. Zmiany w kodzie

### 5.1. Nowe tryby mostu

| tryb | plik | co robi |
|---|---|---|
| `pw` | `Pw.cs` | przychód wewnętrzny — lustrzane odbicie `Rw.cs` |
| `pola-wlasne` (z planem) | `PolaWlasne.cs` | zapis wartości prostego pola własnego; **bez planu** = odczyt metadanych |
| `magazyn-zaloz` | `MagazynZaloz.cs` | zakłada magazyn |

### 5.2. Przepięcie MAG → Magazyn

| plik | co |
|---|---|
| `subiekt_magazyn_gui.py:50` | `MAGAZYN = "Magazyn"` |
| `Zd.cs:~219` | domyślny magazyn ZD |
| `Rw.cs`, `Pw.cs` | fallback gdy plan nie poda magazynu |

⚠️ Stała `MAGAZYN` dotyczy **wyłącznie zapisów**:

| funkcja | używa stałej? | skutek |
|---|---|---|
| odczyt stanów (`pobierz_magazyn`) | **NIE** | ✅ tryb `magazyn` SUMUJE wszystkie magazyny |
| zapis progów | TAK | ⚠️ szedł na pusty MAG |
| tworzenie RW | TAK | ⚠️ zdejmowałby z MAG |

Czyli **przeglądanie stanów działało od ręki** po migracji — do poprawy były
tylko ścieżki zapisu.

**Nie mylić** z `UWAGI_MAGAZYN = "MAGAZYN"` (`subiekt_magazyn_gui.py:53`,
`subiekt_dokumenty_gui.py:154`) — to znacznik tekstowy w Uwagach dokumentów,
nie symbol magazynu. Nazwa tylko przypadkiem podobna.

### 5.3. Opis i Położenie w GUI

- **Most**: tryby `magazyn` i `stan` zwracają teraz `Opis` i `Polozenie`.
  W `Magazyn.cs` oba pola są **w projekcji EF**, nie przez sięgnięcie po
  encję po fakcie — każde takie sięgnięcie to osobne zapytanie i cofnęłoby
  zysk z jednego przelotu (~7 s na 3444 kartotekach).
  W `Stan.cs` jako property z wartością domyślną, nie parametry konstruktora:
  `Poz` tworzymy też dla kartotek nieistniejących.
- **Okno Magazyn**: kolumny w kolejności **Nazwa → Opis → Położenie**.
  Szukajka obejmuje oba — `oring` znajdzie po rodzaju, `r20` wypisze
  wszystko z regału 20.
- **Karta pozycji**: Opis i Położenie w sekcji „Kartoteka i stany",
  Położenie wyróżnione. Oba dopisane do zbioru `znane`, żeby nie dublowały
  się w sekcji „pozostałe pola z mostu".

---

## 6. Pułapki, które kosztowały czas

### 6.1. Dwie różne „jednostki organizacyjne" w SDK

- `InsERT.Moria.Kadry.Duze.IJednostkiOrganizacyjne` → **DZIAŁ kadrowy**
  (`JednostkaOrganizacyjnaGr`: Nazwa, JednostkaNadrzedna… **brak Symbol,
  brak NIP**). Mimo najbardziej oczywistej nazwy — to NIE to.
- `InsERT.Moria.ModelOrganizacyjny` → **CENTRALA/ODDZIAŁ firmy** (klasa
  `JednostkaOrganizacyjna`, podklasy `Centrala` i `Oddzial`). **To** jest
  wymagane przez `Magazyn.Dane.JednostkiOrganizacyjne`.
  Dostęp: `ICentrale.Znajdz()` (zawsze jedna) + `IOddzialy.Dane.Wszystkie()`.

Właściwości (`Symbol`, `Nazwa`) nie są jednolicie dostępne na typie bazowym
mimo że dokumentacja je tam wypisuje — trzeba `dynamic`. **Pole NIP nie jest
bezpośrednio na tym obiekcie** — dopasowanie zadziałało po Symbolu.

### 6.2. Zapis prostych pól własnych

Proste pola własne (`PoleWlasne1..8`) zapisuje się **wprost na encji**:
`Asortyment.PolaWlasne.PoleWlasne1` (typ `PolaWlasneAsortyment`).

**NIE** przez `UtworzPolaWlasneAdv2Accessor` — ten obsługuje pola
**zaawansowane v2**, których ta baza nie ma:

> *„Dla encji 'InsERT.Moria.ModelDanych.Asortyment' nie zdefiniowano
> zaawansowanych pól własnych w wersji 2."*

Dodatkowo to metoda **rozszerzenia**, więc nie da się jej wywołać na
argumencie `dynamic` (błąd kompilacji **CS1973**) — trzeba rzutować
`ob.Dane` na `InsERT.Moria.ModelDanych.Asortyment`.

### 6.3. Kartoteki są wspólne dla magazynów

Lista „Asortyment" filtrowana na magazyn pokazuje **wszystkie** kartoteki
uprawnione do bycia na tym magazynie, niezależnie od tego, czy tam coś leży.
To nie jest kopiowanie danych — magazyny współdzielą jeden katalog towarów.

### 6.4. Usługi nie przyjmują stanu

Pozycja rodzaju „Usługa" zostanie przyjęta do dokumentu PW **bez błędu**,
ale stan magazynowy się nie utworzy. Trzeba to wychwycić porównaniem
plan ↔ rzeczywisty stan po zapisie.

### 6.5. Symbol ze spacją wiodącą

Cały most trimuje symbole, więc kartoteka z symbolem `" 35/35/1,5"` była
niewidoczna dla trybu `rw` („brak kartoteki"), a tryb `symbole` uznawał ją
za „już poprawną". Widać to **tylko na liście Asortymentu** jako wcięcie
wiersza. Naprawa: ręcznie w Subiekcie (`Home`, `Delete`, zapis).

### 6.6. Tryb `dokumenty` nie widzi PZ ani FZ

Czyta tylko ZK/ZD/RW/WZ. „Brak dokumentów z tą pozycją" z tego trybu **nie
znaczy**, że kartoteka nie ma historii zakupu — od tego jest tryb `stan`
(`OstatniaCenaZakupu` / `DataOstatniegoZakupu`).

---

## 7. Pliki

### Excel: `magazyn 28.05.2026.xlsx`

| arkusz | zawartość |
|---|---|
| `Arkusz1` | oryginał inwentaryzacji (1410 wierszy), nietknięty |
| `Import do Magazynu` | dane finalne (1376): Symbol, Nazwa, Opis, Dostępne, Położenie, progi |
| `Raport zmian` | co odpadło i dlaczego, zmienione symbole, podsumowanie liczbowe |
| `Rozbieznosci do decyzji` | 23 rozbieżności Excel↔Subiekt z decyzją użytkownika |
| `Brak w Subiekcie` | pozycje bez kartoteki (przed ich założeniem) |

### Ślad roboczy w `C:\RMPAK_CLIENT\`

`magazyn_przed.json` → `magazyn_final2.json`, plany i wyniki `rw_*.json`,
`pw_*.json`, `regaly_*.json`, `kartoteki_*.json`, skrypty `zaloz_kartoteki.py`
i `obrob_reczne.py`.

---

## 8. Nadal do zrobienia

- [ ] **Nazwać `PoleWlasne1` jako „Położenie"** w Subiekcie
      (Konfiguracja → Pola własne) i ustawić widoczność — dane już tam są
      (1367 wpisów), ale pole nie ma etykiety w GUI.
- [ ] Zdecydować co z **`576410`** (rodzaj „Usługa" — nie przyjmuje stanu).
- [ ] Zdecydować co z **`8741127`** (Opis `8743246` — nieznany kod).
- [ ] Uzupełnić **636 pustych Opisów** rodzajem produktu.
- [ ] Rozważyć osobne pole na **numer katalogowy** elementu znormalizowanego
      (dziś siedzi w Symbolu; wtedy Symbol mógłby być czysto wewnętrzny).
