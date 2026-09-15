---
name: project_zapis_do_bazy_projektu
description: "Zapis do bazy projektu TYLKO przez db_manager.project_con — nigdy własnym połączeniem do pliku na Y:, bo RM_BAZA pracuje na kopii lokalnej"
metadata: 
  node_type: memory
  type: project
  originSessionId: b4b4fbd4-107b-4ece-9328-8ca8b8a060fc
  modified: 2026-09-10T10:41:32.018Z
---

Każdy zapis do bazy projektu (`items` i reszta) MUSI iść przez
**`db_manager.project_con`** — nigdy przez własne `sqlite3.connect()` do
pliku na `Y:/RM_BAZA/projects/project_<id>.sqlite`.

**Why:** przy przejętym locku RM_BAZA pracuje na **kopii lokalnej**
(`C:/RMPAK_CLIENT/project_<id>.sqlite`) i dopiero przy zwalnianiu locka
nadpisuje nią plik na serwerze. Zapis „obok", wprost na `Y:`, ginie
bezpowrotnie w momencie zwolnienia locka — a wygląda na udany, bo commit
przechodzi. Realnie się na tym przewrócono przy zmianie dostawcy złożeń
(09/10.09.2026, `RMPAK_ZMIANA_DOSTAWCY_ZLOZEN.md`).

**How to apply:**
- Zapis: `self.db_manager.project_con.execute(...)` + `commit()`.
- Odczyt „na boku" (diagnostyka, statystyki) może iść własnym połączeniem
  RO, ale wtedy pamiętać, że przy locku widzi STAN SERWERA, nie to, co
  user właśnie zmienił — dlatego przy sprawdzaniu skutków zapisu czytać
  przez `project_con` albo po zwolnieniu locka.
- Ten sam wzorzec dotyczy nowych modułów: `subiekt_produkcja.plan_rw()` /
  `wyslij_rw()` i planowany bufor schowka montażowego
  ([[project_rmpak_produkcja_pw_rw]] jeśli powstanie).
- Diagnoza „zapisałem, a nie ma": sprawdzić, CZY jest lock, i porównać
  plik lokalny z serwerowym — patrz [[project_master_watchdog_ro]], gdzie
  ten sam objaw miał inną przyczynę (połączenie RO).

Master (`master.sqlite`) działa inaczej — tam nie ma kopii lokalnej, patrz
[[project_master_journal_delete]] i [[project_rm_baza_db_model_decision]].
