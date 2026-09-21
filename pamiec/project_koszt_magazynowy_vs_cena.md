---
name: project_koszt_magazynowy_vs_cena
description: "Na dokumentach magazynowych (PW/RW/WZ) wartosc niesie KosztMagazynowy, nie Cena.NettoPoRabacie"
metadata: 
  node_type: memory
  type: project
  originSessionId: bd77b2db-aa7d-4871-a44f-b0388f221230
  modified: 2026-09-09T23:18:16.447Z
---

W Sferze `PozycjaDokumentu` ma DWIE różne miary wartości:

* **`Cena.NettoPoRabacie`** — parametr HANDLOWY. Ma sens na ZK/ZD/FS. Na dokumencie magazynowym zostaje **zerowy**.
* **`KosztMagazynowy`** i **`JednostkowyKosztMagazynowy`** — wartość magazynowa, którą Subiekt liczy SAM z ceny przyjęcia, wg metody wyceny rozchodu.

Potwierdzone 2026-09-10 na `RW 1/MASTER/2026`: cena netto = 0 przy każdej pozycji, a `KosztMagazynowy` = 4848 zł — dokładnie tyle co źródłowe PW.

**Skutek dla kodu:** `Dokumenty.cs` czytał wyłącznie cenę, więc każdy dokument magazynowy wyglądał na bezwartościowy. Teraz czyta oba pola, a wartość dokumentu liczy z kosztu, gdy jest niezerowy. Przegląd dokumentów ma dynamiczne nagłówki: PW/RW/WZ → „Koszt jedn." / „Wartość magazynowa", ZK/ZD → „Cena netto" / „Wartość".

**Czego NIE robić:** nie wpisywać ceny na RW ręcznie. Gdy ten sam detal leży na magazynie w kilku partiach po różnych cenach, ręczna wartość rozjedzie się z metodą wyceny rozchodu. Subiekt wie lepiej — czytamy, nie ustawiamy. (Przy PW jest odwrotnie: tam cenę wpisujemy, bo to nasza kalkulacja — [[project_cena_na_pozycji_pw]].)

Ceny widoczne na starych RW w bazie demo pochodzą z ręcznego wystawienia w GUI Subiekta, które podstawia cenę ewidencyjną kartoteki. Sfera tego nie robi.

**How to apply:** przy każdym nowym odczycie dokumentu magazynowego sprawdzić, czy nie czyta się ceny zamiast kosztu. Kontekst: [[project_rmpak_produkcja_pw_rw]].
