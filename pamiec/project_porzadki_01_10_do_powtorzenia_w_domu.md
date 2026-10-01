---
name: project_porzadki_01_10_do_powtorzenia_w_domu
description: "Porządki z 01.10.2026 (podział MEMORY.md, sprzątanie repo NOW) — co przyjdzie z git pull, a co trzeba powtórzyć ręcznie na M-OLD, bo dotyczy plików poza gitem"
metadata:
  type: project
---

# Porządki 01.10.2026 — co powtórzyć w domu (M-OLD)

Część zmian poszła na gita i przyjdzie sama. **Reszta dotyczy plików, które
celowo NIE są wersjonowane** (klucze sekretne, pliki lokalne), więc na M-OLD
trzeba je wykonać ręcznie. Ta notatka jest listą do odhaczenia.

## 1. Przychodzi samo — wystarczy `git pull`

W **RM-BAZA-MANAGER** (commit `6b5c570`):

* `pamiec/MEMORY.md` — z 23 KB zrobił się **spis obszarów** (1,7 KB).
* Nowe `pamiec/INDEKS_*.md` — 9 plików tematycznych, 172 wpisy rozdzielone.
* `CLAUDE.md` — tabela obszarów + zasada: **nowe wpisy pamięci idą do
  właściwego `INDEKS_*.md`, NIE do `MEMORY.md`**.

⚠️ `MEMORY.md` **musi zostać pod tą nazwą** — mechanizm pamięci Claude Code
szuka pliku o tej nazwie przez dowiązanie
`~/.claude/projects/<projekt>/memory` → `pamiec/`. Skasowanie albo
przemianowanie = brak indeksu przy starcie sesji.

## 2. Do zrobienia RĘCZNIE w repo NOW

Te pliki nigdy nie były w gicie, więc `git pull` ich nie usunie.

```bash
cd <ścieżka>/NOW
rm -f AGENTS.md              # nieaktualny duplikat CLAUDE.md
rm -rf .codex                # konfiguracja subagenta Codex (14.09)
```

**Dlaczego `AGENTS.md` leci:** powstał 14.09, `CLAUDE.md` z 28.09 go zastąpił,
a stary zdążył się rozjechać z rzeczywistością — podawał **RM_PRINT na porcie
8060**, podczas gdy kod i serwer mają **5055**. Brakowało w nim też
`RM_ARCHIWUM/` i `RM_NOTATKA_ANDROID/`. Dwa pliki instrukcji obok siebie to
proszenie się o to, żeby ktoś przeczytał nieaktualny.

Jeśli w domu wiszą też pliki robocze spoza gita (u mnie było makro
`Narzedzia_Drobne/VG_NG125_SR.bas` + `.dxf`) — ocenić osobno, czy to żywa
praca, czy śmieć. **Nie kasować w ciemno**: nieśledzonego pliku git nie odda.

## 3. Do dopisania RĘCZNIE: `serwis_port`

Plik `NOW/RM_STATS/config.json` **jest poza gitem** (trzyma `secret_key`
i `serwis_secret_key`), więc klucz trzeba dopisać na każdej maszynie osobno.

```json
"port": 5050,
"serwis_port": 5058,
```

**Po co:** bez `serwis_port` RM_SERWIS bierze domyślne **5055** (`RM_STATS/
app_mode.py`, `default_port`) — czyli ten sam port, na którym stoi RM_PRINT.
Konflikt wychodzi dopiero przy uruchomieniu obu naraz.

## Porty — stan potwierdzony na serwerze firmowym (01.10.2026)

Sprawdzone przez WinRM, `Get-NetTCPConnection`, nie z dokumentacji:

| port | co |
|---|---|
| 5050 | RM_STATS |
| 5055 | RM_PRINT |
| 5058 | RM_SERWIS (z `serwis_port`) |
| 5060 | `rm_serwer.py` — serwer RM_BAZA, **nie** przeglądarkowy |
| 5075 | RM_ARCHIWUM (wg `CLAUDE.md` w NOW) |

Na serwerze `C:\Apps\NOW\RM_STATS\config.json` ma `serwis_port` ustawiony —
tam kolizji nie ma i nic nie trzeba poprawiać.

⛔ **Port 5060 jest nieużywalny dla aplikacji webowych** — to port SIP (VoIP)
z listy zastrzeżonych przez przeglądarki, Firefox i Chrome odmawiają
połączenia („Zastrzeżony adres"). Od 27.09.2026 porty są **te same w domu
i w firmie**.

Zobacz też: [[project_srodowisko_domowe_m_old]],
[[feedback_git_pull_multi_maszyna]].
