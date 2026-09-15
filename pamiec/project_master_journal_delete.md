---
name: project_master_journal_delete
description: master.sqlite celowo w journal_mode=delete — NIE proponować WAL/TRUNCATE; WAL po SMB z wieloma piszącymi się rozpada
metadata: 
  node_type: memory
  type: project
  originSessionId: b4b4fbd4-107b-4ece-9328-8ca8b8a060fc
  modified: 2026-09-09T10:01:06.921Z
---

`Y:/RM_BAZA/master.sqlite` ma `journal_mode=delete`, `synchronous=2`, `busy_timeout=5000` — i to jest **świadoma decyzja** użytkownika (potwierdzone 09.09.2026).

**Why:** WAL po SMB z wieloma użytkownikami piszącymi jednocześnie się psuje (plik `-shm` wymaga współdzielonej pamięci, której udział sieciowy nie zapewnia). Bazy projektowe mogą być w WAL (jeden piszący na raz przez locki), master nie.

**How to apply:** Widok pliku `master.sqlite-journal` i chwilowa blokada pliku na wyłączność to NORMALNE zachowanie, nie objaw awarii. Nie diagnozować "brak połączenia z RM_BAZA" jako winy journal_mode i nie proponować migracji na WAL/TRUNCATE. Szukać przyczyny gdzie indziej (watchdog RO — [[project_master_watchdog_ro]], sieć, locki w [[reference_db_paths]]).

Uboczne ustalenia z tej samej diagnozy:
- RM_Tray_Organizer nie generuje ruchu sieciowego poza SMB; podwójne procesy TRAY/RM_BAZA to bootloader+dziecko PyInstaller onefile, NIE duplikaty — nie ubijać.
- `Y:/RM_BAZA/locks/sync_config.json` (17.02.2026, ścieżki `U:`) to martwy śmieć — RM_BAZA czyta config lokalnie z `C:/RMPAK_CLIENT/sync_config.json`.
