---
name: project_zielen_na_zk_arkusz
description: "Zielone tlo \"pozycja jest na ZK\" w arkuszu - kolumna Ilosc dostarczonych, jeden odcien, wariant dwukolorowy odrzucony"
metadata: 
  node_type: memory
  type: project
  originSessionId: bd77b2db-aa7d-4871-a44f-b0388f221230
  modified: 2026-09-09T19:58:32.805Z
---

Kolorowanie „pozycja jest na ZK w Subiekcie" w arkuszu RM_BAZA. Stan wyjsciowy od 2026-09-09, commit `6eb0ebc` na origin/main.

**Jak ma byc:**
- kolor `_COLOR_SUBIEKT_PARA = "#E8F8E8"` (jeden, bladozielony) na **kolumnie 6 „Ilosc dostarczonych"**
- zrodlo: `order_qty IS NOT NULL` w tabeli `items` pliku projektu, czytane raz na odswiezenie przez `_wczytaj_pary_subiekta()`
- kolumna 0 (Nr rysunku) **bez** tego kolorowania — tam zostaje sama niebieska czcionka pozycji bibliotecznych
- w kolumnie 6 jaskrawa zielen `#90EE90` (komplet: `delivered_qty >= target_qty`) wchodzi pozniej w kodzie i **celowo nadpisuje** blada

**Czego NIE robic ponownie:** wariantu dwukolorowego — drugi odcien `#B4E3B4` dla „na ZK + nadpisany recznie", mieszania z szarym tlem nadpisania, przykrywania zieleni przez podswietlenie zaznaczonego wiersza. To bylo commity 2c2bb34, beb676e, 2cb0da6, 16770b2, ae8a345 — wszystkie cofniete w `3430228`.

**Why:** uzytkownik odrzucil rozroznianie odcieniem — ciemniejsza zielen mieszana z szarym byla nieczytelna i mnozyla znaczenia w jednej komorce. Na pytanie o trzeci odcien na przeciecie „na ZK + komplet" odpowiedzial „tak jak jest jest OK", czyli swiadomie godzi sie, ze przy komplecie nie widac juz, czy pozycja byla na ZK.

**How to apply:** przy zmianach kolorow arkusza trzymac jeden odcien na jedno znaczenie; nie dokladac odcieni na przeciecia stanow bez wyraznej prosby. Kod: `_color_single_row()` w [[project_disk_layout]] / RM_BAZA_v15_MAG_STATS_ORG.py, ok. linii 4984.
