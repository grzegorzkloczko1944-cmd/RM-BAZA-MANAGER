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

## Co dalej (kolejność z planu obiegu przyjęć)

1. test „Załóż nową kartotekę" na demo
2. ekran przyjęcia DOSTAWY → 3. powiązanie z pozycją ZD → 4. PZ → 5. rozliczanie
