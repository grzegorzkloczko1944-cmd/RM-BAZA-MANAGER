---
name: project_okno_wydania_rw
description: "Nowe okno magazyniera \"Wydanie z magazynu\" — obok starego skanera, NIE zamiast"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5f190e79-13f0-43ff-a820-54ac4e6eb565
  modified: 2026-09-10T22:14:04.461Z
---

Planowane okno magazyniera: skan kodu → sesja pozycji → jedno RW ze wszystkimi pozycjami. Specyfikacja i makieta GUI od użytkownika (2026-09-11), pliki w `C:\Users\herrm\Downloads\`: `RM_BAZA_okno_magazyniera_wydanie_RW.md` + zrzut `ChatGPT Image 10 wrz 2026, 21_42_53.png`.

⚠️ **STARY SKANER ZOSTAJE NIETKNIĘTY.** `menu_scanner` / okno „SKANER — Uzupełnianie DOSTARCZONO" ([RM_BAZA_v15_MAG_STATS_ORG.py:12032](RM_BAZA_v15_MAG_STATS_ORG.py#L12032)) działa dalej bez zmian.

**Why:** projekty prowadzone starą ścieżką wciąż idą w toku — kompatybilność wsteczna jest warunkiem, nie życzeniem. Nowe okno powstaje OBOK, nie zamiast.

**How to apply:** nie refaktoryzować starego skanera „przy okazji", nie przenosić z niego kodu w sposób, który zmienia jego zachowanie. Kopiowanie wzorców — tak; modyfikacja — nie.

Stan rozpoznania (2026-09-11):
- **Potrzeba/wydano**: `items` w bazie projektu ma `order_qty`, `work_qty`, `src_qty`, `delivered_qty`, `delivered_updated_at` — 75 kolumn.
- **Lokacja**: NIE ma jej w bazie projektu; jest w Subiekcie jako `Polozenie` na kartotece (RM_BAZA już to czyta: `subiekt_pozycja_gui`, `subiekt_magazyn_gui`, `subiekt_edytor_gui`).
- **Wystawianie RW**: gotowe — `subiekt_magazyn_gui.utworz_rw(pozycje, uwagi, magazyn, zapisz, tytul)`, most tryb „rw".
- **Nierozstrzygnięte**: czy „wydano wcześniej" czytać z RW w Subiekcie (jedno źródło prawdy), czy z `delivered_qty` (szybciej, ale rozjazd przy ręcznym RW). Pytanie zadane, użytkownik przerwał — do ustalenia.

Uwagi RW wg specyfikacji mają nieść `POBRAŁ: <osoba>` — musi trafić do drugiego wiersza Uwag, bo pierwszy należy do numeru projektu (patrz [[project_uwagi_tytul_dokumentow]]).

Powiązane: [[project_uwagi_tytul_dokumentow]], [[project_rmpak_produkcja_pw_rw]]
