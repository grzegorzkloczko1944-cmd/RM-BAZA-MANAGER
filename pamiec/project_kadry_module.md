---
name: project_kadry_module
description: Blok Urlopy rozbudowany do modułu kadrowego — workflow wniosków, kalendarz zespołu, typy ustawowe, PDF
metadata:
  type: project
---

Rozbudowa bloku [[project_urlopy_block]] w pełny moduł kadrowy (2026-07-20), na życzenie pracowników ("wypasiony blok jak programy kadrowe"). Model dostępu bez zmian: obsługuje **tylko kadrowa/kierownik** (brak self-service per pracownik) — "wniosek" to wpis ze statusem prowadzony ręcznie.

**Warstwa danych (rm_manager.py):**
- `employee_availability` dostała kolumny `status` (OCZEKUJE/ZATWIERDZONY/ODRZUCONY), `decided_by/at`, `decision_note` (ALTER + except OperationalError). Istniejące wpisy → ZATWIERDZONY.
- Stary `CHECK(reason IN ...)` blokował nowe typy → `_rebuild_availability_without_reason_check()` przebudowuje tabelę bez CHECK (walidacja w kodzie). Kopiuje kolumny dynamicznie z PRAGMA table_info.
- `ABSENCE_TYPES` (lista dictów: code/label/counts_as_vacation/annual_limit) — dodane URLOP_ZADANIE(limit 4), OKOLICZNOSCIOWY, OPIEKA_188(limit 2), BEZPLATNY, MACIERZYNSKI. `used_urlop` w raporcie = suma typów z counts_as_vacation=True.
- Nowe API: `set_absence_status()`, `count_absence_type_days_in_year()`. Raport i `_used_urlop_in_year` pomijają ODRZUCONY.

**GUI (rm_manager_gui.py, okno vacation_dialog):**
- 4 zakładki: Wnioski/Nieobecności (status + Zatwierdź/Odrzuć + filtr + licznik oczekujących), Kalendarz zespołu (grafik miesięczny, kolory wg typu, wykrywanie konfliktów obsady per kategoria), Pula, Rozliczenie (+ eksport PDF zestawienia i Karty urlopowej).
- PDF przez **matplotlib** (już w RM_MANAGER.spec), NIE reportlab (reportlab nie jest w .spec — nie dodawać bez potrzeby, ryzyko .exe). `_vacation_report_to_pdf`, `_vacation_card_to_pdf`.
- Dodano `date` do importu datetime (linia 37); UWAGA: wiele metod ma lokalne `from datetime import ...` — sprawdź czy nie cieniują.

Testy data-layer przeszły (migracja, workflow, limity, raport, idempotencja). Emoji-print/cp1250 dotyczy tylko konsoli testowej — patrz [[project_cp1250_emoji_print]].
