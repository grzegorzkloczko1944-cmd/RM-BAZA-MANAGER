@echo off
REM ---------------------------------------------------------------------------
REM  RM_SERWER — kopia zapasowa danych na DRUGA MASZYNE (\\nic).
REM
REM  PO CO: caly system (master RM_BAZA, rm_manager.sqlite, bazy projektow,
REM  mapowania Subiekta, KSeF) lezy na JEDNYM dysku C: serwera W2019S.
REM  Wewnetrzny backup RM_SERWER-a robi spojne kopie baz, ale odklada je
REM  w tym samym miejscu — padniecie dysku zabiera oryginal i kopie naraz.
REM  Ten skrypt wynosi dane poza serwer.
REM
REM  CO KOPIUJEMY (i czego NIE):
REM    dane\*.sqlite            NIE — zywe bazy, robocopy zlapalby je w polowie
REM                             transakcji i kopia byla by uszkodzona. Zamiast
REM                             nich bierzemy spojne kopie z backup_*\master,
REM                             ktore serwer robi przez SQLite Online Backup API.
REM    Projekty\RM_*_projects   TAK — pliki projektow, zywe dane uzytkownikow
REM    Projekty\subiekt_historia TAK
REM    Projekty\chat, SESSIONS  TAK (drobne, ale to tez dane)
REM    ai_rules.txt, HMAC.json  TAK
REM    backup_*\master          TAK, ale tylko NAJNOWSZE kopie (patrz nizej)
REM    backup_RM_MANAGER\projects  NIE — 2,3 GB archiwum kopii projektow.
REM                             Backup backupow; zywe pliki i tak kopiujemy.
REM
REM  Dzieki temu na \\nic ladzie ~150 MB zamiast 2,7 GB.
REM
REM  DOSTEP DO \\nic: wzorzec z RM_DWF\_service_launcher.bat — UNC bez liter
REM  dyskow (litery koliduja miedzy uslugami startujacymi rownoczesnie,
REM  System error 85), `net use` z jawnym kontem, retry gdy siec jeszcze spi.
REM
REM  URUCHAMIANIE: Harmonogram zadan, codziennie w nocy (po 00:57 — wtedy
REM  serwer robi swoj wewnetrzny backup, wiec kopiujemy juz swieze pliki).
REM ---------------------------------------------------------------------------

setlocal enabledelayedexpansion

set ZRODLO=C:\Apps\RM_SERWER\dane
set UDZIAL=\\nic\PROJEKTY
set CEL=%UDZIAL%\BACKUP_RM_SERWER
set LOG=C:\Apps\RM_SERWER\logi\backup_nic.log
set OPCJE=/FFT /R:2 /W:5 /NP /NDL /NFL

if not exist "C:\Apps\RM_SERWER\logi" mkdir "C:\Apps\RM_SERWER\logi"

echo. >> "%LOG%"
echo ======================================================== >> "%LOG%"
echo [%date% %time%] START backup na %CEL% >> "%LOG%"

REM --- polaczenie z udzialem (retry: po restarcie siec bywa jeszcze nieaktywna)
set RETRY=0
:retry_net
REM  Haslo NIE w repozytorium — wersja na serwerze ma je wpisane wprost,
REM  tak jak RM_DWF\_service_launcher.bat. Przy odtwarzaniu: podstaw haslo
REM  konta nic\mongo (jest w launcherze RM_DWF na serwerze).
net use %UDZIAL% /user:nic\mongo HASLO_TUTAJ /persistent:no >> "%LOG%" 2>&1
if not errorlevel 1 goto polaczono
set /a RETRY+=1
if !RETRY! geq 10 (
    echo [%date% %time%] BLAD: brak polaczenia z %UDZIAL% po 10 probach >> "%LOG%"
    exit /b 1
)
timeout /t 3 /nobreak >nul
goto retry_net

:polaczono
if not exist "%CEL%" mkdir "%CEL%" >> "%LOG%" 2>&1

set BLEDY=0

REM --- 1. Pliki projektow (zywe dane uzytkownikow) --------------------------
REM  /MIR = lustro: skasowany projekt znika tez z kopii, inaczej katalog
REM  rosnie bez konca. Historia i tak siedzi w backupach serwera.
for %%K in (RM_BAZA_projects RM_MANAGER_projects subiekt_historia chat SESSIONS) do (
    robocopy "%ZRODLO%\Projekty\%%K" "%CEL%\Projekty\%%K" /MIR %OPCJE% /LOG+:"%LOG%"
    if !ERRORLEVEL! GEQ 8 (
        echo [%date% %time%] BLAD kopiowania %%K, kod !ERRORLEVEL! >> "%LOG%"
        set /a BLEDY+=1
    )
)

REM --- 2. Spojne kopie baz (SQLite Online Backup API, robione przez serwer) --
REM  BEZ /MIR: rotacja na serwerze zostawia 20 kopii, a na \\nic chcemy miec
REM  takze starsze — to jedyne miejsce, gdzie przezyja padniecie dysku C:.
REM  /MAXAGE:30 — tylko z ostatnich 30 dni, zeby nie ciagnac calego archiwum
REM  przy pierwszym uruchomieniu.
for %%K in (backup_RM_BAZA backup_RM_MANAGER) do (
    robocopy "%ZRODLO%\Projekty\%%K\master" "%CEL%\bazy\%%K" /MAXAGE:30 %OPCJE% /LOG+:"%LOG%"
    if !ERRORLEVEL! GEQ 8 (
        echo [%date% %time%] BLAD kopiowania kopii %%K, kod !ERRORLEVEL! >> "%LOG%"
        set /a BLEDY+=1
    )
)

REM --- 3. Pliki pojedyncze ---------------------------------------------------
robocopy "%ZRODLO%\Projekty" "%CEL%\Projekty" ai_rules.txt HMAC.json %OPCJE% /LOG+:"%LOG%"
if !ERRORLEVEL! GEQ 8 set /a BLEDY+=1

REM --- 4. Konfiguracja i kod serwera (odtworzenie bez grzebania w gicie) -----
robocopy "C:\Apps\RM_SERWER" "%CEL%\aplikacja" *.py *.json %OPCJE% /XF *.bak_* /LOG+:"%LOG%"
if !ERRORLEVEL! GEQ 8 set /a BLEDY+=1

REM --- podsumowanie ----------------------------------------------------------
REM  Robocopy: 0-7 = sukces (bity: 1 skopiowano, 2 dodatkowe, 4 niezgodne),
REM  8 i wyzej = blad. Kod >0 sam w sobie NIE oznacza awarii.
if !BLEDY! GTR 0 (
    echo [%date% %time%] ZAKONCZONE Z BLEDAMI: !BLEDY! >> "%LOG%"
) else (
    echo [%date% %time%] OK >> "%LOG%"
)

REM --- znacznik dla monitoringu: kiedy ostatnio sie udalo ---
if !BLEDY! EQU 0 echo %date% %time% > "%CEL%\_ostatni_udany_backup.txt"

REM --- rozlaczenie: nie zostawiamy otwartej sesji SMB miedzy backupami -------
net use %UDZIAL% /delete /y >> "%LOG%" 2>&1

REM --- przyciecie logu do 2000 linii, zeby nie rosl bez konca ---------------
powershell -NoProfile -Command "if ((Get-Content '%LOG%').Count -gt 5000) { Get-Content '%LOG%' -Tail 2000 | Set-Content '%LOG%.tmp'; Move-Item '%LOG%.tmp' '%LOG%' -Force }" 2>nul

if !BLEDY! GTR 0 exit /b 1
exit /b 0
