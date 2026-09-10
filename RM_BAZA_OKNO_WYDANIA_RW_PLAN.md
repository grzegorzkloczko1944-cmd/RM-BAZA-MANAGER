# Okno magazyniera „Wydanie z magazynu" — plan implementacji

Stan: **plan do zatwierdzenia**, nic jeszcze nie zakodowane.
Podstawa: specyfikacja i makieta GUI od użytkownika (10–11.09.2026).

---

## 1. Zasada nadrzędna: skąd co się bierze

```text
POTRZEBA          → Subiekt:
                      ZK  dla pozycji kupowanych
                      PW  dla produkcji własnej
STAN MAGAZYNU     → Subiekt
LOKACJA           → Subiekt (Polozenie na kartotece)
WYDANO WCZEŚNIEJ  → dokumenty RW w Subiekcie
```

**Całe okno operuje na faktach zapisanych w Subiekcie**, nie na założeniach
konstrukcyjnych:

```text
ZK → co trzeba wydać z zakupów
PW → co przyjęto z własnej produkcji i trzeba wydać
RW → co już faktycznie wydano
```

BOM zostaje źródłem **konstrukcyjnym**, ale nie licznikiem magazynowym.

### Dlaczego dwa dokumenty, nie BOM

Tory są rozdzielone od dawna (`RMPAK_PRODUKCJA_USTALENIA.md` §2):

```text
Dostawca ≠ RMPAK  → tor zakupowy    → ZK
Dostawca = RMPAK  → tor produkcji   → PW → RW
```

Detale produkcji własnej **świadomie nie trafiają na ZK** — RMPAK jest
producentem, nie zamawia u siebie. Gdyby potrzeba szła z BOM-u, okno
pokazywałoby pozycje, których nikt jeszcze nie kupił ani nie wyprodukował.

Kod już na tym stoi: `pw_do_rw()` bierze pozycje **dokładnie z PW**, nie
z BOM-u ani kalkulatora (§11 ustaleń) — żeby przyjęcie i wydanie nie
rozjechały się, gdy ktoś później zmieni ilości w projekcie.

### Przykład

```text
ZK 48/2026:              PW 31/MASTER/2026:
  UCFL 201        4        2741-100.01     6
  Czujnik SICK    2        2741-200.02     2
```

daje jedną listę potrzeb:

```text
UCFL 201        potrzeba 4   źródło ZK
Czujnik SICK    potrzeba 2   źródło ZK
2741-100.01     potrzeba 6   źródło PW
2741-200.02     potrzeba 2   źródło PW
```

a potem `POZOSTAŁO = POTRZEBA (ZK/PW) − SUMA RW`.

Kolumna **źródło** zostaje widoczna w oknie — magazynier ma wiedzieć, czy
pozycja przyszła z zakupu, czy z własnej produkcji.

### ⚠️ Nie sumować ZK + PW dla tego samego symbolu

Te drogi są rozłączne z założenia. Jeśli symbol pojawi się w obu (stare
dane, błędnie ustawiony dostawca), **nie dodajemy ilości** — pokazujemy
konflikt do sprawdzenia:

```text
⚠ 2741-100.01 występuje i na ZK 48/2026 (4 szt.), i na PW 31/MASTER/2026 (6 szt.)
  Sprawdź dostawcę tej pozycji — potrzeba niepoliczona.
```

Ciche `4 + 6 = 10` byłoby liczbą, której nikt nie zamierzał.

**Dokument RW jest faktem magazynowym i to on odpowiada na pytanie, ile
naprawdę wyszło z magazynu.** Nie liczymy tego z własnej bazy.

### Czego NIE robimy i dlaczego

**`delivered_qty` zostaje nietknięte.** To pole ma stare znaczenie
„dostarczono od dostawcy". Dopisywanie tam wydań magazynowych zmieszałoby
dwa różne fakty w jednej kolumnie — a ta sama kolumna zasila arkusz główny
i stary skaner.

**Nie zapisujemy postępu wydań do bazy projektu.** Odrzucony wariant „RW
w Subiekcie + zapis do bazy" tworzy dwa niezależne zapisy przy jednej
operacji: gdy jeden przejdzie, a drugi nie, nikt nie wie, która liczba jest
prawdziwa.

### Co z tego wynika dobrego

**Nie potrzeba locka projektu.** Skanowanie i wydawanie nie zapisuje nic do
bazy projektu — powstaje wyłącznie dokument w Subiekcie. Dwóch magazynierów
może pracować równocześnie na tym samym projekcie; kontrolę robimy przed
zapisem (§4).

---

## 2. Haczyk: ręczne RW bez identyfikatora projektu

RW wystawione ręcznie w Subiekcie bez oznaczenia projektu:

```text
RW 145/MASTER/2026
UCFL 201    4 szt.
Uwagi: ""
```

mówi, że wydano UCFL 201, ale **nie mówi, na który projekt**. Takiego
dokumentu nie wolno automatycznie doliczyć do żadnego projektu — ani do
2741, ani do 2742, ani do warsztatu.

### Rozpoznanie po nowym formacie (od 10.09.2026)

Format `RM_BAZA — PROJEKT 2741` **już nie obowiązuje**. Obecny:

```text
Uwagi:  2741 Projekt          ← pierwszy człon = numer projektu
        POBRAŁ: Jan Kowalski  ← drugi wiersz: kto pobrał
Tytuł:  RM_BAZA 2741          ← znacznik pochodzenia
```

Do liczenia „wydano wcześniej" bierzemy RW, w których
`numer_projektu_z_uwag(Uwagi) == numer projektu` — **niezależnie od tego,
czy mają znacznik w Tytule**. Ręczne RW z poprawnie wpisanym numerem MA się
liczyć: magazynier fizycznie wydał towar i to jest fakt.

Znacznik `RM_BAZA` w Tytule rozstrzyga co innego — czy dokument wolno
zmieniać/kasować (patrz `SUBIEKT_MIGRACJA_UWAGI_TYTUL.md` §6). Do zliczania
wydań nie jest potrzebny.

### Co widzi magazynier

RW bez numeru projektu w Uwagach jest **niewidoczne** dla okna. To celowe,
ale musi być powiedziane wprost — okno pokaże w stopce:

```text
ℹ RW bez numeru projektu w Uwagach nie są liczone (3 takie w Subiekcie)
```

żeby różnica „stan spadł, a licznik nie" miała wyjaśnienie na ekranie,
a nie w domysłach.

---

## 3. Wydajność: lekkie zapytanie zamiast pełnego przeglądu

Dziś jedyna droga do RW to tryb `dokumenty`, który ciągnie **ZK + ZD + RW +
PW + WZ z pozycjami** — stąd ~9 s. Dla skanera to za dużo.

### Nowy tryb mostu: `wydanie-stan`

Jedno wywołanie daje wszystko, czego okno potrzebuje na starcie —
potrzebę (ZK + PW) i wydania (RW) tego projektu:

```text
NexoRecon.exe wydanie-stan --projekt=2741 [--magazyn=MASTER] [--out=w.json]
```

```json
{
  "projekt": "2741",
  "magazyn": "MASTER",
  "pozycje": [
    {"symbol": "UCFL 201",    "potrzeba": 4, "zrodlo": "ZK", "wydano": 6},
    {"symbol": "2741-100.01", "potrzeba": 6, "zrodlo": "PW", "wydano": 0},
    {"symbol": "DIN 933 M8x30","potrzeba": null, "zrodlo": null, "wydano": 4}
  ],
  "konflikty": [
    {"symbol": "2741-200.02", "zk": 4, "pw": 6}
  ],
  "rw_bez_projektu": [
    {"numer": "RW 141/MASTER/2026", "data": "2026-09-10", "pozycji": 6}
  ]
}
```

Trzy kolekcje (`ZamowieniaOdKlientow`, `PrzychodyWewnetrzne`,
`RozchodyWewnetrzne`), filtr po numerze projektu z Uwag, sumy per symbol.
Bez cen, bez pozostałych rodzajów dokumentów, bez nagłówków poza tym, co
potrzebne do listy pominiętych RW.

Pola specjalne:

- `potrzeba: null` + `zrodlo: null` → pozycja **spoza BOM-u**, wydana wcześniej
  na ten projekt, ale nieplanowana (§8)
- `konflikty` → symbol i na ZK, i na PW — potrzeba **niepoliczona** (§1)
- `rw_bez_projektu` → gotowa lista do klikalnej stopki (§8)

### Cache — wyłącznie przyspieszenie

Plik JSON obok bazy projektu (nie tabela — ten sam wzorzec co
`subiekt_historia`: awaria cache nie może zablokować pracy):

```json
{"projekt": "2741", "magazyn": "MASTER", "odczyt": "2026-09-11 08:12:03",
 "pozycje": {"UCFL 201": 6, "DFM-20-100": 2}}
```

Zasady:

- **Nigdy nie liczymy prawdy z cache, gdy Subiekt jest dostępny.**
- Cache można skasować w dowolnej chwili i odbuduje się sam.
- Wiek cache jest **widoczny na ekranie** — „dane z 08:12, odświeżam…"
  zamiast cichego pokazywania nieaktualnych liczb.

### Przebieg otwarcia okna

```text
otwarcie okna
     ↓
natychmiast: pokaż cache (jeśli jest) + etykieta „odświeżam…"
     ↓
w tle: wydanie-stan z Subiekta
     ↓
0,5–3 s: podmień liczby, zapisz cache, zdejmij etykietę
```

Gdy Subiekt niedostępny: okno działa na cache, ale **wystawienie RW jest
zablokowane** — bez świeżego odczytu nie wolno wydawać (patrz §4).

---

## 4. Kontrola przed zapisem — obowiązkowa

Dwóch magazynierów może mieć otwarty ten sam projekt. Dlatego przycisk
**ZAKOŃCZ WYDANIE → RW** robi **świeży odczyt** przed utworzeniem
dokumentu:

```text
[ZAKOŃCZ WYDANIE → RW]
     ↓
świeży wydanie-stan + stany magazynu
     ↓
czy coś się zmieniło od otwarcia okna?
     ├─ NIE  → podgląd sesji → potwierdzenie → RW
     └─ TAK  → OKNO RÓŻNIC, decyzja człowieka
```

Okno różnic mówi konkretnie, co się zmieniło — i **rozróżnia dwa przypadki**.

### Zmieniła się POTRZEBA (ktoś wydał w międzyczasie) → ostrzeżenie

```text
⚠ Stan projektu zmienił się podczas pracy

                 Przy skanowaniu   Teraz
Wydano wcześniej        4            7
Pozostało               6            3
Twoje wydanie           6            6

Po zapisaniu projekt będzie miał:
13 / 10 szt.  (+3 ponad potrzebę)

[ Wróć i popraw ]   [ Wystaw mimo to ]
```

„Wystaw mimo to" zostaje: magazynier trzyma towar w ręku i może wiedzieć
lepiej niż BOM — ale musi to być **świadoma decyzja**, nie cichy skutek.

### Spadł STAN MAGAZYNU poniżej sesji → twarda blokada

Bez „Wystaw mimo to". Subiekt i tak dokumentu nie przyjmie, więc taka
opcja tylko przesunęłaby błąd na koniec procesu.

---

## 5. Co powstaje w Subiekcie

Jedno RW na całą sesję, przez istniejące `subiekt_magazyn_gui.utworz_rw()`
(most, tryb `rw` — sprawdzony, nie piszemy nowego):

```text
Uwagi:  2741 Projekt
        POBRAŁ: Jan Kowalski
Tytuł:  RM_BAZA 2741
```

`POBRAŁ` idzie do **drugiego wiersza** Uwag — pierwszy należy do numeru
projektu i tam nic innego nie może stać. Uwagi się drukują, więc nazwisko
będzie widoczne na dokumencie.

Osoba w polu „Pobiera": tabela `users` w `master.sqlite` (18 rekordów,
kolumna `display_name`).

Zapis idzie przez **suchy przebieg → potwierdzenie → zapis → read-back**,
tak jak PW/RW w kalkulatorze RMPAK. Sukces ogłaszamy dopiero po odczytaniu
tego, co powstało.

---

## 6. Pliki

| Plik | Co się dzieje |
|---|---|
| `subiekt_wydanie_gui.py` | **nowy** — całe okno |
| `subiekt_sfera/NexoRecon/WydanieStan.cs` | **nowy** — tryb `wydanie-stan` |
| `subiekt_sfera/NexoRecon/CommandDispatcher.cs` | +1 tryb (odczyt, nie zapis) |
| `subiekt_magazyn_gui.py` | bez zmian — `utworz_rw()` używane jak jest |
| `RM_BAZA_v15_MAG_STATS_ORG.py` | +1 pozycja w menu, otwarcie okna |

### ⚠️ Czego NIE ruszamy

**Stary skaner „SKANER — Uzupełnianie DOSTARCZONO"**
([RM_BAZA_v15_MAG_STATS_ORG.py:12032](RM_BAZA_v15_MAG_STATS_ORG.py#L12032))
zostaje bez zmian — projekty prowadzone starą ścieżką wciąż są w toku.
Nowe okno powstaje **obok**, nie zamiast. Kopiujemy z niego wzorce
(obsługa skanera, fokus, auto-uzupełnianie pola), ale go nie modyfikujemy.

---

## 7. Kolejność prac

1. **Tryb `wydanie-stan`** w moście + test na demo (sam odczyt, bezpieczny).
2. **Szkielet okna** — układ wg makiety, dane z punktu 1, bez wystawiania RW.
   Do obejrzenia, czy układ pasuje magazynierowi.
3. **Sesja wydania** — dodawanie, usuwanie, poprawianie ilości, historia skanów.
4. **Kontrola przed zapisem** (§4) + wystawienie RW.
5. **Cache** — na końcu, bo to wyłącznie optymalizacja.

Po każdym kroku jest co pokazać; 1–2 wystarczą, żeby ocenić, czy pomysł
działa w praktyce.

---

## 8. Polityka wyjątków — ROZSTRZYGNIĘTA (11.09.2026)

| Sytuacja | Reakcja |
|---|---|
| ponad potrzebę | **ostrzeżenie**, można wydać |
| poza BOM | **ostrzeżenie**, można wydać |
| ponad stan Subiekta | **blokada** |
| zmiana RW w tle | ponowna analiza przed zapisem (§4) |
| brak Subiekta | podgląd z cache OK, wystawienie RW NIE |
| RW bez numeru projektu | nie liczyć, ale jawnie pokazać ich liczbę |

Reguła nadrzędna: **fizyczne wydanie jest ważniejsze od założenia BOM-u**,
ale czego nie ma na stanie, tego wydać się nie da.

### Ponad potrzebę — ostrzeżenie w wierszu, bez popupu

„Pozostało 2", magazynier wpisuje 5 → wiersz sesji robi się pomarańczowy
i niesie `⚠ ponad potrzebę o 3 szt.`. Pozycja wchodzi do sesji normalnie.

**Bez osobnego popupu przy każdym skanie** — magazynier skanuje seriami
i okno co chwilę przerywające pracę jest gorsze niż widoczny kolor. Różnica
wraca raz jeszcze przy końcowym podsumowaniu RW.

### Poza BOM — wydać, ale oznaczyć

Smar, elektrody, tarcze, przewody, śruby „z ręki" — odmowa byłaby zbyt
sztywna. Przy skanie kartoteki spoza projektu:

```text
⚠ POZYCJA SPOZA BOM-U PROJEKTU

DIN 933 M8x30
Nie występuje w BOM projektu 2741.

[ Dodaj do wydania na projekt 2741 ]   [ Anuluj ]
```

W tabeli sesji dostaje znacznik **POZA BOM**, a pola wyglądają tak:

```text
Potrzeba:          —          ← nie udajemy potrzeby, której nie ma
Wydano wcześniej:  6          ← nadal sumujemy RW tego projektu
Pozostało:         —
Stan:            120
Wydaję teraz:      4
```

Wcześniejsze wydania liczymy normalnie (to fakt magazynowy), ale „potrzeby"
nie wymyślamy.

To także **materiał analityczny**: pozwoli później sprawdzić, ile kosztów
projektu poszło na materiały, których konstruktor nie miał w BOM-ie.

### Ponad stan — blokada przy dodawaniu do sesji

```text
⛔ Brak wystarczającego stanu

Stan magazynu: 12 szt.
Próba wydania: 20 szt.

[ Ustaw 12 ]   [ Odśwież stan ]   [ Anuluj ]
```

Blokada wchodzi **przy dodawaniu do sesji**, nie przy „Zakończ wydanie" —
inaczej magazynier zebrałby całą sesję, zanim dowie się, że jedna pozycja
jej nie przepuści. Bez „Wystaw mimo to": Subiekt dokumentu nie przyjmie.

### Pominięte RW — lista na kliknięcie

Stopka `ℹ RW bez numeru projektu nie są liczone (3 takie)` jest klikalna
i pokazuje, o które chodzi:

```text
RW 141/MASTER/2026   10.09.2026   6 pozycji
RW 137/MASTER/2026   09.09.2026   2 pozycje
RW 129/MASTER/2026   08.09.2026   8 pozycji
```

Dzięki temu źródło rozjazdu „stan spadł, a licznik nie" znajduje się od razu,
zamiast szukać po Subiekcie.
