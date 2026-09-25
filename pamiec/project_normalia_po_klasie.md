---
name: project_normalia_po_klasie
description: "Normalia poznajemy po KLASIE (ZNORMALIZOWANE), nie po kształcie symbolu — looks_like_drawing_no odpada, bo symbol Subiekta ląduje w work_drawing_no"
metadata:
  type: project
---

# Normalia poznajemy po KLASIE, nie po kształcie symbolu

Ustalone 25.09.2026 (`cf4bb88`, `e5ca254`). Dotyczy **czterech** miejsc:
Projekt/Aktualizacja, Scal kody handlowe, Raport duplikatów, kolejność
wierszy w arkuszu.

## Co się zmieniło w danych

Dawniej normalia **nie miała numeru rysunku** — i cały system się na tym
opierał: „pusty numer = element handlowy". To przestało być prawdą, gdy
symbole Subiekta zaczęły trafiać do `work_drawing_no` (Podmień / Nazwij /
Scal / dopasowanie kartoteki). Po przypisaniu kartoteki normalia
**ma numer** i każda reguła oparta na jego braku — albo na jego wyglądzie —
zaczyna kłamać.

## Kryterium

```sql
COALESCE(class_manual, class_auto) = 'ZNORMALIZOWANE'
```

Klasa pochodzi z importu, jest jednoznaczna i **niezależna od tego, jak kto
zapisał symbol**. `looks_like_drawing_no` (= „ma cyfrę i NIE ma spacji")
zostaje **wyłącznie jako zapas dla baz bez kolumn klasy** — sprawdzenie
`ma_klase = "class_auto" in cols`.

## ⛔ Dlaczego test po kształcie symbolu nie działa

Błąd szedł **w obie strony**, zależnie od tego, czy symbol ma spację
(spacje w symbolach są dozwolone — [[project_symbole_ze_spacja]]):

| okno | symbol | co się działo |
|---|---|---|
| Projekt/Aktualizacja | `6004 ZZ 20x42x12` (ze spacją) | ⛔ pozycja **niewidoczna** mimo 25 szt. w BOM-ie |
| Scal kody / Raport duplikatów | `6004ZZ`, `UCFL201` (bez spacji) | ⛔ normalia wyglądała na detal i **wypadała** |
| Scal kody / Raport duplikatów | `6004 ZZ` (ze spacją) | ✔ działało **przypadkiem** |

W Projekt/Aktualizacja zamiast tego stoi teraz **`wyglada_na_towar`**, nie
klasa: tam chodzi o odsianie **opisów** wpisanych w pole numeru
(„Przygotowanie powietrza"), nie o rozróżnienie normalia/detal.

⚠️ `wyglada_na_towar` **nie sprawdza już, czy jest cyfra** — odrzuca tylko
puste i dłuższe niż 60 znaków. Warunek „ma cyfrę" wycinał realne pozycje
BOM bez numeru i bez cyfry (`Filtr`, `Zamek`, `sprezyna klawiszy` — 280 szt.).

## Kolejność w arkuszu

`database_manager` sortuje `CASE WHEN klasa = 'ZNORMALIZOWANE' THEN 0 ELSE 1`,
dopiero potem numer i nazwa. Wcześniej znormalia były na górze **tylko dlatego**,
że NULL sortuje się pierwszy; po nadaniu symbolu spadały między rysunki
(`626 ZZ` lądowało między `2637-700.06ZZ` a `EWTR-820.00ZZ`).

To **jedyne zapytanie pobierające pozycje** — arkusz nie sortuje ponownie —
więc zmiana obejmuje też eksport XLSX i pozostałe widoki.

## Wyjątek, który zostaje

Detal własny z numerem rysunku jest poza oknem scalania — **chyba że ten sam
numer stoi w kilku wierszach** (HGH15SO ×2). Patrz
[[project_scalanie_duplikaty_identyczne]].

Sprawdzone na projekcie 75: `6004 ZZ` wchodzi do wszystkich trzech okien,
rama `2637-100.01Z` nadal nie (detal), 78 znormaliów na pozycjach 1–78.

Powiązane: [[project_symbole_ze_spacja]], [[project_sklejanie_duplikatow_bom]],
[[project_scalanie_duplikaty_identyczne]].
