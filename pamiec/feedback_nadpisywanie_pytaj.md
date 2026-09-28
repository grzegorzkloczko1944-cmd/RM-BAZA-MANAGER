---
name: feedback_nadpisywanie_pytaj
description: "Nadpisywanie istniejących danych (zdjęcia, kartoteki) wymaga pytania ZA KAŻDYM RAZEM — zgoda jest jednorazowa, nigdy stała"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 94cf9632-ccf8-4bf7-bcc9-11963398558f
  modified: 2026-09-28T15:40:39.965Z
---

Zgoda na nadpisanie istniejących danych dotyczy **tylko tego jednego
uruchomienia**. Nie wolno jej traktować jako reguły dla danego rodzaju
danych ani zapisywać w kodzie jako trwałego wyjątku.

**Why:** 28.09.2026 przy wgrywaniu miniatur łożysk użytkownik zgodził się
nadpisać istniejące zdjęcia. Opisałem to w kodzie jako „WYJĄTEK dla
łożysk" — czyli stałą regułę. Sprostował: „nie wyjątek teraz, dzisiaj,
jeśli na przyszłość ma być nadpisanie, masz pytać".

**How to apply:** przełącznik `--nadpisz` w
`subiekt_lozyska_zdjecia.py` (i każdy podobny) uruchamiać wyłącznie po
świeżym potwierdzeniu. Domyślne zachowanie systemu zdjęć to POMIJANIE
kartotek, które już mają obrazek — patrz `subiekt_miniatury_masowo.py`.
To samo dotyczy nadpisywania nazw/opisów istniejących kartotek
(tryb `kartoteki` mostu, status `do-zmiany`): pokazać listę PRZED
zapisem i poczekać na zgodę.

Szersza zasada: [[feedback_nic_po_cichu]] — każda zmiana danych z oknem
przed i raportem po.
