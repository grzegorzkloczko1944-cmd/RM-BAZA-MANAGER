---
name: project_build_release_stimulsoft_hardlink
description: dotnet build do bin/Release padal na kopiowaniu Stimulsoft.*.dll (hardlinki wspoldzielone z dzialajacym Subiektem) - NAPRAWIONE w csproj 02.10.2026 (Stimulsoft poza CopyLocal); obejscie historyczne w tresci
metadata:
  type: project
---

# Build mostu do `bin/Release` pada na Stimulsoft — hardlink z Subiektem

Objaw (02.10.2026): `dotnet build -c Release` kończy się „Liczba błędów: 4" —
MSB3021/MSB3027 „Nie można skopiować Stimulsoft.Base.dll / Stimulsoft.Report.dll
… używany przez inny proces". **Kompilacja przechodzi**, ale MSBuild przerywa na
kopiowaniu i `NexoRecon.dll` w `bin/Release` ZOSTAJE STARE — łatwo przeoczyć,
bo błąd dotyczy cudzych DLL-i.

## Przyczyna

`bin/Release/Stimulsoft.Base.dll` i `Stimulsoft.Report.dll` to **hardlinki**
(`dowiaz_biblioteki_wydruku.ps1`, `New-Item -ItemType HardLink`) tego samego
pliku co `%LOCALAPPDATA%/InsERT/Deployments/Nexo/RM PRODUKCJA…/Binaries/` —
czyli binarki **działającego Subiekta Nexo**. Subiekt ma je załadowane, więc
zapis jest zablokowany. Dopóki źródło (`C:/iLogic/SUBIEKT/Bin`) było identyczne,
MSBuild nie miał czego kopiować; po aktualizacji Subiekta 06.09 źródło jest
nowsze (06.09) niż dowiązane pliki (04.08) i każdy build chce je nadpisać.

Sprawdzone: `fsutil hardlink list` pokazuje 4 ścieżki; otwarcie z
`FileShare.None` → „używany przez inny proces" przy ZERO procesów NexoRecon.

## Obejście (działa, użyte 02.10.2026)

    dotnet build -c Release -o %TEMP%/nxR      # świeży katalog — zawsze przechodzi
    kopiuj 4 pliki: NexoRecon.exe, NexoRecon.dll, NexoRecon.deps.json,
                    NexoRecon.runtimeconfig.json  → bin/Release
    (most z bin/Release MUSI być wtedy zatrzymany — trzyma NexoRecon.dll)

Stimulsoft w `bin/Release` zostaje stary — wydruk ZD działał z nim cały dzień;
staging na serwer i tak bierze tylko 5 plików mostu, bez Stimulsofta. Po
buildzie SPRAWDŹ, że `bin/Release/NexoRecon.dll` zawiera nową klasę (szukaj
nazwy w bajtach DLL), zamiast wierzyć samemu „Liczba błędów".

## NAPRAWIONE w csproj (02.10.2026, ten sam dzień)

Target `NieKopiujBibliotekInsERT` wyrzucał z CopyLocal tylko `InsERT.*`;
Stimulsoft szedł zwykłą kopią NA hardlink trzymany przez Subiekta. Warunek
rozszerzony o `StartsWith('Stimulsoft.')` — te dwa pliki i tak kładzie
`DowiazBibliotekiWydruku` jako dowiązania.

Dowód: dwa kolejne buildy do tego samego świeżego katalogu (pierwszy tworzy
hardlinki, drugi w nie trafia) — oba „Liczba błędów: 0". Przed poprawką drugi
padał. Obejście wyżej zostaje jako zapis historii; od teraz zwykły
`dotnet build -c Release` do bin/Release znów działa (most z bin/Release musi
być zatrzymany — to osobna, stara zasada).
Patrz też [[project_zd_pdf_brakujace_dll]] — „csproj NIE poprawiony" jest już nieaktualne.
