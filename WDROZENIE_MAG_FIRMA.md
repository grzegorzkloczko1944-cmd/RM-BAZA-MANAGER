# WDROŻENIE MAG W FIRMIE — instrukcja dla agenta

> Spisane 28.09.2026 na M-OLD (dom), gdzie całość **działa**. W firmie jeszcze
> NIC z tego nie ma. Wykonujesz to na stacji **MONGO** (firma), w imieniu
> Grzegorza. Czytaj od góry do dołu, krok po kroku. Każdy krok ma
> weryfikację — nie idź dalej, dopóki poprzedni nie przejdzie.

## Co to jest MAG (jednym akapitem)

Makro Inventora `MAG` pokazuje kartoteki Subiekta (stan, cena, miniatura,
wymiary łożysk, model 3D) i katalog łożysk kulkowych. Dane czyta przez HTTP
z serwera W2019S (port **5061**, `rm_mag_http.py` uruchamiany wewnątrz
usługi RM_SERWER). Serwer trzyma **kopię** Subiekta w `subiekt_kopia.sqlite`;
kopię odświeża RM_BAZA na stacji z mostem Sfery (MONGO) na zlecenie z przycisku
„Synchronizuj" w MAG. Szczegóły: `PLAN_MAG.md`, pamięć
`pamiec/project_mag_*.md`, `pamiec/feedback_makra_ivb_nazwa_mag.md`.

## ⛔ Zasady, których NIE łamiesz

1. **Restart usługi RM_SERWER zatrzymuje RM_BAZA na wszystkich stanowiskach.**
   Zanim zrestartujesz — ZAPYTAJ Grzegorza, czy teraz można (najlepiej po
   godzinach albo gdy potwierdzi, że nikt nie pracuje w RM_BAZA).
2. **Nie nadpisuj na serwerze plików, których nie ma na liście w kroku 2**,
   a zwłaszcza: `rm_serwer_config.json`, `HMAC.json`, niczego w `dane\`.
3. **Przed nadpisaniem plików serwera zrób diff z repo** — bywały poprawki
   wprowadzane prosto na serwerze, spoza gita (pamięć:
   `project_mapowania_subiekta_stan_14_09`). Różnice, których nie ma w repo,
   POKAŻ Grzegorzowi, zanim cokolwiek nadpiszesz.
4. **Nie pushuj bez zgody**, nie zamykaj okien RM_BAZA/RM_MANAGER/Inventora
   bez pytania (pamięć: `feedback_nie_zamykaj_okien_usera`).
5. **Żadnych hooków Windows w VBA** (pamięć: `feedback_bez_hookow_vba` —
   zawiesiło cały komputer).

---

## Krok 0 — przygotowanie na MONGO

```powershell
cd C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER ; git pull --ff-only
cd C:\RMPAK_CLIENT\Repozytoria\NOW              ; git pull --ff-only
```

Weryfikacja — w RM-BAZA-MANAGER muszą być:
- `rm_mag_http.py`, `subiekt_kopia_sync.py`, `subiekt_kopia_zlecenia.py`
- `katalog_lozysk\lozyska_kulkowe.json` (≈ 94 KB, 293 łożyska)
- commit `bec3416` lub nowszy (`git log --oneline -3`)

W NOW: `MAKRA\MAG_zrodla\MAG.vba` (≈ 49 KB), commit `eea0e24` lub nowszy.

**Sprawdź nazwę komputera** — od niej zależy pierwszeństwo przy synchronizacji:
```powershell
$env:COMPUTERNAME
```
W `subiekt_kopia_zlecenia.py` jest `PREFEROWANE = ("MONGO", "M-OLD")`.
Jeśli MONGO nazywa się inaczej (np. „MONGO" to tylko nazwa konta) — **popraw
tę krotkę na faktyczną nazwę**, zacommituj (bez pusha — zapytaj) i powiedz
Grzegorzowi. Bez tego MONGO i tak przejmie zlecenie, ale dopiero po 2 minutach.

**Sprawdź ustawienie „Serwer projekty"** (`server_dir` w
`C:\RMPAK_CLIENT\sync_config.json`, sekcja `paths`) — to korzeń folderów
projektów, w którym RM_BAZA szuka rysunków DWF (miniatury w arkuszu, zdjęcia
kartotek przy zasiewie, wyszukiwarka plików). Projekty leżą **bezpośrednio
w `V:\`** (np. `V:³7 Feniks Z 25L`). Na M-OLD stało `V:/SERVER_PROJEKTY`
i 28.09.2026 zasiew 2637 dostał miniatury tylko z biblioteki (74 z 348).
Jeśli w firmie też wskazuje na nieistniejący folder — pokaż Grzegorzowi,
popraw w RM_BAZA: Ustawienia → Konfiguracja ścieżek → „Serwer projekty"
(nie edytuj pliku, gdy RM_BAZA chodzi — nadpisze go przy zapisie ustawień).

## Krok 1 — połączenie z serwerem (WinRM)

Pełny opis: `NOW\DOKUMENTACJA\DOSTEP_SERWER.md`. W skrócie:

```powershell
$cred = Import-Clixml "$env:TEMP\rmdwf_srvcred.xml"
$s = New-PSSession -ComputerName 192.168.100.84 -Credential $cred -ErrorAction Stop
```

- **Po IP, NIE po nazwie** — TrustedHosts ma tylko `192.168.100.84`
  (po nazwie `W2019S` pada „ServerNotTrusted").
- Plik poświadczeń odszyfruje się tylko na koncie `mongo` na tej maszynie.
- Kod RM_SERWER: `C:\Apps\RM_SERWER\` (to **nie** jest klon gita —
  wgrywamy przez `Copy-Item -ToSession`). Usługa NSSM: `RM_SERWER`.
- Sesja WinRM **nie widzi Y:** ani `\\nic` — i nie musi.

## Krok 2 — diff: co stoi na serwerze vs repo

Pliki do wdrożenia (i tylko te):

| plik w repo | cel na serwerze |
|---|---|
| `rm_serwer.py` | `C:\Apps\RM_SERWER\rm_serwer.py` |
| `rm_serwer_operacje.py` | `C:\Apps\RM_SERWER\rm_serwer_operacje.py` |
| `rm_mag_http.py` (NOWY) | `C:\Apps\RM_SERWER\rm_mag_http.py` |
| `katalog_lozysk\lozyska_kulkowe.json` (NOWY) | `C:\Apps\RM_SERWER\katalog_lozysk\lozyska_kulkowe.json` |

```powershell
$repo = "C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER"
$tmp  = Join-Path $env:TEMP "serwer_przed_mag"; New-Item -ItemType Directory -Force $tmp | Out-Null
foreach ($f in "rm_serwer.py","rm_serwer_operacje.py") {
    Copy-Item "C:\Apps\RM_SERWER\$f" (Join-Path $tmp $f) -FromSession $s -Force
}
# diff z WERSJĄ SPRZED MAG (commit 0682436) — to powinno wyjść PUSTE:
cd $repo
git show 0682436:rm_serwer.py           | Out-File "$tmp\repo_rm_serwer.py"           -Encoding utf8
git show 0682436:rm_serwer_operacje.py  | Out-File "$tmp\repo_rm_serwer_operacje.py"  -Encoding utf8
```
Porównaj `$tmp\rm_serwer*.py` (serwer) z `$tmp\repo_*.py` (repo sprzed MAG),
np. `git diff --no-index --ignore-cr-at-eol`. **Pusto** → serwer = repo sprzed
MAG, jedziemy dalej. **Są różnice** → ustal, czym są, zanim cokolwiek nadpiszesz:

- **serwer STARSZY niż repo** — różnice to fragmenty z commitów, których na
  serwer nie wgrano (sprawdź: `git log --oneline -- rm_serwer.py rm_serwer_operacje.py`
  i porównaj z wcześniejszymi commitami, np. `git show <sha>:rm_serwer.py`).
  To jest OK — nowe pliki i tak je zawierają; powiedz tylko Grzegorzowi,
  które zmiany wejdą przy okazji.
- **poprawki SPOZA gita** — kodu z serwera nie ma w żadnym commicie → STOP,
  pokaż Grzegorzowi. Najpierw przenieść je do repo, dopiero potem wdrażać
  (inaczej nadpisanie je skasuje).

Kopia zapasowa (zawsze, nawet przy pustym diffie):
```powershell
Invoke-Command -Session $s -ScriptBlock {
    $b = "C:\Apps\RM_SERWER\backup_przed_MAG_" + (Get-Date -Format yyyyMMdd_HHmm)
    New-Item -ItemType Directory -Force $b | Out-Null
    Copy-Item C:\Apps\RM_SERWER\rm_serwer.py, C:\Apps\RM_SERWER\rm_serwer_operacje.py $b
    $b
}
```

## Krok 3 — wgranie plików (BEZ restartu)

```powershell
Invoke-Command -Session $s -ScriptBlock {
    New-Item -ItemType Directory -Force C:\Apps\RM_SERWER\katalog_lozysk | Out-Null
}
Copy-Item "$repo\rm_serwer.py"                          "C:\Apps\RM_SERWER\rm_serwer.py"          -ToSession $s -Force
Copy-Item "$repo\rm_serwer_operacje.py"                 "C:\Apps\RM_SERWER\rm_serwer_operacje.py" -ToSession $s -Force
Copy-Item "$repo\rm_mag_http.py"                        "C:\Apps\RM_SERWER\rm_mag_http.py"        -ToSession $s -Force
Copy-Item "$repo\katalog_lozysk\lozyska_kulkowe.json"   "C:\Apps\RM_SERWER\katalog_lozysk\lozyska_kulkowe.json" -ToSession $s -Force
```

Sprawdź składnię NA SERWERZE (to nie restartuje usługi):
```powershell
Invoke-Command -Session $s -ScriptBlock {
    cd C:\Apps\RM_SERWER
    python -m py_compile rm_serwer.py rm_serwer_operacje.py rm_mag_http.py; "py_compile: $LASTEXITCODE"
    python rm_serwer.py --sprawdz
}
```
`--sprawdz` wypisze bazę, integrity_check, liczbę operacji i „port 5060: ZAJĘTY"
(bo usługa chodzi — to dobrze). „migracje do dołożenia: N" to NIE zaległość
(pamięć: `project_wdrozenie_18_09_dostawy`).

## Krok 4 — zapora: port 5061

```powershell
Invoke-Command -Session $s -ScriptBlock {
    if (-not (Get-NetFirewallRule -DisplayName "RM_MAG HTTP (port 5061)" -EA SilentlyContinue)) {
        New-NetFirewallRule -DisplayName "RM_MAG HTTP (port 5061)" -Direction Inbound `
            -Protocol TCP -LocalPort 5061 -Action Allow -Profile Any | Out-Null
    }
    Get-NetFirewallRule -DisplayName "RM_MAG HTTP (port 5061)" | Select DisplayName, Enabled
}
```
(Wzór: reguła „RM_SERWER (port 5060)" z pierwszego wdrożenia.)

## Krok 5 — restart usługi ⚠ ZAPYTAJ GRZEGORZA

Dopiero po jego zgodzie:
```powershell
Invoke-Command -Session $s -ScriptBlock {
    Restart-Service RM_SERWER -Force; Start-Sleep 6
    Get-Service RM_SERWER | Select Status
    $log = Get-ChildItem C:\Apps\RM_SERWER\logi\rm_serwer_*.log | Sort LastWriteTime | Select -Last 1
    Get-Content $log.FullName -Tail 40 -Encoding UTF8 | Select-String "MAG HTTP|Kopia Subiekta|łożysk|⚠|⛔"
}
```
Oczekiwane w logu:
- `Kopia Subiekta: C:\Apps\RM_SERWER\dane\subiekt_kopia.sqlite`
- `+ katalog łożysk: 293 pozycji (…)`
- `MAG HTTP: 0.0.0.0:5061 (tylko odczyt)`

Jeśli brak `MAG HTTP` albo jest `⛔ … port 5061` — sprawdź, czy
`rm_serwer_config.json` na serwerze nie ma `"port_mag": 0` / innego
`"nasluch"`. Domyślne wartości (bez wpisów w configu) są właściwe —
**nie dopisuj** nic do configu, jeśli nie trzeba.

**Wycofanie** (gdyby usługa nie wstała): skopiuj z `backup_przed_MAG_*`
dwa pliki z powrotem, usuń `rm_mag_http.py`, restart usługi.

## Krok 6 — test HTTP z MONGO

```powershell
(Invoke-WebRequest "http://W2019S:5061/mag/status?format=tsv" -UseBasicParsing).Content
(Invoke-WebRequest "http://W2019S:5061/mag/lozyska?format=tsv&q=6004" -UseBasicParsing).Content
```
- `status`: `kartotek` będzie **0** — kopia jest jeszcze pusta, to normalne.
- `lozyska?q=6004`: wiersz `6004 … 20x42x12`.
- Jeśli `W2019S` się nie rozwiązuje, spróbuj `http://192.168.100.84:5061/...`.
  Działa po IP, a po nazwie nie → w `MAG.vba` stała `MAG_SERWER` na IP
  (zmieniasz w `MAKRA\MAG_zrodla\czesci\modul.vba`, potem
  `python zloz_MAG.py` w `MAKRA\MAG_zrodla`).

## Krok 7 — pierwsza synchronizacja kopii Subiekta

RM_BAZA na MONGO musi być uruchomiony **ze źródeł** z aktualnym kodem (po
`git pull`), bo tylko wtedy startuje wykonawca zleceń
(`subiekt_kopia_zlecenia.py`). Jeśli RM_BAZA chodzi ze starego kodu —
**zapytaj** Grzegorza, czy możesz go zamknąć i uruchomić ponownie:
```powershell
cd C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER
Start-Process python -ArgumentList "RM_BAZA_v15_MAG_STATS_ORG.py" -WorkingDirectory (Get-Location)
```
Szybsza droga do pierwszej kopii (bez czekania na zlecenie) — ręcznie z konsoli:
```powershell
python subiekt_kopia_sync.py --miniatury-od-nowa     # ok. 5 min przy ~3500 kartotek
```
Potem `/mag/status` → `kartotek` ≈ liczba kartotek w Subiekcie, `miniatur` > 0.

## Krok 8 — MAG w Inventorze

⚠ **Pierwszy raz na Inventorze firmowym (VBA7 64-bit!)** — w domu był VBA 6.
Kod jest przygotowany na oba, ale to pierwszy test VBA7.

1. Inventor → Narzędzia → Makra → Edytor VBA.
2. W projekcie aplikacji (`Default.ivb`) wstaw nowy moduł (w domu Grzegorz
   ma MAG w `Module9` — zapytaj, gdzie chce w firmie).
3. Otwórz `NOW\MAKRA\MAG_zrodla\MAG.vba` w VS Code → Ctrl+A, Ctrl+C →
   w module Ctrl+A, Ctrl+V → **ZAPISZ projekt (Ctrl+S)**.
4. Uruchom makro `MAG`. Pierwszy raz: „MAG założył/zaktualizował swoje okno —
   uruchom MAG jeszcze raz" (zakłada okno `MAG_okno`, klasę `MAG_wiersz`,
   okno `MAG_lozyska` i referencję MSHTML). Drugi raz: okno MAG.
5. Sprawdź: wpisz `6004` (kolumna Wymiary 20x42x12), `6x`, kliknij wiersz
   (szczegóły + zdjęcie), kółko myszy nad listą, przycisk „Katalog łożysk".

Gdy coś nie działa — pułapki są spisane w `pamiec/project_mag_okno_przegladarka.md`
i `pamiec/project_mag_katalog_lozysk.md`. Najczęstsze:
- „Can't find project or library" na zwykłej funkcji (`Left`) → w Tools →
  References jest „MISSING: …" — odznacz.
- „Out of memory" przy zakładaniu okna → projekt za duży; MAG w osobnym `.ivb`.
- Okno miga i znika → projekt się zresetował po zmianie kodu; uruchom MAG drugi raz.

## Krok 9 (opcjonalny) — indeks modeli 3D

Na stacji z Inventorem firmowym (2015 — w domu 2013 nie czytał nowszych IDW):
```powershell
cd C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER
python indeks_modeli_3d.py --raport indeks_raport.txt   # suchy przebieg, B:\
python indeks_modeli_3d.py --zapisz                     # po akceptacji raportu
```
Raport pokaż Grzegorzowi przed `--zapisz` (konflikty kopii, Part Number ≠ numer).
Szczegóły: `PLAN_MAG.md`, sekcja 6a.

## Krok 10 — na koniec

- Zapisz w `pamiec/` notatkę o przebiegu wdrożenia (co wyszło inaczej niż
  tu opisano) + linię w `pamiec/MEMORY.md` (UTF-8!).
- Uaktualnij „Stan:" na górze `PLAN_MAG.md`.
- Commit — tak. **Push — tylko po zgodzie Grzegorza.**
- `Remove-PSSession $s`.

## Stacje z `.exe` RM_BAZA

Nie muszą nic robić, żeby MAG działał (wystarczy MONGO jako wykonawca
synchronizacji). Wykonawca zleceń trafi do `.exe` przy następnym buildzie —
moduły są już w `RM_BAZA_v15_MAG.spec`. Builda NIE rób bez zlecenia.
