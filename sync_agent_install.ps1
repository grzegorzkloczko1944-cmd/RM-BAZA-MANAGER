# =============================================================================
# sync_agent_install.ps1 - zaklada zadanie Task Scheduler dla RM_SYNC_AGENT.
#
# Cykl co 60 s: agent wypycha kooperantow do RM_RFQ i sciaga wyniki ofertowania
# do master.sqlite (kolumna WYCENA). Bez tego zadania sync jest RECZNY, a dane
# w RM_BAZA pochodza z ostatniego uruchomienia - to bylo zrodlo polowy
# "bledow odswiezania" diagnozowanych 29.08.2026.
#
# UZYCIE (bez admina - zadanie w kontekscie zalogowanego usera):
#   powershell -ExecutionPolicy Bypass -File sync_agent_install.ps1
#   powershell -ExecutionPolicy Bypass -File sync_agent_install.ps1 -Remove
#
# Sciezke do master.sqlite wybiera sync_agent_run.bat po hostname - patrz tam.
# =============================================================================

param(
    [string]$TaskName = 'RM_SYNC_AGENT',
    [int]$IntervalSeconds = 60,
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $here 'sync_agent_run.bat'
$hidden = Join-Path $here 'sync_agent_hidden.vbs'

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Zadanie '$TaskName' usuniete."
    } else {
        Write-Host "Zadanie '$TaskName' nie istnieje - nie ma czego usuwac."
    }
    return
}

# Runner jest w .gitignore (per-maszyna), wiec po swiezym klonie go nie ma.
if (-not (Test-Path $runner)) {
    Write-Host "BRAK $runner" -ForegroundColor Red
    Write-Host "Utworz go z wzorca:" -ForegroundColor Yellow
    Write-Host "   copy sync_agent_run.example.bat sync_agent_run.bat"
    exit 1
}
if (-not (Test-Path $hidden)) {
    Write-Host "BRAK $hidden (powinien byc w repo)" -ForegroundColor Red
    exit 1
}

# Trigger: RepetitionInterval ma minimum 1 minute (Task Scheduler nie przyjmuje
# krotszych).
#
# Duration: NIE dawac [TimeSpan]::Zero - Scheduler odrzuca "PT0S" bledem
# 0x80041318 ("wartosc niepoprawnie sformatowana"). "Bez konca" ustawia sie
# przez wyzerowanie samego pola w XML (RepetitionDuration = $null nie dziala
# przez cmdlet), wiec dajemy maksimum przyjmowane przez API: 9999 dni.
# Zadanie i tak startuje ponownie przy kazdym logowaniu.
$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Seconds $IntervalSeconds) `
    -RepetitionDuration (New-TimeSpan -Days 9999)).Repetition

# Uruchamiamy przez wscript.exe + .vbs, NIE bezposrednio .bat: Scheduler
# odpalajacy batcha zawsze mignie oknem cmd.exe, a ustawienie -Hidden zadania
# tego nie ukrywa (dotyczy okna zadania, nie procesu potomnego). VBScript
# startuje batcha z parametrem widocznosci 0 i przekazuje kod wyjscia.
$action = New-ScheduledTaskAction -Execute 'wscript.exe' `
    -Argument "`"$hidden`"" -WorkingDirectory $here

# StartWhenAvailable: nadrobi cykl po uspieniu komputera.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -Hidden `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Stare zadanie '$TaskName' usuniete (nadpisuje)."
}

$opis = "RM_SYNC_AGENT - synchronizacja RM_BAZA / RM_RFQ co $IntervalSeconds s"
Register-ScheduledTask -TaskName $TaskName -Trigger $trigger -Action $action `
    -Settings $settings -Description $opis | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "Zadanie '$TaskName' zalozone i uruchomione (co $IntervalSeconds s)." -ForegroundColor Green
Write-Host "Log: $(Join-Path $here 'sync_agent.log')"
Write-Host ''
Write-Host "Sprawdzenie:  Get-ScheduledTask -TaskName $TaskName"
Write-Host 'Usuniecie:    powershell -File sync_agent_install.ps1 -Remove'
