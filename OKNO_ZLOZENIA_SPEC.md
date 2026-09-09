# Okno „Złożenia projektu" — specyfikacja do zaprojektowania

**Data:** 2026-09-10
**Cel:** zaprojektować wygląd okna, które pokazuje złożenia (komplety) projektu
**Stan:** logika i dane gotowe, brakuje wyglądu

---

## 1. Kontekst — o co chodzi

RM_BAZA to system zarządzania projektami konstrukcyjnymi maszyn w firmie RMPAK.
Zintegrowany z **Subiektem nexo PRO** (system handlowo-magazynowy).

Projekt maszyny ma **drzewko konstrukcyjne** z Inventora (BOM). Pozycje dzielą
się na typy:

```
TW  = towar, pojedyncza część:
      STANDARD  — element znormalizowany albo kupny
      X / XX    — element do cięcia / cięcia i gięcia

KT  = komplet, złożenie z części:
      Z         — złożenie
      ZZ        — złożenie złożeń (zespół)
```

W Subiekcie odwzorowuje to **kartoteka typu Komplet** ze składem.

### Kluczowa właściwość kompletu

**Komplet NIE MA własnego stanu magazynowego.** Jego dostępność wynika ze
stanu składników. Dlatego komplet:

* nie trafia na ZK (zamówienie do dostawcy),
* nie trafia na PW (przyjęcie z produkcji),
* nie trafia na RW (wydanie),
* **istnieje wyłącznie jako kartoteka ze składem**.

Przyjęcie kompletu obok jego części zdublowałoby stan na każdym poziomie
drzewa.

---

## 2. Problem do rozwiązania

Dziś złożenia **nie mają swojego widoku**. Użytkownik widzi je tylko:

1. przy zasiewie projektu do Subiekta — jako suchy komunikat
   „25 kompletów do utworzenia",
2. klikając pojedynczo w „Kartę pozycji" konkretnego detalu.

**Brakuje miejsca, gdzie widać wszystkie złożenia projektu naraz** i można
sprawdzić, czy są w Subiekcie kompletne i poprawne.

---

## 3. Dane, które okno ma pokazać

Wszystkie są już dostępne — sprawdzone na żywym projekcie **3500 Dupal**
(id 71, 211 pozycji, 27 złożeń).

### 3.1. Dla każdego złożenia

| Pole | Skąd | Przykład |
|---|---|---|
| Numer rysunku | drzewko / BOM | `2627-100.00ZZ` |
| Nazwa | BOM | `Kabina` |
| Typ | `class_*` w bazie | `ZZ` albo `Z` |
| Ilość w projekcie | BOM | `1` |
| Składników wg drzewka | plik `*_OUT.xlsx` | `38` |
| Składników w Subiekcie | most, tryb `komplet` | `38` |
| Stan kartoteki | most | `istnieje` / `brak` / `pusty` |
| Zgodność składu | porównanie | `OK` / `rozjazd` |
| Wchodzi w | most (`WchodziW`) | `2627-000.00ZZ YamCandle_Z` |
| Produkcja własna | reguła RMPAK | `tak` / `nie (dostawca MAJA)` |

### 3.2. Skład rozwinięty (po kliknięciu)

Każdy składnik ma: symbol, nazwę, ilość, **rodzaj** (Towar / Komplet) —
złożenia bywają **zagnieżdżone**, np. `2627-100.00ZZ Kabina` zawiera
5 innych kompletów i 33 towary.

---

## 4. Stan faktyczny na projekcie 3500 (dane do makiety)

```
złożeń w projekcie:        27
  ze składem w Subiekcie:  25   ✓ zgodne z drzewkiem, ZERO rozjazdów
  BEZ składu (puste):       2   ⚠ 027-100.00Z, 027-300.06Z
  brak kartoteki:           0

z tych 27:
  produkcja własna:        25   (robimy u siebie)
  kupowane gotowe:          2   (mają wpisanego dostawcę)
```

Dwa puste to **złożenia biblioteczne** — ich skład mieszka w bibliotece
`B:\`, nie w folderze projektu, i biblioteka ma tam bałagan. To znany
przypadek, nie awaria: użytkownik musi je rozstrzygnąć ręcznie
(założyć bez składu / uzupełnić / pominąć).

### Przykład wiersza z prawdziwymi danymi

```
2627-100.00ZZ   Kabina              ZZ   1 szt.
    składników: 38 (drzewko) = 38 (Subiekt)   ✓ zgodne
    wchodzi w:  2627-000.00ZZ YamCandle_Z
    produkcja własna
    skład: 33 towary + 5 kompletów zagnieżdżonych:
           2602-100.45ZZ Zespół naprawczy zawiasa  ×4
           2627-100.19ZZ Rolka napinacza           ×4
           2627-100.16Z  Wanna pospawana           ×1
           2627-100.21Z  Rama suwaka B             ×1
           2627-100.26Z  Uchwyt                    ×1
```

---

## 5. Do czego to okno służy — scenariusze

1. **Po zasiewie projektu** — sprawdzić, czy wszystkie złożenia powstały
   i mają pełny skład. Dziś trzeba klikać pojedynczo.
2. **Znaleźć niekompletne** — złożenie bez składu to komplet, którego
   magazynier nie ma z czego złożyć, a wygląda na poprawny.
3. **Zobaczyć strukturę** — co w co wchodzi, ile poziomów ma maszyna.
4. **Rozstrzygnąć biblioteczne** — te dwa puste wymagają decyzji człowieka.

---

## 6. Ograniczenia techniczne

* **Tkinter** (Python), biblioteka **tksheet** do tabel — jak reszta RM_BAZA.
* Zapytanie do Subiekta o skład 27 złożeń trwa **kilka sekund** — okno musi
  ładować dane asynchronicznie z widocznym stanem „czytam…".
* Struktura jest **wielopoziomowa** (komplet w komplecie), ale głębokość
  rzadko przekracza 3-4 poziomy.
* Okno ma być spójne z resztą aplikacji: ciemnogranatowe paski nagłówków
  (`#34495e`), legenda kolorów pod paskiem filtrów, tabela tksheet.

### Kolory używane w RM_BAZA (do zachowania spójności)

```
#d6eaf8   ZK — zamówienie od klienta
#d5f0dd   PW — przyjęcie z produkcji własnej
#fdebd0   RW — wydanie na produkcję
#f4ecf7   WZ — wydanie zewnętrzne
#f2dede   błąd / brak (czerwonawe)
#fcf3cf   trafienie wyszukiwarki (żółte)
#eaecee   anulowany / nieaktywny (szare)
```

---

## 7. Czego oczekuję od projektu graficznego

Makieta okna pokazująca:

* **układ** — gdzie lista złożeń, gdzie skład wybranego, gdzie filtry;
  czy panele w pionie czy w poziomie (w oknie dokumentów sprawdził się
  układ poziomy: lista po lewej, szczegóły po prawej);
* **jak pokazać zagnieżdżenie** — drzewko rozwijane czy płaska lista
  z wcięciem? Maszyna ma 3-4 poziomy;
* **jak wyróżnić problemy** — złożenie bez składu i rozjazd składu muszą
  rzucać się w oczy, bo to jedyny powód, dla którego ktoś tu zagląda;
* **co w nagłówku** — podsumowanie liczbowe (27 złożeń, 25 OK, 2 puste);
* **jakie filtry** — pokazać tylko problematyczne? tylko produkcję własną?

Nie potrzebuję kodu — potrzebuję **układu i hierarchii informacji**.
Implementację zrobię w Tkinter/tksheet.

---

## 8. Uwaga na koniec

Okno jest **tylko do odczytu**. Nie zmienia niczego w Subiekcie ani w bazie
projektu — służy do sprawdzenia, czy to, co tam jest, zgadza się z drzewkiem.

Zakładanie i naprawa składów dzieje się w istniejącym oknie
„Projekt / Aktualizacja".
