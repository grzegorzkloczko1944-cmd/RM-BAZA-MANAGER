---
name: feedback_most_rebuild_release
description: "Po zmianie kodu mostu - dotnet build -c Release ORAZ ubicie chodzacego NexoRecon.exe, inaczej testy klamia"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd77b2db-aa7d-4871-a44f-b0388f221230
  modified: 2026-09-09T21:49:18.839Z
---

Po każdej zmianie w `subiekt_sfera/NexoRecon/*.cs` trzeba zrobić **oba** kroki:

```
taskkill /F /IM NexoRecon.exe        # staly most trzyma stary kod w pamieci
dotnet build -c Release              # Python bierze exe z bin/Release, NIE z Debug
```

**Why:** `_find_exe()` w `subiekt_stany.py` wskazuje `bin/Release/NexoRecon.exe`, więc `dotnet build` bez `-c Release` buduje Debug i zmiana nie działa. Osobno: stały most ([[project_subiekt_staly_most]]) to proces serwera, który po rebuildzie nadal ma w pamięci poprzednią wersję.

2026-09-09 kosztowało to dwa fałszywe suche przebiegi — filtr produkcji własnej wyglądał na niedziałający, choć kod był poprawny.

**How to apply:** przy testowaniu zmian mostu najpierw sprawdzić datę pliku (`bin/Release/NexoRecon.exe`) i czy `NexoRecon.exe` nie chodzi w tasklist. Gdy wynik testu wygląda tak, jakby zmiana nie weszła — sprawdzić to ZANIM zacznie się szukać błędu w kodzie.

Powiązane: [[project_cena_na_pozycji_pw]], [[reference_dokumentacja_sfery]].
