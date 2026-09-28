---
name: project-wstaw-z-subiekta-recznie
description: "Dodaj pozycję ręcznie" ma przycisk Z Subiekta (F4) — szuka po symbolu, nazwie I OPISIE; osobne okno bez zapisu do bazy
metadata:
  type: project
---

Okno „➕ Dodaj pozycję ręcznie" w RM_BAZA ma przycisk **🔍 Z Subiekta…**
(albo **F4**). Otwiera `subiekt_wybor_kartoteki_gui.py` — wyszukiwarkę
kartotek filtrującą w trakcie pisania po **symbolu, nazwie i opisie**.
Wybrana kartoteka wypełnia Nr rysunku (symbol), Nazwę i Opis.
Wdrożone i sprawdzone na żywo 28.09.2026.

**Why:** wpisywanie symbolu z pamięci kończyło się literówką albo
kartoteką „KFL001 / KFL001" — czyli dokładnie tym bałaganem, który
porządkowanie ma usuwać. Zasiew projektu nie rozpozna takiej pozycji jako
tej samej kartoteki. Opis w wyszukiwarce jest konieczny, bo po symbolu
i nazwie nie odróżnisz wariantów tej samej części (ten sam powód co
w [[project_dopasuj_kartoteke_wiersza]]).

**How to apply:**

- `subiekt_wybor_kartoteki_gui.py` **nic nie zapisuje do bazy** — oddaje
  wybraną kartotekę przez callback `on_wybor(kartoteka)`. Tym różni się od
  okna „Dopasuj kartotekę Subiekta" ([[project_dopasuj_kartoteke_wiersza]]),
  które przepisuje wiersz. Da się je podpiąć pod kolejne formularze.
- ⛔ Filtr po opisie jest **w tym module** (`szukaj_w_katalogu`), NIE
  w `subiekt_dopasowanie.Indeks.szukaj`. Tamta metoda ma dwóch innych
  wołających (okno dopasowania BOM-u, dopasowanie wiersza), którzy liczą na
  dzisiejsze wyniki — nie rozszerzać jej o opis.
- Typ / Materiał / Grubość / Dostawca / Ilość zostają puste **celowo**:
  kartoteka Subiekta ich nie niesie w formie, którą da się wpisać bez
  zgadywania. Status pod polami mówi „uzupełnij Typ i ilość", kursor
  wchodzi w pole Typ.
- Nadpisanie wypełnionych pól pyta o zgodę z listą `było → będzie`
  ([[feedback_nic_po_cichu]], [[feedback_nadpisywanie_pytaj]]); przy pustym
  formularzu wstawia bez klikania.
- Katalog przez `subiekt_scalanie.wczytaj_katalog_subiekta()` (ma cache,
  [[project_katalog_cache_odswiezanie]]), F5 wymusza świeży.
