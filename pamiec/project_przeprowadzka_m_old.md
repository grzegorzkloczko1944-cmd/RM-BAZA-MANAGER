---
name: project_przeprowadzka_m_old
description: Procedura przenosin domowego M-OLD na nowy komputer/Windows - co jest TYLKO na dysku, kopia, odtworzenie srodowiska testowego (udawany W2019S, Subiekt demo, junctiony)
metadata:
  type: project
---

# Przeprowadzka M-OLD na nowy komputer (spisane 07.10.2026)

User zmienia komputer i Windowsa. Cel: oba repo (RM-BAZA-MANAGER, NOW)
w stanie 1:1 i działające **domowe środowisko testowe** RM_BAZA_MANAGER.

Inwentaryzacja zrobiona 07.10 na starym M-OLD (Lenovo 10TV0024PB, i5-8400,
Win10 Pro 19045, sieć domowa `192.168.68.x`). **Dotyczy TYLKO domu** —
firma (W2019S, `192.168.100.x`, NAS NIC) ma osobną listę:
[[project_wdrozenie_firma_04_10_2026]]. **W gicie jest tylko kod** — całe środowisko (udawany
serwer, Subiekt demo, klucze, bazy, konfiguracje) jest poza gitem.

## ⚠ Tylko na tym dysku — przepadnie bez kopii

| co | gdzie | stan 07.10 |
|---|---|---|
| repo **Recorder** | `Repozytoria\Recorder` | **brak remote** — cała historia tylko lokalnie; decyzja usera otwarta (GitHub albo `git bundle`) |
| ~~zmiany RM_ZJAZD (4 pliki)~~ | NOW | ✅ zacommitowane i wypchnięte 07.10 (1cd9a6e i wcześniejsze) |
| keystore Androida `rm_mail.jks` + `keystore.properties` | `NOW\RM_NOTATKA_ANDROID` | bez nich nie da się wydać aktualizacji aplikacji |
| klucze `.ai_api_key`, `master.sqlite`, `rm_serwer_config.json`, `sync_agent_run.bat` | RM-BAZA-MANAGER (gitignore) | |
| `config.json` + bazy RM_RFQ / RM_VIDEO / RM_STATS / RM_ARCHIWUM / RM_DWF / RM_PRINT | NOW (gitignore) | sekrety + dane |
| `sync_config.json`, `.nexo_sfera.json`, `widocznosc_kolumn.json`, `subiekt_*.json` | `C:\RMPAK_CLIENT\` | konfiguracja per maszyna |
| SDK nexo **61.1.0.9431** | `C:\iLogic\Subiekt_nexo_PRO_dokumentacja\SDK\` | most się bez niego nie zbuduje |
| instalator `InsERT_nexo.exe` | `Downloads` | wersja MUSI = SDK = firma (61.1.0.9431); ze strony może przyjść nowsza |
| bazy SQL `Nexo_RMPRODUKCJA`, `InsERT_Launcher` | instancja `.\INSERTNEXO` | dane testowe Subiekta |
| `C:\Users\herrm\.claude` (734 MB) | profil | historia rozmów, ustawienia, mail-mcp, skrypty sync |
| `C:\Users\herrm\.claude.json` | profil, **obok** katalogu `.claude` | rejestracje serwerów MCP: `mail` i `inventor` (most do Inventora z 07.10, `NOW/RM_INVENTOR_MCP`); bez niego `claude mcp add` od nowa — komendy w README mostu |

Gałąź `kadry-wip-backup` (ca5cc40) — **skasowana 07.10 na polecenie usera**
(„niepotrzebne"), na GitHubie jej nie było.

## ✅ WARIANT WYBRANY (07.10): stary dysk jako D: w nowym komputerze

> ⚠ **Litera D: jest zajęta** przez zewnętrzny USB WD Elements (udziały
> `Maszyny`, `projekty …` wskazują na `D:\…`). Stary NVMe podpiąć pod
> **inną literę (np. E:)** i w poleceniach niżej czytać `E:` zamiast `D:`
> — inaczej po przeprowadzce udziały z WD Elements trafią w pustkę.

User podepnie stary NVMe do nowego komputera jako **D:**, a agent na nowym
komputerze kopiuje z D: na C:. Kopia na dysk zewnętrzny (Etap 1 niżej)
**odpada** — stary dysk sam jest źródłem.

**Przygotowane na starym dysku 07.10** w `C:\RMPAK_CLIENT\_przeprowadzka\`
(na nowym: `D:\RMPAK_CLIENT\_przeprowadzka\`):
* `pip_freeze.txt` — 158 pakietów Pythona,
* `zadanie_RM_SYNC_AGENT.xml`, `zadanie_RM_RFQ_BACKUP.xml`,
  `zadanie_ClaudeMemorySync.xml`.

Bazy Subiekta zbackupowane 07.10 02:04 (`COPY_ONLY`) do katalogu instancji:
`D:\Program Files\Microsoft SQL Server\MSSQL15.INSERTNEXO\MSSQL\Backup\`
`Nexo_RMPRODUKCJA.bak` (373 MB), `InsERT_Launcher.bak` (598 MB). Do tego
katalogu zwykły user nie ma dostępu — czytać jako admin.

**Sprawdzone przed wyłączeniem:** BitLocker na C: **wyłączony** (dysk
czytelny bez klucza odzyskiwania). Szybkie uruchamianie: w rejestrze
`HiberbootEnabled=1`, ale `hiberfil.sys` brak → nieaktywne; i tak wyłączyć
**pełnym zamknięciem** (`shutdown /s /t 0`), żeby NTFS był czysty.

**Fizycznie:** nowy komputer potrzebuje wolnego slotu M.2 NVMe (albo
obudowy USB-NVMe). Stary dysk ma własny Windows i partycję EFI —
w BIOS-ie start z **NOWEGO** dysku. Literę D: nadać w Zarządzaniu dyskami.

**Kopiowanie na nowym komputerze** (PowerShell **jako administrator**):

```powershell
$o = '/E','/XJ','/B','/COPY:DAT','/R:1','/W:1','/NFL','/NDL'
robocopy D:\RMPAK_CLIENT  C:\RMPAK_CLIENT  @o
robocopy D:\iLogic        C:\iLogic        @o
robocopy D:\BibliotekaRM  C:\BibliotekaRM  @o
robocopy D:\Biblioteka    C:\Biblioteka    @o
robocopy D:\test          C:\test          @o
robocopy D:\Projekty      C:\Projekty      @o
robocopy D:\Users\herrm\.claude "$env:USERPROFILE\.claude" @o
Copy-Item D:\Users\herrm\.claude.json "$env:USERPROFILE\.claude.json"   # rejestracje MCP: mail, inventor
robocopy "D:\Program Files\Microsoft SQL Server\MSSQL15.INSERTNEXO\MSSQL\Backup" C:\RMPAK_CLIENT\_przeprowadzka *.bak /B
Copy-Item D:\Users\herrm\Downloads\InsERT_nexo.exe C:\RMPAK_CLIENT\_przeprowadzka\
```

* `/B` (tryb kopii zapasowej, wymaga admina) — pliki na D: mają
  uprawnienia **starego** użytkownika (inny SID na nowym Windowsie,
  zwłaszcza `D:\Users\herrm`); bez `/B` będzie „odmowa dostępu".
* `/COPY:DAT` **bez** właściciela i ACL — kopie należą do nowego usera,
  więc git nie zgłosi „detected dubious ownership".
* `/XJ` — junctiony odtworzyć ręcznie (krok 4 Etapu 2); wskazują na
  `C:\RMPAK_CLIENT\...`, więc po kopii na C: będą znów poprawne.

**Uprawnienia NTFS na starym dysku (sprawdzone 07.10)** — nowy Windows
nie zna starego konta `M-OLD\herrm` (inny SID), ale grupy wbudowane mają
ten sam SID wszędzie:

| folder | ACL | z nowego Windowsa |
|---|---|---|
| `RMPAK_CLIENT`, `BibliotekaRM` | Wszyscy: pełne | odczyt i zapis |
| `iLogic` | Użytkownicy uwierzytelnieni: modyfikacja | odczyt i zapis |
| `Projekty`, `test` | Wszyscy: odczyt | tylko odczyt — do kopii wystarczy |
| `Users\herrm\.claude` | herrm + Administratorzy + SYSTEM | tylko jako admin (`/B`) |

`Projekty` i `test` **celowo NIE otwierane** na zapis dla Wszystkich —
to udziały sieciowe, pełne NTFS dla Wszystkich = zapis dla każdego z LAN.

**Git — „detected dubious ownership"**: właścicielem plików na D: jest
stary SID, a git odmawia pracy z repo innego właściciela. Zgody **nie da
się zapisać w repo** (git ignoruje `safe.directory` z `.git/config`
celowo, ze względów bezpieczeństwa) — tylko na maszynie, raz:

```powershell
git config --global --add safe.directory "*"
```

Po kopii na C: z `/COPY:DAT` niepotrzebne (kopie należą do nowego usera),
ale konieczne, gdy pracuje się z repo prosto na D:. Praca prosto z D:
wymaga też junctiona `C:\RMPAK_CLIENT` → `D:\RMPAK_CLIENT` — ścieżka
`C:\RMPAK_CLIENT` jest na sztywno w 35 plikach RM-BAZA-MANAGER i 11 w NOW
(m.in. `DEFAULT_LOCAL_DIR`). Wybrany wariant to kopia, nie praca z D:.

Potem **Etap 2 od kroku 1** (instalacje → udziały/hosts/rejestr/junctiony
→ Subiekt → zadania → test). Zadania importować z `_przeprowadzka\*.xml`,
bazy przywracać z `_przeprowadzka\*.bak`.

Stary dysk **zostawić nietknięty** do czasu, aż na nowym przejdzie test
z kroku 9 — to jedyna pełna kopia (Recorder nie ma remote).

## Etap 1 — stary komputer (wariant z dyskiem zewnętrznym — NIEUŻYWANY)

Zamknąć RM_BAZA, RM_MANAGER, rm_serwer, Subiekta, Inventora (spójne SQLite).
Wyłączyć zadanie `RM_SYNC_AGENT` na czas kopii.

```powershell
$K = 'X:\M-OLD_kopia'          # dysk zewnętrzny / NAS — NIE Google Drive (sekrety)
$o = '/E','/XJ','/COPY:DAT','/R:1','/W:1','/NFL','/NDL'
robocopy C:\RMPAK_CLIENT  "$K\RMPAK_CLIENT"  @o
robocopy C:\iLogic        "$K\iLogic"        @o
robocopy C:\BibliotekaRM  "$K\BibliotekaRM"  @o   # 16,6 GB, dysk B:
robocopy C:\Biblioteka    "$K\Biblioteka"    @o   #  5,4 GB
robocopy C:\test          "$K\test"          @o   #  8,7 GB, dysk V:
robocopy C:\Projekty      "$K\Projekty"      @o   # 116 GB
robocopy "$env:USERPROFILE\.claude" "$K\.claude" @o
Copy-Item "$env:USERPROFILE\Downloads\InsERT_nexo.exe" $K

# zadania harmonogramu
foreach ($t in 'RM_SYNC_AGENT','RM_RFQ_BACKUP','ClaudeMemorySync') {
  schtasks /Query /TN "\$t" /XML | Out-File "$K\zadanie_$t.xml" -Encoding unicode }

# pakiety Pythona
python -m pip freeze | Out-File "$K\pip_freeze.txt" -Encoding utf8
```

`/XJ` pomija junctiony — inaczej `RM_SERWER_UDZIAL` skopiowałby `RM_BAZY`
drugi raz. Junctiony odtwarza się ręcznie (etap 2).

**Bazy Subiekta** — sqlcmd nie ma, idzie przez .NET; plik ląduje
w domyślnym katalogu backupu instancji (`...\MSSQL15.INSERTNEXO\MSSQL\Backup`),
skąd trzeba go skopiować do `$K`:

```powershell
$c = New-Object System.Data.SqlClient.SqlConnection 'Server=.\INSERTNEXO;Integrated Security=true;Database=master'
$c.Open()
foreach ($db in 'Nexo_RMPRODUKCJA','InsERT_Launcher') {
  $cmd = $c.CreateCommand(); $cmd.CommandTimeout = 600
  $cmd.CommandText = "BACKUP DATABASE [$db] TO DISK = N'$db.bak' WITH COPY_ONLY, INIT"
  [void]$cmd.ExecuteNonQuery() }
$c.Close()
```

## Etap 2 — nowy komputer (kolejność ma znaczenie)

1. **Nazwa komputera `M-OLD`, użytkownik `herrm`** — gdy stary idzie
   w odstawkę. Wtedy ścieżki w zadaniach, mapowania B:/V:
   (`\\M-OLD\...`) i katalog pamięci Claude działają bez zmian. Inna
   nazwa → poprawić mapowania i zadania.
2. **Instalacje:** Git · Python 3.12 (per-user, ścieżka
   `%LOCALAPPDATA%\Programs\Python\Python312`) + `pip install -r pip_freeze.txt`
   · .NET SDK 8 · `InsERT_nexo.exe` 61.1.0.9431 (stawia SQL 2019 Express
   `INSERTNEXO`; pułapki instalacji: `subiekt_sfera/INSTALACJA_DOMOWA_NOTATKI.md`)
   · Inventor 2013 · Google Drive · VS Code + Claude Code.
3. **Przywrócić katalogi pod TE SAME ścieżki** (`robocopy $K\... C:\...`).
   Repo musi leżeć w `C:\RMPAK_CLIENT\Repozytoria\` — od tej ścieżki zależy
   nazwa katalogu pamięci Claude (`c--RMPAK-CLIENT-Repozytoria-RM-BAZA-MANAGER`).
4. **Udawany W2019S** (szczegóły: [[project_srodowisko_domowe_m_old]]),
   PowerShell jako administrator:

```powershell
New-SmbShare -Name 'RM_SERWER$' -Path 'C:\RMPAK_CLIENT\RM_SERWER_UDZIAL' -FullAccess 'Wszyscy'
Add-Content "$env:windir\System32\drivers\etc\hosts" "`r`n127.0.0.1`tW2019S"
New-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Lsa\MSV1_0' `
  -Name BackConnectionHostNames -PropertyType MultiString -Value 'W2019S' -Force
New-Item -ItemType Junction -Path C:\RMPAK_CLIENT\RM_SERWER_UDZIAL\RM_BAZA_projects `
  -Target C:\RMPAK_CLIENT\RM_BAZY\RM_BAZA\projects
New-Item -ItemType Junction -Path C:\RMPAK_CLIENT\RM_SERWER_UDZIAL\RM_MANAGER_projects `
  -Target C:\RMPAK_CLIENT\RM_BAZY\RM_MANAGER\RM_MANAGER_projects
# pozostałe udziały
New-SmbShare -Name BibliotekaRM -Path C:\BibliotekaRM -FullAccess 'Wszyscy'
New-SmbShare -Name Biblioteka   -Path C:\Biblioteka   -FullAccess 'Wszyscy'
New-SmbShare -Name test         -Path C:\test         -FullAccess 'Wszyscy'
New-SmbShare -Name Projekty     -Path C:\Projekty     -FullAccess 'Wszyscy'
New-SmbShare -Name RMPAK_CLIENT -Path C:\RMPAK_CLIENT -FullAccess 'Wszyscy'
```

   Potem **restart Windowsa** (BackConnectionHostNames), dopiero wtedy
   mapowania (jako zwykły user, nie admin):
   `net use B: \\M-OLD\BibliotekaRM /persistent:yes` i
   `net use V: \\M-OLD\test /persistent:yes`.
   Udziały na `D:\` (`Maszyny`, `projekty morfeusz`, `projekty pietryna`,
   `projekty2` → `D:\projekty mono\projekty`) **są prawdziwe** — D: to
   zewnętrzny USB **WD Elements 1,4 TB**, który bywa odłączony (07.10 rano
   go nie było i błędnie uznałem te udziały za martwe). Odtworzyć je, gdy
   WD Elements jest podłączony jako D:.
5. **Pamięć Claude** — junction wg `CLAUDE.md` (sekcja „Ustawienie na
   nowej maszynie"). Robocopy z `/XJ` go nie przeniósł.
6. **Subiekt:** przywrócić bazy (`RESTORE DATABASE ... WITH REPLACE`) albo
   archiwizacją w samym nexo; most:
   `dotnet build -c Release -nowarn:MSB3277` w `subiekt_sfera\NexoRecon`
   (`bin/` jest w gitignore). Licencja demo: 45 dni od 03.09.2026, czyli
   koniec ok. **18.10.2026** — niezależnie od przeprowadzki.
7. **Zadania:** `schtasks /Create /TN "RM_SYNC_AGENT" /XML zadanie_RM_SYNC_AGENT.xml`
   (i dwa pozostałe).
8. **Poświadczenia** — Windows ich nie przeniesie: logowanie do GitHuba
   (pierwszy `git fetch`). Nic więcej dla środowiska domowego.
   ⚠ W Menedżerze poświadczeń starego M-OLD wiszą wpisy `192.168.100.x`,
   `NIC`, `ss2` — to **sieć FIRMOWA** (dom = `192.168.68.x`, z domu
   nieosiągalne, sprawdzone 07.10). NIE są częścią środowiska domowego,
   nie odtwarzać (pomyłka w pierwszej wersji procedury, wytknięta przez usera).
9. **Test:** `git status` w każdym repo = to samo co przed kopią;
   start `rm_serwer.py` → `RM_BAZA_v15_MAG_STATS_ORG.py` → `rm_manager_gui.py`;
   most Subiekta (`subiekt_sfera/bridge_test.py`).
10a. **Strażnik kopii między repo** (od 10.10.2026) — w OBU repo raz:
    `git config core.hooksPath .githooks`, potem `python sprawdz_kopie.py` = „zgodnych”.
    Szczegóły: CLAUDE.md → „WSPÓLNE PLIKI Z DRUGIM REPO”.
10. **Wygląd jak Windows 10** (nowy komputer ma Windows 11; user 09.10.2026 —
    „dopisz”). Bez instalacji:
    - pasek zadań / Start do lewej: Ustawienia → Personalizacja → Pasek zadań →
      Zachowania paska zadań → Wyrównanie: do lewej; tam też schować Widżety,
      Czat, Widok zadań;
    - klasyczne menu pod prawym przyciskiem (bez „Pokaż więcej opcji”), potem
      wylogowanie albo restart Eksploratora:
      `reg add "HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32" /f /ve`
      (powrót: `reg delete "HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}" /f`).
    Pełny wygląd Win10 (Start, pasek zadań, Eksplorator ze wstążką) — program:
    **StartAllBack** (zalecany: najstabilniejszy, ok. 5 USD, 100 dni próby);
    alternatywy ExplorerPatcher (darmowy, psują go aktualizacje Windows, Defender
    bywa podejrzliwy) albo Open-Shell (tylko menu Start). Zapytać usera, czy
    instalować — to program spoza repo.

Powiązane: [[project_srodowisko_domowe_m_old]] [[project_subiekt_integracja_m_old]]
[[project_porzadki_01_10_do_powtorzenia_w_domu]] [[feedback_most_rebuild_release]]
