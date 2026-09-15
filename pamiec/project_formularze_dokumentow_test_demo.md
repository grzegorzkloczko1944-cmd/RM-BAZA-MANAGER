---
name: project_formularze_dokumentow_test_demo
description: Formularze RW/PW/ZD/ZK z Edytora kartotek — testowane WYŁĄCZNIE suchym przebiegiem; realny zapis do sprawdzenia na bazie DEMO w domu
metadata: 
  node_type: memory
  type: project
  originSessionId: b4b4fbd4-107b-4ece-9328-8ca8b8a060fc
  modified: 2026-09-10T18:18:12.439Z
---

Cztery formularze dokumentów z Edytora kartotek (10.09.2026) —
`subiekt_rw_gui`, `subiekt_pw_gui`, `subiekt_zd_gui`, `subiekt_zk_gui` na
wspólnym szkielecie `subiekt_dokument_form` — działają, ale **żaden nie był
przetestowany REALNYM ZAPISEM**. Wszystko szło suchym przebiegiem
(`zapisz=False`) na bazie produkcyjnej.

**Do zrobienia: pierwszy zapis każdego typu na bazie DEMO w domu.**

**Why:** dokumentu magazynowego nie cofa się jednym kliknięciem — PW i RW
ruszają stan, ZD i ZK tworzą dokumenty powiązane z zapotrzebowaniem. Suchy
przebieg sprawdza plan i walidację Sfery, ale nie samo `Zapisz()` ani tego,
co Subiekt zapisze naprawdę (read-back).

**How to apply:**
- Kolejność: RW (najprostszy, bez cen) → PW (cena tworzy warstwę) →
  ZD (kilka dokumentów naraz, grupowanie po dostawcy) → ZK (blokada
  „jeden projekt = jedno ZK").
- Po każdym zapisie sprawdzić w Subiekcie: czy dokument JEST NA LIŚCIE
  (brak daty wystawienia = dokument istnieje, ale wypada z list — pułapka
  znana z ZD i RW), czy Uwagi mają SAM numer projektu, czy Tytuł ma opis
  ([[project_subiekt_uwagi_tytul]]).
- ZK: sprawdzić, czy blokada duplikatu działa przy zapisie, nie tylko
  w suchym przebiegu — `ZkNowe.cs` odmawia gdy `ZnajdzZkProjektu` coś zwróci.
- PW: pierwszy zapis z ceną i drugi bez ceny — ten drugi ma dać ostrzeżenie
  o zerowej warstwie ([[project_subiekt_rw_bez_wyceny]] jeśli powstanie).
- Znane pułapki SDK złapane w suchym przebiegu, ale warte uwagi przy zapisie:
  `PozycjaDokumentu.Cena` to OBIEKT (liczy się `NettoPoRabacie`),
  numer dokumentu to `NumerWewnetrzny.PelnaSygnatura`, data to
  `DataWydaniaWystawienia` na klasie bazowej `Dokument`.
