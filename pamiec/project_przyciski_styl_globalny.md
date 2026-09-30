---
name: project_przyciski_styl_globalny
description: "Wygląd przycisków RM_BAZA z jednego miejsca (rm_przyciski.py): ramka groove + podświetlenie pod myszą; pułapki Tk na Windows"
metadata:
  node_type: memory
  type: project
  originSessionId: 2ce09832-b3af-42b5-8d1b-2f96962306d6
  modified: 2026-09-30T02:13:58.859Z
---

Od 30.09.2026 przyciski w całej RM_BAZA stylizuje `rm_przyciski.wlacz(self)` — wołane w `MainWindow.__init__` zaraz po `super().__init__()`, PRZED budową okien (baza opcji Tk działa tylko na przyciski tworzone później).

* Baza opcji (`*Button.*`, priorytet `widgetDefault`): tło `#fbfcfd`, `relief=groove`, `bd=2`. Przycisk z własnym `bg`/`relief` zachowuje swoje.
* `bind_class("Button", "<Enter>/<Leave>", add="+")`: jasny → `#dcebf8`, kolorowy → rozjaśniony o 30 %. Nieaktywne bez podświetlenia. `<Leave>` przywraca kolor TYLKO, gdy przycisk ma nadal nasz kolor podświetlenia (kod zmienia `bg` w locie, np. „Wystaw RW”).

**Pułapki Tk na Windows (sprawdzone pomiarem pikseli):**
* `relief=solid` rysuje CZARNĄ ramkę — user: „za ciemne”. `groove` bierze odcienie z tła przycisku.
* `highlightThickness`/`highlightBackground` na tk.Button NIE rysuje szarej ramki (tylko kropkowany fokus).
* Tk nie podświetla tk.Button pod myszą sam — `activebackground` widać tylko przy wciśnięciu.
* Rozjaśnienie 18 % na nasyconych kolorach było niewidoczne („kolorowe nie mają podświetleń”).
* Wzorzec opcji musi zaczynać się od `*` (pierwszy człon to nazwa aplikacji); ścieżka okna `.!edytorwindow` w wzorcu nie działa.

Edytor kartotek ma własną, ciemniejszą paletę (`TLO #c9d3dc`, `TLO_SEKCJI #e6ebf0`) i wysokość 960 (panel 5 pakowany przed panelem 2). Powiązane: [[project_treeviewselect_czysci_panel]], [[project_zrzut_ekranu_dpi]].
