---
name: project_bazy_projektowe_konto_techniczne
description: "Decyzja 12.09.2026: bazy projektowe RM_MANAGER zostają plikami na udziale serwera, ukryte przed userami kontem technicznym (nie protokołem); wycena protokołu odrzucona"
metadata:
  type: project
---

**Decyzja (12.09.2026): bazy projektowe RM_MANAGER zostają plikami** na
udziale serwera, a dostęp zwykłych
userów blokuje **konto techniczne + uprawnienia NTFS**, nie protokół.

Warunek użytkownika: *„userzy z poziomu Windows Explorera nie mają prawa mieć
dostępu do tego folderu"* — ale bez płacenia za to wydajnością i przepisywaniem
kodu.

**Why:** przeniesienie projektów na protokół (jak master w
[[project_rm_serwer_etap25_domkniecie]]) wyceniono na 3 sesje: 370 zapytań
w 154 funkcjach. Pomiary pokazały, że przepisanie 1:1 dałoby **20× wolniej**
(96 zapytań przy samym otwarciu projektu × 2,5 ms = 240 ms wobec 12 ms na
plikach). Sensowne tylko z grupowaniem operacji, co jest istotą roboty, nie
dodatkiem. Konto techniczne daje ten sam efekt dla usera za zero pracy.

**Pomiary (11–12.09.2026, mediany):**

| | 1 odczyt | 20 odczytów | 1 zapis |
|---|---|---|---|
| Y: (stare) | 0,4 ms | 7 ms | 4,9 ms |
| udział serwera | 0,4 ms | 8 ms | 15,7 ms |
| protokół | 2,5 ms | 132 ms | 18,8 ms |

Batch 10 zapisów przez protokół = 23 ms wobec 152 ms pojedynczo — **grupowanie
decyduje o wydajności, nie wybór transportu**.

**How to apply:**
- Konto techniczne na serwerze (WORKGROUP, nie domena!) + `icacls` na katalogu:
  zdjąć dziedziczenie, usunąć `BUILTIN\Users`/`Everyone`, zostawić SYSTEM,
  Administratorów i konto techniczne. Program łączy się tym kontem, hasło
  w konfiguracji stacji; połączenie zapamiętane, żeby przeżyło restart.
- ⚠️ To zabezpieczenie **przed przypadkiem i ciekawskim, nie przed upartym** —
  hasło leży w konfiguracji na stacji. Pełną szczelność daje tylko protokół.
- ⚠️ **Udział SMB zawsze widać w Explorerze** — nie da się dać dostępu
  aplikacji, odbierając go człowiekowi. Ukryty udział (`$`) to zasłona, nie
  zabezpieczenie. Jedyne realne wyjścia to uprawnienia albo brak udziału.
- ⚠️ Ścieżka sieciowa w trybie URI wymaga **czterech ukośników**
  (`file:////serwer/udzial/plik.sqlite`) — przy dwóch SQLite rzuca
  „invalid uri authority". Poprawione w `db.open_ro`.
- ⚠️ Udział **tylko do odczytu nie działa wcale** — SQLite nie otworzy nawet
  do czytania (sprawdzone: „unable to open database file").
- HTTP zamiast własnego protokołu: narzut ułamka ms przy trwałym połączeniu,
  czyli bez znaczenia wobec latencji sieci. Nie rozwiązuje żadnego dzisiejszego
  problemu — wracać, gdy pojawi się potrzeba dostępu z zewnątrz.
- Blokady projektów już idą przez serwer niezależnie od tej decyzji —
  [[project_rm_serwer_etap25_domkniecie]].

**Struktura katalogów na serwerze (12.09.2026):**

```
C:\Apps\RM_SERWER\dane\Projekty\          <- udostępniony jako \W2019S\RM_SERWER
  RM_MANAGER_projects\   81 baz, przeniesione i zweryfikowane co do bajtu
  RM_BAZA_projects\      pusty — projekty RM_BAZA (87 + 7 magazynowych) DO ZROBIENIA 13.09.2026
```

Ścieżka klienta w `manager_sync_config.json`: `rm_projects_dir` =
`\W2019S\RM_SERWER\RM_MANAGER_projects` (BEZ segmentu `Projekty` — udział
już wskazuje na ten katalog, dopisanie go drugi raz dawało niewidoczną
ścieżkę).

**Pozostało z dzisiejszej pracy, PRZED założeniem konta technicznego:**
- Udział `RM_SERWER` na serwerze jest **wciąż otwarty dla wszystkich**
  (`Everyone: FullAccess`) — to placeholder do czasu konta technicznego,
  nie stan docelowy.
- RM_BAZA (87 projektów + 7 magazynowych z `Y:\RM_BAZA\projects` i
  `projects_MAG`) czeka na przeniesienie do `RM_BAZA_projects` — jutro.
  Przy skanowaniu natrafiono na plik niebędący bazą SQLite w tym katalogu —
  do zdiagnozowania przed przenosinami.
- Konto techniczne (`RM_KLIENT` czy podobne) + `icacls` na `Projekty` —
  zaplanowane, nie wykonane (blokada klasyfikatora auto mode na tworzenie
  kont/zmianę uprawnień — wymaga wykonania ręcznego albo trybu z jawną zgodą).

**12.09.2026, koniec sesji — dopisane po `ai_rules.txt` i teście obciążenia:**

- `ai_rules.txt` (kontekst firmowy dla asystenta AI w RM_MANAGER) przeniesiony
  z `Y:\RM_MANAGERi_rules.txt` na `\W2019S\RM_SERWERi_rules.txt`
  (leży bezpośrednio w katalogu `Projekty`, bo to jedyny udostępniony
  katalog — nie zakładać dla niego osobnego udziału). `manager_sync_config.json`
  → `ai_rules_path` zaktualizowane, sprawdzone na żywo. **RM_BAZA nie ma
  żadnego asystenta AI ani pliku reguł — to wyłącznie sprawa RM_MANAGER,
  nic tu nie trzeba robić po stronie RM_BAZA.**
- W oknie „Konfiguracja ścieżek" RM_MANAGER (menu Plik) zostały **martwe pola
  wskazujące na Y:**: `master.sqlite (RM_BAZA)`, `rm_manager.sqlite`, folder
  backupów, folder locków. Program je nadal zapisuje i pokazuje, ale po
  dzisiejszych zmianach nie są już czytane (master i locki idą przez
  `_master()` / `lock_manager_serwer`). Zmiana ich wartości dziś **nic by nie
  zmieniła** — czyszczenie okna z tych pól to osobna, nieodrobiona sprzątaczka.
- **Test obciążenia: 10 użytkowników piszących naraz do serwera — zero
  błędów, żaden zapis nie ginie.** Serwer ma jeden wątek roboczy (kolejka),
  więc zapisy idą pojedynczo: pojedynczy zapis ~17–28 ms, przy realnym rytmie
  pracy (0,5–2 s między akcjami) mediana 37 ms, ale w chwilach zbiegu
  90-percentyl skacze do ~640 ms, najgorszy zaobserwowany ~920 ms. To jest
  cena bezpieczeństwa (ta sama własność, która daje jednego zwycięzcę
  w wyścigu o blokadę), nie usterka. Przy 10 osobach i biurowym rytmie pracy
  — wystarcza z zapasem. Gdyby trzeba było skalować dalej: grupowanie
  zapisów w batch (jak `update_stage_definitions`) albo kilka wątków
  roboczych na osobnych połączeniach do bazy.

**Stan na koniec dnia 12.09.2026, do kontynuacji po `git pull`:**
- Wszystko wypchnięte, `origin/main` = `3f3f83e` + ta sesja bez nowych
  commitów kodu (tylko konfiguracja lokalna i pliki na serwerze).
- Jutro (13.09.2026): przenieść 87 projektów RM_BAZA + 7 magazynowych
  z `Y:\RM_BAZA\projects` / `projects_MAG` do już przygotowanego
  `C:\Apps\RM_SERWER\dane\Projekty\RM_BAZA_projects` — ta sama operacja
  co dziś dla RM_MANAGER (kopiuj, sumy kontrolne, przestaw `projects_dir`
  w konfiguracji RM_BAZA). W katalogu źródłowym są 2 pliki-śmieci
  (`project_22_before_restore_*.sqlite`, kopie zapasowe z kwietnia z
  wyzerowanym nagłówkiem — NIE przenosić, zostają na Y: jako archiwum).
- Konto techniczne (nazwa robocza `RM_KLIENT`) + `icacls` na
  `C:\Apps\RM_SERWER\dane\Projekty` do wykonania — zablokowane w tej
  sesji przez klasyfiator auto mode (tworzenie kont/zmiana uprawnień),
  wymaga wykonania ręcznego przez usera albo jawnej zgody w kolejnej sesji.
  Do czasu tego kroku udział `RM_SERWER` jest otwarty dla `Everyone`.
- Publikacja nowego `.exe` dla wszystkich stacji nadal nieodrobiona —
  dzisiejsza praca działa na razie tylko na tej stacji.
