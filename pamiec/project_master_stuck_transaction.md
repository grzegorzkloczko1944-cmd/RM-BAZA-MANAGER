---
name: project_master_stuck_transaction
description: "PRZYCZYNA rodziny \"master locked\" — nieudany commit() na master_con zostawia transakcję OTWARTĄ (RESERVED do końca procesu); zakleszczenie samoodtwarzające się między stanowiskami; fix master_commit()+siatka (11.09.2026)"
metadata: 
  node_type: memory
  type: project
  originSessionId: b4b4fbd4-107b-4ece-9328-8ca8b8a060fc
  modified: 2026-09-11T13:35:30.362Z
---

**Przyczyna źródłowa** całej rodziny „master.sqlite locked" (watchdog RO 07.09,
crash close() 09.09, „lock trwa kilkanaście sekund" 11.09.2026):

`master_con` ma `isolation_level='DEFERRED'`. DML otwiera transakcję. Gdy
`commit()` padnie na „database is locked" (ktoś czytał w tej chwili — po SMB
w journal=delete to codzienność), **Python NIE cofa transakcji**: połączenie
zostaje `in_transaction=True` i trzyma RESERVED **do zamknięcia procesu**.
Nikt w firmie nie zapisze do master. Druga połowa: nieudany DML (bo ktoś
trzyma RESERVED) TEŻ zostawia otwartą transakcję, a każdy kolejny SELECT na
tym połączeniu trzyma SHARED — więc posiadacz RESERVED nie może zrobić
commit. **Zakleszczenie wielu stanowisk, które odtwarza się samo**, dopóki
choć jeden stary klient ma otwartą transakcję. Udowodnione na bazie
tymczasowej (Python 3.14, sqlite 3.50).

**Why:** w RM_BAZA było 17 miejsc DML na `master_con` z `commit()` i ŻADNE
z `rollback()` przy błędzie. Objaw widać dopiero przy 6+ stanowiskach online
(11.09: master zablokowany 96–100% czasu przez >40 min, `client_sessions`
zamrożone o 14:44).

**How to apply:**
- Zapis do master TYLKO przez `db_manager.master_commit()` (commit → przy
  błędzie rollback → wyjątek dalej). Nigdy gołe `master_con.commit()`.
- Siatka: `master_rollback_stuck()` na starcie `acquire_lock`/`release_lock`
  i w heartbeacie (transakcja wisząca 2 ticki = cofnij). Log: „🧹 master_con:
  cofnieto wiszaca transakcje".
- Diagnoza w 10 s: `sqlite3.connect(master, timeout=0.05); BEGIN IMMEDIATE`
  w pętli — `X` = zablokowany. Kto trzyma: **\\nic → Zarządzanie komputerem →
  Foldery udostępnione → Otwarte pliki → master.sqlite** (WinRM na nic
  nie działa: TrustedHosts).
- Zdalnego posiadacza zwalnia TYLKO restart jego RM_BAZA (lub zamknięcie
  pliku na serwerze). Bramka wersji sprawdza wersję **tylko przy starcie**
  — kto ma RM_BAZA otwartą, monitu NIE zobaczy; po publikacji .exe trzeba
  ludziom powiedzieć „zrestartujcie".
- **NIE testować przejmowania locków ze źródeł na produkcji przy wielu
  osobach online** — 11.09 to moja instancja testowa (otwarta transakcja +
  SELECT trzymający SHARED przy przejęciu locka) uruchomiła zakleszczenie
  całej firmy. Do testów locków: baza DEMO albo pora, gdy nikogo nie ma.
- Zapisy best-effort w ścieżce locka (`usun_zamowienia`) mają timeout 0,5 s,
  nie 10 — inaczej „zwalnianie locka się wiesza".
- Most Subiekta i SMB są tu NIEWINNE (zk-ilosci 30 ms, kopia pliku 1 ms) —
  nie szukać N+1 w moście. Log RM_BAZA uruchamiać `python -u`, inaczej bufor
  gubi wszystko z testów (taskkill = utrata bufora).
- **Trwałe rozwiązanie:** [[project_rm_serwer_plan]] — serwer mastera (etap 1),
  jedyny właściciel pliku.
- Powiązane: [[project_master_watchdog_ro]], [[project_master_con_retire_crash]],
  [[project_master_journal_delete]].
