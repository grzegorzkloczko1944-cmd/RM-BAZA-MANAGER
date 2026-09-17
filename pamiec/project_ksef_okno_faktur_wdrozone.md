---
name: project_ksef_okno_faktur_wdrozone
description: Okno „Faktury z KSeF" (kafel 🧾 w panelu Subiekt) — ZBUDOWANE 17.09.2026; gdzie co się zapisuje, co przetestowane, pułapki Tk i testów ze zrzutami
metadata:
  type: project
---

**Zastępuje punkt wznowienia z [[project_ksef_okno_stan_17_09]]** — okno istnieje
i działa. Zbudowane 17.09.2026 wieczorem na M-OLD, testowane na trzech
fakturach (QUAY 55 poz., AMB 5, alu-frost 4) i bazie demo Subiekta.

## Co to jest

`ksef_faktury_gui.py` — NOWE okno, osobne od archiwum w menu KSeF
(`ksef_archiwum.OknoArchiwum` zostaje nietknięte, z układem kolumn, który
użytkownik sam ustawił). Wejście: panel Subiekt → kafel „🧾 Faktury z KSeF"
→ `RM_BAZA.open_subiekt_faktury()`.

Układ na wzór makiety (`G:\Mój dysk\SUBIEKT\ChatGPT Image 17 wrz 2026,
20_52_03.png`), ale nie 1:1 — użytkownik tak chciał: drzewo faktur po dacie
z odznakami (Nowa / W toku (N) / Rozstrzygnięta), nagłówek z Podmiot1/2,
WZ, kwotami i kontrahentem w Subiekcie, zakładki Pozycje / Dodatkowe
informacje / Plik XML, **panel decyzji wbudowany na dole** (nie modal),
skok „Następny brak" po każdym zapisie.

## ⚠️ Gdzie co się zapisuje — trzy miejsca, żadnej nowej tabeli mapowań

| decyzja | trafia do | przez |
|---|---|---|
| symbol dostawcy → kartoteka | **SUBIEKT**, `DaneAsortymentuDlaPodmiotu` | most `symbole-dostawcy --zapisz` |
| numer rysunku RM → kartoteka | `mapowania` (istniejąca, klucz `numer_rysunku`) | `subiekt_mapowania.put(..., sposob="faktura")` |
| „czym jest linia" (typ, projekt, komentarz) | `FV_KSEF.pozycje.decyzja` (JSON) | serwer `ksef-decyzja-zapisz` |

Powód braku własnej tabeli: [[project_symbole_dostawcy_w_sferze]] — Sfera ma
to wbudowane, dublowanie byłoby błędem.

`decyzja` JSON: `{typ: towar|usluga|zbiorcza|rysunek, asortyment_id, symbol,
nazwa, numer_rysunku, projekt, komentarz, kto, kiedy, nowa?}`. Decyzja
człowieka NAKŁADA się na wynik `kk.dopasuj()` (`nalozyc_decyzje`) — usługa nie
zostanie towarem, bo pasuje symbolem.

Odznaka „Rozstrzygnięta" celowo zamiast „Rozliczona" z makiety — rozliczenie
(FZ) to osobny etap, którego okno nie robi. AMB z 5 rysunkami bez kartotek
jest „rozstrzygnięta" (RYSUNEK_RM ∈ STATUSY_OK), choć na PZ nic z niej nie
wejdzie — zgodnie z decyzją z [[project_obieg_przyjec_dostawa_pz]].

## Serwer — zmiany wdrażać RAZEM (`rm_serwer.py` + `rm_serwer_operacje.py`)

- `ALTER TABLE pozycje ADD COLUMN decyzja TEXT` (warunkowy, w `zastosuj_migracje_ksef`)
- `ksef-pozycje` zwraca też `decyzja`; nowe `ksef-pozycje-wszystkie` (odznaki
  drzewa jednym zapytaniem) i `ksef-decyzja-zapisz` (UPDATE, nie REPLACE —
  REPLACE skasowałby `indeks`/`dodatkowe`)
- `_indeks_rysunkow`: zapasowa ścieżka `projects/` obok mastera — w firmie
  bazy są w `Projekty/RM_BAZA_projects`, na M-OLD w `projects/`; bez tego
  indeks u budującego był PUSTY (0 projektów) i okno nie podpowiadało projektów

⚠️ **Serwer nie przeładowuje operacji** — po zmianie `rm_serwer_operacje.py`
restart obowiązkowy. Migrację schematu da się puścić bez restartu tą samą
funkcją (`ops.zastosuj_migracje_ksef(con)` na `dane/FV_KSEF.sqlite`), ale
nowych operacji to nie dołoży.

⚠️ **Ubicie lokalnego serwera na M-OLD ZAMKNĘŁO otwartą RM_BAZA** (23:10,
17.09.2026) — ta sama pułapka co w firmie, nie tylko usługa Windows.
Ścieżka wyjścia nie została wskazana w kodzie (heartbeat pokazuje baner,
nie wychodzi; `os._exit(0)` jest w normalnym zamykaniu). Przed restartem
serwera sprawdzić `Get-Process` po `RM_BAZA_v15` i ZAPYTAĆ.

## Most

`symbole-dostawcy` bez `--plan` = ODCZYT listy powiązań (`CzyZapis` liczy
go jak `progi`: zapis tylko z planem). Z planem + `--zapisz` = zapis.
Zbudowany lokalnie (sha po `ee3acf0`), **NIE wystawiony** na
`\\W2019S\RM_SERWER$\MOST`.

## Przetestowane (harness ze zrzutami, 17.09.2026)

- wybór faktury, dopasowanie z powiązań Subiekta (lp 5 QUAY → `688 ZZ` z
  `DaneAsortymentuDlaPodmiotu`), zimny i ciepły most
- zapis usługi (lp 43 `OBSLUGA`) → tylko archiwum; zapis towaru z kartoteką
  (lp 7 `6001 2RSR-C-2HRS` → `6001 ZZ`) → archiwum + Subiekt (odczytane z
  powrotem: 16 powiązań); rysunek + projekt (AMB lp 2 → projekt 10)
- odznaki: QUAY 38 → 36 braków po dwóch decyzjach

NIE testowane: „Załóż nową kartotekę" (formularz `subiekt_asortyment` +
`po_zapisie` → dowiązanie symbolu), „Pobierz nowe z KSeF" (brak tokena),
mapowania RM przy rysunku Z kartoteką.

## ⚠️ TEN SAM SYMBOL W KILKU WIERSZACH TO NIE DUPLIKAT

Faktura QUAY `RVQ/05195/26` ma `CP 5M 25` w wierszach 35 (6 szt.) i 36
(2 szt.), w tej samej cenie 11,35. Podobnie `RCK80 25x34` (47 i 48),
`PGIKR 8 D` / `PGIKR 16 D`. Wygląda na błąd wystawcy i tak zostało
zgłoszone (17.09.2026), ale to poprawne zachowanie:

| Lp. | ilość | Numer wydania |
|---|---:|---|
| 35 | 6 szt. | `WZ/01578/26` |
| 36 | 2 szt. | `WZ/01584/26` |

Towar przyszedł **dwiema dostawami** i każda ma własny wiersz z własnym WZ.

**Okno NIE SKLEJA takich wierszy — celowo:**
* WZ to krok 1 kojarzenia faktury z przyjęciami ([[project_obieg_przyjec_dostawa_pz]]);
  sklejenie do 8 szt. gubi informację, z której dostawy co przyszło,
* na PZ te pozycje idą osobno, bo to osobne przyjęcia,
* decyzja zapisuje się per `nr_wiersza` — zlanie rozjechałoby się z archiwum.

Obie linie dopasowują się do tej samej kartoteki i to jest w porządku.

Otwarte (nie zrobione): dyskretny znacznik „1 z 2 / 2 z 2" przy powtórzonym
symbolu, żeby nie trzeba było porównywać kolumny WZ wzrokiem.

⚠️ Co u QUAY faktycznie utrudnia dopasowanie (i z czym okno już sobie radzi):
wiodące spacje w `P_7`, symbol z doklejonym zamiennikiem
(`618/4 2Z=684 2Z`, `3304 2RS=5304 EE`), brak `<Indeks>`, `OBSLUGA` jako
trzy osobne wiersze.

## Szata graficzna i nazewnictwo (18.09.2026)

Okno przeszło na **paletę okna dokumentów** (`subiekt_dokumenty_gui`):
granatowy pasek tytułu `#34495e`, szary pasek filtrów `#ecf0f1`, legenda
kolorów, **tksheet zamiast ttk.Treeview** (szerokości przez
`podepnij_szerokosci`, klucz `ksef_faktury_pozycje`), stopka. Powód:
„okna zakładki SUBIEKT mają wyglądać jak jeden program".

* Kolor niesie **kolumna Status i Typ**, nie cały wiersz — przy 14 kolumnach
  pełne tło dawało pasiastą ścianę.
* **Numerator wierszy tksheet WYŁĄCZONY** (`sheet.hide("row_index")`) —
  stał obok kolumny „Lp." i wyglądał jak drugie ID. Prawdziwym numerem jest
  Lp. Z FAKTURY: ono siedzi w decyzji, a numer widoku przy filtrze myli.
* Kolumny kartotekowe rozbite: `Kartoteka` (samo ID) | `Nr rysunku / symbol`
  | `Nazwa kartoteki` | `Opis kartoteki`. ⚠️ **`Opis` wymaga czytania
  katalogu WPROST z mostu** — `subiekt_scalanie.wczytaj_katalog_subiekta()`
  zwraca tylko {id, symbol, nazwa} i gubi `Opis`; wspólnej funkcji nie
  ruszamy, bo jej format to kontrakt innych okien.
* **Liczniki są FILTRAMI** — klik pokazuje tylko dany rodzaj, drugi klik
  wraca. `_widoczne` to podzbiór `_dop`; wszystko, co mapuje wiersz na
  pozycję, musi iść przez `_widoczne`, nie `_dop`.

### ⚠️ TW / US to rodzaje kartotek Subiekta, ZB i RM — NIE

Pytanie użytkownika: „myślałem że w Subiekcie mam TW, KT, USL — co to za RM?".
Subiekt zna TW / KT / US / OP. Panel odpowiada na INNE pytanie — „czym jest
ta linia faktury" — i dwie odpowiedzi nie są rodzajem kartoteki:

| | co to naprawdę | w Subiekcie |
|---|---|---|
| **ZB** | jedna linia = wiele detali (alu-frost „Detale cięte laserem") | **żadna kartoteka** — nie idzie na PZ |
| **RM** | „Rysunek RMPAK": szukany po numerze rysunku, nie po symbolu dostawcy | zwykły **TW albo KT** — rodzaj bierze się stamtąd |

Każdy przycisk ma **dymek** (`DYMKI_TYPU`, wygląd jak `_show_bom_tooltip`
w arkuszu: `#ffffcc`, Arial 9) z wyjaśnieniem i przykładem z realnej faktury.
Treść dymka RM zredagował użytkownik — nie przepisywać bez pytania.

⚠️ Rozważane i ODRZUCONE: rozbicie RM na „TW RM" i „KT RM". Pomiar: 26 z 643
kartotek z numerem rysunku to komplety (symbole `…Z`/`…ZZ`), więc detal
z rysunku faktycznie bywa jednym i drugim — ale **z faktury nie da się tego
poznać**, a gdy wskażesz kartotekę, rodzaj już w niej jest. Pytanie „TW czy
KT?" przerzucałoby na człowieka decyzję, którą Subiekt zna lepiej.

### ⚠️ `wyglada_na_usluge()`: OBSLUGA z QUAY nigdy nie działała

Docstring twierdził, że `OBSLUGA` ma jednostkę `usł.` — **w danych jest
`szt.`**, a `Opis` to „Obsluga" (bez „usług"). Ani jednostka, ani opis jej
nie łapały; „Usługi: 1" w liczniku brało się z ręcznej decyzji człowieka.
To samo z alu-frost „Usługa Kurierska" (`szt`, bez DodatkowyOpis).

Naprawione 18.09.2026 — trzeci test: nazwa/indeks/Opis **zaczynające się**
od „usług…" albo „obsług…" (`_NAZWA_USLUGI`). Tylko początek tekstu, bo
„usług" w środku bywa częścią nazwy towaru. Zmierzone: 4 trafienia
(alu-frost lp 4, QUAY lp 43-45), zero fałszywych na `Uszczelka`,
`Obsada łożyska`, `Tuleja obsługi`.

## Pułapki, które kosztowały rundy

- **Grid Tk odbiera miejsce kolumnom z wagą, gdy treść jest za szeroka** —
  lewa kolumna wartości nagłówka zapadła się do ZERA („Data wystawienia"
  stała pusta obok „Numery WZ"). Wagi tylko na pustej kolumnie-buforze.
- **`Treeview.selection_set` tego samego wiersza zgłasza `<<TreeviewSelect>>`
  jak klik** — przebudowa drzewa po przeliczeniu odznak przeładowywała
  fakturę i czyściła panel decyzji tuż po zapisie. `_wybrano_fakture` ignoruje
  wybór równy bieżącej.
- **Raport PO nadpisywany przez skok do następnego braku** — `_raport`
  zostaje na wierzchu panelu, dopóki człowiek sam nie kliknie innej pozycji
  (`_auto_skok` odróżnia skok od kliku).
- **Zrzut ekranu z sesji narzędzia: `ImageGrab.grab(bbox)` daje CZARNY obraz**;
  działa `ImageGrab.grab(window=int(okno.frame(), 16))` (PrintWindow,
  Pillow 12). Test: `scratchpad/test_okno_faktur{2,3}.py` — wzorzec do
  ponownego użycia przy innych oknach.
- Pierwszy harness „przełączał fakturę" sam — artefakt skryptu (jawne
  `_wybrano_fakture()` + zimny most), nie okna; dwa czyste przebiegi nie
  powtórzyły.
- **Etykiety zależne od danych z mostu trzeba odświeżyć PO jego odpowiedzi.**
  „Kontrahent w Subiekcie: sprawdzam…" wisiał wiecznie, gdy fakturę wybrano
  przed dociągnięciem kontrahentów — ustawiany był tylko przy wyborze faktury
  (18.09.2026). `_tlo_gotowe` woła teraz `_ustaw_kontrahenta` w obu gałęziach.
- **Dymek (Toplevel) nie łapie się na `ImageGrab.grab(window=…)`** — zrzut
  pokazuje okno bez niego. Testować obecność i treść przez `winfo_children()`,
  nie wzrokowo (`scratchpad/test_dymki.py`).
- **Python nie przeładuje modułu w locie**: po zmianie w `ksef_faktury_gui.py`
  samo zamknięcie i otwarcie okna nic nie da — trzeba zrestartować RM_BAZA.

## Co dalej (kolejność z planu obiegu przyjęć)

1. ~~test „Załóż nową kartotekę" na demo~~ — nadal NIE zrobiony
2. ~~ekran przyjęcia DOSTAWY~~ — ZROBIONY 18.09.2026, [[project_przyjecie_dostawy_pz]]
3. ~~powiązanie z pozycją ZD~~ — ZROBIONE PRZY OKAZJI punktu 2 (Subiekt trzyma
   `Realizuje` sam, przez `WypelnijNaPodstawieZD`)
4. ~~PZ~~ — ZROBIONE, punkt 2
5. **rozliczanie faktury względem PZ po WZ** — PLAN gotowy, kodu NIE MA,
   patrz [[project_rozliczanie_faktury_z_pz_plan]] (punkt wznowienia)
