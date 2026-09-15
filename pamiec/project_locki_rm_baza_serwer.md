---
name: project_locki_rm_baza_serwer
description: "Blokady RM_BAZA przez serwer (12.09.2026) — DWA osobne systemy: lock-* do mastera, rmm-lock-* do rm_manager.sqlite; numery projektów kolidują w 81/85"
metadata: 
  node_type: memory
  type: project
  originSessionId: 69849967-a91f-4896-bd40-f0b3f36b7447
  modified: 2026-09-12T14:17:03.721Z
---

**Blokady RM_BAZA idą przez RM_SERWER** (12.09.2026, commit `539f644`) —
koniec plików `project_<id>.lock` na dysku sieciowym. To samo, co wcześniej
przeszedł RM_MANAGER.

**⚠️ DWA OSOBNE SYSTEMY BLOKAD — nie jeden wspólny:**

| program | operacje | baza |
|---|---|---|
| RM_BAZA | `lock-*` (bez prefiksu) | master RM_BAZA |
| RM_MANAGER | `rmm-lock-*` | `rm_manager.sqlite` |

Rozdziela je **routing serwera po prefiksie nazwy** (`rm_serwer._polaczenie`).
Tabela `project_locks` nazywa się w obu bazach tak samo, ale to inne pliki
i nic ich nie łączy.

**Why:** numery projektów obu programów **pokrywają się w 81 na 85 przypadków**
(RM_BAZA 1..2611, RM_MANAGER 1..90). Jedna wspólna tabela kazałaby userowi
RM_BAZA czekać na „zajęty" projekt 22 dlatego, że ktoś otworzył zupełnie inny
projekt 22 w RM_MANAGER. Sprawdzone przed wdrożeniem — to nie teoria.

`lock_manager_baza_serwer.ProjectLockManager` jest **podklasą**
`lock_manager_serwer` i podmienia wyłącznie transport (master przez
`rm_klient` zamiast `rm_manager.rmm_*`) oraz prefiks nazw (`_nazwa()` ścina
`rmm-`). Logika wyścigu, przejmowania i bicia serca żyje w jednym miejscu.

**How to apply:**
- Zmiana operacji blokad = zmiana w `rm_serwer_operacje.py` **i wgranie na
  serwer + `Restart-Service RM_SERWER`**, inaczej klient dostaje
  „nieznana operacja odczytu". Tabelę zakłada migracja przy starcie.
- Wgrywanie na serwer: `Copy-Item -ToSession` przez WinRM **po IP
  192.168.100.84** (nie po nazwie — TrustedHosts ma tylko IP). Backup pliku
  przed nadpisaniem; sprawdzić składnię na serwerze PRZED restartem.
- `lock_manager_v2` (pliki) zostaje w repo jako awaryjny powrót — wystarczy
  cofnąć import w `RM_BAZA_v15_MAG_STATS_ORG.py`.
- `locks_dir` w `sync_config.json` jest już nieużywany, ale zostaje —
  konstruktor go przyjmuje i ignoruje.
- Test wyścigu bez ruszania produkcji: numer projektu 999999 + dwa menedżery
  z różnym `my_computer`, wątki równolegle. Skrypt wzorcowy był w scratchpadzie.

**Przy okazji (12.09.2026):** bazy projektowe RM_BAZA (85 + 7 magazynowych)
**przeniesione** z `Y:\RM_BAZA\projects` i `projects_MAG` do
`\\W2019S\RM_SERWER$\RM_BAZA_projects` — oba rodzaje w JEDNYM katalogu
(`projects_dir` i `projects_mag_dir` wskazują to samo miejsce). Skopiowane
z weryfikacją SHA-256 każdego pliku, źródło na `Y:` zostało nietknięte jako
zapas. Pominięte 2 pliki `project_22_before_restore_*` (archiwum z kwietnia).
`project_2611.sqlite` ma **0 bajtów od utworzenia** (27.07) i taki sam jest
we wszystkich backupach — to nie uszkodzenie z przenosin.

Powiązane: [[project_udzial_ukryty_rm_serwer]],
[[project_bazy_projektowe_konto_techniczne]], [[project_rm_serwer_etap25_domkniecie]].
