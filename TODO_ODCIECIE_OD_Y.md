# TODO — odcięcie RM_BAZA od dysku `Y:` (do zrobienia w firmie, na żywym organizmie)

Stan na 14.09.2026 (audyt z M-OLD). Kod pracuje przez RM_SERWER i UNC
`\\W2019S\RM_SERWER$`, ale zostały miejsca, które **otwierają pliki
bezpośrednio** po ścieżce z `sync_config.json` stacji — a stacje mają
configi sprzed przenosin (`Y:/RM_BAZA/...`). Na M-OLD tego nie widać, bo
tam config jest poprawiony ręcznie. W firmie trzeba to sprawdzić na
prawdziwej stacji, z prawdziwym configiem.

Kolejność: pkt 0 (ustalenia) → 2 (bezpieczne) → 1 (główne) → 3 (porządki).

**Stan 14.09.2026 (w firmie, stacja GKI/MONGO): pkt 0 ustalony, pkt 1 zakodowany
i przetestowany lokalnie — czeka na wdrożenie serwera + build .exe. Zostały pkt 2 i 3.**

---

## 0. Do ustalenia PRZED zmianami — ✅ USTALONE 14.09.2026 (w firmie)

- [x] **Gdzie leży `subiekt_mapowania.sqlite`?** Na serwerze,
      `C:\Apps\RM_SERWER\dane\` (domyślna ścieżka, `baza_mapowania` nie
      nadpisane). `map-statystyki` przez TCP: **859 auto, 2 reczny, 2 zalozona
      = 863** — identycznie ze starym `Y:\RM_BAZA\$subiekt_mapowania.sqlite`
      (ostatni wpis 10.09 14:01). Jeden plik, **nic do scalania**.
- [x] Config stacji GKI: `paths.master = Y:/RM_BAZA/master.sqlite`,
      `paths.projects_dir = \\W2019S\RM_SERWER$\RM_BAZA_projects`. Litera
      udziału różni się między stacjami (W:/U: dominują), cel fizyczny ten sam.
- [x] `Y:\RM_BAZA\` **ISTNIEJE** (poprzedni wpis pisany z M-OLD, gdzie nie
      widać): zawartość przemianowana na `$nazwa`. Dziś rano dwa stare buildy
      założyły tam `master.sqlite` (tylko `rfq_tags`) i `locks\` — bramka
      wersji milczy poza `Y:` (pamięć `project_autoaktualizacja_exe`).
- [x] Test rozstrzygający: `DB_PATH = Y:/RM_BAZA\subiekt_mapowania.sqlite`,
      `stats() = {'razem': 0}` → **wariant 1** (pliku nie ma). Ale **bez
      strat**: każdy zapis założyłby plik (`ensure_schema` → `connect`), a
      pliku nie ma → od 12.09 nikt nic nie zapisał. Rozjazd był zagrożeniem
      przy pierwszym zapisie, nie faktem. Koszt: odczyty `{}` → w dopasowaniu
      nie działała reguła A „zapamiętane" (2 ręczne wpisy wracały do decyzji).

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

**Zrobione 14.09.2026** (test na lokalnym RM_SERWER z kopią produkcyjnych
863 wpisów: 47 asercji, 0 błędów; `put_many` 1203 wpisów w 0,08 s;
integracja `przygotuj_pozycje` OK). Korekta do „Co już jest": klient nie
używał `map-*` w **żadnym** miejscu — wszystkie 7+ wywołań szło po pliku.
- [x] serwer: `map-get-many` (lista jako JSON → `json_each`, bez limitu 999
      zmiennych), `map-przepnij-symbol`, `map-odrzuc`, `map-odrzucone-lista`;
      `map-put` z regułą „ręczne ma pierwszeństwo" **w SQL** (`DO UPDATE … WHERE`,
      odrzucony wpis = rowcount 0); `map-dostawca-decyzja` → UPSERT;
      `map-dostawcy-nie-firmy` szuka `'nie-firma'` (było `'nie_firma'` — nigdy
      nie trafiało). `put_many` = `master-batch` z `map-put` (paczki po 500),
      scalenie = jeden batch (alias + przepięcie + wpis scalona), wszystko albo nic.
- [x] `subiekt_mapowania.py`: tylko `rm_klient`; `_connect`/`DB_PATH`/
      `_DB_PATH_FALLBACK`/`ensure_schema*`/`_lock` usunięte. Błędy = `BladSerwera`,
      bez cichego `{}` — to cisza ukryła martwe mapowania. `path=` ignorowany.
- [x] `subiekt_dopasowanie.py`: odrzucenia (`wczytaj_odrzucone`/`odrzuc`) też
      przez serwer; `_polacz`/`_DDL_ODRZUCONE` usunięte.
- [x] schemat w migracjach serwera; `odrzucone_dopasowania` wyrównane do
      schematu KLIENTA `(klucz_rm, id_subiekt, symbol)` — pierwotna migracja
      miała `(numer_rysunku, symbol_subiekt)`; produkcja ma kliencki (plik
      z Y:), M-OLD dostał pusty zły → `napraw_odrzucone_dopasowania` (pusta →
      drop, z danymi → `_stare`) wołana przed migracjami.
- [x] `baza_mapowania` — serwer już wskazuje właściwy plik, nic do zmiany.
- [ ] **wdrożenie, w tej kolejności**: (1) `rm_serwer.py` + `rm_serwer_operacje.py`
      na W2019S (`Copy-Item -ToSession` po IP 192.168.100.84) +
      `Restart-Service RM_SERWER` — stary klient plikowy tego nie zauważy;
      (2) build `.exe` — nowy klient WYMAGA nowych operacji, więc nigdy przed (1).
- [ ] test na produkcji: Projekt/Aktualizacja → zasiew (`put_many`), Edytor →
      scalenie, okno dopasowania (Odepnij), Dostawcy (nie firma) — dwie stacje naraz

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
| ~~`subiekt_bridge.py` lista `Y:\...\Subiekt`, `Z:`, `X:`, `V:`~~ | **ZROBIONE 14.09.2026** — „Pobierz most" czyta z `\\W2019S\RM_SERWER$\MOST` (`udzial_serwera.UDZIAL`), litery dysków usunięte; stary `paths.bridge_dir` z configu stacji (`Y:\RMPAK_CLIENT\iLogic\Subiekt`) jest pomijany. Most `62f2f36` wystawiony na serwerze; `Y:\...\MOST` już NIE jest aktualizowane — stare `.exe` pobiorą nowy most dopiero po buildzie RM_BAZA |
| `_na_serwer()` (`RM_BAZA:346`) | to jest właśnie mechanizm, który ratuje stacje ze starym configiem — zostaje, dopóki wszystkie configi nie będą poprawione |

---

## Jak sprawdzić po wszystkim

```
grep -n "Y:" *.py | grep -v "^.*#" 
```
powinno zostawić tylko: `DEFAULT_SERVER_DIR`, `client_version.DEFAULT_SERVER_EXE`
i spec (lista kandydatów mostu w `subiekt_bridge.py` zniknęła 14.09.2026).
