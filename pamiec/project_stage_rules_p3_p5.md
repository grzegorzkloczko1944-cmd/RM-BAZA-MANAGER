---
name: project_stage_rules_p3_p5
description: Reguły etapów — P3 (zamknij gotowy projekt 1 klikiem) i P5 (walidacja kolejności dat). P4 odrzucony jako fałszywy.
metadata: 
  node_type: memory
  type: project
  originSessionId: 82f2a873-9dc2-427e-b90e-cba22eee7c22
---

Reguły biznesowe z analizy AI harmonogramu (2026-07-15). Wdrożone TYLKO P3 i P5 — reszta odrzucona po weryfikacji na danych.

**P5 — walidacja kolejności dat (save_dates w rm_manager_gui.py ~12335):**
Po zebraniu saved_iso, przed commitem: sprawdza czy start następnika < koniec poprzednika dla par: URUCHOMIENIE→SAT(URUCHOMIENIE_U_KLIENTA), ODBIORY→FAT, URUCHOMIENIE→TRANSPORT, MONTAZ→URUCHOMIENIE. MIĘKKIE ostrzeżenie (askyesno "zapisać mimo to") — nie twarda blokada, bo daty bywają celowo nietypowe.

**P3 — zamknij gotowy projekt (is_project_ready_to_close w rm_manager.py przed end_stage):**
Zwraca ready=True gdy: brak aktywnych etapów roboczych (is_milestone=0, ended_at NULL) + jest ≥1 zakończony etap roboczy + od ostatniego ended_at minęło ≥ idle_days (domyślnie 14). GUI (finish_frame ~6714): gdy nie DONE i zakonczony_enabled i ready → pokazuje "💡 Gotowy do zamknięcia" + przycisk "✅ Zamknij projekt" → _quick_close_project → toggle_project_done(True). UWAGA: użyj datetime.now().date() NIE date.today() — w rm_manager.py zaimportowane tylko `from datetime import datetime, timedelta`, brak `date`.

**ODRZUCONE reguły (weryfikacja na Y:\RM_MANAGER\RM_MANAGER_projects):**
- P4 "identyczne actual_start==actual_end = import → wyklucz z KPI": FAŁSZ. ~30 projektów ma start==end ale RÓŻNE timestampy (tylko 4 współdzielone przez 2-3 proj). To NORMALNE oznaczanie etapu jako "zrobione teraz" jednym klikiem, nie import. Reguła wyrzuciłaby realne projekty z KPI. Dodatkowo get_delays i tak nie liczy ukończonych etapów, więc problem nieistniejący.
- P2/alerty TRANSPORT/ZAKONCZONY: odłożone (wymaga nowego widoku alertów).
- Diagnoza AI była NIEAKTUALNA: projekty 2553/2614/2617 rzekomo "wiszą skończone" — w rzeczywistości już status=DONE (po wcześniejszych naprawach statusów [[project_stage_start_status_bug]]).

Powiązane: [[project_ai_optimizer_stages_paths]], [[project_urlopy_block]].
