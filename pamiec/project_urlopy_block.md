---
name: project_urlopy_block
description: Blok URLOPY — okno rozliczania nieobecności (urlop/L4/godzinowe) + pula roczna; zastąpił zakładkę Niedostępność w optymalizatorze
metadata: 
  node_type: memory
  type: project
  originSessionId: 82f2a873-9dc2-427e-b90e-cba22eee7c22
---

Blok **URLOPY** (2026-07-15) — pełne rozliczanie nieobecności pracowników. Przycisk "🏖 Urlopy" na głównym pasku (rm_manager_gui.py, przed Optymalizatorem) → `vacation_dialog()`.

**Okno, 3 zakładki:**
- Nieobecności — CRUD (`_vacation_build_absences_tab`). Daty Od–Do + opcjonalne godziny time_from/time_to (HH:MM, puste=cały dzień; godziny tylko dla wpisu jednodniowego Od=Do). reason zapisywany WIELKIMI literami (CHECK w schemacie: URLOP/L4/DELEGACJA/SZKOLENIE/INNE — wcześniej GUI zapisywało małe, niezgodne z CHECK).
- Pula urlopu — dwuklik edytuje roczną pulę dni per pracownik (`_vacation_build_quota_tab`).
- Rozliczenie — suma dni wg typu, urlop wykorzystany/pozostały (czerwone gdy <0), eksport CSV (`_vacation_build_report_tab`).

**Backend (rm_manager.py):**
- Migracja w `ensure_rm_master_tables`: ALTER employee_availability ADD time_from/time_to; nowa tabela `employee_vacation_quota(employee_id, year, days, ...)` PK(employee_id,year), domyślnie 26.
- Funkcje: get/set_vacation_quota, get_vacation_report(year), _count_absence_days (godzinowe: 8h=1 dzień roboczy, ułamek). DEFAULT_VACATION_DAYS=26.
- save_employee_availability rozszerzony o time_from/time_to. get_* używa SELECT ea.* → godziny automatycznie.

**Przełom roku (2027+):**
- get_vacation_quota: gdy brak wpisu na dany rok, DZIEDZICZY z najbliższego wcześniejszego roku z ustawioną pulą (indywidualne pule przenoszą się automatycznie); brak jakiegokolwiek → 26.
- Zaległy urlop: get_vacation_report liczy carryover = max(0, pula_poprz_roku − urlop_wykorzystany_poprz_roku). available = carryover + quota. remaining = available − used_urlop. Kolumny w Rozliczeniu: Zaległy, Pula, Dostępne, Urlop, Pozostało. _used_urlop_in_year() pomocnicza.

**Historia pracownika:** `_vacation_show_employee_history` — dwuklik na wierszu Rozliczenia (poza kolumną Zaległy) lub przycisk "📖 Historia pracownika". Okno: wszystkie nieobecności (wszystkie lata), podsumowanie sum dni wg typu, tabela Od/Do/Godziny/Dni/Powód/Uwagi. MA własny toolbar Dodaj/Edytuj/Usuń — używa wspólnego `_vacation_edit_absence(parent, avid, on_saved, preset_employee_id)` (wydzielony edytor, ta sama metoda co zakładka Nieobecności).

**Zaległy edytowalny (ręczne urealnienie):** dwuklik kolumny 'Zaległy' (#3) w Rozliczeniu → simpledialog. Backend: OSOBNA tabela `employee_carryover_override(employee_id, year, days)`. get/set_carryover_override. get_vacation_report: override ma pierwszeństwo nad auto-wyliczeniem. Puste = wyczyść (DELETE) = powrót do auto.

**DWIE PULE (2026-07-15 wieczór):**
- Pula bazowa (permanentna) — tabela `employee_vacation_base(employee_id, days)`, edytowalna, domyślnie 26. get/set_vacation_base.
- Pula roczna (korekta) — `employee_vacation_quota(employee_id, year, days)`, nadpisuje bazową TYLKO dla danego roku. set_vacation_quota / clear_vacation_quota / has_vacation_quota_for_year.
- get_vacation_quota: priorytet korekta roczna → bazowa → 26. USUNIĘTO stare dziedziczenie "z poprzedniego roku" — teraz źródłem prawdy jest baza permanentna.
- WAŻNE: override zaległego przeniesiony do osobnej tabeli (employee_carryover_override), bo wcześniej był kolumną w quota i mieszał się z wykrywaniem "czy jest korekta roczna". Stara kolumna carryover_override w quota pozostała (nieużywana, nieszkodliwa).
- GUI zakładka Pula: 2 kolumny "Pula bazowa" (dwuklik #4) + "Pula {rok}" (dwuklik #5). Rok dziedziczony pokazuje "N (bazowa)" szarym. Puste w edycji rocznej = clear = powrót do bazowej.

**Centrowanie:** wszystkie okna URLOPY (vacation_dialog, historia, edytor) używają self._center_window(win,w,h) zamiast geometry() — otwierają się na środku okna aplikacji (multi-monitor OK).

**Optymalizator:** zakładka Niedostępność USUNIĘTA z optimizer_dialog. Optymalizator DALEJ czyta employee_availability (get_scheduling_data → _add_availability_constraints w rm_optimizer.py). Solver pracuje NA DNIACH (date_to_index) — godziny nie zmieniają rozdzielczości, służą tylko rozliczeniu.

**PyInstaller:** brak nowych zależności (csv/matplotlib już były). Wymaga rekompilacji .exe.

Powiązane: [[reference_db_paths]], [[project_worker_reorder]], [[project_optimizer_readiness]].
