---
name: project_subiekt_edytor_kartotek
description: "Edytor kartotek Subiekta — model grafowy, pułapki Treeview, reguły spójne z resztą systemu (08.09.2026)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 47fa97da-3439-4292-864b-075339162d55
  modified: 2026-09-08T17:48:11.219Z
---

`subiekt_edytor_gui.py` — okno do zakładania/edycji wielu kartotek i kompletów
naraz. Kafel „✎ Edytor kartotek" w panelu Subiekta, tryb mostu `kartoteki`.

**Model to GRAF, nie drzewo:** `pozycje{symbol: Kartoteka}` + `relacje[(rodzic,
dziecko, ilosc)]` + `korzenie[]`. Ta sama kartoteka może być w kilku kompletach.
Usunięcie składnika kasuje relację; pozycja znika z `pozycje` dopiero przy
OSTATNIM wystąpieniu. `_osadzone()` (osiągalne z korzeni) to jedyne źródło dla
walidacji, planu, liczników i blokady symboli — bez tego powstają „duchy":
pozycje niewidoczne w drzewie, które i tak idą do Subiekta.

**Pułapki Treeview, na które wpadłem:**
- symbol NIE może być parsowany z tekstu wiersza — symbole ze spacją
  (`DN20 K=34`, `Z 7640051`) obcinały się do pierwszego członu i operacje
  po cichu nie działały; trzymam go w kolumnie ukrytej przez `displaycolumns`;
- kolor tagu obejmuje CAŁY wiersz — żeby wyróżnić fragment (rodzaj TW/KT/US),
  trzeba osobnej kolumny;
- rozwijanie tylko `get_children("")` zostawia zagnieżdżone komplety zwinięte,
  co wygląda jak zgubienie składu;
- DnD wymaga progu ruchu (8 px), inaczej drgnięcie przy kliknięciu wyciąga
  składniki.

**Reguły wspólne z resztą systemu — NIE wymyślać własnych:**
- symbol z nazwy = `subiekt_projekt.symbol_z_nazwy` + `rozroznij_symbol`
  (ta sama, co okno „Nowa kartoteka" i automat z projektu). Własna numeracja
  rozjechałaby tę samą pozycję na dwie kartoteki w Subiekcie;
- Położenie = `PoleWlasne1`, gdzie `null` znaczy „nie ruszaj", NIE „wyczyść"
  (patrz [[project_subiekt_magazyn]] — 1367 regałów z migracji).

**Why:** okno zapisuje do produkcyjnego Subiekta, a symbol po zapisie jest
kluczem nie do zmiany — każdy cichy błąd kończy się śmieciem w bazie.

**How to apply:** przy zmianach w tym oknie sprawdzaj symbole ze spacją i to,
czy nowa ścieżka przechodzi przez `_osadzone()`. Zmiana rodzaju Komplet→Towar
musi rozstrzygnąć los składników — `do_planu` daje skład tylko kompletom.

Dokumentacja: `SUBIEKT_ZMIANY_2026-09-08.md`.
