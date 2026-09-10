# Subiekt — zmiany z 10.09.2026

Dzień w trzech częściach: **naprawa tego, co nie działało** (import BOM-u,
cena zerowana przy zapisie kartoteki), **diagnoza kosztów RW** i — największa
część — **formularze dokumentów wystawianych z Edytora kartotek**.

---

## 1. Edytor kartotek — zapis pojedynczej pozycji

Panel 2 dostał przycisk **„💾 Zapisz tę pozycję do Subiekta"**. Wysyła
WYŁĄCZNIE zaznaczoną kartotekę, nie całe drzewo — przy poprawianiu jednej
nazwy czy ceny wysyłanie wszystkiego jest i wolne, i ryzykowne (dotyka
pozycji, których nikt nie tknął).

Własne okno potwierdzenia pokazuje pola, które pójdą, i pełny skład kompletu.

Dwie blokady:

- **komplet ze składnikami spoza Subiekta** — most ich nie założy przy okazji,
  bo do planu idzie jedna pozycja; okno wymienia brakujące i odsyła do zapisu
  całego drzewa;
- po udanym zapisie `w_subiekcie=True` dostaje **tylko ta pozycja**. Wspólny
  `_zapis_gotowy` oznaczał wcześniej całe `_osadzone()` — przy zapisie
  pojedynczym oznaczyłby jako zapisane rzeczy, które nigdy nie poszły.

---

## 2. Scalanie duplikatów kartotek (panel 5 + tryb mostu `scal`)

Zduplikowane kartoteki (`DN10 K=34` / `1DN10 K=34` / `DN10 K=50,5` — jedna
uszczelka, trzy kartoteki) rozbijają historię cen i stany magazynowe.

**Zasada: symbol jest kluczem.** Scalanie NIE zmienia symboli i NIE zakłada
nowej kartoteki. Kartoteka docelowa zostaje 1:1; źródła są przepinane
i wycofywane.

Co robi `Scal.cs`:

- przepina użycie źródeł w kompletach (relacja odwrotna `SkladnikiWKompletach`
  z SDK — bez przelotu po bazie), przy kolizji **sumuje ilości**;
- różnice danych (nazwa, cena, JM, VAT×2, położenie) tylko **raportuje** —
  cel wygrywa, nic nie jest mieszane automatycznie;
- źródła dostają `SCALONO DO: <cel>` w Opisie i Uwagach; już scalonej nie da
  się scalić drugi raz;
- **blokuje** komplety po obu stronach i różne rodzaje (tylko Towar→Towar,
  Usługa→Usługa).

⚠️ **Sfera NIE MA na Asortymencie flagi „nieaktywna"/„wycofana"** — sprawdzone
w `InsERT.Moria.ModelDanych.xml` (jest `Przeceniony`, `IsInRecycleBin`,
`FlagaWlasna`, nic o wycofaniu). Znacznik w polach tekstowych to maksimum bez
kasowania, a kasowanie odpada przez historię dokumentów.

**Aliasy po scaleniu** (`subiekt_mapowania`): tabela `aliasy_scalen`,
przepięcie mapowań stary→cel ORAZ wpis `mapowania[numer=stary_symbol] → cel`
(`sposob=scalona`). Dzięki temu stary kod z BOM-u rozpozna się bez zmian
w `subiekt_dopasowanie`.

**Odmowa = raport, nie awaria.** Kod wyjścia 0 nawet przy `ok=false` — kod ≠ 0
rzucał `BridgeError` i user nie widział POWODU blokady.

---

## 3. Lista kartotek (sekcja 4): kolumny Opis i Stan

- **Opis** dochodzi z trybu `katalog` w TEJ SAMEJ projekcji LINQ — bez
  drugiego przelotu po bazie.
- **Stan** pobierany razem z katalogiem. Dawna uwaga „katalog świadomie nie
  czyta stanów" jest **nieaktualna**: pochodzi z czasów, gdy każde wywołanie
  startowało Sferę od nowa (~10 s). Dziś przy stałym moście `magazyn` to
  **0,1 s** na 1378 pozycji.
- **Fajka ✓ = pozycja OSADZONA W DRZEWIE**, nie „obecna w `self.pozycje`".
  Podgląd z listy dopisuje kartotekę do modelu (musi, żeby dało się ją
  edytować i zapisać), więc samo kliknięcie odfajkowywało pozycje.

---

## 4. Cena 0 nie nadpisuje ceny w Subiekcie

Pole „Cena ewid." startuje z `0,00`, więc zapis kartoteki **bez dotykania tego
pola zerował cenę** ustawioną w Subiekcie.

Zabezpieczone po obu stronach:

- Python nie wysyła zera (brak klucza = „nie ruszaj", jak przy VAT-ach);
- most nie zeruje przy edycji — `Kartoteki.cs` miał ten warunek przy
  zakładaniu (`p.Cena is > 0`), przy edycji **NIE** (`p.Cena is { }`).

Dwustronnie, bo starsze binarki klientów nadal zero wysyłają.

---

## 5. Import BOM-u — „Z pliku…" mówi PRAWDZIWĄ przyczynę

Funkcja nie działała u użytkownika i nie dało się dowiedzieć dlaczego.
Dwa błędy:

**a) `print` z emoji WEWNĄTRZ bloku `except`.** Na konsoli cp1250 sam print
rzucał `UnicodeEncodeError`, więc wyjątek **uciekał z funkcji** zamiast
zwrócić `[]` — wołacz dostawał crash zamiast łagodnego „nie da się odczytać".
W `.exe` (`console=False`) print i tak nie ma gdzie trafić.

> **Reguła:** print diagnostyczny w `except` ZAWSZE w `try/except: pass` —
> inaczej diagnostyka wywraca obsługę błędu, którą miała opisać.
> To trzecie wystąpienie tej pułapki, w najgroźniejszym wariancie.

**b) Każda awaria wyglądała tak samo.** Brak openpyxl, plik zajęty przez
Excela, uszkodzony ZIP, niedostępny dysk — wszystko dawało „nie ma arkusza
DRZEWKO TEKST". Teraz `ostatni_blad_drzewka()` niesie prawdziwy powód, a gdy
plik otworzył się poprawnie — komunikat **wypisuje arkusze, które zawiera**.

Flaga kasowana na WEJŚCIU funkcji: dwa wczesne `return []` omijały reset
i przenosiły błąd z poprzedniego pliku.

Sprawdzone na `V:\2602 Lanwar\~$…xlsx` (zaślepka Excela) — dawniej crash,
teraz `BadZipFile: File is not a zip file`.

---

## 6. RW bez wyceny — diagnoza i ostrzeżenie

### Objaw

RW wychodziły z zerowym kosztem. `RW 24/09/2026` (projekt **2645**,
wydanie na projekt): **17 z 24 pozycji po 0,00 zł**, wartość 1 911,92 zamiast
realnej.

### Przyczyna — NIE błąd w kodzie

Wzorzec stuprocentowy: koszt wychodzi zero dokładnie tam, gdzie kartoteka
**nie ma żadnego przyjęcia z ceną**.

| | ilość |
|---|---|
| towarów w kartotece | 3035 |
| leży na stanie | 1376 |
| **bez ceny przyjęcia** | **1183 (86 %)** |
| z nich ma cenę ewidencyjną > 0 | **2** |
| sztuk bez wyceny | **18 995** |

Źródło: **migracja magazynu nr 2 z 07.09** — siedem PW (`PW 2–8/09/2026`,
1354 pozycje) przyjęło 24 373 szt. **bez ceny**, bo obsługę ceny w `Pw.cs`
dołożono dopiero 09.09 (`65ec2a9`).

Subiekt zachował się rozsądnie: pozycjom z historią FZ podstawił ostatnią cenę
(zweryfikowane co do grosza: `010-100.03` → 44,00; `011-100.25` → 37,60).
Reszta weszła po 0 zł.

### Czego NIE da się zrobić

Automatycznej naprawy **nie ma z czego zrobić**. Jedyne realne źródło cen
w RM_BAZA to `items.price_pln` — 2694 wpisy, **115 unikalnych numerów**,
kluczowane numerem rysunku, nie symbolem kartoteki. Pokrycie rozkłada się
najgorzej tam, gdzie trzeba: **ZZ 0 na 102**, STANDARD 41 na 371.
KSeF ma 9 rekordów, ZD nie ma pól cenowych.

Decyzja użytkownika: **ceny uzupełniane ręcznie w magazynie.**

### Co zrobiono

Suchy przebieg RW zwraca status **`bez-wyceny`** dla pozycji, które pójdą
z zerem. Koszt liczony z trzech źródeł po kolei:

1. `WartoscZakupu / IloscDostepna` ze stanów — ta sama warstwa, z której
   Subiekt liczy rozchód;
2. ostatni dokument przychodowy z niezerowym kosztem (PZ/PW/FZ/MM);
3. `CenaEwidencyjna` (w tym wdrożeniu praktycznie zawsze 0).

Zweryfikowane: wyliczone kwoty zgadzają się **co do grosza** z tym, co Subiekt
policzył na RW 24 (123,27 / 54,84 / 605,81).

Okno Magazyn robi suchy przebieg przed potwierdzeniem i wypisuje listę pozycji
bez wyceny. Brak mostu = zwykłe potwierdzenie, nie blokada.

> ⚠️ Ostrzeżenie nie dosięgnie RW wystawianych **ręcznie w Subiekcie** —
> a `RW 24` powstał właśnie tak (Uwagi „2645" nie pasują do żadnej ścieżki
> w kodzie). Jeśli tak się pracuje, potrzebny jest raport kontrolny po fakcie.

---

## 7. Formularze dokumentów z Edytora kartotek

Specyfikacja: `SUBIEKT_FORMULARZE_DOKUMENTOW.md`. Drzewo z sekcji 1 to
**roboczy koszyk** — zebrane w nim pozycje idą na jeden dokument zbiorczy.

### `subiekt_dokument_form.py` — wspólny szkielet

Zrobiony **OD RAZU**, nie „później". Powód konkretny, nie estetyczny: **RW ma
już dziś trzy niezależne implementacje** (Kalkulator RMPAK, okno Magazyn,
ręcznie w Subiekcie), które się rozjechały. Czwarta kopia przy każdym typie
dokumentu skończyłaby się tak samo.

- `pozycje_z_drzewa()` — model Edytora → pozycje dokumentu, trzy tryby
  rozwijania kompletów. Ilości mnożą się wzdłuż ścieżki (zespół 2× ze śrubą
  10× = 20 śrub), powtórzone symbole **sumują się** w jeden wiersz, cykl
  w składzie ma strażnika.
- `TabelaPozycji` — checkbox użycia, edycja dwuklikiem w komórce, spacja
  przełącza, kolumny dodatkowe podaje wołający.
- `OknoDokumentu` — nagłówek + tryb rozwijania + tabela + stopka
  Anuluj/Sprawdź/Wystaw. **Nie zna Subiekta** — da się testować bez Sfery.

**Źródłem są ZAZNACZONE węzły drzewa** (dowolne, nie tylko korzenie);
zaznaczony komplet wchodzi z całym poddrzewem, nic nie zaznaczone = całe
drzewo. Węzły **zagnieżdżone w innych zaznaczonych są odsiewane** — inaczej
zaznaczenie kompletu RAZEM ze składnikiem policzyłoby składnik dwa razy.
Odsiewanie po **ID węzłów**, nie po symbolach: ta sama kartoteka bywa
w kilku miejscach drzewa (model grafowy).

### Cena — trzy różne odpowiedzi

| dokument | cena | dlaczego |
|---|---|---|
| **RW** | ❌ nie wpisujemy | wartość to KOSZT MAGAZYNOWY liczony przez Subiekta z warstw przyjęcia; ręczna cena rozjechałaby się z metodą wyceny rozchodu |
| **PW** | ✅ edytowalna | cena **ustala warstwę**, z której policzy się późniejszy koszt RW |
| **ZD** | ✅ edytowalna | na zamówieniu do dostawcy cena jest naturalna — z niej bierze się wartość zamówienia |
| **ZK** | ✅ opcjonalna | ZK z RM_BAZA liczy zapotrzebowanie, nie sprzedaje; `ZK 1/09/2026` ma 32 pozycje bez cen i działa |

RW **pokazuje** koszt (kolumna wypełnia się po „Sprawdź" wartościami z mostu),
choć go nie przyjmuje — wartość dokumentu widać przed wystawieniem.

ZD podpowiada **ostatnią cenę zakupu** (`OstatniaCenaZakupu` z trybu `stan`),
dociąganą w tle; nie nadpisuje ceny już wpisanej.

### `UWAGI` = SAM NUMER PROJEKTU, `TYTUŁ` = opis

Pierwotny format `2741 — Montaż maszyny` **zepsułby odczyt projektu**:
`numer_projektu_z_uwag()` bierze CAŁĄ treść Uwag jako numer, a
`subiekt_dokumenty_gui` mapuje `"projekt": d.get("Uwagi")`.

`Rw.cs` i `Pw.cs` dostały obsługę pola `Tytul` — `UstawUwagi` uogólnione do
`UstawPole`, z tym samym ODCZYTEM KONTROLNYM (setter przy jawnej
implementacji interfejsu potrafi po cichu nic nie zrobić).

### ZK — jeden projekt = jedno ZK

Nowy tryb mostu **`zk-nowe`** (`ZkNowe.cs`), wąski: tylko zamówienie, bez
zakładania kartotek i kompletów (to robi tryb `projekt`).

Kolejność sprawdzeń: **czy projekt ma już ZK** → klient → kartoteki → zapis.
Wyszukiwanie idzie przez `Projekt.ZnajdzZkProjektu` — **tę samą metodę**,
której używa zapis BOM-u; własna kopia rozjechałaby się przy pierwszej
zmianie formatu Uwag.

Dopisywanie do istniejącego ZK zostaje w arkuszu RM_BAZA (tryb `projekt`) —
decyzja użytkownika. Formularz odmawia z komunikatem, dokąd pójść.

Sprawdzone na żywo: `ZP196` (ma `ZK 1/09/2026`) → odmowa z numerem;
projekt bez ZK → przechodzi.

### Klient na ZK — RMPAK po NIP, nie po nazwie

W Subiekcie są **DWA podmioty z „RMPAK"**:

| nazwa | NIP |
|---|---|
| RMPAK Grzegorz Kłoczko *(JDG)* | 5381617408 |
| RMPAK SPÓŁKA Z O.O. | **1231452843** ← ten |

Dopasowanie po fragmencie nazwy brało **pierwszy z brzegu**, czyli o wyborze
decydowała kolejność zwracana przez Sferę — przypadek. Formularz wiąże teraz
po NIP i stawia spółkę pierwszą na liście.

⚠️ **Ta sama dwuznaczność siedzi w zapisie projektu z arkusza**
(`subiekt_projekt.py` wysyła tekst „RMPAK", `ZnajdzPodmiot` dopasowuje przez
`Contains`). Dotychczasowe ZK poszły poprawnie, ale mechanizm jest kruchy —
do naprawy.

### ZD — jedno zamówienie na dostawcę

Formularz grupuje po dostawcy i mówi wprost, ile dokumentów powstanie:

```
POWSTANIE 2 ZD:  FESTO — 1 poz. / 624,00 zł   TECH — 1 poz. / 192,00 zł
                                              ·   RAZEM 816,00 zł netto
```

Przycisk zmienia napis na „UTWÓRZ 2 ZD". Dostawca obowiązkowy, cena
i dostawca ustawiane hurtem.

Pozycje idą trybem **ręcznym** (`reczna: true`) — bez powiązania z ZK.
Zamówienia z zapotrzebowania klienta to osobny, istniejący workflow.

`utworz_zd()` dostała **suchy przebieg** (dotąd zawsze zapisywała). Przy
okazji: ścieżka awaryjna CLI miała `--zapisz` **na sztywno**, więc przy
„Sprawdź" utworzyłaby prawdziwe dokumenty.

### Operacje hurtowe: PODŚWIETLONE, nie wszystkie z ✓

`uzyte()` zwraca pozycje z ptaszkiem (te, które wejdą na dokument),
`podswietlone()` — zaznaczone w tabeli (te, na których się pracuje).
„Ustaw cenę / dostawcę" dotyczy drugiego; gdy nic nie podświetlone, obejmuje
wszystkie z ✓.

---

## 8. Pułapki SDK złapane po drodze

| pułapka | objaw |
|---|---|
| `var kosztJedn = KosztWarstwy(enc)` gdzie funkcja bierze `dynamic enc` | wynik staje się `dynamic`, `.Value` rozstrzyga się w runtime → `'decimal' does not contain a definition for 'Value'`. Jawny `decimal?` przywraca statyczne wiązanie |
| `DokumentZK.NumerDokumentu` | nie istnieje — numer to `NumerWewnetrzny.PelnaSygnatura` |
| `DokumentZK.DataWystawienia` | nie istnieje — data to `DataWydaniaWystawienia` na klasie bazowej `Dokument` (ZK ma z dat tylko `DataSprzedazy`) |
| `DataZamowienia` | termin to `TerminRealizacji` |
| `PozycjaDokumentu.Cena` | to OBIEKT, nie liczba; liczy się `NettoPoRabacie` — samo `NettoPrzedRabatem` zostawia zerową wartość |

---

## 9. Okna

- Formularze i trzy okna potwierdzeń Edytora **nie wołały centrowania wcale** —
  Tk stawiał je w lewym górnym rogu monitora GŁÓWNEGO, czyli nie tam, gdzie
  stoi Edytor. `wysrodkuj()` liczy pozycję względem rodzica i przycina do
  pulpitu **wirtualnego** (współrzędne bywają ujemne).
- Edytor: **1900×860** (siedem kolumn sekcji 4 nie mieściło się w 1760).
- RW/PW: **940×700**, ZD: **1200×700**, ZK: **1040×700**.
- Kolumny „Nazwa" i „Opis" dzielą wolną szerokość z górnymi limitami —
  długi opis nie może wypchnąć kolumn liczbowych poza krawędź.

---

## 10. Pliki

**Nowe:**
`subiekt_dokument_form.py`, `subiekt_rw_gui.py`, `subiekt_pw_gui.py`,
`subiekt_zd_gui.py`, `subiekt_zk_gui.py`,
`subiekt_sfera/NexoRecon/Scal.cs`, `subiekt_sfera/NexoRecon/ZkNowe.cs`,
`SUBIEKT_FORMULARZE_DOKUMENTOW.md`

**Zmienione:**
`subiekt_edytor_gui.py`, `subiekt_mapowania.py`, `subiekt_magazyn_gui.py`,
`subiekt_zamowienia.py`, `import_bom.py`,
`Rw.cs`, `Pw.cs`, `Zd.cs`, `Katalog.cs`, `Kartoteki.cs`, `Projekt.cs`,
`CommandDispatcher.cs`

---

## 11. Co zostało otwarte

1. **Realny zapis nie był testowany** — wszystkie cztery formularze sprawdzone
   WYŁĄCZNIE suchym przebiegiem. Pierwszy zapis każdego typu → **baza DEMO**.
2. **Klient na ZK z arkusza** — `subiekt_projekt.py` dopasowuje „RMPAK" przez
   `Contains`, trafiając w jeden z dwóch podmiotów zależnie od kolejności.
3. **Ceny 1183 kartotek** — do uzupełnienia ręcznie w magazynie.
4. **Raport RW bez wyceny po fakcie** — ostrzeżenie w RM_BAZA nie dosięga
   dokumentów wystawianych ręcznie w Subiekcie.
5. **MM, PZ, WZ** — kolejne formularze z listy specyfikacji.
6. **Most na `Y:`** wciąż w wersji `e21b527` — nowe tryby (`scal`, `zk-nowe`,
   cena na ZD, `bez-wyceny`) działają tylko lokalnie.
