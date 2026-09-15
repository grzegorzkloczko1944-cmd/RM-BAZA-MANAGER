---
name: project_audyt_min_po_przenosinach
description: "Audyt 14.09.2026: wszystkie pozostale 'miny' po przenosinach na serwer — co naprawione, co zostaje i dlaczego"
metadata: 
  node_type: memory
  type: project
  originSessionId: 53d0f737-0a5d-428d-97fb-3835bdc2161b
  modified: 2026-09-14T11:01:57.013Z
---

Pelny audyt kodu 14.09.2026 po tym, jak wzorzec „sciezka liczona ze starej
lokalizacji" wyszedl trzeci raz tego dnia (okno ZD bez dostawcow).

## Naprawione tego dnia

| gdzie | objaw | fix |
|---|---|---|
| `subiekt_stany._projects_dir()` | config stacji `Y:\RM_BAZA\projects` → katalog nie istnieje; **7 miejsc** w 5 modulach dostawalo `{}`/`None` BEZ bledu (okno ZD bez dostawcow, typow, przypisania do projektu) | podmiana starych koncowek na `\\W2019S\RM_SERWER$\RM_BAZA_projects`, jak `_na_serwer()` w RM_BAZA |
| `subiekt_zamowienia.pracownik_rm_manager` | `os.path.isfile` na `<projekty>/../RM_MANAGER/rm_manager.sqlite` — plik nie istnieje NA ZADNEJ stacji; kontakt prowadzacego cicho znikal z wysylki ZD | straznik usuniety, `get_employee_by_user_login` i tak chodzi przez `rmm-*` |

Ciche zwroty przy braku pliku projektu (wszystkie przez `PROJECTS_DIR`, wiec
naprawione hurtem): `subiekt_pozycja_gui:125`, `subiekt_projekt:398/1138/4215`,
`subiekt_wydanie_gui:976`, `subiekt_zamowienia:302`, `subiekt_zlozenia_gui:96`.

## Rozbrojone tego samego dnia (druga tura, „napraw to")

- `subiekt_scalanie.KATALOG_CACHE` -> `C:/RMPAK_CLIENT/subiekt_katalog.json` (lokalnie;
  na udziale NIGDY nie zostal zapisany, wiec kazde otwarcie okna pobieralo
  kartoteki 15 s od nowa).
- `subiekt_wyslij_zd._katalog_pdf_domyslny` -> wprost `udzial_serwera.UDZIAL/zd_pdf`
  (bylo `Path(master).parent/zd_pdf` — trafialo w korzen udzialu przypadkiem).
  6 PDF-ow ZD z `Y:/RM_BAZA/$zd_pdf` SKOPIOWANE na serwer (Y: nietkniete).
- `subiekt_historia.historia_dir` -> wprost `udzial_serwera.UDZIAL/subiekt_historia`
  (ten sam przypadek co zd_pdf).
- Martwe pomocniki usuniete: `_sciezka_master` (subiekt_zamowienia, subiekt_produkcja),
  `_master_path` (subiekt_dostawcy), `_master` (subiekt_wyslij_zd),
  `_czy_master_ro` + galaz „TYLKO DO ODCZYTU, sprawdz uprawnienia do Y:" (RM_BAZA).

## Trzecia tura (14.09, „backupy sie robia na serwerze")

- `rm_manager.py` — trzeci zapas `Y:/RM_BAZA/sync_config.json` z listy configow
  USUNIETY (plik i tak przemianowany na `$sync_config.json`).
- `backup_manager.py` blok `__main__` — sciezki serwera przez `udzial_serwera.UDZIAL`
  + `reconfigure(utf-8)` (emoji w print wywalalo proces przy uruchomieniu z konsoli).
  Uruchomienie = to samo, co RM_BAZA przy pierwszym starcie dnia: 93 pominiete,
  0 bledow, lista master parsuje nazwy serwera (`master_20260914_004425`).
- Nastepstwo poprawki backupu MAG: `list_project_backups` parsowal date jako
  `split('_',2)[2]` (dla `project_MAG_11_2026-09-14` dawalo `11_2026-09-14`),
  `list_all_project_backups` robil `int("MAG")`. Naprawione; RM_BAZA dostal
  `_klucz_backupu(project_id, typ)` -> `MAG_N` dla WAREHOUSE, uzyty w liscie dat,
  podgladzie kopii i dialogu przywracania. `restore_project("MAG_11", ...)` trafia
  we wlasciwy plik, bo wzorzec `project_{id}.sqlite` daje `project_MAG_11.sqlite`.
  BEZ tego klucza przywrocenie kopii magazynu nadpisaloby baze maszynowa o tym
  samym numerze.

## Zostaje — swiadomie

- **`DEFAULT_MASTER_PATH` / `DEFAULT_LOCKS_DIR`** (`RM_BAZA:338/342`) — master nie
  jest otwierany, blokady w tabeli. Zostaja jako kotwica katalogu w configu.
- **`client_version.DEFAULT_SERVER_EXE`** — kanal aktualizacji `.exe`, jedyna
  rzecz, ktora zostaje na `Y:` (decyzja uzytkownika 14.09.2026).

## Obserwacja: kopie RM_MANAGER stoja od piatku

`RM_SERWER$/backup_RM_MANAGER/projects` — ostatnie pliki 12.09 22:55, w poniedzialek
14.09 zero, choc stacje pracuja (sesje RM_BAZA z 12.09 23:20 wciaz zywe = komputery
nie byly restartowane przez weekend). Mechanizm „raz dziennie" w OBU programach
odpala sie TYLKO przy starcie aplikacji (`run_backup_in_background` po 3 s) —
aplikacja chodzaca tydzien nie robi kopii wcale. Build RM_MANAGER z 23:08 NIE jest
przyczyna (`backup_manager` w datas, import statyczny). Kandydat: backup takze
z timera (np. co 24 h od startu) — nie zrobione, do decyzji.

**Why:** te miny nie daja bledu — daja CISZE. `return {}` przy braku pliku
wyglada jak „nie ma danych", nie jak „zla sciezka". Roznica miedzy stacjami
(budujacy ma poprawiony config, reszta nie) sprawia, ze u autora wszystko
dziala i nikt nie umie tego wytlumaczyc.

**How to apply:** szukajac podobnego — `grep -rn "dirname(PROJECTS_DIR\|master_path).parent"`.
Kazda nowa sciezka liczona z `PROJECTS_DIR` albo `master_path` to kandydat.
Patrz [[project-odciecie-od-y]], [[project_mapowania_subiekta_stan_14_09]].

## Wydanie 14.09.2026 13:24

Commity `43c82ef` (okno ZD / PROJECTS_DIR), `3e1dec4` (kalkulatory, backup MAG,
most w tle, audyt userow), `54f93bd` (sprzatanie sciezek + usuniety zbedny
`RM_BAZA_v15_MAG_STATS_ORG.spec`). Build `RM_BAZA_v15_MAG.spec` ->
`Y:\RMPAK_CLIENT\RM_BAZA_v15_MAG.exe` (128232209 B, 13:24:06), zweryfikowany:
wstaje, melduje sie w `client_sessions` z nowym `exe_mtime`. **NIE wypchniete
na origin** — push tylko na wyrazne polecenie ([[feedback_git_push]]).

Obserwacja z `sessions-list`: stacje RMPPC17 i RMPPC18 pobraly build z 12:42
tego samego dnia same — kanal aktualizacji przez bramke wersji dziala tam,
gdzie udzial jest zamapowany jako `Y:` ([[project_autoaktualizacja_exe]]).
