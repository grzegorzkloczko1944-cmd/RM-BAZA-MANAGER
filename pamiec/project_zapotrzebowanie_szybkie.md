---
name: project_zapotrzebowanie_szybkie
description: Tryb mostu `zapotrzebowanie` przyspieszony 01.10.2026 — przegląd ZK i tryb własny jednym zapytaniem; SDK i tryb własny różnią się o 4 pozycje (stan sprzed zmiany); przełącznik NEXORECON_ZAPOTRZEBOWANIE do porównań
metadata:
  type: project
---

01.10.2026, `ZapotrzebowanieBezpieczne.cs` + `Zapotrzebowanie.cs` (most, M-OLD; pomiary domowe, 495–499 pozycji):

| etap | przed | po |
|---|---|---|
| przegląd ZK (szukanie pozycji bez kartoteki) | ~420 ms (każdy ZK i pozycja osobno) | 1 ms (`Where(zk => zk.Pozycje.Any(p => p.AsortymentAktualny == null))`) |
| tryb własny + pętla pozycji | ~520 + 160 ms | ~25 + 0 ms (jedna projekcja kolumn, `ZapotrzebowanieWlasneOdczyt`) |
| całość, tryb własny | ~1,3–1,6 s | **~0,12–0,15 s** |
| całość, SDK | ~1,4–2 s | bez zmian (SDK = ~1,1 s podłogi) |

W firmie zawsze działa tryb własny (pozycja jednorazowa „Gasket” na ZK 2/09/2026, patrz [[project_zk_pozycja_bez_kartoteki]]), więc tam zysk jest pełny.

**Szybka ścieżka TYLKO dla listy** (`Policz(sfera, tylkoOdczyt: true)`, wynik bez encji, z gotowymi tekstami w `Potrzeba.Opis`). `Zd.cs` (tworzenie ZD) świadomie zostaje na encjach i starej drodze (`PrzegladPelny` + `ZapotrzebowanieWlasne`) — potrzebuje `PozycjeZK` do `UtworzNaPodstawieZapotrzebowania`. Próba z encjami z projekcji (EF6) była WOLNIEJSZA: leniwe ładowanie i tak pytało bazę po każdej pozycji, a śledzenie wielu encji spowalniało kolejne zapytania.

**Weryfikacja:** nowy tryb własny = stary tryb własny, 0 różnic na wszystkich polach (symbol, ilość, jm, dostawca, stany, źródłowe ZK). Sucha próba `zd` OK w trybie SDK i własnym.

**Rozjazd SDK vs tryb własny (był WCZEŚNIEJ, nie od tej zmiany):** na danych TESTOWYCH M-OLD tryb własny pokazuje 4 pozycje, których SDK nie liczy — `027-100.00Z`, `2602-100.42X`, `2627-100.04XX`, `3333` (wszystkie Towar). Przyczyna nieustalona. W firmie porównać się nie da, dopóki SDK pada na „Gasket” (działa tam tylko tryb własny). Dopóki jej nie ma, NIE przełączać na „zawsze tryb własny” (dałoby to −1,1 s w domu), bo wynik różni się od Subiektu.

**Przełącznik do porównań:** zmienna środowiskowa `NEXORECON_ZAPOTRZEBOWANIE` procesu mostu: `wlasny` = tryb własny mimo działającego SDK, `stary` = dawna droga encjami. Ustawić w Pythonie PRZED startem mostu (ubić `NexoRecon.exe`). JSON ma `czasy_ms` per etap.

Powiązane: [[feedback_most_rebuild_release]], [[project_subiekt_most_stan_serwera]].
