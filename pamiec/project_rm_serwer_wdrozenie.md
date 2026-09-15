---
name: project_rm_serwer_wdrozenie
description: "RM_SERWER na W2019S — usługa NSSM, port 5060, C:\\Apps\\RM_SERWER; stan wdrożenia etapu 1 (master przez serwer) na 11.09.2026"
metadata: 
  node_type: memory
  type: project
  originSessionId: b4b4fbd4-107b-4ece-9328-8ca8b8a060fc
  modified: 2026-09-11T17:01:37.694Z
---

**RM_SERWER działa na produkcyjnym serwerze** jako usługa NSSM (11.09.2026,
etap 1 planu — [[project_rm_serwer_plan]]).

| | |
|---|---|
| Host | `W2019S`, `192.168.100.84`, Python **3.12.8** |
| Katalog | `C:\Apps\RM_SERWER\` (kod), `dane\master.sqlite`, `logi\`, `backup\` |
| Usługa | NSSM `RM_SERWER`, Automatic, `AppExit Default Restart` |
| Port | **5060** + reguła zapory „RM_SERWER (port 5060)" |
| Restart | `Restart-Service RM_SERWER -Force` |

Zmierzone przez LAN ze stacji roboczej: **odczyt ~20 ms, zapis 22 ms**,
idempotencja działa. Lokalnie: 10 równoczesnych zapisów 10/10 w 0,06 s.

**How to apply:**
- Wdrożenie/diagnostyka przez WinRM wg [[project_rm_serwer_plan]] i
  `NOW/DOKUMENTACJA/DOSTEP_SERWER.md` (poświadczenia `%TEMP%\rmdwf_srvcred.xml`).
- `python rm_serwer.py --sprawdz` — diagnostyka bez nasłuchu (integrity_check,
  migracje, wykryty schemat suppliers, wolny port).
- ⚠️ **Sesja WinRM NIE widzi `Y:` ani `\\nic`** („Access is denied") — kopię
  mastera na serwer robić w dwóch krokach: lokalnie `Connection.backup()`
  (żywy plik jest zajęty, `copy2` się nie uda), potem `Copy-Item -ToSession`.
- ⚠️ **Proces uruchomiony przez `Start-Process` w sesji WinRM ginie razem
  z sesją.** Do testów używać usługi, nie ręcznego startu.
- ⚠️ **cp1250 + emoji w `print` = UnicodeEncodeError, który KOŃCZY proces.**
  `rm_serwer` robi `reconfigure(encoding="utf-8")` na starcie — nie usuwać.
  To samo co [[project_cp1250_emoji_print]].
- Klient (`rm_klient`) domyślnie w trybie **legacy** — serwer włącza się
  wpisem `{"rm_serwer": {"tryb": "serwer", "host": "192.168.100.84",
  "port": 5060}}` w `sync_config.json` na `Y:`, GLOBALNIE dla wszystkich.
- Stan na 11.09.2026: **etap 1 i 2.5 domknięte** — szczegóły w
  [[project_rm_serwer_etap25_domkniecie]]. Serwer trzyma trzy bazy w
  `C:\Apps\RM_SERWER\dane\`: `master.sqlite`, `rm_manager.sqlite`,
  `subiekt_mapowania.sqlite`. HMAC **włączony**.
