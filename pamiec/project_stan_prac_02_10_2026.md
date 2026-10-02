---
name: project_stan_prac_02_10_2026
description: PUNKT WZNOWIENIA po sesji 01–03.10.2026 (M-OLD) — commit 7ef3d0f niewypchnięty, co czeka na wdrożenie mostu w firmie, co sprawdzone tylko suchym przebiegiem, otwarte sprawy (Koło 12T ZK 16 vs BOM 8)
metadata:
  type: project
---

Stan na 03.10.2026, M-OLD. Commity wypchnięte w tej sesji: `67cbf04` (okna szybciej + pokazywane zbudowane + most zapotrzebowanie), `481c460` (CLAUDE.md: komunikacja w pakiecie). Reszta pracy z 02–03.10 — commit `7ef3d0f` (03.10.2026), **NIE wypchnięty** w chwili zapisu (sprawdź `git log origin/main..HEAD`).

**Zmiany w tej paczce:** naprawa sumowania ilości (powiązania), blokada nazwy po zasiewie, banner dubletów, czerwone okno przy sklejaniu, okna na monitorze rodzica + pilnowanie rozmiaru, okno „Nowa kartoteka", Przegląd dokumentów (projekt startowy, kolejność arkusza, szukanie, ilość/cena/usuń na ZK), Zamówienia (sortowanie przy odświeżeniu, „do zamówienia"). Most: `ZkIlosc.cs` (nowy), `ZkPozUsun.cs` (`zk` w planie), `Projekt.cs`/`Pw.cs` (publiczne wrappery), `CommandDispatcher.cs`.

**Do zrobienia w FIRMIE (most):** `git pull` → `dotnet build -c Release` → wystawienie na `\\W2019S\RM_SERWER$\MOST` + `most-dist` na `most-server` ([[feedback_most_w_gicie]]). Bez tego w firmie nie działają: szybkie zapotrzebowanie, `zk-ilosc`/`zk-cena`, usuwanie pozycji po numerze ZK. Python bez nowego mostu → błąd „nieznany tryb" przy dwukliku ilość/cena.

**W firmie przy pierwszym przejęciu locka na 2637** wyskoczy okno „Powiązania z Subiektem — naprawa" (te same 3 kolizje co w domu) — kliknąć „Tak" ([[project_powiazania_kolizja_ilosci]]).

**Sprawdzone tylko suchym przebiegiem / skompilowane:** realny zapis ceny i usuwania pozycji z ZK; dopasowanie ilości z ZK z `rozroznij_symbol` (ujawni się przy nowym zasiewie); filtr „do zamówienia" w działającym oknie.

**Otwarte:**
- Koło 12T-100 MM (`KOLO12T-100MM`) na ZK 6/CENTRALA/2026 = **16**, w BOM po sklejeniu 8 — skąd 16 nieustalone (najpewniej zapis Projekt/Aktualizacja przed sklejeniem). User może poprawić dwuklikiem w Przeglądzie dokumentów.
- 2× „6004" po 4 szt. w 2637 — sklejone przez usera (BOM 8), ZK dalej 4 → podnieść ręcznie, jeśli 8 potrzebne.
- Rozjazd SDK vs tryb własny zapotrzebowania (4 pozycje na danych M-OLD) — przyczyna nieznana ([[project_zapotrzebowanie_szybkie]]).
- „Widoczne kolumny" w RM_BAZA: przy drugim kliknięciu tylko `lift()` (może stać na innym monitorze); obcy prostokąt 357×693 — nie podpięte.
- Kolumna „ZK" w oknie ZD — user rozważa uproszczenie do „projekt: ilość" ([[project_zd_okno_do_zamowienia]]).
- Domówienie do stanu optymalnego w oknie ZD — nie podjęte.
- Skan ELESA/GANTER: kopia 406 pozycji w `G:\Mój dysk\SUBIEKT\ELESA\ELESA 2` (84 podfoldery, `_zrodla.csv`, 13 IAM niekompletnych); próba skryptem usera `skan_elesa_v2.py` do `ELESA 3` przerwana i wyczyszczona.
