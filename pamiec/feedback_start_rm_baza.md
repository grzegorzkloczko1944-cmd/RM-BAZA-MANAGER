---
name: feedback-start-rm-baza
description: "Odpal RM_BAZA" = RM_BAZA_v15_MAG_STATS_ORG.py, NIE rm_manager_gui.py
metadata:
  type: feedback
---

Gdy użytkownik mówi „odpal RM_BAZA", chodzi o `RM_BAZA_v15_MAG_STATS_ORG.py`.
`rm_manager_gui.py` to RM_MANAGER — inny program w tym samym repo.

**Why:** Nazwa repozytorium (RM-BAZA-MANAGER) i pliku `rm_manager_gui.py`
mylą; pomyliłem je dwa razy pod rząd (06.09.2026), za drugim razem
użytkownik musiał to prostować.

**How to apply:** `pythonw RM_BAZA_v15_MAG_STATS_ORG.py` z katalogu repo.
Okna Subiekta ([[project_subiekt_stan_05_09_2026]]) — panel, Magazyn,
Zamówienia — otwiera się właśnie z RM_BAZA, więc każda weryfikacja zmian
w `subiekt_*.py` idzie przez ten plik.
