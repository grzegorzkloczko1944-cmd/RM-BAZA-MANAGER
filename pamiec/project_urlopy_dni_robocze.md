---
name: project_urlopy_dni_robocze
description: "Urlopy/nieobecności liczone w DNIACH ROBOCZYCH wg kalendarza firmowego, nie surowych dni kalendarzowych"
metadata: 
  node_type: memory
  type: project
  originSessionId: 383a3826-b965-4168-84c4-7cd465f3f22c
---

Nieobecności pracowników (urlopy, L4 itd.) liczą się jako **dni robocze** wg kalendarza firmowego (`company_calendar`) — pomijają weekendy i święta, uwzględniają soboty pracujące (`SATURDAY_WORK`). NIE surowe dni kalendarzowe Od–Do.

**Kluczowe funkcje (rm_manager.py):**
- `compute_absence_days(db, date_from, date_to, ...)` → `{working_days, skipped[], is_hourly}`; `skipped` to lista pominiętych dni z opisem (dla UI).
- `_count_absence_days(...)` — przyjmuje `rm_master_db_path` (liczy robocze) i `days_override` (ręczne zmniejszenie ma pierwszeństwo). Bez ścieżki bazy → fallback do surowych dni kalendarzowych (stare zachowanie).
- Kolumna `days_override REAL` w `employee_availability`: user może wpisać TYLKO MNIEJ niż wyliczono (np. wrócił wcześniej); NULL = licz automatycznie.

**Why:** wpis „od pon do pon" liczył 8 dni zamiast ~5 roboczych; urlop obejmujący 1 maja liczył święto jako urlop. Rozjazd: Historia pokazywała 10 dni, Rozliczenie 8 — bo liczyły różnymi ścieżkami.

**How to apply:** wszystkie 3 miejsca liczące dni (`_used_urlop_in_year`, `get_vacation_report`, okno Historia w GUI) MUSZĄ przekazywać `rm_master_db_path` + `days_override`. Nie wracać do sumowania surowych dni. Powiązane: [[project_swieta_auto_seed]].
