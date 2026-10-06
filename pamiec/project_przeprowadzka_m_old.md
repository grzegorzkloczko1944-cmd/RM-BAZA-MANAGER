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
Win10 Pro 19045). **W gicie jest tylko kod** — całe środowisko (udawany
serwer, Subiekt demo, klucze, bazy, konfiguracje) jest poza gitem.

## ⚠ Tylko na tym dysku — przepadnie bez kopii

| co | gdzie | stan 07.10 |
|---|---|---|
| repo **Recorder** | `Repozytoria\Recorder` | **brak remote** — cała historia tylko lokalnie; decyzja usera otwarta (GitHub albo `git bundle`) |
| zmiany RM_ZJAZD (4 pliki) | NOW | niezacommitowane |
| keystore Androida `rm_mail.jks` + `keystore.properties` | `NOW\RM_NOTATKA_ANDROID` | bez nich nie da się wydać aktualizacji aplikacji |
| klucze `.ai_api_key`, `master.sqlite`, `rm_serwer_config.json`, `sync_agent_run.bat` | RM-BAZA-MANAGER (gitignore) | |
| `config.json` + bazy RM_RFQ / RM_VIDEO / RM_STATS / RM_ARCHIWUM / RM_DWF / RM_PRINT | NOW (gitignore) | sekrety + dane |
| `sync_config.json`, `.nexo_sfera.json`, `widocznosc_kolumn.json`, `subiekt_*.json` | `C:\RMPAK_CLIENT\` | konfiguracja per maszyna |
| SDK nexo **61.1.0.9431** | `C:\iLogic\Subiekt_nexo_PRO_dokumentacja\SDK\` | most się bez niego nie zbuduje |
| instalator `InsERT_nexo.exe` | `Downloads` | wersja MUSI = SDK = firma (61.1.0.9431); ze strony może przyjść nowsza |
| bazy SQL `Nexo_RMPRODUKCJA`, `InsERT_Launcher` | instancja `.\INSERTNEXO` | dane testowe Subiekta |
| `C:\Users\herrm\.claude` (734 MB) | profil | historia rozmów, ustawienia, mail-mcp, skrypty sync |

Gałąź `kadry-wip-backup` (ca5cc40) — **skasowana 07.10 na polecenie usera**
(„niepotrzebne"), na GitHubie jej nie było.

## Etap 1 — stary komputer

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
   Udziałów na `D:\` (Maszyny, projekty morfeusz/pietryna/mono) NIE
   odtwarzać — dysku D: już nie było, były martwe.
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
   (pierwszy `git fetch`), NAS i udziały `192.168.100.x`, `NIC`, `ss2`
   (`cmdkey` / pierwsze otwarcie udziału).
9. **Test:** `git status` w każdym repo = to samo co przed kopią;
   start `rm_serwer.py` → `RM_BAZA_v15_MAG_STATS_ORG.py` → `rm_manager_gui.py`;
   most Subiekta (`subiekt_sfera/bridge_test.py`).

Powiązane: [[project_srodowisko_domowe_m_old]] [[project_subiekt_integracja_m_old]]
[[project_porzadki_01_10_do_powtorzenia_w_domu]] [[feedback_most_rebuild_release]]
