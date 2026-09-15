---
name: project_subiekt_karta_pozycji
description: "Karta pozycji (subiekt_pozycja_gui) — nawigator po złożeniu; tryb \"komplet\" w moście; pułapki tksheet i wątków Tk"
metadata: 
  node_type: memory
  type: project
  originSessionId: 834ab505-1a4e-4f62-bb02-1b4871507207
  modified: 2026-09-06T19:15:34.743Z
---

**`subiekt_pozycja_gui.py`** — jedno okno pokazujące wszystko o jednej pozycji.
Powstało 06.09.2026 (commity `0b17a50`, `cc2cfce`, `6d665f7`).

## Skąd się otwiera

Dwuklik albo PPM w **każdym** arkuszu z pozycjami: główny arkusz RM_BAZA (PPM),
Magazyn, Dokumenty (pozycje dokumentu), Stany w Subiekcie, Zamówienia ZD.
Dostawcy pominięci — tam wiersze to kontrahenci.

**Jedno okno na aplikację** (`_OTWARTA`): kolejne wywołanie przełącza istniejącą
kartę, bo to nawigator i przy kilkunastu klikach robił się stos okien, każde
z własnymi wątkami do mostu.

## Trzy źródła, oznaczone kolorami

| Kolor | Sekcje | Skąd |
|---|---|---|
| 🟣 INVENTOR | Należy do, Zawiera | drzewko `*_OUT.xlsx` (`subiekt_projekt.read_tree`) |
| 🟢 RM_BAZA | Dane pozycji | arkusz projektu (tabela `items`) |
| 🔵 SUBIEKT | Kartoteka i stany, Struktura złożenia | most, na żywo |

Wiersz **„Zgodność z Inventorem"** porównuje skład z obu drzewek po rdzeniu numeru
(bez końcówki X/XX/Z/ZZ — zapisują je różnie). Wyłapuje: komplet bez składników,
składniki z Inventora bez kartoteki, nadmiar w Subiekcie.

**ID (wiersz BOM)** to link — `RM_BAZA.jump_to_bom_item()` przełącza projekt przez
`_switch_to_project` (odmawia przy locku) i zaznacza wiersz. **Projekty w nagłówku**
są klikalne: przełączają kontekst karty, gdy detal jest w kilku maszynach.
Otwierając z ZD bierzemy projekt **z filtra**, nie pierwszy z `bom_ref` — lista jest
sortowana numerycznie, więc 2632 wygrywało z 3000.

## Tryb `komplet` w moście (Komplet.cs)

Most umiał tylko **zapisywać** składniki. Odczyt przez gotowe relacje Sfery:
`Asortyment.SkladnikiKompletu` (skład) i `SkladnikiWKompletach` (relacja odwrotna —
bez przelotu po bazie). Element obu to `SkladnikKompletu` z `Komplet`, `Skladnik`,
`Ilosc`.

**Sprawdzone: komplety NIE wiszą w powietrzu.** `2632-350.24ZZ` = Komplet, 2 składniki-
towary, wchodzi w 3 komplety nadrzędne. Rodzaje w Subiekcie: Towar 3209, Komplet 152,
Usługa 83 — **„Komponentu" nie ma**. Z/ZZ → Komplet, X/XX → Towar ([Projekt.cs:85](../../../c%3A/RMPAK_CLIENT/Repozytoria/RM-BAZA-MANAGER/subiekt_sfera/NexoRecon/Projekt.cs)).

## ⚠️ Pułapki, które kosztowały wiele rund

**Wątki a Tk.** `self.after()` wołane z wątku roboczego rzuca „main thread is not in
main loop" — w `pythonw` **bez śladu**. Wyniki muszą wracać kolejką odpytywaną
z wątku głównego (jak `subiekt_panel._odbierz_wyniki`), a pętla odbioru **nigdy** nie
może się przerwać: pierwszy `TclError` kończył ją `return` i wszystkie kolejne
odpowiedzi przepadały.

**Zniszczone widgety po przebudowie treści.** Sekcja Subiekt była pusta po „Wstecz",
bo `_wypelnij` padało na `lbl_projekty.config()` — tę etykietę niszczy
`_projekty_gotowe`, budując linki. `TclError` kończył metodę **przed** startem wątków.
Znalezione dopiero **logiem do pliku** (`C:\RMPAK_CLIENT\subiekt_logi\karta.log`) —
zgadywanie zawiodło trzy razy.

**tksheet:**
- `get_selected_rows()` zwraca **pusty zbiór** przy pojedynczej zaznaczonej komórce
  (czyli po zwykłym kliku) — trzeba dołożyć `get_currently_selected()`
- `sheet.bind()` **nie dociera do komórek** — podpinać do `sheet.MT` i `sheet.RI`
- kółko myszy: `bind_all` jest globalny i zostaje po zamknięciu okna; `<MouseWheel>`
  nie propaguje do rodzica, więc podpinać rekurencyjnie do dzieci

**How to apply:** Log karty zostaje włączony — przy każdym problemie z pustymi
sekcjami czytać go zamiast zgadywać. Patrz [[project_subiekt_stan_05_09_2026]],
[[project_subiekt_most_stan_serwera]].
