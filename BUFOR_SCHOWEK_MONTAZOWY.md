# Schowek montażowy (bufor RW) — do zrobienia

**Data:** 2026-09-10
**Status:** SPECYFIKACJA — nic jeszcze nie zaimplementowane
**Zgłoszenie:** magazynier ma "dupozawracanie" od monterów — biorą element,
zaraz oddają bo nie pasuje, biorą inny, dobierają, zwracają. Nie chce robić
papieru na każdy pojedynczy ruch.

---

## 1. Problem

Dzisiejszy proces (RW = dokument magazynowy w Subiekcie) wymaga decyzji przy
KAŻDYM wydaniu. Przy montażu maszyny monter próbuje kilka wariantów, zanim
coś pasuje — realny ruch fizyczny jest szumem wokół tego, co faktycznie
zostaje wbudowane. Robienie dokumentu na każdą próbę:

* jest bez sensu księgowo (element wraca tego samego dnia),
* zniechęca magazyniera do jakiejkolwiek ewidencji,
* i tak nie odda prawdy — nikt nie zdąży klikać RW między próbami.

## 2. Rozwiązanie: bufor, nie dokument

Schowek to WARSTWA POŚREDNIA między monterem a Subiektem. W ciągu dnia
zapisuje tylko zdarzenia (pobrano / oddano), a Subiekt widzi jeden ruch
dopiero po zamknięciu — i to NETTO, nie sumę wszystkich prób.

```text
RANO                              KONIEC DNIA
Schowek pusty                          │
                                        ▼
bierze:  A×1, B×2, C×1            RW: A×1, B×1, D×3
oddaje:  B×1, C×1                 (zamiany znikają z papierologii)
dobiera: D×3
        ↓
stan: A×1, B×1, D×3
```

Kluczowa własność: **zwrot tego samego dnia = zero śladu na dokumencie.**
`+1 pobrano, -1 oddano → 0 → nie trafia na RW`. To jedyny powód, dla
którego to rozwiązanie w ogóle rozwiązuje problem magazyniera.

## 3. Model danych

```text
schowki
-------
id
projekt_id       -- schowek NALEŻY do projektu, nie do magazyniera
uzytkownik       -- monter/ekipa (np. "Kowalski")
data
status           -- OTWARTY | ROZLICZONY
rw_numer         -- numer RW z Subiekta, po rozliczeniu

schowek_ruchy
-------------
id
schowek_id
symbol
ilosc            -- +N (pobrano) / -N (oddano)
czas
operator
```

Stan schowka to zawsze `SUM(ilosc) GROUP BY symbol` — nigdy osobne pole
"aktualny stan". Dzięki temu historia jest źródłem prawdy, a nie cache,
który może się rozjechać.

**Jeden projekt może mieć wiele schowków równolegle** — po jednym na
monterów pracujących przy różnych maszynach naraz (`3500 — Kowalski`,
`3500 — Nowak`, `3521 — Kowalski`). Rozliczają się osobno, każdy do
własnego RW.

## 4. Widoczność stanu w ciągu dnia — KRYTYCZNE

Subiekt pokazuje stan magazynowy bez wiedzy o aktywnych schowkach. Trzeba
policzyć dostępność FIZYCZNĄ, nie tylko systemową:

```text
DOSTĘPNE = STAN_SUBIEKT − SUMA(aktywnych schowków dla tego symbolu)
```

Bez tego magazynier "wyda drugi raz" coś, co już chodzi po hali w rękach
montera. To pole musi być widoczne wszędzie, gdzie dziś pokazuje się stan
magazynowy (karta pozycji, okno magazynu) — nie tylko w samym schowku.

## 5. Terminal skanera — dwa tryby

```text
┌────────────────────────────┐
│ SCHOWEK — PROJEKT 3500      │
│ Monter: Kowalski            │
├────────────────────────────┤
│   [ ➜ POBIERAM ]            │
│   [ ← ODDAJĘ ]               │
├────────────────────────────┤
│ W schowku: 17 poz. / 36 szt.│
│ [ POKAŻ SCHOWEK ]            │
└────────────────────────────┘
```

Po wybraniu trybu każdy zeskanowany kod od razu dopisuje wiersz do
`schowek_ruchy` — bez wyboru pozycji z listy, bez wpisywania dokumentu.

**Feedback natychmiastowy po każdym skanie** (kolor + dźwięk):

```text
✓ UCF204                    ✓ UCF204                  ⛔ NIE MA TEJ SZTUKI
  POBRANO                     ODDANO                     W SCHOWKU
  Schowek: 3 szt.             Schowek: 2 szt.            (żaden ruch nie
  Dostępne: 7 szt.                                        zapisuje się)
```

Próba oddania więcej niż jest w schowku = twardy błąd, zero zapisu — zgodnie
z zasadą "nic po cichu".

## 6. Zamknięcie dnia — rozliczenie do RW

```text
SCHOWEK — 10.09.2026, Projekt 3500
-----------------------------------
2627-100.15    2
2627-100.22    1
UCF204         4
M8x20         16
-----------------------------------
4 pozycje / 23 szt.

[ HISTORIA ]   [ ROZLICZ I WYSTAW RW ]
```

Sekwencja (ten sam wzorzec co istniejące PW/RW — suchy przebieg →
potwierdzenie → zapis → read-back, patrz `subiekt_produkcja.py`
`plan_rw()` / `wyslij_rw()` / `sprawdz_rw()`):

```text
1. blokuje schowek (nikt nie skanuje w trakcie rozliczania)
2. liczy stan NETTO (SUM po symbolu, tylko > 0)
3. pokazuje podgląd — user widzi dokładnie, co pójdzie do Subiekta
4. suchy przebieg mostu
5. świadome potwierdzenie
6. zapis RW + read-back (porównanie po wierszach, jak przy PW/RW dziś)
7. sukces → status ROZLICZONY, rw_numer zapisany
```

Bufor NIE wystawia własnego typu dokumentu — produkuje zwykły plan RW,
identyczny w kształcie do tego, co dziś buduje `plan_rw()` z PW. Różnica
jest tylko w źródle pozycji: nie "to, co przyjęło PW", tylko "bilans netto
schowka".

## 7. Zwrot PO rozliczeniu — osobna ścieżka

Jeśli schowek jest już `ROZLICZONY`, a monter następnego dnia oddaje coś
z niego — NIE wolno cofać zamkniętego schowka, bo RW już istnieje w
Subiekcie.

```text
⚠ Pozycja pochodzi z ROZLICZONEGO schowka.
  RW: 87/2026

  Zwrot wymaga ponownego przyjęcia na magazyn.
  [ Otwórz PW zwrotu ]
```

To osobny, prosty dokument przyjęcia — nie mieszamy go z logiką bufora.

## 8. Czego NIE robimy (świadomie, na start)

* Bufor nie zna cen ani wartości — to czysta ewidencja ilościowa; wartość
  liczy Subiekt na RW tak jak dziś (koszt magazynowy, nie cena netto —
  patrz [[project_koszt_magazynowy_vs_cena]]).
* Nie łączymy z PW/kalkulatorem RMPAK — to osobny tor: PW/RW produkcji
  własnej vs. zużycie komponentów kupowanych przy montażu. Mogą działać
  równolegle bez kolizji, bo oba kończą się zwykłym RW.
* Nie projektujemy wielu jednoczesnych rozliczeń jednego schowka — blokada
  na czas rozliczania wystarczy na start.

## 9. Punkty zaczepienia w istniejącym kodzie

* Wzorzec zapisu dokumentu: `subiekt_produkcja.py` — `plan_rw()`,
  `wyslij_rw()`, `sprawdz_rw()` (suchy przebieg → potwierdzenie → zapis →
  read-back po wierszach). Bufor potrzebuje analogicznej trójki, ale z
  planem budowanym z `schowek_ruchy`, nie z pozycji PW.
* Zapis do bazy MUSI iść przez `db_manager.project_con`, nigdy osobnym
  połączeniem do pliku na `Y:` — RM_BAZA pracuje na kopii lokalnej i
  nadpisuje plik przy zwolnieniu locka. Patrz
  [[project_zapis_do_bazy_projektu]] — to źródło błędu, na którym już
  się przewróciliśmy przy zmianie dostawcy złożeń.
* Terminal skanera to NOWA aplikacja (albo tryb istniejącego RM_KOD?, do
  ustalenia) — dzisiejszy RM_KOD.py obsługuje kody odblokowujące PLC, nie
  ma nic wspólnego ze skanowaniem kartotek. Zero infrastruktury do
  reużycia poza wzorcem logowania użytkownika.
* Magazyn dla RW: dziś na sztywno `MASTER` w `plan_rw()` — to samo
  nierozstrzygnięte pytanie co w torze PW/RW produkcji własnej
  ([[project_rmpak_produkcja_pw_rw]]).

## 10. Otwarte pytania do rozstrzygnięcia przed startem

1. Terminal skanera — osobna aplikacja czy tryb w RM_BAZA/RM_KOD?
2. Czy schowek MUSI być przypisany do projektu, czy może istnieć luźny
   "schowek ogólny" (np. materiały eksploatacyjne bez konkretnej maszyny)?
3. Sprzęt: skaner jako klawiatura (HID) czy dedykowany terminal z appką?
4. Czy magazynier widzi WSZYSTKIE aktywne schowki naraz (dashboard), czy
   każdy monter rozlicza swój sam?
