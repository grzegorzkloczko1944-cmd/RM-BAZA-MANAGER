# RM_BAZA ↔ Subiekt: dwa źródła prawdy na dokumencie ZK

**Data:** 2026-09-08, uzupełnione 2026-09-09
**Status:** architektura USTALONA, brak otwartych decyzji projektowych.
Raportowanie rozjazdu naprawione i wdrożone (sekcja 7). **Wdrożenie reszty
ODŁOŻONE** (ramka na początku sekcji 11) — na teraz ilości idą sztywno z arkusza
przy zasiewie, tak jak dotąd.
**Testy 0c wykonane (2026-09-09) — wariant 1 ODRZUCONY.** Zapotrzebowanie stoi
na płaskich wierszach składników, a kalkulatora z `ZamowSkladniki` nie da się
zawołać ze Sfery. Struktura ZK zostaje bez zmian (6D.4a).
**Dla czytającego z zewnątrz:** sekcje 1–4 to opis problemu, 6D to rozwiązanie
docelowe po konsultacji, 9 to weryfikacja modelu, a 10–11 to podsumowanie i plan.
Sekcje 5–6 opisują odrzucone warianty — wartościowe jako kontekst, ale nie są
tym, co zamierzamy wdrożyć.
**Kontekst:** integracja systemu RM_BAZA (własna aplikacja, Python/Tkinter + SQLite) z Subiekt Nexo
(system handlowo-księgowy InsERT) przez most napisany w C# na Sferze (`NexoRecon`).

---

## 1. Czym są oba systemy i co je łączy

**RM_BAZA** — wewnętrzna aplikacja do prowadzenia projektów konstrukcyjnych. Trzyma BOM
(Bill of Materials, listę części) każdego projektu w osobnej bazie SQLite
(`project_<id>.sqlite`, tabela `items`). Dane wchodzą tam z eksportów z Autodesk Inventor
(pliki `*_OUT.xlsx` i `.csv` leżące na dysku sieciowym V:\).

**Subiekt Nexo** — system handlowy. To on jest podstawą **księgowości**: z ZK
(Zamówienie od Klienta) wynikają dalsze dokumenty, zapotrzebowanie, rozliczenia.

**Most** — okno „Projekt / Aktualizacja w Subiekcie" (`subiekt_projekt.py`,
klasa `SubiektProjektWindow`) czyta BOM z RM_BAZA i przez proces C# (`NexoRecon.exe`,
tryb `projekt`, plik `subiekt_sfera/NexoRecon/Projekt.cs`) zakłada w Subiekcie:

1. **kartoteki** towarowe dla pozycji, których jeszcze nie ma,
2. **komplety** (kartoteki rodzaju Komplet, ze składem — dla złożeń typu Z/ZZ),
3. **dokument ZK** z tymi pozycjami, oznaczony numerem projektu w polu „Uwagi".

Proces jest dwuetapowy: najpierw zawsze **suchy przebieg** (`run_bridge(plan, zapisz=false)`) —
odpytuje Subiekta, nic nie zapisuje, buduje „plan"; użytkownik ten plan ogląda w oknie
potwierdzenia i dopiero wtedy akceptuje **zapis** (`zapisz=true`).

Ponowne uruchomienie okna na tym samym projekcie jest normalną czynnością — stąd nazwa
„Aktualizacja". Dokument ZK jest odnajdywany po numerze projektu w polu „Uwagi”
(`ZnajdzZkProjektu`), żeby nie powstał drugi dokument dla tego samego projektu.

---

## 2. Co się faktycznie wydarzyło (przebieg incydentu)

### Krok 1 — dołożenie zakresu do BOM-u

Do projektu doszedł nowy zakres prac. Użytkownik użył w RM_BAZA funkcji **„dodaj BOM"**,
wskazując plik `2627-650.11ZZ Transporterek_OUT.xlsx`.

Część pozycji z tego pliku **już była** w BOM-ie projektu (te same numery rysunków —
to normalne, bo ten sam detal występuje w wielu miejscach maszyny). RM_BAZA zachowała się
zgodnie z zamierzeniem: **zsumowała ilości** na istniejących pozycjach zamiast je duplikować.

> Użytkownik potwierdza, że to zachowanie RM_BAZA jest **poprawne i pożądane** —
> to nie jest część problemu.

Stan po tym kroku: BOM w RM_BAZA ma podwyższone (zsumowane) ilości.
Dokument ZK w Subiekcie ma nadal **stare** ilości.

### Krok 2 — uruchomienie „Projekt / Aktualizacja"

Użytkownik otworzył okno i kliknął „Przelicz". Okno **pokazało nowe, zsumowane ilości**
w drzewku pozycji — czyli poprawnie odczytało zmieniony BOM.

### Krok 3 — okno potwierdzenia przed zapisem

Tu pojawił się problem. Okno potwierdzenia („Zapis do Subiekta — potwierdzenie",
nagłówek „BAZA PRODUKCYJNA — sprawdź, zanim zapiszesz") pokazało:

```
25   BEZ ZMIAN

• istniejące ZK 1/CENTRALA/2026 — dopisze 0 poz. (210 już na dokumencie)
  (nowy dokument NIE powstanie)

[tabela — tylko 2 wiersze, oba dotyczące złożeń bibliotecznych bez składu]
```

**Zero informacji o zmianie ilości.** Ani słowa o tym, że BOM ma teraz inne wartości
niż dokument. Komunikat „dopisze 0 poz." i kafelek „25 BEZ ZMIAN" sugerowały,
że operacja jest bezskutkowa.

### Krok 4 — zapis

Zapis został wykonany. **Zsumowane ilości NIE trafiły na ZK** — dokument w Subiekcie
pozostał ze starymi wartościami.

Użytkownik sprawdził dokument i potwierdził: *„jest rozjazd, nie zapisało"*.

### Podsumowanie objawu

| | RM_BAZA (BOM) | ZK w Subiekcie | Co pokazało okno |
|---|---|---|---|
| Ilości pozycji | nowe (zsumowane) | stare | „BEZ ZMIAN", „dopisze 0 poz." |

Cytat użytkownika: *„cała zmiana przebiega po cichu. USER nawet nie wie co zrobił"*.

---

## 3. Przyczyna techniczna

### 3.1. Suchy przebieg porównuje wyłącznie symbole

`subiekt_sfera/NexoRecon/Projekt.cs`, linie 259–279:

```csharp
if (juzJest != null)
{
    var naZk = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
    try
    {
        foreach (var poz in juzJest.Pozycje)
        {
            var s = Bezp(() => poz.AsortymentAktualny?.Symbol)?.Trim();
            if (!string.IsNullOrEmpty(s)) naZk.Add(s!);   // ← tylko SYMBOL, bez ilości
        }
    }
    catch { }
    var nowe = pozycje.Count(p =>
    {
        var e = Znajdz(p.Symbol);
        return e != null && !naZk.Contains((e.Symbol ?? "").Trim());
    });
    var numer = Bezp(() => juzJest.NumerWewnetrzny?.PelnaSygnatura) ?? "";
    kroki.Add(new Krok("zk", numer, "do-dopisania",
        $"dopisze {nowe} poz. ({naZk.Count} już na dokumencie)"));
}
```

`naZk` to `HashSet<string>` **samych symbolów**. Ilość nie wchodzi do porównania w ogóle.
Dlatego pozycja, która jest na dokumencie w ilości 4, a w BOM-ie ma teraz 10,
liczy się jako „już jest" → `nowe = 0` → komunikat „dopisze 0 poz.".

### 3.2. Zapis pomija istniejące pozycje

Ten sam plik, linie 339–361:

```csharp
// Co już jest na dokumencie — nie dublujemy pozycji.
var juzNaZk = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
try
{
    foreach (var poz in ob.Dane.Pozycje)
    {
        var s = Bezp(() => poz.AsortymentAktualny?.Symbol)?.Trim();
        if (!string.IsNullOrEmpty(s)) juzNaZk.Add(s!);
    }
}
catch { }

var dodane = 0;
var pominietoJest = 0;
foreach (var p in pozycje)
{
    var enc = Znajdz(p.Symbol);
    if (enc == null) continue;
    if (juzNaZk.Contains((enc.Symbol ?? "").Trim())) { pominietoJest++; continue; }  // ← POMIJA
    ob.Pozycje.Dodaj(enc.Symbol, p.Ilosc <= 0 ? 1m : p.Ilosc);
    dodane++;
}
```

Pozycja o symbolu już obecnym na dokumencie jest **pomijana w całości** — jej ilość
nie jest ani aktualizowana, ani dodawana. Stąd „nie zapisało".

Następnie, linie 363–368:

```csharp
if (dodane == 0 && istniejace != null)
{
    zkNumer = Bezp(() => ob.Dane.NumerWewnetrzny?.PelnaSygnatura);
    kroki.Add(new Krok("zk", zkNumer ?? "", "bez-zmian",
        $"wszystkie {pominietoJest} pozycji już są na dokumencie"));
}
```

→ status `bez-zmian`, który okno wiernie wyświetla.

### 3.3. Okno potwierdzenia nie ma kategorii dla pozycji towarowych

`subiekt_projekt.py`, linie 2367–2382 (kafelki podsumowania) i 2489–2506 (tabela)
iterują po krokach mostu, ale biorą **wyłącznie** `Rodzaj == "komplet"` i `"kartoteka"`:

```python
for k in (self.dry or {}).get("kroki", []):
    if k.get("Rodzaj") != "komplet":
        continue
    ...
```

Zwykłe pozycje towarowe ze zmienioną ilością **nie mają żadnej reprezentacji** w oknie —
ani kafelka, ani wiersza w tabeli. Nawet gdyby most je wykrył, okno nie miałoby ich gdzie pokazać.

### 3.4. Kontrast: komplety zrobiono poprawnie

Warto zauważyć, że dla **składu kompletów** ten sam plik robi rzecz właściwą
(`Projekt.cs`, linie 161–181): porównuje pary `(Symbol, Ilosc)`, wykrywa różnicę
i zwraca status `do-aktualizacji` wraz z opisem różnic (`OpiszRoznice`):

```csharp
var zPlanu = skl.Select(s => (s.Symbol.Trim().ToUpperInvariant(),
                              s.Ilosc <= 0 ? 1m : s.Ilosc))
                .OrderBy(x => x.Item1).ThenBy(x => x.Item2).ToList();
var stare = wBazie.OrderBy(x => x.Item1).ThenBy(x => x.Item2).ToList();
takiSam = zPlanu.Count == stare.Count
          && zPlanu.Zip(stare, (a, bb) => a.Item1 == bb.Item1 && a.Item2 == bb.Item2).All(x => x);
```

Czyli wzorzec „porównaj symbol **i** ilość, pokaż różnicę" w tym systemie już istnieje
i działa — po prostu nigdy nie zastosowano go do pozycji ZK.

---

## 4. Dlaczego to nie jest zwykły bug

Pierwsza diagnoza brzmiała: „brakuje porównania ilości, trzeba dopisać". Zaproponowano
naprawę w dwóch warstwach (most + okno) i zapytano użytkownika, czy przy istniejącej
pozycji ilość ma być **nadpisywana** wartością z BOM-u, czy **dodawana** do tej na dokumencie.

Reakcja użytkownika przecięła to pytanie:

> *„o kurwa, mam dwa źródła prawdy"*

I to jest właściwa diagnoza. Pytanie „nadpisywać czy dodawać" jest źle postawione, bo obie
odpowiedzi są arbitralne, dopóki nie wiadomo, **kto jest właścicielem danych na ZK**.
Dokładanie reguły arytmetycznej do systemu, który nie ma zdefiniowanego źródła prawdy,
leczy objaw i przy okazji utrwala problem.

Istota problemu:

- RM_BAZA i ZK w Subiekcie to **dwa niezależne stany**, które **oba mogą się zmieniać**.
- Nic ich nie uzgadnia i nic nie definiuje, który z nich wygrywa w razie rozbieżności.
- Operacja nazwana „Aktualizacja" sugeruje, że RM_BAZA ma prawo poprawiać Subiekta —
  ale nikt nigdy nie zdecydował, czy tak faktycznie ma być.

---

## 5. Rozważane modele

### Model A — ZK jest projekcją BOM-u

RM_BAZA to jedyne źródło prawdy; ZK ma zawsze odzwierciedlać aktualny BOM.
„Aktualizuj" = doprowadź ZK do stanu BOM-u (dopisz różnicę, pokaż co i z czego na co).

- ✅ Operacja **idempotentna** — dwa kliknięcia dają ten sam wynik.
- ✅ Jasna, jednoznaczna reguła.
- ❌ Ręczna zmiana ilości dokonana w Subiekcie zostanie **nadpisana**.
- ❌ ZK przestaje być miejscem, gdzie wolno cokolwiek ręcznie poprawiać — a jest to
  dokument księgowy, więc to poważne ograniczenie.

### Model B — ZK jest dokumentem handlowym z własnym życiem

Raz wystawiony ZK żyje w Subiekcie i ludzie go tam zmieniają. RM_BAZA nie ma prawa go
„aktualizować" — może tylko **pokazać rozjazd** i pozwolić świadomie dopisać nową partię,
nigdy nie ruszając tego, co już jest.

- ✅ Szanuje rolę Subiekta jako systemu księgowego.
- ❌ Rozjazd staje się stanem trwałym — trzeba z nim żyć i umieć go czytać.

### Model C — wersja wstępna, później zastąpiona przez 6D

> ⚠ **HISTORYCZNE.** Ta sekcja opisuje wcześniejszy etap myślenia. Punkty niżej
> („RM_BAZA ma wyłącznie prawo odczytu", „Aktualizuj przestaje być operacją
> zapisu") **nie obowiązują** — w rozwiązaniu docelowym okno Projekt / Aktualizacja
> **zapisuje** do Subiekta jako jego frontend (6D.1, 6D.3). Nie kodować z tej sekcji.

> *„SUBIEKT jest ważniejszy bo jest księgowy. RM_BAZA wprowadza dane na starcie
> a potem już trzeba w subiekcie prowadzić zmiany a RM_BAZA już tylko czyta"*

To nie jest wybór jednego z dwóch źródeł, tylko **rozdzielenie ich w czasie**.
Dokument ZK ma **moment przekazania własności**:

- **przed zasiewem** — właścicielem jest RM_BAZA (zakłada kartoteki, komplety, tworzy ZK),
- **po zasiewie** — właścicielem jest Subiekt; RM_BAZA ma wyłącznie prawo **odczytu**.

Konsekwencje dla kodu:

1. **„Aktualizuj" na istniejącym ZK przestaje być operacją zapisu.** Przycisk zapisu
   na dokumencie, który już istnieje, powinien być zablokowany albo mocno ograniczony
   (patrz pytanie otwarte niżej). Okno ma pokazywać **porównanie**: co w BOM-ie,
   co na ZK, gdzie rozjazd.
2. **Rozjazd przestaje być błędem.** Dziś traktowany jak defekt; w tym modelu to
   normalny, oczekiwany stan — ktoś w Subiekcie zmienił ilość, bo tak było trzeba.
   Wiersz „u Ciebie 10, w Subiekcie 14" to **informacja**, nie alarm.
3. Nazwa okna („Projekt / **Aktualizacja** w Subiekcie") staje się myląca.

---

## 6. Historyczne pytanie otwarte przy modelu C: nowy zakres prac

> ⚠ **HISTORYCZNE.** Pytanie zostało rozstrzygnięte — obowiązuje 6a, ale z innym
> uzasadnieniem niż podane niżej (patrz przypis na końcu sekcji). Nie kodować stąd.

**Co zrobić, gdy do projektu dochodzi nowy zakres** — dokładnie sytuacja z incydentu
(„dodaj BOM" z Transporterka)? To nie jest korekta istniejącej pozycji, tylko realnie
nowa robota, która musi trafić do Subiekta.

Dwie drogi zgodne z zasadą „Subiekt jest właścicielem":

### 6a. Nowe pozycje owszem, istniejące nigdy

Symbol, którego na ZK nie ma → dopisujemy. Symbol, który już jest → nie ruszamy,
tylko raportujemy rozjazd.

> **Uwaga:** to jest właściwie **dzisiejsze zachowanie mostu** — tyle że dziś robi to
> *przypadkiem i po cichu*, zamiast świadomie i z komunikatem. Kod robi rzecz słuszną
> z zupełnie złego powodu (`if (juzNaZk.Contains(...)) continue;` powstało jako
> „nie dublujmy pozycji", a nie jako „Subiekt jest właścicielem ilości").
> Naprawy wymagałaby wyłącznie **warstwa informacyjna**.

### 6b. Dosiew idzie na osobny dokument

Doszedł zakres → powstaje **nowe ZK** na tę partię, stary zostaje nietknięty.

- ✅ Czystsze księgowo, łatwiejsze do prześledzenia (widać, co doszło i kiedy).
- ❌ Mnoży dokumenty na jeden projekt — a w kodzie **już istnieje** ostrzeżenie
  `UWAGA-DUPLIKATY` i twarda blokada zapisu przy wykryciu dwóch ZK na projekt
  (`Projekt.cs`, linie 253–257 i 305–313). Ktoś kiedyś uznał wiele dokumentów
  na projekt za sytuację podejrzaną i wymagającą ręcznej interwencji.
  Wybór 6b wymagałby przemyślenia tamtej decyzji.

> Przy rozwiązaniu docelowym (sekcja 6D) obowiązuje **6a** — dosypywanie nowego
> zakresu idzie na istniejące ZK, bez zakładania drugiego dokumentu.
>
> Uzasadnienie z 6a („istniejących nigdy nie ruszamy") **przestaje jednak
> obowiązywać**: w modelu docelowym ilość pozycji już obecnej na ZK da się
> świadomie zmienić przez okno Projekt / Aktualizacja, działające jako frontend
> Subiekta (6D.1, 6D.3). Zasiew nowego zakresu i edycja istniejącej ilości
> to po prostu dwie różne operacje w tym samym oknie.

---

## 6D. ROZWIĄZANIE DOCELOWE — jedno źródło dla „Ilość (zam.)”

Modele A/B/C próbowały uzgadniać dwie liczby o podobnym znaczeniu. Rozwiązanie docelowe
rozdziela je jednoznacznie:

- **„Ilość BOM”** pozostaje wartością konstrukcyjną RM_BAZA / Inventora,
- **„Ilość (zam.)”** jest wartością dokumentową i jej właścicielem jest Subiekt.

To nie są dwie kopie tej samej liczby, tylko **dwie różne informacje**. Rozjazd między nimi
nie jest sam w sobie błędem: BOM mówi, ile konstrukcyjnie wynika z projektu, a ZK mówi,
ile faktycznie jest prowadzone / zamawiane operacyjnie w Subiekcie.

> *„po wrzuceniu pozycji z RM_BAZA idzie to do subiekta. Potem już nie edytujemy
> Ilości (zam.) w arkuszu RM_BAZA — zmiany idą przez okno Projekt / Aktualizacja,
> które jest nakładką na Subiekta i zapisuje bezpośrednio do Subiekta.”*

### 6D.1. Pierwszy zasiew i dalsza praca

Okno **„Projekt / Aktualizacja w Subiekcie”** ma dwa etapy życia:

1. **Pierwszy zasiew projektu**
   - RM_BAZA czyta BOM,
   - zakłada brakujące kartoteki,
   - zakłada komplety KT i ich skład,
   - tworzy ZK,
   - początkowe wartości „Ilość (zam.)” są zasiewane do Subiekta.

2. **Po zasiewie**
   - okno nie synchronizuje automatycznie ilości BOM → ZK,
   - staje się **frontendem / nakładką na Subiekta**,
   - edycja „Ilość (zam.)” zapisuje bezpośrednio do ZK w Subiekcie,
   - RM_BAZA czyta te wartości z Subiekta i pokazuje je w arkuszu.

W efekcie zmiana:

`Ilość BOM = 10`, `Ilość (zam.) = 4`

nie oznacza błędu. Użytkownik widzi obie wartości i sam decyduje w oknie
Projekt / Aktualizacja, czy „Ilość (zam.)” ma zostać zmieniona.

### 6D.2. Dwie kolumny ilości w RM_BAZA

W arkuszu głównym pozostają dwie osobne kolumny:

- **Ilość BOM** — ilość konstrukcyjna; nie zmieniamy jej logiki,
- **Ilość (zam.)** — ilość wynikająca z ZK w Subiekcie.

Nie wolno nadpisywać „Ilość BOM” wartością z Subiekta ani odwrotnie.

Stan początkowy kolumn pozostaje taki jak obecnie. Po pierwszym zasiewie albo po późniejszej
edycji wykonanej przez okno Subiekta wartość „Ilość (zam.)” ma odzwierciedlać stan z Subiekta.
Na późniejszym etapie można rozważyć **podświetlenie komórki** jako informację, że jej źródłem
jest Subiekt, ale nie zmieniamy przez to zachowania arkusza ani znaczenia kolumn.

### 6D.2a. Cykl życia kolumny „Ilość (zam.)" — trzy fazy

Kolumna nie jest ani czysto wejściowa, ani czysto odczytowa — zmienia rolę
w momencie zasiewu:

| Faza | Skąd wartość | Edycja w arkuszu |
|---|---|---|
| **przed zasiewem** | wpisuje użytkownik w arkuszu | ✅ tak — to ona idzie na ZK |
| **zasiew** | wartość z arkusza trafia na ZK, po czym zostaje **nadpisana** tym, co odczytano z Subiekta | — |
| **po zasiewie** | Subiekt (odczyt) | ❌ **zablokowana** |

Zasiew jest więc **momentem przekazania własności**: do tej chwili kolumna jest
wejściem, potem staje się oknem na stan Subiekta. Nadpisanie po zapisie nie jest
formalnością — to potwierdzenie, że na dokumencie faktycznie jest ta wartość
(spójne z read-backiem z 6D.6; jeśli odczyt nie zgadza się z oczekiwaniem,
użytkownik widzi to od razu w arkuszu).

**Blokada jest SKUTKIEM stanu, nie jego nośnikiem.** Kryterium:

> - symbol **ma własną pozycję na ZK** → „Ilość (zam.)" jest ilością **tej pozycji**
>   i jest **edytowalna** przez Projekt / Aktualizacja;
> - symbol **nie ma własnej pozycji na ZK** i występuje **wyłącznie** jako składnik KT
>   → „Ilość (zam.)" = `—`, **nieedytowalna**.

Decyduje więc **istnienie własnego wiersza na ZK**, a nie to, czy pozycja gdzieś
występuje jako składnik. Wcześniejsze sformułowanie („ma pozycję na ZK **albo**
jest składnikiem zasianego KT → nieedytowalna") było **błędne** — patrz 6D.2b.

Nie odwrotnie — sam fakt, że komórka była wczoraj szara, nigdzie się nie zapisuje
i po restarcie RM_BAZA nie byłoby z czego go odtworzyć.

### 6D.2b. Rola ≠ typ kartoteki. Ta sama pozycja może być i luzem, i składnikiem

Dokument mieszał dotąd dwa niezależne pojęcia. Trzeba je rozdzielić:

| Cecha | Wartości |
|---|---|
| **Typ kartoteki** | `KT`, `TW` |
| **Rola w projekcie / na ZK** | samodzielna; składnik KT-A; **samodzielna + składnik KT-A**; składnik KT-A i KT-B |

**To nie są role rozłączne.** RM_BAZA sumuje ten sam numer rysunku do jednej
pozycji BOM-u (`build_plan`, [subiekt_projekt.py:644-676](subiekt_projekt.py#L644-L676) —
jeden wpis z sumaryczną ilością, a `skladniki` to osobna lista), więc realny jest układ:

```
TW-X:  2 szt. luzem
       3 szt. jako składnik KT-A
       4 szt. jako składnik KT-B
```

Na ZK powinno wtedy powstać:

```
TW-X ×2      ← własna pozycja (część luzem)
KT-A ×1
KT-B ×1
```

Ilość `2` jest **własną ilością dokumentową** TW-X i **musi pozostać edytowalna**,
mimo że ten sam symbol występuje dodatkowo wewnątrz dwóch kompletów.
Zapotrzebowanie wynikające z KT jest czymś osobnym (6D.3a).

**Kolumna „Typ / Źródło" pokazuje jedno, ale logika pod spodem musi rozumieć rolę:**

```
KT                              samodzielny
KT • składnik KT-A
TW                              samodzielny
TW • składnik KT-A
TW • samodzielny + składnik KT-A     ← ilość EDYTOWALNA (ma własny wiersz ZK)
TW • składnik KT-A, KT-B
```

Dopiero z roli wynika, czy istnieje własny wiersz ZK — a z tego blokada.

### 6D.2c. KT wewnątrz KT — na ZK trafiają tylko korzenie

BOM ma podzespoły (Z wewnątrz ZZ), więc występuje układ:

```
KT-A
 └─ KT-B
     └─ TW-X
```

Przy wariancie 1 **KT-B nie może dostać własnej pozycji na ZK**, skoro jest
składnikiem KT-A — inaczej zamówienie policzyłoby go dwa razy:

```
ZK:
  KT-A ×1
  KT-B ×1     ← BŁĄD, jeśli B jest już wewnątrz A
```

**Zasada zasiewu:**

> Na ZK trafiają wyłącznie pozycje **samodzielne / korzenie zamawianego drzewa**.
> Składniki nie trafiają jako osobne pozycje — **niezależnie od tego, czy ich
> kartoteka jest typu TW czy KT**.

To dlatego „Składnik KT" w kolumnie „Typ / Źródło" może dotyczyć zarówno TW,
jak i innego KT. Wyjątek pozostaje jeden: pozycja występująca **także luzem**
dostaje własny wiersz na tę część, która jest luzem (6D.2b).

Nie wymaga to osobnej flagi `sent_to_subiekt`: wystarczy powiązanie, które i tak
trzeba przechowywać (6D.7) — identyfikator/numer ZK plus `qty_subiekt_at`.
Obecność tego powiązania jest źródłem prawdy o tym, czy pozycja została zasiana;
wygląd komórki jest tylko jego odbiciem.

### 6D.3. Edycja ilości — przez okno Projekt / Aktualizacja

Po zasiewie ilości dokumentowe edytujemy w oknie **Projekt / Aktualizacja w Subiekcie**.

To okno jest interfejsem RM_BAZA, ale zapis wykonywany jest **bezpośrednio do Subiekta**.
Nie traktujemy tej operacji jako zapisu do BOM-u ani jako synchronizacji BOM → ZK.

Edycja dotyczy:

| Rola pozycji w widoku Projekt / Aktualizacja | Zachowanie |
|---|---|
| **KT samodzielny / korzeń** | jest na ZK, ilość **edytowalna** |
| **TW samodzielny / luzem** | jest na ZK, ilość **edytowalna** |
| **Składnik KT** (TW *lub* KT) bez własnej pozycji ZK | **nie jest osobną pozycją ZK**, ilość nieedytowalna (`—`) |
| **samodzielna + składnik KT** | ma własny wiersz na część samodzielną — **ten wiersz jest edytowalny** |

> Tabela opisuje **widok w RM_BAZA**, nie zawartość dokumentu. Po wdrożeniu
> wariantu 1 składnik KT w ogóle nie ma wiersza na ZK — widnieje w arkuszu,
> bo należy do BOM-u, ale dokument reprezentuje go przez komplet.

**Potrzebna kolumna „Typ / Źródło".** Nie po to, żeby RM_BAZA liczyła skład KT,
lecz czysto jako informacja dla użytkownika — inaczej widzi, że jednej pozycji
nie da się edytować, i nie ma z czego wyczytać dlaczego ani co zrobić zamiast tego:

| Wyświetlane | Znaczenie |
|---|---|
| `KT` | możesz edytować ilość |
| `TW` | możesz edytować ilość |
| `Składnik KT 2627-650.11ZZ` | nie edytujesz tutaj; zmień ilość KT |

Nagłówek **„Typ / Źródło"**, bo kolumna łączy dwie informacje: rodzaj kartoteki
(KT/TW) oraz pochodzenie (skład którego kompletu). Sam „Typ" by to zacierał.

Zapis „Składnik KT …" czyta się jako **rzeczownik** — mówi, czym pozycja jest.
Wcześniejszy wariant ze strzałką (`TW → KT …`) sugerowałby transformację
(„zmienia się w"), a nie przynależność.

> **Symbol pisany w całości**, nie skracany do `650.11ZZ`. W jednym projekcie
> prefiks jest wspólny, więc skrót by działał — ale dosypywanie zakresu może
> wprowadzić na ZK pozycje z różnych projektów i skrót przestaje być jednoznaczny.
> Skracać dopiero przy braku miejsca w kolumnie.
>
> Sortowanie po tej kolumnie powinno grupować składniki tego samego kompletu —
> przy 200 pozycjach to jedyny sposób, żeby zobaczyć je obok siebie. Wychodzi
> samo, o ile tekst zaczyna się od „Składnik KT" i symbol stoi w stałym miejscu.

> Wzorzec istnieje w systemie: Edytor kartotek dostał osobną kolumnę „Typ" (TW/KT/US),
> bo `Treeview` nie koloruje fragmentu tekstu w komórce, więc skrót dopisany do symbolu
> był nie do wyróżnienia (`SUBIEKT_ZMIANY_2026-09-08.md`, sekcja 1.10).

### 6D.3a. „Ilość (zam.)" dla składnika KT — NIE zero, tylko „—"

> ⚠ **NIEAKTUALNE po odrzuceniu wariantu 1 (6D.4a).** Składniki KT **mają**
> własne wiersze na ZK, więc ich „Ilość (zam.)" jest normalną ilością
> dokumentową — zablokowaną po zasiewie jak każda inna, ale nie `—`.
> Sekcja zostaje jako opis reguły, która obowiązywałaby przy wariancie 1.

Po wdrożeniu wariantu 1 składnik kompletu **celowo nie ma wiersza na ZK**.
Reguła „pozycja nieobecna na ZK → `0`" (6D.8) **nie może** się do niego stosować:

```
KT Transporter ×3
 └─ UCFL201 ×2        →  zapotrzebowanie 6 szt.
```

Pokazanie `Ilość (zam.) = 0` dla UCFL201 sugerowałoby, że **nic nie zamówiono**,
podczas gdy jego potrzeba wynika z KT ×3. Byłby to dokładnie ten rodzaj
kłamliwego raportu, przed którym broni zasada z sekcji 8.

**Dlatego:**

| Sytuacja | „Ilość (zam.)” | Typ / Źródło |
|---|---|---|
| pozycja jest na ZK | ilość z dokumentu | `KT` albo `TW` |
| pozycja **usunięta** z ZK | `0` — nic nie zamówione | `TW` |
| **składnik KT** (nigdy nie był osobną pozycją) | `—` *(albo `z KT`)* | `Składnik KT 2627-650.11ZZ` |

Rozróżnienie `0` vs `—` jest istotne: **zero to stwierdzenie** („sprawdzone,
nic nie zamówione"), **myślnik to brak stwierdzenia** („ta pozycja nie ma własnej
ilości na dokumencie — patrz komplet"). Kolumna „Typ / Źródło" mówi, gdzie patrzeć.

> **Rozwinięte zapotrzebowanie to OSOBNA wartość.** Gdyby kiedyś pokazywać
> ile faktycznie wychodzi części (`UCFL201 → 6`), musi to być własna kolumna —
> np. **„Zapotrzebowanie"** — a nie „Ilość (zam.)". Sześć sztuk **nie jest
> ilością pozycji na ZK**; to wynik kalkulatora Subiekta rozwijającego komplet.
> Wsadzenie tego w kolumnę „Ilość (zam.)" zatarłoby różnicę między tym,
> co stoi na dokumencie, a tym, co z niego wynika.

### 6D.4. KT i jego składniki TW

**RM_BAZA nie edytuje ani nie przelicza składników KT na ZK.**

Na dokumencie ZK komplet występuje jako pozycja KT. Zmiana jego ilości zmienia
wyłącznie ilość tej pozycji KT.

Składniki nie są powiązanymi pozycjami dokumentu ZK i nie są automatycznie
przeliczane przy zmianie ilości kompletu.

Rozwinięcie kompletu na składniki następuje w późniejszym procesie dokumentowym
Subiekta, m.in. przy przetwarzaniu ZK → ZD zgodnie z parametrem
`ZamienKompletyNaSkladniki`.

Dlatego RM_BAZA edytuje na ZK tylko ilość **KT** lub **samodzielnego TW**.
Składniki KT nie mają niezależnej ilości dokumentowej wynikającej z KT na ZK.

**Rozróżnienie stanu obecnego i docelowego — precyzyjnie:**

> **Stan obecny:** składniki KT są przez most dodawane na ZK jako **niezależne
> pozycje dokumentu** i uczestniczą w zapotrzebowaniu niezależnie od KT.
> Subiekt **nie zna ich związku z kompletem**.
>
> **Stan docelowy (wariant 1 z 6D.4a):** na ZK pozostaje KT; jego składniki
> nie są dodawane jako niezależne pozycje wynikające z tego KT. Zapotrzebowanie
> na składniki jest wyznaczane przez **kalkulator Subiekta** z obsługą kompletów
> `ZamowSkladniki`.

ZK ma dziś **hybrydową reprezentację BOM-u**: KT jest pozycją dokumentu, a jego
dzieci TW most wrzuca jako osobne, pełnoprawne pozycje. To wyjaśnia, dlaczego
zmiana ilości KT nie rusza TW — i **prawdopodobnie** dlaczego obecne
zapotrzebowanie na części działa: może opierać się właśnie na tych „płaskich" TW.
**Do potwierdzenia testem 0c** (6D.4a).

> Koryguje to wcześniejsze określenie „most wrzuca drzewko". Most **zna** drzewko
> i na jego podstawie przygotowuje dane, ale semantycznie na ZK powstają
> **niezależne pozycje**, a nie drzewo KT→TW rozumiane przez Subiekta.

#### Poniżej: uzasadnienie i dowody z dokumentacji Sfery

RM_BAZA **nie edytuje składu KT** po stronie Subiekta i nie duplikuje logiki kompletów.
Zleca zmianę ilości pozycji KT, a po operacji odczytuje wynik z Subiekta i pokazuje
go użytkownikowi. Skład kompletu jest prowadzony wyłącznie w kartotece Subiekta.

> ### ⛔ ZWERYFIKOWANE: SUBIEKT **NIE** PRZELICZA SKŁADNIKÓW NA ZK
>
> Sprawdzenie dokumentacji Sfery (`C:\iLogic\Subiekt_nexo_PRO_dokumentacja\CHM\sfera\`)
> **obala założenie tej sekcji**. Na dokumencie ZK komplet jest **jedną pozycją**,
> a jego składniki nie istnieją tam jako osobne wiersze.
>
> **Dowody:**
>
> 1. **Relacja komplet ↔ składniki istnieje tylko na dokumentach PRODUKCYJNYCH.**
>    Klasa `PozycjaKomplet : PozycjaDokumentu` (`html/57F084BB.htm`) ma właściwości
>    `DokumentProdukcyjny` („Dokument produkcyjny, na którym jest ten komplet")
>    oraz `PozycjeSkladnik`. Symetrycznie `PozycjaSkladnik.PozycjaKomplet`.
>    Powiązanie działa więc na **ZPM/ZPR** (zlecenie produkcyjne montowania /
>    rozkompletowania), nie na ZK.
>
> 2. **`PozycjaDokumentu` nie ma żadnej relacji do składników.** Pełna lista
>    właściwości zawiera `PozycjaZrodlowa`, `PozycjaPowiazana`, `PozycjeRealizujace`
>    i inne — ale nic, co wiązałoby pozycję z jej wierszami składowymi.
>
> 3. **Mechanizm przeliczania ISTNIEJE, ale nie na zamówieniach.** Właściwość
>    `NiePrzeliczajSkladnikowPoZmianieIlosciKompletu` („Parametr umożliwiający
>    wyłączenie przeliczania ilości składników po zmianie ilości kompletu")
>    występuje wyłącznie na `IZlecenieProdukcyjneMontowania` (`html/4C9299A5.htm`)
>    i `IZlecenieProdukcyjneRozkompletowania` (`html/FC9CEF1F.htm`).
>    Brak odpowiednika dla ZK — czyli tam nie ma czego przeliczać.
>
> 4. **Rozwinięcie kompletu to osobny, jawny krok przy przetwarzaniu.**
>    `ParametrDokumentow.ZamienKompletyNaSkladniki` (`html/8A3AABB4.htm`):
>    *„Określa w jaki sposób mają być traktowane komplety przy przetwarzaniu ZK na ZD"*,
>    wartości `NieZamieniaj` / `ZamienWszystkieNaSkladniki`. Na samym ZK komplet
>    stoi jako komplet; zamiana na składniki następuje dopiero przy generowaniu ZD.
>
> 5. Spójne z `SkladnikiKompletuJakoDodatkowyOpis.cs`, gdzie skład czytany jest
>    z **kartoteki** (`AsortymentAktualny.SkladnikiKompletu`) i doliczany ręcznie —
>    właśnie dlatego, że na dokumencie go nie ma.
>
> **Skąd zatem składniki na ZK?** Wstawił je tam **sam most**: `Projekt.cs` wysyła
> wszystkie pozycje BOM-u płasko, nie sprawdzając, czy któraś jest składnikiem
> kompletu. Są to więc **pozycje całkowicie niezależne** — Subiekt nie wie, że mają
> cokolwiek wspólnego z kompletem obok, i nie ruszy ich przy zmianie jego ilości.
>
> **Konsekwencja: punkty 8–9 sekcji 10 są nieaktualne.** Nie da się „zlecić zmiany
> ilości KT i pozwolić Subiektowi policzyć resztę", bo Subiekt tego nie robi
> na zamówieniu. Rozstrzygnięcia wymaga pytanie postawione w 6D.4a.

### 6D.4a. Składniki KT na ZK — ⛔ WARIANT 1 ODRZUCONY (2026-09-09)

> ## Decyzja końcowa: ZOSTAJE JAK JEST — wariant 2
>
> Na ZK nadal trafiają **komplet ORAZ jego składniki** jako osobne, płaskie
> pozycje. Nie zmieniamy zasiewu.
>
> **Powód — twardy, potwierdzony testem:** zapotrzebowanie na części stoi
> dziś **wyłącznie na tych płaskich wierszach** (test 0c niżej: metoda
> `ZapotrzebowanieNaAsortyment()` zwraca komplety, a nie ich składniki),
> a jedynej alternatywy — `IKalkulatorZapotrzebowania` z `ZamowSkladniki` —
> **nie da się zawołać** ze Sfery (`IInjectionScope ... cannot be constructed`).
>
> Usunięcie składników z ZK wyzerowałoby więc zapotrzebowanie na części,
> nie dając nic w zamian. Wybór między „czystszą strukturą dokumentu"
> a „działającym zapotrzebowaniem" jest oczywisty.
>
> **Konsekwencja:** ilości składników na ZK **nie są edytowane** — ani
> w arkuszu, ani przez okno. Kto musi je zmienić, robi to ręcznie w Subiekcie.
> Etap 5 planu (edycja ilości KT z przeliczaniem składników) **odpada**.
>
> Wracać do tego tematu tylko wtedy, gdy znajdzie się droga do kalkulatora
> albo ktoś zdecyduje policzyć zapotrzebowanie samodzielnie z
> `SkladnikiKompletu` (rekurencja po zagnieżdżeniach + jednostki miary).

Poniżej pozostaje analiza, która do tej decyzji doprowadziła.

### 6D.4a-hist. Rozważane warianty (historyczne)

Skoro Subiekt nie wiąże składników z kompletem na zamówieniu (6D.4), trzeba
rozstrzygnąć, **czy składniki KT w ogóle powinny trafiać na ZK**. Dziś trafiają,
bo most wysyła BOM płasko — ale nikt tego nie zaprojektował, to skutek uboczny.

**Wariant 1 — na ZK idzie sam komplet, bez składników.**
Zamówienie mówi „3 × Transporterek", a rozwinięcie na części robi Subiekt przy
przetwarzaniu ZK → ZD (`ZamienKompletyNaSkladniki`) albo zlecenie produkcyjne.

- ✅ Zgodne z tym, jak Subiekt jest zaprojektowany — komplet reprezentuje swój skład.
- ✅ Znika cały problem: nie ma osobnych ilości do uzgadniania, zmiana ilości KT
  wystarcza. Rozwinięcie przy generowaniu **ZD** wykonuje Subiekt
  (`ZamienKompletyNaSkladniki`), natomiast **zapotrzebowanie** na części ma być
  liczone przez kalkulator z `ObslugaKompletow = ZamowSkladniki` — to dwie
  różne ścieżki, patrz niżej.
- ✅ Dokument staje się czytelny (3 pozycje zamiast 210).
- ❌ **Zmiana zachowania mostu** — dziś składniki tam są; trzeba sprawdzić,
  czy nic dalej na nich nie polega (ZD, zapotrzebowanie, magazyn).
- ❌ Wymaga, żeby skład kompletu w Subiekcie był **kompletny i poprawny** —
  dziś złożenia biblioteczne bez składu (`bib_bez_skladu`) powstają jako puste
  kartoteki, więc rozwinięcie nic by nie dało.

**Wariant 2 — składniki zostają jako pozycje niezależne.**
Tak jak dziś. Wtedy ich ilości są osobnymi wartościami, których nikt automatycznie
nie przelicza — ani Subiekt (bo nie wie o powiązaniu), ani RM_BAZA (bo nie duplikuje
logiki kompletów).

- ✅ Nic nie trzeba zmieniać w moście.
- ❌ Zmiana ilości KT **nie pociąga** ilości składników — użytkownik musiałby
  poprawić każdą osobno, co jest dokładnie tym, przed czym broni cały model.
- ❌ Na dokumencie części są policzone **dwa razy**: raz w komplecie, raz osobno.
  To może zawyżać zapotrzebowanie — **wymaga sprawdzenia, czy tak się dzieje**.

**DECYZJA: wariant 1** — na ZK idzie sam komplet, bez osobnych pozycji składników.

#### ⚠ Warunek wykonalności: zapotrzebowanie musi umieć rozwinąć komplety

Wariant 1 **nie jest samą zmianą w zasiewie**. Dotyka trybu `zapotrzebowanie`
(`Zapotrzebowanie.cs`), który dziś opiera się na `ZapotrzebowanieNaAsortyment()`.

Sprawdzenie dokumentacji Sfery 61.1.0.9431:

- **`ZapotrzebowanieNaAsortyment()` jest bezparametrowa i nieudokumentowana pod
  kątem kompletów.** Opis (`CHM/sfera/html/79A9AF05.htm`) mówi tylko: *„Tworzy
  zestawienie asortymentów, które zostały zamówione przez klienta, a nie zostały
  jeszcze zrealizowane…"*. Zwracany `IZapotrzebowanieNaAsortyment`
  (`A032D463.htm`) ma jedynie `AsortymentID` i `Zapotrzebowanie` — żadnego
  pojęcia rozbicia na składniki. Skoro metoda nie przyjmuje parametrów,
  **nie ma jak przekazać jej decyzji o rozwijaniu kompletów**, co wskazuje,
  że zwraca zapotrzebowanie na samą kartotekę kompletu.
- **Istnieje właściwe API do rozwijania.**
  `IKalkulatorZapotrzebowania.ListaZapotrzebowaniaAsortymentowWgMetodyWyliczania`
  (`74B81549.htm`) przyjmuje `MetodaWyliczaniaKZD`, w której
  `ObslugaKompletow` typu `ObslugaKompletowDlaKZD` (`18F1BD7.htm`) ma wartości:
  `Pomin` („Komplety zostaną pominięte"), `WstawKomplety` („Zostaną zamówione
  komplety"), **`ZamowSkladniki`** („Zamiast kompletów zostaną zamówione ich
  składniki").
- Pomocne przy realizacji: `RealizacjePozycjiDokumentu.PodajSkladnikiNiezrealizowaneZIloscia`
  (`2C1D81DF.htm`) — zwraca słownik składnik → ilość do realizacji dla pozycji
  kompletu z ZK.
- `ParametrDokumentow.ZamienKompletyNaSkladniki` dotyczy **wyłącznie generowania ZD**
  (`8A3AABB4.htm`, `3F828328.htm`), nie zapotrzebowania — to dwie różne ścieżki.

**Konsekwencja:** po usunięciu składników z ZK zapotrzebowanie na części
najpewniej przestanie się pojawiać, dopóki tryb `zapotrzebowanie` nie przejdzie
na `ListaZapotrzebowaniaAsortymentowWgMetodyWyliczania` z `ObslugaKompletow =
ZamowSkladniki`. **To musi wejść razem z wariantem 1, nie po nim.**

#### ⛔ NIE RUSZAĆ ZASIEWU PRZED TESTAMI

Samo usunięcie TW spod KT z zasiewu naprawiłoby strukturę ZK, ale mogłoby
**rozwalić działające zapotrzebowanie**. Wariant 1 musi wejść jako **jedna zmiana
razem z kalkulatorem zapotrzebowania**:

```
DZISIAJ                          DOCELOWO

ZK:                              ZK:
  KT-A  ×2                         KT-A  ×2
  TW-A  ×6   ← płaskie wiersze
  TW-B  ×10    z mostu           zapotrzebowanie:
                                   kalkulator Subiekta
zapotrzebowanie:                   KT-A ×2
  bierze fizyczne wiersze TW          ↓ ZamowSkladniki
                                   TW-A ×6
                                   TW-B ×10
```

Subiekt nadal jest źródłem zapotrzebowania na składniki — ale nie dlatego,
że składniki są sztucznie dopisane jako wiersze ZK, tylko dlatego, że jego
kalkulator **świadomie rozwija KT**.

#### ✅ WYNIKI TESTÓW 0c (2026-09-09, baza produkcyjna, czysty odczyt)

Tryb `zapotrzebowanie-test` (`subiekt_sfera/NexoRecon/ZapotrzebowanieTest.cs`),
uruchomiony na `Nexo_RMPRODUKCJA`:

| Sprawdzane | Wynik |
|---|---|
| `ZapotrzebowanieNaAsortyment()` — pozycji | **209** |
| …w tym **KOMPLETÓW** w wyniku | **26** |
| Kompletów w katalogu Subiekta | 28 |
| …z czego **zagnieżdżonych** (KT wewnątrz KT) | **6** |

**Test 1 — ROZSTRZYGNIĘTY: obecna metoda NIE rozwija kompletów.**
W wyniku siedzą same komplety (`2627-000.00ZZ`, `2627-100.00ZZ`,
`2627-200.08ZZ`…). Gdyby je rozwijała, w ich miejsce weszłyby składniki.

> **Potwierdza to ostrzeżenie z tej sekcji:** zapotrzebowanie na części bierze
> się dziś **wyłącznie z płaskich wierszy TW**, które most dopisuje na ZK obok
> kompletu. Usunięcie ich z zasiewu (wariant 1) **wyzerowałoby zapotrzebowanie
> na części**, dopóki tryb `zapotrzebowanie` nie przejdzie na kalkulator.

**Test 2 — zagnieżdżenia są realne, nie teoretyczne.** 6 z 28 kompletów zawiera
inny komplet (m.in. `2627-000.00ZZ`, `2627-100.00ZZ`, `2627-650.11ZZ`), więc
pytanie o głębokość rozwijania ma praktyczne znaczenie.

**⛔ NIEROZSTRZYGNIĘTE: czy kalkulator w ogóle zadziała.**
`IKalkulatorZapotrzebowania` nie daje się pobrać przez `sfera.PodajObiektTypu<T>()`:

```
InvalidOperationException: The current type, InsERT.Mox.Runtime.IInjectionScope,
is an interface and cannot be constructed. Are you missing a type mapping?
```

Ten interfejs wymaga innego sposobu utworzenia niż zwykłe usługi Sfery
(prawdopodobnie własnego scope'u DI albo fabryki). **Dopóki się nie uda go
zawołać, wariant 1 pozostaje niewykonalny** — bo nie ma czym zastąpić
zapotrzebowania liczonego z płaskich wierszy.

Do sprawdzenia dalej: czy kalkulator jest osiągalny inną drogą (fabryka,
`IZamowieniaDoDostawcow`, kreator ZD), albo czy zapotrzebowanie na składniki
trzeba policzyć samodzielnie z `AsortymentAktualny.SkladnikiKompletu`
(z rekurencją po zagnieżdżeniach i uwagą na jednostki miary).

#### Test 1 — czy `ZapotrzebowanieNaAsortyment()` rozwija komplety

Na bazie testowej, bez ręcznego dodawania składników na ZK:

```
ZK TEST
  KT-TEST ×2

Skład kartoteki KT-TEST:
  TW-A ×3
  TW-B ×5
```

Porównać wynik obecnej metody `ZapotrzebowanieNaAsortyment()` z wynikiem
`ListaZapotrzebowaniaAsortymentowWgMetodyWyliczania` przy
`ObslugaKompletow = ZamowSkladniki`.

Oczekiwany wynik drugiej metody: **TW-A = 6, TW-B = 10**.

> Jeżeli obecna metoda pokaże **tylko `KT-TEST = 2`**, mamy pełne potwierdzenie,
> że dzisiejsze zapotrzebowanie na TW bierze się wyłącznie z płaskich wierszy
> generowanych przez most.

#### Test 2 — zagnieżdżone komplety

BOM ma podzespoły (Z wewnątrz ZZ), więc występuje układ:

```
KT-A
 └─ KT-B
     └─ TW-X
```

Sprawdzić, czy `ZamowSkladniki` rozwija to **do końca**, do `TW-X`, czy tylko
jeden poziom. Ma to znaczenie dla całej architektury zapotrzebowania — przy
rozwijaniu jednopoziomowym część zapotrzebowania zniknęłaby bez śladu.

#### Trzeci warunek

Komplety muszą mieć w Subiekcie **poprawny skład**. Dziś złożenia biblioteczne
bez składu (`bib_bez_skladu`) powstają jako puste kartoteki — dla nich
rozwinięcie nie da nic, więc zapotrzebowanie na ich części przepadnie.

### 6D.4b. Klucz dopasowania pozycji wysłanej — zablokowany w arkuszu

Niezależnie od blokady „Ilość (zam.)" opisanej w 6D.2a trzeba **dodatkowo
zablokować pole będące KLUCZEM** dopasowania RM_BAZA ↔ Subiekt.

**Dlaczego:** symbol kartoteki w Subiekcie bierze się z tego klucza
(`Projekt.cs`, `Znajdz(p.Symbol)`). Zmiana klucza pozycji, która już jest
w Subiekcie, powoduje, że przy kolejnym uruchomieniu okna Projekt / Aktualizacja
RM_BAZA **nie rozpozna istniejącej kartoteki** i potraktuje pozycję jako nową —
założy duplikat obok tej, która już tam jest.

**Kluczem jest co innego dla dwóch rodzajów pozycji:**

| Rodzaj pozycji | Klucz | Co blokujemy |
|---|---|---|
| z numerem rysunku | **numer rysunku** | numer; nazwa zostaje edytowalna (to tylko opis) |
| **znormalizowane** (bez numeru) | **symbol generowany z nazwy** (`symbol_z_nazwy`) | **nazwę** — bo to z niej powstaje symbol |

To rozróżnienie jest istotne: dla łożysk, pasków, czujników i innych pozycji
znormalizowanych **nazwa nie jest opisem, tylko nośnikiem tożsamości**. Jej zmiana
daje inny symbol, czyli dokładnie ten sam skutek co zmiana numeru rysunku
przy pozycji rysunkowej.

Blokada dotyczy pozycji **wysłanych już do Subiekta**, w szczególności tych
wchodzących w skład KT.

> Ten sam problem widziano już wcześniej z drugiej strony: w Edytorze kartotek
> symbol zapisanej kartoteki jest wygaszony, a okno potwierdzenia ostrzega,
> że **symbol po zapisie nie podlega zmianie** (`SUBIEKT_ZMIANY_2026-09-08.md`,
> sekcje 1.7 i 1.9). Tu chodzi o źródło tego symbolu po stronie RM_BAZA.
>
> Uwaga na `rozroznij_symbol`: przy kolizji nazw symbol dostaje sufiks (`-2`),
> więc dwie pozycje znormalizowane o podobnych nazwach mogą mieć symbole zależne
> od **kolejności** ich przetwarzania. Przy blokadzie nazw to przestaje być
> problemem dla pozycji już wysłanych, ale warto o tym pamiętać przy zasiewie.

### 6D.5. Lock i współbieżność

RM_BAZA nie blokuje samego programu Subiekt, ale w przyjętym procesie użytkownicy
**nie edytują tych danych bezpośrednio w Subiekcie ani przez inne interfejsy**.

Wszystkie zmiany ilości ZK idą drogą:

`użytkownik → RM_BAZA → lock projektu → Projekt / Aktualizacja → Subiekt`

Lock projektu blokuje równoległą edycję tego samego projektu przez inną instancję RM_BAZA.
W związku z tym:

- odczyt Subiekta przy **wzięciu locka** jest właściwym momentem odświeżenia,
- po **wymuszonym przejęciu locka** dane trzeba odczytać ponownie,
- po każdym własnym zapisie do Subiekta lokalny widok należy odświeżyć wynikiem z Subiekta.

Warunkiem szczelności modelu jest to, że każde przyszłe narzędzie RM_BAZA zmieniające ZK
musi respektować **ten sam lock projektu**.

### 6D.6. Potwierdzenie każdego zapisu — write + read-back

Każdy zapis do produkcyjnego Subiekta musi być potwierdzony odczytem z Subiekta.

Nie wystarczy, że most nie zwrócił wyjątku. Sekwencja ma być następująca:

1. użytkownik wykonuje zmianę,
2. most zapisuje zmianę do Subiekta,
3. most / RM_BAZA ponownie odczytuje zmienioną pozycję lub dokument,
4. wartość odczytana jest porównywana z wartością oczekiwaną,
5. dopiero po zgodności pokazywany jest komunikat sukcesu.

Przykład sukcesu:

> ✅ **Zapisano w Subiekcie**  
> KT 2627-650.11ZZ  
> Ilość: **2 → 3**

Jeżeli zapis został wykonany, ale odczyt kontrolny nie potwierdza wartości, system **nie może**
pokazać zielonego sukcesu. Powinien wyświetlić ostrzeżenie, np.:

> ⚠ **Nie potwierdzono zapisu w Subiekcie**  
> Oczekiwano: **3**  
> Odczytano: **2**

Na obecnym etapie wystarczy zwykłe okno `messagebox` informujące o sukcesie lub braku
potwierdzenia. Rozbudowany raport można dodać później.

Ta zasada obowiązuje dla każdego zapisu zmieniającego dane w Subiekcie.

### 6D.7. Dane Subiekta w RM_BAZA

Dane z Subiekta mogą być przechowywane lokalnie jako cache potrzebny do szybkiego widoku,
np.:

- `qty_subiekt`,
- `qty_subiekt_at`,
- **symbol kartoteki Subiekta** (klucz: numer rysunku / symbol pozycji
  znormalizowanej — patrz 6D.4b; **nie** wprowadzamy dodatkowego ID),
- numer ZK, jeżeli jest potrzebny do jednoznacznego powiązania.

Nie nadpisujemy nimi `src_qty`, `work_qty` ani innych pól BOM-u.

SQLite po stronie RM_BAZA jest w tym zakresie **cache'em odczytu Subiekta**, a nie drugim
źródłem prawdy dla „Ilość (zam.)”.

### 6D.8. Pozycja usunięta z ZK

Jeżeli pozycja nadal istnieje konstrukcyjnie w BOM-ie, ale została usunięta z ZK:

- **Ilość BOM** pozostaje bez zmian,
- **Ilość (zam.)** pokazuje `0`,
- ponowne dodanie pozycji na ZK odbywa się przez okno Projekt / Aktualizacja.

`0` jest stanem prawdziwym: pozycja konstrukcyjnie istnieje, ale na ZK nie ma aktualnie
zamówionej ilości.

> ⚠ **Nie dotyczy składników KT.** Ta reguła obowiązuje tylko pozycje, które
> **były** na ZK i zostały z niego usunięte. Składnik kompletu nigdy nie ma
> własnego wiersza (wariant 1), więc pokazuje `—`, nie `0` — patrz 6D.3a.

### 6D.9. Nowy zakres po pierwszym zasiewie

Dodanie kolejnego BOM-u może zwiększyć „Ilość BOM” istniejących pozycji i dodać nowe pozycje.

RM_BAZA:

- aktualizuje własny BOM zgodnie z dotychczasową logiką,
- pokazuje aktualne „Ilość BOM” obok „Ilość (zam.)” z Subiekta,
- **nie nadpisuje automatycznie istniejącej „Ilość (zam.)”**.

Nowe kartoteki / KT nieobecne jeszcze w Subiekcie mogą zostać zasiane przez
Projekt / Aktualizacja. Dla pozycji już istniejących na ZK użytkownik świadomie zmienia
„Ilość (zam.)” w tym samym oknie — jako bezpośrednią edycję Subiekta.

### 6D.10. Migracja projektu z incydentu

Projekt z incydentu zostanie usunięty z Subiekta i założony od nowa.
Istniejące narzędzie „↩ Cofnij projekt” usuwa odpowiednie elementy, po czym projekt zostanie
zasiany ponownie z prawidłowym stanem początkowym.

Nie jest potrzebne osobne narzędzie migracyjne dla błędnego stanu historycznego.

**Pozostałe istniejące ZK — tryb legacy.** Projekt z incydentu to nie jedyny
dokument zasiany po staremu; wszystkie dotychczasowe ZK mają płaskie składniki.

> **Zasada:** wariant 1 obowiązuje **wyłącznie projekty zasiane po jego wdrożeniu**.
> Istniejące ZK pozostają w trybie **legacy** do zakończenia projektu — nie są
> automatycznie czyszczone ze składników.

Powód: automatyczne usuwanie wierszy z wystawionych dokumentów księgowych byłoby
operacją o dużym zasięgu i nieodwracalną, a przy tym mogłoby wyzerować
zapotrzebowanie, które dziś na tych wierszach stoi (6D.4a). Dokumenty legacy
dożywają swojego cyklu w obecnej postaci.

**Konsekwencja dla 6D.3a:** stwierdzenie „składnik KT nigdy nie był osobną
pozycją" dotyczy projektów **po wdrożeniu**. W projektach legacy składnik ma
własny wiersz na ZK, więc zgodnie z regułą z 6D.2a jego „Ilość (zam.)" jest
normalną, edytowalną ilością dokumentową — nie `—`. Obie reguły działają obok
siebie bez konfliktu, bo obie pytają o to samo: *czy symbol ma własny wiersz na ZK*.
---

## 7. Co już naprawiono (2026-09-08, wdrożone)

Niezależnie od wyboru modelu pewne było jedno: **most musi rozjazd wykrywać
i pokazywać**. To zostało zrobione — jako czysta warstwa informacyjna,
**bez zmiany tego, co jest zapisywane**.

Decyzja użytkownika co do zakresu tej poprawki:

> *„Natomiast na razie niech efekt takiego porównania będzie: ⚠ RÓŻNICA ILOŚCI —
> TYLKO INFORMACJA, a nie automatyczne nadpisanie."*

**Most** (`Projekt.cs`):

- `CzytajPozycjeZk()` zwraca `{symbol → ilość}` zamiast `HashSet` samych symbolów
  (typ `PozycjaDokumentu`; powtórzony symbol sumuje ilości, bo dla zapotrzebowania
  liczy się suma, nie sposób rozpisania na wiersze);
- nowy rodzaj kroku `"zk-poz"` ze statusami `roznica-ilosci` (suchy przebieg)
  i `roznica-ilosci-pominieta` (po zapisie), opis: `BOM: 10 — na ZK: 4 (różnica +6)`;
- status `bez-zmian` przestał kłamać: przy rozjeździe mówi
  *„N pozycji już na dokumencie, w tym M z INNĄ ILOŚCIĄ niż BOM — nic nie zmieniono"*.

**Okno** (`subiekt_projekt.py`) — rozjazd widoczny w czterech miejscach, bo brak
informacji zgłoszono na każdym etapie:

1. pasek statusu zaraz po „Przelicz",
2. czerwony kafelek „RÓŻNICA ILOŚCI" jako pierwszy w oknie potwierdzenia,
3. wiersze na czerwonym tle, sortowane na samą górę tabeli (filtr
   „pokaż tylko zmiany" ich **nie** ukrywa),
4. sekcja w raporcie po zapisie z wartościami + `showwarning` zamiast `showinfo`.

Przy okazji kafelek „BEZ ZMIAN" → „SKŁAD BEZ ZMIAN", bo liczy wyłącznie komplety,
a czytał się jak stwierdzenie o całej operacji — był częścią fałszywego obrazu.

> **Uwaga dla czytającego:** po tej zmianie użytkownik zgłosił *„zapisuje ale
> w subiekcie nie ma zapisu"* — to jest **zachowanie zamierzone**, nie regresja.
> Ilości nie były zapisywane także wcześniej; różnica polega na tym, że teraz
> system o tym mówi. Docelowo problem znika wraz z sekcją 6D.

---

## 8. Zasada nadrzędna zgłoszona przez użytkownika

Sformułowana przy tej okazji, ale dotyczy **całego systemu**, nie tylko ZK:

> *„potrzebuję zawsze informację przed jakąkolwiek zmianą (…) zawsze jakaś zmiana
> to musi być okno pokazujące co będzie zmienione i po zmianie co zostało zmienione
> i na jaką wartość czy na co"*

Czyli każda operacja zmieniająca dane musi mieć:

1. **okno PRZED** — co zostanie zmienione, z jakiej wartości na jaką,
2. **raport PO** — co faktycznie zmieniono i na jaką wartość.

Nie wystarczy liczba zbiorcza ani status wyliczony z niepełnego porównania. Jeśli kod
porównuje tylko część danych (jak tutaj: sam symbol, bez ilości), to raport jest
**kłamliwy** — użytkownik widzi „bez zmian", a dane się zmieniają (albo, jak tutaj,
nie zmieniają się mimo że powinny).

Kontekst wagi tej zasady: zapis idzie na **bazę produkcyjną**, a części zmian
(założone kartoteki) nie da się łatwo cofnąć. To nie jest pierwsze takie zgłoszenie —
w kodzie są komentarze odnoszące się do analogicznych incydentów z 04.09, 06.09, 07.09
i 08.09.2026, każdy o tym samym: coś przeszło po cichu albo raport mówił co innego
niż stan faktyczny.

---

## 9. Weryfikacja rozwiązania docelowego

Po doprecyzowaniu procesu przyjęto następujący model:

1. **„Ilość BOM” i „Ilość (zam.)” to dwie różne informacje.**
   - BOM pozostaje własnością RM_BAZA / Inventora.
   - „Ilość (zam.)” pozostaje własnością Subiekta.

2. **Okno Projekt / Aktualizacja pełni dwie role.**
   - Przy pierwszym zasiewie tworzy dane w Subiekcie.
   - Później jest frontendem do bezpośredniej edycji ZK w Subiekcie.

3. **RM_BAZA nie edytuje składu KT.**
   - Użytkownik zmienia ilość KT; RM_BAZA odczytuje i pokazuje wynik.
   - Subiekt **nie przelicza** składników na ZK — robi to tylko na dokumentach
     produkcyjnych (6D.4).
   - **Decyzja podjęta: wariant 1** — na ZK idzie sam KT, a zapotrzebowanie
     na składniki liczy kalkulator Subiekta z `ObslugaKompletow = ZamowSkladniki`.
     Wykonalność zależy od wyników testów zapotrzebowania (etap 0c).

4. **Edycja Subiekta odbywa się wyłącznie przez RM_BAZA.**
   - Nie ma równoległej edycji tych danych w Nexo przez inne interfejsy.
   - Lock projektu RM_BAZA serializuje zmiany wykonywane przez użytkowników.

5. **Każdy zapis jest weryfikowany read-backiem.**
   - Sukces jest pokazywany dopiero po potwierdzeniu wartości odczytanej z Subiekta.
   - Brak zgodności oznacza ostrzeżenie, nie komunikat sukcesu.

6. **Stan początkowy arkusza pozostaje bez przebudowy UX.**
   - „Ilość BOM” działa jak dotąd.
   - „Ilość (zam.)” po zasiewie / edycji odzwierciedla Subiekta.
   - Ewentualne podświetlenie źródła wartości można dodać później.

Nie projektujemy mechanizmu automatycznego uzgadniania BOM ↔ ZK. Zamiast tego każda z dwóch
kolumn ma własne, jednoznaczne znaczenie, a zmiany wartości dokumentowej wykonywane są
bezpośrednio w Subiekcie przez interfejs RM_BAZA.
---

## 10. Podsumowanie decyzji

Stan na 2026-09-09. Rozwiązanie docelowe jest ustalone.

| # | Decyzja |
|---|---|
| 1 | **Ilość BOM** pozostaje własnością RM_BAZA / Inventora |
| 2 | **Ilość (zam.)** jest własnością Subiekta |
| 3 | Pierwszy zasiew wykonuje okno **Projekt / Aktualizacja** |
| 4 | Po zasiewie to samo okno jest frontendem do bezpośredniej edycji ZK w Subiekcie |
| 5 | RM_BAZA **nie edytuje składu KT** |
| 6 | Edytujemy ilości pozycji mających **własny wiersz ZK**: KT-korzeni oraz TW samodzielnych |
| 7 | Ilości TW będących składnikami KT nie są edytowane bezpośrednio |
| 7a | Kolumna **„Typ / Źródło"**: `KT` / `TW` / `Składnik KT <symbol>` — informacja dla usera |
| ~~8~~ | ~~Zmiana ilości KT powoduje zmianę jego TW po stronie Subiekta~~ — **OBALONE**, Subiekt tego nie robi na ZK (6D.4) |
| 9 | RM_BAZA po zmianie odczytuje wynik z Subiekta, nie duplikuje logiki kompletów |
| 9a | **Klucz** pozycji wysłanej zablokowany w arkuszu: numer rysunku, a dla pozycji znormalizowanych **nazwa** (bo z niej powstaje symbol) |
| ~~9b~~ | ~~Składniki KT nie trafiają na ZK (wariant 1)~~ — **ODRZUCONE 2026-09-09**, struktura ZK zostaje bez zmian (6D.4a) |
| ~~9c~~ | ~~Zapotrzebowanie liczy kalkulator z `ZamowSkladniki`~~ — **ODRZUCONE**, kalkulatora nie da się zawołać ze Sfery |
| 9d | Składniki KT **zostają** na ZK jako płaskie pozycje — na nich stoi zapotrzebowanie. Ich ilości poprawia się ręcznie w Subiekcie |
| 10 | Kolumna **Ilość BOM** pozostaje bez zmiany logiki |
| 11 | Kolumna **Ilość (zam.)** po zasiewie / edycji pokazuje stan z Subiekta |
| 11a | Cykl kolumny: **przed zasiewem** edytowalna (z niej idzie ilość na ZK) → **po zasiewie** nadpisana wartością z Subiekta i **zablokowana** (6D.2a) |
| 11b | Kryterium blokady: **ma własną pozycję na ZK** → edytowalna; **brak własnej pozycji, tylko składnik KT** → `—`, nieedytowalna. Blokada wynika ze stanu danych, nie z wyglądu GUI (6D.2a) |
| 11c | **Rola ≠ typ kartoteki.** Ten sam symbol może być jednocześnie samodzielny i składnikiem KT — wtedy ma własny wiersz ZK na część „luzem" i ta ilość **jest edytowalna** (6D.2b) |
| 11d | Na ZK trafiają wyłącznie **korzenie** zamawianego drzewa. KT będący składnikiem innego KT **nie dostaje** własnej pozycji (6D.2c) |
| 12 | Możliwe późniejsze podświetlenie komórki jako informacji o źródle danych |
| 13 | Wszystkie edycje ZK idą przez RM_BAZA; użytkownicy nie edytują tych danych innymi interfejsami |
| 14 | Lock projektu blokuje równoległą edycję przez inne RM_BAZY |
| 15 | Odczyt Subiekta przy wzięciu locka i ponownie po wymuszonym przejęciu |
| 16 | Każdy zapis do Subiekta: **write → read-back → dopiero komunikat sukcesu** |
| 17 | Na obecnym etapie potwierdzenie zapisu = zwykłe okno sukcesu / ostrzeżenia |
| 18 | Dane Subiekta w SQLite są cache'em i nie nadpisują danych BOM |
| 18a | Powiązanie trzymamy przez **symbol** kartoteki (numer rysunku / symbol znormalizowanej) — bez dodatkowego ID |
| 19 | Pozycja **usunięta** z ZK: Ilość (zam.) = `0`, Ilość BOM bez zmian |
| 19a | **Składnik KT**: Ilość (zam.) = `—` (nie `0`) — nie ma własnej pozycji na ZK (6D.3a) |
| 19b | Rozwinięte zapotrzebowanie (np. 6 szt.) to **osobna kolumna**, nigdy „Ilość (zam.)" |
| 20 | Nowy zakres nie nadpisuje automatycznie ilości istniejących pozycji ZK |
| 21 | Projekt z incydentu zostanie cofnięty w Subiekcie i zasiany od nowa |
| 21a | Wariant 1 obowiązuje **tylko projekty zasiane po wdrożeniu**; istniejące ZK zostają w trybie **legacy** do końca projektu (6D.10) |


## 11. Kolejność wdrożenia

> ### ⏸ ZAKRES NA TERAZ — decyzja z 2026-09-09
>
> **Nie wdrażamy teraz edycji ilości w Subiekcie.** Etapy 1–7 zostają
> **odłożone na później** jako specyfikacja do zrealizowania w swoim czasie.
>
> **Na teraz obowiązuje stan obecny:** ilości idą **sztywno z arkusza RM_BAZA
> przy zasiewie**, tak jak dotąd. Arkusz pozostaje miejscem, gdzie ustala się
> ilości przed wysłaniem projektu do Subiekta.
>
> Czyli działa wyłącznie **faza „przed zasiewem"** z 6D.2a. Brakuje nadpisania
> wartością z Subiekta i blokady po zasiewie — to właśnie odłożona część.
>
> Działa więc wyłącznie **etap 0** (wdrożony): most wykrywa i raportuje różnicę
> ilości BOM vs ZK, niczego nie zapisując. Rozjazd jest widoczny, a poprawki
> na wystawionym dokumencie robi się ręcznie w Subiekcie.
>
> **Co pozostaje aktualne mimo odłożenia:**
> - testy z etapu 0c (można je zrobić kiedykolwiek, nic nie psują),
> - blokada klucza pozycji wysłanych (6D.4b) — chroni przed duplikatami kartotek
>   **niezależnie** od tego, czy edycja ilości kiedykolwiek powstanie,
> - wiedza z 6D.4 o hybrydowej reprezentacji BOM-u na ZK.

**Etap 0 — zrobione.**  
Most wykrywa i raportuje różnice ilości BOM vs ZK. Nie zapisuje ich automatycznie.

**Etap 0a — ZROBIONE (weryfikacja dokumentacji Sfery).**  
Ustalono, że Subiekt **nie przelicza** składników przy zmianie ilości KT na ZK —
komplet jest tam jedną pozycją, a relacja komplet↔składniki istnieje tylko
na dokumentach produkcyjnych (6D.4). Etap 5 w pierwotnej postaci odpada.

**Etap 0b — ZAMKNIĘTY.** Rozważano wariant 1 (na ZK sam KT); po testach 0c
**odrzucony** — struktura ZK zostaje bez zmian (6D.4a).

**Etap 0c — WYKONANY (2026-09-09).**  
Tryb `zapotrzebowanie-test` w moście (`ZapotrzebowanieTest.cs`, czysty odczyt).
Wynik: `ZapotrzebowanieNaAsortyment()` **nie rozwija** kompletów (26 kompletów
w 209 pozycjach), a `IKalkulatorZapotrzebowania` **jest nieosiągalny** ze Sfery.
Stąd decyzja o pozostawieniu płaskich składników na ZK.

> Tryb zostaje w moście — przyda się, gdyby kiedyś sprawdzać, czy nowa wersja
> Sfery udostępnia kalkulator.

**Etap 1 — rozdzielenie widoku ilości.**  
Upewnić się, że „Ilość BOM” i „Ilość (zam.)” są traktowane jako osobne wartości
i żadna nie nadpisuje drugiej. Tu też: **kolumna rodzaju pozycji**
(`KT` / `TW` / `Składnik KT <symbol>`) i **blokada klucza** pozycji wysłanych —
numeru rysunku, a dla znormalizowanych nazwy (6D.4b).

**Etap 2 — identyfikacja pozycji Subiekta + cache.**  
Dodać / utrwalać co najmniej:
- `qty_subiekt`,
- `qty_subiekt_at`,
- **symbol kartoteki Subiekta** (numer rysunku / symbol znormalizowanej —
  bez wymyślania dodatkowego ID),
- numer ZK, jeżeli potrzebny.

**Etap 3 — odczyt przy locku.**  
Po przejęciu locka projektu pobrać aktualne „Ilość (zam.)” z Subiekta.
Po wymuszonym przejęciu wykonać odczyt ponownie.

**Etap 4 — edycja w Projekt / Aktualizacja.**  
Dla projektu już zasianego okno staje się frontendem Subiekta:
- edycja ilości **KT mających własną pozycję ZK** (korzeni),
- edycja ilości **TW samodzielnych / luzem**,
- brak bezpośredniej edycji pozycji będących **składnikami KT** (TW *lub* KT),
  które nie mają własnego wiersza ZK.

Kryterium jest jedno i wspólne (6D.2a): **własny wiersz na ZK** → edytowalne.

**Etap 5 — ODPADA.**  
Miał obsługiwać przeliczanie składników przy zmianie ilości KT. Po odrzuceniu
wariantu 1 (6D.4a) składniki zostają na ZK jako **niezależne pozycje**, a ich
ilości poprawia się ręcznie w Subiekcie. RM_BAZA ich nie przelicza i nie edytuje —
duplikowanie logiki kompletów byłoby powrotem do dwóch źródeł prawdy, tym razem
dla składu.

**Etap 6 — obowiązkowe potwierdzenie każdego zapisu.**  
Po każdej zmianie:
1. zapis,
2. ponowny odczyt,
3. porównanie z wartością oczekiwaną,
4. `messagebox` sukcesu tylko przy zgodności,
5. ostrzeżenie przy braku potwierdzenia.

**Etap 7 — dopracowanie UX (opcjonalne).**  
Można później dodać podświetlenie komórek „Ilość (zam.)” lub tooltip informujący,
że wartość pochodzi z Subiekta. Nie jest to wymagane do poprawności modelu.
---

## Załącznik: pliki i miejsca w kodzie

| Plik | Rola |
|---|---|
| `subiekt_projekt.py` | okno „Projekt / Aktualizacja", `build_plan()`, okno potwierdzenia (`_potwierdz_zapis`, ok. linii 2340–2620) |
| `subiekt_sfera/NexoRecon/Projekt.cs` | most C#: suchy przebieg i zapis ZK (sekcja „── 3. ZK ──", od linii 246), `CzytajPozycjeZk()` |
| `import_bom.py` | odczyt BOM/drzewka z plików `*_OUT.xlsx` z dysku V:\ |
| `SUBIEKT_ZMIANY_2026-09-08.md` | dziennik zmian z tego dnia (m.in. sekcja o raporcie po zapisie w Edytorze kartotek — wzorzec dobrego raportowania) |

Dodatkowo dla rozwiązania z sekcji 6D:

| Plik | Rola |
|---|---|
| `RM_BAZA_v15_MAG_STATS_ORG.py` | arkusz główny; `ProjectLockManager`, `have_lock`, `current_lock_id`, przycisk „Przejmij Lock", heartbeat co 30 s |
| `lock_manager_v2.py` | locki per projekt (`Y:/RM_BAZA/locks`) — miejsce, w którym ma się zaczepić odczyt z Subiekta |
| `project_<id>.sqlite`, tabela `items` | kolumny ilości (`order_qty`, `work_qty`, `src_qty`); tu dochodziłyby `qty_subiekt` + `qty_subiekt_at` |

> Po zmianach w `Projekt.cs` konieczny `dotnet build` i wdrożenie mostu
> do `C:\iLogic\Subiekt\MOST`.
