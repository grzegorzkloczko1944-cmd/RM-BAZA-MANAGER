---
name: project_ai_optimizer_stages_paths
description: "AI Optimizer — gdzie leżą project_stages, dwie bazy master, i bug z niekompletnymi bazami projektów 62/64"
metadata: 
  node_type: memory
  type: project
  originSessionId: 82f2a873-9dc2-427e-b90e-cba22eee7c22
---

AI Asystent harmonogramu (rm_ai_optimizer.py) korzysta z **dwóch** baz master:
- `master_db_path` = `Y:\RM_BAZA\master.sqlite` — projekty (tabela `projects`, klucz `project_id`)
- `rm_master_db_path` = `Y:\RM_MANAGER\rm_manager.sqlite` — pracownicy

Etapy (`project_stages` i cała rodzina `stage_*`) NIE są w żadnym master. Leżą w bazach **per-projekt**:
`Y:\RM_MANAGER\RM_MANAGER_projects\rm_manager_project_{pid}.sqlite` (znajdowane przez `_project_db`, kandydat `base/"RM_MANAGER_projects"/fname`).
Uwaga: `Y:\RM_BAZA\projects\project_{pid}.sqlite` to INNE bazy (RM_BAZA/MAG) — NIE mają tabel stage.

**Bug naprawiony (2026-07-15):** `get_project_stages()` łapało `OperationalError` tylko przy zapytaniach o pracowników/okresy, nie przy głównym zapytaniu o etapy. Gdy baza projektu istniała ale była niekompletna, wyjątek `no such table: project_stages` wysadzał całe `get_delays()`. Model AI zmyślał wtedy komunikat o braku tabeli w master.sqlite. Fix: główne zapytanie owinięte w try/except → niekompletna baza jest pomijana.

**Do zrobienia:** bazy projektów **62** i **64** są uszkodzone/puste (istnieją, brak `project_stages`). Zregenerować albo usunąć z aktywnych, jeśli porzucone. Powiązane: [[reference_db_paths]], [[project_optimizer_readiness]].
