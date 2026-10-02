---
name: project_przeglad_dokumentow_edycja_zk
description: Okno „Przegląd dokumentów" 02.10.2026 — filtr na projekt z RM_BAZA, pozycje w kolejności arkusza, szukanie w pozycjach, edycja ilości/ceny ZK (most zk-ilosc/zk-cena), usuwanie pozycji ZK prawym klikiem; pułapki układu tksheet
metadata:
  type: project
---

`subiekt_dokumenty_gui.py` + most `ZkIlosc.cs` (nowy), `ZkPozUsun.cs`, `CommandDispatcher.cs`. Zrobione 02.10.2026 na M-OLD.

**Co umie okno:**
- **Projekt startowy** — `open_window(parent, projekt=nazwa)`; RM_BAZA (`open_subiekt_dokumenty`) podaje nazwę projektu wybranego w arkuszu, filtr „Projekt" startuje na jego numerze. Pomijane, gdy okno otwarto na konkretny dokument (`szukaj=`, klik w RW z okna wydania).
- **Filtr projektu po pojedynczych numerach** — ZD wspólne ma w Uwagach „2627,3500"; lista miała osobną pozycję „2627,3500", a filtr „2627" takiego ZD nie pokazywał. Teraz `_numery_projektow(d)` i dopasowanie przez członkostwo.
- **Pozycje w kolejności arkusza** — `_kolejnosc_arkusza(numer)`: to samo ORDER BY co `database_manager.get_project_items` (ZNORMALIZOWANE na górze, potem numer, nazwa, NOCASE), klucze: subiekt_symbol / numer / nazwa. Odczyt RAZ na projekt i okno (read-only SQLite + jedno `projects-list`). Spoza arkusza → na koniec po symbolu; dokument bez projektu → po symbolu. Test 2637: 301/301 pozycji w kolejności arkusza.
- **„🔍 w pozycjach:"** — filtr symbol/nazwa/opis, debounce 250 ms, działa też w trybie „Wszystkie pozycje".
- **Dwuklik „Ilość" / „Cena netto" pozycji ZK** → własne okno (`_okno_ilosci(d, p, pole)`, styl `komunikat`: pasek, karta pozycji, „teraz → nowa", ±, różnica na żywo, walidacja w oknie) → suchy przebieg → `komunikat` warn → zapis → wynik z read-backu → przeładowanie na tym samym ZK. Pozostałe kolumny / inne dokumenty → karta pozycji.
- **Prawy klik „🗑 Usuń pozycję z ZK…"** → `zk-poz-usun` z `{"zk": numer}` (nowe pole planu; dotąd tylko po projekcie). Czerwone okno: pozycja z BOM wróci przy Projekt/Aktualizacja — trzeba ją też ukryć w arkuszu.
- Przycisk „🗑 Usuń zaznaczone DOKUMENTY" (dawniej „Usuń zaznaczone" — mylił się z pozycjami).

**Most `zk-ilosc` / `zk-cena`** (jeden moduł `ZkIlosc.cs`, o polu decyduje plan `{"zk", "pozycje":[{"symbol","ilosc"|"cena"}]}`): ZK po numerze jednym zapytaniem; odmawia: ilość ≤ 0 (usuwa się, nie zeruje), zmniejszenia pozycji z ZD, symbolu w kilku wierszach, ceny ujemnej. Ilość przez `Projekt.UstawIloscPozycjiPubl` + `Przelicz()`; cena przez `Pw.UstawCenePozycjiPubl` (NettoPoRabacie) **bez `Przelicz()`** (mógłby podstawić cennik). Read-back jednym zapytaniem. Sprawdzone TYLKO suchym przebiegiem — pierwszy realny zapis robi user.

**Pułapki:**
- tksheet `Sheet(...)` bez `width/height` żąda szerokości wszystkich kolumn → w `ttk.PanedWindow` wychodził poza panel i chował się pod sąsiednim razem z paskiem przewijania. Fix: `width=200, height=200` (rozmiar i tak daje pack). Wagi PanedWindow dzielą tylko NADMIAR → podział ustawiony `sashpos` na 60% po zmapowaniu.
- `_przelacz_pozycje` wołał nieistniejące `_pokaz_pozycje` (odznaczenie „Wszystkie pozycje" się wysypywało) — teraz metoda istnieje i renderuje.
- Test okna poza RM_BAZA: `_serwer()` łączy się z IP firmowym (192.168.100.84), nie z lokalnym — `projects-list` zwraca {}; w testach wstrzykiwać `w._pid_po_numerze = {"2637": 72}`. Wątek okna wymaga `root.mainloop()` (nie pętli `update()`).

Powiązane: [[project_zapotrzebowanie_szybkie]], [[project_okna_pokazane_zbudowane]], [[project_cena_na_pozycji_pw]], [[project_ilosc_zk_wlasnosc_subiekta]].
