---
name: project_plan_automatyka
description: "Dział automatyki w RM_BAZA — NIE klonować MACHINES; brakuje tylko kartotek w Subiekcie; czeka na eksport ze schematów (PLAN_AUTOMATYKA.md)"
metadata:
  type: project
---

**Rozpoznanie 15.09.2026, nic nie zaimplementowane.** Pełny dokument:
[`PLAN_AUTOMATYKA.md`](../PLAN_AUTOMATYKA.md) w korzeniu repo.

**Pytanie użytkownika:** czy przekopiować MACHINES i zrobić z nieużywanego
`WAREHOUSE` drugi tryb dla automatyki?

**Odpowiedź: nie.** `WAREHOUSE` to nie moduł, tylko **99 rozsianych warunków**
`if project_type == "WAREHOUSE"` (80 w samym `RM_BAZA_v15_MAG_STATS_ORG.py`).
Nie ma czego kopiować — cała różnica to katalog baz w `database_manager.py`.
Klon = dwa zestawy tego samego kodu i każda poprawka robiona dwa razy
([[project_ai_agents_two_places]]).

**Stan WAREHOUSE:** 87 projektów w bazie = 81 MACHINE + **6 WAREHOUSE bez
nazw** (numery 10–16, status PROJEKT). Martwe. Do usunięcia kiedyś, ale to
osobna sprawa.

**Czego automatyka naprawdę potrzebuje:** ten sam magazyn, ten sam
magazynier, te same operacje (przyjęcie/wydanie). Czyli **nie osobny tryb**.
Magazyn, `pw`, `rw`, okno magazyniera i progi **już działają** —
brakuje WYŁĄCZNIE kartotek automatyki w Subiekcie.

**Kolejność:** (1) zasiać kartoteki, (2) sprawdzić, czy okno magazyniera
wystarcza, (3) projekty automatyki jako zwykłe MACHINE.

**How to apply:**
- ⛔ **Nie budować przyjęć/wydań po stronie RM_BAZA** — powstałyby dwa źródła
  prawdy o tym samym magazynie. Subiekt zostaje jedynym.
- **Drzewka: nie decydować z góry.** Płaska lista i złożenie to ta sama
  struktura w bazie; grupowanie da się dołożyć później bez przebudowy.
  NIE pytać działu o „drzewka" — spytać, jak prowadzą jeden montaż i czy
  dzielą listę na podzespoły.
- ⚠️ **Czeka na dane wejściowe:** przykładowy eksport z programu do schematów
  (nazwa programu nieustalona — EPLAN/WSCAD/SEE?), przykładowy Excel, rząd
  wielkości. Z samego eksportu wyjdzie odpowiedź o drzewka i o to, czy
  symbole są katalogowe.
- Narzędzia gotowe do zasiewu: tryb mostu `kartoteka`,
  [[project_subiekt_edytor_kartotek]], [[project_dopasowanie_podpowiedzi]].
