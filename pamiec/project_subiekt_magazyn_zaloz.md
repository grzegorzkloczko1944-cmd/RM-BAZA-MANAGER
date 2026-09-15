---
name: project_subiekt_magazyn_zaloz
description: Zakladanie magazynu przez Sfere - pulapka dwoch roznych "jednostek organizacyjnych"
metadata:
  type: project
---

`IMagazyny.Utworz()` istnieje i dziala (tryb `magazyn-zaloz` w moscie,
`MagazynZaloz.cs`). Ale Subiekt **odrzuca zapis magazynu bez co najmniej
jednej jednostki organizacyjnej**: *"Magazyn X musi byc podlaczony do co
najmniej jednej jednostki organizacyjnej"*.

## Pulapka: DWIE rozne "jednostki organizacyjne" w SDK

- `InsERT.Moria.Kadry.Duze.IJednostkiOrganizacyjne` -> **DZIAL kadrowy**
  (`JednostkaOrganizacyjnaGr`: Nazwa, JednostkaNadrzedna... **brak Symbol**).
  Mimo najbardziej oczywistej nazwy - to NIE to.
- `InsERT.Moria.ModelOrganizacyjny` -> **CENTRALA/ODDZIAL firmy**
  (klasa `JednostkaOrganizacyjna`, podklasy `Centrala` i `Oddzial`).
  TO jest wymagane przez `Magazyn.Dane.JednostkiOrganizacyjne`.
  Dostep: `ICentrale.Znajdz()` (zawsze jedna) + `IOddzialy.Dane.Wszystkie()`.

Wlasciwosci nie sa jednolicie dostepne na typie bazowym mimo ze dokumentacja
je tam wypisuje - trzeba `dynamic` na Centrala/Oddzial osobno.

**Pole NIP nie jest bezposrednio na tym obiekcie** - dopasowanie zadzialalo
dopiero po Symbolu. W tej firmie jednostka to
`RMPRODUKCJADZIERZGOWSKI,KLOCZKOS` (jedyna w systemie).

Patrz [[project_magazyn_nr2_migracja]].
