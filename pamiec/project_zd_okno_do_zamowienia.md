---
name: project_zd_okno_do_zamowienia
description: Okno Zamówienia do dostawców 02.10.2026 — kolejność liczona przy KAŻDYM odświeżeniu (klucz_wiersza), filtr „do zamówienia" = Kupić>0 albo stan po zdjęciu ≤ minimum (do_zamowienia); co znaczy kolumna ZK
metadata:
  type: project
---

`subiekt_zamowienia.py`, 02.10.2026.

**Kolejność (`klucz_wiersza`)**: znormalizowane → bez ZD → z dostawcą → dostawca → symbol (casefold, białe znaki zwinięte). Do 02.10 sortowało się tylko przy wczytaniu — wiersz, któremu user wskazał dostawcę ręcznie, zostawał w sekcji „bez dostawcy" (filtr QUAY: WJ200…, WS-10…, potem dopiero 018kW…, DSNU…). Teraz `self.wszystkie.sort(key=klucz_wiersza)` w każdym `_refill` (sort stabilny — zaznaczanie nie przestawia).

**„do zamówienia" (`do_zamowienia(w)`)** — jedna reguła dla filtra „Stan" i obu liczników: brak ZD **i** (Kupić > 0 **albo** `stan_min > 0` i `dostępne − ze_stanu ≤ stan_min`). Granica „≤" = ta sama co pomarańczowe podświetlenie Min/Opt („10/15" = domawiaj przy 10). Pozycje w całości ze stanu bez naruszenia minimum widać w „— wszystkie —". Ręczne pozycje mają Kupić ≥ 1, więc zostają. ⚠️ „Kupić" dalej = tylko brak na projekt; dobicie do optymalnego robi okno Magazyn (osobna, nie podjęta zmiana).

**Kolumna „ZK"** (user pytał, co to jest — wyjaśnione, NIE zmieniane): rozbicie sumarycznej potrzeby Subiekta na dokumenty ZK z ilościami („ZK 1/CENTRALA/2026 (88), ZK 2 (8)"). Potrzebna do filtra projektu, powiązania ZD↔ZK i kontroli wspólnych zamówień. Forma techniczna — ew. „3500: 88, 2627: 8" zamiast numerów ZK (kolumna Projekt by się zdublowała); user nie zdecydował.

Powiązane: [[project_zd_sortowanie_znormalia]], [[project_zapotrzebowanie_szybkie]], [[project_subiekt_magazyn]].
