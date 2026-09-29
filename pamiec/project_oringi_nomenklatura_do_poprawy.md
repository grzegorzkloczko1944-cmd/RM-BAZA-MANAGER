---
name: project_oringi_nomenklatura_do_poprawy
description: 14 kartotek oringów niezgodnych z nomenklaturą OR-<D>X<przekrój> <MATERIAŁ> (29.09.2026) — lista do ręcznej poprawy w Subiekcie przez usera; symbolu NIE da się zmienić przez most
metadata:
  type: project
---

# Oringi: niezgodna nomenklatura — DO POPRAWY W SUBIEKCIE

Stan 29.09.2026: **205 kartotek `OR-`**, z tego **191 zgodnych** z wzorcem
`OR-<D>X<przekrój> <MATERIAŁ>` i **14 niezgodnych**.

⏸ **User poprawia RĘCZNIE w Subiekcie** (29.09.2026: „wrócę do tego jak
poprawię w subiekcie"). Powód: symbolu istniejącej kartoteki **NIE DA SIĘ
zmienić przez most** — Sfera traktuje go jako klucz
([[project_subiekt_scalanie_kartotek]]), więc jedyne drogi przez API to
usunięcie (gdy duplikat) albo załóż-nową-i-scal.

Raport: `C:\iLogic\oringi_do_poprawy.csv` (kolumna „Proponowany symbol").

## Lista — 14 pozycji

| # | Symbol obecny | Stan | Problem | Symbol docelowy |
|---|---|---|---|---|
| 1 | `OR-1,6/2-70EPDM` | 0 | ukośnik, brak spacji, twardość 70 | `OR-1,6X2 EPDM` |
| 2 | `OR-11/2-70NBR` | 0 | ukośnik, brak spacji, twardość 70 | `OR-11X2 NBR` |
| 3 | `OR-110X5.33 VMQ` | 3 | kropka zamiast przecinka | `OR-110X5,33 VMQ` |
| 4 | `OR-11x2` | 0 | małe `x`, brak materiału | `OR-11X2 FPM` |
| 5 | `OR-13/1,5-70EPDM` | 0 | ukośnik, twardość | `OR-13X1,5 EPDM` ⚠️ JUŻ ISTNIEJE |
| 6 | `OR-14X2,5` | 7 | brak materiału | `OR-14X2,5 FPM` |
| 7 | `OR-20X2.5 EPDM` | **712** | kropka zamiast przecinka | `OR-20X2,5 EPDM` |
| 8 | `OR-38X4 Silikon` | 0 | `Silikon` zamiast `S` | `OR-38X4 S` ⚠️ JUŻ ISTNIEJE (16 szt.) |
| 9 | `OR-40X3 Silikon` | 0 | `Silikon` zamiast `S` | `OR-40X3 S` ⚠️ JUŻ ISTNIEJE (4 szt.) |
| 10 | `OR-58/3.5 80FPM` | 0 | ukośnik, kropka, twardość 80 | `OR-58X3,5 FPM` |
| 11 | `OR-5X3,5NBR` | 14 | brak spacji | `OR-5X3,5 NBR` |
| 12 | `OR-7X2EPDM` | 17 | brak spacji | `OR-7X2 EPDM` |
| 13 | `OR-90X6` | 0 | brak materiału | `OR-90X6 ?` — **MATERIAŁ DO USTALENIA** |
| 14 | `OR-92X6 Silikon` | 0 | `Silikon` zamiast `S` | `OR-92X6 S` ⚠️ JUŻ ISTNIEJE (6 szt.) |

**Osobno:** `OR-40X4 VQM` (stan 0) — symbol pasuje do wzorca, więc nie ma go
w tabeli, ale **`VQM` to literówka `VMQ`** (przestawione litery). Docelowo
`OR-40X4 VMQ`.

## Podział wg ryzyka

* **Do usunięcia (4)** — stan 0, docelowy symbol JUŻ istnieje:
  `OR-13/1,5-70EPDM`, `OR-38X4 Silikon`, `OR-40X3 Silikon`, `OR-92X6 Silikon`.
  Wzorzec identyczny jak 8 kartotek usuniętych 28.09 ([[project_oringi_wymiarowka]]).
* **Przemianować, stan 0 (5)** — bezpieczne: `OR-1,6/2-70EPDM`,
  `OR-11/2-70NBR`, `OR-11x2`, `OR-58/3.5 80FPM`, `OR-90X6`.
* **Przemianować, MA STAN (5)** — wymaga scalenia, żeby nie zgubić zapasu:
  `OR-110X5.33 VMQ` (3), `OR-14X2,5` (7), `OR-5X3,5NBR` (14),
  `OR-7X2EPDM` (17), **`OR-20X2.5 EPDM` (712 — najczęściej używany, największe ryzyko)**.

## Oznaczenia SILIKONU — cztery zapisy na to samo

| zapis | ile | uwaga |
|---|---|---|
| `VMQ` | 14 | oznaczenie normowe |
| `S` | 3 | skrót — **wszystkie MAJĄ stan** |
| `Silikon` | 3 | pełne słowo — **wszystkie stan 0** (duplikaty wersji `S`) |
| `VQM` | 1 | literówka `VMQ` |

⚠️ Wariantu **`SIL` w bazie NIE MA** (user o niego pytał).

Pary duplikatów silikonowych: `OR-38X4 S` (16) ↔ `OR-38X4 Silikon` (0),
`OR-40X3 S` (4) ↔ `OR-40X3 Silikon` (0), `OR-92X6 S` (6) ↔ `OR-92X6 Silikon` (0).

## Otwarte pytania do usera

1. Jaki materiał ma `OR-90X6`? Ani symbol, ani nazwa go nie podają.
2. Czy ruszamy `OR-20X2.5 EPDM` (712 szt.)? Scalanie niesie tu największe ryzyko.
3. Docelowy zapis silikonu: `S`, `VMQ` czy `SILIKON`? Dziś przeważa `VMQ` (14),
   ale kartoteki ze stanem używają `S`.

## Modele 3D oringów

205 modeli w `G:\Mój dysk\SUBIEKT\Oringi` (user, 29.09.2026) — NIE ma ich
jeszcze na firmowym `B:\Znormalizowane\Oringi`. Kolejność: najpierw poprawa
nomenklatury w Subiekcie, potem kopiowanie modeli i
`indeks_oringi_zasiew.py --zapisz` (inaczej zasiew utrwali stare symbole).

Zobacz też: [[project_oringi_wymiarowka]], [[project_firma_do_zrobienia_29_09]],
[[project_subiekt_scalanie_kartotek]].
