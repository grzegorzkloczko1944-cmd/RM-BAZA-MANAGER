---
name: project_regal_z_opisu_migracja
description: 349 kartotek mialo regal wpisany w OPIS zamiast w Polozenie (PoleWlasne1) - przeniesione i znormalizowane do RX/PX 03.10.2026; konwencja RX/PX jest obowiazujaca
metadata:
  type: project
---

# Regał z Opisu → Położenie: 349 kartotek (03.10.2026)

## Zgłoszenie i fałszywy trop

User: „brak możliwości edycji Położenie w Edytorze kartotek", potem
„wyświetla się w Opis a nie w Położenie" i „wcześniej było dobrze".

Pierwsza hipoteza (błąd w kodzie) była **nietrafiona**. Sprawdzone i wykluczone:
`Stan.cs` czyta `a.Opis` i `PolaWlasne.PoleWlasne1` osobno; tryb `magazyn` —
niezależna projekcja EF — daje identyczny wynik; kolumna „Opis" w edytorze
czyta `k["Opis"]`. Żaden kod w repo nie przenosi danych z `PoleWlasne1` do
`Opis`. To były **dane w Subiekcie**, nie program.

⚠️ Druga pomyłka w tej samej sesji: napisałem, że zapis Położenia z Edytora
nie zadziała, bo `kartoteka-edytuj` nie zna tego klucza. Edytor zapisuje
trybem **`kartoteki`** (`zapisz_kartoteki` → `_uruchom("kartoteki", …)`),
a ten obsługuje je przez `UstawPolozenie` od dawna. Suchy przebieg to
potwierdził: `Polozenie: „" → „REG.5.4"`. Sprawdzaj, KTÓRY tryb woła okno,
zanim orzekniesz brak obsługi.

## Przyczyna

Migracja na magazyn nr 2 (09.2026, [[project_magazyn_nr2_migracja]]) wpisała
regały do `PoleWlasne1` dla **1367** kartotek. Poza nią zostało **349**, które
miały regał w polu **Opis** („REG.5.4", „Reg 4.3", „Reg 1", „Reg16.2") i puste
Położenie. Dla nich kolumna Położenie w oknie Magazyn i w oknie wydania była
pusta — magazynier nie znajdował detalu po lokalizacji. User trafił akurat na
jedną z nich (`012-100.06`), stąd wrażenie regresji.

## Decyzje użytkownika

* **Konwencja `RX/PX` jest obowiązująca** — „te w konwencji RX/PX są wszystkie OK".
* **Normalizować** przy przenoszeniu: `Reg 4.3` → `R4/P3`, `REG.5.4` → `R5/P4`,
  sam regał `Reg 1` → `R1` (bez półki).
* **Czyścić Opis** po przeniesieniu — informacja jest już w Położeniu.

## Wykonanie

`narzedzia_regal_z_opisu.py [--zapisz] [--czysc-opis]` — suchy przebieg
domyślnie. Jedna paczka do trybu `kartoteki` (zapis hurtem, CLAUDE.md).

Wynik: **zmieniona=349, zero błędów**. Po migracji: kartotek z wypełnionym
Położeniem 1369 → **1718** (1369+349), z regałem w Opisie **0**.

Formaty źródłowe: `Reg x.y` 233, `Reg x` 58, `REG.x.y` 57, `Reg16.2` 1.

## 6 konfliktów — NIE RUSZANE

Kartoteki z WYPEŁNIONYMI oboma polami. Narzędzie ich nie dotyka (nie zgaduje,
które jest prawdziwe). User rozstrzygnął: **Położenie `RX/PX` jest poprawne**,
Opis to stary ślad.

    011-100.39A  Reg 4.3  / R4/P3   to samo miejsce
    011-100.40B  Reg 5.5  / R5/P5   to samo
    5612B142     Reg 14.5 / R14/P5  to samo
    576410       Reg 15.5 / R15/P5  to samo
    011-100.29   Reg 3.2  / R3/P3   RÓŻNA PÓŁKA  (stan 16)
    011-100.15   Reg 3.2  / R4/P4   RÓŻNY REGAŁ  (stan 24)

Dwie ostatnie mają realny stan i rozbieżne adresy — obowiązuje `RX/PX`,
ale warto sprawdzić fizycznie przy najbliższym wydaniu.

## Przy okazji dołożone

* **Kolumna „Położenie"** w sekcji 4 Edytora kartotek, obok Opisu — od razu
  widać, gdy regał siedzi w złym polu. Wymagało dołożenia pola do trybu
  **`katalog`** w moście (`Katalog.cs`), bo wcześniej go nie zwracał i kolumna
  byłaby pusta. Szerokości sekcji 4 rozdzielają się proporcjonalnie do
  `KOL_LISTA` przy każdym `<Configure>`, więc nowa kolumna weszła sama
  (90–132 px przy oknie 900–1300 px).
* **`kartoteka-edytuj`** zna teraz `polozenie` (używa go okno Asortyment
  i biblioteka modeli) — ta sama zasada co w `UstawPolozenie`:
  `null` = „nie ruszaj", nie „wyczyść".
* **Okno wydania**: wiersz „Ilość wydawana teraz" i „Lokacja" powiększony
  do 18 pt bold — magazynier czyta go stojąc przy stole.
