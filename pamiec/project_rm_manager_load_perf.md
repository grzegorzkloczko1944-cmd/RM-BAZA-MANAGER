---
name: project_rm_manager_load_perf
description: "Zacinka przy wczytywaniu projektu w RM_MANAGER = latencja Y: × ~34 otwarć połączenia; optymalizacje"
metadata: 
  node_type: memory
  type: project
  originSessionId: c95eb76c-a81f-4f5f-8efa-c2351dab0df1
---

Objaw: RM_MANAGER "długo loguje / niedostępne etapy" przy wyborze projektu (zgłoszone dla 2639 = project_id 68). Bazy zdrowe (integrity ok) — problem to WYDAJNOŚĆ, nie dane.

**Przyczyna:** `on_project_selected` ([rm_manager_gui.py](rm_manager_gui.py)) odpala sekwencyjnie ~10 metod (ensure_project_initialized → load_project_stages → refresh_timeline → refresh_dashboard → refresh_history → create_embedded_gantt_chart → check_alarms → load_backup_dates). Łącznie **~34 otwarcia połączenia** do baz na dysku sieciowym **Y:**, gdzie otwarcie `master.sqlite` = śr. 391 ms, max **3,8 s**. Zmierzone realnie.

**Kluczowe fakty:**
- Config aplikacji: `C:\RMPAK_CLIENT\manager_sync_config.json` (NIE w repo). Wszystko wskazuje na Y:/RM_MANAGER i Y:/RM_BAZA.
- Etapy projektu leżą w `Y:/RM_MANAGER/RM_MANAGER_projects/rm_manager_project_<id>.sqlite` (osobna baza per projekt, ~17 wierszy project_stages). To NIE ta sama baza co Y:/RM_BAZA/projects/project_<id>.sqlite (tam Machines/BOM/items). Patrz [[project_ai_optimizer_stages_paths]] i [[reference_db_paths]].
- `_open_rm_connection` (rm_manager.py) robiło 6 osobnych PRAGMA + weryfikację journal_mode = 7 round-tripów SMB na KAŻDE otwarcie.

**Zrobione optymalizacje (2026-08-04, na main, jeszcze nie pushnięte — patrz [[feedback_git_push]]):**
1. `_open_rm_connection`: 6 PRAGMA scalone w jeden `executescript()`; weryfikacja journal_mode raz na plik/proces (`_JOURNAL_MODE_VERIFIED`). WAL-guard zachowany (WAL na SMB = korupcja, journal_mode MUSI=DELETE).
2. Migracje etapów `ensure_all_stages_for_all_projects`/`fix_stage_sequence_for_all_projects`/`ensure_default_dependencies_for_project` w `ensure_project_initialized` odpalane RAZ na projekt na sesję (guard `self._stages_migrated_this_session`), nie przy każdym kliknięciu. Ręczne wywołania z menu serwisowego nietknięte.
3. `load_project_stages`: −3 otwarcia — nowa `get_milestones_bulk(con, pid, codes)` czyta PRZYJETY/ZAKONCZONY jednym SELECT na współdzielonym `con`; con_completed scalony do tego samego połączenia.

**Nietknięte świadomie:** `refresh_dashboard` — redundancje słabe (get_project_status_summary/calculate_critical_path to ciężkie funkcje analityczne na różnych bazach; zysk ~1 otwarcie vs ryzyko). Dalszy potencjał: refaktor pomocników rm_manager.py na przyjmowanie `con=` (get_active_stages, is_project_paused) — większy, odłożony.

Build: `python -m PyInstaller --noconfirm --clean RM_MANAGER.spec` (log → build_rmmanager.log). Uwaga na emoji w print + cp1250 przy testach z konsoli — [[project_cp1250_emoji_print]].

**RM_BAZA — audyt tego samego problemu (2026-08-04):** RM_BAZA ma INNĄ architekturę — trzyma długożyjące połączenia `self.db_manager.master_con` / `self.project_con` (PRAGMA raz, reużycie), więc WCZYTYWANIE projektu jest już zdrowe (`on_project_selected` @ ~5205 = 1 nowe połączenie). Zrobione: (1) `_open_baza_connection` (database_manager.py ~1271) — bliźniak `_open_rm_connection`, ten sam fix: scalone PRAGMA w executescript() + weryfikacja raz na plik (`_BAZA_JOURNAL_VERIFIED`, klucz = ścieżka bez ?query URI; działa dla rw/ro/immutable — przetestowane). (2) DEBOUNCE 300 ms w wyszukiwarce nazw (`on_name_typing` → `_run_name_suggestions` @ ~8218 w RM_BAZA_v15_MAG_STATS_ORG.py) — `search_name_suggestions` otwierało połączenie do KAŻDEJ bazy projektu na Y: przy KAŻDYM wciśniętym znaku (bind `<KeyRelease>`→on_name_changed→on_name_typing, brak debounce). Świadomie NIE ruszane (user, Recommended): pętle skanujące per-plik w search_on_drawing_number (@7732), search_by_partial_name (@8163/18432), menu_delete_supplier (@19230) — nadal 1 połączenie/projekt/skan, ale rusza raz nie co znak. Build RM_BAZA: `RM_BAZA_v15_MAG.spec` (produkcyjny, ma datas z database_manager.py itd.), wyjście dist/RM_BAZA_v15_MAG.exe; log → build_rmbaza.log. Drugi spec RM_BAZA_v15_MAG_STATS_ORG.spec buduje z tego samego .py inną nazwę — NIE produkcyjny.

**Auto-otwarcie folderu po buildzie:** oba produkcyjne .spec (RM_MANAGER.spec, RM_BAZA_v15_MAG.spec) mają na końcu (po `exe = EXE(...)`) dopisek `os.startfile(os.path.join(os.path.abspath(DISTPATH),''))` w try/except. `.spec` wykonuje się jako Python, EXE() buduje plik w momencie konstrukcji, więc kod po nim = po buildzie. DISTPATH to globalna PyInstallera (potwierdzone realnym buildem 2026-08-04). Explorer otwiera się sam po każdym `pyinstaller *.spec`.
