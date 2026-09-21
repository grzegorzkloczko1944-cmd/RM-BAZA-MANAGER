---
name: project_srodowisko_domowe_m_old
description: Dom (M-OLD) udaje firmowy serwer W2019S przez udzial SMB + junctiony, bez zmian w kodzie
metadata:
  type: project
---

Na M-OLD (dom) kod RM_BAZA/RM_MANAGER ma na sztywno sciezke `\W2019S\RM_SERWER$`.
Zamiast ruszac kod (co zepsuloby wersje firmowa), dom UDAJE ten serwer:

- udzial SMB `RM_SERWER$` → `C:\RMPAK_CLIENT\RM_SERWER_UDZIAL` (`-FullAccess 'Wszyscy'`, bo polski Windows nie ma `Everyone`)
- w `hosts`: `127.0.0.1  W2019S`
- **`BackConnectionHostNames` = `W2019S`** w `HKLM\SYSTEM\CurrentControlSet\Control\Lsa\MSV1_0` — BEZ TEGO udzial dziala przez `localhost`/`M-OLD`/`127.0.0.1`, ale NIE przez `W2019S` (blokada loopbacku SMB). To bylo najdluzej szukane.
- dane NIE sa kopiowane — junctiony `RM_BAZA_projects` i `RM_MANAGER_projects` wskazuja na `C:\RMPAK_CLIENT\RM_BAZY\...`
- HMAC pominiety (uzytkownik go wywalil, kod znosi brak po cichu)
- `C:\RMPAK_CLIENT\sync_config.json` ma sekcje `rm_serwer: {host 127.0.0.1, port 5060}`

**Why:** dwa srodowiska (dom + firma) na jednym kodzie z gita; konfiguracja jest per-maszyna (gitignore / poza repo), wiec `git pull` nie miesza domu z firma.

**How to apply:** kolejnosc startu — `rm_serwer.py`, potem `RM_BAZA_v15_MAG_STATS_ORG.py`, potem `rm_manager_gui.py`. Odpalac przez `Start-Process` jako proces okienkowy, NIE przez `nohup` w tle (niedokonczony start zostawia mylace „inna instancja juz dziala"). Po `git pull` serwer podniesc od nowa, inaczej odpowiada starym kodem. Patrz [[project_subiekt_integracja_m_old]], [[feedback_most_rebuild_release]].
