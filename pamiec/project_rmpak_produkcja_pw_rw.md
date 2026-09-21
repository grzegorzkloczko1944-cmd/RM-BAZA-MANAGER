---
name: project_rmpak_produkcja_pw_rw
description: "Produkcja wlasna RMPAK - PW/RW zamiast ZK, proces dziala end-to-end"
metadata: 
  node_type: memory
  type: project
  originSessionId: bd77b2db-aa7d-4871-a44f-b0388f221230
  modified: 2026-09-09T23:17:58.156Z
---

Tor produkcji własnej RMPAK: kalkulacja → PW → RW, osobny od toru zakupowego (ZK). Ustalenia w repo: `RMPAK_PRODUKCJA_USTALENIA.md`.

**Zasady, które nie podlegają renegocjacji bez powodu:**

* Ilość na PW z **projektu / BOM** (`COALESCE(work_qty, src_qty)`), NIE z `order_qty`. RMPAK nie zamawia u siebie.
* Produkcja własna = dostawca RMPAK / „RMPAK + materiał", **albo złożenie Z/ZZ bez dostawcy**. Wyjątek: złożenie z realnym dostawcą (MAJA) to zakup → zostaje na ZK.
* Filtr działa **tylko przy dodawaniu pozycji na dokument ZK** — nigdy przy budowie planu ani składów KT, inaczej drzewko się rozpada.
* Na PW idą **wyłącznie TW**. Komplety KT nie mają własnego stanu.
* **PW z ceną, RW bez ceny.** Ale RW NIE jest bezwartościowe: cena netto to parametr handlowy (na dokumencie magazynowym = 0), a wartość niesie `KosztMagazynowy`, który Subiekt liczy sam z ceny przyjęcia. Patrz [[project_koszt_magazynowy_vs_cena]].
* **Numery PW/RW czytane z Subiekta**, nie trzymane lokalnie — rozpoznanie po markerze „RM_BAZA — PROJEKT <nr>" w Uwagach. Ten sam wzorzec co `Ilość (zam.)`. Powód: `project_con` bez locka jest READ-ONLY, więc zapis lokalny cicho przepadał.
* `DAGAR + RMPAK` (kooperacja) celowo NIEROZSTRZYGNIĘTE — idzie na ZK.

**Stan 2026-09-10 (wypchnięte, `6dedb94`): wszystkie 5 kroków GOTOWE.** Proces przeszedł end-to-end na projekcie 3500 (id 71): ZK dostał 180 z 211 pozycji, `PW 2/MASTER/2026` (6 detali, 4848 PLN), `RW 1/MASTER/2026` z markerem `| PW: PW 2/MASTER/2026`, wartość 4848 zł jako koszt magazynowy.

Kod: `subiekt_produkcja.py` (cała reguła + PW/RW), sekcja w `rmpak_calculator.py`, filtr w `Projekt.cs`, cena w `Pw.cs`, koszt w `Dokumenty.cs`. Okno złożeń: `subiekt_zlozenia_gui.py`.

**Zmiana dostawcy złożeń** (commit `6178a42`): menu prawym w Projekt/Aktualizacja, kolumna „Dostawca” w tabeli, tryb mostu `zk-poz-usun` (zdejmuje z ZK pozycje przeniesione na produkcję własną, ale NIE rusza tych, które poszły dalej na ZD). Zapis MUSI iść przez `db_manager.project_con`, nie osobnym połączeniem — patrz [[project_zapis_do_bazy_projektu]]. Sfera nie wystawia `Usun` dla pozycji ZK; most NIGDY nie zeruje ilości jako zamiennik (zero wraca do BOM-u przez `_zapisz_ilosci_z_subiekta`).

**Nierozstrzygnięte:** magazyn dla PW/RW (na sztywno MASTER), status `DAGAR + RMPAK`, migracja `RMPAK + materiał` → jeden dostawca.

**How to apply:** przy zmianach trzymać wzorzec suchy przebieg → potwierdzenie → zapis → read-back po wierszach. Rebuild mostu: [[feedback_most_rebuild_release]]. Ceny na PW: [[project_cena_na_pozycji_pw]].
