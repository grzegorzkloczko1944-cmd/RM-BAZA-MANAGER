---
name: project_client_version_gate
description: "Bramka wersji .exe + heartbeat sesji (client_sessions) w RM_BAZA — client_version.py, 09.09.2026; jak działa, czego NIE blokuje"
metadata: 
  node_type: memory
  type: project
  originSessionId: b4b4fbd4-107b-4ece-9328-8ca8b8a060fc
  modified: 2026-09-09T10:11:09.011Z
---

Dodane 09.09.2026. Build: `python -m PyInstaller --noconfirm --clean RM_BAZA_v15_MAG.spec` (NIE _STATS_ORG.spec) — spec na końcu SAM PUBLIKUJE `dist/RM_BAZA_v15_MAG.exe` na `Y:/RMPAK_CLIENT` (poprzednia → `backup dd-mm-rrrr`, copy2 dla mtime). Każdy build = publikacja = blokada starych klientów. Moduł `client_version.py`
+ 9 wpięć w `RM_BAZA_v15_MAG_STATS_ORG.py` + `"client_version"` w spec.

**Po co:** userzy na wersjach sprzed fixu watchdoga (07.09, `2cf4473`) przy
`journal_mode=delete` blokowali mastera wszystkim i sami ścinali się do RO
([[project_master_journal_delete]], [[project_master_watchdog_ro]]). Nie
było jak sprawdzić, kto na czym siedzi.

**Bramka startu** (`check_outdated`, w `initialize_core` PRZED
DatabaseManager): własny `.exe` vs `Y:/RMPAK_CLIENT/RM_BAZA_v15_MAG.exe`
(to samo miejsce, z którego aktualizuje TRAY). Porównanie rozmiar+mtime,
nie hash. Przestarzały = serwerowy NOWSZY i INNY rozmiar. Dialog proponuje
`self_update` (rename uruchomionego .exe → `.old`, copy2 z serwera, rollback
przy błędzie), potem `destroy()`.

**NIE blokuje:** pracy ze źródeł (`sys.frozen` False), lokalnego buildu
nowszego niż serwerowy (dev), gdy wzorzec niedostępny, gdy
`ui.version_gate=false` w sync_config. Wzorzec nadpisywalny:
`paths.server_exe`. Innych blokuje dopiero po WGRANIU nowego .exe na
Y:/RMPAK_CLIENT i tylko przy ich starcie — publikacja = decyzja.
Stare wersje bramki nie mają — ich nie zatrzyma; widać je po NIEOBECNOŚCI
w sesjach.

**Heartbeat** (`heartbeat`): tabela `client_sessions` w masterze (PK host),
UPSERT co tick istniejącego heartbeatu locków (2 min, wątek roboczy) +
5 s po init. WŁASNE krótkie połączenie, busy_timeout 2 s — nigdy
`master_con` (wątek!). Przy locked odpuszcza, pierwszą awarię loguje raz.
`close_session` w `cleanup_on_exit` ustawia `ended_at`.

**Okno:** Narzędzia → „👥 Sesje klientów…" (`menu_show_client_sessions`):
czerwone = build_id ≠ serwerowy, szare = zamknięta/bez sygnału >5 min.

**How to apply:** przy pytaniu „kto ma starą wersję" — to okno albo
`SELECT host, username, build_id, last_seen FROM client_sessions`.
Przy publikacji nowego .exe na Y:/RMPAK_CLIENT pamiętać, że od tej chwili
wszyscy ze starym dostaną blokadę przy starcie.

## Katalog testowy (10.09.2026)

Build z `RM_BAZA_v15_MAG.spec` laduje w `Y:/RMPAK_CLIENT/TESTY RM_BAZA/`, NIE na produkcji — inaczej bramka wersji wywolywala monit o aktualizacji u wszystkich userow po kazdym buildzie (127 MB do pobrania). Wydanie na produkcje to swiadomy, reczny krok: `copy /y` do `Y:/RMPAK_CLIENT/` (mtime musi przetrwac, bramka porownuje rozmiar+mtime).
