---
name: project_serwis_block
description: Blok "Serwis" — grafik serwisantów (linie A z RM_MANAGER + B wyjazdy), przycisk obok Kadry
metadata:
  type: project
---

Blok **🔧 Serwis** — nowe okno-grafik serwisantów, wzorowane na Kalendarzu zespołu z Kadr.

**Przycisk:** na `top_frame2` (drugi wiersz belki) **zaraz po "🏖 Kadry"** (rm_manager_gui.py ~3270), styl jak inne przyciski top_frame2, wywołuje `service_schedule_dialog`. Zob. [[project_topbar_two_rows]].

**Struktura okna = ttk.Notebook (jak Kadry):** `service_schedule_dialog` tworzy Toplevel + Notebook z zakładkami: „📆 Grafik serwisów" (`_service_build_chart_tab(parent, dlg)` — zwraca _reload_lineB) i „✈ Wyjazdy" (`_service_build_trips_tab` — Treeview CRUD, zwraca _reload). `<<NotebookTabChanged>>` odświeża aktywną. Silnik grafiku bierze `parent` (zakładka), `dlg` tylko dla okien potomnych. Wiersz-nagłówek pracownika = `kind='H'` (ciemny pasek, samo nazwisko) — osobny wiersz nad A/B, żeby nazwisko nie nachodziło na nazwy projektów.

**Okno czasowe linii A** (kluczowe — inaczej serwisant z wieloma projektami w roku = dziesiątki wierszy): pola „wstecz N dni / w przód M dni" w stagebar (domyślnie 7/30) + checkbox „pokaż wszystkie". Wiersz A dla projektu powstaje tylko gdy projekt ma etap serwisowy przecinający okno [dziś−wstecz, dziś+wprzód] (`_entry_in_window` w `_rebuild_rows`). Filtr działa na danych z cache → zmiana okna = tylko `_redraw` (tanie, bez ponownego forecastu). Malowanie i tak rysuje wszystkie etapy projektu; okno steruje tylko ISTNIENIEM wiersza.

**Karta serwisanta** (`_service_person_card`, wzorowana na `_employee_card` z Kadr) — klik nazwiska/etykiety w lewym panelu grafiku (`names_cv.bind('<Button-1>')`). Notebook: „✈ Wyjazdy" (`_service_card_trips_tab` — CRUD filtrowany po pracowniku), „📆 Aktualne etapy" (`_service_card_stages_tab` — linia A read-only, przelicza `_collect_service_stages`), „📜 Historia" (`_service_card_history_tab` — wyjazdy ZREALIZOWANE lub date_to < dziś). on_change → odświeża grafik pod spodem.

**Układ wierszy (per serwisant, kategoria pracownika `Serwis`):**
- Linia **A** = etapy/milestone z projektów RM_MANAGER, **rozbita: 1 wiersz = 1 projekt** (3 projekty → 3 wiersze A), zawsze, niezależnie od nakładania w czasie. Read-only.
- Linia **B** = 1 wiersz na serwisanta — własne wyjazdy z nowej tabeli `service_trips`. Edytowalne.
- Wysokość bloku pracownika ZMIENNA = (liczba projektów) + 1. To główna różnica vs kalendarz zespołu (tam wiersz = 1 pracownik).

**Linia A — dane:** dla każdego projektu `recalculate_forecast(rm_db, pid)` (SERCE SYSTEMU, rm_manager.py:4364) → daty etapów. Kto: `get_stage_assigned_staff` (rm_manager.py:6608) + `get_stage_employee_id` dla SAT (6379). Filtr kategorii `Serwis`. Daty: **prognoza pełnym kolorem + szablon obrysem/cieniem**. Etapy **wybieralne** (checkboxy w belce: SAT/URUCHOMIENIE_U_KLIENTA, ODBIORY, FAT, ODBIOR_1/2/3, URUCHOMIENIE, POPRAWKI). Milestone vs etap: STAGE_DEFINITIONS rm_manager.py:138 (is_milestone flag).
**Wydajność:** recalculate_forecast liczy cały graf — ~58 projektów. Cache przy otwarciu + przycisk "🔄 Przelicz", NIE liczyć przy scrollu.

**Linia B — tabela `service_trips`** (w rm_master): employee_id, project_id (NULL), client_or_place, trip_type (gwarancja/przegląd/awaria/szkolenie — własny słownik+kolory), date_from, date_to, status (PLANOWANY/POTWIERDZONY/ZREALIZOWANY), note, created_by, created_at. CRUD + `ensure_service_trips_table`.

**Kolizja (czerwony):** tylko **wyjazd B ∩ milestone A** per serwisant (dni wpisów B pokrywające się z dniami milestone'ów SAT/FAT/ODBIOR_1-3/URUCHOMIENIE_U_KLIENTA). Nakładanie 2 projektów A lub zwykłych etapów ≠ kolizja.

**Silnik:** refaktor rdzenia z `_vacation_build_team_calendar_tab` (rm_manager_gui.py:31752) — oś ciągła, zamrożone nazwiska, sync scroll X/Y, PDF. Rysowanie figurami na Canvas.

**Kolejność:** 1) tabela+CRUD backend, 2) collect_service_stages+cache, 3) okno+silnik (sama linia A), 4) linia B+dialog, 5) filtry+kolizje+szablon-obrys+PDF.

Powiązane: [[project_kadry_module]], [[project_urlopy_block]], [[project_linia_feature]].
