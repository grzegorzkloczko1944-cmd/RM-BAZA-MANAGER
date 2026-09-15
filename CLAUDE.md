# RM-BAZA-MANAGER — instrukcje dla agenta

## ⚠️ NAJPIERW PRZECZYTAJ PAMIĘĆ PROJEKTU

W katalogu [`pamiec/`](pamiec/) leżą notatki opisujące ten system: przyczyny
awarii, podjęte decyzje, pułapki i rzeczy, których NIE należy próbować
ponownie. Indeks: [`pamiec/MEMORY.md`](pamiec/MEMORY.md).

**Kolejność czytania — od najświeższych:**

```bash
# 1. Co zmieniło się ostatnio (najważniejsze — tu jest bieżący stan)
git log --oneline -15

# 2. Notatki zmienione najpóźniej
ls -t pamiec/*.md | head -10

# 3. Dopiero potem indeks, jeśli szukasz konkretnego obszaru
```

Notatka opisuje stan **z dnia zapisu**. Gdy jest starsza niż ostatnie
commity dotykające tego obszaru — **wierz kodowi, nie notatce**, a rozbieżność
zgłoś użytkownikowi.

Zanim zmienisz cokolwiek w danym module, otwórz notatki jego dotyczące. Wiele
z nich powstało po awariach, które kosztowały dzień pracy — jest tam nie
tylko naprawa, ale i ślepe uliczki („PRÓBOWANE I NIE DZIAŁA — nie powtarzać").

### Obszary o największej liczbie pułapek

| Obszar | Zacznij od |
|---|---|
| Subiekt / most Sfery | `project_subiekt_most_stan_serwera`, `project_zd_pdf_brakujace_dll` |
| Bazy, locki, RM_SERWER | `project_rm_baza_db_model_decision`, `project_zapis_do_bazy_projektu` |
| Sieć, udziały, dyski | `project_odciecie_od_Y`, `project_nas_nic_poswiadczenia` |
| Build `.exe` | `project_exe_persistent_paths`, `project_build_leniwe_importy` |

## Jak pamięć działa na różnych maszynach

Claude Code trzyma pamięć poza repo, w katalogu użytkownika:

```
~/.claude/projects/<nazwa-projektu>/memory/
```

Żeby notatki działały jak pamięć (ładowanie do kontekstu przy starcie
sesji) i jednocześnie wersjonowały się w gicie, katalog użytkownika
**dowiązujemy** do `pamiec/` w repo.

### Ustawienie na nowej maszynie (raz)

Windows, PowerShell **jako administrator** — albo zwykły, gdy włączony jest
Tryb dewelopera:

```powershell
# 1. Ustal nazwę katalogu projektu (Claude tworzy ją ze ścieżki repo)
$proj = (Get-ChildItem "$env:USERPROFILE\.claude\projects" -Directory |
         Where-Object Name -like '*RM-BAZA-MANAGER*').FullName

# 2. Zdejmij istniejącą pamięć (jeśli była) — ZRÓB KOPIĘ, gdy coś w niej jest
if (Test-Path "$proj\memory") { Rename-Item "$proj\memory" "memory_stara" }

# 3. Podlinkuj repo
New-Item -ItemType Junction -Path "$proj\memory" `
         -Target "C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER\pamiec"
```

`Junction` zamiast `SymbolicLink`: **nie wymaga uprawnień administratora**
i działa dla katalogów na tym samym dysku.

Gdy dowiązanie się nie uda — nic nie przepada. Notatki leżą w repo jako
zwykłe pliki Markdown i agent przeczyta je na żądanie; brakuje tylko
automatycznego ładowania przy starcie sesji.

### Jak pisać nowe notatki

Zapisuj je w `pamiec/` (przez dowiązanie robi to się samo), jeden fakt na
plik, z nagłówkiem YAML: `name`, `description`, `metadata.type`
(`user` / `feedback` / `project` / `reference`). Po dodaniu pliku dopisz
jedną linię do `pamiec/MEMORY.md` — to indeks ładowany do kontekstu.

⚠️ `MEMORY.md` zapisuj **w UTF-8**. `Add-Content` z PowerShella potrafi
zapisać w stronie kodowej systemu i rozwalić polskie znaki (zdarzyło się
15.09.2026); używaj `Out-File -Encoding utf8` albo Pythona.

## Zasady pracy w tym repo

- **Nie pushuj bez wyraźnej zgody** użytkownika.
- **`backup_nic.bat` zostaje poza gitem** — ma hasło do konta na NAS-ie.
  Żyje tylko na serwerze, patrz [`pamiec/project_backup_nic_poza_gitem.md`](pamiec/project_backup_nic_poza_gitem.md).
- **Most Subiekta**: źródła `.cs` na `main`, binarka wystawiana na
  `\\W2019S\RM_SERWER$\MOST`. Przed wystawieniem `git diff <sha na serwerze>..HEAD`
  — bywały tam poprawki spoza repo.
- **Okna użytkownika to jego praca** — nie zamykaj RM_BAZA ani RM_MANAGER
  bez pytania.
- Start aplikacji: `RM_BAZA_v15_MAG_STATS_ORG.py` (nie `rm_manager_gui.py`).
