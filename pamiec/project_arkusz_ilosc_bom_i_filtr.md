---
name: project_arkusz_ilosc_bom_i_filtr
description: "Arkusz: kolumna Ilość BOM pokazuje liczbę (nie krążek) i eksport XLSX ją niesie; filtr Dostawca po wyborze wraca na POCZĄTEK nazwy (xview_moveto)"
metadata:
  type: project
---

# Arkusz RM_BAZA: Ilość BOM i filtr Dostawca

Dwie naprawy z 25.09.2026 (`b53b4ae`, `4c2fc59`).

## Kolumna „Ilość BOM" — liczba, nie krążek

Krążek pojawiał się, gdy pozycja występowała w **więcej niż jednym module**
z ilościami (`MODUŁ = "300(2),600(1)"`). Intencja była taka, że suma nie
oddaje rozbicia — ale **arkusz i tak ma JEDEN wiersz na pozycję**, więc
rozbicia w tym widoku nie widać. Symbol zasłaniał liczbę, która jest
policzona, i nic w zamian nie dawał.

Zdjęte w `_display_items_in_sheet` **i** w `export_to_xlsx`.

Wprowadzone 16.04.2026 (`c21c6e8` „Koniec dnia"), bez śladu w pamięci projektu.

### Dwie rzeczy naprawione mimochodem

1. **Martwa blokada edycji** (`on_cell_edited`, kol. 3) sprawdzała
   **WARTOŚĆ PO EDYCJI** (`new_value == <symbol>`), a symbol znikał z komórki,
   gdy tylko user zaczynał pisać. Łapała więc wyłącznie wyjście z komórki
   **bez zmiany** — przypadek i tak nieszkodliwy — a **przepuszczała realny
   zapis do `work_qty`**. Usunięta razem z symbolem.
2. **Eksport XLSX nie niósł ilości**: w pliku był symbol, a import
   (`raw_bom_val == <symbol>`) podstawiał za niego „Ilość (zam.)". Teraz
   w pliku jest prawdziwa suma z BOM-u.

### ⛔ NIE RUSZONE — celowo

* **Krążki w kolumnach Δ** (zmiana ręczna) i **ODEBRANE**
  (dostarczone ≥ zamówione) — inne znaczenie, zostają.
* **Osiem odczytów `== <symbol>`** w importach — zgodność wsteczna ze starymi
  plikami XLSX, które symbol nadal zawierają.

## Filtr „Dostawca" — widać POCZĄTEK nazwy

Zgłoszone po kompilacji: w polu „Dostawca" na drugiej belce
([[project_topbar_two_rows]]) widać było same końcówki („…ODUKT lasery").

⛔ **Przyczyna nie ma związku z `.exe`.** `width=18` w ttk to 18 znaków
**przeliczonych na piksele wg czcionki**, więc próg ucinania wypada gdzie
indziej przy innym DPI albo podmienionej czcionce — **ten sam `.exe` na innej
maszynie pokazuje co innego**. Readonly Combobox to w środku Entry: przy
tekście szerszym niż pole przewija się na KONIEC, bo tam stoi kursor.

Fix: **`xview_moveto(0)` po wyborze** — widok wraca na początek nazwy, czyli
na tę część, która odróżnia dostawców.

### ⛔ Próbowane i odrzucone

* **Poszerzanie pola** — rozpycha belkę, a najdłuższych nazw i tak nie pomieści.
* **Dymek z pełną nazwą** — nie działał, user uznał za zbędny. Zapisane też
  w komentarzu w kodzie, żeby nie wracać do pomysłu. (Kontrast:
  w selektorze projektu dymek **działa** i został — [[project_project_combo_tooltip]].)

Powiązane: [[project_topbar_two_rows]], [[project_project_combo_tooltip]],
[[project_jedno_zrodlo_prawdy_ilosci]].
