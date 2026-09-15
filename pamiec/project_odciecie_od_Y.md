---
name: project-odciecie-od-y
description: "12.09.2026: RM_BAZA i RM_MANAGER odcięte od Y: — master, projekty, backupy, locki, KSeF, historia Subiekta i chat na serwerze; zostaje most Subiekta i tray"
metadata: 
  node_type: memory
  type: project
  originSessionId: 69849967-a91f-4896-bd40-f0b3f36b7447
  modified: 2026-09-12T16:42:38.070Z
---

**12.09.2026 oba programy przestały potrzebować `Y:`.** Wszystko, co tam leżało,
poszło na serwer; katalogi na `Y:` są przemianowane na `$nazwa` (nieaktywne).

| co | gdzie teraz |
|---|---|
| master RM_BAZA | protokół TCP (nie plik) — [[project_rm_baza_master_przez_serwer]] |
| projekty RM_BAZA (92) | `\\W2019S\RM_SERWER$\RM_BAZA_projects` |
| projekty RM_MANAGER (81) | `\\W2019S\RM_SERWER$\RM_MANAGER_projects` |
| backupy obu (7236 plików) | `RM_SERWER$\backup_RM_BAZA` i `backup_RM_MANAGER` |
| blokady | tabela `project_locks` — [[project_locki_rm_baza_serwer]] |
| faktury KSeF | `dane\FV_KSEF.sqlite`, **XML w kolumnie `xml`** |
| historia Subiekta (25) | `RM_SERWER$\subiekt_historia` |
| chat (25) | `RM_SERWER$\chat` |
| sekret HMAC | `RM_SERWER$\HMAC.json` (był `sync_config.json` na Y:) |

**RM_STATS i RM_SERWIS** (kod w repo NOW, usługi NSSM na serwerze, porty 5050
i 5058, konto `.\mongo`) — **wspólny `config.json`** w `C:\Apps\NOW\RM_STATS\`.
Miały tam `\\nic\rysunki\RM_BAZA\...` (czyli `Y:` widziane z serwera), więc po
przemianowaniu katalogów każde `/api/*` zwracało **500**. Przestawione na
ścieżki LOKALNE (`C:\Apps\RM_SERWER\dane\...`) — usługi chodzą na tej samej
maszynie co bazy, sieć jest im niepotrzebna. W repo NOW leży osobny config
z `Y:`, nietknięty.

**RM_PRINT** (repo NOW, zadanie harmonogramu, port 5055) — własny
`webapp\config.json` z tymi samymi martwymi ścieżkami; poprawione tak samo.
Ścieżki do RYSUNKÓW (`\\nic\PROJEKTY`, `\\nic\BIBLIOTEKA`) zostają — to inne
udziały, nietykane. Przy okazji dwie optymalizacje (commit `580ca88` w NOW):
`/api/projects` 6243→257 ms i `/api/project/*/drawings` 4338→777 ms. W obu
przypadkach ten sam błąd: pytanie dysku sieciowego w pętli o to samo
(`iterdir()` raz na projekt; `entry.is_dir()` osobno dla każdego wpisu →
`os.walk`). Lokalnie niewidoczne, po SMB kosztowało sekundy.

⚠️ **Rozwijanej listy `<select>` NIE da się poprawić** — rysuje ją przeglądarka.
Próba zamiany na `size` + własne pozycjonowanie zepsuła scroll, hover i wyjście
poza okno; cofnięte. Jedyna sensowna droga, gdyby wrócić do tematu, to gotowa
biblioteka (Choices.js), nie własna implementacja.

**⚠️ ZOSTAJE NA `Y:`:**
- ~~Most Subiekta na Y:~~ — **od 14.09.2026 most leży na `\\W2019S\RM_SERWER$\MOST`** (`udzial_serwera.UDZIAL`
  + podfolder MOST), `subiekt_bridge` nie zna już liter dysków, a stary `paths.bridge_dir`
  z configu stacji jest pomijany. `Y:\...\MOST` NIE jest aktualizowane; stare `.exe` szukają
  tam do czasu aktualizacji RM_BAZA. Na `Y:` zostaje TYLKO `RMPAK_CLIENT\RM_BAZA_v15_MAG.exe`.
- **`RM_Tray_Organizer`** (repo NOW) liczy katalog chatu jako
  `master.sqlite`.parent / "chat" → `Y:\RM_BAZA\chat`. Dopóki user tego nie
  poprawi, **chat jest rozjechany**: RM_BAZA pisze na serwer, tray czyta z Y:,
  bez żadnego błędu — po prostu nie widzą swoich wiadomości.

**How to apply:**
- ⚠️ **Wzorzec, który powtórzył się 5 razy**: ścieżka liczona z `master_path`
  albo `PROJECTS_DIR` (`Path(master_path).parent / "cos"`). Po przejściu mastera
  na serwer wskazuje katalog, którego nie ma. Tak psuły się: faktury KSeF,
  historia Subiekta, cache `subiekt_katalog.json`, chat, `projects_path`.
  Szukając podobnego błędu — grepować `master_path).parent` i `dirname(PROJECTS_DIR`.
- ⚠️ **Puste katalogi wracały po skasowaniu** — `mkdir(exist_ok=True)` przy
  starcie: `Y:\RM_BAZA\locks` (RM_BAZA), `LOCKS` (RM_MANAGER, przy zapisie
  konfigu), `faktury_ksef` (konstruktor ArchiwumKsef). Usunięte.
- ⚠️ **Weryfikacja plików projektu czyta ścieżkę z tabeli
  `project_file_tracking`, nie z konfiguracji.** Wpisy miały pięć różnych liter
  dysku (W: 51, U: 25, Y: 2, X: 2, V: 1). Objaw: czerwony pasek „PLIK PROJEKTU
  NIE ISTNIEJE" na każdym projekcie. Naprawa: **Narzędzia → Resetuj śledzenie
  wszystkich projektów** (nie poprawianie konfigu!).
- Migracje ścieżek w locie: `_na_ukryty_udzial()` i `_na_projekty_rm_bazy()`
  w `rm_manager_gui` — stacje dostaną poprawkę z nowym `.exe`, bez obchodzenia
  dziesięciu komputerów.
- ⚠️ Konfig edytować przy ZAMKNIĘTYM programie — zapisuje go przy wyjściu.
- ⚠️ **`Set-Content -Encoding UTF8` w Windows PowerShell DOKŁADA BOM.** Złapało
  mnie 12.09 dwa razy: `manager_sync_config.json` (program poszedł w wartości
  domyślne i pokazał je w oknie konfiguracji) i `config.json` RM_STATS (obie
  usługi przestały wstawać z `JSONDecodeError`, bo `db.py` czyta `utf-8` bez
  `-sig`). Zapisywać przez Edit/Write albo
  `[System.IO.File]::WriteAllText(p, t, (New-Object System.Text.UTF8Encoding($false)))`.

**Zostało do zrobienia:**
- **Build `.exe`** — 9 stacji chodzi na starym, wciąż szuka na `Y:`.
- Skasować `$`-katalogi z `Y:` po potwierdzeniu (2,55 GB samych backupów).
- `icacls` + konto techniczne — udział nadal `Everyone: Full`.

**Odbiór użytkowników 14.09.2026:** po przenosinach na RM_SERWER i poprawkach
z tego dnia — *„RM_BAZA działa sprawnie i szybko, userzy chwalą"*. Stan bazowy
jest DOBRY: przy kolejnych zmianach w warstwie dostępu do danych (master przez
protokół, blokady w tabeli, projekty jako pliki na udziale) to punkt odniesienia
— jeśli po zmianie ktoś zgłosi „muli", szukać regresji, nie „tak było zawsze".
