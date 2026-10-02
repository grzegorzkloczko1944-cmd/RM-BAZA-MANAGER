---
name: project_wydanie_poza_bom_i_zd
description: Pozycja poza BOM nie wchodzi juz do zakladki "Mozliwe do wydania"; ZD jest awaryjnym zrodlem potrzeby, gdy milcza ZK i PW
metadata:
  type: project
---

# Okno "Wydanie z magazynu": poza BOM + ZD jako zrodlo potrzeby

Zgloszone 02.10.2026: symbol **419817** (Guide rail clamps MPG-T-S) wisial
w ZP196 w domyslnej zakladce **"Mozliwe do wydania"** z PUSTYMI kolumnami
Potrzeba i Pozostalo, ze statusem `poza BOM`.

## Skad sie tam wzial

Most (`WydanieStan.cs`) buduje liste jako sume symboli **ZK + PW + RW**.
Towar byl zamowiony na **ZD 15/09/2026** (`Uwagi: "ZP196 Projekt +2639 3SZT
419817"`), ktorego ten tryb w ogole nie czytal, i wydany na **RW 91/09/2026**
(`Uwagi: "ZP196"`, 3 szt.). Wszedl wiec na liste wylacznie przez RW — bez
potrzeby, czyli `potrzeba = null`.

## Dwie naprawy

**1. Filtr (`subiekt_wydanie_gui.py:_pasuje_do_filtra`)**
`potrzeba = None` dawalo `pozostalo = None`, a warunek
`pozostalo is None or pozostalo > 0` czytal to jako "cos jeszcze zostalo".
Teraz `poza_bom` jest wykluczone z "Mozliwe do wydania" i z "Czesciowo
wydane", a WLACZONE do "Wydane" (gdy cokolwiek wydano) — inaczej pozycja
wypadlaby ze wszystkich zakladek poza "Wszystkie". Kolumna Status mowila
`poza BOM`, a filtr "do wydania" — dokladnie sprzecznosc, przed ktora
ostrzega naglowek tej metody.

**2. ZD jako awaryjne zrodlo potrzeby (`WydanieStan.cs`)**
Kolejnosc: **ZK -> PW -> ZD**. ZD czytane DOPIERO gdy milcza ZK i PW.

⚠️ **ZD NIE wchodzi do "konfliktow"** — pozycja jednoczesnie na ZK i ZD to
norma (zamowilismy u dostawcy to, co klient zamowil u nas), nie anomalia
do rozstrzygniecia przez czlowieka. ZD nigdy nie nadpisuje potrzeby, ktora
juz znamy skadinad.

Efekt na ZP196: `419817` ma `potrzeba=3, zrodlo=ZD, wydano=3` -> domkniete.
Naprawily sie przy okazji `27 T5/19` (2/2) i `27 T5/32` (4/4).

## PROBOWANE I ODRZUCONE: "RW bez numeru projektu maja numer w Uwagach"

Hipoteza z 02.10.2026, ze te 20 dokumentow to **reczne RW z numerem projektu
w Uwagach**, ktorego most nie czyta. **SPRAWDZONE — NIEPRAWDA.**

Wszystkie 20 ma Uwagi **DOSLOWNIE PUSTE** (`''`): 19 z nich to RW z 2023 roku
(sprzed calego systemu znacznikow, ustalonego 10.09.2026), plus `RW 3/09/2026`.
Nie ma tam czego parsowac.

Reczne RW z numerem w Uwagach **JUZ DZIALAJA** — `Znacznik.NumerProjektu`
bierze pierwszy czlon pierwszego wiersza, wiec samo `"ZP196"` albo `"2639"`
wpisane recznie jest rozpoznawane. Potwierdza to RW 91/09/2026 (`Uwagi:
"ZP196"`, tytul `"Rozchod wewnetrzny"` — nie z RM_BAZA) — zostalo policzone.
To byl zreszta zrodlowy dowod w tej sprawie: te 3 szt. widoczne w oknie
pochodza wlasnie z recznego RW.

Lista `rw_bez_projektu` dziala poprawnie: to dokumenty bez ZADNEGO numeru.
Dokumenty z CUDZYM numerem sa pomijane cicho i slusznie — naleza do innego
projektu. Jest wspolna dla calej bazy, nie per projekt, wiec te same 20
pozycji zobaczysz w kazdym projekcie; to szum historyczny, nie blad.

Powiazane: [[project_rmpak_produkcja_pw_rw]]

## Status „brak na stanie" na pozycji DOMKNIETEJ (02.10.2026, ten sam dzien)

Po naprawie ZD okno pokazalo 17 pozycji w zakladce "Wydane" — wszystkie
z `Potrzeba == Wydano`, `Pozostalo 0` — ale na CZERWONO ze statusem
`⚠ brak na stanie`. Zakladka "Brak stanu" liczyla 33 pozycje przy 34
w calym projekcie.

Przyczyna: w `_status_wiersza` warunek `if p["stan"] <= 0` stal PRZED
sprawdzeniem, czy pozycja jest domknieta. Po wydaniu wszystkiego magazyn
ma zero, wiec kazda w pelni wydana pozycja dostawala "brak na stanie".
Ten sam blad kolejnosci byl w filtrze "brak" — stad 33 zamiast 17
(17 wydanych + 16 realnych brakow liczylo sie podwojnie).

⚠️ KOLEJNOSC: `domkniete` sprawdzamy PRZED stanem. Pusty magazyn jest
problemem tylko wtedy, gdy COS JESZCZE ZOSTALO do wydania.

Po naprawie: Wydane 17, Brak stanu 17, Wszystkie 34 (17+17=34 — zgadza sie).

## Kolumna „Do wyd." (02.10.2026)

Dodana na prosbe uzytkownika. Pokazuje `min(pozostalo, stan - teraz)` —
ile REALNIE da sie wziac z regalu teraz. Wczesniej magazynier musial
porownywac w glowie "Pozost." ze "Stan" wiersz po wierszu.
`—` dla pozycji domknietych i `poza BOM`.

⚠️ Kolumna jest WYLICZANA, nie ma jej w `self.plan` — `_widoczne_wiersze`
ma dla niej osobna galaz sortowania, inaczej klik w naglowek sortowalby
po napisie. Szerokosci: budzet tabeli ~820 px zostal bez zmian, nowe
56 px oddala "Nazwa" (170 -> 114) jako jedyna rozciagliwa kolumna.

## Tryb `zd-usun` nie znal PZ (02.10.2026)

Testowe przyjecie z `pz-utworz` (PZ 1/10/2026, SKF6002ZZ 5 szt.) nie dalo sie
skasowac: `zd-usun` mial liste rodzajow `ZK, ZD, RW, WZ, PW` — bez PZ. Numer
z nierozpoznanym prefiksem wpada w galaz „szukamy wszedzie", ktora przegladala
wszystkie kolekcje POZA ta, w ktorej PZ naprawde leza.

To DOKLADNIE ta sama historia co z PW 10.09.2026, opisana w naglowku ZdUsun.cs.
Dodane `"PZ" => sfera.PrzyjeciaZewnetrzne()` i PZ do tablicy WSZYSTKIE.

⚠️ Przy nowym rodzaju dokumentu w `pz-utworz`/`Pw.cs`/itp. SPRAWDZ, czy
`zd-usun` go zna — inaczej smieci po testach zostaja w bazie produkcyjnej
i trzeba je klikac recznie w Subiekcie.
