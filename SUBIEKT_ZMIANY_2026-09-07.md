# Subiekt — zmiany z 7 września 2026

Dzień po przebudowie mostu (`SUBIEKT_ZMIANY_2026-09-06.md`). Powstało nowe
okno **Asortyment**, naprawiły się dwa błędy, przez które **komplety w ogóle
nie powstawały**, i zniknęła przyczyna tego, że główny arkusz zwalniał
z upływem czasu.

Zakres: 16 commitów, `7cad87d..6e291b6`.

> ⚠️ **W firmie po `git pull` konieczny `dotnet build`.** Zmieniły się cztery
> pliki mostu (`Projekt.cs`, `Katalog.cs`, `CommandDispatcher.cs`,
> `ServerHost.cs`) plus doszedł nowy (`KartotekaEdytuj.cs`). Bez przebudowy
> komplety dalej nie powstaną, a filtr duchów i ostrzeżenie o nieaktualnych
> danych się nie włączą.

---

## 1. Nowe okno: Asortyment

Brakowało odpowiednika listy „Asortyment" z Subiekta. Był tylko formularz na
jedną kartotekę i okno Magazyn — a ono pokazuje **wyłącznie pozycje ze stanem
albo z progiem**, bo służy magazynierowi do domawiania.

Nowe okno (`subiekt_asortyment_gui.py`) pokazuje **wszystkie** kartoteki,
także te bez żadnego ruchu, bo jego tematem jest sama kartoteka: czy nazwa się
zgadza, czy komplet ma właściwy skład.

Kolumny jak w Subiekcie: Rodzaj (TW/KT/US/OP), Symbol, Nazwa, Stan,
Zarezerwowane, Dostępne, Netto, Składników, Użyta w, Opis. Bez Brutto, Waluty
i J.m. — świadomie, na życzenie.

### Stany na żądanie

Tryb `katalog` (nazwa, rodzaj, cena) idzie ~9 s na 3444 kartotekach. Pełne
stany to osobne zapytanie **na kartotekę** i przy całej bazie okno wisiałoby
minutami — dokładnie ten problem wyszedł 05.09 przy oknie Magazyn.

Dlatego lista otwiera się **bez stanów**: w kolumnach stanu stoi `–` na szarym
tle, co znaczy „jeszcze nie pytałem", a nie „zero". Stany dociąga się
przyciskiem **„📊 Pokaż stany (tylko widoczne)"** albo z PPM dla zaznaczonych,
porcjami po 300. Przy więcej niż 300 pozycjach okno pyta, czy na pewno.

### Edycja

Nazwa i cena wprost w tabeli (żółte tło = niezapisane). Dwuklik w komplet
pokazuje skład na dole: ilości edytowalne, składniki można dodawać i usuwać.
Przed zapisem lista zmian do potwierdzenia.

**Symbol jest nietykalny** — to klucz w kodach kreskowych, na dokumentach
i w składach kompletów. Od jego zmiany jest osobny tryb `symbole`, który wie,
co przy tym poprawić.

Zapis idzie nowym trybem mostu `kartoteka-edytuj` (`KartotekaEdytuj.cs`).
Skład ustawiany jak w `Projekt.cs`: **plan jest prawdą**, czyścimy i wpisujemy
od nowa, Lp 1..N — więc dwukrotna edycja nie zdubluje składników.

### Filtr duchów

Lista rozwijana „Stan": *wszystkie / ze stanem / bez stanu (duchy) / stan
niewczytany*. Chodzi o odnalezienie kartotek założonych kiedyś i nigdy
nieużytych.

**Duch to NIE jest sam zerowy stan.** Część kupowana pod zamówienie stoi na
zerze przez większość roku, a jest potrzebna, bo siedzi w składzie kompletu.
Dlatego `Katalog.cs` zwraca teraz `WKompletach` — w ilu kompletach kartoteka
jest składnikiem (relacja odwrotna `SkladnikiWKompletach`, liczona w **tej
samej projekcji**, bez drugiego przelotu po bazie). Duch = zero stanu **i**
zero użyć.

Usługi są poza filtrem: transport czy prowizja nie mają stanu z definicji, więc
zero nie znaczy przy nich nic.

Brak pola `WKompletach` (starsza binarka mostu) znaczy „nie wiem", nie
„w niczym nie siedzi" — filtr się wtedy wyłącza, zamiast pokazać wszystkie
składniki kompletów jako duchy do skasowania.

Pomiar na demo (200 kartotek): 164 używane w kompletach, 25 ze stanem
nieużywanych, **11 duchów**.

### Usuwanie kartotek

Przycisk „🗑 Usuń kartoteki z Subiekta…" jest **w tym oknie**, nie tylko
w Magazynie — duchy widać właśnie tutaj.

Bariery przed zapisem, bo łatwo zaznaczyć wiele wierszy naraz:

* pozycje **ze stanem** i **będące składnikiem kompletu** wypisywane osobno,
  bez możliwości kontynuacji (Subiekt i tak odmówi, ale odmowa przychodzi
  *po* próbie),
* przy **niewczytanym stanie** pytanie z podpowiedzią „najpierw Pokaż stany",
* lista do potwierdzenia i dopiero zapis.

Główną siatką bezpieczeństwa zostaje odmowa Subiekta.

### Lista „gdzie użyta"

Kolumna „Użyta w" mówi ILE, a przy kasowaniu liczy się GDZIE. Dolna tabela dla
pozycji **niebędącej kompletem** pokazuje teraz komplety, w których ta pozycja
siedzi (`WchodziW` z tego samego wywołania trybu `komplet` — bez drugiego
zapytania). Wcześniej stała pusta.

Widok jest tylko do odczytu: ilość w komplecie nadrzędnym poprawia się na
TAMTEJ kartotece.

---

## 2. Komplety nie powstawały — dwa razy ten sam błąd

**Najważniejsza naprawa dnia.** Zakładanie projektu kończyło się 25 błędami:

```
RuntimeBinderException: No overload for method 'Usun' takes 1 arguments
```

ZK powstawało, kartoteki też, ale **żaden komplet nie był utworzony**.

### Przyczyna

`WyczyscSklad` brała `dynamic ob`. Przy `dynamic` binder wybiera przeciążenie
`Skladniki.Usun` **po typie runtime** argumentu i nie trafia w żadne z trzech
(`Asortyment` / `int` / `string`) — mimo że `Usun(string)` istnieje.

Naprawa: parametr ma typ statyczny `IAsortyment`, więc przeciążenie rozstrzyga
kompilator.

### Dlaczego wyszło dwa razy

Ten sam błąd trafił się najpierw w nowym `KartotekaEdytuj.cs` (złapany na
teście, naprawiony od razu), a potem okazało się, że **identyczna wada siedziała
w `Projekt.cs`** — i wyszła dopiero u użytkownika na ekranie.

> **Wniosek na przyszłość:** po naprawieniu błędu tego typu przeszukać repo za
> tym samym wzorcem, a nie poprzestać na pliku, w którym go znaleziono.

### Dubli nie było

Sprawdzone w bazie po nieudanym przebiegu: `komplet-napraw` pokazał **0
duplikatów na 28 kompletach**. Wynika to z ułożenia operacji — `WyczyscSklad`
jest PIERWSZE, więc wyjątek leciał, zanim doszło do `Dodaj`; a nawet gdyby coś
dopisał, `ob.Zapisz()` jest dopiero na końcu i też by się nie wykonał.

Po naprawie, na żywo: pierwszy zapis „utworzony (2 skł.)", drugi z tym samym
planem „zaktualizowany (2 skł., zastąpiono 2)", skład dalej 2 wiersze zamiast 4.

---

## 3. Arkusz zwalniał z czasem — wyciek handlerów

Główny arkusz chodził coraz wolniej im dłużej trwała sesja, i wyraźnie wolniej
niż okna zakładki SUBIEKT przy podobnej liczbie pozycji.

**Przyczyna nie była w danych.** Zmierzone: kolorowanie 400 wierszy to 8 ms,
`set_sheet_data` 160 ms, dane do alarmów idą jednym zapytaniem hurtem.

Winne były `_show_delivered_tooltip` i `_show_bom_tooltip`. Każda robiła
u siebie:

```python
self.sheet.bind("<Motion>", on_motion, add="+")
```

a dymek pokazuje się przy **każdym kliknięciu** w kolumnę ODEBRANE albo BOM.
`add="+"` dokłada handler do istniejących i nikt go nie odpinał — okienko
znikało po 5 s, ale jego handler zostawał do końca sesji.

| Handlerów | 200 ruchów myszy |
|---|---:|
| 0 | 3 ms |
| 10 | 55 ms |
| 50 | 251 ms |
| 100 | 499 ms |
| 200 | 1028 ms |
| 400 | 2030 ms |

Wzrost liniowy. To tłumaczy, czemu **restart pomagał** i czemu okna Subiekta
były szybsze — są świeżo otwarte i nic w nich nie narosło.

Teraz jeden wspólny obserwator, podpinany **dokładnie raz**
(`_zapewnij_obserwatora_dymka`), czytający bieżący dymek ze stanu obiektu.
Sprawdzone: 200 dymków → 1 handler.

Przejrzane pozostałe 12 bindów z `add="+"` — reszta siedzi w `create_ui` albo
na widgetach tworzonych razem z oknem, nie narastają. **RM_MANAGER sprawdzony
osobno: nie ma tego problemu** (jedyny `add="+"` na poziomie okna wręcz odpina
scroll przy zamknięciu, `bind_all` zbilansowane 15:15).

---

## 4. Szybszy scroll

Prędkość była zduszona do 1 wiersza co 100 ms (= 10 wierszy/s) jako obejście
redrawu liczonego wtedy na ~150 ms.

Pomiar dziś (2560×1440, arkusz 600×22): pełny redraw ~48 ms, a przewinięcie
o 3 wiersze kosztuje **tyle samo co o 1** (47 vs 48 ms) — płaci się za sam
redraw, nie za liczbę wierszy.

Stąd 3 wiersze na krok za darmo i próg zbity do 50 ms: **60 wierszy/s zamiast
10**, przy tej samej liczbie przerysowań.

> Gdyby na słabszej maszynie zaczęło szarpać, wraca się podnosząc
> `MIN_STEP_MS`, a **nie** zmniejszając `SCROLL_STEP_ROWS` — te wiersze są
> darmowe.

---

## 5. Karta pozycji — koniec fałszywych alarmów

### „Nadmiar w Subiekcie" na poprawnym komplecie

Karta wypisywała jako „nadmiar" **wszystkie** składniki kompletu, którego skład
był w porządku.

Warunek przerywający porównanie wymagał, żeby OBA zbiory były puste. Gdy
drzewko Inventora było puste, a Subiekt miał 6 składników, porównanie szło
dalej i każdy składnik wypadał jako nadmiar — bo nie znajdował się w pustym
zbiorze.

**Puste drzewko znaczy „nie mam z czym porównać", nie „w Inventorze nic nie
ma".** Puste bywa z powodów niezależnych od danych: okno otwarte bez projektu,
pozycja spoza BOM-u, brak pliku `*_OUT.xlsx`. Powód jest teraz nazwany wprost,
zamiast jednego ogólnika.

### Normalia poza porównaniem

Drzewko pracuje **tylko na numerach rysunku** — kupowana norma (łożysko, pasek,
siłownik, śruba) nigdy się w nim nie znajdzie. Porównanie traktowało taki
składnik jak rozjazd i zgłaszało jako „nadmiar", czyli sugerowało usunięcie
części, która w komplecie jest potrzebna.

Teraz składniki bez numeru rysunku wypadają z porównania. Reguły nie pisano od
nowa — `_ma_numer_rysunku` z `subiekt_wyslij_zd`, które wzięło ją z RM_IMPORT.
**Jedna definicja „numeru rysunku" na cały RM_BAZA.**

Ile pozycji zostało poza porównaniem, widać przy wyniku — inaczej „✓ skład taki
sam" sugerowałoby, że sprawdzono wszystko.

### Kopiowalne wartości

Wartości siedzą teraz w `Text` (stan `disabled`) zamiast w `Label`. Z etykiety
nie da się zaznaczyć tekstu ani go skopiować, a to właśnie wartości się
przekłada: symbol do wyszukania w Subiekcie, numer dokumentu, nazwa dostawcy.

Ctrl+C podpięty jawnie (Text w `disabled` nie zawsze dostaje fokus klawiatury),
PPM daje Kopiuj / Zaznacz wszystko. Wysokość wiersza liczona po ułożeniu
(`after_idle`) i przy każdej zmianie szerokości. Jedno miejsce (`_wiersz_kv`)
obsługuje wszystkie 36 wierszy karty.

---

## 6. Okno „Załóż projekt"

### Legenda kolorów

Kolory nie były nigdzie opisane, więc trzeba było zgadywać, czy pomarańczowy
znaczy „jest" czy „nie ma" — a od tego zależy, co się zaznaczy do założenia.
Opisy mówią, **co zrobić**, nie tylko czym pozycja jest.

### Brak kartoteki ma pierwszeństwo

Dotąd Z/ZZ zawsze dostawało niebieski, więc **złożenie bez kartoteki wyglądało
identycznie jak z kartoteką** — a to właśnie ono wymaga zaznaczenia, żeby
komplet w ogóle powstał. Teraz każda pozycja bez kartoteki jest pomarańczowa;
rodzaj widać w kolumnie Typ i po drzewku.

### Generator symbolu przepuszczał złe znaki

Wypuszczał `+`, nawiasy, cudzysłowy, `&`, `*`, `;`, `%` i **spacje** (te
ostatnie znikały dopiero przy skracaniu, więc krótkie nazwy przepuszczały je do
Subiekta).

Symbol jest **kluczem** — wpisywanym z ręki, wklejanym, skanowanym
i porównywanym po TRIM-ie; takie znaki gubią się przy skanowaniu i rozjeżdżają
dopasowanie.

Nowe sito (`_tylko_bezpieczne`): zostają litery, cyfry i `- _ .`, czyli
dokładnie to, co występuje w numerach rysunku RMPAK. Znaki niosące podział
(`/`, `\`, `+`, `&`) idą na myślnik, żeby nie sklejać członów:

```
Zawor 1/2 + korek  →  Zawor1-2-kore     (nie Zawor12korek)
Pasek 5M+L2525     →  Pasek5M-L2525
Kolo 50% szer      →  Kolo50szer
```

To samo sito w `rozroznij_symbol` — inaczej `+` wracałby tą drogą. Licznik
kolizji rozdziela myślnikiem zamiast `#`, bo `#` sam wypadał przy czyszczeniu.

> **To naprawia nowe symbole.** Kartoteki z `+` czy spacją założone wcześniej
> zostają w Subiekcie — do sprawdzenia w oknie Asortyment.

### Dymki wyłączone

Wyskakiwały przy każdym przesunięciu myszy nad drzewkiem i zasłaniały wiersze.
Wyłączone przełącznikiem `DYMKI`; kod został, przywrócenie to zdjęcie flagi.

---

## 7. Zamówienia ZD — widać, co wysłane

### Wiersz zamówiony ginął na tle

Kolor był nakładany poprawnie, ale `#dfeaf7` ma kontrast **1,22** wobec bieli —
na monitorze nie do odróżnienia.

### Trzy stany zamiast dwóch

* **jasny błękit** `#dfeaf7` — ZD wystawione, **NIEWYSŁANE**; dostawca jeszcze
  nie wie, jest co zrobić,
* **mocniejszy błękit** `#b3d1ec` (kontrast 1,59) — ZD wysłane, zostaje
  czekanie na dostawę,
* szary `#eef1f3` — pokryte ze stanu.

Numer ZD zawsze na granacie z białym tekstem (kontrast 5,47, powyżej progu
WCAG) — drugi sygnał, niezależny od koloru tła: kolor bywa nieczytelny na
słabym monitorze albo przy daltonizmie.

### Nowa kolumna „Wysłano"

To **co innego niż „Data ZD"**, która mówi, kiedy dokument wystawiono
w Subiekcie. ZD potrafi leżeć wystawione i niewysłane, a właśnie to trzeba
widzieć. Pusto = brak ZD, `—` na pomarańczowym = ZD jest, ale nikt go nie
wysłał.

Ślad jest po stronie RM_BAZA (tabela `zd_wyslane`), bo status dokumentu
w Subiekcie mówi o stanie **magazynowym**, nie o wysyłce. Dane zbierały się od
06.09, ale **żadne okno ich nie pokazywało**.

Czytane RAZ na odświeżenie i trzymane w cache — inaczej szłoby jedno zapytanie
na wiersz (przy 200 pozycjach 200 zapytań na każde przerysowanie). Cache
czyszczony przy „Odśwież" i po wysyłce, przez istniejący callback
`po_wyslaniu`.

---

## 8. Ostrzeżenie przed zapisem na nieaktualnych danych

Dwa okna Asortymentu otwarte naraz nie psuły danych (most ma jeden worker
i kolejkę, zapisy są idempotentne), ale mogły się **cicho nadpisać**: okno A
wczytuje listę, okno B coś zapisuje, A zapisuje po swojemu i nadpisuje cudzą
zmianę. Nikt się o tym nie dowiaduje.

Most liczy teraz udane zapisy i wystawia je w `status` jako `writes`.
`handled` nie wystarcza — podbija go każdy odczyt, więc samo odświeżenie listy
wyglądałoby jak cudza zmiana. Liczą się trzy warunki naraz: tryb może
zapisywać, **poproszono o zapis** (nie suchy przebieg) i zapis się udał.

Okno zapamiętuje licznik przy wczytaniu i porównuje przed własnym zapisem oraz
przed usuwaniem kartotek. Wyższa wartość = ktoś zapisał w międzyczasie, więc
pytanie z domyślnym NIE i propozycją Odśwież.

**Ostrzegamy, a nie blokujemy** — licznik zlicza wszystkie zapisy przez most,
także niezwiązane z tymi pozycjami. Własny zapis przesuwa punkt odniesienia.
Gdy licznika nie da się odczytać (starsza binarka), przepuszczamy bez pytania:
brak informacji nie może blokować pracy — dlatego `None`, nie zero.

---

## 9. Drobne, ale warte zapamiętania

**PPM działa na wierszu pod kursorem.** Menu czytało zaznaczenie, a tksheet
(`rc_select`) zaznacza wiersz dopiero PO otwarciu menu — więc pierwsze prawe
kliknięcie w niezaznaczony wiersz nie robiło nic. Dotyczyło obu tabel okna
Asortyment. Lewy klik czyści ten kontekst, żeby przyciski szły po zaznaczeniu.

**Okno projektu wraca na wierzch po dialogu.** Bez `transient()` (celowo —
inaczej Windows odbiera oknu minimalizację) system nie wie, że to okno-dziecko,
i po zamknięciu messageboxa fokus wraca do okna głównego. `_na_wierzch()` po
sześciu dialogach.

Odrzucona alternatywa: siatka na `<Visibility>` łapiąca przykrycie z dowolnej
przyczyny. W teście nie odpaliła się ani razu przy 20 próbach, a niosła ryzyko
walki o warstwę z innymi programami.

**„CENTRALA" w numerach ZK/ZD to nie RM_BAZA.** To człon numeru nadawanego
przez Subiekta — nazwa **miejsca sprzedaży**. Widać to po dokumentach
`ZK 1/OUTLET/2026` w tej samej bazie. Cały kod czyta wyłącznie
`NumerWewnetrzny.PelnaSygnatura`, czyli przepisuje numer bez zmian. Zmiana
możliwa tylko w Subiekcie (Konfiguracja → struktura firmy), i dotknie
wszystkich dokumentów, nie tylko z RM_BAZA.

---

## 10. Pułapki C# — do zapamiętania

**`dynamic` i przeciążenia.** Przy `dynamic` binder wybiera przeciążenie po
typie runtime i potrafi nie trafić w żadne, mimo że pasujące istnieje.
`ISkladnikiKompletu.Usun` ma trzy przeciążenia (`Asortyment` / `int` /
`string`) — z `dynamic` leciał wyjątek. **Encja i obiekt asortymentu muszą mieć
typ statyczny.**

**LINQ na `dynamic`.** Nie wolno podać lambdy do wyrażenia dynamicznego
(CS1977) — trzeba zwykłą pętlą albo typem statycznym.

**Projekcja przed materializacją.** `Rodzaj`, `WKompletach`, `Skladnikow` idą
przez nawigacje **w projekcji**, nie po materializacji encji — sięgnięcie po
nie z gotowej encji to osobne zapytanie na kartotekę.

---

## 11. Co zostało

* **Powtórzyć zakładanie projektu 3500** — komplety nie powstały. Uwaga:
  `ZK 5/CENTRALA/2026` już istnieje, a tryb nie sprawdza, czy ZK dla projektu
  jest — powstanie drugie. Najpierw usunąć stare.
* **Agent Fable** — naprawa duplikatów składników na produkcji, instrukcja
  w `SUBIEKT PODWÓJNE POZYCJE DO NAPRAWY.md`.
* **Okno projektu znikające z ekranu** przy zwykłym klikaniu w drzewku (nie
  samo przykrycie — inny objaw, inna przyczyna). Kliknięcia z okna-dziecka
  docierają do `bind_all` okna głównego (sprawdzone), ale żaden z tamtejszych
  handlerów nie podnosi ani nie chowa okien. Do zbadania, gdy wystąpi ponownie.
* **Kartoteki ze złymi znakami w symbolu** założone przed dzisiejszą poprawką.
* **Zakładka Faktury / odbiór dostaw** — tryb mostu `faktury` istnieje i działa,
  ale **żadne okno go nie woła**. Plan: `SUBIEKT_FV_DO_ZD_PARSOWANIE_PLAN.md`.
  To ostatni odcinek obiegu bez wsparcia: masz zamawianie, kartoteki i wydawanie,
  nie masz przyjmowania. Uwaga: jedyna z tych rzeczy, która **dotyka pieniędzy** —
  robić etapami, zaczynając od podglądu „co przyszło vs co zamówione", bez zapisu.
* **Benchmark w firmie** na 3444 kartotekach.
