---
name: project_pw_rw_blokady_do_ustalenia
description: "Blokady drugiego PW/RW — celowo miękkie, czeka na ustalenia z logistykiem, NIE naprawiać samemu"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5f190e79-13f0-43ff-a820-54ac4e6eb565
  modified: 2026-09-10T21:49:12.744Z
---

Zasada `1 projekt = 1 PW = 1 RW` (RMPAK_PRODUKCJA_USTALENIA.md §6) to **domyślny przebieg, nie twarde ograniczenie**. §15 świadomie każe trzymać blokadę drugiego PW **miękką**: okno „PW już istnieje — wystawić mimo to?" z domyślnym Nie.

**Why:** cytat z §15 — *„Twarde »nie da się« skończy się wystawianiem PW ręcznie w Subiekcie — i utratą kontroli"*. Dorobienie detalu po PW jest przewidzianym wyjątkiem.

Trzy niespójności wykryte 2026-09-10, **zostawione świadomie** — użytkownik nie zna się na księgowości i pyta logistyka:

1. **RW ma blokadę TWARDĄ, PW miękką** — `btn_rw` wyszarza się na amen gdy RW istnieje ([rmpak_calculator.py](rmpak_calculator.py) `_pokaz_numery`), `btn_pw` nie ma reguły wcale. Skutek: detal dorobiony drugim PW *po* RW nie da się wydać z RM_BAZA.
2. **Formularz PW z Edytora kartotek nie ostrzega w ogóle** — `subiekt_pw_gui` nie woła `dokumenty_produkcji()`, więc drugie PW powstaje tam bez świadomej decyzji, o którą §15 prosi. Tak powstało PW 3/MASTER/2026.
3. **Czy PW z Edytora to „PW projektu"?** Obie ścieżki piszą identyczny Tytuł `RM_BAZA <numer>` i Uwagi, więc `dokumenty_produkcji()` traktuje je jako równorzędne — choć jedno to partia produkcyjna, a drugie doraźne przyjęcie pozycji znormalizowanej.

**How to apply:** NIE naprawiać z własnej inicjatywy — to decyzja procesowa, nie techniczna. Czeka na ustalenia z logistykiem. Gdy przyjdą, zmienić spójnie w obu oknach (kalkulator + Edytor) naraz.

Powiązane: [[project_rmpak_produkcja_pw_rw]], [[project_uwagi_tytul_dokumentow]]
