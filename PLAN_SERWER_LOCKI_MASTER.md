# Serwer locków i mastera — plan wdrożenia

Dokument wykonawczy. Wersja 2 (11.09.2026) — po recenzji wersji 1.

| Etap | Robota | Co naprawia |
|---|---|---|
| **B. Master przez serwer** | 3–4 dni | awarię z 11.09.2026 — u źródła |
| **A. Locki przez serwer** | 1–2 dni | wyścigi o pliki `.lock`, stale locks |

**Kolejność: B, potem A.** B leczy realny ból; A jest tańszy, ale naprawia problem,
którego 11.09 nie było.

> **Zmiany wobec wersji 1** (wszystkie z recenzji): klienci **nie otwierają**
> master.sqlite — także do odczytu (§4); **nie ma** automatycznego fallbacku
> per-klient (§6); `request_id` przeciw duplikatom po zerwanym TCP (§3);
> lease z TTL i `server_epoch` zamiast gołego heartbeatu (§5); `master-exec`
> przyjmuje **nazwane operacje**, nigdy SQL (§3, §8); backup mastera przechodzi
> na serwer w etapie B (§4); token HMAC w każdym żądaniu (§8).

---

## 0. Dlaczego

### Co się stało 11.09.2026

`master.sqlite` zablokowany do zapisu **96–100% czasu przez ponad 40 minut**.
Sześć stanowisk przestało odświeżać sesje o 14:44. Przejęcie/zwolnienie locka —
kilkanaście sekund na każdej maszynie.

Mechanizm (udowodniony na bazie tymczasowej, Python 3.14 / sqlite 3.50):

1. `master_con` ma `isolation_level='DEFERRED'` → DML otwiera transakcję, bierze RESERVED.
2. `commit()` pada na „database is locked" (ktoś czytał — po SMB w `journal=delete` to codzienność).
3. **Python NIE cofa transakcji.** Połączenie zostaje `in_transaction=True`
   i trzyma RESERVED **do końca procesu**.
4. Kolejne stanowisko dostaje „locked" przy DML → **też** zostaje z otwartą transakcją,
   a każdy jego SELECT trzyma SHARED → pierwszy nie może zrobić `commit()`.
5. **Zakleszczenie odtwarzające się samo**, dopóki choć jeden klient ma otwartą transakcję.

Doraźnie naprawione (`dd66ea3`): `master_commit()` z rollbackiem + siatka
`master_rollback_stuck()`. **To opatrunek** — leczy skutek, nie przyczynę.

### Przyczyna źródłowa

**Dziesięć procesów otwiera jeden plik SQLite przez SMB.** Nie tylko pisze —
**otwiera**. Czytelnik trzymający SHARED potrafi zablokować commit pisarza; pisarz
z wiszącą transakcją blokuje wszystkich.

Rozwiązanie: **jeden proces posiada plik, reszta go prosi.** To samo, co zrobiliśmy
z Subiektem (`SUBIEKT_STALY_MOST_PLAN.md`), działa od 06.09.2026.

### Docelowa zasada

```
            master.sqlite
                  ↑
          TYLKO RM_SERWER

  RM_BAZA ──TCP──► RM_SERWER ──► master.sqlite
```

Klient **nie ma** połączenia z tym plikiem. Żadnego — ani do zapisu, ani do odczytu,
ani do backupu. Dopóki ma, przyczyna źródłowa istnieje.

### Czego plan NIE obejmuje

**`project_con` zostaje bez zmian.** Pliki projektów działają dobrze: pod lockiem
kopiujemy je lokalnie (2 ms), pracujemy na kopii, oddajemy przy zwolnieniu. Nie ma
współbieżnego pisania, nie ma czego naprawiać. **244 wywołania SQL nietknięte.**

Zobacz `project_rm_baza_db_model_decision` w pamięci — decyzja „warstwy SQLite nie
refaktorujemy" dotyczy dokładnie tego zakresu.

---

## 1. Architektura

Wzorzec mostu Subiekta — sprawdzony, wszyscy go znają.

```
    RM_BAZA (10 stanowisk)
         |
         |  TCP, 4 bajty długości LE + UTF-8 JSON + HMAC
         v
    RM_SERWER (jeden proces na \\nic)
         |
         |  jedno połączenie SQLite, jeden wątek zapisu
         v
    master.sqlite  +  locks/  +  backups/
```

### Decyzje i powody

**TCP + ramka z długością, nie HTTP.** Most Subiekta używa dokładnie tego
(`ServerHost.cs`, `subiekt_bridge.py`): 4 bajty little-endian + JSON. Zero
zależności, gotowy kod po obu stronach. „HTTP" w rozmowie znaczyło „przez serwer,
nie przez plik" — i to dostajemy.

**Jeden wątek wykonujący operacje na bazie.** Wątki TCP tylko wkładają żądania do
kolejki — jak `SferaWorker` w moście. Współbieżność **znika z problemu**, zamiast
być obsługiwana.

**Serwer w Pythonie.** Most jest w C#, bo woła SDK Sfery. Tu rozmawiamy z SQLite,
który Python obsługuje natywnie — a logika locków już istnieje w `lock_manager_v2.py`.

**Nasłuch na LAN.** Jedyna różnica wobec mostu (tamten: `127.0.0.1`). Stąd
autoryzacja — §8.

---

## 2. Kontrakt: kto dotyka pliku

| | Dziś | Po etapie B |
|---|---|---|
| Zapisy do mastera | 10 klientów | **serwer** |
| Odczyty z mastera | 10 klientów | **serwer** |
| Migracje / PRAGMA | 10 klientów | **serwer** (przy starcie) |
| Backup mastera | klient przy zwalnianiu locka | **serwer** |
| Pliki projektów | klient (kopia lokalna) | klient — bez zmian |

Po etapie B `DatabaseManager.master_con` **przestaje istnieć**. To jest test
kompletności: dopóki pole istnieje, ktoś może go użyć.

---

## 3. Protokół

Ramka: 4 bajty długości (LE) + UTF-8 JSON.

```jsonc
// żądanie
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "cmd": "supplier-delete",
  "args": {"supplier_id": 123},
  "kto":  {"user": "ADMIN", "host": "MONGO", "pid": 1234},
  "hmac": "9f2c…"
}

// odpowiedź
{"ok": true,  "request_id": "550e8400-…", "data": {"rowcount": 1}}
{"ok": false, "request_id": "550e8400-…", "blad": "Projekt zajęty",
               "data": {"owner": {...}}}
```

`ok: false` to **normalna odpowiedź**, nie wyjątek — „projekt zajęty" to informacja.
Wyjątek leci tylko, gdy serwer jest nieosiągalny.

### request_id — obowiązkowy przy każdej operacji zmieniającej

Bez niego przy zerwanym TCP po commicie klient nie wie, czy zapis przeszedł:

```
klient  → supplier-add
serwer  → INSERT + COMMIT  ✓
serwer  → odpowiedź ──X──  zerwane TCP
klient  → ponawia → DRUGI DOSTAWCA
```

Serwer trzyma `{request_id: odpowiedź}` przez 10 minut. Powtórzone żądanie
**nie wykonuje operacji** — zwraca zapamiętany wynik z `powtorzone: true`.
Klient generuje `request_id` **raz na operację**, nie raz na próbę.

Dotyczy: wszystkich `*-add/-edit/-delete`, `lock-acquire`, `lock-release`.
Odczyty są idempotentne, więc ich nie obejmuje.

### Nazwane operacje, nigdy SQL

Klient **nie wysyła SQL**. Wysyła nazwę operacji + parametry; SQL istnieje
wyłącznie w serwerze:

```python
# ŹLE — dowolny SQL z LAN
master_exec(sql="DELETE FROM suppliers WHERE supplier_id=?", params=(123,))

# DOBRZE
master_exec(operation="supplier-delete", params={"supplier_id": 123})
```

Dotyczy też `master-batch`: lista **nazwanych** operacji, nie tablica SQL-i.

### Komendy — etap B (master)

| Komenda | Argumenty | Zwraca |
|---|---|---|
| `master-read` | `operation`, `params` | wiersze |
| `master-exec` | `operation`, `params`, `request_id` | `rowcount`, `lastrowid` |
| `master-batch` | `operacje: [{operation, params}]`, `request_id` | **wszystko albo nic** |
| `ping` | — | `protokol`, `server_epoch`, `uptime` |

`master-batch` jest konieczny: „dodaj dostawcę + wpis do audytu" to jedna
transakcja. Dziś dwa `execute` i jeden `commit`.

**Lista operacji do zbudowania** (z inwentaryzacji kodu):

- odczyt: `suppliers-list`, `supplier-get`, `stage-definitions`, `material-prices`,
  `users-list`, `projects-list`, `project-get`, `settings-get`, `sessions-list`
- zapis: `supplier-add`, `supplier-edit`, `supplier-delete`, `supplier-tags-set`,
  `user-add`, `user-edit`, `user-delete`, `user-audit-add`, `settings-set`,
  `session-heartbeat`, `session-close`, `project-status-sync`, `zd-zamowione-*`

### Komendy — etap A (locki)

| Komenda | Argumenty | Zwraca |
|---|---|---|
| `lock-acquire` | `project_id`, `force`, `request_id` | `lock_id`, `expires_at`, `server_epoch` |
| `lock-release` | `project_id`, `lock_id`, `request_id` | `zwolniony` |
| `lock-heartbeat` | `project_id`, `lock_id` | `expires_at`, `server_epoch` |
| `lock-owner` | `project_id` | `owner` albo `null` |
| `lock-list` | — | wszystkie locki |
| `lock-force-delete` | `project_id`, `request_id` | `usuniety` |

### Wersja protokołu

`ping` zwraca `protokol`. Klient zna minimalną zgodną wersję i przy niezgodności
mówi wprost, co zaktualizować — mechanizm z `subiekt_bridge._sprawdz_protokol`.

---

## 4. Etap B — master

### Stan obecny

133 wywołania SQL na `master_con`:

| | ile | uwaga |
|---|---|---|
| DML (INSERT/UPDATE/DELETE/ALTER/CREATE) | **17** | zapisy |
| SELECT | **8** | 5× suppliers, stage_definitions, sqlite_master, material_prices |
| PRAGMA | **27** | migracje i introspekcja, głównie przy starcie |
| reszta | ~81 | w `database_manager.py`: łączenie, testy, konfiguracja |

**To mniej, niż się wydaje.** Odcięcie klientów od pliku to kilkanaście realnych
miejsc, nie setki — dlatego robimy je **od razu**, a nie „kiedyś".

### Co się zmienia

```python
# przed
self.db_manager.master_con.execute(
    "DELETE FROM suppliers WHERE supplier_id = ?", (sid,))
self.db_manager.master_commit()

# po
self.db_manager.master_exec("supplier-delete", {"supplier_id": sid})
```

```python
# przed
rows = self.db_manager.master_con.execute(
    "SELECT supplier_id, name FROM suppliers ORDER BY name").fetchall()

# po
rows = self.db_manager.master_read("suppliers-list")
```

`master_read`, `master_exec`, `master_batch` w `DatabaseManager` **zastępują**
`master_con`. Pole znika — patrz §2.

### Migracje schematu

Dziś każdy klient przy starcie sprawdza i dokłada kolumny (27 PRAGMA). Po zmianie
robi to **serwer przy starcie, raz**. Klient nie ma prawa zmieniać schematu.

Efekt uboczny, mile widziany: znikają logi `⚠️ Nie udało się dodać kolumny
'subiekt_symbol': attempt to write a readonly database`.

### Backup mastera — przechodzi na serwer

Dziś robi go klient przy zwalnianiu locka (`backup_manager.backup_master`).
Skoro ustanawiamy jednego właściciela pliku, klient nie ma jak zrobić spójnej kopii
— i nie powinien próbować.

```
RM_SERWER
   ├─ posiada master.sqlite
   ├─ backup (SQLite Online Backup API — spójny, bez blokowania)
   └─ rotacja: ostatnie 20 kopii
```

Wyzwalacz: raz dziennie + po N zapisach. Klient **nie dotyka** backupu mastera.
Backupy projektów zostają po stronie klienta — to inne pliki.

### Dlaczego to usuwa przyczynę

Nie „z definicji" — konkretnie: **żaden klient nie ma otwartego połączenia z tym
plikiem**, więc nie ma kto trzymać SHARED ani zostawić wiszącej transakcji. Serwer
ma jedno połączenie, jeden wątek i `try/finally` wokół każdej transakcji.

Zostaje jedno ryzyko: **awaria samego serwera** — §6.

---

## 5. Etap A — locki jako lease

### Stan obecny

`lock_manager_v2.py` (481 linii) czyta i pisze `Y:\RM_BAZA\locks\project_N.lock`.
Reszta programu woła **13 metod**, 92 wywołania. Trzy metody to 65 z nich:
`get_project_lock_owner` (32), `release_project_lock` (21), `acquire_project_lock` (12).

### Co się zmienia

**Tylko wnętrza metod.** Sygnatury zostają → **92 wywołania w GUI nietknięte.**

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
    return rm_klient.zapytaj("lock-owner", {"project_id": project_id}).get("owner")
```

### Lease, nie „lock z heartbeatem"

```
TTL locka:   90 s
heartbeat:   co 20 s   (4 szanse na dojście)
brak heartbeatu przez 90 s → lock wygasa, serwer oddaje go następnemu
```

Struktura locka po stronie serwera:

```jsonc
{
  "project_id": 90,
  "lock_id": "380d3f78-…",     // UUID, wymagany przy release i heartbeat
  "owner": {"user": "ADMIN", "host": "MONGO", "pid": 1234},
  "acquired_at": "2026-09-11T15:47:07",
  "expires_at":  "2026-09-11T15:48:37",
  "server_epoch": "a1b2c3d4"
}
```

**`release` i `heartbeat` wymagają właściwego `lock_id`.** Bez tego spóźniony
klient zwalnia lock, który należy już do kogoś innego — i dwie osoby piszą do
jednego projektu.

### server_epoch — restart serwera

Krytyczne przy naszym modelu: klient bierze lock, **kopiuje projekt lokalnie**,
pracuje na kopii i nadpisuje plik przy zwolnieniu. Gdyby serwer zapomniał locki po
restarcie, drugi użytkownik dostałby ten sam projekt — i jedna praca przepadłaby
bez śladu.

Serwer generuje `server_epoch` przy każdym starcie. Klient zapamiętuje go przy
przejęciu locka i porównuje przy każdym heartbeacie:

```
klient:  epoch = ABC, lock_id = 123
serwer:  epoch = XYZ            ← serwer wstał na nowo

→ ⛔ UTRACONO LOCK PROJEKTU
→ zapis na serwer ZABRONIONY
→ oferta: zapisz kopię awaryjną do C:\RMPAK_CLIENT\awaria\
```

Ta sama reakcja, gdy `lock-heartbeat` zwróci `ok: false` (lock wygasł albo ktoś
użył `force`). Kod na to już częściowo istnieje — `release_lock` sprawdza, czy
lock nadal nasz, i wywołuje `_force_cancel_lock_on_lost`.

Serwer zapisuje stan locków na dysk przy każdej zmianie, więc **restart nie musi**
ich gubić. `server_epoch` to zabezpieczenie na wypadek, gdy jednak zgubi
(uszkodzony plik, ręczne czyszczenie).

### Co znika z klienta

`cleanup_stale_locks()`, `_release_my_other_locks()`, `_lock_age_seconds()`
i obsługa „plik zniknął w trakcie czytania". Wszystko to wie teraz serwer.

---

## 6. Awaria serwera — bez cichego powrotu do SMB

**Nie ma automatycznego fallbacku per-klient.** To była najgroźniejsza wada wersji 1:

```
PC1 → serwer działa      ─┐
PC2 → timeout → SMB      ─┼─► dwóch właścicieli zapisu = stan sprzed wdrożenia
PC3 → serwer działa      ─┘
```

Zamiast tego:

| Co | Zachowanie przy braku serwera |
|---|---|
| Odczyty z mastera | z **lokalnego cache** (ostatni znany stan, oznaczony jako nieświeży) |
| Zapisy do mastera | **zablokowane** — komunikat „serwer niedostępny, spróbuj za chwilę" |
| Locki | **nie można przejąć**; już przejęty działa do wygaśnięcia TTL |
| Praca na projekcie | trwa — kopia jest lokalna |
| Zwolnienie locka | plik projektu idzie na `Y:` normalnie (to nie master) |

**Minuta bez możliwości edycji jest lepsza niż cichy powrót do architektury, która
spowodowała 40-minutowe zakleszczenie.**

### Żeby ta minuta była minutą

- serwer jako **usługa Windows** z auto-restartem (`sc failure … restart/5000`)
- watchdog: jeśli nie odpowiada na `ping` 30 s → restart usługi
- log niedostępności + jeden komunikat w GUI (nie przy każdym kliknięciu)

### Tryb legacy — tylko ręcznie

Gdyby serwer padł na dłużej (awaria maszyny), administrator przełącza
**cały system** wpisem w `sync_config.json` na `Y:`:

```json
{"rm_serwer": {"tryb": "legacy", "powod": "awaria nic, 11.09 16:00"}}
```

Klienci czytają to przy starcie i **wszyscy naraz** wracają na SMB. To jest
świadoma decyzja człowieka, nie skutek uboczny timeoutu.

---

## 7. Pliki

```
rm_serwer.py            TCP, kolejka, jeden wątek, HMAC, request_id     ~300 linii
rm_serwer_master.py     nazwane operacje + migracje + backup            ~250 linii
rm_serwer_locki.py      lease, TTL, server_epoch                        ~180 linii
rm_klient.py            klient (wzorzec subiekt_bridge)                 ~180 linii

lock_manager_v2.py      ZMIANA: wnętrza 13 metod → rm_klient
database_manager.py     ZMIANA: master_con → master_read/exec/batch
backup_manager.py       ZMIANA: backup_master() znika z klienta
RM_BAZA_v15_MAG_STATS_ORG.py   ZMIANA: 17 DML + 8 SELECT
```

Serwer w repo, wystawiany na `\\nic` — zasada z `feedback_most_w_gicie`.

---

## 8. Bezpieczeństwo

Most Subiekta słucha na `127.0.0.1`. Ten musi na LAN, więc:

**Token HMAC w każdym żądaniu.** Samo `"kto": {"user": "ADMIN"}` nie uwierzytelnia
nikogo — dowolny klient w LAN napisze, że jest ADMIN, i wywoła `lock-force-delete`.

```
sekret:   plik na Y: czytelny tylko dla grupy RM_BAZA
hmac:     HMAC-SHA256(sekret, request_id + cmd + json(args))
serwer:   odrzuca żądanie bez poprawnego HMAC
```

To nie kryptografia wojskowa — to bariera przeciw przypadkowi i ciekawskiemu
skryptowi. Wystarczy.

**Pozostałe:**
- nasłuch na konkretnym interfejsie LAN, nie `0.0.0.0`
- reguła zapory: tylko podsieć firmowa
- **żadnego SQL od klienta** — wyłącznie nazwane operacje (§3)
- log każdego zapisu: kto, co, kiedy → `C:\RMPAK_CLIENT\rm_serwer_logi\`
- `lock-force-delete` i operacje na users: dodatkowo rola ADMIN sprawdzana
  **po stronie serwera**, nie w GUI

---

## 9. Kolejność wdrożenia

### Etap B

1. `rm_serwer.py` + `rm_serwer_master.py` — lista operacji, migracje, backup
2. Usługa Windows na `\\nic` + auto-restart + watchdog
3. `rm_klient.py` + `master_read/exec/batch` w `DatabaseManager`
4. Przepisanie 17 DML + 8 SELECT + migracje; **usunięcie `master_con`**
5. `backup_manager`: backup mastera znika z klienta
6. **Test u siebie** — RM_BAZA ze źródeł
7. **Test awarii** — ubić serwer: odczyty z cache, zapisy zablokowane, praca trwa
8. **Test restartu** — serwer wraca, `server_epoch` się zmienia, klienci reagują
9. Build `.exe` → `TESTY RM_BAZA`
10. Jedno stanowisko na próbę (dzień pracy)
11. Produkcja + prośba o restart RM_BAZA

### Etap A

Jak wyżej. **Serwer musi działać na produkcji, zanim pójdzie `.exe`** — inaczej
klienci nie przejmą locków w ogóle (bo fallbacku nie ma).

---

## 10. Testy akceptacyjne

**Etap B:**
- 10 równoczesnych zapisów z różnych maszyn → wszystkie przechodzą
- `master-batch` przerwany w połowie → **nic** nie zostaje zapisane
- zerwane TCP po commicie → ponowienie z tym samym `request_id` **nie duplikuje**
- serwer ubity w trakcie zapisu → klient dostaje błąd, nie cichą stratę
- żądanie bez poprawnego HMAC → odrzucone
- żądanie z nieznaną `operation` → odrzucone
- **po tygodniu: żadne stanowisko nie ma otwartego master.sqlite** (sprawdzić
  w „Otwarte pliki" na `\\nic` — to jest dowód, że przyczyna zniknęła)

**Etap A:**
- dwa stanowiska proszą o ten sam lock w tej samej sekundzie → jedno dostaje
- klient ubity → lock wygasa po 90 s, nie wisi
- `release` z cudzym `lock_id` → odrzucony
- restart serwera → klient z lockiem dostaje „utracono lock", **nie nadpisuje** pliku
- `force` odbiera lock → poprzedni właściciel dowiaduje się przy heartbeacie (≤20 s)

---

## 11. Czego plan nie rozwiązuje

- **`project_con`** — pliki projektów zostają, świadomie (§0)
- **`rm_manager.sqlite`** — RM_MANAGER ma własną bazę, osobny temat.

⚠️ **Poza RM_BAZA do master.sqlite piszą jeszcze dwa narzędzia** — muszą przejść
na serwer **razem z etapem B**, inaczej zostają współwłaścicielami pliku i cała
praca idzie na marne:

| Kto | Co robi | Co z tym zrobić |
|---|---|---|
| **RM_MANAGER** (`rm_manager.sync_to_master`) | `UPDATE projects SET status, designer, montaz, fat, completed_at` przy zwalnianiu locka | operacja `project-status-sync` przez `rm_klient` |
| **backup_manager** (`backup_master`) | otwiera master i robi kopię | znika z klienta — backup robi serwer (§4) |

Pozostałe narzędzia dotykające mastera są **bezpieczne** i zostają bez zmian:
`project_manager.py` (biblioteka — dostaje połączenie z zewnątrz, nie otwiera pliku),
`Parser_RM_BAZA`, `RM_KOD`, `db.py`, `rm_ai_optimizer` (read-only albo własne ścieżki),
`ksef_archiwum` (pisze do własnej bazy obok mastera).
- **Bramka wersji** — działa tylko przy starcie; kto ma otwarte, nie zobaczy monitu.
  Przy wdrożeniu trzeba powiedzieć ludziom „zrestartujcie".
- **Backupy projektów** — zostają po stronie klienta (inne pliki, inny problem)

---

## 12. Kontekst

| Dokument / pamięć | Co zawiera |
|---|---|
| `SUBIEKT_STALY_MOST_PLAN.md` | wzorzec architektury, protokół, dystrybucja |
| `subiekt_sfera/NexoRecon/ServerHost.cs` | gotowy serwer TCP + kolejka |
| `subiekt_bridge.py` | gotowy klient, wersjonowanie protokołu |
| `project_master_stuck_transaction` | przyczyna awarii 11.09 i diagnoza |
| `project_rm_baza_db_model_decision` | zakres: HTTP docelowo, bez refaktoru SQLite |
| `project_master_journal_delete` | dlaczego `journal=delete`, nie WAL po SMB |
| `project_master_con_retire_crash` | dlaczego `master_con` nie wolno `close()` |
| `feedback_most_w_gicie` | źródła w gicie, binarka osobno |

---

*Wersja 2, 11.09.2026 — po recenzji. Wersja 1 w historii gita (`c6130ff`).*
