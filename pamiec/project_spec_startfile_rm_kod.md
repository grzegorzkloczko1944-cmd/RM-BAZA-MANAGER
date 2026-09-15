---
name: project_spec_startfile_rm_kod
description: "startfile(dist) w .spec uruchamiał RM_KOD.exe przez Eksplorator — 152 procesy po jednym buildzie; usunięte z obu .spec"
metadata:
  type: project
---

# ⛔ NIE DODAWAĆ `_os.startfile(DISTPATH)` DO ŻADNEGO `.spec`

**Objaw (15.09.2026, zgłoszone: „odpalasz mi miliony RM_KOD"):** po buildzie
`.exe` w systemie wisiały **152 procesy `RM_KOD.exe`**, wszystkie
z `dist\RM_KOD\RM_KOD.exe`, wystartowane w ciągu ~5 sekund od zakończenia
builda. Każdy ~47 MB RAM, razem ponad 7 GB.

**Przyczyna:** oba `.spec` kończyły się wygodnym

```python
_os.startfile(_os.path.join(_os.path.abspath(DISTPATH), ''))   # „pokaż dist"
```

W `dist\` leży **katalog `RM_KOD` z `RM_KOD.exe`**. Eksplorator, wchodząc do
folderu i generując podglądy zawartości podkatalogów, **URUCHOMIŁ ten plik** —
wielokrotnie.

**Naprawa:** wywołanie usunięte z `RM_BAZA_v15_MAG.spec` i `RM_MANAGER.spec`.
Ścieżkę gotowego pliku i tak wypisuje sekcja PUBLIKACJA; folder użytkownik
otwiera sam, gdy chce.

**How to apply:**
- ⚠️ `import os as _os` w `RM_BAZA_v15_MAG.spec` **zostaje** — używa go
  sekcja publikacji na Y: (kopiowanie, `stat`, `makedirs`). Nie usuwać.
- Sprzątanie, gdyby się powtórzyło:
  `Get-Process RM_KOD | Stop-Process -Force` (ubiło wszystkie 152 za pierwszym
  razem, nie wracały).
- Prawdopodobnie ta sama przyczyna stoi za datą `15.09 11:06` na
  `Y:\RMPAK_CLIENT\RM_KOD` — build z rana też otwierał folder. Zawartość
  katalogu na Y: pozostała nietknięta (zero plików ze zmienioną datą).
- Ogólniej: **nic w `.spec` nie powinno uruchamiać ani otwierać niczego** —
  to plik budujący, wykonywany też na cudzych maszynach i w CI.
