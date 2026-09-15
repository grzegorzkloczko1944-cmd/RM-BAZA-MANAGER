---
name: project_subiekt_magazyn
description: "Okno Magazyn (progi min/opt, ZD na skład, RW, usuwanie kartotek) — tryby mostu progi/rw/kartoteka-usun i pułapki Sfery"
metadata: 
  node_type: memory
  type: project
  originSessionId: 834ab505-1a4e-4f62-bb02-1b4871507207
  modified: 2026-09-05T19:59:33.668Z
---

Okno **Magazyn — stany, progi min/opt, zamówienia na skład** (`subiekt_magazyn_gui.py`, menu SUBIEKT → 🏬). Zbudowane 05.09.2026 na pytanie „jak magazynier ma zamawiać na magazyn". Decyzje użytkownika: progi ustawiane w RM_BAZA (nie w Subiekcie), ZD na skład ze znacznikiem `MAGAZYN` w Uwagach, cały magazyn z filtrem.

## Co robi

| Funkcja | Most | Uwagi |
|---|---|---|
| Progi Min/Opt edytowane w tabeli, „Kupić" = opt − stan gdy stan ≤ min | `progi` (odczyt / `--plan --zapisz --magazyn=MAG`) | 05.09 żadna z 3442 kartotek nie miała progów — magazynier biegał z karteczkami |
| ZD na skład dla zaznaczonych | `zd` z `uwagi:"MAGAZYN"`, pozycje `reczna:true` | bez ZK, bez projektu; Przegląd dokumentów pokazuje 📦 MAGAZYN |
| „Dodaj z katalogu…" — przeglądarka WSZYSTKICH kartotek z wyszukiwarką | `katalog` (3444 w ~9 s, bez stanów) | lista główna to tylko 794 ze stanem/progiem |
| Zdejmij ze stanu (RW) z powodem w Uwagach | `rw` | pierwsze prawdziwe RW od lipca 2023: RW 1/09/2026 |
| Usuń kartoteki z Subiekta | `kartoteka-usun` | tylko bez historii; Subiekt odmawia reszcie |

Kolumna ZD z otwartych zamówień przychodzi RAZEM ze stanami (tryb `magazyn` zwraca `Zd`, `StanMinimalny/Optymalny`, `Dostawca`) — osobne wywołanie kosztowało drugie ~10 s startu Sfery. Odczyt: **15,8 s** (było 27), z czego ~10 s to sam start mostu.

## Pułapki Sfery, które kosztowały rundy

- **Progi siedzą w ZAKRESIE magazynowym** (`StanyWMagazynachZakresy`), nie na kartotece, i zakresu nie ma żadna kartoteka. Zakładamy go: `new StanWMagazynieZakres()` → **NAJPIERW `Add()`** → dopiero potem pola (dokładnie jak SDK `RealizacjaBase.cs`). Ustawienie `Magazyn`/`Asortyment` przed Add dawało `Zapisz()==false` z pustym `PodajBledy()`.
- **`Wszystkie()` nie doładowuje kolekcji zakresów** — odczyt po udanym zapisie pokazywał „brak progu". Wzorem `Magazyn.cs`: projekcja symboli, potem `WyszukajPoSymbolu` per kartoteka.
- **LINQ to Entities**: własna metoda (`Bezp`) w predykacie na `Magazyny().Dane.Wszystkie()` → „does not recognize the method". `ToList()` przed filtrem.
- **`Usun()` kartoteki wraca BEZ wyjątku, choć Subiekt odmówił** — 015-100.13 (stan 30, ZD) dostało „usunieta", a istniało. `MoznaUsunac` też mówiło true. Jedyna prawda: ponowne `WyszukajPoSymbolu` po `Usun()`; odmowa daje `Usun()=false` + PodajBledy „Nie można usunąć asortymentu, który jest użyty na dokumencie".
- **`Utworz(Konfiguracja)` dla RW**: właściwość w `DaneDomyslne` szukać **po typie** `ModelDanych.Konfiguracja` — po nazwie „RozchodWewn" trafiało w konfigurację pól własnych („invalid arguments").
- **Encja `Asortyment` nie ma `Dostawcy`** (to na obiekcie biznesowym); kolekcję dostawców szukamy refleksją. I tak 0/794 kartotek ma przypisanego dostawcę — dane, nie kod.

## Pułapki własne

- **`NL` w kodzie generowanym skryptem** — nazwa istniała w skrypcie, nie w module; klik „Wystaw RW" kończył się NameError w konsoli i ciszą w oknie. Teraz `NL = chr(10)` w module.
- **Przełącznik „pokaż też bez stanu"** ciągnął 3442 kartoteki × osobne zapytania → okno wisiało minutami. Usunięty; zamiast niego katalog na żądanie.
- **Kolorowanie**: ZD tylko na swojej kolumnie (cały wiersz zasłaniał „poniżej progu"); Dostępne / Min-Opt / Kupić w trzech różnych kolorach; zielony zarezerwowany na zrealizowane.

**How to apply:** Każda nowa operacja zapisu przez Sferę — po `Zapisz()`/`Usun()` **odczytać z powrotem i porównać**; sukces zwrotu nic nie znaczy. Patrz [[project_subiekt_stan_05_09_2026]], [[project_subiekt_zk_komplety]].
