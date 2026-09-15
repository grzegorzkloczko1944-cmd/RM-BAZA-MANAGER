---
name: project_backup_nic_poza_gitem
description: "backup_nic.bat (lustro C:/Apps/RM_SERWER na NAS) żyje TYLKO na serwerze — poza gitem, bo ma hasło do konta nic\\mongo; decyzja użytkownika 14.09.2026"
metadata: 
  node_type: memory
  type: project
  originSessionId: 53d0f737-0a5d-428d-97fb-3835bdc2161b
  modified: 2026-09-14T18:52:17.666Z
---

**Kopia całego katalogu serwera na NAS — działa od 14.09.2026.**

| | |
|---|---|
| Skrypt | `C:\Apps\RM_SERWER\backup_nic.bat` (**tylko na serwerze, NIE w repo**) |
| Cel | `\\nic\PROG\RM_BAZA_MANAGER_BACKUP` |
| Zadanie | Harmonogram W2019S: **„RM_SERWER backup na nic"**, codziennie 02:00, konto SYSTEM |
| Zasada | `robocopy /MIR` — lustro, JEDNA kopia nadpisywana, bez historii |
| Log | `C:\Apps\RM_SERWER\logi\backup_nic.log` + znacznik `_ostatni_udany_backup.txt` w celu |

**Why (po co w ogóle):** cały system (master, rm_manager.sqlite, bazy
projektów, mapowania, KSeF, kopie dzienne) leży na JEDNYM dysku C: serwera.
Wewnętrzny backup RM_SERWER-a odkłada kopie w tym samym miejscu — padnięcie
dysku zabiera oryginał i kopie naraz. To wynosi wszystko poza serwer.
Cytat użytkownika: *„takie zabezpieczenie gdyby padł dysk fizycznie"*.

**Why (czemu poza gitem):** linia 63 ma hasło otwartym tekstem —
`net use %UDZIAL% /user:nic\mongo <haslo>`. To OSOBISTE konto na NAS-ie,
widzące wszystkie udziały (PROJEKTY, BIBLIOTEKA, Mongo, RMPAK…), nie
techniczne o wąskich prawach jak `RM_KLIENT` w `udzial_serwera.py` (tamto
jest w repo świadomie). Repo jest na GitHubie, a historia gita pamięta
wszystko — usunięcie później wymagałoby przepisania historii.

**Decyzja użytkownika 14.09.2026: wariant 1 — ZOSTAWIĆ JAK JEST.**
Odrzucone: (2) rozdzielenie hasła do `backup_nic.cfg` w `.gitignore`,
(3) osobne konto na NAS-ie z dostępem tylko do folderu backupu.

**How to apply:**
- ⚠️ **Odtwarzając serwer z gita, tego pliku tam NIE BĘDZIE** — trzeba go
  napisać od nowa albo odzyskać z kopii na `\\nic`. Sam skrypt jest w lustrze
  (kopiuje cały katalog serwera, czyli także siebie).
- Zmiana skryptu = edycja wprost na serwerze przez WinRM, bez commita.
- Przy odtwarzaniu z kopii: brać bazy z `Projekty\backup_RM_*\master`
  (spójne, Online Backup API), NIE żywe pliki z `dane\*.sqlite` — te mogły
  zostać złapane w połowie transakcji przez robocopy.
