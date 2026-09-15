---
name: project-optimizer-readiness
description: Wskaźnik gotowości projektu do optymalizacji normalnej w oknie Wybór Projektów
metadata: 
  node_type: memory
  type: project
  originSessionId: 80ccf185-a65c-47a4-9b6d-5eed6ab33fa2
---

Zaimplementowany maj 2026.

**Funkcja:** `rmm.check_optimizer_readiness(project_db_path, project_id)` w rm_manager.py
- Sprawdza warunek trybu normalnego optymalizatora: przynajmniej jeden nie-milestone etap ma przypisanego mastera w `stage_staff_assignments`
- Pomija etapy N/A (oba pola dat puste: `template_start IS NULL AND template_end IS NULL`)
- Pomija etapy milestone (`_OPTIMIZER_MILESTONE_STAGES`)
- Zwraca: `{can_optimize, issues, stages_missing_staff, stages_missing_dates}`

**Warunek z rm_optimizer.py (linia ~243):** projekt kwalifikuje się gdy choć jeden nie-milestone etap ma pracownika w `stage_staff_assignments`. Bez tego → ERROR z komunikatem o brakujących pracownikach.

**UI w selektorze projektów:**
- Kolumna "Opt." z ikonami `⚡` (żółty=niezbadany) / `⊘` (szary=nieaktywny)
- Kliknięcie `⚡` → sprawdza WSZYSTKIE projekty w wątku tła → ikony zmieniają kolor: zielony=gotowy, czerwony=braki
- Popup dla klikniętego projektu pokazuje szczegóły braków
- `_opt_icon_widgets: dict` — referencje do ikon

**Zmiany UI (commit 691bf62, maj 2026):**
- `_check_all_and_update(clicked_pid=None)` — `clicked_pid` teraz opcjonalny
- Dodano flagę `_check_running[0]` — guard przed startem wielu równoległych wątków
- Hover na ikonę ⚡ wywołuje `_check_all_and_update()` bez `clicked_pid` → odświeża kolory w tle BEZ popupu
- Popup otwierany tylko gdy `clicked_pid is not None` (kliknięcie)
- Powiązane z: [[project-linia-feature]]

**Dlaczego nie cache w bazie:** pliki projektów są na SMB — otwarcie każdego pliku kosztuje 5-20ms. Cache wymagałby hooków w 5 miejscach zapisu staff. Wybrano check na żądanie (jeden projekt = jedno otwarcie SMB).

**How to apply:** przy pytaniach o optymalizator — warunek normalnego trybu to STAFF w stage_staff_assignments dla nie-milestone etapów z datami.
