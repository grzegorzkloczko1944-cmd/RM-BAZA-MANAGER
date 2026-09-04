# Nakładka RM_BAZA na Subiekt: ZD do dostawców i wydania monterom

> **Status:** plan z 04.09.2026, nic jeszcze nie zaimplementowane.
> Kontynuacja [`SUBIEKT_PROJEKTY_WYDANIA.md`](SUBIEKT_PROJEKTY_WYDANIA.md)
> (tam: ZK jako lista projektu, komplety Z/ZZ — **działa na produkcji**).
> Tu: co dalej z ZK — **zamówienia do dostawców** i **wydania na produkcję**.

## 1. Po co nakładka, skoro Subiekt to potrafi sam

Subiekt ma i ZD, i RW. Nakładka ma sens tylko wtedy, gdy daje coś, czego
Subiekt nie da — a daje dwie rzeczy:

* **Kontekst projektu.** Subiekt nie zna pojęcia „projekt" (sekcja 1
  poprzedniego dokumentu). `ZapotrzebowanieNaAsortyment()` zwraca zapotrzebowanie
  **ze wszystkich** ZK naraz — magazynier i zaopatrzeniowiec widzą kotłowaninę
  pozycji bez podziału na to, na co komu potrzebne. RM_BAZA wie, że
  `013-100.22X` to Ceramizator 2619, i potrafi to pokazać.
* **Mniej klików niż dziś.** To nie jest kosmetyka — patrz sekcja 4.

Jeśli nakładka nie da obu tych rzeczy, **nie warto jej pisać** — lepiej nauczyć
ludzi Subiekta.

## 2. Punkt 1: ZD do dostawców (robimy najpierw)

**Kto klika:** biuro/zaopatrzenie, nie magazyn → brak ryzyka adopcyjnego,
dlatego to idzie pierwsze.

**Łańcuch API — cały potwierdzony w SDK 61.1.0.9431:**

```
IZamowieniaOdKlientow.ZapotrzebowanieNaAsortyment()
   → ICollection<PozycjaZestawieniaZapotrzebowania>
        .Asortyment       co
        .Ilosc            ile brakuje
        .JednostkaMiary
        .Dostawca         ← Subiekt SAM podpowiada u kogo (z kartoteki)
        .PozycjeZK        ← z których ZK wynika ta potrzeba = z których projektów
   ↓  (filtr RM_BAZA: zostaw pozycje, których PozycjeZK wskazują wybrany projekt)
IZamowieniaDoDostawcow.UtworzNaPodstawieZapotrzebowania(pozycje[])
   → ICollection<IZamowienieDoDostawcy>   (osobne ZD per dostawca — Subiekt grupuje sam)
```

⚠️ **`ZapotrzebowanieNaAsortyment()` nie przyjmuje parametrów** — zwraca
zapotrzebowanie ze WSZYSTKICH niezrealizowanych ZK. Zawężenie do projektu robi
RM_BAZA po `PozycjeZK`. Konsekwencja: przy wielu otwartych ZK to wywołanie
będzie kosztowne — mierzyć, zanim się je wpnie w odświeżanie.

### 2.2 Sprawdzone na żywej bazie (04.09.2026, tryb `zapotrzebowanie`)

Pierwsze realne wywołanie na `Nexo_RM PRODUKCJA`, przy jednym otwartym
ZK 1/09/2026 (projekt 2619):

* **6 pozycji zapotrzebowania** — dokładnie te z ZK, z ilościami (1, 4, 3, 1, 4, 1 szt).
* **Przypisanie do projektu działa:** każda pozycja niesie `Zk[].Uwagi = "2619"`,
  czyli numer projektu wpisany przy zakładaniu ZK wraca tędy z powrotem.
  To potwierdza sens decyzji „Uwagi = sam numer" z poprzedniego dokumentu.
* **`Dostawca` pusty dla wszystkich 6** — kartoteki nie mają przypisanych
  dostawców, więc Subiekt nie ma czego podpowiedzieć. **Wniosek dla okna:**
  kolumnę Dostawca wypełniać domyślnie **z BOM-u RM_BAZA** (kolumna „Dostawca"),
  a podpowiedź Subiekta traktować jako uzupełnienie, nie źródło. To kolejne
  miejsce, gdzie nakładka daje coś, czego sam Subiekt nie ma.
* **Czas: 8,5 s** przy jednym ZK — to głównie koszt startu Sfery (tyle samo co
  tryb `katalog`), nie funkcja liczby pozycji. Przy kilkunastu otwartych ZK
  zmierzyć ponownie, zanim wywołanie trafi w automatyczne odświeżanie.

### 2.3 Dostawcy: automat dopasuje mniej niż połowę

Pomiar na projekcie 2619 (15 różnych nazw z kolumny Dostawca w BOM):
**dopasowanych 7, niedopasowanych 8**. Trzy rozłączne przyczyny:

| przyczyna | przykład z 2619 |
|---|---|
| nazwa z dopiskiem | `Alufrost domówione`, `RMPAK+` |
| dwie firmy w jednym polu | `DAGAR + RMPAK` |
| **to w ogóle nie dostawca, tylko status** | `magazyn`, `anulowane` |

⚠️ Ostatni wiersz to najważniejsze odkrycie: **kolumna Dostawca w BOM-ie
RM_BAZA miesza dwie rzeczy** — kto dostarcza i skąd pozycja pochodzi.
Wszystkie 6 pozycji zapotrzebowania z ZK 2619 ma tam `magazyn`. Automatyczne
mapowanie na kontrahenta Subiekta jest więc z definicji niepełne i **nie da się
tego naprawić lepszym algorytmem** — dane po prostu nie niosą tej informacji.

**Konsekwencja dla okna (zaimplementowana):**
* Dostawca jest **listą rozwijaną z realnych podmiotów Subiekta** (629 firm,
  pobieranych tym samym wywołaniem co zapotrzebowanie — osobne kosztowałoby
  drugie ~8 s), a nie polem tekstowym: ZD i tak powstanie tylko dla
  istniejącego kontrahenta.
* Obok jest kolumna **„wg BOM"** — pokazuje, co RM_BAZA miała w tym polu,
  żeby było wiadomo, czego szukać na liście.
* PPM → **„Ustaw dostawcę dla wierszy…"** — jeden wybór dla wielu pozycji,
  bo typowo cała grupa idzie do tego samego kontrahenta.
* Automatyczne dopasowanie zostaje jako **podpowiedź** (dokładne, po
  uproszczeniu znaków — łapie `MAJA` ↔ `"MA-JA"` — i po pierwszym członie,
  gdy jest jednoznaczny).

**Okno „Zamów braki" (szkic):**

| kolumna | skąd |
|---|---|
| ✓ | wybór, co zamawiać |
| Nr rysunku / symbol | `Asortyment.Symbol` |
| Nazwa | RM_BAZA (BOM), nie Subiekt — źródło prawdy dla danych konstrukcyjnych |
| Brakuje | `Ilosc` |
| Dostawca | `Dostawca` — edytowalny, bo podpowiedź bywa pusta |
| Projekt(y) | z `PozycjeZK` — **to jest ta wartość dodana** |

Po zatwierdzeniu: jedno ZD na dostawcę, log jak przy ZK
(`C:\RMPAK_CLIENT\subiekt_logi\`), zapis mapowań.

### 2.1 Forma: duży arkusz na silniku arkusza głównego (decyzja 04.09.2026)

To **nie** ma być okno dialogowe w stylu `subiekt_projekt.py` (Treeview,
ograniczona lista), tylko **pełnoprawny arkusz roboczy jak główny arkusz
RM_BAZA** — ten sam `tksheet.Sheet`, te same nawyki użytkownika.

Powód: zaopatrzeniowiec ma tu pracować, nie tylko zatwierdzać. Sortowanie po
dostawcy, filtrowanie, zaznaczanie zakresów, kopiowanie do Excela, edycja
ilości w miejscu — to wszystko jest już w arkuszu głównym i ludzie to znają.
Odtwarzanie tego w Treeview byłoby gorsze i droższe.

Wzorzec do skopiowania — `RM_BAZA_v15_MAG_STATS_ORG.py` ok. linii 1593:

* `Sheet(headers=[...], column_width=100, theme="light blue")`
* `set_options(show_selected_cells_border=True, enable_edit_cell_auto_resize=False,
  empty_horizontal=0, empty_vertical=0)`
* `enable_bindings((...))` — `single_select`, `select_all`, `column_width_resize`,
  `arrowkeys`, `right_click_popup_menu`, `rc_select`, `copy`, `paste`, `edit_cell`
* `bind("<<SheetModified>>", ...)` do edycji, `popup_menu_add_command(...)` na PPM
* zapamiętywanie szerokości kolumn (`CH.bind("<ButtonRelease-1>", ...)`) — jeśli
  okno ma być używane codziennie, warto od razu, bo `set_sheet_data()` resetuje
  szerokości przy każdym odświeżeniu

⚠️ **Nie kopiować kodu przez wklejenie** — arkusz główny ma ~30 tys. linii klasy
i mnóstwo zależności od `self` aplikacji. Nowy arkusz ma być osobnym modułem
(`subiekt_zamowienia.py`) z własną, małą klasą okna; z arkusza głównego bierzemy
**wzorzec konfiguracji i bindingów**, nie logikę.

Otwarte: czy to ma być `Toplevel`, czy zakładka w oknie głównym. Na razie
`Toplevel` (jak reszta okien Subiekta), do rewizji gdy będzie działać.

**Otwarte:** ZD nigdy nie były w firmie używane (0 sztuk w historii). To zmiana
procesu, nie tylko techniczna — potwierdzić, że zaopatrzenie faktycznie chce
zamawiać przez Subiekt, a nie mailem/telefonem jak dziś.

**Styk z RM_RFQ — rozstrzygnięte 04.09.2026: RFQ zostaje nietknięte.**
Ta nakładka to **osobna, prosta ścieżka**: braki z ZK → ZD w Subiekcie, bez
ofertowania. Ścieżka przez RM_RFQ (`SUBIEKT_PRZEPLYW_OPIS.md`, kroki 6–11)
istnieje dalej i nic w niej nie zmieniamy — nie dotykamy jej kodu, kontraktu
danych ani przepływu.

Dwie drogi do zamówienia żyją więc równolegle, i to jest świadome:
zakup rutynowy (znany dostawca, znana cena) idzie wprost przez to okno,
a zakup wymagający ofert — przez RM_RFQ. To odpowiednik „kroku 10" z opisu
przepływu (zamów bez RFQ), tylko realizowanego dokumentem ZD w Subiekcie.

## 3. Punkt 2: wydania monterom (potem)

**Kto klika: magazynier, przy wydawaniu.** To rozstrzygnięcie z 04.09.2026 i ono
determinuje cały projekt tego okna.

**Łańcuch API:**

```
IZamowieniaOdKlientow.ZestawieniePozycjiGotowychDoWydania()   → co da się wydać
IDokumentRealizujacyZamowienie.WypelnijNaPodstawieZK(zamowienia[], zrodlo, ParametryGrupowania)
   → RW/WZ wypełnione pozycjami z ZK, z MetodaGrupowaniaPozycji
     (BezKonsolidacji / KonsolidacjaWJednostceMiaryICenie / KonsolidacjaBezWzgleduNaJednostkeMiary)
```

Technicznie to jest łatwiejsze niż ZD. **Trudność jest gdzie indziej.**

## 4. Dlaczego punkt 2 może się nie udać (i co z tym zrobić)

Fakt z rozpoznania: **RW porzucono w 2023, bo magazynier robił wydania na
karteczkach** — dokument w Subiekcie był wolniejszy niż kartka, i nikt tego nie
egzekwował. Przez dwa lata nie bolało, bo nikt nie potrzebował danych „co poszło
na który projekt".

To nie jest anegdota, tylko **wymaganie projektowe**:

> Ścieżka „otwieram → wydaję → gotowe" musi być **realnie szybsza niż napisanie
> tego na kartce**. Inaczej mechanizm poprawny w dokumentacji będzie martwy
> w praktyce — a integracja będzie cicho pokazywać nieaktualne dane, co jest
> **gorsze niż brak integracji**, bo ludzie zaczną jej ufać.

Z tego wynikają twarde decyzje UI, nie do negocjacji dla wygody programisty:

* **Bez logowania i bez wybierania projektu z listy 80 pozycji.** Magazynier ma
  przed sobą jeden ekran z otwartymi ZK.
* **Wyszukiwanie jednym polem** — wpisuje kawałek numeru rysunku, lista się
  zawęża. Docelowo skaner kodów, jeśli detale są oznaczane.
* **Ilość domyślnie = ile zostało do wydania.** Enter zatwierdza. Typowe wydanie
  to ma być: znajdź, Enter.
* **Bez modalnych potwierdzeń „czy na pewno".** Zamiast tego cofnięcie ostatniej
  operacji.
* **Działa, gdy Subiekt nie odpowiada** — kolejka lokalna i dosłanie później.
  Magazynier nie może czekać na sieć z pudłem w ręku.

**Zanim powstanie kod: zmierzyć kartkę.** Ile sekund zajmuje dziś zapisanie
wydania na kartce i ile klików zajmie proponowany ekran. Jeśli ekran nie wygrywa,
projekt punktu 2 jest do przemyślenia od nowa, a nie do wdrożenia.

⚠️ **Uwaga: forma z sekcji 2.1 (duży arkusz) dotyczy ZD, NIE wydań.** Arkusz
z sortowaniem, filtrami i edycją w miejscu jest dobry dla zaopatrzeniowca, który
przy nim siedzi i pracuje. Dla magazyniera z pudłem w ręku byłby **dokładnie tym,
przed czym ostrzega ta sekcja** — za dużo elementów, za dużo klików, wolniej niż
kartka. Ekran wydań ma być maksymalnie ubogi: pole wyszukiwania, lista, Enter.
Ta sama biblioteka, zupełnie inny ekran.

## 5. Kolejność prac

1. ~~Rozstrzygnąć styk z RM_RFQ~~ — zrobione: RFQ zostaje nietknięte (sekcja 2).
2. Tryb `zapotrzebowanie` w moście (odczyt) — zobaczyć realne dane z produkcji,
   zmierzyć czas wywołania przy kilku otwartych ZK.
3. Okno „Zamów braki" na `tksheet` — suchy przebieg, potem zapis (jak przy ZK).
4. Dopiero potem punkt 2, zaczynając od pomiaru z sekcji 4, nie od kodu.
