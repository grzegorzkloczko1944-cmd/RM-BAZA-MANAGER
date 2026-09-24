---
name: project_dopasuj_kartoteke_wiersza
description: "PPM w arkuszu → Dopasuj kartotekę Subiekta: jedna pozycja, działa TYLKO na niezaimportowanych; bez zapisu do globalnych mapowań"
metadata:
  type: project
---

**„Dopasuj kartotekę Subiekta…" — menu prawego klawisza w arkuszu RM_BAZA
(24.09.2026).**

Porządkowanie elementów znormalizowanych PRZED importem projektu do Subiekta.
Użytkownik robi to **pozycja po pozycji, patrząc na wiersz w arkuszu** — nie
listą w osobnym oknie. Okno „Dopasowanie kartotek" (menu SUBIEKT) zostaje
nietknięte i robi to samo hurtem dla całego BOM-u.

Moduły: `subiekt_dopasuj_wiersz.py` (logika) + `subiekt_dopasuj_wiersz_gui.py`
(okno). Handler `dopasuj_kartoteke_wiersza()` w RM_BAZA ~12950.

## Dwa przypadki użycia (słowa użytkownika)

1. **częstszy** — projekt jeszcze nieimportowany, obrabiamy wszystko,
2. **rzadszy** — dokładka BOM-u po imporcie, obrabiamy tylko dopisane wiersze.

Oba obsługuje ta sama blokada: stare wiersze **same się bronią**, bo mają
`subiekt_symbol`. Nie trzeba ich odróżniać ręcznie.

## ⛔ Blokada: tylko pozycje NIEZAIMPORTOWANE

`sprawdz_edytowalnosc()` odmawia w czterech przypadkach:

| powód | co to znaczy |
|---|---|
| `zasiew` | ma `subiekt_symbol` — nazwa jest już KLUCZEM kartoteki |
| `zamowiona` | `ordered_flag` — należy do dokumentu ZK/ZD |
| `z_subiekta` | `is_manual=1` + symbol + notes półprodukt/„z zamówienia ZK" |
| `brak_wiersza` | wiersz zniknął z bazy |

Znacznik `subiekt_symbol` to **ten sam**, którym blokowana jest edycja nazwy
w komórce (RM_BAZA ~14186) — narzędzie nie wymyśla własnej reguły. Powód:
po zasiewie zmiana nazwy sprawia, że okno Projekt/Aktualizacja nie rozpozna
istniejącej kartoteki i założy **DUPLIKAT** obok niej.

⚠️ Blokada sprawdzana **dwa razy**: przy otwarciu okna i ponownie w
`zastosuj_wybor()` — między jednym a drugim mógł wejść zasiew z innej maszyny.

## Decyzje

- **Bez zapisu do globalnych mapowań** (decyzja użytkownika). Zmiana siedzi
  w BOM-ie tego projektu. Spójne z odcięciem czytania mapowań z tego samego
  dnia — patrz [[project_dopasowanie_wylaczone_mapowania]].
- **Celujemy w JEDEN wiersz po `item_id`**, nie po nazwie jak
  `wpisz_numery_do_bom()`. Dwie pozycje o tej samej nazwie w różnych
  złożeniach to norma — hurtowe dopasowanie po nazwie ruszyłoby obie.
- **Zapis przez `db_manager.project_con`**, nie własnym `sqlite3.connect` —
  przy locku RM_BAZA pisze do kopii lokalnej ([[project_zapis_do_bazy_projektu]]).
- **`src_name` nietknięte** — nadpisujemy tylko `work_name` i
  `work_drawing_no`, żeby dało się wrócić do nazwy konstruktora.
- **⛔ Okno NIE ZAKLADA kartotek samo** (poprawione 24.09.2026 po zgłoszeniu).
  Pierwsza wersja miała przycisk wołający `zaloz_kartoteke()` z czterema
  wartościami z automatu. Dla pozycji będącej samym kodem („7810210")
  powstawała kartoteka **„7810210 / 7810210"** — nazwa bez żadnej informacji,
  czyli dokładnie ten bałagan, który porządkowanie ma usuwać.

  Teraz przycisk **„➕ Nowa kartoteka w edytorze…"** otwiera Edytor kartotek
  (`subiekt_edytor_gui`, nowy tryb `nowa={"symbol","nazwa"}`) z wypełnionymi
  polami: user ma komplet — rodzaj, jednostkę, cenę ewid., położenie, opis —
  i listę istniejących kartotek obok. Nazwę nadaje człowiek. Zapis zostaje
  pod zielonym przyciskiem edytora.

  ⚠️ Nazwa równa symbolowi NIE jest podstawiana — pole zostaje puste jako
  czytelny sygnał „uzupełnij".
  ⚠️ Symbol już zajęty w Subiekcie → pozycja dostaje symbol roboczy
  (`NOWA-01`), a lista filtruje się na ten symbol. Bez tego user zapisałby
  zmiany **na cudzej kartotece**.
- **Symbol** liczy `subiekt_projekt.symbol_z_nazwy()` — ta sama funkcja,
  której użyje zasiew projektu; trafia do edytora jako wartość początkowa.

## Lancuch F4 -> edytor -> arkusz (domkniety 24.09.2026)

Pierwsza wersja urywala sie w polowie: „Nowa kartoteka w edytorze" otwierala
edytor i **zamykala okno dopasowania** (`self.destroy()`). Po zapisaniu
kartoteki i zamknieciu edytora **wiersz w arkuszu zostawal nietkniety** —
nikt do niego nie wracal.

Rozwiazanie (pomysl uzytkownika): przycisk **w EDYTORZE**, obok „Zapisz te
pozycje do Subiekta":

```
⬅ Podmień w arkuszu RM_BAZA
```

* **Widoczny tylko wtedy**, gdy edytor otwarto z arkusza przez F4 —
  `open_window(..., do_arkusza=callback)`. Przy zwyklym otwarciu z menu
  SUBIEKT przycisku NIE MA (sprawdzone).
* **Szary do czasu zapisu** kartoteki do Subiekta. Wstawienie do arkusza
  symbolu, ktorego w Subiekcie nie ma, dawaloby wiersz wskazujacy na nic,
  a zasiew projektu zalozylby DRUGA kartoteke obok. Aktywuje sie
  w `_zapis_gotowy` razem z `w_subiekcie = True`.
* Okno dopasowania **zostaje otwarte** i czeka z callbackiem; zamyka sie
  dopiero po udanej podmianie.

## Edytor: JEDNO okno dla obu wejsc + „Klonuj" w panelu 2

**Jedno okno** (zgloszenie 25.09.2026: „dlaczego okna edytora sie roznia?").
Przycisk „Wstaw do arkusza RM_BAZA" powstawal tylko przy `do_arkusza`, wiec
edytor z menu SUBIEKT wygladal inaczej niz ten z F4. Teraz przycisk jest
ZAWSZE — bez kontekstu arkusza wyszarzony, a podpis mowi dlaczego:
„nieaktywne — otworz edytor klawiszem F4 z wiersza arkusza".

**„Klonuj" w panelu 2**, obok „Zapisz te pozycje". Logika ta sama co
„Duplikuj" w panelu 1 (drzewo) — ale pod reka tam, gdzie user patrzy na
POLA kartoteki. Oba przyciski zostaja.

Klon przenosi komplet: nazwa, rodzaj, jednostka, cena, opis, VAT-y, pola
wlasne i sklad kompletu. NIE przenosi `polozenie` (regal jest wlasnoscia
konkretnej kartoteki, nie wzoru). Dostaje wolny symbol roboczy
(`_nowy_symbol`), wiec oryginalu nie nadpisze; fokus ladu je na polu Symbol
z zaznaczona trescia, bo to jedyne pole do zmiany.

⚠️ **`_domknij_opis()` PRZED klonowaniem.** `tk.Text` nie ma trace, wiec
swiezo wpisany opis siedzi w widgecie, nie w modelu — bez tego klon
dostawalby stara wartosc, a wpisany tekst przepadal przy przerysowaniu
drzewa (ta sama pulapka co 16.09.2026, wykryta testem).

Symbol kartoteki juz zapisanej do Subiekta jest `readonly` (`w_subiekcie`),
wiec klon jest jedynym sposobem na zrobienie jej wariantu.

## Do arkusza ida TRZY kolumny

Numer rysunku (symbol), Nazwa i **Opis** — zyczenie uzytkownika. Opis idzie
do `work_desc`, tak samo jak nazwa do `work_name`: kolumna ROBOCZA,
`src_desc` z importu zostaje nietknieta.

Sprawdzone na atrapie bazy: po podmianie `work_drawing_no`, `work_name`
i `work_desc` maja dane z kartoteki, `src_name` i `src_desc` bez zmian,
blokada zasiewu dalej odmawia.

## Podglad zmiany: DWIE linie, nie cztery pola

Pierwsza wersja pokazywala kazde pole osobno:

```
Numer / symbol:
   przed: (pusto)
   po:    7810210
Nazwa:
   przed: 7810210
   po:    Zawias
```

User musial skladac w glowie, jak ostatecznie bedzie wygladal wiersz.
Teraz jedna linia = jeden stan wiersza, `SYMBOL   Nazwa`:

```
teraz:    7810210
bedzie:   7810210   Zawias
```

Funkcja `_opis_wiersza(symbol, nazwa)` w module logiki; `podglad_wyboru()`
zwraca gotowe `teraz` i `bedzie`. Raport PO zapisie ma ten sam uklad
(`bylo` / `jest`). `zmiany` zostaje jako lista pol, ktore sie ruszyly.

## Szukanie kandydatów

Klucz wg zasady z 09.09.2026: **jest numer → numer, nie ma → nazwa**.
Najpierw trafienia DOSŁOWNE (zielone tło, `norm_kod` równe), potem
`Indeks.szukaj()` po członach — `„6004 rS"` znajduje `„SS 6004 2RS INOX"`
mimo innej kolejności słów. Sprawdzone.

## ⛔ Bez locka nie ma zapisu

Projekt otwarty bez locka jest **READ-ONLY** (`db_manager.is_local == False`)
i `UPDATE` kończy się surowym `attempt to write a readonly database`.
Zgłoszone 24.09.2026 jako „zapis nie idzie" — komunikat SQLite nic nie mówi
człowiekowi, a praca z wyborem kartoteki szła na darmo.

Dwa poziomy zabezpieczenia:
1. **handler w RM_BAZA** nie otwiera okna, gdy `self.have_lock` jest fałszywe
   — mówi „Kliknij Przejmij Lock" ZANIM zaczniesz wybierać,
2. **`zastosuj_wybor()`** łapie błąd SQLite i tłumaczy go
   (`BLOKADA_BRAK_LOCKA`) — lock mógł zniknąć PO otwarciu okna: wymuszenie
   z drugiej maszyny albo wygaśnięcie.

## ⚠️ Katalog MUSI iść z `subiekt_magazyn_gui`, nie z `subiekt_scalanie`

`subiekt_scalanie.wczytaj_katalog_subiekta()` (i jego cache) **tnie kartotekę
do `id/symbol/nazwa`** — robi to `subiekt_podobne._przelicz()`. Opisu, rodzaju
ani ceny tam nie ma, choć most je zwraca.

Do wyboru wariantu to za mało: kartoteki `KFL000/001/002/004` mają **nazwę
równą symbolowi**, więc po symbolu i nazwie nie da się wskazać właściwej —
rozstrzyga dopiero **opis** i **cena** (zgłoszone 24.09.2026). Okno czyta
więc `subiekt_magazyn_gui.pobierz_katalog()`, tak jak Edytor kartotek.

Kolumny listy: Symbol, Nazwa, **Opis**, **Rodzaj**, **Stan**, **Cena netto**.

**Stany hurtem**, nie per symbol: `pobierz_magazyn(tylko_niezerowe=True)`
w tym samym wątku co katalog (~0,1 s na komplet). Wcześniejsze `query_stock`
per symbol bywało niedostępne i kolumna wisiała na `…`.

**Autowyszukiwanie** — lista filtruje się w trakcie pisania
(`var_fraza.trace_add`), debounce 180 ms. Tak działa sekcja 4 Edytora
kartotek i tego user oczekuje; przycisk „Szukaj" i Enter zostają.

Stany magazynowe dociągane osobnym wątkiem PO pokazaniu listy — brak stanów
nie może blokować wyboru kartoteki.

⚠️ Dopisane do `RM_BAZA_v15_MAG.spec` w **obu** listach (hiddenimports
i datas) — import jest leniwy, więc PyInstaller sam go nie zobaczy
([[project_build_leniwe_importy]], piąty nawrót tej pułapki).

Powiązane: [[project_dopasowanie_podpowiedzi]], [[project_blokada_klucza_zasiew]],
[[feedback_nic_po_cichu]].
