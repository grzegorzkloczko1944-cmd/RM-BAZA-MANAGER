---
name: project_lozyska_katalog_28_09
description: Katalog łożysk w Subiekcie 28.09.2026 — ZAKOŃCZONE: 1127 kartotek, 1160 zdjęć, 1172 modele 3D z miniaturami; pułapki olefile/limit 500/kopia MAG/symbol niezmienny
metadata:
  type: project
---

# Łożyska: kartoteki, zdjęcia, modele 3D (28.09.2026)

293 oznaczenia × 4 warianty (`ZZ`, `2RS`, `SS ZZ`, `SS 2RS`) = **1172
pozycje**. Modele: `B:\Znormalizowane\Łożyska katalog\gotowe\*.ipt`
(1172 pliki), rendery PNG: `C:\iLogic\LOZYSKA\miniatury`.

## NOMENKLATURA (źródło prawdy = iProperties modelu)

    plik:   6004 ZZ 20x42x12.ipt
    symbol: 6004 ZZ              (Part Number)
    nazwa:  6004 ZZ 20x42x12     (= nazwa pliku)
    opis:   Łożysko kulkowe zwykłe      /  nierdzewne dla „SS ”

Symbol = nazwa pliku BEZ wymiarów. Ta sama reguła w trzech miejscach:
zakładanie kartotek, wgrywanie zdjęć, zasiew indeksu 3D.

## ZROBIONE

**Kartoteki** (tryb mostu `kartoteki`, jeden wsad, 4 min 14 s):
1127 założonych, 10 ujednoliconych, 35 bez zmian, 0 błędów.
Ustawienia: towar, jm `szt`, cena 0, VAT 23/23, bez dostawcy.
Kartotek w Subiekcie: 3518 → **4678**.

Przy ujednolicaniu poprawione **dwa błędne wymiary w Subiekcie**:
`688 ZZ` 8x16x5 → **8x16x4**, `SS 6300 2RS` 15x32x13 (to wymiary 63002!)
→ **10x35x11**. Potwierdzone katalogiem Timken i modelem.

**Zdjęcia** (`subiekt_lozyska_zdjecia.py --nadpisz --zapisz`, 7 min):
1160 wysłanych, 9 zastąpionych, 0 błędów. 600×600, Subiekt sam robi
miniaturę. ⚠️ `--nadpisz` użyte za JEDNORAZOWĄ zgodą —
[[feedback_nadpisywanie_pytaj]].

## Modele 3D — ZROBIONE (19:53–19:55)

Łożyska z Content Center **nie mają plików .idw**, a `indeks_modeli_3d.py`
buduje mapę właśnie z nich — stąd pusta kolumna „3D" w MAG mimo 1172 modeli
na `B:\Znormalizowane\Łożyska katalog\gotowe`.

Rozwiązanie bez zmian w indeksie ani na serwerze — **mechanizm wpisów
ręcznych już istniał**:

1. **`indeks_lozyska_zasiew.py --zapisz`** → 1172 ścieżki jako
   `zrodlo='reczny'`. Takie wiersze są CHRONIONE (`map-model3d-zapisz`
   nie nadpisze, `map-model3d-usun-*` nie skasuje), więc nocny indeks
   może chodzić bez obaw.
2. **`indeks_modeli_3d.odswiez_miniatury()`** → 1172 zapisane, 0 bez
   miniatury, 0 błędów (29 s). Czyta ścieżki wprost z indeksu, więc NIE
   trzeba skanować całej biblioteki `--root`.
3. **`subiekt_kopia_sync.py`** → odświeżenie kopii dla MAG.

Weryfikacja: **1172/1172** mają `modeli=1` i `ma_mini3d=1`.

⚠️ Miniatury w plikach `.ipt` zrobione przez API Inventora (user, do 19:50).
Te sprzed ~18:00 miały kadr przybliżony na przekrój kulki — dlatego zasiew
czekał na komplet. Sprawdzenie przed startem: mtime plików + próbka przez
`miniatura_modelu()`.

⚠️ Po synchronizacji MAG potrzebuje chwili na dociągnięcie 1172 obrazków —
pusta kolumna „3D" zaraz po odświeżeniu to normalne, nie błąd.

## ⛔ Pułapki (sprawdzone, nie powtarzać)

* **`olefile` NIE widzi miniatury** w .ipt (właściwość 17 czyta się przez
  COM). Na tej podstawie stwierdziłem „modele nie mają miniatur" — błąd.
  Właściwe narzędzie: `indeks_modeli_3d.miniatura_modelu()`.
* **`/mag/szukaj` tnie wynik na 500** — bilans „brakuje 215 kartotek" był
  fałszywym alarmem. Sprawdzać przez `/mag/kartoteka` per symbol.
* **Kopia dla MAG to OSOBNA baza.** Zdjęcia były w Subiekcie, a MAG ich
  nie pokazywał, bo synchronizacja pyta o miniatury tylko dla kartotek
  nowych/zmienionych. Lekarstwo: `--miniatury-od-nowa` albo przycisk
  „Synchronizuj SUBIEKT" → **TAK** (`miniatury_od_nowa=True`).
* **`SS 6001 RS`** istnieje w Subiekcie, ale nie ma modelu ani PNG —
  wariant spoza czwórki (pojedyncze `RS`). Prawdopodobnie duplikat
  `SS 6001 2RS`; do rozstrzygnięcia (tryb `scal`).
* Pomijać `OldVersions` — inaczej jeden symbol dostaje dwie ścieżki.
* **`rm_klient` NIE MA funkcji `wywolaj()`** — jest `master_batch(operacje)`,
  a klucz to `operacje`, nie `operations`. Zgadnięcie nazwy kosztowało
  nieudany przebieg (na szczęście padł przed zapisem).
* **Symbolu istniejącej kartoteki NIE DA SIĘ zmienić** przez most — Sfera
  traktuje go jako klucz, a cała infrastruktura scalania na tym polega
  („Symbol jest kluczem", [[project_subiekt_scalanie_kartotek]]).

Zobacz też: [[project_subiekt_scalanie_kartotek]],
[[project_mag_indeks3d_zlecenie]], [[project_mag_katalog_lozysk]].
