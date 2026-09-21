---
name: project_status_odchylenie
description: "Status/odchylenie projektu liczone wg daty zakończenia (forecast vs plan), NIE sumy odchyleń czasów trwania etapów"
metadata: 
  node_type: memory
  type: project
  originSessionId: 383a3826-b965-4168-84c4-7cd465f3f22c
---

Status projektu (ZGODNIE Z PLANEM / ZAGROŻONY / OPÓŹNIONY) i „Odchylenie (całkowite)" liczą się jako **przewidywany koniec projektu vs. planowany koniec** (data-do-daty), w `get_project_status_summary()` (rm_manager.py).

**Why:** wcześniej sumowano `variance_days` (odchylenia czasów trwania etapów). To maskowało opóźnienia: (1) etap „w toku" ma czas trwania zawsze = planowany → odchylenie 0, nawet gdy tygodnie po terminie; (2) wcześnie zamknięty etap z rezerwą kasował opóźnienie etapu krytycznego. Efekt: projekt tygodnie po terminie pokazywał „🟢 ZGODNIE Z PLANEM".

**How to apply:** aktywny przeterminowany etap przesuwa `forecast_end` co najmniej na dziś (branch B w `_recalculate_forecast_with_con`, ~linia 4359). Nie wracać do `sum(variance_days)` jako metryki statusu. Powiązane liczenie: [[project_urlopy_dni_robocze]].
