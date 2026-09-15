---
name: project-disk-layout
description: Rozdział kod (repo git) vs dane (katalog roboczy) na dysku C:\RMPAK_CLIENT
metadata: 
  node_type: memory
  type: project
  originSessionId: 32263a47-f8b3-44e1-8aaf-deccc5584315
---

Ustalone 2026-07-06: cała praca nad kodem RM_MANAGER/RM_BAZA jest wyłącznie w repo git
`C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER\`. `C:\RMPAK_CLIENT\RM_MANAGER\` to
katalog **wyłącznie na żywe dane** (baza produkcyjna), NIE zawiera już kodu ani
build'ów - użytkownik potwierdził, że wszelki kod/.exe/backupy kodu w tym katalogu
i obok niego (foldery `RM_MANAGER_*-2026*`) to śmieci ze starych sesji sprzed
przejścia na git, i kazał je usunąć.

**Co zostało posprzątane (usunięte, 682MB+):**
- Wewnątrz `RM_MANAGER/`: wszystkie foldery `backup DD-MM-2026*`, `backups/`,
  `STARY ŚMIEĆ *`, `build/`, `dist/`, `__pycache__/`, zdublowane pliki `.py`
  (np. `rm_manager_gui — kopia.py`), stare `.exe`/`.spec`.
- Obok `RM_MANAGER/`: `RM_MANAGER_07-05-2026_CP-SAT` (402MB), `RM_MANAGER_09-05-2026`
  (275MB), `RM_MANAGER_BACKUP_2026-07-03` (5.5MB).

**Co zostało (żywe dane, NIE usuwać bez pytania):**
- `C:\RMPAK_CLIENT\RM_MANAGER\rm_manager.sqlite` - główna baza
- `C:\RMPAK_CLIENT\RM_MANAGER\RM_MANAGER_projects\` - bazy per-projekt
- `C:\RMPAK_CLIENT\RM_MANAGER\RM_BAZA\` - master.sqlite/projects/chat/locks
  (zgodne z [[reference_db_paths]])

**Reguła na przyszłość:** jeśli w przyszłości znowu pojawi się kod/.py/.exe/build w
`C:\RMPAK_CLIENT\RM_MANAGER\` (poza samymi bazami danych) albo nowy folder
`RM_MANAGER_<data>` obok niego, to prawdopodobnie efekt uboczny jakiejś sesji/builda,
nie celowe działanie - do wyjaśnienia z użytkownikiem, nie zakładać że to trzeba
zachować.
