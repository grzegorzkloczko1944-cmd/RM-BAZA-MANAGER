---
name: project_subiekt_id_tozsamosc
description: Dopasowanie arkusz<->Subiekt idzie po Id kartoteki (subiekt_id), symbol tylko awaryjnie - zmiana nazwy w arkuszu ani w Subiekcie nie robi juz dubli
metadata:
  type: project
---

# `subiekt_id` — tożsamość pozycji po Id kartoteki (02.10.2026)

## Dlaczego

Dopasowanie arkusz <-> Subiekt szło WYŁĄCZNIE po tekście symbolu
(`subiekt_symbol`). Psuła je każda zmiana nazwy:

* **w arkuszu** — user zmienił HGH15SO -> HGH15SOK (projekt 2637), a
  `subiekt_symbol` został stary; „Przelicz" z ZK nie trafił i dopisał dubla;
* **ręcznie w Subiekcie** — przemianowanie kartoteki zmienia symbol na
  WSZYSTKICH dokumentach (Subiekt trzyma je po Id), a arkusz dalej ma stary
  tekst. Tego nie zatrzymuje nic: odmowa mostu („kartoteka użyta na
  dokumentach") dotyczy tylko trybu `symbole`, nie okna Subiekta.

Id kartoteki nie rusza ani jedno, ani drugie. Decyzja użytkownika: wariant 3.

## Co się zmieniło

**Most** (binarka wymaga wystawienia na serwer):
* `Stan.cs` — `Poz.Id` (init-property; null dla nieistniejących);
* `ZkIlosci.cs` — `PozIlosc(Symbol, Ilosc, Id)` przez nową
  `Projekt.CzytajPozycjeZkZId` (stara `CzytajPozycjeZk` zostaje — używa jej
  zapis ZK);
* `WydanieStan.cs` — pole `id` w każdej pozycji.

⚠️ PUŁAPKA EF: `Id = p.AsortymentAktualny.Id` w ZAGNIEŻDŻONEJ projekcji
(`d.Pozycje.Select(...)`) rzuca `TargetInvocationException` i cały tryb
oddawał **0 pozycji** z `blad`. `Symbol` przez tę samą nawigację działa.
Rozwiązanie: Id JEDNYM zapytaniem po całym asortymencie
(`Asortymenty().Dane.Wszystkie().Select(a => new { a.Id, a.Symbol })`) — ten
sam wzorzec co w `Stan.cs`. NIE wracać do Id w projekcji.

**Python:**
* migracja `items.subiekt_id INTEGER` (słownik `required_cols` w RM_BAZA);
* `subiekt_projekt.pobierz_ilosci_zk_z_id` -> `(ilosci, kart, zk, blad)`,
  `kart = {SYM: (Id, symbol jak pisze Subiekt)}`; stara funkcja deleguje;
* `_zapisz_ilosci_z_subiekta`: trafienie **najpierw po Id** (`sym_po_id`),
  po symbolu awaryjnie; przy trafieniu po symbolu bez Id — **uzupełnienie Id
  wstecz** (to cała migracja danych: projekt po projekcie, przy pierwszym
  odświeżeniu pod lockiem). Gdy symbol na ZK różni się od zapisanego —
  **arkusz idzie za Subiektem**: `subiekt_symbol` zawsze, „Nr rysunku" tylko
  gdy był równy staremu symbolowi (pozycja z kartoteki, nie z rysunku).
  Komunikat „Symbole zmienione w Subiekcie" — nic po cichu;
* `_dopisz_pozycje_z_zk` — nowy wiersz z `subiekt_id` od razu;
* zasiew (`subiekt_projekt.zapisz_zasiew`) — Id jednym `query_stock` po
  wszystkich symbolach, jeden `executemany`;
* `subiekt_wydane_do_arkusza.zapisz(..., idy=)` — `_mapa_bom_id` i trafienie
  po Id przed symbolem.

Wszystko ma ścieżkę awaryjną: baza bez kolumny (otwarta bez locka) albo most
bez `Id` -> dopasowanie po symbolu jak dotąd.

## Sprawdzone 02.10.2026 (kopia bazy ZP196 + nowa binarka)

`zk-ilosci` 31/31 z Id; `wydanie-stan` 34/34 z `id`; `stan` Id dla
istniejących, null dla brakujących. Symulacja synchronizacji: 31/31 trafień,
30 wierszy dostało Id wstecz, sztucznie przemianowany wiersz rozpoznany po Id
i poprawiony, 0 dubli. `zapisz` RW: wiersz z obcym symbolem trafiony po Id.

Powiązane: [[project_aktualizacja_bom_zmiana_numeru]] [[project_wydane_do_arkusza_symbol]]
