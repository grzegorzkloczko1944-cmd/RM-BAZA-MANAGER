# Środowisko domowe na M-OLD

**Po co to jest:** kod RM_BAZA ma ścieżki do firmowego serwera **wpisane na sztywno**
(`\\W2019S\RM_SERWER$`). W domu takiego serwera nie ma. Zamiast przerabiać kod — co
zepsułoby wersję firmową i wymagałoby pilnowania dwóch wariantów w jednym repo —
**dom udaje serwer W2019S**. Kod nie wie, że jest w domu.

Spisane 13.09.2026 z rzeczywistego stanu maszyny (nie z pamięci).

---

## 1. Dlaczego akurat tak

Rozważane były trzy drogi:

| wariant | dlaczego odpadł / przeszedł |
|---|---|
| zmiana ścieżek w kodzie | ❌ ryzyko wypuszczenia domowej ścieżki na produkcję |
| zmienne środowiskowe / config | ❌ trzeba dotknąć kilkunastu miejsc w kodzie, to praca na inny dzień |
| **udawany udział SMB** | ✅ **zero zmian w kodzie**, konfiguracja żyje poza repo |

Konsekwencja: `git pull` **nigdy nie miesza domu z firmą**, bo cała różnica siedzi
w plikach, których git nie śledzi (patrz §6).

---

## 2. Sieć — nazwa `W2019S`

### 2.1 Rozwiązywanie nazwy

Plik `C:\Windows\System32\drivers\etc\hosts`:

```
127.0.0.1	W2019S
```

### 2.2 ⚠️ Odblokowanie SMB (najważniejszy krok)

Windows **blokuje** dostęp do udziału własnego komputera pod obcą nazwą — to ochrona
przed atakiem typu NTLM reflection. Objaw jest mylący: udział **działa** przez
`\\localhost\`, `\\M-OLD\` i `\\127.0.0.1\`, a przez `\\W2019S\` **nie**, mimo że
nazwa poprawnie rozwiązuje się na 127.0.0.1.

Lekarstwo — rejestr `HKLM\SYSTEM\CurrentControlSet\Control\Lsa\MSV1_0`,
wartość **`BackConnectionHostNames`** (typ `MultiString`) = `W2019S`:

```powershell
# PowerShell JAKO ADMINISTRATOR
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\Lsa\MSV1_0" `
  -Name "BackConnectionHostNames" -Value "W2019S" -PropertyType MultiString -Force
Restart-Service LanmanServer -Force
```

Ten wpis mówi Windowsowi: „nazwa `W2019S` to ja sam, wpuść". Dotyczy **wyłącznie tej
jednej nazwy**.

> **Nie używać `DisableLoopbackCheck`.** Załatwia ten sam objaw, ale wyłącza ochronę
> globalnie, dla wszystkich nazw.

---

## 3. Udział SMB

```powershell
# PowerShell JAKO ADMINISTRATOR
New-SmbShare -Name 'RM_SERWER$' -Path 'C:\RMPAK_CLIENT\RM_SERWER_UDZIAL' -FullAccess 'Wszyscy'
```

> **`Wszyscy`, nie `Everyone`** — na polskim Windowsie `Everyone` nie istnieje i
> `New-SmbShare` kończy się błędem *Windows System Error 1332* („nie zmapowano nazw
> kont"). Sprawdzone przez SID `S-1-1-0`.

Stan faktyczny:

| pole | wartość |
|---|---|
| Name | `RM_SERWER$` |
| Path | `C:\RMPAK_CLIENT\RM_SERWER_UDZIAL` |
| Dostęp | `Wszyscy` — `Allow` / `Full` |

---

## 4. Zawartość udziału — junctiony, nie kopie

`C:\RMPAK_CLIENT\RM_SERWER_UDZIAL\`:

```
backup_RM_BAZA          <DIR>        ← zwykły katalog, RM_BAZA sama tu pisze backupy dobowe
backup_RM_MANAGER       <DIR>        ← zwykły katalog
chat                    <DIR>        ← zwykły katalog
RM_BAZA_projects        <JUNCTION>   → C:\RMPAK_CLIENT\RM_BAZY\RM_BAZA\projects
RM_MANAGER_projects     <JUNCTION>   → C:\RMPAK_CLIENT\RM_BAZY\RM_MANAGER\RM_MANAGER_projects
```

Bazy **nie są kopiowane** — junction to dowiązanie katalogowe, więc istnieje jeden
komplet danych. Zapis przez `\\W2019S\...` i zapis lokalny trafiają w ten sam plik,
nie ma ryzyka rozjazdu dwóch kopii.

```powershell
New-Item -ItemType Junction -Path 'C:\RMPAK_CLIENT\RM_SERWER_UDZIAL\RM_BAZA_projects' `
  -Target 'C:\RMPAK_CLIENT\RM_BAZY\RM_BAZA\projects'
New-Item -ItemType Junction -Path 'C:\RMPAK_CLIENT\RM_SERWER_UDZIAL\RM_MANAGER_projects' `
  -Target 'C:\RMPAK_CLIENT\RM_BAZY\RM_MANAGER\RM_MANAGER_projects'
```

### HMAC — świadomie pominięty

Kod szuka `\\W2019S\RM_SERWER$\HMAC.json` (`RM_BAZA_v15…py:379`, `rm_klient.py:83`).
W domu tego pliku **nie ma** i tak ma zostać — HMAC został wyłączony, a kod znosi brak
pliku po cichu.

---

## 5. Pliki konfiguracyjne

### 5.1 `C:\RMPAK_CLIENT\sync_config.json` — poza repozytorium

```json
"paths": {
  "master":           "C:/RMPAK_CLIENT/RM_BAZY/RM_BAZA/master.sqlite",
  "projects_dir":     "C:/RMPAK_CLIENT/RM_BAZY/RM_BAZA/projects",
  "projects_mag_dir": "C:/RMPAK_CLIENT/RM_BAZY/RM_BAZA/projects_MAG",
  "server_dir":       "V:/",
  "local_dir":        "C:/RMPAK_CLIENT",
  "locks_dir":        "C:/RMPAK_CLIENT/RM_BAZY/RM_BAZA/locks",
  "backup_dir":       "C:/RMPAK_CLIENT/RM_BAZY/RM_BAZA/backups"
},
"locks":     { "folder": "C:/RMPAK_CLIENT/RM_BAZY/RM_BAZA/locks" },
"rm_serwer": { "host": "127.0.0.1", "port": 5060 }
```

Sekcja **`rm_serwer` jest obowiązkowa** — bez niej RM_BAZA wywala się na starcie
z `ValueError: adres RM_SERWER jest wymagany`.

### 5.2 `rm_serwer_config.json` — w repo, ale w `.gitignore:37`

```json
{
  "baza":            "C:/RMPAK_CLIENT/RM_BAZY/RM_BAZA/master.sqlite",
  "baza_mapowania":  "C:/RMPAK_CLIENT/RM_BAZY/RM_BAZA/subiekt_mapowania.sqlite",
  "baza_rm_manager": "C:/RMPAK_CLIENT/RM_BAZY/RM_MANAGER/rm_manager.sqlite",
  "port": 5060,
  "nasluch": "0.0.0.0"
}
```

---

## 6. Co dokładnie oddziela dom od firmy

| element | gdzie żyje | śledzony przez git? |
|---|---|---|
| kod aplikacji | repo | ✅ **wspólny dla obu** |
| `sync_config.json` | `C:\RMPAK_CLIENT\` | ❌ poza repo |
| `rm_serwer_config.json` | repo | ❌ `.gitignore:37` |
| udział SMB, hosts, rejestr | system | ❌ nie plik |
| bazy `.sqlite` | `C:\RMPAK_CLIENT\RM_BAZY\` | ❌ poza repo |

Dlatego `git pull` jest bezpieczny w obie strony.

---

## 7. Uruchamianie — kolejność ma znaczenie

```powershell
cd C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER
Start-Process python -ArgumentList "rm_serwer.py"                 # 1. serwer — musi być pierwszy
Start-Process python -ArgumentList "RM_BAZA_v15_MAG_STATS_ORG.py" # 2.
Start-Process python -ArgumentList "rm_manager_gui.py"            # 3.
```

Most Subiekta `NexoRecon.exe` startuje sam, na żądanie.

### ⚠️ `Start-Process`, nigdy `nohup … &`

Aplikacje okienkowe odpalone przez `nohup` w tle **nie dochodzą do końca startu** —
proces gaśnie, ale zdąży posprzątać po sobie `app.lock`. Efekt: mylący komunikat
**„Inna instancja aplikacji już działa!"** przy kolejnej próbie, przy czym żadna
instancja naprawdę nie działa.

### ⚠️ Po `git pull` — serwer od nowa

RM_SERWER trzyma kod w pamięci. Bez restartu odpowiada starą wersją, objaw:
`BladSerwera: nieznana operacja odczytu: '…'`.

### ⚠️ Po zmianach w moście — `dotnet build -c Release`

Python czyta `bin/Release/NexoRecon.exe`. Budowanie bez `-c Release` ląduje w
`bin/Debug` i **wygląda, jakby poprawka nie zadziałała**. Działający `NexoRecon.exe`
blokuje plik — najpierw ubić proces.

---

## 8. Weryfikacja

```powershell
Test-Path "\\W2019S\RM_SERWER$"                    # True  ← jeśli False, patrz §2.2
Test-Path "\\W2019S\RM_SERWER$\RM_BAZA_projects"   # True
(Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Lsa\MSV1_0" `
  -Name BackConnectionHostNames).BackConnectionHostNames   # W2019S
Get-SmbShare -Name 'RM_SERWER$'
```

Serwer żyje:

```powershell
(New-Object Net.Sockets.TcpClient).Connect("127.0.0.1", 5060)   # bez wyjątku = OK
```

Stan po poprawnym starcie (13.09.2026): udział widoczny, **64** bazy w
`RM_BAZA_projects`, **62** wpisy w `RM_MANAGER_projects`, RM_BAZA robi backupy
dobowe na `\\W2019S\RM_SERWER$\backup_RM_BAZA\`.

---

## 9. Rozwiązywanie problemów

| objaw | przyczyna | co zrobić |
|---|---|---|
| `\\W2019S\…` = False, ale `\\localhost\…` = True | brak `BackConnectionHostNames` | §2.2 |
| `New-SmbShare` → błąd 1332 | `Everyone` na polskim Windows | użyć `Wszyscy` |
| „Inna instancja już działa", a nic nie działa | start przez `nohup` | `Start-Process`, w razie potrzeby skasować `C:\RMPAK_CLIENT\app.lock` |
| `ValueError: adres RM_SERWER jest wymagany` | brak sekcji `rm_serwer` | §5.1 |
| `BladSerwera: nieznana operacja odczytu` | serwer na starym kodzie | restart `rm_serwer.py` |
| RM_MANAGER nie wstaje, proces ~3 MB bez okna | zombie z poprzedniej sesji trzyma lock | `Stop-Process -Force`, potem start |

### Śmieci, które mylą przy diagnozie

`C:\RMPAK_CLIENT\RM_BAZA_v15_MAG_STATS_ORG_26-04-2026.py\` — **katalog** nazwany jak
plik `.py`, w środku `app.lock` z lutego 2026 (PID 153584, komputer „Mongo"). Niczego
nie blokuje — prawdziwy lock to `C:\RMPAK_CLIENT\app.lock` (`DEFAULT_LOCAL_DIR`,
stała w kodzie, **nie** brana z configu). Zostawione do decyzji użytkownika.

---

## 10. Gdzie kod trzyma nazwę serwera

Zmiana nazwy serwera wymaga dotknięcia tych miejsc — **w domu nie ruszamy**:

| plik : linia | stała |
|---|---|
| `RM_BAZA_v15_MAG_STATS_ORG.py:264` | `PROJEKTY_NA_SERWERZE` |
| `RM_BAZA_v15_MAG_STATS_ORG.py:270` | `DEFAULT_BACKUP_DIR` |
| `RM_BAZA_v15_MAG_STATS_ORG.py:301` | `DEFAULT_CHAT_DIR` |
| `RM_BAZA_v15_MAG_STATS_ORG.py:379` | `DEFAULT_WSPOLNY_CONFIG` (HMAC) |
| `RM_BAZA_v15_MAG_STATS_ORG.py:23785` | `SERVER_HOSTNAMES = ('W2019S', 'SERWER')` |
| `rm_klient.py:83` | `WSPOLNY_HMAC` |
| `udzial_serwera.py` | `UDZIAL`, `KONTO`, `HASLO` |
