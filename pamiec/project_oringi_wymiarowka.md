---
name: project_oringi_wymiarowka
description: Wymiarówka oringów z Subiekta (28.09.2026) — 205 żywych kartotek po usunięciu 8 martwych duplikatów; CSV w C:\iLogic; modele 3D jeszcze nie ma
metadata:
  type: project
---

# Oringi: wymiarówka z Subiekta (28.09.2026)

Zadanie: „pełna wymiarówka stosowanych oringów, nie patrz na materiał".

## Jak szukane

Frazy `oring`, `o ring`, `o-ring`, `uszczelka` w `/mag/szukaj` → 276 trafień,
z tego 216 z „oring/o-ring" w nazwie lub opisie. Wymiar wyciągany wzorcem
`(\d+[.,]?\d*)\s*[x/]\s*(\d+[.,]?\d*)` — zadziałał dla 215/216 mimo trzech
różnych konwencji symboli.

**Ręcznie wykluczone 3 fałszywe trafienia:**
`ZS4R-200.17` („Rolka oringowa" — rolka, nie oring) oraz `S03-P 25X33XL5`
i `K03-P 30X22XL5` (uszczelki H-PU *z oringiem*; format wymiaru
D×D_zewn×długość, nie średnica×przekrój — drugi człon > 15 mm to sygnał).

## USUNIĘTE: 8 martwych kartotek

Stare nazewnictwo sprzed ujednolicenia na `OR-`, **wszystkie ze stanem 0**,
5 z nich dublowało wymiar istniejący już w nowym formacie:

    Oring5x15EPDM, Oring7x15EPDM, oring 7x1 5, Oring16x2EPDM,
    oring 16x2, Oring20x3EPDM, oring 20x3, oring 50x5

Tryb `kartoteka-usun --zapisz` → 8/8 `usunieta`, 0 błędów. Subiekt sam
sprawdza brak powiązań (dokumenty, stany, komplety) i odmówiłby, gdyby
którakolwiek była gdzieś użyta.

## Stan końcowy: 205 kartotek

Jednolity format `OR-<D>X<przekrój> <MATERIAŁ>`, opis „Oring" w 193/205.
Uzupełniony jeden pusty opis (`OR-58/3.5 80FPM` → „Oring").

**Pliki w `C:\iLogic\`:**
* `oringi_wymiarowka.csv` — 205 kartotek (symbol, nazwa, opis, średnica
  wewn., przekrój, materiał, stan)
* `oringi_wymiary_unikalne.csv` — **148 unikalnych wymiarów** (+ wyliczona
  średnica zewnętrzna = d + 2×przekrój) — to jest ta „pełna wymiarówka"
* `oringi_MARTWE_stary_format.csv` — archiwum 8 usuniętych

Wysłane mailem na 98k@wp.pl (Outlook, `Display(False)` — user wysłał ręcznie).

## Ustalenia

* **Materiały to synonimy, nie sprzeczności:** VITON = FKM ≈ FPM (kauczuk
  fluorowy), VMQ = SILIKON. Po ich odsianiu **zero realnych rozjazdów**
  symbol↔nazwa. Rozkład: EPDM 87, FKM 30, FPM 29, VITON 21, NBR 13,
  VMQ 11, SILIKON 8, bez oznaczenia 6.
* **`OR-11x2`** ma małe `x` (reszta 204 wielkie `X`) — ZOSTAWIONE: symbolu
  istniejącej kartoteki nie da się zmienić przez most, a scalanie byłoby
  nieproporcjonalne do literówki.

## Modele 3D — ZROBIONE (29.09.2026, M-OLD, Inventor 2013)

`katalog_oringow/generuj_modele.py --zapisz` → **205 modeli** w
`B:\Znormalizowane\Oringi\` (model na KARTOTEKĘ, nie na wymiar — materiał
= kolor gumy). Metoda TOOLS++ „funkcja 18" (Module4 `TOOLS_CreateOring`):
pierścień ID/OD=ID+2×przekrój, wysokość = przekrój, zaokrąglenie 0,4×przekrój.
Kopia szablonu → Open(False) → Save (2013: Add+SaveAs pada err 5).
Materiały usera: `EPDM`, `NBR-` (z myślnikiem!), `VITON`, `SILIKON`;
FKM/FPM→VITON, VMQ/VQM→SILIKON, `OR-90X6` bez materiału → EPDM.
Part Number = symbol kartoteki; plik = symbol z „/"→„x".
Biały render 300×300 → `miniatury\`, lista `oringi_modele.csv`.
⚠️ Zapis kopii szablonu zostawia `OldVersions\<plik>.0001.ipt` — generator
je kasuje. Przerwany przebieg zostawia PUSTY plik otwarty niewidocznie
w Inventorze — zamknąć `Close(True)` i usunąć (tak było z OR-25X6 VITON).

`indeks_oringi_zasiew.py --zapisz` → 205 przypisań `zrodlo='reczny'` +
205 białych miniatur (`mtime=-1`). Zrobione na serwerze DOMOWYM;
**w firmie: skopiować `B:\Znormalizowane\Oringi` (jeśli dom≠firma) i odpalić
zasiew tam.** Zdjęcia do SUBIEKTA — NIE wgrywane (osobna zgoda).
