# Subiekt — zmiany 08.09.2026

Dwa tematy: **Edytor kartotek** (nowe okno, dopracowane w kilkunastu iteracjach
na żywych danych) i **projekt z pliku CSV** (małe złożenia spoza RM_BAZA —
funkcja NIEDOKOŃCZONA, patrz sekcja 3).

Poprzedni dzień: [SUBIEKT_ZMIANY_2026-09-07.md](SUBIEKT_ZMIANY_2026-09-07.md).
Migracja magazynu: [MAGAZYN.md](MAGAZYN.md).

---

## 1. Edytor kartotek — okno

`subiekt_edytor_gui.py` (~1700 linii), otwierane kaflem „✎ Edytor kartotek"
w panelu Subiekta. Tryb mostu `kartoteki` (`subiekt_sfera/NexoRecon/Kartoteki.cs`).

Cztery sekcje: **1** drzewo struktury, **2** szczegóły kartoteki (zakładki
Podstawowe / Handlowe / Magazyn / Dodatkowe), **3** skład kompletu,
**4** lista istniejących kartotek z Subiekta.

### 1.1. Model to GRAF, nie drzewo

```
pozycje  {symbol: Kartoteka}          — dane wspólne dla wszystkich wystąpień
relacje  [(rodzic, dziecko, ilosc)]   — wystąpienia
korzenie [symbol, …]                  — wierzchołki
```

Ta sama kartoteka może być w kilku kompletach naraz. Dlatego usunięcie
**składnika** kasuje tylko relację, a nie kartotekę — o ile jest jeszcze gdzieś
używana. Gdy to było **ostatnie** wystąpienie, pozycja znika też z `pozycje`.

> ⚠️ **Duchy.** Wcześniej usunięty składnik zostawał w `pozycje`: znikał
> z drzewa, ale szedł do walidacji i do planu zapisu. Pusty komplet blokował
> więc zapis komunikatem o pozycji, której na ekranie już nie było
> („usunąłem 2243 a komunikat dalej mam"). Druga linia obrony: `_osadzone()`
> zwraca tylko pozycje osiągalne z korzeni i **na tym** liczą się walidacja,
> plan, liczniki i blokada symboli po zapisie.

Wyjątek przy sprzątaniu: kartoteka **z Subiekta** mająca własny skład wychodzi
na wierzch drzewa zamiast wyparować — user może chcieć ją dalej edytować,
a inaczej zgubiłby się cały jej skład.

### 1.2. Symbol węzła w ukrytej kolumnie

`_symbol_wezla` parsował tekst wiersza po białych znakach, więc symbol ze
spacją (`DN20 K=34`, `Z 7640051` — takie **są** w Subiekcie) obcinał się do
pierwszego członu. Zaznaczanie, usuwanie i przeciąganie takiej pozycji celowały
w nieistniejący symbol i **po cichu nic nie robiły**.

Symbol siedzi teraz w kolumnie roboczej ukrytej przez `displaycolumns`.
Tekst wiersza może wyglądać dowolnie.

### 1.3. Przeciąganie myszą

`ttk.Treeview` nie ma DnD — trzy zdarzenia (`<Button-1>`, `<B1-Motion>`,
`<ButtonRelease-1>`) plus próg **8 px**, żeby drgnięcie przy kliknięciu nie
wyciągało składników.

- upuszczenie na **komplet** → wkłada do składu, **na początku** (doklejanie na
  koniec wyglądało jak „pozycja wypadła poza drzewko", bo ostatnie dziecko
  korzenia jest ostatnim wierszem całej listy);
- upuszczenie na **puste pole pod listą** → wyciąga na wierzch;
- upuszczenie na **towar** → nic (świadomie, żeby nie rozwalać struktury).

Cykl (A zawiera B, B zawiera A) jest blokowany — Subiekt takiego składu i tak
nie przyjmie.

### 1.4. Cel dodawania

Wynika **wyłącznie z zaznaczenia**: zaznaczony komplet → do niego; zaznaczony
składnik → do jego rodzica; nic z tego → pozycja ląduje luzem na dole.

> Krótko istniała reguła „jedyny komplet w drzewie jest domyślnym celem" —
> **usunięta**: świeżo dodane kartoteki same wchodziły do środka, czego user
> nie chciał. Zaznaczenie po dodaniu **zostaje na miejscu**; wcześniej
> przeskakiwało na dodaną pozycję i cicho zmieniało cel kolejnego dwukliku.

### 1.5. Zmiana rodzaju Komplet → Towar

Groźniejsze, niż wyglądało. Rodzaj zmieniał się w modelu, ale składniki
zostawały w relacjach i wisiały w drzewie, a `do_planu` daje skład **tylko**
kompletom. Do Subiekta poszedłby TOWAR, a pozycje zniknęłyby bez słowa;
walidacja tego nie łapała.

Teraz przy zejściu z kompletu na rodzaj bez składu pada pytanie: odpiąć
składniki (wychodzą na wierzch, nic nie ginie) czy zostawić komplet. Odmowa
cofa też combobox do stanu faktycznego.

### 1.6. Puste nazwy

`self.nazwa = nazwa or symbol` powodowało, że w drzewie stało `SKL-01  SKL-01` —
dwa identyczne napisy czytały się jak błąd wyświetlania, a naprawdę pozycja nie
miała żadnej nazwy.

Pusta nazwa **zostaje pusta** w modelu; widoki rysują `(bez nazwy — uzupełnij)`,
a walidacja zatrzymuje zapis. Zaślepka NIE trafia do danych — w `do_planu` za
pustą nazwę podstawia się symbol, jak dotąd.

### 1.7. Przycisk „Auto" przy Symbolu

Nadaje symbol **z nazwy**, wołając `subiekt_projekt.symbol_z_nazwy` +
`rozroznij_symbol` — czyli **tę samą regułę**, której używa okno „Nowa
kartoteka" i automat zakładający kartoteki z projektu.

> ⚠️ Pierwsza wersja wymyślała własną numerację `KPL-001`/`TOW-001`. Dwie różne
> reguły w jednym systemie znaczyłyby, że ta sama pozycja założona raz ręcznie,
> raz automatem **rozjeżdża się w Subiekcie na dwie kartoteki**.

Kolizje sprawdzane wobec katalogu Subiekta **oraz** pozycji już w drzewie.
Dla kartoteki zapisanej w Subiekcie przycisk jest wygaszony — symbol istniejącej
kartoteki jest kluczem.

### 1.8. Pole „Położenie" (zakładka Magazyn)

Regał/półka = `PoleWlasne1`, to samo, które pokazuje kolumna Położenie w oknie
Magazyn. Osobna ścieżka w moście (`UstawPolozenie`), bo obowiązuje tu inna
zasada niż przy polach dodatkowych:

> **`null` znaczy „nie ruszaj", nie „wyczyść".** Bez tego zapis kartoteki
> z pustym formularzem skasowałby 1367 regałów wgranych przy migracji magazynu.
> Żeby faktycznie usunąć położenie — trzeba je skasować w Subiekcie.

Tryb `komplet` zwraca teraz `Opis` i `Polozenie`, więc formularz pokazuje stan
faktyczny zamiast pustych rubryk.

Sprawdzone na żywej bazie (`016-100.03`): odczyt `R20/P4`, zapis tej samej
wartości → `bez-zmian`, innej → `Polozenie: „R20/P4" → „R20/P9"`.

### 1.9. Zapis: podsumowanie i raport

**Przed zapisem** — osobne okno (nie messagebox z trzema liczbami): pełna
struktura, komplety z rozpisanym składem, przy każdej pozycji nazwa, ilość i to,
czy będzie założona czy zmieniona. Nowe na niebiesko, komplety pogrubione.
Na dole ostrzeżenie, że **symbol po zapisie nie podlega zmianie** — to ostatni
moment na wyłapanie kompletu o roboczej nazwie `NOWA-01`.

**Po zapisie** — raport kolorowany według **wagi informacji** (tło, nie tekst,
żeby wiersz było widać kątem oka):

| Waga | Tło | Statusy |
|---|---|---|
| wymaga uwagi | czerwone | `blad`, `pominiety-brak-skladnikow` |
| nadpisanie danych z Subiekta | łososiowe | `do-zmiany`, `zmieniona` |
| nowe w Subiekcie | niebieskie | `do-zalozenia`, `zalozona` |
| uzupełnienie składu | żółte | `do-ustawienia`, `sklad-ustawiony` |
| bez zmian | szare | `bez-zmian` |

> Rozdzielenie **nadpisania** od **uzupełnienia** jest celowe: pierwsze kasuje
> wartość, którą ktoś wpisał w Subiekcie, drugie tylko wypełnia puste miejsce
> w kartotece, która i tak dopiero powstaje.

Nad tabelą legenda z licznikiem każdej grupy. Kolumna „Co" pokazuje **rodzaj
pozycji** (Towar / Komplet (Z) / Usługa), nie rodzaj kroku mostu — „kartoteka"
nic nie wnosiło, bo dotyczyło każdego wiersza. Dymek z pełną treścią po
najechaniu, `Ctrl+C` i „Kopiuj wszystko" (kolumny rozdzielone tabulatorem).

### 1.10. Drobiazgi, które okazały się realnymi błędami

- **Lista 4 pokazywała pierwsze 400 z 3469 kartotek.** Stąd „gdy usuwam to nie
  wracają do listy podręcznej" — pozycja była poza czterysetką. Limit zdjęty;
  pozycje obecne w drzewie mają ✓ i są szare (celowo **nie** ukrywane — ta sama
  kartoteka może iść do drugiego kompletu).
- **`_odswiez_drzewo` rozwijało tylko poziom 0.** Zagnieżdżony komplet zostawał
  zwinięty i jego skład znikał z ekranu — wyglądało na zgubienie składników.
  Zmienna `rozwiniete` była przy tym liczona i **nigdy nieużywana**.
- Rodzaj TW/KT/US w **osobnej kolumnie Typ** — `Treeview` nie koloruje
  fragmentu tekstu w komórce, więc dopóki skrót siedział przy symbolu, nie dało
  się go wyróżnić.
- Sekcje 3 i 4 **nie miały żadnego paska przewijania**; kolumna Szczegóły
  w raporcie obcinała treść (330 px, bez rozciągania).

---

## 2. Okna otwierają się na monitorze aplikacji

`subiekt_stany.wysrodkuj` liczyło pozycję względem rodzica poprawnie, ale zaraz
potem przycinało ją do `winfo_screenwidth/height` — a to rozmiar monitora
**GŁÓWNEGO**, nie całego pulpitu.

Stanowisko ma trzy monitory, pulpit sięga od `x=-2560` do `x=5120`, więc każde
okno otwierane z aplikacji stojącej na lewym albo prawym monitorze było ściągane
z powrotem na środkowy.

Clamp używa teraz granic **wirtualnego pulpitu** (`SM_*VIRTUALSCREEN` z Win32).
Poza Windows albo gdy metryki zawiodą — stary zakres jednego ekranu.

> Dotyczy **wszystkich** okien RM_BAZA wołających `wysrodkuj()`, nie tylko
> edytora.

| Monitor | Aplikacja | Okno |
|---|---|---|
| lewy | -1992 | -1784 |
| środkowy | 808 | 1016 |
| prawy | 3608 | 3816 |

---

## 3. ⚠️ Projekt z pliku CSV — NIEDOKOŃCZONE

**Stan: działa suchy przebieg, NIE przetestowany zapis do Subiekta.**
Do dokończenia w domu.

### 3.1. Po co

Małe złożenia (pojedynczy zespół wyeksportowany z Inventora) nie mają ani wpisu
w RM_BAZA, ani pliku `*_OUT.xlsx`, więc okno „Projekt / Aktualizacja w Subiekcie"
ich nie widziało. Produkowanie OUT tylko dla nich się nie opłaca, a sam BOM w CSV
jest już pełnym opisem składu.

Przykład: `V:\2622 Ceramizator_W\Rysunki Karuzela 200 2622\2622-200.81ZZ Zestaw Wagi.csv`

### 3.2. Jak działa

Kafel **„📄 Projekt z pliku CSV"** w panelu Subiekta (sekcja „Praca z projektem")
i bliźniacza pozycja w menu górnym. **Nie wymaga** otwartego projektu w arkuszu.

1. Wskazujesz plik CSV.
2. Okienko pyta o **nazwę projektu** (podpowiadana z nazwy pliku, idzie na ZK).
3. Dalej okno działa bez zmian: kartoteki, komplety, ZK.

### 3.3. Kształt danych

`read_items_csv` zwraca **dokładnie ten sam kształt** co `read_project_items`,
a `tree_z_csv` — co `read_tree`. Dzięki temu klasyfikacja X/XX/Z/ZZ, budowa planu
i ZK nie wiedzą, skąd przyszły dane. `build_plan` i okno dostały opcjonalny
`csv_path`; **ścieżka bazodanowa jest nietknięta**.

Szczegóły:

- symbol składnika = **Nr rysunku**, a bez numeru `symbol_z_nazwy` (elementy
  znormalizowane), czyli ta sama reguła co reszta systemu;
- **samo złożenie nie jest wierszem BOM-u** — tożsamość niesie nazwa pliku
  (`2622-200.81ZZ Zestaw Wagi.csv` → symbol `2622-200.81ZZ`, nazwa `Zestaw Wagi`),
  więc dopisujemy je jako pozycję; bez tego powstałyby same składniki bez
  kompletu, który je spina;
- kodowanie i separator **wykrywane** (eksporty z Inventora bywają cp1250,
  nagłówki mają polskie znaki);
- log zapisu idzie **pod numerem projektu**, bo `project_id` nie istnieje —
  inaczej nazwałby się samym znacznikiem czasu i nie dałoby się go odnaleźć
  przy cofaniu.

Wynik na pliku testowym: komplet `2622-200.81ZZ` typu ZZ, 8 składników,
tuleje po 2 szt., ZK z numerem projektu `2622-200.81ZZ`.

### 3.4. Co zostało do zrobienia

- [ ] **Przetestować ZAPIS** na żywym Subiekcie (dotąd tylko suchy przebieg).
- [ ] Sprawdzić **cofanie** takiego projektu — log jest pod nazwą, nie pod id;
      `SubiektProjektCofnijWindow` szuka po `project_id`.
- [ ] Zdecydować, co z **zagnieżdżeniami**: dziś CSV opisuje jedno złożenie
      (płaski skład). Podzespół = osobny plik. Czy wystarczy?
- [ ] Notatki/zadania projektu (`subiekt_historia`) zapisują się pod
      `project_id = None` — działa, ale wszystkie takie projekty trafiają
      do jednego worka.

---

## 4. Zamknięcie okna w trakcie odczytu

```
TclError: invalid command name ".!subiektprojektwindow.!frame.!button"
```

Suchy przebieg trwa kilka sekund i chodzi w wątku. Zamknięcie okna, zanim wątek
wróci, kończyło się sięgnięciem po widgety zniszczone już przez Tk.

Doszły strażniki `_zyje()` i `_po_watku()`. Po zamknięciu okna wynik **odczytu**
jest porzucany — nic się nie stało, to był suchy przebieg.

> ⚠️ **Wyjątek: zapis.** Tam most JUŻ ZAPISAŁ do Subiekta, więc zamknięcie okna
> nie może skasować śladu — log i mapowania zapisują się niezależnie od tego,
> czy jest gdzie narysować wynik. Bez logu nie da się potem cofnąć projektu,
> a kartoteki, komplety i ZK już w Subiekcie są.

Te same strażniki dostało okno cofania projektu — ma identyczny wzorzec wątków.

---

## 5. Pliki

| Plik | Co |
|---|---|
| `subiekt_edytor_gui.py` | Edytor kartotek (całe okno) |
| `subiekt_projekt.py` | `read_items_csv`, `tree_z_csv`, `open_window_csv`, `csv_path` w `build_plan`; strażniki wątków; poprawka `rozroznij_symbol` |
| `subiekt_stany.py` | `wysrodkuj` — granice wirtualnego pulpitu |
| `subiekt_panel.py` | kafle „Edytor kartotek" i „Projekt z pliku CSV" |
| `subiekt_sfera/NexoRecon/Kartoteki.cs` | tryb `kartoteki`, `UstawPolozenie` |
| `subiekt_sfera/NexoRecon/Komplet.cs` | zwraca `Opis` i `Polozenie` |
| `RM_BAZA_v15_MAG_STATS_ORG.py` | `open_subiekt_edytor`, `open_subiekt_projekt_csv` |

> **Most przebudowany i wdrożony** do `C:\iLogic\Subiekt\MOST` (08.09.2026).
> `.exe` w `dist/` jest z rana i **nie zawiera** ani Edytora kartotek, ani
> żadnej z tych zmian — wszystko działa tylko przy uruchomieniu ze źródła
> (`python RM_BAZA_v15_MAG_STATS_ORG.py`).

---

## 6. Naprawiony przy okazji: `rozroznij_symbol`

Błąd w **samej regule**, dotykający także okna „Nowa kartoteka":

```python
rozroznij_symbol("Obejmy TC DN100", {"OBEJMYTCDN100"})  # → "ObejmyTCDN100"
```

Funkcja mająca **ominąć** kolizję zwracała symbol identyczny z zajętym, bo
porównywała z uwzględnieniem wielkości liter, a wywołujący (`subiekt_asortyment.py`)
podaje zbiór wielkimi. Subiekt porównuje symbole bez względu na wielkość liter,
więc taka kartoteka trafiłaby w istniejącą zamiast założyć nową.

Porównania idą teraz przez znormalizowany zbiór. `symbol_z_nazwy` **bez zmian**.
