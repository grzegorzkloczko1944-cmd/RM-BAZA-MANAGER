# RM_BAZA — formularze dokumentów z Edytora kartotek Subiekta

## Status
Robocze ustalenia z 10.09.2026. Szczegóły działania poszczególnych dokumentów będą dalej dopracowywane.

### Rozstrzygnięcia z 10.09.2026 (po konfrontacji specyfikacji z kodem)

1. **Ceny do PW** — będą uzupełnione w magazynie, ręcznie. Formularz PW nie
   musi ich skądkolwiek wyliczać; pole zostaje edytowalne, domyślnie puste.
   Kontekst: 1183 z 1376 kartotek ze stanem nie ma dziś żadnej ceny przyjęcia
   (skutek migracji magazynu nr 2, patrz MAGAZYN.md) — dlatego RW potrafi
   wyjść z kosztem 0,00 i dlatego most ostrzega o tym statusem `bez-wyceny`.
2. **ZD może być z ceną 0** — cena nie jest warunkiem wystawienia zamówienia.
   Uwaga do wykonania: dzisiejszy `subiekt_wyslij_zd.py` i `Zd.cs` NIE mają
   pól cenowych, więc cena na ZD to rozszerzenie mostu, nie podpięcie.
3. **Projekt na dokumencie** — do Uwag idzie SAM NUMER (np. `2741`), bez
   prefiksów. Tak wyglądają dokumenty wystawiane dotąd ręcznie w Subiekcie
   (RW 24/09/2026 → Uwagi `2645`), więc format zostaje zachowany.
4. **Kolejność prac**: RW → PW → ZK (dopisz) → ZK (nowe) → ZD → MM/PZ/WZ.
5. **`subiekt_dokument_form.py` powstaje OD RAZU**, nie „później" — wspólna
   tabela pozycji dla wszystkich formularzy. Powód: dziś istnieją już trzy
   niezależne ścieżki wystawiania RW (Kalkulator RMPAK, okno Magazyn, ręcznie
   w Subiekcie), które się rozjechały. Drugi raz tego nie powtarzamy.

---

## 1. Pasek dokumentów w Edytorze

Na górnym pasku Edytora kartotek Subiekta:

**[ RW ] [ PW ] [ ZD ] [ ZK ▼ ] [ Więcej ▼ ]**

### ZK
Menu rozwijane:

- **Utwórz ZK**
- **Dopisz do ZK**

### Więcej
Na początek:

- **MM**
- **PZ**
- **WZ**

---

## 2. Zasada główna — okno 1 jest roboczym koszykiem

Dokumenty są tworzone dla **wielu pozycji jednocześnie**.

Źródłem jest:

**1. Struktura kartoteki (drzewo)**

Pozycje wrzucone do okna 1 tworzą roboczy zestaw, z którego użytkownik może wystawić dokument.

Przykład:

```text
OKNO 1

UCFL 201                  4 szt.
DFM-20-100-P-A-GF         2 szt.
DRVS-32-180               3 szt.
CZUJNIK SICK              6 szt.
DIN 912 M6x20            40 szt.
```

Kliknięcie **RW / PW / ZD / ZK** otwiera **jedno zbiorcze okno formularza** z całym zestawem pozycji.

Nie otwieramy osobnego formularza dla każdej kartoteki.

---

## 3. Zasada pobierania pozycji

Domyślnie formularz dokumentu pobiera **wszystkie pozycje znajdujące się w oknie 1**.

W samym formularzu każda pozycja ma checkbox:

```text
☑ użyj na dokumencie
```

Użytkownik może:

- odznaczyć pozycję,
- poprawić ilość,
- usunąć pozycję z bieżącego dokumentu,
- anulować formularz bez zmiany okna 1.

Później można rozważyć dodatkowy tryb „tylko zaznaczone w drzewie”, ale nie jest potrzebny w pierwszej wersji.

---

# 4. Formularz RW

Jedno RW może zawierać wiele pozycji.

Przykładowy formularz:

```text
RW — ROZCHÓD WEWNĘTRZNY

Magazyn: [ MASTER ▼ ]
Data:    [ 10.09.2026 ]
Projekt: [ 2741 ]
Uwagi:   [ ................................ ]

☑  Symbol                 Nazwa             Stan    Ilość RW
----------------------------------------------------------------
☑  UCFL 201               Łożysko             12       4
☑  DFM-20-100-P-A-GF      Siłownik              5       2
☑  DRVS-32-180            Napęd                  3       3
☑  SICK-WT...             Czujnik               20       6
☑  DIN 912 M6x20          Śruba                180      40

[ Zaznacz wszystko ] [ Odznacz wszystko ]

                         [ Sprawdź ] [ WYSTAW RW ]
```

### Założenia RW

- jeden dokument dla całej wybranej listy,
- wybór magazynu,
- ilość edytowalna,
- stan pokazany informacyjnie,
- bez ręcznego wpisywania ceny,
- przed zapisem: **Sprawdź** / suchy przebieg.

### Uwaga
Istniejący workflow produkcyjny **PW → RW** pozostaje osobnym mechanizmem.  
Przycisk RW w Edytorze ma być ręcznym RW z pozycji okna 1.

---

# 5. Formularz PW

Jedno PW może zawierać wiele pozycji.

```text
PW — PRZYCHÓD WEWNĘTRZNY

Magazyn: [ MASTER ▼ ]
Data:    [ 10.09.2026 ]
Projekt: [ 2741 ]
Uwagi:   [ ................................ ]

☑  Symbol             Nazwa              Ilość PW     Cena
-------------------------------------------------------------
☑  2741-100.01        Korpus                 2        450,00
☑  2741-100.02        Płyta                  4        120,00
☑  2741-200.00        Zespół                 1       1800,00

                             [ Sprawdź ] [ WYSTAW PW ]
```

### Założenia PW

- jeden dokument dla wielu pozycji,
- magazyn,
- ilość,
- cena przyjęcia,
- uwagi/projekt,
- suchy przebieg przed właściwym zapisem.

---

# 6. Formularz ZD — generator wielu dokumentów

ZD różni się od RW/PW.

Pozycje z okna 1 mogą mieć **różnych dostawców**, dlatego jeden formularz ZD powinien umieć wygenerować **kilka ZD jednocześnie**.

```text
ZD — ZAMÓWIENIA DO DOSTAWCÓW

☑ Symbol               Dostawca          Ilość    Cena
-------------------------------------------------------
☑ DFM-20-100            FESTO               2     312,00
☑ DRVS-32-180           FESTO               3     420,00
☑ UCFL 201              TECH-ŁOŻYSKA        4      48,00
☑ GN 617.1-6            ELESA+GANTER        6      35,00
☑ SICK-WT...            SICK                2     690,00

DOKUMENTY, KTÓRE POWSTANĄ

FESTO                  2 poz.  → ZD
TECH-ŁOŻYSKA           1 poz.  → ZD
ELESA+GANTER            1 poz.  → ZD
SICK                    1 poz.  → ZD

                    [ Sprawdź ] [ UTWÓRZ 4 ZD ]
```

### Założenia ZD

- tabela zbiorcza wszystkich pozycji,
- dostawca widoczny i edytowalny,
- ilość edytowalna,
- cena zakupu,
- możliwość pominięcia pozycji,
- automatyczne grupowanie po dostawcy,
- podsumowanie: ile dokumentów ZD powstanie,
- jeden przycisk może utworzyć kilka ZD.

To jest **ręczne ZD z Edytora**, niezależne od ZK.

Istniejący mechanizm „Zamówienia do dostawców” oparty na zapotrzebowaniu z ZK pozostaje oddzielnym workflow.

---

# 7. ZK — dwa tryby

## 7.1. Utwórz nowe ZK

Wszystkie wybrane pozycje z okna 1 trafiają na jedno nowe ZK.

```text
ZK — NOWE ZAMÓWIENIE OD KLIENTA

Klient:          [ ABC Sp. z o.o. ▼ ]
Termin:          [ 30.09.2026 ]
Projekt / uwagi: [ Maszyna 2741 ]

☑ Symbol          Nazwa                    Ilość      Cena
----------------------------------------------------------
☑ 2741-000        Nalewarka                  1      120000
☑ SZ-100          Szafa sterownicza          1       25000
☑ URUCH           Uruchomienie               1        5000

                                  [ UTWÓRZ ZK ]
```

---

## 7.2. Dopisz do istniejącego ZK

```text
ZK — DOPISZ POZYCJE

Klient: [ ABC Sp. z o.o. ▼ ]

OTWARTE ZK KLIENTA

● ZK 48/2026    Projekt 2741        31 pozycji
○ ZK 51/2026    Części zamienne      8 pozycji

DO DOPISANIA

☑ UCFL 201             4 szt.
☑ DFM-20-100            2 szt.
☑ CZUJNIK SICK          3 szt.

                       [ DOPISZ DO ZK 48/2026 ]
```

### Kolizja pozycji
Jeżeli symbol już istnieje na ZK:

```text
UCFL 201 już występuje na ZK w ilości 4 szt.

[ Dodaj do ilości ] [ Zostaw bez zmian ] [ Anuluj ]
```

Nie należy bezmyślnie tworzyć drugiego identycznego wiersza.

---

# 8. Komplety / drzewo — sposób rozwijania

To wymaga jeszcze osobnego ustalenia dla każdego dokumentu.

Wspólny możliwy wybór:

```text
Pozycje:
● pozycje bezpośrednio z okna 1
○ rozwiń komplety o jeden poziom
○ rozwiń komplety do najniższych składników
```

Przykład drzewa:

```text
ZESPÓŁ A
 ├─ UCFL 201
 └─ śruba

ZESPÓŁ B
 ├─ UCFL 201
 └─ czujnik
```

Po rozwinięciu i spłaszczeniu dokument może dostać:

```text
UCFL 201      6 szt.
Śruba        20 szt.
Czujnik       2 szt.
```

Powtarzające się symbole powinny być sumowane.

Nie zakładamy jeszcze, że RW, PW, ZD i ZK mają korzystać z identycznej reguły rozwijania — to będzie ustalane osobno.

---

# 9. Architektura GUI

Z punktu widzenia użytkownika:

- RW → osobne okno RW,
- PW → osobne okno PW,
- ZD → osobne zbiorcze okno ZD,
- ZK → jedno okno ZK pracujące w trybie `new` albo `append`,
- MM / PZ / WZ → osobne formularze później.

W kodzie wspólne elementy powinny być współdzielone.

Proponowany podział:

```text
subiekt_dokument_form.py      # wspólna tabela pozycji, walidacja, checkboxy

subiekt_rw_pw_gui.py          # RW + PW
subiekt_zd_gui.py             # ręczne / zbiorcze ZD
subiekt_zk_gui.py             # nowe ZK + dopisz do ZK
subiekt_mm_gui.py             # MM
subiekt_pz_wz_gui.py          # PZ + WZ

subiekt_dokumenty_gui.py      # pozostaje przeglądarką istniejących dokumentów
```

---

# 10. Wspólne elementy formularzy

W każdym formularzu:

- tabela wielu pozycji,
- checkbox użycia pozycji,
- edycja ilości,
- możliwość usunięcia z bieżącego dokumentu,
- podgląd stanu, jeśli ma znaczenie,
- walidacja przed zapisem,
- **Sprawdź** przed operacją zapisującą,
- **Anuluj** bez zmiany danych źródłowych,
- jednoznaczny przycisk końcowy, np. `WYSTAW RW`, `WYSTAW PW`, `UTWÓRZ 4 ZD`.

---

## Kolejne tematy do ustalenia

1. Dokładne reguły rozwijania kompletów dla RW.
2. Dokładne reguły rozwijania kompletów dla PW.
3. Dokładne reguły rozwijania kompletów dla ZD.
4. Dokładne reguły rozwijania kompletów dla ZK.
5. Skąd pobierać ceny domyślne dla PW/ZD/ZK.
6. Jak przypisywać dostawcę przy ZD.
7. Jak wybierać klienta i istniejące ZK.
8. Czy formularze mają pozwalać dodawać jeszcze pozycje spoza okna 1.
9. Zachowanie przy braku kartoteki Subiekta.
10. Obsługa MM, PZ i WZ.
