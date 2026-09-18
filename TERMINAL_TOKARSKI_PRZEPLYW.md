# Terminal tokarski RM_BAZA — przepływ informacji

**Status:** PROJEKT — kodu jeszcze nie ma (dokument z 18.09.2026, do realizacji
za kilka dni). Nic z tego nie jest jeszcze wdrożone.

**Drugi koniec tego łańcucha:**
[`RMPAK_PRODUKCJA_USTALENIA.md`](RMPAK_PRODUKCJA_USTALENIA.md) — kalkulator
RMPAK, który te dane skonsumuje (dziś liczy z wartości wpisywanych ręcznie),
i dalszy obieg PW/RW do Subiekta. Tam są też ustalenia o cenie jako snapshot
(§10) i o tym, że kalkulator wystawia PW, a magazyn RW (§15b) — terminal tego
NIE zmienia, tylko podmienia źródło czasu i materiału z szacunku na pomiar.

## Założenie

Terminal przy tokarce nie jest drugim kalkulatorem ani osobną aplikacją produkcyjną z własną logiką biznesową.

Jego zadanie to zebrać wiarygodne dane z produkcji:

- jaki rysunek / detal jest wykonywany,
- kto go wykonuje,
- kiedy rozpoczęto i zakończono pracę,
- ile czasu faktycznie poświęcono,
- jaki materiał zużyto,
- ile sztuk wykonano poprawnie,
- ile powstało braków,
- ewentualne uwagi operatora.

Właściwe liczenie kosztu pozostaje po stronie RM_BAZA.

---

## Ogólna architektura

```text
RYSUNEK / ZLECENIE
       ↓ CODE128
TERMINAL TOKARZA
Windows + ekran dotykowy + skaner
       ↓ HTTP
FLASK na serwerze RM_BAZA
       ↓
BAZA PRODUKCJI.sqlite
       ↓
agregacja czasu + materiału + ilości
       ↓
KALKULATOR RMPAK
       ↓
koszt wykonania / szt.
       ↓
PW / dalszy obieg RM_BAZA
```

Terminal nie otwiera bezpośrednio żadnego pliku SQLite po sieci.

Komunikacja:

```text
Tokarnia
   ↓ HTTP / Wi-Fi LAN
Flask na serwerze
   ↓ lokalnie
SQLite
```

---

# 1. Utworzenie pozycji w RM_BAZA

Konstruktor tworzy pozycję projektu, np.:

```text
Projekt:       2630
Rysunek:       2630-500.20
Nazwa:         Wał napędowy
Ilość:         4 szt.
item_id:       18452
```

Na wydruku rysunku umieszczany jest kod CODE128.

Najlepiej, żeby kod nie zawierał wyłącznie numeru rysunku, ale stabilny identyfikator rekordu, np.:

```text
RM|P2630|I18452
```

Pod kodem kreskowym normalnie pozostaje czytelny numer:

```text
2630-500.20
```

Dzięki temu skan jednoznacznie wskazuje konkretną pozycję RM_BAZA.

---

# 2. Tokarz skanuje rysunek

Tokarz podchodzi do terminala i skanuje CODE128.

Skaner USB pracuje jako klawiatura HID:

```text
RM|P2630|I18452<ENTER>
```

Przeglądarka na terminalu ma aktywne pole skanowania.

Po zeskanowaniu JavaScript wysyła do Flaska np.:

```text
POST /api/production/scan
```

Przykładowe dane:

```json
{
  "terminal": "TOKARNIA_01",
  "barcode": "RM|P2630|I18452"
}
```

Terminal sam nie analizuje baz projektu.

---

# 3. Flask rozpoznaje pozycję

Serwer RM_BAZA odczytuje pozycję i zwraca terminalowi kartę pracy.

Na ekranie może pojawić się:

```text
PROJEKT:      2630
RYSUNEK:      2630-500.20
NAZWA:        Wał napędowy
DO WYKONANIA: 4 szt.

[ PODGLĄD RYSUNKU ]

Wykonano wcześniej: 0 / 4
Czas zapisany:      0:00
Materiał:           brak

              [ START ]
```

W tym miejscu można również wyświetlać PDF, DWF lub obraz rysunku.

Tokarz nie musi ręcznie wyszukiwać projektu ani pozycji.

---

# 4. Identyfikacja operatora

Jeśli chcemy wiedzieć, kto wykonywał detal, każdy pracownik może mieć własną kartę z CODE128.

Na początku zmiany operator skanuje swoją kartę, np.:

```text
OP|17
```

Terminal zapamiętuje:

```text
operator_id = 17
terminal_id = TOKARNIA_01
```

Nie trzeba ponownie wybierać operatora dla każdej pozycji.

---

# 5. Rozpoczęcie pracy

Tokarz naciska:

```text
[ START ]
```

Do bazy produkcyjnej zostaje zapisane zdarzenie:

```text
production_session

id                  9281
project_id          2630
item_id             18452
drawing_no          2630-500.20
terminal_id         TOKARNIA_01
operator_id         17
started_at          2026-09-18 07:34:12
finished_at         NULL
status              RUNNING
```

Nie zapisujemy wyłącznie jednej wartości typu `calc_hours`.

Zachowujemy historię rzeczywistych sesji produkcyjnych.

---

# 6. Ekran podczas pracy

Interfejs powinien być prosty i przystosowany do ekranu dotykowego:

```text
┌────────────────────────────────────────┐
│ 2630-500.20       WAŁ NAPĘDOWY         │
│                                        │
│            CZAS: 01:17:42              │
│                                        │
│          [ WSTRZYMAJ ]                 │
│                                        │
│ Materiał: 316 / pręt Ø60               │
│                                        │
│          [ + MATERIAŁ ]                │
│                                        │
│          [ ZAKOŃCZ ]                   │
└────────────────────────────────────────┘
```

Timer jest pomocniczy.

Na zakończenie operator musi mieć możliwość korekty czasu rzeczywistego, ponieważ w trakcie pracy może:

- odejść od maszyny,
- wykonywać pomiar,
- pomagać innemu pracownikowi,
- mieć przerwę,
- wykonywać czynności niezwiązane bezpośrednio z detalem.

---

# 7. Rejestracja materiału

Tokarz nie wpisuje kosztu materiału w PLN.

Wpisuje rzeczywiste zużycie materiału.

Przykład:

```text
Materiał:     316
Forma:        Pręt
Średnica:     60 mm
Zużycie:      540 mm
```

albo:

```text
Materiał:     PA6
Forma:        Pręt
Średnica:     80 mm
Zużycie:      220 mm
```

Do bazy zapisujemy dane źródłowe:

```text
material_usage

session_id     9281
material       316
profile        PRET
dimension_1    60
length_mm      540
quantity       1
```

RM_BAZA wylicza z tego:

```text
przekrój
   ↓
objętość
   ↓
masa
   ↓
gęstość materiału
   ↓
aktualna cena/kg
   ↓
koszt materiału
```

Dzięki temu operator nie musi znać cen materiałów.

---

# 8. Zakończenie zlecenia

Po naciśnięciu:

```text
[ ZAKOŃCZ ]
```

wyświetla się podsumowanie:

```text
2630-500.20
Wał napędowy

Czas pracy:
[ 1:32 ]

Wykonano OK:
[ 4 ] szt.

Braki:
[ 0 ] szt.

Materiał:
316 / pręt Ø60 / 540 mm

[ + DODAJ MATERIAŁ ]

Uwagi:
[____________________________]

        [ ZAKOŃCZ ZLECENIE ]
```

Po zatwierdzeniu terminal wysyła komplet danych do serwera.

---

# 9. Zapis transakcyjny

Flask zapisuje cały komplet danych transakcyjnie.

Przykład:

```text
session 9281
finished_at = 09:06
worked_minutes = 92
qty_ok = 4
qty_scrap = 0
status = FINISHED
```

oraz wszystkie wpisy zużycia materiału.

Albo zapisze się komplet, albo nic.

---

# 10. Kilku pracowników przy jednym detalu

Nie nadpisujemy pojedynczego pola czasu.

Jeśli detal wykonywało kilka osób:

```text
2630-500.20

Kowalski    0:45
Nowak       1:10
----------------
RAZEM       1:55
```

w bazie pozostają osobne sesje.

Kalkulator RM_BAZA sumuje je podczas obliczania kosztu.

---

# 11. Połączenie z kalkulatorem RMPAK

Obecny kalkulator RMPAK może nadal korzystać z pól kosztowych, ale źródłem danych produkcyjnych powinna być osobna baza produkcji.

Przykład zapytania:

```text
daj rozliczenie dla item_id = 18452
```

Serwer odpowiada np.:

```json
{
  "hours": 1.9167,
  "material_cost": 84.32,
  "qty_ok": 4,
  "qty_scrap": 0
}
```

Kalkulator pokazuje:

```text
2630-500.20

Ilość:                    4 szt.

CZAS
Z terminala:              1:55 h
Stawka:                  85,00 PLN/h
Robocizna:              162,92 PLN

MATERIAŁ
316 pręt Ø60 × 540      84,32 PLN

Dodatkowe:                0,00 PLN

────────────────────────────────
Koszt partii:           247,24 PLN
Koszt / szt.:            61,81 PLN
```

---

# 12. Jedno źródło prawdy

Nie należy bez potrzeby kopiować tych samych wartości między tabelami.

Nie:

```text
Terminal DB
     ↓ kopiowanie
calc_hours
     ↓ kopiowanie
inna tabela
```

Lepiej:

```text
ZDARZENIA PRODUKCYJNE
        ↓ SUM()
KALKULATOR
        ↓
wynik kosztowy
```

Baza produkcyjna jest źródłem danych rzeczywistych.

---

# 13. Zamrożenie kosztu historycznego

W chwili wystawienia PW lub innego dokumentu kończącego produkcję można zapisać snapshot kosztu.

Przykład:

```text
PW utworzono:
18.09.2026 10:15

czas przyjęty:       1.9167 h
koszt materiału:     84.32 PLN
stawka:              85.00 PLN/h
koszt/szt.:          61.81 PLN
```

To ważne, ponieważ późniejsza zmiana ceny materiału lub stawki godzinowej nie może zmienić historycznego kosztu wykonania detalu.

---

# 14. Lokalizacja bazy SQLite

Proponowana struktura:

```text
SERWER RM_BAZA
│
├── rm_serwer / Flask
│
├── RM_BAZA
│
└── data/
    └── production.sqlite
```

Nie należy robić:

```text
TOKARNIA
  ↓ Wi-Fi
\\serwer\RM_BAZA\production.sqlite
```

Terminal nie otwiera pliku SQLite.

Prawidłowo:

```text
TERMINAL TOKARNIA
      ↓
HTTP / Wi-Fi LAN
      ↓
FLASK
      ↓
production.sqlite
```

---

# 15. Hardware terminala

Docelowo:

```text
Windows x86
+
ekran dotykowy 15,6–17"
+
fanless mini PC
+
skaner CODE128 USB
+
przeglądarka Edge / Chrome
```

Terminal działa w trybie kiosku i otwiera np.:

```text
http://192.168.100.84:5060/tokarnia
```

Na terminalu nie trzeba instalować właściwej aplikacji RM_BAZA.

Aktualizacja interfejsu odbywa się na serwerze.

---

# 16. Dodatkowa wartość systemu

Po kilku miesiącach RM_BAZA zaczyna mieć dane rzeczywiste o produkcji.

Można porównywać kalkulację z wykonaniem:

```text
2630-500.20
plan kalkulowany:       2:00
rzeczywisty:            1:55

2630-500.21
plan kalkulowany:       1:00
rzeczywisty:            2:35   ⚠

2630-500.22
plan kalkulowany:       0:45
rzeczywisty:            0:41
```

Dzięki temu system odpowiada nie tylko na pytanie:

> Ile kosztował detal?

ale również:

> Jak trafnie wyceniliśmy jego wykonanie przed produkcją?

To daje podstawę do późniejszego poprawiania norm czasowych, wycen ofertowych i kontroli rentowności produkcji własnej.
