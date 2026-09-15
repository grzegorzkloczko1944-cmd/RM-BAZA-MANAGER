---
name: project_stats_views_from_rmstats
description: "Okna Podsumowanie i Status projektów w RM_MANAGER — port modułów z RM_STATS, wspólny kod dla łatwej migracji"
metadata: 
  node_type: memory
  type: project
  originSessionId: 82f2a873-9dc2-427e-b90e-cba22eee7c22
---

Dwa okna statystyk w RM_MANAGER (2026-07-19), przycisk "📊 Podsumowanie" i "📋 Status" na głównej belce (przed Optymalizatorem):
- `stats_summary_dialog` — kolumny: ID, Projekt, Status (OPOZNIONY/ZAGROZONY/ZGODNIE Z PLANEM/ZAKONCZONY, kolorowane + znaczniki ⏸/⚠️/📦⚠️), Odchylenie, Przew. zakończenie, Aktywne etapy, Etapy bez rezerwy (CPM n/total), Płatności, Kompletacja (BOM). KLIKALNE KARTY filtra statusów (Wszystkie + Opóźnione/Zagrożone/Zgodne z planem/Zakończone wg status_code) jak w Statusie — filtr na status_code, klik ponownie wyłącza. Okno 1180x830.
- `stats_status_dialog` — KLIKALNE KARTY statystyk u góry (jak RM_STATS): 3 główne (Aktywne=in_progress_count, Na czas=on_time_count, Opóźnione=delayed_count) + karta per status z by_status. Klik karty filtruje listę (filtry: ACTIVE=nie Zakonczony/Wstrzymany, ON_TIME, DELAYED, albo nazwa statusu); klik ponownie = wyłącz. Poniżej lista: ID, Projekt, Status, Priorytet, Opóźnione etapy (chipy ETAP +Nd, opóźnione na czerwono).

**Karty:** równy grid 6 kolumn (uniform width 150px, holder z pack_propagate False), podświetlenie aktywnego filtra (_highlight_cards), hover. Fullscreen: `_add_fullscreen(win, toolbar)` — przycisk "⛶ Pełny ekran" + F11 toggle + Esc wyjście, w obu oknach statystyk.

**Kolumna Kompletacja (widok Status):** received_percent z master.sqlite (kolumna projects.received_percent, tekst typu "94% (510)"). Dociągana w GUI przez _db.list_projects() (mapa pid→received_percent w state['completion']).

**Trzecia warstwa sygnałów (2026-07-19, port z RM_STATS):** oba widoki pokazują sygnały niezależne od CPM:
- ⚠️ needs_attention = status Poprawki
- 📦⚠️ overdue_milestones = przeterminowane milestone'y odbiorowe (FAT/ODBIOR_1-3/URUCHOMIENIE_U_KLIENTA po terminie, niezamknięte). DONE→0.
- ⏸ is_paused
stats_status.build_status_overview: needs_attention w wierszu, overdue_milestone_projects osobna sekcja. Opóźnienia liczone z CPM (overall_variance_days>5), nie z surowej listy etapów. STATUS_ORDER z polskimi znakami + _ascii_fold (dwustronna normalizacja Przyjęty/PRZYJETY). PRZYJETY/TRANSPORT wykluczone z opóźnień.
stats_project_summary.build_project_summary: dodane needs_attention + overdue_milestones_count (lokalny _overdue_milestones_count z inputs, bez cyklicznego importu) + bom_completion_pct/total (db.completion_percent). GUI Podsumowanie: znaczniki w kolumnie Status (⏸/⚠️/📦⚠️) + kolumna "Kompletacja" (📦 NN% (M)).

**db.py completion_percent(pid):** liczy kompletację BOM z tabeli items w bazie Machines (project_<id>.sqlite w RM_BAZA/projects). Wymaga projects_path w konstruktorze RMStatsDB (GUI przekazuje self.projects_path). mag_db_path(pid) = projects_path/project_<id>.sqlite. Wzór: odebrane/(wszystkie−ZZ), ZZ=numer rysunku kończy się na ZZ.

**Sekcja Przeterminowane odbiory (widok Status):** osobne drzewo pod główną listą (overdue_wrap, pakowane before=main_wrap tylko gdy data['overdue_milestone_projects'] niepuste). Kolumny ID/Projekt/Status/Przeterminowane. Główna lista owinięta w main_wrap (pack in_=).
**BUG filtra ACTIVE naprawiony:** _FINAL musi mieć POLSKIE znaki {'Zakończony','Wstrzymany'} — wcześniej {'Zakonczony',...} bez ogonków nie pasowało do statusu z bazy, więc ACTIVE pokazywał wszystkie 58 zamiast 29.
**Tooltip znaczników:** `_attach_marker_tooltip(tree, 'status')` — motion tooltip po najechaniu na kolumnę Status, opisuje ⏸/⚠️/📦⚠️. Podpięty do 3 drzew (Status główne, odbiory, Podsumowanie). ⚠️ wykrywane przez text.replace('📦⚠️','').find('⚠️') żeby nie mylić z 📦⚠️.
**Ciemniejsze czcionki Podsumowania:** tagi statusu przyciemnione (DELAYED #a01e1e, AT_RISK #b8600f, ON_TRACK #1e6b3a, DONE #4a4a4a) + styl 'Summary.Treeview' foreground #1a1a1a.

**Single-instance (blokada wielu okien):** `_single_window(key)` / `_register_window(key, win)` w GUI. Trzyma self._open_windows dict; jeśli okno danego typu żyje → deiconify+lift+focus i return (nie tworzy drugiego). Sprząta wpis na <Destroy>. Użyte w: stats_summary ('stats_summary'), stats_status ('stats_status'), vacation ('vacation'). Można dodać do innych okien.

**Architektura — celowa łatwa migracja z/do RM_STATS (C:\RMPAK_CLIENT\Repozytoria\NOW\RM_STATS):**
- `stats_status.py` i `stats_project_summary.py` SKOPIOWANE VERBATIM z RM_STATS (importują `from db import RMStatsDB`). NIE modyfikować logiki lokalnie — poprawki migruj kopiując plik między projektami.
- `db.py` — adapter RMStatsDB dla RM_MANAGER: te same metody co db.py z RM_STATS (list_projects, project_stage_status, project_forecast_inputs, payment_milestones), ale ścieżki z configu RM_MANAGERa (przekazane w konstruktorze), nie z config.json. To JEDYNA różnica między projektami. Read-only (mode=ro). Zawiera tylko metody potrzebne tym 2 widokom — dołóż resztę przy przenoszeniu kolejnych.
- GUI `_stats_db()` tworzy RMStatsDB(master_db_path, rm_master_db_path, rm_projects_dir).

Progi statusu: odchylenie >10d OPOZNIONY, >5d ZAGROZONY, reszta ZGODNIE Z PLANEM; project_status DONE → ZAKONCZONY. Odchylenie = max(forecast_end) − max(template_end) całego projektu (NIE suma czasów trwania — patrz commit 8593fc8).

**PyInstaller:** db.py, stats_status.py, stats_project_summary.py dodane do datas ORAZ hiddenimports w RM_MANAGER.spec (importowane dynamicznie przez `import` w metodach → PyInstaller sam nie wykryje).

Weryfikacja: oba okna 58 wierszy na żywych bazach; wynik zgodny ze screenem RM_STATS (2618 +22d, 2520 −87d itd.). Powiązane: [[project_ai_optimizer_stages_paths]], [[reference_db_paths]].
