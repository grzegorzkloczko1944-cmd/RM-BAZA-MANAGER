---
name: project_rm_dwf_sciezki_serwer
description: "RM_DWF (repo NOW) — ścieżki do RM_MANAGER poprawione na lokalne serwera 15.09.2026; config per instalacja, poza gitem; RM_DWF nie robi żadnych backupów"
metadata: 
  node_type: memory
  type: project
  originSessionId: 53d0f737-0a5d-428d-97fb-3835bdc2161b
  modified: 2026-09-15T11:22:30.012Z
---

RM_DWF filtruje listę projektów widoczną dla monterów po statusie z RM_MANAGER
(usługa na W2019S, port 5057, `C:\Apps\NOW\RM_DWF`).

## Naprawione 15.09.2026 (commit `f3d51fc` w repo NOW)

Po przenosinach danych na serwer (12.09) config wskazywał
`\\nic\rysunki\RM_BAZA\master.sqlite` — udział, do którego konto usługi nie ma
dostępu, a dane i tak leżą gdzie indziej. **Przez trzy dni RM_DWF w ogóle nie
filtrował** — cicho, bo:

⚠️ **`Path.is_file()` na ścieżce sieciowej nie zwraca False — RZUCA**
`PermissionError [WinError 5]`. Stało PRZED blokiem `try`, a w `except` był
tylko `sqlite3.Error`, więc wyjątek szedł aż do `api_projects` i wywracał całą
listę projektów — mimo że docstring obiecywał „błąd odczytu nie wywala
wyjątku". Ten sam wzorzec był w `_read_latest_event_closed`, która leci
w PĘTLI po 81 plikach. Teraz `OSError` obok `sqlite3.Error` w obu miejscach.

**Ścieżki (tylko na serwerze, patrz niżej):**
```
rm_manager_db_path      = C:\Apps\RM_SERWER\dane\master.sqlite
rm_manager_projects_dir = C:\Apps\RM_SERWER\dane\Projekty\RM_MANAGER_projects
```
⚠️ Tabela `projects` (nazwa folderu → `project_id`) jest w **masterze RM_BAZA**,
NIE w `rm_manager.sqlite` (ta nie ma takiej tabeli) — sprawdzone na serwerze.
Statusy czytane są potem z per-projektowych `rm_manager_project_<id>.sqlite`
(tabela `project_events`), bo `projects.status` w masterze bywa martwa.

Po poprawce: 78 projektów w mapie, 51 zamkniętych, 27 aktywnych, zero błędów.

## Co warto wiedzieć

- **`config.json` jest w `.gitignore`** — konfiguracja per instalacja. Poprawka
  ścieżek żyje TYLKO na serwerze; w repo zostaje wersja ze starymi. Stawiając
  RM_DWF od nowa, trzeba je wpisać ręcznie.
- ⚠️ **Aplikacja przepisuje `config.json` sama** (zapisuje stan z pamięci, gdy
  admin zmieni coś w panelu). Edytować przy ZATRZYMANEJ usłudze, inaczej zmiana
  zostanie nadpisana. 15.09 obeszło się bez szkody — ścieżki były już poprawne
  w pamięci po restarcie. Ten sam mechanizm co w RM_MANAGER.
- **RM_DWF NIE robi żadnych backupów** — zero `shutil`/`copy2` w kodzie. Pliki
  `*.bak_*` w jego katalogu to ręczne kopie sprzed wdrożeń. Do baz łączy się
  wyłącznie `mode=ro`, nigdy nie zapisuje do cudzej bazy.
- Zapisuje tylko swoje: `config.json`, `library.json` (indeks biblioteki),
  `_launcher_netuse.log`.

Patrz [[project-odciecie-od-y]], [[project_audyt_min_po_przenosinach]].
