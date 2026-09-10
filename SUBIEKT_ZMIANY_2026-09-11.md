# Subiekt — zmiany z 11.09.2026

Dzień w dwóch częściach: **domknięcie formatu Uwag/Tytułu** z 10.09 (poprawki
tego, co się przy nim posypało) i — większa część — **okno magazyniera
„Wydanie z magazynu"**: lista kompletacyjna, skaner, jedno RW.

---

## 1. Numer projektu z nazwy — naprawa po wczorajszej zmianie

Kalkulator RMPAK trzyma **pełną nazwę** projektu (`3500 dupal`), a okno
projektu sam numer. Wczorajsza zmiana formatu Uwag tego nie uwzględniła
i wyszło to dopiero w praktyce:

- `dokumenty_produkcji("3500 dupal")` porównywało nazwę z numerem z Uwag
  (`3500`) → nie pasowało → **„PW: —" i wyszarzony przycisk „Wystaw RW"**
  mimo istniejącego PW;
- `plan_pw`/`plan_rw` wpisywały całą nazwę do Uwag → `PW 3/MASTER/2026`
  dostało `3500 dupal Projekt` i przestało być odnajdywane.

Jedno miejsce ucina do pierwszego członu — `sam_numer()` w
`subiekt_zamowienia`, używane przez `zloz_uwagi`, `tytul_dokumentu`
i `dokumenty_produkcji`. Nazwa i numer dają teraz identyczny wynik.

## 2. Kasowanie PW nie działało

Tryb `zd-usun` nie znał typu **PW**: lista rodzajów miała `ZK, ZD, RW, WZ`,
więc przy numerze `PW 2/MASTER/2026` kod wpadał w gałąź „szukamy wszędzie"
i przeglądał wszystkie kolekcje **poza tą, w której PW leżą**. Kończyło się
komunikatem „nie znaleziono dokumentu o tym numerze", choć dokument istniał
i był widoczny w Przeglądzie.

RW działało poprawnie od 05.09 — brakowało wyłącznie PW.

## 3. Okna podglądu PW/RW — przyciski poza ekranem

„Wystaw RW" wypadało poza okno z dwóch powodów naraz:

- stopka pakowana **po** tabeli z `expand=True` (tabela zjadała wysokość),
- wszystko w jednym rzędzie — długie etykiety wypychały przyciski za prawą
  krawędź okna szerokiego na 820 px.

Stopka idzie teraz `side="bottom"` i **przed** tabelą, opisy w osobnym
rzędzie nad przyciskami. Zmierzone: przyciski widoczne nawet przy oknie
ściśniętym do 260 px wysokości.

## 4. Edytor kartotek — przyciski przy tym, czego dotyczą

„Sprawdź całość" i „Załóż / Zapisz" działają na drzewie z sekcji 1, a stały
w pasku górnym, gdzie wyglądały na akcje całego okna → zeszły pod drzewo.

W sekcji 5 panel „Po scaleniu" zszedł spod prawej krawędzi **pod tabelę**
(dwie kolumny), a odzyskane ~340 px dostały kolumny Symbol/Nazwa/Opis —
to one identyfikują scalane duplikaty.

## 5. Jasnozielone tło = stan ZK

`_zapisz_ilosci_z_subiekta` pomijało pozycje spoza ZK, więc raz wpisane
`order_qty` zostawało **na zawsze**: pozycja zdjęta z zamówienia dalej
świeciła i pokazywała nieprawdziwą „Ilość (zam.)". Na 3500 dawało to 213
z 213 podświetlonych pozycji przy 184 realnie na ZK.

Teraz pozycje spoza ZK dostają `NULL`. Zerowanie jest bezpieczne, bo
nieudany odczyt kończy funkcję **przed** pętlą zapisu — awaria mostu niczego
nie czyści.

---

## 6. Okno magazyniera „Wydanie z magazynu"

Nowy przycisk **📤 Wydaj** na dolnej belce, obok Drukuj.
Skan kodu → lista kompletacyjna → **jedno RW** ze wszystkimi pozycjami.

### Skąd co się bierze

```text
POTRZEBA          Subiekt: ZK (zakupy) + PW (produkcja własna)
WYDANO WCZEŚNIEJ  RW tego projektu
STAN, LOKACJA     kartoteka Subiekta
```

Całe okno operuje na **faktach z Subiekta**, nie na założeniach
konstrukcyjnych. BOM zostaje źródłem konstrukcyjnym, ale nie licznikiem
magazynowym: mówi, co konstruktor zaprojektował, a nie co realnie kupiono
albo wyprodukowano.

Potrzeba **nie może** iść z samej ZK — tory są rozdzielone
(`RMPAK_PRODUKCJA_USTALENIA` §2) i detale produkcji własnej świadomie na ZK
nie trafiają. Sama ZK pokazałaby połowę pracy magazyniera.

Symbol występujący i na ZK, i na PW to **konflikt do sprawdzenia**, nie suma
— ciche `4 + 6 = 10` byłoby liczbą, której nikt nie zamierzał.

### Czego nie ruszamy

`delivered_qty` ma stare znaczenie „dostarczono od dostawcy" i zasila arkusz
oraz stary skaner. Dopisywanie tam wydań zmieszałoby dwa różne fakty w jednej
kolumnie. Odrzucony też wariant „RW + zapis do bazy": dwa niezależne zapisy
przy jednej operacji to miejsce, w którym powstaje rozjazd.

Skutek uboczny okazał się korzystny: okno **nie zapisuje nic** do bazy
projektu, więc **nie potrzeba locka** i dwóch magazynierów może kompletować
równocześnie. Kolizję wykrywa obowiązkowy świeży odczyt przed zapisem.

### Prawa tabela to PLAN, nie sesja

Pierwsza wersja pokazywała „co zeskanowałem" — magazynier zaczynał od pustego
ekranu i musiał wiedzieć z głowy, czego szukać. Po korekcie jedna tabela łączy
trzy rzeczy: **plan wydania + co już wydano + co przygotowano w tej sesji**.
Druga lista przestała być potrzebna.

Sortowanie po **lokacji** domyślnie i **naturalne**: `R3/P5` przed `R22/P6`.
Tekstowe dawało `R1, R22, R3, R31` i magazynier chodziłby po magazynie
w kółko. Pozycje bez lokacji lądują na końcu, żeby nie rozbijać trasy.

Sesja żyje osobno od planu (`{symbol: ilość}`), więc „Odśwież" w środku
kompletacji nie kasuje pracy. „Usuń z wydania" zeruje kolumnę *Teraz* zamiast
kasować wiersz — plan wynika z ZK/PW i nie jest naszą własnością.

### Polityka wyjątków

| Sytuacja | Reakcja |
|---|---|
| ponad potrzebę | ostrzeżenie, wiersz pomarańczowy, **bez popupu** |
| poza BOM | wydać, wiersz oznaczony |
| ponad stan | **blokada** przy dodawaniu, z wyjściem „Ustaw N" |
| zmiana w tle | ponowna analiza: zmiana POTRZEBY → ostrzeżenie, spadek STANU → blokada |
| brak ceny przyjęcia | pytanie — towar zejdzie, tylko wartość będzie zaniżona |
| brak Subiekta | wystawienie RW zablokowane |

Reguła nadrzędna: **fizyczne wydanie jest ważniejsze od założenia BOM-u**,
ale czego nie ma na stanie, tego wydać się nie da. Bez popupu przy każdym
skanie — magazynier skanuje seriami.

### Nowy tryb mostu `wydanie-stan`

Tryb `dokumenty` ciągnie ZK+ZD+RW+PW+WZ z pozycjami (~0,58 s) — dla skanera
za dużo, bo odpytuje przy otwarciu i przed każdym zapisem. Nowy tryb czyta
trzy kolekcje i zwraca same sumy per symbol: **0,06 s, dziesięciokrotnie
szybciej**.

Zwraca też `konflikty` (ZK/PW) i `rw_bez_projektu` — dokumentów bez numeru
projektu nie wolno doliczyć, ale trzeba pokazać, inaczej „stan spadł, a
licznik nie" zostaje bez wyjaśnienia.

### Dwie osoby na dokumencie

```text
Uwagi:  2627
        WYDAŁ: Grzegorz   POBRAŁ: Andrzej
Tytuł:  RM_BAZA 2627
```

RW zdejmuje towar ze stanu, więc przy sporze „gdzie się podział ten detal"
potrzebne są obie strony. „Wydał" podstawia się na zalogowanego użytkownika,
„Pobiera" zostaje puste — to świadomy wybór. Obie wymagane przed zapisem.

---

## 7. Wnioski i pułapki

**Symbole w Subiekcie ZAWIERAJĄ spacje** — `6212 2RS`, `DIN 933 M8x30`,
`UCFL204 UCFL 204`. Skopiowałem ze starego skanera cięcie kodu na pierwszej
spacji; tam było poprawne, bo tamten szuka po **numerze rysunku**, a numery
spacji nie mają. Kartoteka nie była znajdowana, choć istniała. Teraz pytamy
najpierw o cały wpisany tekst, a dopiero potem o pierwszy człon.

**`tk.Label` liczy `width`/`height` w ZNAKACH, nie pikselach.** Miniatura
rysunku z `width=14` wychodziła wielkości znaczka. Rozmiar w pikselach
wymusza ramka z `pack_propagate(False)`.

**Nie pytać wątku roboczego o zgodę użytkownika.** Pierwsza wersja zapisu RW
kazała wątkowi czekać w pętli na odpowiedź z okienka — to zawiesiłoby GUI,
które ma tę odpowiedź pokazać. Decyzję podejmuje główny wątek i on woła zapis.

**Zanim zdiagnozujesz GUI — sprawdź, czy aplikacja w ogóle działa.**
Straciłem czas na analizę „miniatury się nie wyświetlają", licząc geometrię
z symulacji layoutu, podczas gdy RM_BAZA była po prostu zamknięta. Po
uruchomieniu miniatury działały bez żadnej zmiany w kodzie.

**Migracja dokumentów wykonana** — 3 dokumenty projektu 3500 przepisane na
nowy format, zweryfikowane odczytem. Instrukcja dla bazy firmowej:
`SUBIEKT_MIGRACJA_UWAGI_TYTUL.md`.

**Dane testowe na demo**: 502 detale dostały ceny (12,50–450 zł) i stany
(2–40 szt.) z `PW 4/MASTER/2026`. Do skasowania jednym `zd-usun`, gdy
przestaną być potrzebne.

---

## 8. Zostawione świadomie

**Blokady PW/RW czekają na logistyka.** Miękka blokada drugiego PW jest
celowa (§15 ustaleń: *„twarde »nie da się« skończy się wystawianiem PW
ręcznie w Subiekcie — i utratą kontroli"*). Ale są trzy niespójności do
omówienia: RW ma blokadę twardą a PW miękką, formularz PW z Edytora nie
ostrzega w ogóle, i nie wiadomo, czy PW z Edytora to „PW projektu".

**Punkt 5 planu — cache.** Czysta optymalizacja: okno pokazywałoby ostatnio
znane liczby natychmiast, świeże dociągało w tle.

**Wykrywanie dubletu ZK** łapie tylko numer stojący na początku Uwag. ZK
z Uwagami `Projekt 3500` albo pustymi przejdzie niezauważone. Pełne wykrycie
wymagałoby porównywania pozycji dokumentów.
