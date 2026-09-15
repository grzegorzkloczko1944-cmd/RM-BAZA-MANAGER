---
name: project_master_con_retire_crash
description: Twarde crashe RM_BAZA 0xc0000005 (sqlite3.dll/python314.dll) = close() dzielonego master_con z innego wątku; fix _retire_master_con (09.09.2026)
metadata: 
  node_type: memory
  type: project
  originSessionId: b4b4fbd4-107b-4ece-9328-8ca8b8a060fc
  modified: 2026-09-09T10:45:55.813Z
---

**Objaw:** RM_BAZA pada twardo (dump w `%LOCALAPPDATA%\CrashDumps`, Event Log
1000, kod `0xc0000005`, moduł `sqlite3.dll` / `python314.dll` / `ntdll.dll`),
bez wyjątku Pythona. Cztery takie 09.09.2026, zawsze gdy master był
blokowany przez innych klientów (storm journali co ~2 s od userów na starych
wersjach — [[project_client_version_gate]]).

**Mechanizm:** wszystkie połączenia mają `check_same_thread=False`, `master_con`
dzieli ~20 wątków. `_safe_ensure_master_alive` odpala `ensure_master_alive()`
w wątku z timeoutem **3 s**, ale reconnect ma busy_timeout **5 s** → przy
locku GUI porzuca wątek, pracuje dalej na `master_con`, a porzucony wątek
2 s później **zamyka to samo połączenie** → use-after-free w sqlite.
Watchdog RO-degradacja ([[project_master_watchdog_ro]]) to był inny bug
w tej samej funkcji.

**Fix (database_manager.py):** `_retire_master_con()` = `self.master_con = None`
BEZ `close()` — CPython zamknie połączenie, gdy ostatni wątek skończy na nim
pracować, we własnym wątku. Podmienione 5 miejsc w managerze + 4 w GUI
(„wymuś reconnect przez close()"). Reconnect w `ensure_master_alive` pod
nieblokującym `_master_reconnect_lock` (osobny od istniejącego
`_reconnect_lock`, który ma blokujący `acquire()` w innej funkcji).
Prawdziwe `close()` tylko w `close_all()`.

Test: 6 wątków SELECT + wątek retire/connect + wątek watchdog przez 6 s
→ 4830 odczytów, 0 błędów, brak AV (scratchpad `stress_retire.py`).

**How to apply:** nigdy nie wołać `master_con.close()` poza `close_all()`;
przy „wymuś reconnect" używać `_retire_master_con()`. Przy nowym dumpie
0xc0000005 w sqlite3.dll szukać innego miejsca, które zamyka dzielone
połączenie (project_con ma ten sam wzorzec i NIE jest jeszcze objęty).
Diagnostyka: Event Log Application Id=1000 daje moduł winny bez WinDbg.
