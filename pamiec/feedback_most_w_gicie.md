---
name: feedback_most_w_gicie
description: "Most Sfery (NexoRecon) trzymamy w gicie — źródła C# na main, wystawiona binarka w most-server/most-dist; commitować i pushować razem z Pythonem"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b4b4fbd4-107b-4ece-9328-8ca8b8a060fc
  modified: 2026-09-09T15:27:05.814Z
---

Polecenie użytkownika (09.09.2026): **„od teraz MOST też trzymamy na gicie"**.

**Why:** most to część systemu na równi z Pythonem — bez jego źródeł i bez
śladu, która binarka poszła na produkcję, nie da się odtworzyć stanu z danego
dnia ani dojść, czemu u usera coś nie działa. Wersje rozjeżdżały się już
realnie: 09.09.2026 po `git pull` przyszły nowe `.cs`, a na serwerze stała
binarka sprzed nich — „Ilość (zam.)" i usuwanie projektów przestały działać
([[project_subiekt_most_stan_serwera]]).

**How to apply:**
- Źródła `subiekt_sfera/NexoRecon/*.cs` (38 plików) są śledzone na `main` —
  **każda zmiana w moście = commit razem z resztą**, nie „poprawię i zbuduję".
- `bin/` i `obj/` zostają w `.gitignore` (`.spec` linie 29-30) — binarki nie
  wrzucamy na `main`.
- **Wystawiona** binarka idzie do gałęzi `most-server`, katalog `most-dist/`
  (exe + dll + deps.json + runtimeconfig.json + `wersja.json`) — to jedyny
  zapis tego, co danego dnia dostali userzy. Robić to przy KAŻDYM wystawieniu
  na serwer (`\\W2019S\RM_SERWER$\MOST`, na serwerze `C:/Apps/RM_SERWER/dane/Projekty/MOST`,
  przez WinRM `Copy-Item -ToSession`), w tym samym kroku. **Nie na Y:** (od 14.09.2026).
- Pushować oba branche: `git push origin main` i `git push origin most-server`.
- Kolejność przy wydaniu: commit `.cs` → `dotnet build -c Release` →
  `MOST_STAGING` + ręczny `wersja.json` (protokol/zbudowano/sha/uwaga) →
  serwer → `most-dist` → push.

Pułapka przy budowaniu: `bin/Release/NexoRecon.exe` bywa zablokowany przez
chodzący most `server` (RM_BAZA go uruchamia) — najpierw `Stop-Process`,
inaczej build pada na kopiowaniu apphost. Patrz [[project_subiekt_most_stan_serwera]].


**Aktualizacja 14.09.2026:** wystawienie z 12.09 (`4937834`) NIE zostało odłożone na
`most-server` — uzupełnione wstecz (`2538542`) z plików z udziału. Wygodna droga
bez przełączania gałęzi: `git worktree add <tmp> most-server` → kopiuj 5 plików
do `most-dist/` → commit → `git worktree remove <tmp>`. Kontrola przed
wystawieniem: `git diff <sha z wersja.json>..HEAD -- subiekt_sfera/NexoRecon/`
(14.09 pokazała, że `WydanieStan.cs` bez `Take(400)` był w źródłach, ale
NIE w binarce u userów — ponad dobę). Smoke test binarki z 5 plików:
`NexoRecon.exe stan C:/nie/ma.json` ze stagingu → ma dojść do „BRAK KONFIGU".
