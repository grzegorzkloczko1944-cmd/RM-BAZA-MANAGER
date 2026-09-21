---
name: odciecie-od-y-mapowania
description: "Odcięcie od Y: — mapowania Subiekta już przez RM_SERWER (kod 14.09.2026), zostało wdrożenie serwera w firmie + build .exe; plan w TODO_ODCIECIE_OD_Y.md"
metadata: 
  node_type: memory
  type: project
  originSessionId: 5f190e79-13f0-43ff-a820-54ac4e6eb565
  modified: 2026-09-14T19:19:44.180Z
---

Stan 14.09.2026 wieczór: `subiekt_mapowania.py` NIE otwiera już pliku —
wszystko przez `rm_klient` (`map-get-many`, `map-put` batch, `map-alias-dodaj`,
`map-przepnij-symbol`, `map-odrzuc`…). Zrobione w firmie (commit `62f2f36`),
przetestowane na lokalnym serwerze z kopią 863 wpisów. Pkt 0 ustalony:
w firmie plik mapowań leży na serwerze `C:\Apps\RM_SERWER\dane\`, nic do
scalania, żadnych strat (pliku na Y: nie było, więc nikt nie zapisał).

**Why:** nowy klient WYMAGA nowych operacji serwera — build .exe przed
wdrożeniem `rm_serwer.py` + `rm_serwer_operacje.py` na W2019S rozłoży
wszystkich (`BladSerwera: nieznana operacja`).

**How to apply:** serwer na W2019S JUŻ WDROŻONY 14.09 wieczorem (commit
`e4f736c` „Wdrozone na W2019S, usluga zrestartowana"). Zostaje: weryfikacja
`map-statystyki` ze stacji (859/2/2), potem build .exe. Po `git pull`
w domu RESTART `rm_serwer.py` (stary proces nie zna `map-*`) — zrobione
14.09 21:18. Pkt 2 (subiekt_stany) zrobiony inaczej niż w TODO: moduł sam
podmienia starą ścieżkę (`43c82ef`), TODO tego nie odhacza. Zostały
porządki (pkt 3). Nie ruszać: `Y:/SERVER_PROJEKTY`, `Y:\RMPAK_CLIENT\*.exe`.
Domowy `rm_manager.sqlite` ma starą `active_sessions` z FK do `users` →
serwer loguje „no such table: main.users" przy zapisie sesji (nieszkodliwe).
Powiązane: [[subiekt-integracja-m-old]], [[git-pull-multi-maszyna]].
