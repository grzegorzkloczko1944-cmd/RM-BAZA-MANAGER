<#
    Kladzie obok NexoRecon.exe twarde dowiazania (hardlinki) do bibliotek
    InsERT-u, ktorych wymaga SILNIK WYDRUKU przy eksporcie ZD do PDF.

    PO CO TO ISTNIEJE
    Stimulsoft (wzorzec wydruku ZD) nie laduje przez .NET — sklada sciezke
    jako tekst (katalog .exe + nazwa pliku) i czyta plik wprost z dysku.
    Zaden hook rozwiazywania assembly tego nie przechwyci; sprawdzone
    15.09.2026 na AssemblyLoadContext.Resolving, AppDomain.AssemblyResolve
    i APP_PATHS w runtimeconfig — wszystkie bez efektu, bo `Eksport()` NIE
    RZUCA WYJATKU, tylko cicho nic nie zapisuje. Objaw u uzytkownika: mail
    do dostawcy wychodzi z rysunkami, ale bez PDF-a zamowienia.

    DLACZEGO DOWIAZANIE, A NIE KOPIA
    Kopia zamraza wersje. Baza aktualizuje sie sama przy starcie Subiekta,
    a stara kopia przestaje do niej pasowac — Sfera odmawia polaczenia,
    most startuje, odpowiada na ping, ale nigdy nie osiaga ready i RM_BAZA
    wisi na przejeciu locka (awaria z 09.09.2026). Hardlink to drugi wpis
    katalogowy do TEGO SAMEGO pliku, wiec tresc jest zawsze ta, co w SDK.

    Zrodlo wybieramy tak samo jak SdkLoader.cs: najpierw instalacja Subiekta
    (ClickOnce, aktualizowana razem z baza), potem statyczne kopie SDK.

    Skrypt NIE MOZE przerwac builda — brak SDK na maszynie budujacej jest
    dopuszczalny (most i tak doladuje biblioteki w locie). Stad exit 0
    w kazdym przypadku i ContinueOnError w csproj.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string] $Wyjscie,
    [Parameter(Mandatory = $true)][string] $SdkBin,
    [Parameter(Mandatory = $true)][string] $Biblioteki
)

$ErrorActionPreference = 'Continue'

function Znajdz-BinariaSubiekta {
    # Ta sama regula co SdkLoader.SzukajBinariowSubiekta(): katalog ClickOnce
    # ma w nazwie baze i hash, wiec szukamy zamiast wpisywac na sztywno.
    # Przy kilku instalacjach wygrywa NAJSWIEZSZA — ta jest zgodna z baza.
    $baza = Join-Path $env:LOCALAPPDATA 'InsERT\Deployments\Nexo'
    if (-not (Test-Path $baza)) { return $null }
    Get-ChildItem $baza -Directory -ErrorAction SilentlyContinue |
        ForEach-Object { Join-Path $_.FullName 'Binaries' } |
        Where-Object { Test-Path (Join-Path $_ 'InsERT.Moria.Sfera.dll') } |
        Sort-Object { (Get-Item (Join-Path $_ 'InsERT.Moria.Sfera.dll')).LastWriteTimeUtc } -Descending |
        Select-Object -First 1
}

$zrodlo = Znajdz-BinariaSubiekta
if (-not $zrodlo) { $zrodlo = $SdkBin }

if (-not (Test-Path $zrodlo)) {
    Write-Host "  (wydruk) pomijam dowiazania — brak SDK: $zrodlo"
    exit 0
}

$nazwy = $Biblioteki -split ';' | Where-Object { $_ }
$dowiazane = 0
$skopiowane = 0
$brakujace = @()
$zajete = @()

foreach ($nazwa in $nazwy) {
    $src = Join-Path $zrodlo "$nazwa.dll"
    $dst = Join-Path $Wyjscie "$nazwa.dll"

    if (-not (Test-Path $src)) { $brakujace += $nazwa; continue }

    # ⚠️ NIE KASUJEMY PLIKU, KTORY JUZ JEST AKTUALNY. ClickOnce przy
    # aktualizacji PODMIENIA pliki, wiec stare dowiazanie moze wskazywac na
    # nieaktualna wersje — ale bezwarunkowe Remove-Item wywracalo CALY build,
    # gdy plik trzymal OTWARTY SUBIEKT (te same biblioteki, MSB3027 „Plik jest
    # zablokowany przez: Subiekt"; zdarzylo sie 15.09.2026). Rozmiar + czas
    # zapisu wystarcza, zeby poznac, ze to ten sam plik.
    if (Test-Path $dst) {
        $a = Get-Item $dst
        $b = Get-Item $src
        if ($a.Length -eq $b.Length -and $a.LastWriteTimeUtc -eq $b.LastWriteTimeUtc) {
            $dowiazane++
            continue
        }
        Remove-Item $dst -Force -ErrorAction SilentlyContinue
        # Nadal jest = trzyma go inny proces. Zostawiamy: stara wersja tej
        # samej biblioteki jest lepsza niz przerwany build.
        if (Test-Path $dst) { $zajete += $nazwa; continue }
    }

    try {
        New-Item -ItemType HardLink -Path $dst -Target $src -ErrorAction Stop | Out-Null
        $dowiazane++
    } catch {
        # Hardlink dziala tylko w obrebie jednego wolumenu. Gdy SDK jest na
        # innym dysku — kopiujemy. Wersja moze sie rozjechac po aktualizacji
        # Subiekta, ale SdkLoader zglosi to czytelnym komunikatem, a wydruk
        # dziala tu i teraz.
        try { Copy-Item $src $dst -Force -ErrorAction Stop; $skopiowane++ }
        catch { $brakujace += $nazwa }
    }
}

$opis = "  (wydruk) biblioteki PDF: $dowiazane dowiazanych"
if ($skopiowane) { $opis += ", $skopiowane skopiowanych" }
if ($zajete) { $opis += ", $($zajete.Count) zajetych (otwarty Subiekt) — zostaja stare" }
Write-Host "$opis  [$zrodlo]"
if ($brakujace) { Write-Host "  (wydruk) NIE ZNALEZIONO: $($brakujace -join ', ') — PDF zamowienia nie powstanie" }

exit 0
