---
name: project_lozyska_katalog_28_09
description: Katalog łożysk w Subiekcie — 1127 kartotek + 1160 zdjęć wgranych 28.09.2026; PUNKT WZNOWIENIA: zasiew indeksu 3D czeka na dokończenie miniatur w modelach
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

## ⏸ PUNKT WZNOWIENIA — co zostało

**1. Zasiew indeksu 3D** — `python indeks_lozyska_zasiew.py --zapisz`
(suchy przebieg domyślny; ostatnia próba: 1172/1172 rozpoznane).

Dlaczego osobny skrypt: `indeks_modeli_3d.py` buduje mapę z plików
**.idw**, a łożyska z Content Center rysunków NIE MAJĄ — stąd pusta
kolumna „3D" w MAG mimo istniejących modeli. Zasiew wpisuje je jako
`zrodlo='reczny'`; takie wiersze są CHRONIONE przed automatem
(`map-model3d-zapisz` nie nadpisze, `map-model3d-usun-*` nie skasuje),
więc nocny indeks może chodzić. **Żadnych zmian w indeksie ani na
serwerze — mechanizm wpisów ręcznych już istniał.**

**2. Potem** „Synchronizuj 3D" (miniatury z .ipt) i „Synchronizuj
SUBIEKT" (odświeżenie kopii dla MAG).

**⚠️ CZEKA NA:** generowanie miniatur w modelach przez API Inventora.
Stan na 18:28 — **347/1172 (29%)**, ostatni `6020 ZZ 100x150x24`.
Pliki sprzed ~18:00 mają miniaturę **przybliżoną na przekrój kulki**
(wygląda jak śmieć), nowe pokazują całe łożysko. Krok 2 puścić DOPIERO
po dokończeniu, inaczej indeks zapamięta złe kadry. Zasiew ścieżek
(krok 1) jest od tego niezależny.

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

Zobacz też: [[project_subiekt_scalanie_kartotek]],
[[project_mag_indeks3d_zlecenie]], [[project_mag_katalog_lozysk]].
