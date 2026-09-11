# RM_SERWER — plan wdrożenia w trzech etapach

Dokument wykonawczy. Wersja 8 (11.09.2026).

| Etap | Co przechodzi przez serwer | Robota | Co daje |
|---|---|---|---|
| **1** | `master.sqlite` | 3–4 dni | koniec awarii typu 11.09.2026 — u źródła |
| **2** | pliki projektów (checkout/checkin) + locki | 3–4 dni | serwer plików świadomy locków; koniec kopiowania po SMB |
| **2.5** | bazy RM_MANAGER (`rm_manager.sqlite` + 81 projektowych) | do wyceny | ten sam problem co master, tylko jeszcze nie wybuchł |
| **3** | rysunki i pozostałe pliki | do wyceny | **RM_BAZA nie potrzebuje `Y:`** |

**Kolejność: 1 → 2 → (2.5) → 3.** Każdy etap ma własny cutover i jest użyteczny sam
w sobie. Etap 1 jest opisany w pełni (Część I) — to on idzie do kodowania
teraz. Etapy 2 i 3 są zakresem i decyzjami (Części II i III); szczegóły
protokołu doprecyzujemy przed ich kodowaniem, gdy etap 1 będzie chodził.

> **Zmiana wobec wersji 7 — decyzja: cel docelowy to RM_BAZA bez dysków
> sieciowych.** Wersje 5–7 świadomie zostawiały projekty i locki na `Y:`,
> bo „locki działają, nie ma bólu". To nadal prawda — i dlatego **etap 2 nie
> przebudowuje warstwy danych ani reguł locków**. Zmienia się wyłącznie
> transport: zamiast `shutil.copy2` po SMB i plików `.lock` na udziale —
> `checkout`/`checkin` przez serwer i te same reguły locków wykonywane po jego
> stronie. Kopia lokalna zostaje, 244 wywołania SQL na `project_con` zostają,
> `acquire_project_lock()` i pozostałe metody zostają. Zysk, którego etap 1
> nie daje: stanowisko potrzebuje tylko adresu serwera i lokalnego cache —
> bez mapowania dysków, poświadczeń SMB i „nie widzi udziału".

```
DZIŚ                                   DOCELOWO
RM_BAZA ──SMB──► Y:\RM_BAZA\master     RM_BAZA ──TCP──► RM_SERWER ──► C:\Apps\RM_SERWER\dane\master.sqlite
RM_BAZA ──SMB──► Y:\RM_BAZA\projects                        │        ├── projects\
RM_BAZA ──SMB──► Y:\RM_BAZA\locks                           │        ├── locks (w pamięci + dysk)
RM_BAZA ──SMB──► Y:\SERVER_PROJEKTY, B:, V:                  │        └── backups\
                                                          └── pliki: get_file → lokalny cache
```

> **Zmiany wobec wersji 6** (w Części I): rollback i tryb legacy **oddają plik
> na `Y:`** (§5, §8); HMAC nie przecenia ochrony przed replayem (§7).
> **Wobec wersji 5**: read-only to nie zwolnienie — snapshot dla narzędzi
> raportowych (§10); weryfikacja przez `handle.exe` (§8, §9).
> **Wobec 1–4**: klienci nie otwierają mastera wcale; brak fallbacku
> per-klient; `request_id` + `_server_request_log` w masterze; nazwane
> operacje; backup na serwerze; HMAC z kanonicznym JSON; cutover zamiast
> pilota.

---

# CZĘŚĆ I — ETAP 1: master.sqlite przez serwer

*Ta część jest kompletna i idzie do kodowania jako pierwsza.* Wszędzie, gdzie
mowa „locki i projekty zostają na `Y:`", rozumieć: **w etapie 1**. Etap 2
(Część II) przenosi je na serwer — bez zmiany reguł.

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
    master.sqlite  +  backups/     (locks/ i projects/ zostają na Y: w ETAPIE 1;
                                    przechodzą na serwer w ETAPIE 2 — Część II)
```

### Maszyna docelowa — ustalone 11.09.2026

| | |
|---|---|
| **Host** | `W2019S`, `192.168.100.84` (LAN), Windows Server 2019 Essentials |
| **Konto** | `w2019s\mongo` (lokalne, WORKGROUP — bez domeny) |
| **Katalog aplikacji** | `C:\Apps\RM_SERWER\` |
| **Dane** | `C:\Apps\RM_SERWER\dane\master.sqlite` — **dysk lokalny, 121 GB wolne** |
| **Python** | 3.12.8 (zainstalowany) |
| **Usługa** | NSSM (`C:\Tools\nssm\nssm.exe`), ObjectName `.\mongo` |
| **Port** | 5060 (wolne; zajęte: 5050 RM_STATS, 5055 RM_PRINT, 5057 RM_DWF, 5058 RM_SERWIS) |
| **Dostęp administracyjny** | WinRM/PSSession, poświadczenia w `%TEMP%\rmdwf_srvcred.xml` (DPAPI) |

Wzorzec wdrożenia i obsługi usług — jak pozostałe aplikacje firmowe:
`NOW/DOKUMENTACJA/DOSTEP_SERWER.md`.

⚠️ **SERWER NIE DOTYKA DYSKÓW SIECIOWYCH** — decyzja z 11.09.2026. Żadnego
`Y:`, żadnego `\\nic` w jego konfiguracji. Master i (w etapie 2) pliki
projektów leżą na dysku lokalnym serwera.

Trzy powody, każdy wystarczający:
1. **To jest sedno tego planu** — jeden proces, jeden lokalny plik, koniec
   SQLite po SMB (§0).
2. **Sesja WinRM nie widzi dysków sieciowych.** Sprawdzone: `Test-Path Y:` →
   „Access is denied", `\\nic\rysunki` tak samo. Mapowanie żyje tylko
   w sesji usługi (przez `net use` z osobnym hasłem `nic\mongo`
   w launcherze). Gdyby serwer czytał bazę z `Y:`, każda diagnoza przez
   WinRM byłaby ślepa.
3. **SQLite i tak nie działa przez UNC** — stąd w pozostałych aplikacjach
   firmowych litera `Y:`. Dysk lokalny usuwa ten problem u źródła, zamiast
   go obchodzić.

Konsekwencja dla cutoveru (§8): master **przeprowadza się** z `Y:` na dysk
lokalny serwera. To nie jest szczegół konfiguracji, tylko jeden z kroków
wdrożenia — i powód, dla którego rollback wymaga kopii w drugą stronę.

### Decyzje i powody

**TCP + ramka z długością, nie HTTP.** Most Subiekta używa dokładnie tego
(`ServerHost.cs`, `subiekt_bridge.py`): 4 bajty little-endian + JSON. Zero
zależności, gotowy kod po obu stronach. „HTTP" w rozmowie znaczyło „przez serwer,
nie przez plik" — i to dostajemy.

**Jeden wątek wykonujący operacje na bazie.** Wątki TCP tylko wkładają żądania do
kolejki — jak `SferaWorker` w moście. Współbieżność **znika z problemu**, zamiast
być obsługiwana.

**Serwer w Pythonie.** Most jest w C#, bo woła SDK Sfery. Tu rozmawiamy wyłącznie
z SQLite, który Python obsługuje natywnie — żadnej zewnętrznej zależności.

**Nasłuch na LAN.** Jedyna różnica wobec mostu (tamten: `127.0.0.1`). Stąd
autoryzacja — §7.

**Serwer i master na LOKALNYM dysku maszyny `nic`.** To domyka całą rzecz: serwer
otwiera `C:\Apps\RM_SERWER\dane\master.sqlite`, a nie `\\nic\rysunki\RM_BAZA\master.sqlite`.
**SMB znika ze ścieżki do bazy całkowicie** — razem z sieciowymi blokadami
plikowymi, które były źródłem awarii. Udział sieciowy zostaje dla plików
projektów i rysunków; baza przestaje przez niego przechodzić.

Przy przenosinach pliku pamiętać o `sync_config.json` — klienci nie będą już
potrzebować ścieżki do mastera (nie otwierają go), ale narzędzia read-only
wymienione w §10 — owszem.

---

## 2. Kontrakt: kto dotyka pliku

| | Dziś | Po etapie B |
|---|---|---|
| Zapisy do mastera | 10 klientów | **serwer** |
| Odczyty z mastera | 10 klientów | **serwer** |
| Migracje / PRAGMA | 10 klientów | **serwer** (przy starcie) |
| Backup mastera | klient przy zwalnianiu locka | **serwer** |
| Pliki projektów | klient (kopia lokalna) | klient — bez zmian |

Po etapie B `DatabaseManager.master_con` **przestaje być używane w trybie
domyślnym**. Test kompletności w trybie serwer: dopóki `master_con` jest
otwierane, ktoś może go użyć.

---

## 2a. Przełącznik serwer / legacy — narzędzie wdrożenia, nie architektura docelowa

**Po co istnieje:** żeby cutover (§8) i ewentualne wycofanie były decyzją
jednego kliknięcia ADMIN-a, a nie podmianą `.exe` na dziesięciu komputerach
pod presją czasu. Przełącznik żyje **przez okres wdrożenia** — od pierwszego
cutoveru do momentu, gdy tryb serwer jest sprawdzony w boju (propozycja:
2–4 tygodnie stabilnej pracy).

| Tryb | Jak dotyka mastera | Rola |
|---|---|---|
| **serwer** | przez `rm_serwer` (§0–§10) | docelowy |
| **legacy** | dokładnie dzisiejszy kod — `master_con` bezpośrednio po SMB | **siatka bezpieczeństwa na czas wdrożenia** |

**Tryb jest globalny, ustawiany przez ADMIN-a, czytany przez WSZYSTKIE
stanowiska naraz** — dokładnie ten sam mechanizm co przełącznik legacy
w §5/§8 (`sync_config.json` na `Y:`, klient czyta przy starcie). To nie jest
wybór per-komputer.

```json
{"rm_serwer": {"tryb": "serwer"}}    // domyślny
{"rm_serwer": {"tryb": "legacy"}}    // ADMIN wyłączył serwer
```

To **ten sam klucz i ten sam mechanizm** co tryb legacy w §5 — nie dwa
osobne przełączniki. §5 opisuje go od strony awarii („serwer padł na
dłużej"), tutaj od strony wdrożenia („ADMIN cofa cutover"). Jedna flaga,
dwa powody użycia.

⚠️ **Dlaczego nie per-stanowisko.** Rozważane i odrzucone: gdyby każdy
komputer wybierał tryb niezależnie, PC1 mógłby pisać przez serwer, a PC2
w tym samym momencie bezpośrednio po SMB do tego samego pliku. To jest
dosłownie mechanizm awarii z 11.09 (§0) — czytelnik/pisarz po SMB trzyma
blokadę, która blokuje commit serwera, i odwrotnie. Serwer nie chroni przed
niczym, jeśli obok niego ktoś inny otwiera ten sam plik wprost. Globalny
przełącznik gwarantuje, że w danej chwili **tylko jeden model dostępu** jest
aktywny dla wszystkich.

### Co to oznacza dla kodu

`DatabaseManager` dostaje jedną warstwę pośrednią (`master_read` /
`master_exec` / `master_batch` z §3), którą i tak już wprowadza ten plan —
przełącznik **nie jest nową architekturą**, tylko drugą implementacją tej
samej warstwy:

```python
def master_exec(self, operation, params, request_id=None):
    if self.tryb_mastera == "serwer":
        return rm_klient.zapytaj("master-exec", {...})
    else:  # "legacy" — dzisiejszy kod, zachowany na czas wdrożenia
        return self._master_exec_local(operation, params)
```

Stary kod (`master_con.execute(sql)` na 133 miejscach) **nie znika** —
przenosi się pod `_master_exec_local` i mapowanie `operation → SQL`, którego
i tak wymaga tryb serwer (nazwane operacje, §3). Innymi słowy: implementując
tryb serwer zgodnie z resztą tego planu, tryb legacy dostajemy niemal za
darmo — to ten sam SQL, tylko wołany bezpośrednio zamiast przez sieć.

### Kiedy tryb legacy znika

Dwie ścieżki kosztują: każda nowa operacja na masterze musi działać po obu
stronach przełącznika, inaczej powrót na „legacy" po miesiącach cicho łamie
funkcję, której nikt w tym trybie nie sprawdził.

Dlatego tryb legacy ma **termin ważności**:

```
cutover  →  2–4 tygodnie obu trybów  →  usunięcie trybu legacy
                                         (master_con znika naprawdę)
```

Warunek usunięcia: tryb serwer przepracował ten okres bez sytuacji, w której
ADMIN musiał wrócić na „legacy". Wtedy `_master_exec_local` i `master_con`
wypadają z kodu, a §2 („kto dotyka pliku") obowiązuje bez zastrzeżeń.

Dopóki przełącznik istnieje, **nowe funkcje piszemy w obu trybach** — to jest
cena za możliwość wycofania jednym kliknięciem.

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

**Dziennik musi przeżyć restart serwera.** Cache w pamięci nie wystarcza —
najgorszy przypadek to właśnie ten, w którym serwer pada tuż po commicie:

```
INSERT + COMMIT ✓  →  serwer pada przed odpowiedzią  →  restart
                   →  cache pusty  →  klient ponawia  →  DRUGI INSERT
```

Dziennik idzie **do samego mastera**, jako tabela techniczna:

```sql
CREATE TABLE _server_request_log (
    request_id  TEXT PRIMARY KEY,
    operation   TEXT NOT NULL,
    kto         TEXT,
    result_json TEXT,
    created_at  TEXT NOT NULL
);
```

```
BEGIN
    właściwa operacja
    INSERT _server_request_log
COMMIT
```

**Jedna baza, jeden journal, jedna transakcja.** Rozważałem osobną
`rm_serwer.sqlite` z `ATTACH`, ale to komplikuje najważniejszą gwarancję systemu
w zamian za czystość estetyczną — łatwiej udowodnić brak dziury, gdy wszystko
siedzi w jednym pliku, którego i tak jesteśmy jedynym właścicielem.

Podkreślenie `_` w nazwie mówi wprost: to stan serwera, nie dane firmy. Backup
obejmuje ją razem z resztą — i dobrze, bo po odtworzeniu kopii ochrona przed
duplikatami działa dalej.

Czyszczenie: rekordy starsze niż **24 h** (raz dziennie, przy okazji backupu).
Klient generuje `request_id` **raz na operację**, nie raz na próbę.

Dotyczy **wszystkich operacji zmieniających** (`*-add/-edit/-delete`,
`master-batch`). Odczyty są idempotentne, więc ochrona ich nie obejmuje — ale
`request_id` wysyłamy przy każdym żądaniu, bo wchodzi do podpisu HMAC (§7).

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

### Komendy

| Komenda | Argumenty | Zwraca |
|---|---|---|
| `master-read` | `operation`, `params` | wiersze |
| `master-exec` | `operation`, `params`, `request_id` | `rowcount`, `lastrowid` |
| `master-batch` | `operacje: [{operation, params}]`, `request_id` | **wszystko albo nic** |
| `ping` | — | `protokol`, `uptime`, `zapisow_od_startu` |

`master-batch` jest konieczny: „dodaj dostawcę + wpis do audytu" to jedna
transakcja. Dziś dwa `execute` i jeden `commit`.

**Lista operacji do zbudowania** (z inwentaryzacji kodu):

- odczyt: `suppliers-list`, `supplier-get`, `stage-definitions`, `material-prices`,
  `users-list`, `projects-list`, `project-get`, `settings-get`, `sessions-list`
- zapis: `supplier-add`, `supplier-edit`, `supplier-delete`, `supplier-tags-set`,
  `user-add`, `user-edit`, `user-delete`, `user-audit-add`, `settings-set`,
  `session-heartbeat`, `session-close`, `project-status-sync`, `zd-zamowione-*`

### Wersja protokołu

`ping` zwraca `protokol`. Klient zna minimalną zgodną wersję i przy niezgodności
mówi wprost, co zaktualizować — mechanizm z `subiekt_bridge._sprawdz_protokol`.

---

## 4. Zmiany w kodzie

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

Zostaje jedno ryzyko: **awaria samego serwera** — §5.

---

## 5. Awaria serwera — bez cichego powrotu do SMB

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
| Locki projektów | **działają normalnie** — w etapie 1 to pliki `.lock` na `Y:`, serwer ich nie dotyka (etap 2: patrz Część II, §14) |
| Praca na projekcie | trwa — kopia jest lokalna |
| Zwolnienie locka | **działa normalnie** — plik projektu idzie na `Y:` jak dziś |

**Minuta bez możliwości edycji jest lepsza niż cichy powrót do architektury, która
spowodowała 40-minutowe zakleszczenie.**

### Co z pracy na projektach przetrwa awarię serwera

**Wszystko.** Locki i pliki projektów są poza zakresem **etapu 1** — klient bierze
lock z `Y:\RM_BAZA\locks`, pracuje na kopii lokalnej i oddaje plik na `Y:`
dokładnie tak jak dziś. Brak serwera oznacza wyłącznie: **nie zapiszesz danych
z mastera** (dostawcy, użytkownicy, ustawienia, statusy).

To jest mocna strona węższego zakresu: awaria serwera nie może zabrać nikomu
pracy nad projektem, bo w etapie 1 serwer o projektach nic nie wie.
(W etapie 2 ta własność jest zachowana inaczej — praca na kopii lokalnej
trwa, tylko `checkin` czeka na serwer; Część II, §14.)

⚠️ Jeden przypadek do zapamiętania: **„Zamówiono" z wysyłki ZD** siedzi w masterze
(`zd_zamowione_pozycje`) i jest nakładane na kopię przy przejęciu locka. Przy
niedostępnym serwerze wpisy **nie znikną** — zostaną nałożone przy następnym
przejęciu projektu (mechanizm jest idempotentny, patrz `usun_zamowienia`).
Nic nie ginie, tylko później dochodzi.

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

⚠️ **Sama flaga nie wystarczy — trzeba oddać plik.** Klienci w trybie legacy
szukają mastera na `Y:`, a aktualny leży na dysku lokalnym maszyny `nic`. Pełna procedura
to ta sama, co przy wycofaniu programu (§8): zatrzymać serwer, skopiować
`C:\Apps\RM_SERWER\dane\master.sqlite` → `Y:\RM_BAZA\master.sqlite`, sprawdzić
`integrity_check`, dopiero potem przełączyć flagę.

Jeśli maszyna `nic` **nie żyje** i lokalny plik jest nieosiągalny, do `Y:` idzie
najnowszy backup z rotacji — z jawną informacją dla ludzi, ile pracy przepadło
(różnica między czasem backupu a awarią). Lepiej powiedzieć wprost „tracimy
dwie godziny" niż pozwolić komuś odkryć to samodzielnie po tygodniu.

**Powrót z legacy na serwer** to zwykły cutover (§8) w drugą stronę: cisza,
kopia `Y:` → dysk lokalny serwera, start serwera, nowy `.exe`, weryfikacja `handle.exe`.

---

## 6. Pliki

```
rm_serwer.py            TCP, kolejka, jeden wątek, HMAC, request_id     ~300 linii
rm_serwer_master.py     nazwane operacje + migracje + backup            ~250 linii
rm_klient.py            klient (wzorzec subiekt_bridge)                 ~180 linii

database_manager.py     ZMIANA: master_con → master_read/exec/batch
backup_manager.py       ZMIANA: backup_master() znika z klienta
RM_BAZA_v15_MAG_STATS_ORG.py   ZMIANA: 17 DML + 8 SELECT
```

**`lock_manager_v2.py` — BEZ ZMIAN w etapie 1.** Locki plikowe zostają dokładnie
takie, jakie są. Etap 2 podmienia **wnętrza** jego metod na wywołania serwera,
z tymi samymi regułami (Część II, §12).

Serwer w repo, wystawiany na `\\nic` — zasada z `feedback_most_w_gicie`.

---

## 7. Bezpieczeństwo

Most Subiekta słucha na `127.0.0.1`. Ten musi na LAN, więc:

**Token HMAC w każdym żądaniu.** Samo `"kto": {"user": "ADMIN"}` nie uwierzytelnia
nikogo — dowolny klient w LAN napisze, że jest ADMIN, i wywoła `user-delete`
albo `supplier-delete`.

```
sekret:   plik na Y: czytelny tylko dla grupy RM_BAZA
hmac:     HMAC-SHA256(sekret, request_id + "|" + cmd + "|" + kanoniczny_json(args))
serwer:   odrzuca żądanie bez poprawnego HMAC
```

**Kanoniczny JSON** — inaczej podpis raz na jakiś czas nie zgodzi się bez powodu,
bo Python ułożył klucze inaczej:

```python
json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
```

Trzy rzeczy muszą być ustalone po obu stronach: **kolejność kluczy** (`sort_keys`),
**brak spacji** (`separators`) i **kodowanie znaków** (`ensure_ascii=False`, bo
w danych są polskie znaki i nazwy dostawców). Separator `|` między członami —
żeby `request_id` „ab" + `cmd` „c" nie dawało tego samego co „a" + „bc".

`request_id` idzie w **każdym** żądaniu, także w odczytach — dla jednoznacznego
podpisania i śledzenia żądania w logu.

⚠️ **Sam podpis nie chroni przed replayem.** HMAC gwarantuje, że treść nie
została podmieniona — ale przechwycony pakiet, odsłany bez zmian, ma poprawny
podpis. Realnie:

| | Ochrona przed powtórzeniem |
|---|---|
| operacje zmieniające | **`_server_request_log`** — drugie wykonanie zwraca zapamiętany wynik, nic się nie dzieje |
| odczyty | brak — i **nie jest potrzebna**: powtórzony odczyt jest nieszkodliwy |

Nie dokładamy tu nic więcej (nonce, znacznik czasu, numery sekwencyjne). W LAN,
za zaporą, przy nieszkodliwym replayu odczytów — byłaby to złożoność bez zysku.

To nie kryptografia wojskowa — to bariera przeciw przypadkowi i ciekawskiemu
skryptowi.

⚠️ **HMAC uwierzytelnia KLIENTA, nie użytkownika.** Sekret jest wspólny, więc
każdy, kto go ma, może wysłać `"kto": {"user": "ADMIN"}` — a serwer sprawdza
rolę właśnie po tym polu. Sprawdzanie roli po stronie serwera jest lepsze niż
w GUI, ale **tylko dopóki polu `kto.user` można ufać**.

W LAN, przy grupie pracowników firmy, to akceptowalne na start. Docelowo
`kto.user` musi wynikać z **sesji**, nie z JSON-a:

```
logowanie w RM_BAZA  →  serwer wydaje token sesji (user + rola + ważność)
kolejne żądania      →  token zamiast gołego "kto"
```

Serwer ma już po temu materiał: tabela `users` w masterze i `client_sessions`
z heartbeatem. To osobna zmiana — **nie blokuje tego wdrożenia**, ale powinna
wejść, zanim przez serwer pójdą operacje groźniejsze niż dziś.

**Pozostałe:**
- nasłuch na konkretnym interfejsie LAN, nie `0.0.0.0`
- reguła zapory: tylko podsieć firmowa
- **żadnego SQL od klienta** — wyłącznie nazwane operacje (§3)
- log każdego zapisu: kto, co, kiedy → `C:\RMPAK_CLIENT\rm_serwer_logi\`
- operacje wrażliwe (`user-add/-edit/-delete`, `settings-set`,
  `supplier-delete`): rola ADMIN sprawdzana **po stronie serwera**, nie w GUI

---

## 8. Kolejność wdrożenia

### ⚠️ Nie ma pilota na produkcyjnym masterze

Wersja 1 planu przewidywała „jedno stanowisko na próbę — dzień pracy". **To
przeczy zasadzie z §0**: przez ten dzień jeden klient chodziłby przez serwer,
a dziewięciu nadal otwierało `master.sqlite` wprost. Czyli dokładnie ten stan,
który usuwamy — tylko z dodatkowym pisarzem.

Testujemy na **kopii mastera**, wdrażamy **jednorazowym cutoverem**.

### Budowa i testy (na kopii)

1. `rm_serwer.py` + `rm_serwer_master.py` — nazwane operacje, `request_log`,
   migracje, backup
2. `rm_klient.py` + `master_read/exec/batch` w `DatabaseManager`
3. Przepisanie 17 DML + 8 SELECT + migracje; **usunięcie `master_con`**
4. `backup_manager`: backup mastera znika z klienta
5. RM_MANAGER: `sync_to_master` → operacja `project-status-sync` (§10)
6. **Środowisko testowe**: serwer + **kopia** `master.sqlite` + 1–2 klienty ze
   źródeł. Produkcyjny master **nietknięty**.
7. Testy z §9 — wszystkie, w tym awaria serwera i restart
8. Build `.exe` → `TESTY RM_BAZA`

### Cutover (jedno okno, ~30 min)

Poza godzinami pracy albo w umówionym oknie:

```
1.  Ostrzeżenie dzień wcześniej: "jutro 7:30-8:00 RM_BAZA niedostępna"
2.  Wszyscy zamykają RM_BAZA
3.  Sprawdzenie: \\nic -> Otwarte pliki -> master.sqlite = PUSTO
4.  Kopia zapasowa master.sqlite (poza rotacją)
5.  Start RM_SERWER jako usługa + weryfikacja `ping`
6.  Publikacja `.exe` na produkcję
7.  Uruchomienie klientów - bramka wersji wymusi nowy `.exe`
8.  Weryfikacja NA MASZYNIE nic (handle.exe / Process Explorer):
    uchwyt do C:\Apps\RM_SERWER\dane\master.sqlite ma WYLACZNIE proces RM_SERWER
```

Krok 3 jest istotny: dopóki któryś klient trzyma plik, serwer nie jest jedynym
właścicielem i cutover jest pozorny.

⚠️ **Kroki 3 i 8 sprawdzają co innego i innym narzędziem** — bo w międzyczasie
baza przeprowadza się z udziału sieciowego na dysk lokalny:

| | Gdzie leży master | Czym sprawdzić |
|---|---|---|
| **krok 3** (przed) | `Y:` — udział sieciowy | `\nic` → Zarządzanie komputerem → **Otwarte pliki** |
| **krok 8** (po) | `C:\Apps\RM_SERWER\dane` na `nic` — lokalnie | na maszynie `nic`: `handle.exe master.sqlite` albo Process Explorer |

„Otwarte pliki" pokazują **wyłącznie uchwyty przez SMB**. Po przenosinach serwer
otwiera plik lokalnie, więc ta lista będzie pusta **zawsze** — także wtedy, gdy
coś będzie nie tak. Test, który zawsze przechodzi, nie jest testem.

```
# na maszynie nic, po cutoverze:
handle.exe master.sqlite

# oczekiwane: dokładnie jeden proces — RM_SERWER (python.exe / rm_serwer.exe)
```

### Wycofanie — dwie różne rzeczy

⚠️ **Wycofanie programu to NIE jest odtworzenie bazy.** Mylenie tych dwóch
kasuje pracę: jeśli serwer działał pięć godzin, a ktoś odtworzy master z kopii
zrobionej o 7:30, ginie pięć godzin pracy całej firmy.

**Wycofanie programu** — gdy nowa wersja się źle zachowuje:

⚠️ **Baza musi wrócić tam, gdzie stary klient jej szuka.** Podczas cutoveru
master przeprowadza się z `Y:` na dysku lokalnym maszyny `nic`; stary `.exe` nie zna
ścieżki lokalnej i sam jej nie znajdzie. Bez kroku 4 poniżej rollback wygląda
na wykonany, a klienci startują na **starym, nieaktualnym** pliku z `Y:`
— i cicho rozjadą dane.

```
1. Wszyscy zamykają RM_BAZA
2. Zatrzymaj RM_SERWER
3. Backup C:\Apps\RM_SERWER\dane\master.sqlite            ← bezcenne przy diagnozie
4. Skopiuj AKTUALNY master z powrotem na udział:
       C:\Apps\RM_SERWER\dane\master.sqlite  →  Y:\RM_BAZA\master.sqlite
5. PRAGMA integrity_check na kopii docelowej
6. Przełącz sync_config.json na tryb legacy
7. Przywróć stary .exe (RM_BAZA_v15_MAG.exe.przed_*)
8. Uruchomienie klientów
```

Schemat bazy się nie zmienia, więc stary klient czyta i pisze te dane bez
problemu — wraca tylko do robienia tego wprost po SMB.

Kroki 1 i 2 są w tej kolejności nieprzypadkowo: kopiowanie żywego pliku SQLite,
do którego ktoś pisze, daje uszkodzoną kopię. Najpierw cisza, potem kopia.

**Odtworzenie bazy z kopii sprzed cutoveru** — osobna, świadoma decyzja, wyłącznie
gdy master jest **faktycznie uszkodzony** (`PRAGMA integrity_check` zgłasza błędy,
brakuje tabel, dane są wewnętrznie sprzeczne). Wtedy i tak najpierw kopia
awaryjna z kroku 2 — bo może się okazać, że da się z niej coś odzyskać.

Nie ma terminu „do końca pierwszego dnia" — wycofanie programu jest bezpieczne
zawsze.

## 9. Testy akceptacyjne

**Master przez serwer:**
- 10 równoczesnych zapisów z różnych maszyn → wszystkie przechodzą
- `master-batch` przerwany w połowie → **nic** nie zostaje zapisane
- zerwane TCP po commicie → ponowienie z tym samym `request_id` **nie duplikuje**
- serwer ubity w trakcie zapisu → klient dostaje błąd, nie cichą stratę
- żądanie bez poprawnego HMAC → odrzucone
- żądanie z nieznaną `operation` → odrzucone
- **po tygodniu: uchwyt do mastera ma wyłącznie RM_SERWER** — sprawdzone
  `handle.exe master.sqlite` NA MASZYNIE `nic` (nie przez „Otwarte pliki":
  te pokazują tylko dostęp przez SMB, a baza leży już lokalnie na serwerze). To jest dowód,
  że przyczyna zniknęła — i jedyny test, który wyłapie zapomniany skrypt
  czytający żywy plik

**Locki — regresja (muszą działać jak dotąd):**
- przejęcie i zwolnienie locka projektu — bez zmian
- `release_lock` przy utraconym locku — nadal wykrywa i nie nadpisuje cudzej pracy
- praca przy niedostępnym serwerze — lock się bierze, projekt zapisuje na `Y:`

---

## 10. Czego plan nie rozwiązuje

- **`project_con`** — pliki projektów zostają, świadomie (§0)
- **`rm_manager.sqlite`** — RM_MANAGER ma własną bazę, osobny temat.

⚠️ **Poza RM_BAZA do master.sqlite piszą jeszcze dwa narzędzia** — muszą przejść
na serwer **razem z etapem B**, inaczej zostają współwłaścicielami pliku i cała
praca idzie na marne:

| Kto | Co robi | Co z tym zrobić |
|---|---|---|
| **RM_MANAGER** (`rm_manager.sync_to_master`) | `UPDATE projects SET status, designer, montaz, fat, completed_at` przy zwalnianiu locka | operacja `project-status-sync` przez `rm_klient` |
| **backup_manager** (`backup_master`) | otwiera master i robi kopię | znika z klienta — backup robi serwer (§4) |

### ⚠️ Read-only to NIE jest zwolnienie

Kuszące jest zostawić narzędzia, które tylko czytają. **Nie wolno** — przeczyłoby
to mechanizmowi opisanemu w §0: **czytelnik trzyma SHARED i potrafi zablokować
commit pisarza**. To była druga połowa awarii z 11.09, nie przypis do niej.

Zasada jest jedna, bez wyjątku dla trybu odczytu:

```
KAŻDY program otwierający ŻYWY master.sqlite
    → przechodzi przez RM_SERWER
albo
    → czyta wyłącznie KOPIĘ / snapshot, nigdy żywego pliku
```

Po przeniesieniu bazy na dysku lokalnym maszyny `nic` te narzędzia i tak przestaną ją
widzieć pod dotychczasową ścieżką — więc decyzja zapada tak czy inaczej.
Lepiej podjąć ją świadomie przed cutoverem niż przez awarię po nim.

| Narzędzie | Jak dziś dotyka mastera | Co zrobić |
|---|---|---|
| `Parser_RM_BAZA` | `DatabaseManager(master_path=...)` — **otwiera żywy plik** | snapshot: serwer wystawia dzienną kopię do odczytu |
| `Parser_RM_BAZA_gui` | j.w., ścieżka z okna | j.w. |
| `RM_KOD` | `master_db_path` z konfiguracji | snapshot albo `master-read` |
| `db.py` (RM_STATS) | `master_db_path` | snapshot — statystyki nie potrzebują danych sprzed sekundy |
| `rm_ai_optimizer` | przez `db.py` | jak wyżej |
| `RM_MANAGER` | **pisze** (`sync_to_master`) | operacja `project-status-sync` (wyżej) |
| `backup_manager` | otwiera master do kopii | znika z klienta — backup robi serwer (§4) |
| `project_manager.py` | **biblioteka** — dostaje połączenie z zewnątrz | bez zmian; wołający decyduje |
| `ksef_archiwum` | pisze do **własnej** bazy obok mastera | bez zmian |

**Snapshot dla czytelników** — najtańsze rozwiązanie dla narzędzi raportowych:
serwer przy okazji backupu wystawia `master_snapshot.sqlite` na udziale
sieciowym. Read-only, nikogo nie blokuje, wiek ≤ 24 h. Dla Parsera i statystyk
to w zupełności wystarcza; gdy któreś będzie potrzebowało świeżych danych,
dostanie `master-read`.

⚠️ **Inwentaryzacja przed cutoverem jest obowiązkowa** — powyższa lista powstała
z przeszukania repozytorium, ale skrypty i narzędzia mogą żyć poza nim (harmonogram
zadań, cudze kopie, makra). Test z §9 (uchwyty do pliku) jest ostatecznym
sprawdzeniem, czy kogoś nie pominęliśmy.
- **Bramka wersji** — działa tylko przy starcie; kto ma otwarte, nie zobaczy monitu.
  Przy wdrożeniu trzeba powiedzieć ludziom „zrestartujcie".
- **Backupy projektów** — zostają po stronie klienta (inne pliki, inny problem)

---

# CZĘŚĆ II — ETAP 2: projekty i locki przez serwer

## 11. Co się zmienia, a co świadomie nie

Dziś projekt przechodzi przez SMB trzy razy:

```
Y:\RM_BAZA\locks\project_2627.lock     ← utwórz / odśwież / usuń
Y:\RM_BAZA\projects\project_2627.sqlite ─copy→ C:\RMPAK_CLIENT\project_2627.sqlite
                                              ↓ praca na kopii (244 zapytania SQL)
Y:\RM_BAZA\projects\project_2627.sqlite ←copy─ C:\RMPAK_CLIENT\project_2627.sqlite
```

Po etapie 2 te same trzy kroki, ale przez serwer:

```
RM_BAZA  ──►  project-checkout(2627)   serwer: sprawdza i zakłada lock, odsyła plik
RM_BAZA       zapisuje lokalnie, otwiera przez OBECNY project_con
RM_BAZA       praca — 244 zapytania SQL DOKŁADNIE JAK DZIŚ
RM_BAZA  ──►  project-checkin(2627, plik)   serwer: czy lock nadal tego klienta?
                                            zapisuje, weryfikuje, backup, zwalnia lock
```

| | Zostaje bez zmian | Zmienia się |
|---|---|---|
| **Warstwa danych** | model kopii lokalnej; `project_con`; **244 wywołania SQL** | — |
| **Reguły locków** | jeden lock na użytkownika; stale po **300 s**; heartbeat co **30 s**; `force`; `bulk` dla linii produkcyjnej (RM_MANAGER) | wykonywane **na serwerze**, nie na plikach |
| **API locków w GUI** | 13 metod `lock_manager_v2`, 92 wywołania — sygnatury te same | tylko **wnętrza** metod |
| **Transport** | — | `shutil.copy2` po SMB → `checkout`/`checkin` przez TCP |
| **Backup projektu** | — | z klienta (przy zwalnianiu) na serwer (przy `checkin`) |
| **Weryfikacja po zapisie** | — | `integrity_check` + `checkpoint` robi serwer, nie klient |

To jest **serwer plików projektowych świadomy locków**, nie centralizacja bazy
projektów. Różnica w skali roboty: dni, nie tygodnie.

## 12. Locki — te same reguły, inne miejsce wykonania

Nie projektujemy nowego systemu lease/heartbeat (wersje 2–4 tego planu
próbowały — i słusznie z tego zrezygnowaliśmy). Przenosimy **dokładnie
obecną logikę** z `lock_manager_v2.py`:

| Reguła dziś | Skąd | Na serwerze |
|---|---|---|
| jeden lock na użytkownika | `_release_my_other_locks()` | serwer trzyma mapę `użytkownik@komputer → lock` |
| lock osierocony po 300 s bez heartbeatu | `stale_lock_seconds = 300` | ta sama wartość, liczona zegarem serwera |
| heartbeat co 30 s | `_heartbeat_interval_ms` | klient woła `lock-heartbeat`, jak dziś woła `refresh_heartbeat()` |
| `force` przejmuje cudzy lock | `acquire_project_lock(force=True)` | ta sama semantyka + wpis w logu serwera |
| `bulk` — wszystkie projekty linii naraz | `acquire_project_locks_bulk()` (RM_MANAGER) | `lock-acquire-bulk`, atomowo: wszystkie albo żaden |
| kto trzyma? | odczyt pliku `.lock` | `lock-owner` — ta sama struktura odpowiedzi |

Metody `lock_manager_v2` zostają, zmienia się wnętrze:

```python
# dziś
def get_project_lock_owner(self, project_id):
    lock_file = self.locks_folder / f"project_{project_id}.lock"
    ...

# etap 2
def get_project_lock_owner(self, project_id):
    return rm_klient.zapytaj("lock-owner", {"project_id": project_id}).get("owner")
```

Co znika z klienta: `cleanup_stale_locks()`, `cleanup_my_computer_locks()`,
obsługa „plik `.lock` zniknął w trakcie czytania". Serwer wie to sam.

**Bramka przed nadpisaniem cudzej pracy** — ta, która już istnieje
(`release_lock` sprawdza `lock_id`; `rm_manager.py:313`) — przenosi się do
`project-checkin`: serwer odmawia zapisu, gdy lock nie należy do proszącego.
Klient wtedy **nie traci pracy**: plik zostaje lokalnie jako kopia awaryjna
(`C:\RMPAK_CLIENT\awaria\`). To domyka dziurę odnotowaną w wersji 3:
`_force_cancel_lock_on_lost` dziś zamyka kopię i nic z nią nie robi.

⚠️ **RM_MANAGER dzieli te same locki.** Używa `lock_manager_v2` (plus stub
„no-lock" do symulacji) i `bulk` dla linii produkcyjnej. Etap 2 obejmuje go
tak samo jak RM_BAZA — inaczej dwa programy miałyby dwa różne źródła prawdy
o tym, kto trzyma projekt.

## 13. Komendy etapu 2

| Komenda | Argumenty | Zwraca | Uwagi |
|---|---|---|---|
| `project-checkout` | `project_id`, `typ` (MACHINE/WAREHOUSE), `force` | `lock_id`, plik (bajty), `wersja` | zakłada lock **i** oddaje plik w jednej operacji |
| `project-checkin` | `project_id`, `lock_id`, plik, `request_id` | `ok`, `wersja` | serwer: lock nadal tego klienta? → zapis → `integrity_check` → backup → zwolnij |
| `project-download` | `project_id` | plik (bajty), `wersja` | **snapshot do odczytu** bez locka — zastępuje dzisiejsze `mode=ro&immutable=1` po SMB |
| `project-list` | — | lista `{id, nazwa, typ, wersja, lock}` | jedna odpowiedź zamiast listowania katalogu |
| `lock-acquire` / `-release` / `-owner` / `-heartbeat` / `-force` | jak dziś w `lock_manager_v2` | jak dziś | dla przypadków, gdy lock jest brany bez pobierania pliku |
| `lock-acquire-bulk` | `project_ids`, `force` | mapa `id → (ok, lock_id)` | atomowo — dla RM_MANAGER |
| `backup-list` / `backup-get` | `project_id` | lista kopii / plik | okno „Przywróć backup (ADMIN)" musi mieć skąd brać |

Rozmiary są bez znaczenia dla transportu: **94 pliki, średnio 109 KB, największy
476 KB, razem 10,5 MB**. `checkout` to ułamek sekundy w LAN.

`project-download` zamiast czytania `immutable=1` po SMB: dziś przeglądanie
projektu bez locka otwiera plik na udziale w trybie „nic się nie zmienia".
Po etapie 2 klient pobiera kopię i otwiera ją lokalnie tak samo. Jedyna
różnica widoczna dla użytkownika: żadna.

`request_id` przy `checkin` chroni przed podwójnym zapisem po zerwanym TCP —
tak samo jak przy operacjach na masterze (`_server_request_log`).

## 14. Awaria serwera w etapie 2

Tu zasada „brak fallbacku per-klient" ma większe konsekwencje niż w etapie 1
i trzeba je nazwać wprost:

| Sytuacja | Zachowanie |
|---|---|
| Serwer pada, klient **ma** projekt pobrany (checkout) | praca na kopii lokalnej **trwa** — nic się nie dzieje |
| Klient chce oddać projekt (checkin), serwer nie odpowiada | `checkin` czeka; komunikat „serwer niedostępny — projekt zostaje u Ciebie, spróbuj za chwilę". **Nie ma** zapisu na `Y:` |
| Klient chce pobrać nowy projekt | odmowa: „serwer niedostępny" |
| Klient chce tylko **przejrzeć** projekt | z lokalnego cache ostatnio pobranych snapshotów, oznaczone jako nieświeże |
| Heartbeat nie dochodzi > 300 s | lock po stronie serwera wygasa; klient dowiaduje się przy `checkin` → odmowa + kopia awaryjna |

Ta ostatnia linia to jedyny przypadek, w którym praca **może** wymagać ręcznego
scalenia — dokładnie ten sam, co dziś przy `force` albo padnięciu sieci
w trakcie pracy. Etap 2 go nie tworzy; czyni go jawnym i zostawia plik.

**Tryb legacy** (§5) w etapie 2 oznacza dodatkowo: serwer musi oddać na `Y:`
katalogi `projects\` i `projects_MAG\` — nie tylko master. Ta sama zasada
„najpierw cisza, potem kopia".

## 15. Cutover etapu 2

Ten sam schemat co w etapie 1 (§8), z jedną różnicą w kroku 4: na dysku lokalnym maszyny
`nic` przenoszą się także `projects\`, `projects_MAG\`, `locks\` i `backups\`.
Krok 3 („Otwarte pliki = pusto") obejmuje wtedy **wszystkie** pliki `.sqlite`
w `RM_BAZA\`, nie tylko master.

Przed cutoverem — inwentaryzacja, kto jeszcze czyta pliki projektów z `Y:`
bezpośrednio (nie przez RM_BAZA): `Parser_RM_BAZA` (wszystkie bazy projektowe
→ snapshot), `subiekt_stany.py` (`Y:/RM_BAZA/projects` → `project-download`),
RM_MANAGER (własne `rm_manager_project_*.sqlite` w `Y:/RM_MANAGER` — **inna
baza, poza zakresem**, ale locki projektów RM_BAZA bierze przez ten sam
`lock_manager_v2` → etap 2).

## 16. Do rozstrzygnięcia przed kodowaniem etapu 2

Nie teraz — gdy etap 1 będzie chodził. Zapisane, żeby nie zginęły:

1. **`subiekt_mapowania.sqlite` na `Y:`** — drugi współdzielony SQLite z wieloma
   pisarzami po SMB (RW, `journal=DELETE`, 15 miejsc DML, 8 commitów, 0 rollbacków).
   Ta sama klasa problemu co master; mniejsze ryzyko, bo połączenia są krótkie
   (nie ma trwałego `master_con`, więc nieudany commit kończy się `close()`,
   które zwalnia RESERVED). Do decyzji: nazwane operacje na serwerze w etapie 1
   (najczyściej) albo osobny mały krok między 1 a 2.
2. **Chat** (`Y:/RM_BAZA/chat`, pliki JSON, odpytywanie co 30 s) — trywialne
   `chat-post`/`chat-poll`, ale to etap 3 albo przy okazji 2.
3. **Wersjonowanie pliku projektu** — `wersja` z `checkout`/`checkin` pozwala
   serwerowi odrzucić `checkin` starszej kopii, gdyby lock został przejęty
   przez `force` i oddany. Dziś tej ochrony nie ma; tania, warto.
4. **Lokalny cache snapshotów** — ile trzymać, kiedy sprzątać (propozycja:
   ostatnie 20 projektów, sprzątanie przy starcie).

---

# CZĘŚĆ II.5 — ETAP 2.5: bazy RM_MANAGER przez serwer

## 17. Dlaczego osobny etap, a nie część etapu 1

RM_MANAGER ma **własne bazy** na tym samym dysku sieciowym:

```
Y:\RM_MANAGER\rm_manager.sqlite                     424 KB — procesy, pracownicy, płatności
Y:\RM_MANAGER\RM_MANAGER_projects\rm_manager_project_<id>.sqlite   81 plików — zdarzenia per projekt
```

**To ta sama klasa problemu co master**: wielu użytkowników, jeden plik SQLite
po SMB. Różnica jest wyłącznie w tym, że dotąd nie wywołało to awarii —
RM_MANAGER ma mniej użytkowników niż RM_BAZA i krótsze sesje zapisu.

⚠️ **Nie mylić z przeniesieniem programu.** RM_MANAGER to aplikacja okienkowa
(Tkinter, 38 tys. linii GUI). Program okienkowy na serwerze nie ma komu
wyświetlić okna — ludzie pracują na swoich stanowiskach. Przeniesienie
*programu* oznaczałoby przepisanie na web, jak RM_STATS czy RM_RFQ. To miesiące
i osobna decyzja, nie ten plan. **Ten etap przenosi wyłącznie DANE.**

## 18. Zakres

| | Liczba | Uwaga |
|---|---|---|
| Wywołania SQL w `rm_manager.py` | **568** | warstwa danych |
| Wywołania SQL w `rm_manager_gui.py` | **187** | GUI woła bezpośrednio |
| Programy czytające te bazy | **10** | RM_BAZA, RM_STATS (`db.py`), optymalizator, RM_KOD, backup… |

755 wywołań to **więcej niż cały etap 1** (133 na masterze). Dlatego osobny
etap, a nie dopisek — i dlatego kolejność ma znaczenie: wchodzimy tu dopiero,
gdy mechanizm jest sprawdzony na masterze i na plikach projektów.

## 19. Dwa punkty styku, które wchodzą WCZEŚNIEJ

RM_MANAGER dotyka rzeczy z etapów 1 i 2 **niezależnie od tego etapu** — i tam
musi być obsłużony, inaczej zostaje współwłaścicielem plików:

| Co | Gdzie | Etap |
|---|---|---|
| `sync_to_master` — `UPDATE projects` w **masterze RM_BAZA** | `rm_manager.py` | **1** (§10) |
| Locki projektów, w tym `acquire_project_locks_bulk` dla linii produkcyjnej | `lock_manager_v2` | **2** (§12) |

To jest ważne rozróżnienie: **RM_MANAGER wchodzi do planu przez te dwa punkty
już teraz**, a jego własne bazy dopiero w tym etapie.

## 20. Jak to zrobić, gdy przyjdzie czas

Ten sam wzorzec co etap 1 — architektura już stoi, dochodzi tylko treść:

1. **Inwentaryzacja** 755 wywołań: ile to realnych, różnych operacji (przy
   masterze 133 wywołania okazały się 17 zapisami i 8 odczytami — reszta to
   PRAGMA, migracje i obsługa połączenia).
2. **Operacje** do `rm_serwer_operacje` (osobna mapa albo prefiks `rmm-`).
3. **`rm_manager_gui` i `rm_manager`** przepięte na `rm_klient`.
4. **Pozostałe 9 programów** czytających te bazy: przez serwer albo snapshot —
   ta sama zasada co §16 („read-only to nie zwolnienie").
5. Cutover jak w §8.

Bazy projektowe RM_MANAGER (81 plików) są kandydatem na model `checkout`/
`checkin` z etapu 2 — ale tylko jeśli okaże się, że ktoś je edytuje pod lockiem.
Jeśli są zapisywane wprost, idą przez operacje jak `rm_manager.sqlite`.

## 21. Kiedy

**Po etapie 2**, przed etapem 3 albo równolegle z nim. Nie wcześniej: 755
wywołań to duża powierzchnia, a etapy 1 i 2 dają nam pewność, że wzorzec
działa, zanim zastosujemy go na czymś większym.

---

# CZĘŚĆ III — ETAP 3: pliki przez serwer — `Y:` znika z RM_BAZA

## 22. Co jeszcze RM_BAZA bierze z dysków sieciowych

Inwentaryzacja z kodu (po etapach 1 i 2 zostaje to):

| Ścieżka | Do czego | Kto | Propozycja |
|---|---|---|---|
| `Y:\SERVER_PROJEKTY` | rysunki DWF/PDF/DXF/STP/STL projektów; miniatury | arkusz, panel plików, wysyłka ZD, RFQ | `get_file(projekt, nazwa)` + lokalny cache |
| `B:\` | biblioteka RM — komponenty wspólne (`dwf_biblioteka=1`) | miniatury, „Szukaj w bibliotece" | **indeks** (§23) + `get_file` |
| `V:\` | drzewa złożeń Inventora (`_OUT.xlsx`), „Szukaj na serwerze" | import BOM, skany | **indeks** (§23) + `get_file` |
| `Y:\RM_BAZA\chat` | wiadomości JSON | chat | `chat-post` / `chat-poll` |
| `Y:\RM_BAZA\backups` | backupy projektów | okno „Przywróć backup" | już w etapie 2 (`backup-list/-get`) |
| `Y:\RMPAK_CLIENT\*.exe` | bramka wersji, samoaktualizacja | `client_version` | `client-version` + `client-download` |
| `Y:\RMPAK_CLIENT\iLogic\Subiekt\MOST` | dystrybucja mostu Subiekta | `subiekt_bridge` | `most-version` + `most-download` |
| `Y:\RM_BAZA\subiekt_mapowania.sqlite` | mapowania Subiekta | `subiekt_mapowania` | patrz §16 pkt 1 |
| `Y:\RM_MANAGER\` | bazy RM_MANAGER | RM_MANAGER, RM_STATS | **poza zakresem** — osobny program |

## 23. Dwie rzeczy do nazwania uczciwie

**„RM_BAZA bez `Y:`" to nie „stanowisko bez `Y:`".** Konstruktorzy pracują
w Inventorze i AutoCAD-zie na tych samych udziałach — one zostają. Zysk etapu 3
jest realny (RM_BAZA nie zależy od mapowania, poświadczeń i liter dysków), ale
dotyczy programu, nie infrastruktury.

**Skany plików to największa pozycja.** „Szukaj w bibliotece" i „Szukaj na
serwerze" to dziś `os.walk` po `B:` i `V:` z klienta (w wątkach, z „Anuluj" —
naprawionym 11.09).

**Decyzja: indeks, nie endpoint wyszukiwania.** Serwer skanuje `B:` i `V:` raz
(w tle, okresowo albo na sygnał zmiany), trzyma gotową listę plików w pamięci
lub małej bazie, klient tylko pyta „gdzie jest plik X" i dostaje odpowiedź
natychmiast — bez dotykania dysku sieciowego przy każdym wyszukaniu. Dziś ten
sam skan wolnego `B:`/`V:` robi osobno każdy z 10 klientów; indeks robi go raz
i wszyscy z niego korzystają.

Konsekwencje dla implementacji etapu 3:
- serwer potrzebuje własnego wątku odświeżającego indeks (interwał albo
  `watchdog`/zmiana mtime katalogu — do ustalenia przy kodowaniu);
- komenda `file-search(query)` zwraca trafienia z indeksu, nie z dysku;
- `get_file(projekt, nazwa)` zostaje osobno — services pobranie konkretnego
  pliku po znalezieniu go w indeksie;
- „Anuluj" ze skanu klienckiego (naprawione 11.09) znika wraz z samym skanem —
  odpytanie indeksu jest natychmiastowe, nie ma czego anulować.

## 24. Docelowe stanowisko

```
potrzebuje:                 nie potrzebuje:
  adres RM_SERWER             Y:  V:  B:  X:  Z:
  token klienta (HMAC)        \\nic\...
  C:\RMPAK_CLIENT\cache\      mapowania dysków przy logowaniu
                              poświadczeń SMB
                              „nie widzi udziału" / „inna litera dysku"
```

Etap 3 jest **do wyceny po etapie 2** — z ustaloną decyzją o indeksie (§23),
zostaje wycena samego mechanizmu odświeżania i objętości `B:`/`V:`.

---

## 25. Kontekst

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
| `project_rfq_zamowienia_subiekt` | WinRM na W2019S — jak wystawiono poprzedni serwer |
| `lock_manager_v2.py` | reguły locków przenoszone 1:1 w etapie 2 |

---

*Wersja 8, 11.09.2026 — trzy etapy; etap 1 gotowy do kodowania. Poprzednie
wersje w historii gita (`c6130ff`, `d3e2f6e`, `2cfec13`, `5c1a465`, `cbc721d`,
`5572370`, `9e70fae`). Plik zmienił nazwę z `PLAN_SERWER_MASTER.md`.*
