---
name: project_autoaktualizacja_exe
description: "Autoaktualizacja .exe działa przez literę Y: — do przepisania na UNC, bo nie wszyscy mają tak pomapowane"
metadata: 
  node_type: memory
  type: project
  originSessionId: 69849967-a91f-4896-bd40-f0b3f36b7447
  modified: 2026-09-12T21:23:00.182Z
---

DO ZROBIENIA (zgłoszone 12.09.2026, odłożone na później): `DEFAULT_SERVER_EXE`
w `client_version.py` ma zaszyte `Y:/RMPAK_CLIENT/RM_BAZA_v15_MAG.exe`.
Nie wszystkie stanowiska mają ten udział pomapowany jako `Y:` — u nich
sprawdzanie wersji milczy (celowo nie blokuje pracy), więc .exe nigdy się
nie zaktualizuje i zostaje runda po komputerach.

**Why:** tego samego dnia wszystkie pozostałe ścieżki przeszły z liter dysków
na UNC `\\W2019S\RM_SERWER$\...` właśnie dlatego, że litera zależy od
stanowiska. `client_version.py` został pominięty.

**How to apply:** zmienić `DEFAULT_SERVER_EXE` na ścieżkę UNC do katalogu
z binarkami (tam, gdzie `.spec` je wystawia). Uwaga: `.spec` obu programów
publikuje na `Y:\RMPAK_CLIENT` — ścieżkę publikacji też trzeba przepisać na
UNC, inaczej będą się rozjeżdżać. Sam mechanizm jest sprawny:
`server_exe_path()` bierze plik o nazwie własnego .exe, `self_update()`
podmienia binarkę przez rename (Windows nie pozwala nadpisać uruchomionego
.exe, ale pozwala przemianować). Patrz [[project_client_version_gate]]
i [[project_odciecie_od_Y]].

**Potwierdzone na produkcji 14.09.2026:** dwie stacje ze starym buildem
(Wojtek 07:52 — plikowy `lock_manager_v2` założył `RM_BAZA\locks`; druga
07:20 — stary `_init_rfq_tags_tables` sprzed `40a02c5` założył `master.sqlite`
z samym `rfq_tags`) **pisały na udział `\\nic\rysunki\RM_BAZA`** mimo bramki
wersji. Bramka milczy, bo u nich udział nie jest `Y:` (`build_info` → None →
„wzorzec niedostępny" → przepuść). Wg `project_file_tracking` litery w firmie
to głównie **W: (51) i U: (25)**, `Y:` ma garstka — bramka jest ślepa na
większości stanowisk. Stare buildy nie logują się do `client_sessions`, więc
tabela sesji ich NIE pokazuje; widać je tylko po właścicielu pliku na NAS
(`Get-Acl`, SID `S-1-5-21-1450428445-…`; RID→osoba z autorów w `$chat`:
3004 mongo, 3016 Pioter, 3020 DYREKTOR, 3028 Agnieszka, 3042 KAMILA/USER$$,
3044 Wojtek, 3052 Grzegorz Talaga).

**Decyzja użytkownika 14.09.2026:** na udziale `\\nic\rysunki` (Y:) zostaje
**wyłącznie `RMPAK_CLIENT\` z binarką do aktualizacji**; `RM_BAZA\` ma zniknąć
w całości. Tray (`RM_Tray_Organizer`) jest niewinny: `get_master_sqlite_path`
sprawdza `exists()` i otwiera `mode=ro` — nie tworzy pliku; jego
`master_sqlite_path`/`server_apps_path` to osobny config per stacja
(`rm_tray_config.json` obok .exe), też z literą.
