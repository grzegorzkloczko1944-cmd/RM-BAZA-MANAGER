---
name: feedback_restart_po_edycji
description: Po każdej edycji kodu RM_BAZA sam ją restartuję (instancja z Pythona) — łagodnie, bez /F; przy locku decyduje user w oknie „Masz lock!"
metadata:
  type: feedback
---

**Po każdej edycji kodu RM_BAZA sam ją restartuję, nie czekam na „odpalaj".**
Polecenie usera 05.10.2026: „po każdej edycji odpalaj". To stała zgoda,
wyjątek od [[feedback_nie_zamykaj_okien_usera]], ale tylko w tym zakresie.

**Why:** user po każdej zmianie i tak pisał „odpalaj", a wcześniej sam
zamykał okno. Chce widzieć efekt od razu.

**How to apply:**
- Dotyczy tylko instancji deweloperskiej z Pythona
  (`pythonw RM_BAZA_v15_MAG_STATS_ORG.py`). Nigdy `.exe`, RM_MANAGER ani
  Subiekt: tam dalej obowiązuje pytanie przed zamknięciem.
- Najpierw `py_compile` i testy. Restart dopiero, gdy kod jest gotowy, a nie
  przy każdym pośrednim Edit.
- Zamykam ŁAGODNIE: `taskkill //PID <pid>` **bez `/F`** (WM_CLOSE →
  `on_closing`). Bez locka okno zamyka się od razu. Z lockiem pokazuje
  „⚠️ Masz lock!" i czeka na usera: wtedy NIE dobijam procesu, tylko mówię,
  że czeka okno, i odpalam po zamknięciu.
- Po starcie podaję PID nowej instancji.
