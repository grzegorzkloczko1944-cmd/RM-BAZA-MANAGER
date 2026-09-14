# TODO — odcięcie RM_BAZA od dysku `Y:` (do zrobienia w firmie, na żywym organizmie)

Stan na 14.09.2026 (audyt z M-OLD). Kod pracuje przez RM_SERWER i UNC
`\\W2019S\RM_SERWER$`, ale zostały miejsca, które **otwierają pliki
bezpośrednio** po ścieżce z `sync_config.json` stacji — a stacje mają
configi sprzed przenosin (`Y:/RM_BAZA/...`). Na M-OLD tego nie widać, bo
tam config jest poprawiony ręcznie. W firmie trzeba to sprawdzić na
prawdziwej stacji, z prawdziwym configiem.

Kolejność: pkt 0 (ustalenia) → 2 (bezpieczne) → 1 (główne) → 3 (porządki).

---

## 0. Do ustalenia PRZED zmianami (w firmie)

- [ ] **Gdzie fizycznie leży dzisiejszy `subiekt_mapowania.sqlite`?**
      Kandydaci: `Y:\RM_BAZA\subiekt_mapowania.sqlite` (stara lokalizacja,
      wynika z `paths.master` w configu stacji) albo katalog RM_SERWER
      (`rm_serwer.py:79` — `DOMYSLNA_BAZA_MAPOWANIA = <KATALOG>\dane\subiekt_mapowania.sqlite`,
      nadpisywalne kluczem `baza_mapowania` w configu serwera).
      ⚠️ Jeśli są DWA pliki (stacje pisały na `Y:`, serwer ma własny) —
      trzeba je scalić przed przepięciem, inaczej znikną mapowania.
      `subiekt_mapowania.stats()` pokaże liczby wpisów w każdym.
- [ ] Co mają stacje w `C:\RMPAK_CLIENT\sync_config.json` → `paths.master`
      i `paths.projects_dir`? (wystarczy zajrzeć na 2–3 stanowiska)
- [ ] Czy `Y:\RM_BAZA\` w ogóle jeszcze istnieje / jest zapisywalne?

---

## 1. `subiekt_mapowania.py` → przez serwer (operacje `map-`) — GŁÓWNE

**Problem.** Moduł otwiera `sqlite3.connect(<katalog paths.master>/subiekt_mapowania.sqlite)`
bezpośrednio (`subiekt_mapowania.py:43-75`). Ścieżka z configu stacji,
bez podmiany `_na_serwer()`. Stacja ze starym configiem czyta i **pisze**
na `Y:\RM_BAZA\`. Fallback przy braku configu: `Y:\RM_BAZA\subiekt_mapowania.sqlite`.

**Co już jest.** RM_SERWER ma routing `map-` → osobna baza mapowań
(`rm_serwer.py:357-369`, `database_manager.master_read` docstring).
Operacje istniejące: `map-get`, `map-sposob`, `map-po-sposobie`,
`map-statystyki` (`rm_serwer_operacje.py:813+`). Kod RM_BAZA używa ich
w **jednym** miejscu — reszta (7 wywołań) idzie po pliku.

**Wywołania do przepięcia** (poza samym modułem):
- `subiekt_dopasowanie.py:215` — `get_many(kody)`
- `subiekt_dopasowanie.py:332` — `put_many(wpisy, path=...)`
- `subiekt_edytor_gui.py:1284` — `zapisz_scalenie(cel, idCel, zrodla_id)`
- `subiekt_projekt.py:1115` — `put_many(wpisy)`
- plus wewnętrzne: `get`, `delete`, `alias_dla`, `dostawcy_nie_firmy`,
  `dostawca_decyzja`, `ensure_schema*` (schemat ma pilnować serwer,
  jak przy `rm_manager.sqlite`).

**Do zrobienia:**
- [ ] dopisać brakujące operacje w `rm_serwer_operacje.py`
      (`map-get-many`, `map-put`, `map-put-many` jako batch, `map-delete`,
      `map-alias`, `map-scalenie`, `map-dostawcy-*`)
- [ ] `subiekt_mapowania.py`: funkcje publiczne wołają `rm_klient.master_read/exec/batch`,
      `_connect`/`DB_PATH`/`_DB_PATH_FALLBACK` do usunięcia
- [ ] schemat (`ensure_schema`, `ensure_schema_aliasy`, `ensure_schema_dostawcy`)
      przenieść do migracji serwera
- [ ] wskazać serwerowi właściwy plik (`baza_mapowania` w configu serwera)
      — ten z pkt 0, po ewentualnym scaleniu
- [ ] restart RM_SERWER po pullu (nowe operacje + migracja)
- [ ] test: Projekt/Aktualizacja → zasiew (pisze `put_many`), Edytor →
      scalenie, okno dopasowania — na dwóch stacjach naraz

---

## 2. `subiekt_stany.py` → katalog projektów z `db_manager` — MAŁE, BEZPIECZNE

**Problem.** `read_project_drawings()` (`subiekt_stany.py:~331`) otwiera
`paths.projects_dir/project_X.sqlite` — config czytany surowo (`_projects_dir()`,
linie 68-77), **bez** `_na_serwer()`. Arkusz główny przy starym
`projects_dir: Y:/RM_BAZA/projects` sam przepisuje ścieżkę na
`\\W2019S\RM_SERWER$\RM_BAZA_projects` (`RM_BAZA:346`), to okno — nie.
Objaw: okno „Stany Subiekta" (`RM_BAZA:30753`) →
`FileNotFoundError: Y:\RM_BAZA\projects\project_71.sqlite`.
Ten sam błąd był 03.09 na M-OLD, „naprawiony" przez czytanie configu —
ale config w firmie dalej może wskazywać `Y:`.

**Do zrobienia:**
- [ ] `open_window(...)` dostaje katalog z `db_manager.projects_dir`
      (już po `_na_serwer`), a `subiekt_stany` nie czyta configu na własną rękę
- [ ] usunąć `_projects_dir()`, `PROJECTS_DIR`, `_PROJECTS_DIR_FALLBACK`
- [ ] test na stacji ze starym configiem

---

## 3. Porządki (zero ryzyka, po pkt 1–2)

- [ ] `RM_BAZA_v15_MAG_STATS_ORG.py:25959` `_rm_manager_db_path()` — usunąć.
      Martwe: `get_employee_by_user_login()` czyta przez serwer
      (`rmm-employees-po-user-login`), ścieżka ląduje tylko w treści
      komunikatu błędu i wprowadza w błąd przy audycie.
- [ ] `DEFAULT_MASTER_PATH = "Y:/RM_BAZA/master.sqlite"` (`:338`),
      `DEFAULT_LOCKS_DIR = "Y:/RM_BAZA/locks"` (`:342`) — master nie jest
      już otwierany, blokady w tabeli. Zostawić jedynie to, co config
      musi mieć jako kotwicę katalogu (po pkt 1 nie będzie musiał).
- [ ] stary `C:\RMPAK_CLIENT\RM_BAZY\RM_BAZA\sync_config.json` na M-OLD
      (same ścieżki `Y:`, nic go nie czyta) — skasować.
- [ ] komentarze/komunikaty z `Y:` — przejrzeć greppem `Y:` i zostawić
      tylko te, które opisują coś aktualnego.

---

## NIE ruszać (decyzje, nie błędy)

| Miejsce | Dlaczego zostaje |
|---|---|
| `DEFAULT_SERVER_DIR = "Y:/SERVER_PROJEKTY"` (`RM_BAZA:375`) | rysunki (DWF/PDF/DXF) naprawdę tam leżą; serwer CAD nigdzie się nie przeniósł; config ma `server_dir` do nadpisania |
| `client_version.DEFAULT_SERVER_EXE = "Y:/RMPAK_CLIENT/RM_BAZA_v15_MAG.exe"` + `RM_BAZA_v15_MAG.spec:174` kopiuje build na `Y:\RMPAK_CLIENT` | kanał aktualizacji EXE — spójny sam ze sobą; `Y:` musi być zmapowane na stacjach **tylko** do tego. Przeniesienie na `\\W2019S\RM_SERWER$\RMPAK_CLIENT` to osobna decyzja (config ma już klucz `paths.server_exe`) |
| `subiekt_bridge.py:478-490` lista `Y:\...\Subiekt`, `Z:`, `X:`, `V:` | sondowanie kandydatów tylko gdy mostu nie ma lokalnie; brak dysku = jeden `isfile()` |
| `_na_serwer()` (`RM_BAZA:346`) | to jest właśnie mechanizm, który ratuje stacje ze starym configiem — zostaje, dopóki wszystkie configi nie będą poprawione |

---

## Jak sprawdzić po wszystkim

```
grep -n "Y:" *.py | grep -v "^.*#" 
```
powinno zostawić tylko: `DEFAULT_SERVER_DIR`, `client_version.DEFAULT_SERVER_EXE`,
listę kandydatów w `subiekt_bridge.py` i spec.
