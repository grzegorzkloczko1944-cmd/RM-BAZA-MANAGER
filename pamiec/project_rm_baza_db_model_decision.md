---
name: project_rm_baza_db_model_decision
description: "Decyzja 09.09.2026 — RM_BAZA zostaje na obecnym modelu master_con; docelowo HTTP/API, NIE przebudowywać warstwy SQLite po drodze"
metadata: 
  node_type: memory
  type: project
  originSessionId: b4b4fbd4-107b-4ece-9328-8ca8b8a060fc
  modified: 2026-09-09T10:57:53.449Z
---

**Decyzja użytkownika (09.09.2026):** warstwa dostępu do mastera w RM_BAZA
zostaje jak jest („ma działać jako tako"). Docelowo komunikacja przejdzie na
**HTTP** (serwer na `nic`, klienci przez API — jest już Flask w RM_RFQ), ale
„nie teraz".

**Why:** obecny model (jedno długożyjące `master_con`, `check_same_thread=False`,
`immutable=1` RO + przełączanie RW dla ADMIN-a, watchdog z timeoutem) jest
hybrydą płacącą za obie strony, ale po naprawach z 09.09
([[project_master_con_retire_crash]], [[project_master_watchdog_ro]]) jest
stabilny. Pośredni refaktor (połączenie per wątek + `write()` context manager)
był rozważany i odrzucony — nie warto robić dwóch migracji.

**How to apply:**
- NIE proponować przebudowy modelu połączeń, WAL, property per-wątek itp.
  Naprawiać punktowo, w obecnym wzorcu.
- Nowy kod w wątkach tła: własne krótkie połączenie (jak `client_version.heartbeat`),
  nigdy `master_con` — to jedyna „zasada na przyszłość", bez refaktoru.
- Nigdy `master_con.close()` / `project_con.close()` poza świadomym zamknięciem —
  `_retire_*_con()`.
- Zapis na masterze = `commit()` w tej samej funkcji (RESERVED lock wisi do commitu).
- Gdy przyjdzie czas na HTTP: RM_MANAGER (krótkie połączenia per operacja) jest
  bliższy temu modelowi niż RM_BAZA — [[project_ai_agents_two_places]] to nie to samo.

Fakty o lockach (żeby nie liczyć od nowa): zwykły user na `immutable=1` nie
zakłada ŻADNEGO locka; ADMIN RW trzyma RESERVED od pierwszego zapisu do
`commit()`; storm 09.09 = seria krótkich, cofanych transakcji ze starych
klientów, nie „długi lock".
