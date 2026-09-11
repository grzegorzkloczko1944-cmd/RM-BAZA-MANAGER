# Serwer locków i zapisów do mastera — plan wdrożenia

Dokument wykonawczy. Dwa niezależne etapy, każdy wdrażalny osobno:

| Etap | Robota | Co naprawia |
|---|---|---|
| **A. Locki przez serwer** | 1–2 dni | wyścigi o pliki `.lock`, stale locks, `cleanup` po SMB |
| **B. Zapisy do mastera przez serwer** | 2–3 dni | awarię z 11.09.2026 — u źródła |

Etap B rozwiązuje realny ból; etap A jest tańszy i dobrze rozgrzewa architekturę.
**Można zacząć od B.**

---

## 0. Dlaczego w ogóle

### Co się stało 11.09.2026

`master.sqlite` był zablokowany do zapisu **96–100% czasu przez ponad 40 minut**.
Sześć stanowisk przestało odświeżać sesje o 14:44. Przejęcie/zwolnienie locka
trwało kilkanaście sekund na każdej maszynie.

Mechanizm (udowodniony na bazie tymczasowej, Python 3.14 / sqlite 3.50):

1. `master_con` ma `isolation_level='DEFERRED'` → DML otwiera transakcję i bierze RESERVED.
2. `commit()` pada na „database is locked" (ktoś czytał — po SMB w `journal=delete` to codzienność).
3. **Python NIE cofa transakcji.** Połączenie zostaje `in_transaction=True`
   i trzyma RESERVED **do końca procesu**.
4. Kolejne stanowisko dostaje „locked" przy DML → **też** zostaje z otwartą transakcją,
   a każdy jego SELECT trzyma SHARED → pierwszy nie może zrobić `commit()`.
5. **Zakleszczenie odtwarzające się samo**, dopóki choć jeden klient ma otwartą transakcję.

Doraźnie naprawione (commit `dd66ea3`): `master_commit()` z rollbackiem + siatka
`master_rollback_stuck()`. **To jest opatrunek** — leczy skutek, nie przyczynę.

### Przyczyna źródłowa

**Dziesięć procesów pisze do jednego pliku SQLite przez SMB.** SQLite jest na to
odporny w granicach jednej maszyny; przez sieć blokady plikowe są zawodne, a każdy
błąd zostawia stan, z którego nikt nie sprząta.

Rozwiązanie: **jeden proces posiada plik**, reszta go prosi. To samo, co zrobiliśmy
z Subiektem (`SUBIEKT_STALY_MOST_PLAN.md`) i co tam działa od 06.09.2026.

### Czego ten plan NIE obejmuje

**`project_con` zostaje bez zmian.** Pliki projektów działają dobrze: pod lockiem
kopiujemy je lokalnie (2 ms), pracujemy na kopii, oddajemy przy zwolnieniu. Nie ma
tu współbieżnego pisania, więc nie ma czego naprawiać. 244 wywołania SQL na
`project_con` zostają nietknięte.

Zobacz też: `project_rm_baza_db_model_decision` w pamięci — decyzja „warstwy SQLite
nie refaktorujemy, docelowo HTTP" dotyczy dokładnie tego zakresu.

---

## 1. Architektura

Kopiujemy wzorzec mostu Subiekta — jest sprawdzony i wszyscy go znają.

```
    RM_BAZA (10 stanowisk)
         |
         |  TCP, 4 bajty długości LE + UTF-8 JSON
         v
    RM_SERWER (jeden proces na \\nic)
         |
         |  jedno połączenie SQLite, jeden wątek zapisu
         v
    master.sqlite  +  locks/
```

### Decyzje i ich powody

**TCP + ramka z długością, nie HTTP.** Most Subiekta używa dokładnie tego
(`ServerHost.cs`, `subiekt_bridge.py`): 4 bajty little-endian z długością, potem
JSON. Zero zależności, zero parsowania nagłówków, gotowy kod po obu stronach do
skopiowania. „HTTP" w rozmowie znaczyło „przez serwer, nie przez plik" — i to
dostajemy.

**Jeden wątek wykonujący zapisy.** Wątki TCP tylko wkładają żądania do kolejki.
Dokładnie jak `SferaWorker` w moście. Dzięki temu współbieżność znika z problemu,
a nie jest „obsługiwana".

**Serwer nasłuchuje na LAN, nie na loopbacku.** Tu jedyna różnica wobec mostu
Subiekta: tamten stoi na każdym stanowisku i gada sam ze sobą, ten stoi na
serwerze i obsługuje wszystkich. Wiąże się z tym decyzja o bezpieczeństwie —
sekcja 6.

**Serwer w Pythonie, nie w C#.** Most Subiekta jest w C#, bo musi wołać SDK Sfery.
Tutaj rozmawiamy z SQLite, który Python obsługuje natywnie — a cała logika już
jest w `lock_manager_v2.py` i da się ją przenieść niemal bez zmian.

---

## 2. Protokół

Żądanie i odpowiedź: 4 bajty długości (little-endian) + UTF-8 JSON.

```jsonc
// żądanie
{"cmd": "lock-acquire", "args": {"project_id": 90, "force": false},
 "kto": {"user": "ADMIN", "host": "MONGO", "pid": 1234}}

// odpowiedź
{"ok": true, "data": {"lock_id": "380d3f78-...", "owner": null}}
{"ok": false, "blad": "Projekt zajęty", "data": {"owner": {...}}}
```

`kto` idzie w KAŻDYM żądaniu — serwer nie zgaduje, kto pyta. Z tego biorą się
wpisy właściciela locka i ślad w logu.

`ok: false` to **normalna odpowiedź**, nie wyjątek — „projekt zajęty" to informacja,
nie awaria. Wyjątek leci tylko, gdy serwer jest nieosiągalny.

### Komendy — etap A (locki)

| Komenda | Argumenty | Zwraca |
|---|---|---|
| `lock-acquire` | `project_id`, `force` | `lock_id` albo `owner` zajmującego |
| `lock-release` | `project_id`, `lock_id` | `zwolniony: bool` |
| `lock-owner` | `project_id` | `owner` albo `null` |
| `lock-heartbeat` | `project_id`, `lock_id` | `ok: bool` |
| `lock-list` | — | wszystkie locki (okno „kto co trzyma") |
| `lock-force-delete` | `project_id` | `usuniety: bool` |

### Komendy — etap B (master)

| Komenda | Argumenty | Zwraca |
|---|---|---|
| `master-exec` | `sql`, `params`, `commit` | `rowcount`, `lastrowid` |
| `master-batch` | `operacje: [{sql, params}]` | jak wyżej, **wszystko albo nic** |

`master-batch` jest istotny: „dodaj dostawcę + wpisz do audytu" musi być jedną
transakcją. Dziś to dwa `execute` i jeden `commit`; przez serwer to jedno żądanie.

### Wersja protokołu

Serwer zwraca `protokol` w odpowiedzi na `ping`. Klient zna minimalną zgodną
wersję i przy niezgodności mówi wprost, co zaktualizować — ten sam mechanizm, co
w moście (`_sprawdz_protokol` w `subiekt_bridge.py`).

---

## 3. Etap A — locki

### Stan obecny

`lock_manager_v2.py` (481 linii) czyta i pisze pliki `Y:\RM_BAZA\locks\project_N.lock`.
Reszta programu woła go przez **13 metod**, 92 wywołania. Trzy metody to 65 z nich:

```
32 ×  get_project_lock_owner
21 ×  release_project_lock
12 ×  acquire_project_lock
```

### Co się zmienia

**Tylko wnętrze tych metod.** Zamiast `open(lock_file)` → `_zapytaj("lock-owner", ...)`.
Sygnatury zostają, więc **92 wywołania w GUI są nietknięte**.

```python
# przed
def get_project_lock_owner(self, project_id):
    lock_file = self.locks_folder / f"project_{project_id}.lock"
    if not lock_file.exists():
        return None
    with open(lock_file, 'r', encoding='utf-8') as f:
        return json.load(f)

# po
def get_project_lock_owner(self, project_id):
    odp = rm_klient.zapytaj("lock-owner", {"project_id": project_id})
    return odp.get("owner")
```

### Co znika

- `cleanup_stale_locks()` — serwer sam wie, czyj heartbeat wygasł
- `_release_my_other_locks()` — serwer trzyma mapę `host → locki`
- `_lock_age_seconds()` — czas liczy serwer, nie klient
- Cała obsługa „plik zniknął w trakcie czytania"

Zostaje w pliku, ale wołane wyłącznie w trybie awaryjnym (sekcja 5).

### Zysk

**Lock staje się atomowy.** Dziś dwa stanowiska mogą sprawdzić „wolny" w tej samej
milisekundzie i oba utworzyć plik. Serwer decyduje jeden raz.

---

## 4. Etap B — zapisy do mastera

### Stan obecny

133 wywołania SQL na `master_con`, z czego **17 to DML** (INSERT/UPDATE/DELETE/
ALTER/CREATE). Reszta to odczyty.

Miejsca DML (`RM_BAZA_v15_MAG_STATS_ORG.py`): linie 3170, 3282, 3299, 3334, 3360,
3441, 3521, 20016, 20033, 20040, 23116, 27754 + migracje w `database_manager.py`.

### Co idzie przez serwer

**Tylko zapisy.** Odczyty zostają na bezpośrednim połączeniu — są szybkie
(master ma 360 KB, SELECT to ułamek milisekundy) i nikogo nie blokują.

```python
# przed
self.db_manager.master_con.execute("DELETE FROM suppliers WHERE supplier_id = ?", (sid,))
self.db_manager.master_commit()

# po
self.db_manager.master_zapisz("DELETE FROM suppliers WHERE supplier_id = ?", (sid,))
```

`master_zapisz()` i `master_zapisz_batch()` trafiają do `DatabaseManager` obok
istniejącego `master_commit()`. **17 miejsc do przepisania**, każde to jedna linia.

### Dlaczego to wystarczy

Wisząca transakcja przestaje być możliwa **z definicji**: tylko jeden proces
otwiera transakcje na tym pliku i robi to w jednym wątku, zawsze z `try/finally`.
Klient nie ma jak zostawić czegokolwiek otwartego, bo nie ma własnej transakcji.

### Odczyty — kiedy też przenieść

Gdyby po etapie B nadal zdarzało się „locked" przy odczycie (bo serwer akurat
commituje), wtedy — i tylko wtedy — dokładamy `master-query`. Nie robimy tego
zapobiegawczo: 133 wywołania to dużo roboty za niepewny zysk.

---

## 5. Tryb awaryjny — obowiązkowy

**Serwer nieosiągalny nie może zatrzymać firmy.**

| Etap | Gdy serwer nie odpowiada |
|---|---|
| A (locki) | powrót do plików `.lock` na `Y:` — kod zostaje, tylko nieużywany |
| B (zapisy) | powrót do `master_commit()` (dzisiejsza ścieżka z rollbackiem) |

Przełączenie automatyczne, z jednym ostrzeżeniem w logu (nie w okienku — user nic
z tym nie zrobi). Flaga `_serwer_niedostepny` jak `_most_niedostepny`
w `subiekt_bridge.py`, resetowana przy zmianie ustawień.

⚠️ **Tryb awaryjny locków jest niebezpieczny przy mieszanym stanie**: część
stanowisk na serwerze, część na plikach → wyścig wraca. Dlatego:

**Serwer musi wystartować, zanim ktokolwiek dostanie nowy `.exe`.** Kolejność
wdrożenia w sekcji 8 nie jest kosmetyczna.

---

## 6. Bezpieczeństwo

Most Subiekta słucha na `127.0.0.1` — nie ma prawa wyjść do LAN. Ten serwer musi,
więc:

- **nasłuch na konkretnym interfejsie LAN**, nie `0.0.0.0`
- **reguła zapory**: tylko podsieć firmowa
- **`master-exec` przyjmuje wyłącznie zapytania z listy** — nie dowolny SQL.
  Klient wysyła nazwę operacji + parametry, serwer ma SQL u siebie.
  Inaczej każdy w LAN może wykonać `DROP TABLE`.
- log każdego zapisu: kto, co, kiedy (`C:\RMPAK_CLIENT\rm_serwer_logi\`)

Punkt trzeci warto rozważyć już na etapie A — `lock-force-delete` też jest
operacją, którą trzeba kontrolować.

---

## 7. Pliki

```
rm_serwer.py            serwer: TCP, kolejka, jeden wątek zapisu       ~250 linii
rm_serwer_locki.py      logika locków (przeniesiona z lock_manager_v2)  ~150 linii
rm_serwer_master.py     zapisy do mastera, lista dozwolonych operacji   ~120 linii
rm_klient.py            klient po stronie RM_BAZA (wzorzec subiekt_bridge) ~150 linii

lock_manager_v2.py      ZMIANA: wnętrza 13 metod → rm_klient
database_manager.py     DODANIE: master_zapisz(), master_zapisz_batch()
RM_BAZA_v15_MAG_STATS_ORG.py   ZMIANA: 17 miejsc DML
```

Serwer w repo, wystawiany na `\\nic` — ta sama zasada co most
(`feedback_most_w_gicie`: źródła na `main`, binarka w katalogu dystrybucyjnym).

---

## 8. Kolejność wdrożenia

### Etap B (zalecany pierwszy — leczy dzisiejszy ból)

1. `rm_serwer.py` + `rm_serwer_master.py`, uruchomienie na `\\nic` jako usługa
2. `rm_klient.py` + `master_zapisz()` w `DatabaseManager`
3. Przepisanie 17 miejsc DML
4. **Test u siebie** — RM_BAZA ze źródeł, serwer działa, zapisy przechodzą
5. **Test trybu awaryjnego** — ubić serwer, sprawdzić, czy aplikacja pracuje dalej
6. Build `.exe` → `TESTY RM_BAZA`
7. Jedno stanowisko na próbę (dzień pracy)
8. Publikacja na produkcję + prośba o restart RM_BAZA

### Etap A (locki)

Jak wyżej, z jedną różnicą w kroku 8: **serwer musi być na produkcji, zanim
pójdzie `.exe`** — inaczej część stanowisk trafi do trybu awaryjnego i wyścig
o pliki `.lock` wróci (sekcja 5).

---

## 9. Testy, które muszą przejść

**Etap A:**
- dwa stanowiska proszą o ten sam lock w tej samej sekundzie → jedno dostaje
- stanowisko ginie (kill procesu) → lock wygasa po heartbeacie, nie wisi
- serwer ubity w trakcie pracy → tryb awaryjny, praca trwa
- `force` odbiera lock, poprzedni właściciel dowiaduje się przy najbliższej operacji

**Etap B:**
- 10 równoczesnych zapisów z różnych maszyn → wszystkie przechodzą, żaden nie ginie
- `master-batch` przerwany w połowie → nic nie zostaje zapisane
- serwer ubity w trakcie zapisu → klient dostaje błąd, nie cichą stratę
- **stary klient (obecny `.exe`) i nowy pracują równolegle** → to stan przejściowy
  podczas wdrożenia, musi działać
- po tygodniu: `master.sqlite` ani razu nie zablokowany dłużej niż sekundę

---

## 10. Czego ten plan nie rozwiązuje

- **`project_con`** — zostaje na plikach, świadomie (sekcja 0)
- **`rm_manager.sqlite`** — RM_MANAGER ma własną warstwę, osobny temat
- **Bramka wersji** — nadal działa tylko przy starcie; kto ma otwarte, nie zobaczy
  monitu. Przy wdrożeniu trzeba powiedzieć ludziom „zrestartujcie".
- **Backup mastera** — dziś robi go klient przy zwalnianiu locka. Docelowo powinien
  robić serwer (ma plik na wyłączność), ale to osobna zmiana.

---

## 11. Kontekst

| Dokument / pamięć | Co zawiera |
|---|---|
| `SUBIEKT_STALY_MOST_PLAN.md` | wzorzec architektury, protokół, dystrybucja |
| `subiekt_sfera/NexoRecon/ServerHost.cs` | gotowy kod serwera TCP + kolejka |
| `subiekt_bridge.py` | gotowy kod klienta, fallback, wersjonowanie protokołu |
| `project_master_stuck_transaction` | przyczyna awarii 11.09 i sposób diagnozy |
| `project_rm_baza_db_model_decision` | decyzja o zakresie: HTTP docelowo, bez refaktoru SQLite |
| `project_master_journal_delete` | dlaczego `journal=delete`, a nie WAL po SMB |
| `feedback_most_w_gicie` | zasada: źródła w gicie, binarka osobno |

---

*Przygotowane 11.09.2026, po awarii mastera tego dnia.*
