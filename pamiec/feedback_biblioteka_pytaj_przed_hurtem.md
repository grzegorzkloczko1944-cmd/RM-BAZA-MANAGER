---
name: feedback_biblioteka_pytaj_przed_hurtem
description: Przed hurtową zmianą plików już leżących w bibliotece B: (nawet „oczywista" poprawka) — zapytać usera; 29.09.2026 miniatury 205 oringów podmienione, a user: „nie trzeba ich ruszać"
metadata:
  type: feedback
---

Hurtowe zmiany w plikach, które JUŻ są w bibliotece (`B:\Znormalizowane\…`),
robić dopiero po zgodzie usera — także gdy to „tylko" miniatura albo
iProperties i wygląda na oczywistą poprawkę.

**Why:** 29.09.2026 wstawiłem natywne miniatury do 205 modeli oringów
(zmierzyłem 383 B w pliku i uznałem za pusty), user dopisał w trakcie
„ale oringi mają dobre miniatury… nie trzeba ich ruszać" — za późno,
a kopie z OldVersions zdążyłem skasować (odwrót tylko przez ponowne
wygenerowanie).

**How to apply:** najpierw suchy przebieg + pytanie z liczbą plików i tym,
co się zmieni; dopiero potem `--zapisz`. OldVersions kasować dopiero po
potwierdzeniu, że wynik jest OK. Pliki NOWE z bieżącej sesji (np. świeża
konwersja) można poprawiać bez pytania. Powiązane: [[feedback_nadpisywanie_pytaj]],
[[feedback_nic_po_cichu]].
