---
name: project-edycja-ilosci-w-oknie
description: "Edycja ilości w oknie Projekt/Aktualizacja — ilość DOCELOWA korzenia przelicza poddrzewo, most dopisuje różnicę na ZK"
metadata: 
  node_type: memory
  type: project
  originSessionId: 42739f9a-ed55-4c6c-a06d-d2bf1b97a8bf
  modified: 2026-09-09T01:28:56.337Z
---

**WDROŻONE 2026-09-09, potwierdzone przez usera.**

Dwuklik w kolumnę **„Ilość"** w oknie Projekt/Aktualizacja otwiera wpisanie **ilości DOCELOWEJ** (nie mnożnika — wpisujesz 3, ma być 3 sztuki).

**Co wolno edytować:**
- **KORZENIE drzewa** (złożenia niewchodzące w skład niczego) — przeliczają CAŁE poddrzewo kaskadowo. Przykład sprawdzony: korzeń 1→2 przeliczył 161 pozycji, `2602-100.45ZZ` 4→8 (wchodzi 4× w rodzica), `2602-100.44` 8→16.
- **Pozycje SPOZA drzewa** (znormalizowane, dodane ręcznie, biblioteczne) — ustawiane pojedynczo, mnożenie ich NIE dotyka (decyzja usera: "te swobodne to im wpisuję tylko ilość ręcznie").
- **Składnik wewnątrz drzewa** → komunikat, że ilość wynika ze struktury; trzeba zmienić korzeń.

**Skład czytany z SUBIEKTA, nie z pliku OUT** — `drzewo_z_subiekta()` (tryb mostu `komplet`, zwraca `Skladniki` + `WchodziW`). Decyzja usera: "zakładamy z OUT ale czytamy drzewo przy edycji już z subiekta". Gdy mostu brak — fallback na `read_tree()` z OUT. Sprawdzone: oba drzewa identyczne (0 różnic na 25 kompletach).

**Most USTAWIA ilość wprost** (`Projekt.cs`, potwierdzone read-backiem ze świeżego procesu 2026-09-09): działa w GÓRĘ i w DÓŁ, `0` zeruje pozycję. Trzy rzeczy MUSZĄ być razem, inaczej `Zapisz()` zwraca true a dokument się nie zmienia:
1. `UstawIlosc` to METODA ROZSZERZAJĄCA (`PozycjaExtensions.UstawIlosc(PozycjaDokumentu, decimal)`, statyczna) — szukać refleksją w klasach statycznych, nie na instancji.
2. **`ob.Przelicz()` przed `ob.Zapisz()`** — tak robi przykład SDK `FakturowanieWydan.cs`; bez tego zmiana nie utrwala się.
3. **KONSOLIDACJA wierszy**: ten sam symbol bywa w KILKU wierszach ZK (pozostałość po starej wersji „dopisz różnicę", która dodawała nowe wiersze przez `Pozycje.Dodaj`). Pierwszy wiersz := ilość docelowa, reszta usunięta (`Usun` na `ob.Pozycje` NIE ISTNIEJE — refleksja go nie znajduje) → **zerowana** przez `UstawIlosc(0)`. Sfera przyjmuje wiersze z ilością 0.

Statusy: `do-uzupelnienia` / `do-zmniejszenia` (dry-run), `ilosc-uzupelniona` / `ilosc-zmniejszona` (po zapisie). Okno pokazuje osobne kafelki ZWIĘKSZY / ZMNIEJSZY ILOŚĆ (zmniejszenie czerwone, na górze).

**Skutek uboczny do wiedzy:** `ZK 1/CENTRALA/2026` ma teraz ~20 wierszy z ilością 0 (zdublowane symbole po starej wersji, wyzerowane). Sumy się zgadzają (`CzytajPozycjeZk` sumuje), ale w GUI Subiekta widać puste wiersze. Do ręcznego wyczyszczenia w Subiekcie, jeśli przeszkadzają.

**Kluczowe funkcje** (`subiekt_projekt.py`): `korzenie_drzewa()`, `ilosci_z_drzewa()` (rekurencja z ochroną przed cyklem), `drzewo_z_subiekta()`, `build_plan(..., ilosci_korzeni=...)`, `_edytuj_ilosc()`, `_nazwa_kolumny()`.

**Why:** BOM mówi ile wynika z konstrukcji, ale zamawiać można n sztuk zespołu. Wpisywanie tego w arkuszu nie działało, bo plan bierze ilość wg `COALESCE(order_qty, work_qty, src_qty)` — a `order_qty` wypełnia cache z Subiekta, więc plan zawsze równał się stanowi ZK i rozjazd nie mógł powstać.

**Pułapki, które kosztowały czas:**
- Stały most czyta listę symboli z klucza **`symbols`** (nie `symbole`) — `ServerHost.cs:375`.
- `Treeview` z `show="tree headings"`: numeracja `identify_column` myli — użyć `tree.column(kol, "id")` i porównywać po NAZWIE kolumny.
- Wpisane ilości żyją tylko w oknie (`self.ilosci_korzeni`, `self.ilosci_reczne`) — NIE zapisują się do BOM-u. Zamierzone: BOM zostaje ilością konstrukcyjną.
- **Read-back po zapisie robić ze ŚWIEŻEGO procesu** (`NexoRecon.exe zk-ilosci` CLI), nie przez stały most — stały most trzyma jedną sesję Sfery i przy diagnozie „zapis nie działa" trzeba najpierw wykluczyć cache. (Tu akurat cache nie był winny, ale sprawdzenie zajęło jeden krok i wykluczyło całą klasę hipotez.)
- Gdy `Zapisz()` zwraca true, a dokument się nie zmienia — dodać diagnostykę wartości pozycji NA KAŻDYM ETAPIE (przed/po ustawieniu, po Przelicz, po Zapisz). To ona pokazała „przed=1" przy sumie 2, czyli zdublowane wiersze — zamiast zgadywać po raz czwarty.

**Reguła edycji (doprecyzowana 2026-09-09):** główne złożenie (korzeń całego drzewa, np. `2627-000.00ZZ`) — ZABLOKOWANE; **każde inne KT** (na dowolnym poziomie) — edytowalne, zmiana przelicza JEGO poddrzewo; detal wewnątrz złożenia — zablokowany; pozycja spoza drzewa — edytowalna pojedynczo.

**Baza ilości w oknie = ŻYWE ZK, nie arkusz** (`build_plan(..., bazowe_ilosci=...)`, precedencja BOM < ZK < edycja usera; `_dry_run_worker` pobiera mapę przez `pobierz_ilosci_zk` — wątkowo bezpieczne, sam most). Powód: arkusz (`order_qty`) odświeża się tylko przy braniu locka, więc okno pokazywało „2", gdy ZK miało już 1; user wpisywał 1 → most słusznie mówił „bez zmian" → user widział PUSTE okna i brał to za błąd (dwa razy, 09.09.2026). Diagnoza za każdym razem ta sama: log zapisu bez kroków `zk-poz` + plan == ZK. Teraz okno startuje ze stanu dokumentu, więc „puste" znaczy naprawdę „nic do zrobienia".

**Read-back do arkusza PO ZAPISIE z okna** (`_write_done` woła `master._zapisz_ilosci_z_subiekta()` + `refresh_data()`): bez tego `order_qty` odświeżało się tylko przy braniu locka, więc po zapisie z okna arkusz i okno pokazywały STARE ilości, a kolejny zapis „nic nie robił" (bo ZK już miało cel). Objaw zgłoszony jako „raport pusty" — w rzeczywistości raport był POPRAWNIE pusty, tylko wyświetlana ilość była nieaktualna. Przy diagnozie „pusty raport": najpierw sprawdzić log zapisu (`subiekt_historia/projekt_<id>_*.json` → plan + kroki) i porównać z read-backiem ZK.

**Okna komunikatów: `komunikat()` zamiast `messagebox`** (2026-09-09). `messagebox` to NATYWNY dialog Tk — sam ustala pozycję względem monitora GŁÓWNEGO, a `parent=` tego NIE zmienia. Na stanowisku z trzema monitorami (pulpit x od −2560 do 2560) komunikat z okna na bocznym ekranie wyskakiwał na środkowym. `subiekt_projekt.komunikat(rodzic, tytul, tresc, rodzaj="info|warn|error", pytanie=False)` to własny Toplevel z `wysrodkuj()` — zwraca bool (przy `pytanie=True` Tak/Nie). W `subiekt_projekt.py` podmienione WSZYSTKIE 22 wywołania, zero `messagebox.`. Przy dodawaniu nowych dialogów w tym module — używać `komunikat()`, nie `messagebox`.

**Rozwinięcie drzewka: DECYZJA usera, nie odtwarzanie ścieżek.** Flaga `self._rozwiniete_wszystko` ustawiana przez „⊞ Rozwiń wszystko"; po każdej przebudowie (`_fill_tree`) drzewko wraca do tego stanu. Odtwarzanie po ścieżkach jest zawodne (pozycja może zniknąć z planu albo zmienić rodzica po zmianie ilości) — stąd skarga „rozwijają się, zwijają, nie ogarniam". Odtwarzanie ścieżek zostało jako zachowanie zapasowe, gdy user NIE kliknął „Rozwiń wszystko".

**Zapamiętywanie rozwinięć drzewka — klucz węzła.** `_klucz_wezla()`: numer rysunku, a gdy go brak → `"#" + tekst węzła`. Węzły bez numeru („Pozostałe pozycje", grupy) dawały PUSTY klucz, więc wszystkie miały tę samą ścieżkę i rozwinięcia myliły się między nimi — stąd „czasami zwija rozwinięte drzewka".

**GUI (2026-09-09):** raport PO zapisie to teraz okno graficzne `_okno_raportu()` — bliźniak okna potwierdzenia (kafelki + tabela pozycja po pozycji), nie messagebox. Drzewko w oknie zachowuje rozwinięte gałęzie po „Przelicz" (`_zapamietaj_rozwiniete` / `_przywroc_rozwiniete`, klucz = ŚCIEŻKA symboli, bo ten sam symbol bywa w kilku złożeniach).
