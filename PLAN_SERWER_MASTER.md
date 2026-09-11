# Serwer master.sqlite — plan wdrożenia

Dokument wykonawczy. Wersja 6 (11.09.2026) — **gotowa do kodowania**.

| Zakres | Robota | Co naprawia |
|---|---|---|
| **Master przez serwer** | 3–4 dni | awarię z 11.09.2026 — u źródła |

> **Zmiany wobec wersji 5**: **read-only to nie zwolnienie** — narzędzia
> raportowe też nie mogą otwierać żywego mastera, bo czytelnik trzyma SHARED
> (§10, ze snapshotem jako rozwiązaniem); weryfikacja cutoveru przez
> **`handle.exe` na maszynie `nic`**, nie przez „Otwarte pliki" — po przenosinach
> na dysk lokalny tamta lista jest pusta zawsze (§8, §9); usunięte resztki po
> wyciętym serwerze locków w sekcji bezpieczeństwa.

> **Zmiana wobec wersji 4: LOCKI ZOSTAJĄ TAKIE, JAKIE SĄ.**
>
> Wersje 1–4 miały drugi etap — locki projektów przez serwer, z lease'ami,
> TTL, heartbeatem i `server_epoch`. **Wypadł z zakresu**, i słusznie: sam
> dokument przyznawał, że „naprawia problem, którego 11.09 nie było".
>
> Locki plikowe działają. `lock_manager_v2.py` ruszany cztery razy w całej
> historii repozytorium, bez śladu incydentu — nikt nie zgłosił zgubionej
> pracy ani dwóch osób w jednym projekcie. Bramka przed nadpisaniem cudzej
> pracy **już istnieje** i już sprawdza `lock_id` (RM_BAZA, `release_lock`;
> RM_MANAGER, `rm_manager.py:313` — „ostatnia bramka przed nadpisaniem
> cudzych danych"). Projektowałem od nowa coś, co jest.
>
> Refaktor działającego elementu bez bólu to koszt bez zysku. Zostaje jeden
> cel, dający się zmieścić w jednym zdaniu:
>
> ```
> dziś:        10 komputerów ──SMB──► master.sqlite
> po zmianie:  10 komputerów ──TCP──► serwer ──► master.sqlite
> ```
>
> Projekty i locki zostają całkowicie poza tym.
>
> Co odpadło: `rm_serwer_locki.py`, TTL, heartbeat, `server_epoch`,
> `lock-acquire/release/owner`, `lock-commit-start`, migracja 13 metod
> `lock_manager_v2`, bramka lease przed zapisem projektu i cała obsługa
> utraty lease.

> **Zmiany wobec wersji 3** (poprawki wykonawcze): `_server_request_log`
> **w masterze**, bez `ATTACH` — jedna baza, jeden journal, jedna transakcja
> (§3); **wycofanie programu ≠ odtworzenie bazy** — rollback nie kasuje pracy
> z całego dnia (§8); master na **lokalnym dysku** maszyny `nic`, SMB znika
> ze ścieżki do bazy (§1); kanoniczny JSON w HMAC (§7).
>
> **Zmiany wobec wersji 2**: klienci **nie otwierają** master.sqlite — także
> do odczytu (§4); **nie ma** automatycznego fallbacku per-klient (§5);
> `request_id` przeciw duplikatom po zerwanym TCP (§3); `master-exec`
> przyjmuje **nazwane operacje**, nigdy SQL (§3, §7); backup mastera
> przechodzi na serwer (§4); token HMAC w każdym żądaniu (§7).

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
    master.sqlite  +  backups/     (locks/ ZOSTAJĄ na Y: — poza zakresem)
```

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
otwiera `D:\RM_BAZA\master.sqlite`, a nie `\\nic\rysunki\RM_BAZA\master.sqlite`.
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
| Locki projektów | **działają normalnie** — pliki `.lock` na `Y:`, serwer ich nie dotyka |
| Praca na projekcie | trwa — kopia jest lokalna |
| Zwolnienie locka | **działa normalnie** — plik projektu idzie na `Y:` jak dziś |

**Minuta bez możliwości edycji jest lepsza niż cichy powrót do architektury, która
spowodowała 40-minutowe zakleszczenie.**

### Co z pracy na projektach przetrwa awarię serwera

**Wszystko.** Locki i pliki projektów są poza zakresem tej zmiany — klient bierze
lock z `Y:\RM_BAZA\locks`, pracuje na kopii lokalnej i oddaje plik na `Y:`
dokładnie tak jak dziś. Brak serwera oznacza wyłącznie: **nie zapiszesz danych
z mastera** (dostawcy, użytkownicy, ustawienia, statusy).

To jest mocna strona węższego zakresu: awaria serwera nie może zabrać nikomu
pracy nad projektem, bo serwer o projektach nic nie wie.

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

**`lock_manager_v2.py` — BEZ ZMIAN.** Locki plikowe zostają dokładnie takie,
jakie są.

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

`request_id` idzie w **każdym** żądaniu, także w odczytach — nie dla
idempotencji (odczyty jej nie potrzebują), lecz dlatego, że wchodzi do podpisu
i chroni przed powtórzeniem przechwyconego żądania.

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
    uchwyt do D:\RM_BAZA\master.sqlite ma WYLACZNIE proces RM_SERWER
```

Krok 3 jest istotny: dopóki któryś klient trzyma plik, serwer nie jest jedynym
właścicielem i cutover jest pozorny.

⚠️ **Kroki 3 i 8 sprawdzają co innego i innym narzędziem** — bo w międzyczasie
baza przeprowadza się z udziału sieciowego na dysk lokalny:

| | Gdzie leży master | Czym sprawdzić |
|---|---|---|
| **krok 3** (przed) | `Y:` — udział sieciowy | `\nic` → Zarządzanie komputerem → **Otwarte pliki** |
| **krok 8** (po) | `D:` na `nic` — lokalnie | na maszynie `nic`: `handle.exe master.sqlite` albo Process Explorer |

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

```
1. Zatrzymaj RM_SERWER
2. Zrób AWARYJNĄ kopię AKTUALNEGO mastera   ← bezcenne przy diagnozie
3. Wróć do starego .exe (RM_BAZA_v15_MAG.exe.przed_*)
4. Pracuj dalej na AKTUALNYM masterze
```

Schemat bazy się nie zmienia, więc stary klient czyta i pisze te dane bez
problemu — wraca tylko do robienia tego wprost po SMB.

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
  te pokazują tylko dostęp przez SMB, a baza leży już lokalnie). To jest dowód,
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

Po przeniesieniu bazy na `D:` maszyny `nic` te narzędzia i tak przestaną ją
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

## 11. Kontekst

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

*Wersja 6, 11.09.2026 — gotowa do kodowania. Poprzednie wersje w historii gita
(`c6130ff`, `d3e2f6e`, `2cfec13`, `5c1a465`, `cbc721d`).*
