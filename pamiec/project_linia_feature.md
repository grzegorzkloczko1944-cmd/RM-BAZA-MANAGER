---
name: project-linia-feature
description: "Implementacja funkcji LINIA PRODUKCYJNA — grupowanie projektów-maszyn, lockowanie linii, propagacja etapów równoległych"
metadata: 
  node_type: memory
  type: project
  originSessionId: 80ccf185-a65c-47a4-9b6d-5eed6ab33fa2
---

Zaimplementowana funkcja LINIA PRODUKCYJNA (maj 2026):

**Architektura:**
- Tabele w `rm_master.sqlite`: `production_lines`, `line_projects`
- `parallel_stages_csv` — etapy prowadzone jednocześnie dla całej linii (URUCHOMIENIE, ODBIORY, POPRAWKI)
- Projekt może należeć do max 1 linii (UNIQUE na project_id w line_projects)

**Lock linii:**
- `acquire_project_locks_bulk()` w `lock_manager_v2.py` — omija politykę single-lock
- Po przejęciu locka na projekt → automatycznie locki na pozostałe projekty linii
- Ścieżki: `acquire_lock()`, `force_acquire_lock()`, `_mp_select_and_lock_project()`
- Release: `_release_line_locks()` — wywoływany z `release_lock`, `cancel_lock`, `_mp_unlock_project`, `_mp_cancel_lock`, `_release_current_lock`
- Stan: `_line_locked_pids`, `_line_parallel_stages`, `_line_snapshots`

**Propagacja:**
- `_propagate_parallel_stage(stage_code, start_iso, end_iso)` — propaguje do `_line_locked_pids`
- Wywoływana po każdym zapisie: `save_all_templates`, `save_dates`, `save_stage_template`, drag move/resize (single+multi Gantt)
- Propagacja tylko etapów z `_line_parallel_stages`

**Powiadomienia o zmianie danych (commit 691bf62, maj 2026):**
- `_notify_data_change()` — nowa metoda, wywołuje wszystkie callbacki z `_data_change_callbacks`
- Wywoływana po `save_stage_template` i po zapisie dat (~linia 20034)
- Używana do odświeżania okien zewnętrznych (np. okno kopiowania etapów) po zmianie danych
- Callbacki rejestrowane przez `self._data_change_callbacks.append(cb)` z zewnętrznych okien
- Powiązane z: [[project-optimizer-readiness]]

**UI:**
- Pasek LINIA w panelu ETAPY PROJEKTU (`_render_production_line_bar`)
- Dialog zarządzania liniami (`production_lines_dialog`)
- Nazwy projektów w `project_names` mają sufiks `[nazwa_linii]` (dodawany w `load_projects`)
- Multi-projekt: czerwone podświetlenie wszystkich projektów linii, sekcja linii w prawym panelu
- Selektor projektów: odświeżanie etykiet locków przez `_refresh_mp_lock_labels` → `_mp_selector_refresh_locks`

**Why:** Projekty-maszyny budowane dla jednego klienta mają etapy prowadzone jednocześnie przez tego samego mastera — optymalizator traktuje je jak jedną czynność.
