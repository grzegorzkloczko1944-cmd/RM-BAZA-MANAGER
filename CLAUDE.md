# RM-BAZA-MANAGER — instrukcje dla agenta

## ⛔ KOMUNIKACJA: ODCZYT I ZAPIS W PAKIECIE, NIGDY POJEDYNCZO W PĘTLI

Dotyczy **każdej** nowej i modyfikowanej funkcji, która rozmawia z czymś poza
procesem: most Sfery (Subiekt), RM_SERWER (HTTP), SQLite na udziale, pliki na
`\\W2019S\…`, NAS.

- **Odczyt hurtem:** jedno zapytanie / jedno wywołanie zwraca wszystko, czego
  potrzeba dla całej listy. Nie: pętla po wierszach, a w niej osobne
  pytanie o każdy wiersz (N+1).
- **Zapis hurtem:** jedna paczka (plan, lista pozycji, transakcja), nie seria
  pojedynczych zapisów jeden po drugim.
- **W moście (C#/EF):** projekcja kolumn w jednym `Select`, bez leniwego
  doczytywania encji w pętli (`poz.Dokument`, `p.Asortyment` itp. po jednym
  = osobne zapytanie SQL na każdy wiersz).
- **W Pythonie:** to samo pytanie do serwera/mostu/dysku nie leci drugi raz
  w tej samej operacji — pobierz raz, trzymaj w pamięci (cache na okno /
  na operację); sprawdzanie plików — jeden odczyt katalogu, nie `exists()`
  na wiersz.
- Most obsługuje żądania **po kolei** — równoległe wątki tego nie naprawią.

Dlaczego: 01.10.2026 okna Magazyn / Zamówienia ZD / Przegląd dokumentów
traciły sekundy na właśnie takich pętlach (tryb własny zapotrzebowania
1,5 s → 0,13 s po przejściu na jedno zapytanie; PDF-y `mkdir`+`exists` na
każdy wiersz przy każdym znaku w „Szukaj"). Wcześniej to samo w Magazyn.cs
(7 s → 0,3 s, 06.09). Szczegóły: `pamiec/project_zapotrzebowanie_szybkie.md`.

## ⛔ WSPÓLNE PLIKI Z DRUGIM REPO (NOW ↔ RM-BAZA-MANAGER) — BEZ MIXÓW

Dwa repo, **jedno miejsce na każdy kod**. Nie kopiuj modułu z jednego repo do drugiego
„bo tak szybciej” — kopia rozjeżdża się po cichu i potem nikt nie wie, która wersja jest
prawdziwa (10.10.2026: patrz historia niżej).

- Kod potrzebny w obu repo → **zostaje tam, gdzie żyje**; drugie repo z niego korzysta
  (ścieżka, import z katalogu drugiego repo) albo dostaje **zarejestrowaną kopię**.
- Kopia, która MUSI być, stoi na liście **`kopie_miedzy_repo.json`** (w obu repo, identyczny)
  z trybem: `identyczne` / `identyczne_poza` (dozwolone linie) / `rozne_z_zalozenia`
  i powodem. Zmiana zarejestrowanej kopii → **ten sam commit idzie do OBU repo**.
- Program przeniesiony do drugiego repo → **stary katalog usuwamy** (git trzyma historię)
  i wpisujemy do `usuniete` w `kopie_miedzy_repo.json`. Żadnych „-COPY”, „_stary”, „v2” obok.
- **Strażnik:** `sprawdz_kopie.py` (identyczny w obu repo) + hook `.githooks/pre-commit`.
  Zatrzymuje commit, gdy zarejestrowana kopia różni się od drugiego repo albo gdy dodajesz
  plik `.py`, którego nazwa jest już w drugim repo. **Nie obchodzić `--no-verify`** —
  naprawić przyczynę (skopiować plik / użyć tego z drugiego repo / dopisać do listy).
  Pełny raport ręcznie: `python sprawdz_kopie.py`.
- **Włączenie hooka — raz na każdym klonie** (dom, firma, nowy komputer):
  `git config core.hooksPath .githooks` (w obu repo). Bez drugiego repo obok (np. serwer)
  strażnik tylko informuje i przepuszcza.

### Stan wspólnych plików (10.10.2026)

| NOW | RM-BAZA-MANAGER | tryb | uwagi |
|---|---|---|---|
| `RM_STATS/stats_status.py` | `stats_status.py` | identyczne | okno „Status projektów” w RM_MANAGER; źródło: RM_STATS |
| `RM_STATS/stats_project_summary.py` | `stats_project_summary.py` | identyczne | okno „Podsumowanie” w RM_MANAGER |
| `RM_STATS/db.py` | `db.py` | różne z założenia | w RM-BAZA łącznik przez RM_SERWER; brakującą metodę przenosić 1:1 |
| `RM_DWF/dwf_thumb.py` | `dwf_thumb.py` | identyczne poza `THUMB_CACHE_DIR` | każdy program ma swój cache miniatur |
| `sprawdz_kopie.py`, `kopie_miedzy_repo.json` | to samo | identyczne | strażnik i lista |
| `AGENTS.md` | `AGENTS.md` | identyczne | dla Codex / Cowork / innych agentów — odsyła tutaj + twarde reguły |
| `.github/copilot-instructions.md` | to samo (blok „Zasady wspólne…”) | — | Copilot; własne zasady każdego repo zostają |

### Historia — żeby nie szukać plików

- **10.10.2026 — `RM_Tray_Organizer` USUNIĘTY z RM-BAZA-MANAGER** (`RM_Tray_Organizer.pyw`,
  `RM_Tray_Organizer.spec`, `RM_Tray_Organizer-COPY.spec` z katalogu głównego). To była
  porzucona kopia z maja; **aktualny program jest w `NOW/RM_TRAY_ORGANIZER/`**. Stara wersja
  w historii gita RM-BAZA-MANAGER (commit `5335670`).
- **10.10.2026 — statystyki RM_MANAGER zsynchronizowane z RM_STATS** (commit `33417f3`
  w RM-BAZA-MANAGER): `stats_*.py` były z 19.07 i nie miały poprawek z sierpnia (opóźnienia
  etapów od prognozy, pauza projektu, karta maszyny). Do łącznika `db.py` dopisane 1:1
  `project_sort_key`, `stage_attachments`, `stage_topics`.
- **10.10.2026 — strażnik kopii** (`sprawdz_kopie.py`, `kopie_miedzy_repo.json`, `.githooks/`)
  w obu repo.

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
(`user` / `feedback` / `project` / `reference`).

**Po dodaniu pliku dopisz jedną linię do właściwego `pamiec/INDEKS_*.md`,
NIE do `MEMORY.md`** (01.10.2026). Indeks był jedną płaską listą 172 wpisów
i przestał się nadawać do szukania — rozbity na dziewięć obszarów:

| plik | obszar |
|---|---|
| `INDEKS_zasady.md` | jak mam pracować — czego nie robić bez pytania |
| `INDEKS_subiekt_most.md` | most NexoRecon, SDK Sfery, zapotrzebowanie |
| `INDEKS_subiekt_okna.md` | okna do Subiekta, kartoteki, ZK/ZD/PW/RW |
| `INDEKS_ksef.md` | e-Faktury, archiwum, przyjęcia PZ |
| `INDEKS_mag.md` | makro MAG, indeks modeli 3D, biblioteki |
| `INDEKS_serwer.md` | RM_SERWER, bazy, locki, udziały, NAS |
| `INDEKS_build.md` | PyInstaller, bramka wersji, wystawianie |
| `INDEKS_rm_manager.md` | projekty, kadry, optymalizator, RFQ |
| `INDEKS_interfejs.md` | arkusz, tksheet, drzewka, wygląd okien |

`MEMORY.md` zostaje **spisem obszarów** — to jego nazwy szuka mechanizm
pamięci przy starcie sesji, więc nie wolno go skasować ani przemianować.
Nowy obszar = nowy `INDEKS_*.md` plus jedna linia w `MEMORY.md`.

⚠️ Pliki indeksu zapisuj **w UTF-8**. `Add-Content` z PowerShella potrafi
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
