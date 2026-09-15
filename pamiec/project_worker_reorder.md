---
name: project-worker-reorder
description: Kolejność pracowników w dialogach przypisywania — przyciski Wyżej/Niżej (2026-06-09/10)
metadata: 
  node_type: memory
  type: project
  originSessionId: 5712b7b0-8659-4968-bd99-810f907e9f8e
---

Dodane przyciski ⬆️ Wyżej / ⬇️ Niżej do zmiany kolejności pracowników w dwóch oknach:

**1. `assign_staff_dialog(stage_code)`** — okno "Pracownicy" na Osi czasu (dla każdego etapu)
- Wzorzec: immediate-save — delete-all + re-insert w DB
- Helper: `_get_assigned_staff_ordered()` + `_reorder_staff_in_db(new_order_eids)`
- Po reorderze: `refresh_assigned()` + `self.refresh_timeline()`

**2. `_open_worker_editor(pid, sc)`** w `_open_stage_copy_dialog`** — edytor pracowników przy kopiowaniu projektu
- Wzorzec: deferred-save — operuje na in-memory liście `assigned_eids`, zapis przy "Zapisz"

**Why:** Pierwszy pracownik na liście = "Master". Bez reorderu żeby zmienić mastera trzeba było zdjąć i z powrotem dodać.

**How to apply:** Przy pracy przy obu oknach — logika master = top of list jest ugruntowana i nie powinna być zmieniana bez świadomości tej konwencji.

Commit: `be33b77` — 2026-06-10
