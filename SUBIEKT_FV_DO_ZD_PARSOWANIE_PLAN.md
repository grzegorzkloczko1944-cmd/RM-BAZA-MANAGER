# RM_BAZA ↔ Subiekt nexo PRO — parsowanie e-Faktury/FV i dopasowanie pozycji do ZD

## Cel

Ten plik jest instrukcją dla agenta programistycznego, który ma zbudować mechanizm odbioru dostaw na podstawie faktury zakupowej oraz dopasowania pozycji faktury do otwartych zamówień do dostawców (ZD) w Subiekcie nexo PRO.

Najważniejsza zasada:

> Nie pisać własnego parsera pozycji faktury, jeśli można wykorzystać mechanizmy Subiekta/e-Faktury do rozpoznania asortymentu.

Docelowy przepływ:

```text
e-Faktura / KSeF / dokument elektroniczny
        ↓
Subiekt nexo PRO
        ↓
identyfikacja asortymentu
        ↓
pozycje z rozpoznanym AsortymentId / symbolem
        ↓
RM_BAZA / NexoRecon
        ↓
dopasowanie do otwartych ZD dostawcy
        ↓
propozycja realizacji ZD
        ↓
zatwierdzenie przez użytkownika
```

Nie mieszać dwóch problemów:

1. `pozycja faktury → kartoteka Subiekta`
2. `kartoteka Subiekta → konkretna pozycja / konkretne ZD`

Subiekt powinien, o ile to możliwe, rozwiązywać problem nr 1.  
RM_BAZA powinno rozwiązywać problem nr 2.

---

## 1. Dlaczego nie zaczynać od PDF/OCR

PDF faktury jest złym źródłem jako główny mechanizm:

- różne układy kolumn,
- różne nazwy pól,
- brak jednolitego indeksu,
- różne formaty liczb i jednostek,
- opisy wielowierszowe,
- rabaty, transport i koszty dodatkowe,
- OCR w skanach,
- zmiany szablonu dostawcy.

Jeżeli faktura trafia do Subiekta jako e-Faktura/KSeF, dane są strukturalne i nie trzeba odtwarzać tabeli z wyglądu dokumentu.

Preferowany kierunek:

```text
KSeF/XML/e-Faktura
      ↓
Subiekt
      ↓
rozpoznane pozycje asortymentu
```

PDF może zostać jako fallback.

---

## 2. Co chcemy dostać z Subiekta

Dla każdej pozycji e-Faktury chcemy co najmniej:

```text
invoice_line_no
supplier_nip
supplier_code
supplier_name
description
quantity
unit
unit_price
net_value
vat
currency

subiekt_assortment_id
subiekt_symbol
subiekt_name
match_source
match_status
```

Najważniejsze są:

```text
subiekt_assortment_id
subiekt_symbol
```

Jeżeli Subiekt poprawnie rozpozna kartotekę, RM_BAZA nie musi już analizować nazwy pozycji faktury.

---

## 3. Mechanizm identyfikacji asortymentu w Subiekcie

Subiekt potrafi identyfikować pozycje e-Faktury m.in. na podstawie:

```text
- symbolu u kontrahenta,
- nazwy u kontrahenta,
- GTIN / kodu kreskowego,
- symbolu kartoteki,
- nazwy kartoteki,
- wyszukiwania przybliżonego.
```

Powiązanie może być związane z konkretnym kontrahentem, co jest pożądane.

Przykład:

```text
Dostawca: FESTO
kod na fakturze: DSNU-20-100-P-A

Subiekt:
AsortymentId = 18372
Symbol = DSNU20100PA
```

Następna faktura tego dostawcy może już zostać rozpoznana bez zgadywania po nazwie.

---

## 4. Czego nie robić na początku

Nie tworzyć od razu równoległego globalnego mechanizmu:

```text
supplier_code → symbol_subiekt
```

jeżeli Subiekt już przechowuje podobne zależności dla e-Faktur.

Najpierw sprawdzić, czy przez Sferę/API da się odczytać wynik identyfikacji wykonany przez Subiekta.

Własny mapping w RM_BAZA może być fallbackiem.

---

## 5. Główne zadanie agenta: sprawdzić aktualne SDK

Agent ma przejrzeć aktualne SDK nexo/Sfera oraz assembly używane w projekcie i znaleźć API związane z:

```text
DokumentyElektroniczne
IDokumentyElektroniczne
DokumentElektroniczny
IDokumentElektroniczny
IDaneEFaktury
e-Faktura
KSeF
ImportFaktury
FakturaZakupu
Przetworz
```

Znany kierunek:

```csharp
IDokumentyElektroniczne dokumentyElektroniczne =
    sfera.DokumentyElektroniczne();
```

oraz dostęp do obiektów:

```text
DokumentElektroniczny
IDokumentElektroniczny
DaneFaktury
```

Agent nie ma zgadywać nazw metod. Ma sprawdzić realne API w wersji SDK używanej w firmie.

---

## 6. Preferowany wariant: robocza FZ bez zapisu

Najlepszy wariant:

```text
odebrana e-Faktura
      ↓
Subiekt tworzy roboczy dokument FZ
      ↓
uruchamia swój mechanizm identyfikacji
      ↓
pozycje FZ mają już AsortymentId
      ↓
NexoRecon odczytuje wynik
      ↓
Dispose / anulowanie dokumentu
      ↓
NIC nie zapisujemy w Subiekcie
```

Przykładowy wynik dla RM_BAZA:

```json
{
  "invoice": {
    "number": "FV/342/2026",
    "supplier_nip": "1234567890",
    "date": "2026-09-05"
  },
  "lines": [
    {
      "line_no": 1,
      "supplier_code": "DSNU-20-100-P-A",
      "description": "Siłownik pneumatyczny",
      "quantity": 2,
      "unit": "szt",
      "unit_price": 123.50,
      "subiekt_assortment_id": 18372,
      "subiekt_symbol": "DSNU20100PA",
      "subiekt_name": "Siłownik DSNU 20 100",
      "recognized": true
    }
  ]
}
```

---

## 7. Jeżeli robocza FZ nie jest dostępna przez Sferę

Sprawdzić mechanizm rozszerzenia importu e-Faktury, np. API typu:

```text
IDodatkowaFunkcjaImportuFaktury
```

które podczas przetwarzania otrzymuje obiekty związane z:

```text
IDokument
IDaneEFaktury
```

Agent ma sprawdzić:

- czy można przechwycić już rozpoznane pozycje,
- czy można wywołać to bez ręcznej pracy użytkownika,
- czy wynik można przekazać do NexoRecon/RM_BAZA.

---

## 8. Fallback: własny matcher

Dopiero jeśli nie uda się uzyskać wyniku rozpoznania Subiekta, zrobić własny matcher.

Hierarchia:

```text
1. supplier_id + supplier_code exact
2. supplier_id + normalized supplier_code
3. subiekt_symbol exact
4. GTIN exact
5. exact supplier item name
6. normalized name
7. jednostka + cena + ilość jako sygnały pomocnicze
8. fuzzy name tylko jako podpowiedź
```

Nie automatyzować fuzzy matchingu w ciemno.

Nazwy techniczne mogą być bardzo podobne, mimo że oznaczają inne elementy.

---

## 9. Identyfikacja dostawcy

Pierwszy krok po odczytaniu faktury:

```text
NIP faktury → kontrahent Subiekta
```

NIP traktujemy jako klucz główny.

Nie dobierać dostawcy wyłącznie po nazwie.

Schemat:

```text
supplier_nip
    ↓
KontrahentId Subiekt
    ↓
otwarte ZD tego kontrahenta
```

---

## 10. Dopasowanie kartoteki do ZD

Po rozpoznaniu:

```text
AsortymentId = 18372
```

pobieramy otwarte pozycje ZD tego dostawcy:

```text
ZD/61
  AsortymentId 18372
  zamówiono 3
  zrealizowano 0
  pozostaje 3

ZD/72
  AsortymentId 18372
  zamówiono 4
  zrealizowano 1
  pozostaje 3
```

Pozycja FV:

```text
AsortymentId 18372
ilość 5
```

Propozycja:

```text
ZD/61 → 3
ZD/72 → 2
```

---

## 11. Nie zakładać 1 FV = 1 ZD

Prawidłowy model:

```text
1 FV może realizować wiele ZD
1 ZD może być realizowane przez wiele FV
```

Przykład:

```text
FV/123
poz. 1 → ZD/81 poz. 4
poz. 2 → ZD/81 poz. 8
poz. 3 → ZD/93 poz. 2
poz. 4 → zakup bez ZD
```

Odwrotnie:

```text
ZD/81
zamówiono 10 szt.

FV/123 → 4 szt.
FV/137 → 6 szt.
```

To jest relacja wiele-do-wielu.

---

## 12. Dane relacji FV ↔ ZD

Jeżeli RM_BAZA ma zapamiętywać decyzje przed zapisem w Subiekcie, można dodać tabelę:

```text
invoice_order_match
```

Przykładowe pola:

```text
id
invoice_id
invoice_line_no

supplier_id
subiekt_assortment_id
subiekt_symbol

zd_number
zd_position_id

invoice_qty
assigned_qty

match_method
match_status

confirmed_by
confirmed_at
```

`assigned_qty` jest konieczne, bo jedna linia FV może być rozdzielona na kilka ZD.

---

## 13. Liczenie ilości pozostałej

Nie porównywać FV z ilością pierwotną ZD.

Liczyć:

```text
remaining_qty =
ordered_qty
- already_realized_qty
```

Przykład:

```text
ZD: 20 szt.
odebrano wcześniej: 8 szt.
pozostaje: 12 szt.
FV: 10 szt.

=> po tej FV pozostanie 2 szt.
```

---

## 14. Nadwyżka na FV

Przykład:

```text
pozostaje na ZD: 12
FV: 15
```

Pokazać:

```text
⚠ Nadwyżka: 3
```

Użytkownik powinien móc wybrać:

```text
- 12 przypisz do ZD, 3 poza ZD
- 15 przypisz do ZD mimo nadwyżki
- nie przyjmuj
- wybierz inne ZD
```

Nie robić cichego automatu.

---

## 15. Cena jako walidacja, nie klucz

Cena może zwiększać pewność dopasowania, ale nie jest identyfikatorem.

Możliwe różnice:

```text
- zmiana ceny,
- rabat,
- kurs waluty,
- transport,
- rabat dokumentowy,
- zaokrąglenia.
```

Dlatego cena służy do ostrzeżeń:

```text
⚠ cena +4.8%
```

---

## 16. Jednostki

Normalizować typowe jednostki:

```text
szt. / szt / pcs / pc → szt
kg / KG → kg
m / mb / metr → m
kpl / komplet / set → kpl
```

Nie robić automatycznych przeliczników typu:

```text
1 op = 100 szt.
```

bez jawnej reguły dla konkretnego asortymentu.

---

## 17. Pozycje poza ZD

Faktura może zawierać:

```text
transport
paleta
opakowanie
usługa
rabat
koszt wysyłki
opłata
```

Nie każda pozycja musi odpowiadać ZD.

Przykładowe statusy:

```text
MATCHED_TO_ZD
MATCHED_NO_ZD
SERVICE
COST
UNKNOWN
```

Użytkownik musi móc oznaczyć pozycję jako `poza ZD`.

---

## 18. Pewność dopasowania do ZD

Po rozpoznaniu kartoteki przez Subiekta dopasowanie do ZD jest proste.

Przykład punktacji:

```text
+100 ten sam AsortymentId
+30 ten sam kontrahent
+20 ilość mieści się w remaining_qty
+10 zgodna jednostka
+10 cena w tolerancji
```

Najważniejszy jest exact `AsortymentId`.

Jeżeli kartoteka występuje tylko na jednym otwartym ZD:

```text
AUTO
```

Jeżeli na kilku:

```text
SUGGEST
```

---

## 19. Strategia wyboru ZD

Domyślna propozycja:

```text
najstarsze otwarte ZD najpierw
```

czyli FIFO po dacie.

Przykład:

```text
ZD/61  3 szt. pozostało
ZD/72  4 szt. pozostało

FV 5 szt.

propozycja:
ZD/61 → 3
ZD/72 → 2
```

Propozycję zawsze pokazać użytkownikowi przed zapisem.

---

## 20. Jeżeli numer ZD znajduje się na fakturze

To najlepszy przypadek.

Jeżeli e-Faktura zawiera referencję typu:

```text
OrderReference
BuyerOrderNumber
numer zamówienia
```

albo dostawca wpisuje:

```text
ZD/123/2026
```

należy użyć tego jako priorytetowego zawężenia.

Agent ma sprawdzić, jakie pola referencyjne są dostępne w danych e-Faktury/KSeF w aktualnym SDK.

---

## 21. GUI odbioru

Proponowane okno:

```text
FV: FV/342/2026
Dostawca: FESTO
NIP: 1234567890

┌──────────────────────────────────────────────────────────────────────────────┐
│ FV kod        Nazwa FV       Ilość   Kartoteka      ZD         Status        │
├──────────────────────────────────────────────────────────────────────────────┤
│ DSNU...       Siłownik        2       DSNU20100      ZD/123     ✅ pewne      │
│ UCFL 201      Łożysko         4       UCFL201        ZD/128     ✅ pewne      │
│ M6X20         Śruba           50      DIN912M6X20    2 ZD       ⚠ wybierz     │
│ TRANSPORT     Transport       1       —              —          ⬜ poza ZD     │
└──────────────────────────────────────────────────────────────────────────────┘
```

Dwuklik w niepewną pozycję pokazuje kandydatów i remaining qty.

---

## 22. Po zatwierdzeniu

Dopiero po potwierdzeniu użytkownika wykonujemy realne operacje.

Docelowo należy wykorzystać mechanizm Subiekta realizujący pozycje ZD przez dokument zakupowy/FZ.

Cel:

```text
ZD
 ↓
FZ realizująca konkretne pozycje ZD
```

a nie:

```text
FZ niezależna
+
notatka RM_BAZA "to było z tego ZD"
```

Prawdziwe powiązanie dokumentów ma pozostać w Subiekcie.

---

## 23. PZ

Na obecnym etapie odbiory są robione na podstawie FV.

Nie projektować PZ jako warunku tego mechanizmu.

Architektura ma jednak nie blokować późniejszego wariantu:

```text
ZD → PZ → FZ
```

---

## 24. Proponowany podział modułów

Python:

```text
subiekt_invoice_source.py
```

- lista e-Faktur,
- pobranie danych faktury.

```text
subiekt_invoice_recognizer.py
```

- e-Faktura → rozpoznane kartoteki Subiekta.

```text
subiekt_invoice_zd_matcher.py
```

- kartoteka → otwarte ZD,
- remaining_qty,
- propozycja rozdziału.

```text
subiekt_invoice_gui.py
```

- prezentacja,
- manualne poprawki,
- zatwierdzenie.

Po stronie C# można rozważyć komendy:

```text
invoice-list
invoice-read
invoice-recognize
invoice-zd-candidates
invoice-apply
```

Nazwy są robocze.

---

## 25. Współpraca ze stałym bridge'em

Ten mechanizm powinien korzystać ze stałego bridge'a:

```text
RM_BAZA
   ↓
subiekt_bridge.py
   ↓
NexoRecon server
   ↓
jedna żywa sesja Sfery
```

Nie uruchamiać osobnego `NexoRecon.exe` dla każdej pozycji FV.

---

## 26. Rewalidacja przed zapisem

Tuż przed commit ponownie pobrać stan ZD.

Powód:

```text
user A otworzył FV
user B w tym czasie zrealizował ZD
```

Sprawdzić:

```text
czy ZD nadal istnieje
czy pozycja nadal otwarta
czy remaining_qty się nie zmieniło
```

Jeżeli się zmieniło:

```text
⚠ Dane ZD zmieniły się od czasu otwarcia okna.
Odśwież dopasowanie.
```

---

## 27. Multi-user

Każdy użytkownik ma lokalny bridge, ale wszyscy pracują na tej samej bazie Subiekta.

Dlatego lokalny mutex bridge'a nie wystarczy do ochrony logiki biznesowej.

Zawsze rewalidować stan w Subiekcie przed zapisem.

---

## 28. Status faktury

Dodać rozróżnienie:

```text
NEW
IN_PROGRESS
MATCHED
POSTED
IGNORED
```

Nie proponować drugi raz faktury już obsłużonej.

Najlepiej identyfikować dokument po stabilnym ID dokumentu elektronicznego/KSeF, nie tylko po numerze FV.

---

## 29. Audyt

Każde zatwierdzenie powinno zostawić ślad:

```text
invoice_document_id
invoice_number
supplier_nip
invoice_line_no

subiekt_assortment_id
zd_number
zd_position_id

assigned_qty

user
timestamp
match_method
manual_override
```

---

## 30. Błędy jawne

Przykładowe statusy:

```text
UNKNOWN_ASSORTMENT
AMBIGUOUS_ASSORTMENT
NO_OPEN_ZD
MULTIPLE_ZD
OVER_QUANTITY
PRICE_DIFFERENCE
```

GUI ma je pokazać, nie naprawiać po cichu.

---

## 31. Fuzzy matching

Jeżeli będzie potrzebne, tylko do listy kandydatów.

Nigdy:

```text
fuzzy > threshold
=> automatyczny zapis
```

Dopuszczalne:

```text
fuzzy > threshold
=> pokaż kandydatów użytkownikowi
```

---

## 32. Przyszłe KSeF

Architektura ma oddzielać źródło faktury od matchera FV↔ZD.

```text
PDF parser --------                    KSeF parser --------> InvoiceData → Recognizer → ZD Matcher
                    /
Subiekt e-Faktura --/
```

Po zmianie źródła faktury logika dopasowania do ZD pozostaje ta sama.

---

## 33. MVP

Pierwszy proof-of-concept:

1. pobierz jedną odebraną e-Fakturę z Subiekta,
2. odczytaj NIP dostawcy,
3. odczytaj wszystkie pozycje,
4. uzyskaj wynik identyfikacji kartotek Subiekta,
5. dla każdej kartoteki znajdź otwarte ZD dostawcy,
6. pokaż kandydatów,
7. niczego jeszcze nie zapisuj.

---

## 34. Test na realnej fakturze

Wybrać rzeczywistą FV dostawcy, którego ZD są w Subiekcie.

Raport:

```text
liczba pozycji FV
ile Subiekt rozpoznał automatycznie
ile nie rozpoznał
ile trafiło na 1 ZD
ile na kilka ZD
ile nie ma ZD
```

Przykład:

```text
10 pozycji FV
8 rozpoznanych kartotek
6 jednoznaczne ZD
2 kilka ZD
1 poza ZD
1 nierozpoznana kartoteka
```

Dopiero po takim pomiarze decydować, ile własnej logiki trzeba dopisać.

---

## 35. Kryteria akceptacji pierwszego etapu

Pierwszy etap jest udany, jeśli:

1. NexoRecon potrafi pobrać listę e-Faktur.
2. Potrafi wskazać jedną fakturę.
3. Potrafi odczytać NIP.
4. Potrafi odczytać pozycje.
5. Dla pozycji zwraca rozpoznane `AsortymentId` albo jasno raportuje brak.
6. RM_BAZA znajduje otwarte ZD po kontrahencie.
7. RM_BAZA znajduje pozycje ZD po `AsortymentId`.
8. Pokazuje ordered / realized / remaining.
9. Nic nie zapisuje automatycznie.
10. Nie używa fuzzy do cichego przypisania.
11. Działa przez stały bridge.
12. Wszystkie niejednoznaczności są widoczne.

---

## 36. Najważniejsza myśl dla agenta

Nie zaczynaj od:

```text
regex na PDF
OCR
fuzzy po nazwie
AI do interpretacji pozycji
```

Najpierw sprawdź:

> Czy Subiekt potrafi już rozpoznać pozycję e-Faktury jako konkretną kartotekę i czy wynik tego rozpoznania można dostać przez Sferę / roboczą FZ / mechanizm importu.

Jeżeli tak, to trudniejsza połowa problemu jest już rozwiązana przez Subiekta.

RM_BAZA ma wtedy zrobić przede wszystkim:

```text
rozpoznana kartoteka
        ↓
otwarte ZD dostawcy
        ↓
remaining_qty
        ↓
propozycja realizacji
```

To jest znacznie pewniejsze niż własne parsowanie faktury.
