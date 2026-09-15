---
name: project_stage_start_status_bug
description: "Bug \"projekt nie chce ruszyć po utworzeniu\" — milestone PRZYJETY ustawiony ale project_status utknął w NEW; naprawa retry + samonaprawa"
metadata: 
  node_type: memory
  type: project
  originSessionId: 82f2a873-9dc2-427e-b90e-cba22eee7c22
---

**Objaw:** pracownicy po utworzeniu projektu nie mogą wystartować etapów — "trzeba poklikać i za którymś razem rusza".

**Przyczyna (2026-07-15):** state machine wymaga project_status != NEW żeby startować etapy (can_start_stage / start_stage w rm_manager.py). Przejście NEW→ACCEPTED dzieje się w `set_milestone('PRZYJETY')` w KROKU PO commicie transakcji milestone i było owinięte w try/except który CICHO połykał błąd. master.sqlite (`Y:\RM_BAZA\master.sqlite`) jest współdzielony po SMB i bywa zablokowany → `set_project_status` rzucał "database is locked" → milestone zapisany, ale project_status zostawał NEW → etapy zablokowane.

Uwaga: w tabeli projects są DWIE kolumny statusu — `status` (tekst PL, np. 'Przyjęty', ustawiana przez project_manager.create_project) i `project_status` (enum NEW/ACCEPTED/IN_PROGRESS/PAUSED/DONE, steruje logiką). Rozjeżdżają się. get_project_status czyta `project_status`, NULL→NEW.

**Naprawa:**
1. `set_project_status` (rm_manager.py ~3518) — retry 5x z backoffem na locked/busy, na końcu raise zamiast cichego return. print owinięty w try (stdout cp1250/None w trybie windowed PyInstaller rzuca UnicodeEncodeError na emoji — realne ryzyko cichych awarii w całym rm_manager.py).
2. GUI `_get_ui_button_states` (rm_manager_gui.py ~6348) — dodana ODWROTNA samonaprawa: milestone PRZYJETY ustawiony ale status=NEW → ustaw ACCEPTED. Leczy zabłąkane projekty przy wejściu.
3. Ręcznie naprawione zabłąkane projekty: 52, 56 → ACCEPTED.

Powiązane: [[project_ai_optimizer_stages_paths]], [[reference_db_paths]].
