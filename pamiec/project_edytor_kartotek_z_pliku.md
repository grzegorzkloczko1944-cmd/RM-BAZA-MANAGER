---
name: project-edytor-kartotek-z-pliku
description: "Edytor kartotek — wczytywanie struktury z pliku (CSV płaskie / XLSX drzewko), pole Położenie, fokus na nazwę"
metadata: 
  node_type: memory
  type: project
  originSessionId: 42739f9a-ed55-4c6c-a06d-d2bf1b97a8bf
  modified: 2026-09-09T01:37:44.347Z
---

**WDROŻONE 2026-09-09** w `subiekt_edytor_gui.py` (klasa `EdytorWindow`).

**Przycisk „Z pliku…"** (dawniej „Z projektu…", była to zaślepka bez implementacji) — `_wczytaj_z_pliku()`. Dwa formaty:

- **CSV = płaskie złożenie.** Wiersze to składniki; samego złożenia w nich NIE MA, więc **matkę DODAJEMY z nazwy pliku** (`2627-000.00ZZ YamCandle_Z.csv` → symbol + nazwa). Czytane przez `subiekt_projekt.read_items_csv` + `tree_z_csv`. Test: 21 pozycji, 20 dzieci pod matką.
- **XLSX = pełne drzewko** z arkusza „DRZEWKO TEKST" (`import_bom.find_assembly_tree_rows`). **Matka JEST JUŻ w drzewku** — korzeń wychodzi naturalnie jako symbol, który nie jest niczyim dzieckiem. NIE dokładać nic z nazwy pliku. Test: 20 pozycji, korzeń `2627-650.11ZZ`.

Wczytanie **dokłada** do istniejącej struktury (można złożyć z kilku plików); symbol już obecny zostaje nietknięty, dopisywane są tylko brakujące relacje.

**Pole „Położenie" na karcie Podstawowe** (sekcja 2 „Kartoteka — szczegóły"), obok Symbol/Nazwa/Rodzaj/Jednostka/Cena. To **ta sama `self.var_polozenie`** co pole na karcie Magazyn — jedno pole w dwóch miejscach. UWAGA: `_karta_magazyn()` nie może tworzyć własnej `StringVar`, bo nadpisze tamtą i pola przestaną się zgadzać (kolejność: `var_polozenie` powstaje w karcie Podstawowe, `_karta_magazyn()` wołane później).

**Fokus przy nowej pozycji: NAZWA, nie symbol** (`_dodaj_pozycje`, `_dodaj_skladnik`). Symbol ma już wartość roboczą („NOWA-01") i nadaje się go przyciskiem „Auto" Z NAZWY, więc nazwa jest pierwszą rzeczą do wpisania.

**Komunikaty:** moduł importuje `komunikat as komunikat_ed` z `subiekt_projekt` — `messagebox` (natywny dialog Tk) pozycjonuje się względem monitora GŁÓWNEGO i przy trzech monitorach wyskakuje na złym ekranie. Nowe dialogi w tym module pisać przez `komunikat_ed`, nie `messagebox`.
