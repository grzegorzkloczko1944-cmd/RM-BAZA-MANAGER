---
name: project_powiazania_kolizja_ilosci
description: Dwa wiersze arkusza z tym samym subiekt_symbol → plan Projekt/Aktualizacja SUMOWAŁ ilości (2637: 4+13 → „ustawi 17”). Przyczyna: dopasowanie ilości z ZK po symbol_z_nazwy BEZ rozroznij_symbol. Naprawa 02.10.2026: guard w planie, rozroznij w dopasowaniu, automatyczna naprawa powiązań pod lockiem
metadata:
  type: project
---

**Objaw (02.10.2026, projekt 2637 na M-OLD):** okno „Zapis do Subiekta — potwierdzenie” pokazało „ZWIĘKSZY ILOŚĆ”: `6004ZZ` na ZK 4 → 17, `NakretkaTR16x` 1 → 3, `Lozyskonierdz` 4 → 8. Nikt nie zmieniał BOM-u. Zapis zrobiłby podwójne zamówienie (13 szt. 6004ZZ już stało na ZK pod `6004ZZ-2`).

**Mechanizm (trzy warstwy, każda sama w sobie „działała”):**
1. Zasiew 29.09 nadał dwóm wierszom o nazwach dających ten sam `symbol_z_nazwy` („6004 ZZ” / „6004ZZ”; „…TR16x4” / „…TR16x4.”; łożysko 6004 / 6404 → oba `Lozyskonierdz`) osobne symbole przez `rozroznij_symbol` (`6004ZZ-2`, `NakretkTR16x4`, `Loz64042Z20x7`) — poprawnie, obie kartoteki na ZK.
2. `_zapisz_ilosci_z_subiekta` (RM_BAZA) dopasowywało wiersze BEZ `subiekt_symbol` po samym `symbol_z_nazwy` — bez rozroznij → **drugi wiersz dostał powiązanie z kartoteką pierwszego**, a jego własna kartoteka „nie miała wiersza” i `_dopisz_pozycje_z_zk` dopisała ją jako wiersz „z zamówienia ZK” (dubel w arkuszu).
3. Commit `55cccfd` (02.10, 16:41, „plan z powiązania”) kazał planowi wysyłać symbol z `subiekt_symbol` zamiast z nazwy → dwa wiersze pod jednym symbolem → most sumuje ilości. Do tej zmiany błędne powiązanie było niewidoczne.

**Naprawa (`subiekt_projekt.py`, `RM_BAZA_v15_MAG_STATS_ORG.py`):**
- `read_project_items`: `zajete_przez` — powiązanie zajęte przez inny wiersz NIE nadpisuje symbolu; wiersz idzie pod własnym (z rozroznij), item ma `konflikt_powiazania`, `build_plan` dokłada ostrzeżenie do `warn` (widoczne w oknie). Nigdy ciche sumowanie.
- `_zapisz_ilosci_z_subiekta`: symbol z nazwy zajęty przez wiersz o INNEJ nazwie → `rozroznij_symbol(nazwa, zajęte)` i tylko gdy ten symbol stoi na ZK; identyczna nazwa (różna wielkością liter) = ta sama rzecz z dwóch gałęzi, wspólna kartoteka OK.
- `planuj_naprawe_powiazan(con, kart)` / `wykonaj_naprawe_powiazan(con, akcje)` — uruchamiane przy przejęciu locka (przed dopasowaniem ilości), `askyesno` z listą PRZED, `showinfo` z odczytem kontrolnym PO, wpis `POWIAZANIE_NAPRAWA` w logu zmian. Nadmiarowy wiersz grupy: (1) przepięcie na kartotekę wiersza „z zamówienia ZK” o tej samej nazwie + scalenie (ilość, dostawy; tamten wiersz kasowany), (2) `rozroznij_symbol` jeśli na ZK, (3) odpięcie. Idempotentne.
- Test na kopii `project_72.sqlite`: 3 akcje, po naprawie 0 konfliktów, plan: `6004ZZ` 4 + `6004ZZ-2` 13, `NakretkaTR16x` 1 + `NakretkTR16x4` 2, `Lozyskonierdz` 4 + `Loz64042Z20x7` 4.

**Pułapki:**
- Porównanie nazw w naprawie: wielkość liter i spacje NIE różnią, **kropka różni** („TR16x4” vs „TR16x4.” to dwie kartoteki na ZK — scalanie ich to decyzja usera, nie kodu).
- Wiersze o IDENTYCZNEJ nazwie w dwóch gałęziach (np. 618/619 „6004”, oba 4 szt.) plan dedupuje po nazwie (`seen`) i wysyła ilość PIERWSZEGO — czy ZK powinno mieć sumę, nieustalone; nie ruszać bez decyzji.
- Ten sam stan danych jest w firmie (projekt 2637) — naprawa odpali się tam przy pierwszym przejęciu locka po `git pull`.

Powiązane: [[project_subiekt_id_tozsamosc]], [[project_blokada_klucza_zasiew]], [[feedback_nic_po_cichu]], [[project_zk_ilosci_nie_porownywane]].
