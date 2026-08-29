@echo off
REM ============================================================================
REM RM_SYNC_AGENT - jeden cykl synchronizacji RM_BAZA <-> RM_RFQ.
REM Uruchamiany cyklicznie przez Task Scheduler (co 60 s).
REM
REM UWAGA: ten plik czyta cmd.exe w kodowaniu ANSI - BEZ polskich znakow
REM w komentarzach, inaczej batch sie rozjezdza na parsowaniu.
REM
REM Ten plik to WZORZEC. Realny "sync_agent_run.bat" jest w .gitignore, wiec
REM git pull go NIE nadpisze - kazda maszyna trzyma wlasne sciezki i nie ma
REM "jazd, ze cos nie dziala po pullu".
REM
REM INSTALACJA (raz na maszyne):
REM   copy sync_agent_run.example.bat sync_agent_run.bat
REM   powershell -ExecutionPolicy Bypass -File sync_agent_install.ps1
REM
REM PRZELACZNIK DOM / SERWER - po nazwie komputera, ta sama zasada co
REM config_mode.py w RM_RFQ. Domyslna sciezka w rm_sync_agent.py to firmowa
REM (Y:\RM_BAZA\master.sqlite), wiec na komputerze domowym BEZ podania --master
REM agent konczy sie bledem "unable to open database file".
REM ============================================================================

cd /d "%~dp0"

REM --- wybor sciezki do master.sqlite wg hostname -----------------------------
REM Serwer firmowy: UNC bez litery dysku (uslugi/Scheduler nie widza map dyskow).
REM Dopisz tu kolejne maszyny, jesli dojda.
if /i "%COMPUTERNAME%"=="W2019S" (
    set "MASTER=\\nic\rysunki\RM_BAZA\master.sqlite"
) else (
    set "MASTER=C:\RMPAK_CLIENT\RM_BAZY\RM_BAZA\master.sqlite"
)

set "LOG=%~dp0sync_agent.log"

REM Brak bazy = nie ma po co uruchamiac agenta. Lepiej jeden czytelny wpis
REM w logu niz stacktrace co minute.
if not exist "%MASTER%" (
    echo [%date% %time%] BRAK bazy: %MASTER% ^(host %COMPUTERNAME%^) >> "%LOG%"
    exit /b 1
)

REM Rotacja logu - przy cyklu co minute plik rosnie bez konca.
REM 2 MB to okolo tygodnia; stary zapisujemy jako .1 (jedno pokolenie).
for %%F in ("%LOG%") do if %%~zF GTR 2097152 move /y "%LOG%" "%LOG%.1" >nul 2>&1

python rm_sync_agent.py --once --master "%MASTER%" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] BLAD synchronizacji >> "%LOG%"
    exit /b 1
)
