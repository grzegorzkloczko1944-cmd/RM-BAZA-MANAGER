---
name: project_serwis_urlopy_crosslink
description: Powiazania krzyzowe urlopy (nieobecnosci) ⟷ wyjazdy serwisowe — ostrzezenia w obie strony + tlo dni nieobecnosci na grafiku B
metadata: 
  node_type: memory
  type: project
  originSessionId: d882ee1f-5d5d-4568-9a7c-422454b8e52f
---

Sprzężenie dwóch tabel: **`employee_availability`** (nieobecności — [[project_urlopy_block]] / [[project_kadry_module]]) i **`service_trips`** (wyjazdy serwisowe, linia B — [[project_serwis_block]]). Serwisant nie może być jednocześnie na wyjeździe i na nieobecności — od 2026-08-06 kolizja jest wykrywana „na krzyż". „Urlop/L4" = **wszystkie typy nieobecności** (filtr tylko po dacie+pracowniku, nie po `reason`).

**Backend (rm_manager.py, po `delete_service_trip`):**
- `find_trips_conflicting_with_absence(db, emp_id, date_from, date_to)` — cienki wrapper na `get_service_trips` (overlap dat). NIE filtruje statusu wyjazdu.
- `find_absences_conflicting_with_trip(db, emp_id, date_from, date_to)` — wrapper na `find_overlapping_absences` (pomija ODRZUCONE; łapie planowane/oczekujące/zatwierdzone). Overlap: `A.from <= B.to AND A.to >= B.from`.

**GUI (rm_manager_gui.py) — ostrzeżenia przy zapisie:**
- Wspólny czerwony dialog `_confirm_cross_conflict_dialog(parent, title, intro, conflict_lines, hint)` — nagłówek „⛔ KOLIZJA: URLOP ⟷ WYJAZD SERWISOWY", zwraca True gdy user świadomie potwierdzi. Wzorowany na `_confirm_overlap_dialog`.
- W `_service_trip_editor._save`: po sprawdzeniu nakładania wyjazdów → sprawdza nieobecności.
- W `_vacation_edit_absence._save`: po grupach wykluczających → sprawdza wyjazdy (dla nie-serwisantów lista pusta, okno się nie pokazuje).

**GUI — tło dni nieobecności na grafiku serwisów (linia B):**
- W `_service_build_chart_tab`: cache `sv['absences']` ładowany w `_reload_lineB` (razem z trips), mapa `sv['absence_days'] = {emp_id: {day_index: label}}` liczona w `_compute_collisions` (pomija ODRZUCONE).
- Malowane w `_draw_month` jako **tło komórki wiersza B** kolorem `#f2b8b8` (mdła jasnoczerwień) — PRZED paskami wyjazdów (`_paint_data` później), więc czysto wizualne: nie zmienia kolorów statusów, kolizji, kliknięć. Tylko dni robocze (`wd < 5`); weekendy zostają szare.
- Tooltip „🏖 Nieobecność: <typ>" dokładany w `_paint_data` tylko gdy komórka nie ma już tipa z wyjazdu. Legenda: próbka `#f2b8b8` „Nieobecność (urlop/L4)" przy „Status:".

**Uwaga przy zmianach:** edytując blok Serwis LUB Kadry pamiętaj, że te dwie tabele są sprzężone w 3 miejscach (2× `_save` + grafik B). Zmiana schematu dat/statusów w jednej dotyka drugiej.

Commit `e363a60` (main), .exe przebudowany. Powiązane: [[project_serwis_block]], [[project_urlopy_block]], [[project_kadry_module]].
