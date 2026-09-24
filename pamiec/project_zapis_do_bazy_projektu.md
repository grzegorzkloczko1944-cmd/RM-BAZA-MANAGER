---
name: project_zapis_do_bazy_projektu
description: Zapis do bazy projektu MUSI isc przez db_manager.project_con - RM_BAZA pracuje na kopii lokalnej i nadpisuje plik na Y:
metadata:
  type: project
---

RM_BAZA pracuje na **kopii lokalnej** projektu i przy zwalnianiu/odświeżaniu locka kopiuje ją na dysk sieciowy (`shutil.copy2(local_db, remote_db)`, `RM_BAZA_v15_MAG_STATS_ORG.py` ok. 10239) — **nadpisując plik w całości**.

**Skutek:** zapis zrobiony osobnym połączeniem `sqlite3.connect()` do pliku na `Y:` znika przy pierwszym odświeżeniu locka. Zmiana jest widoczna w oknie, a potem cicho wraca do poprzedniej wartości.

**Zawsze pisać przez `db_manager.project_con`** — to samo połączenie, którego używa arkusz. Tak robi kalkulator RMPAK przy cenach (`_save_item` w RM_BAZA) i tak musi robić każde okno.

Bez locka to połączenie jest **READ-ONLY** (log startowy: `REMOTE READ-ONLY`), więc akcje zapisujące trzeba wyszarzać z góry, sprawdzając `self.master.have_lock`.

Wykryte 2026-09-10 przy zmianie dostawcy złożeń: QUAY ustawiony na `2627-650.11ZZ` znikał po każdym odświeżeniu locka.

**Powiązane pułapki tej samej rodziny** (z notatki lokalnej M-OLD, 10.09.2026):

* **Nie zerować ilości na ZK zamiast usuwania pozycji.** Sfera nie wystawia
  `Usun` dla pozycji ZK (tylko dla dokumentów księgowych i windykacyjnych).
  Zero z ZK **wraca do bazy projektu** przez `_zapisz_ilosci_z_subiekta` jako
  `order_qty=0` i pozycja znika z BOM-u — nie da się jej już edytować.
  Lepiej powiedzieć „usuń ręcznie w Subiekcie".
* **`Zapisz()==true` nie znaczy, że zmiana weszła.** Most raportował
  „usunięto 3 poz.", a na dokumencie stały wszystkie. Po każdym zapisie robić
  read-back i podawać liczbę potwierdzoną odczytem.

Master (`master.sqlite`) działa inaczej — tam nie ma kopii lokalnej, patrz
[[project_master_journal_delete]] i [[project_rm_baza_db_model_decision]].

**How to apply:** przed dodaniem jakiegokolwiek zapisu do bazy projektu sprawdzić, skąd bierze się połączenie. Kontekst: [[project_rmpak_produkcja_pw_rw]], [[feedback_most_rebuild_release]].
