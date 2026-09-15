---
name: project_backupy_tylko_przy_starcie
description: "Backupy RM_BAZA i RM_MANAGER robią się TYLKO przy starcie programu — aplikacja chodząca tydzień nie robi ich wcale (świadomie zostawione 14.09.2026)"
metadata:
  type: project
---

Codzienny backup w OBU programach odpala się **wyłącznie raz, przy starcie**:
`self.root.after(3000, self.run_backup_in_background)` (`rm_manager_gui.py:802`)
i `self.after(2000, ...)` (`RM_BAZA_v15_MAG_STATS_ORG.py:3426`). Logika „czy
dziś już był" jest poprawna — brakuje wyłącznie powtórzenia wywołania.

**Skutek:** program chodzący bez restartu nie robi kopii ani razu. Liczby kopii
per dzień (14.09.2026) odzwierciedlają nie ilość pracy, tylko to, kto tego dnia
restartował aplikację:

| dzień | RM_MANAGER | RM_BAZA |
|---|---|---|
| pon. 14.09 | 5 (starty testowe) | 0 |
| sob. 12.09 | 32 | 3 |
| pt. 11.09 | 4 | 26 |
| czw. 10.09 | 40 | 6 |

Drugi mechanizm RM_BAZA — backup przy zwalnianiu locka — jest na produkcji
**WYŁĄCZONY** (`settings` → `backup_on_release = 0`), więc nie łata dziury.

**Why:** ryzyko nie leży w dniach bez pracy (wtedy nie ma czego kopiować —
i to jest argument użytkownika za zostawieniem tak, jak jest), tylko w
odwrotnym przypadku: stacja startuje w poniedziałek, user edytuje projekty
cały tydzień bez restartu, a jedyna kopia jest z poniedziałku rano. Kopie
na serwerze są rotowane, więc z czasem znika i ta.

**Decyzja użytkownika 14.09.2026: ZOSTAJE jak jest, nie dokładamy timera.**
Wrócić do tematu, gdy ktoś zgłosi brak kopii z konkretnego dnia. Gotowe
warianty: (1) timer w aplikacji — po wykonaniu planuj następny za 24 h,
`after` co godzinę + sprawdzenie daty (przetrwa zmianę doby i uśpienie);
(2) zadanie w Harmonogramie Windows na W2019S — kopie niezależne od tego,
czy ktokolwiek pracuje, ale wymaga wdrożenia skryptu na serwerze.
Patrz [[project_audyt_min_po_przenosinach]].
