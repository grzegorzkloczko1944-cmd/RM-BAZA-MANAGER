---
name: project_cena_na_pozycji_pw
description: "Cena na pozycji dokumentu w Sferze to Cena.NettoPoRabacie, nie liczba - potwierdzone zapisem i read-backiem"
metadata: 
  node_type: memory
  type: project
  originSessionId: bd77b2db-aa7d-4871-a44f-b0388f221230
  modified: 2026-09-09T21:22:59.251Z
---

`PozycjaDokumentu.Cena` w Sferze **NIE jest liczbą**, tylko obiektem `InsERT.Moria.ModelDanych.Cena` z czterema zapisywalnymi polami decimal:

```
NettoPrzedRabatem, NettoPoRabacie, BruttoPrzedRabatem, BruttoPoRabacie
```

Cena pozycji = **`NettoPoRabacie`**. To pole czyta `Dokumenty.cs` przy read-backu, więc zapis i odczyt patrzą w to samo miejsce. Dla PW produkcji własnej ustawiamy oba netto na tę samą wartość (produkcja nie zna rabatu); brutto zostawiamy Subiektowi — przelicza je ze stawki VAT kartoteki.

`ICena.UstawCene()` z `InsERT.Moria.Dokumenty.Logistyka` **się NIE nadaje** — ustawia ceny „zgodnie z wybranym poziomem cen", czyli pobiera z cennika. Do wpisania własnej ceny wytworzenia trzeba pól wprost.

Zaimplementowane w `subiekt_sfera/NexoRecon/Pw.cs` jako `UstawCenePozycji()`; `PozPlan` ma opcjonalne `Cena`, więc stare plany (inwentaryzacja magazynu) działają bez zmian. Gdy ceny nie da się ustawić — **PW się NIE zapisuje**: dokument po 0 zł wygląda na poprawny i trzeba go potem ręcznie anulować.

Potwierdzone 2026-09-09 na M-OLD: `PW 1/MASTER/2026`, `027-200.01` 2 szt., wysłano 123,45 → read-back zwrócił `Cena: 123.45`.

**How to apply:** przy dokładaniu ceny do RW albo innego dokumentu użyć tego samego wzorca. Szukać w [[reference_dokumentacja_sfery]] zanim zacznie się zgadywać nazwy właściwości. Kontekst całości: [[project_rmpak_produkcja_pw_rw]].
