---
name: project_rm_serwer_etap25_domkniecie
description: "Etap 1+2.5 domknięty 11.09.2026 — RM_BAZA i RM_MANAGER nie otwierają już głównych baz z pliku; routing trzech baz, HMAC włączony, okno konfiguracji serwera przy starcie"
metadata:
  type: project
---

**11.09.2026 zamknięty etap 1 i 2.5**: żaden moduł produkcyjny nie otwiera już
`master.sqlite` ani `rm_manager.sqlite` z pliku — wszystko idzie przez
RM_SERWER ([[project_rm_serwer_wdrozenie]], [[project_rm_serwer_plan]]).

**Trzy bazy na serwerze**, routing po prefiksie operacji: `map-` →
`subiekt_mapowania.sqlite`, `rmm-` → `rm_manager.sqlite`, reszta →
`master.sqlite`. Tabela `_server_request_log` (idempotencja) musi istnieć
w **każdej** bazie.

**HMAC włączony.** Sekret w `rm_serwer_config.json` na serwerze i w
`sync_config.json` u klientów; oba w `.gitignore`, nigdy nie trafiają do repo.
Sekretu **nie da się pobrać z serwera** — chroni właśnie to połączenie.

RM_BAZA przy starcie pokazuje **okno konfiguracji serwera** (host, port,
sekret, ścieżka do wspólnego JSON-a) zamiast zgadywania; ścieżka do wspólnego
pliku zapisuje się userowi, bo stacje mają różnie pomapowane dyski.

**Why:** „pół tutaj, pół tutaj" było źródłem rozjazdów — dopóki cokolwiek
czytało stary plik, dane i blokady żyły w dwóch miejscach naraz.

**How to apply:**
- Nowy odczyt/zapis głównej bazy = **nowa nazwana operacja** w
  `rm_serwer_operacje.py`, nigdy SQL od klienta (par. 3 planu). Dynamiczne
  `IN (...)` przez `json_each(?)`, częściowa edycja przez `COALESCE(?, kol)`
  — ale NIE tam, gdzie NULL musi być zapisywalny (np. `working_days`
  wyjazdu, decyzje o nieobecności, pełny zapis pracownika).
- Wielokrokowy zapis = jeden `master_batch` (jedna transakcja).
- `_reconnect_master_rw()` w RM_MANAGER GUI zwraca **atrapę**: `commit()`,
  `rollback()` i `close()` przechodzą, a surowy `execute()` rzuca
  `RuntimeError`. Funkcje z `project_manager` ignorują parametr `con`.
- `os.path.exists(master_db_path)` jako warunek = **błąd**: bez `Y:` blokuje
  poprawną ścieżkę. Wszystkie takie guardy usunięte.
- Bazy **projektowe** (`project_<id>.sqlite`, `rm_manager_project_<id>.sqlite`)
  to nadal pliki — etap 2, poza zakresem.
- Skrypty konsolowe muszą najpierw zawołać `rm_manager._master()`, żeby
  skonfigurować `rm_klient`; w GUI robi to RM_BAZA przy starcie.
- Zostało odłożone: `DatabaseManager` w RM_BAZA otwiera `Y:` read-only na
  starcie (nieszkodliwe), publikacja testowego `.exe` na produkcję, katalog
  `serwer/` z dokumentacją NSSM w repo, `rm_database_manager.py` = martwy kod.
