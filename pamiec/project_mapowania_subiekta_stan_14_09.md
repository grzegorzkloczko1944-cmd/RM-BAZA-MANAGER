---
name: project_mapowania_subiekta_stan_14_09
description: "Mapowania Subiekta 14.09.2026: serwer ma komplet 863, klient wciąż otwiera plik na Y: (nie istnieje) i NIE woła map-*; zero utraconych zapisów, ryzyko = pierwszy zapis tworzy rozjazd"
metadata:
  type: project
---

Stan sprawdzony na stacji w firmie 14.09.2026 (audyt pkt 0 z
`TODO_ODCIECIE_OD_Y.md` — sam TODO był pisany z M-OLD i przesadził):

- `subiekt_mapowania.DB_PATH` = `<paths.master z sync_config>\..\subiekt_mapowania.sqlite`
  → `Y:/RM_BAZA\subiekt_mapowania.sqlite`, **plik nie istnieje**
  (stary przemianowany na `$subiekt_mapowania.sqlite`, 863 wpisy, ostatni 10.09 14:01).
- **RM_SERWER ma komplet**: `map-statystyki` = 859 auto, 2 reczny
  (`151687`, `6004RS → 6004 ZZ`), 2 zalozona — identycznie ze starym plikiem.
  Tabele `aliasy_scalen` i `dostawcy_decyzje` puste (na Y: nigdy nie istniały).
- **Zero utraconych zapisów** — dowód: każdy zapis idzie przez `ensure_schema`
  → `sqlite3.connect(p)`, co założyłoby plik. Brak pliku = nikt nie pisał.
- Odczyty zwracają `{}` → w dopasowaniu nie działa reguła A „zapamiętane";
  859 auto odnajduje się regułą B, 2 ręczne wrócą jako „do decyzji".
- **Klient NIE woła żadnej operacji `map-*`** (grep: zero, TODO mówił „jedno").
  Serwer ma: `map-get/sposob/po-sposobie/statystyki/wszystkie/alias/
  dostawcy-nie-firmy` (odczyt) i `map-put/delete/alias-dodaj/
  dostawca-decyzja[-usun]` (zapis). Brakuje `put-many` (batch) i `scalenie`.

**Why:** ryzyko nie jest w danych, tylko w PIERWSZYM zapisie: założy świeży
pusty plik na udziale i od tej chwili stacje piszą tam, serwer stoi — cichy
rozjazd. Litera dysku nie ma znaczenia (wszystkie stacje trafiają w ten sam
katalog NAS), ale po przepięciu na serwer w ogóle przestaje istnieć.

**How to apply:** pkt 1 TODO (klient przez `rm_klient.master_read/exec/batch`,
`_connect`/`DB_PATH` do usunięcia, schemat pilnuje serwer) zrobić ZANIM ktoś
scali kartoteki albo dopasuje ręcznie. Patrz [[project_autoaktualizacja_exe]],
[[project-odciecie-od-y]], [[project_subiekt_scalanie_kartotek]].

**ZROBIONE 14.09.2026, commit `62f2f36` (nie wypchnięty), serwer wdrożony 12:04:**
klient (`subiekt_mapowania`, odrzucenia w `subiekt_dopasowanie`) idzie WYŁĄCZNIE
przez `rm_klient` i operacje `map-*`; serwer ma `map-get-many` (JSON → `json_each`),
`map-przepnij-symbol`, `map-odrzuc`, `map-odrzucone-lista`, `map-put` z regułą
„ręczne ma pierwszeństwo" w SQL, `map-dostawca-decyzja` UPSERT, `'nie-firma'`.
Wdrożenie = `Copy-Item -ToSession` dwóch plików + `Restart-Service` (backupy
`*.bak_20260914_120421` w C:/Apps/RM_SERWER). Pułapka: serwerowy `rm_serwer.py`
miał poprawkę spoza gita (log złego HMAC) — przed nadpisaniem ZAWSZE `diff`
pobranej kopii z repo. **Zostało: build `.exe`** — stacje na starym buildzie
wciąż liczą mapowania z nieistniejącego pliku (odczyty `{}`), do nowego builda
poprawka do nich nie dociera. Autoaktualizacji nie ruszać (decyzja użytkownika).
