@echo off
REM ============================================================================
REM RM_SYNC_AGENT - jeden cykl synchronizacji RM_BAZA <-> RM_RFQ.
REM Uruchamiany cyklicznie przez Task Scheduler (co 60 s).
REM
REM UWAGA: ten plik czyta cmd.exe w kodowaniu ANSI - BEZ polskich znakow
REM w komentarzach, inaczej batch sie rozjezdza na parsowaniu.
REM
REM Ten plik to WZORZEC. Realny "sync_agent_run.bat" jest w .gitignore, wiec
REM git pull go NIE nadpisze.
REM
REM INSTALACJA (raz na maszyne):
REM   copy sync_agent_run.example.bat sync_agent_run.bat
REM   powershell -ExecutionPolicy Bypass -File sync_agent_install.ps1
REM
REM DOM I FIRMA - TEN SAM PLIK. Od 40a02c5 (11.09.2026) agent NIE otwiera
REM master.sqlite - wszystko idzie przez RM_SERWER. Roznice miedzy maszynami
REM siedza w plikach spoza repo:
REM   C:\RMPAK_CLIENT\sync_config.json -> "rm_serwer": {"host", "port"}
REM   master.sqlite -> settings: rfq_portal_url, rfq_api_key (czyta RM_SERWER)
REM Dawny przelacznik po nazwie komputera i parametr --master usuniete -
REM agent go juz nie zna ("unrecognized arguments" = kazdy cykl padal).
REM ============================================================================

cd /d "%~dp0"

set "CFG=C:\RMPAK_CLIENT\sync_config.json"
set "LOG=%~dp0sync_agent.log"

REM Brak konfiguracji = agent nie zna adresu RM_SERWER. Lepiej jeden czytelny
REM wpis w logu niz stacktrace co minute.
if not exist "%CFG%" (
    echo [%date% %time%] BRAK %CFG% - agent nie zna adresu RM_SERWER ^(host %COMPUTERNAME%^) >> "%LOG%"
    exit /b 1
)

REM Rotacja logu - przy cyklu co minute plik rosnie bez konca.
REM 2 MB to okolo tygodnia; stary zapisujemy jako .1 (jedno pokolenie).
for %%F in ("%LOG%") do if %%~zF GTR 2097152 move /y "%LOG%" "%LOG%.1" >nul 2>&1

python rm_sync_agent.py --once >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] BLAD synchronizacji >> "%LOG%"
    exit /b 1
)
