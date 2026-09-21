---
name: project-import-urlopow-xlsx-todo
description: "TODO - import urlopow z XLSX ksiegowej do RM_MANAGER (employee_availability), wzorowany na mechanizmie cen KSeF w RM_BAZA"
metadata: 
  node_type: memory
  type: project
  originSessionId: 31977024-b194-431d-b12d-c2e945cd8ebf
  modified: 2026-09-01T21:40:44.315Z
---

Do zrobienia: mechanizm importu urlopow pracownikow z pliku XLSX od ksiegowej do tabeli `employee_availability` w RM_MANAGER.

**Status: zablokowane — czekamy na przykladowy plik XLSX od ksiegowej.** Wracamy do tematu, jak uzytkownik go dostarczy.

**Kontekst / dlaczego teraz brak:**
AI Asystent w RM_MANAGER (`rm_ai_optimizer.py`) ma zamkniety zestaw narzedzi tool-calling — `get_absences` tylko czyta z `employee_availability`, zapis ograniczony do `propose_changes`/`commit_changes` z enumem `["assign_worker", "remove_worker", "set_stage_dates"]`. Brak jakiegokolwiek importu XLSX w AI asystencie i brak akcji typu `add_absence`. Logika liczenia dni roboczych juz istnieje: `compute_absence_days()` w `rm_manager.py`, uwzglednia `company_calendar` (pomija weekendy/swieta) i kolumne `days_override` — patrz [[project_urlopy_dni_robocze]].

**Wzorzec do naśladowania — juz dziala w RM_BAZA:**
Import cen z faktur KSeF (`RM_BAZA_v15_MAG_STATS_ORG.py`, funkcja `menu_import_ceny_ksef()` ~linia 15066) to sprawdzony wzorzec: automatyczne dopasowanie pozycji (po kodzie/nazwie) → okno podgladu Treeview z checkboxami → dopiero po recznym zatwierdzeniu `UPDATE` do bazy + log zmiany + backup przed zapisem. Patrz [[project_parser_rm_baza]].

**Plan (do doprecyzowania po otrzymaniu XLSX):**
- Rozpoznac faktyczny uklad pliku ksiegowej (kolumny: pracownik, data od/do, typ nieobecnosci?) dopiero po otrzymaniu przykladu — nie zgadywac struktury z gory.
- Zbudowac import: parsowanie XLSX (openpyxl/pandas) → dopasowanie pracownika po imieniu/nazwisku do tabeli osob → wywolanie `compute_absence_days()` → okno podgladu z zatwierdzeniem → zapis do `employee_availability`.
- Rozwazona (ale NIE ustalona jako decyzja) koncepcja bardziej generycznego mechanizmu: jeden tool `import_spreadsheet(file_path, target_hint)` zamiast punktowej funkcji za kazdym razem, z mapowaniem kolumna→pole trzymanym jako config a nie nowy kod. To pomysl do przemyslenia przy realizacji, nie zatwierdzony zakres.
- Dopiac jako nowy tool w liscie narzedzi AI asystenta (`rm_ai_optimizer.py`) + obsluga uploadu pliku w `rm_manager_gui.py`.
