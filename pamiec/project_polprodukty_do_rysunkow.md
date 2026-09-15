---
name: project_polprodukty_do_rysunkow
description: "Półprodukty zakupowe pod rysunki (koło surowe → detal obrobiony) — ustalenia projektowe 14.09.2026, przed implementacją"
metadata:
  type: project
---

Temat zgłoszony przez logistyka: detal powstaje z KUPIONEGO półfabrykatu
(rysunek „Koło 5M_40 fi38" = gotowe koło 5M/40 + obróbka otworu Ø38 H8).
Trzeba kupować półfabrykat przez ZK projektu i wyceniać detal w kalkulatorze.

## Ustalenia (14.09.2026)

**Właściciel kartoteki = Subiekt. Właściciel RELACJI = RM_BAZA.** Bez drugiego,
równoległego świata półfabrykatów w arkuszu.

**⛔ KOMPLET (Z/ZZ) ODPADA — decyzja zamknięta, nie „na później".** Powody:
- typ kartoteki ustawia się przy ZAKŁADANIU (`szablony.DaneDomyslne.Komplet`,
  `Kartoteka.cs:63`); detale z zasiewu są TW, „awans" = nowa kartoteka;
- detal figuruje już na ZK/RW i w historii → **przerobienie TW na KT to
  rozjazd drzewek** (słowa użytkownika), czyli dokładnie to, czego pilnuje
  panel „Decyzje" i `subiekt_zlozenia_gui`;
- ten sam symbol bywa JEDNOCZEŚNIE samodzielny i składnikiem
  (`ANALIZA_ZK_DWA_ZRODLA_PRAWDY.md` 6D.2b) — jako komplet traci to
  rozróżnienie i ZK ma dwa źródła ilości dla jednej pozycji.
Obie kartoteki zostają TW, niezależne; zużycia Subiekt NIE rozlicza sam.

**⚠️ Pola własne Subiekta (PoleWlasne2..8) NIE jako źródło prawdy.** Most je
czyta i zapisuje (`PolaWlasne.cs`, `PoleWlasne1` = położenie magazynowe), ale:
tekst zamiast `id` (zmiana symbolu rozrywa relację), brak miejsca na ilość
na sztukę, odczyt = przelot przez Sferę (~setki ms, przy zimnej sesji 9 s)
zamiast ~20 ms z bazy mapowań. Dopuszczalne jako JEDNOKIERUNKOWY, czytelny
ślad dla człowieka („detale: 2621-100.61"), nadpisywany przy każdym zapisie.

**Gdzie trzymać relację:** baza mapowań na serwerze (`subiekt_mapowania.sqlite`,
routing `map-*`) — nowa tabela `polprodukty(numer_rysunku, id_subiekt, symbol,
ilosc_na_szt, kto, kiedy)`. NIE w `items` bazy projektu: `items` jest PER
PROJEKT, a relacja ma być globalna (kalkulator ma podpowiadać w nowym
projekcie). Infrastruktura (routing, migracje, backup, klient) już działa.

**Kalkulator — kluczowe:** `items` MA JUŻ kolumny `calc_mode`,
`calc_semi_price`, `calc_semi_name`, `calc_semi_supplier_id`
(`rmpak_calculator._ensure_calc_columns`). Tryb półfabrykatu istnieje, ale
trzyma NAZWĘ i CENĘ, bez `id` kartoteki. Dołożyć `calc_semi_subiekt_id`
i wpiąć się w to, co jest — NIE budować drugiego mechanizmu obok.
Cena: `id` i ilość z RM_BAZA, cena z Subiekta na bieżąco; przy ZAPISANEJ
wycenie utrwalić cenę z chwili kalkulacji.

**ZK:** agregacja po `id_subiekt` (kilka rysunków → jedna pozycja ZK), bez
osobnych linii per rysunek — rozbicie „skąd 9 szt." zostaje w RM_BAZA.
Mechanizm „nie dodać drugi raz" JUŻ DZIAŁA: `subiekt_projekt` porównuje
z żywym ZK i USTAWIA ilość zamiast dopisywać. Relacja jest niezależna od ZK
— logistyk dodaje półfabrykat, gdy ZK jeszcze nie ma i gdy już jest.

**Kolejność wdrożenia:** (1) PPM na pozycji → „Powiąż półprodukt" → okno
wyboru kartoteki (gotowe, z okna dopasowania) → zapis relacji; (2) kalkulator
czyta relację; (3) agregacja do ZK; (4) widoczność w arkuszu. Kolumny
„Półfabrykat" i wiersza-dziecka NIE dokładać od razu — arkusz ma 67 kolumn
i tksheet już przy nich niedomaga.

**Stan: rozpisane, NIEZAIMPLEMENTOWANE.** Patrz [[project_subiekt_zk_komplety]],
[[project_mapowania_subiekta_stan_14_09]].

## Stan 14.09.2026 wieczorem

Plan spisany w repo: **`POLPRODUKTY_PLAN.md`** (346 linii, commit `36772d0`,
wypchnięty na origin/main). Implementacja: **w domu**, wg kolejności z planu
(relacja → PPM → kalkulator → ZK → znacznik 🛒 w Δ).

Domknięte decyzje użytkownika z tej rozmowy (są w planie, ale warto mieć
je i tutaj): ZERO nowych kolumn — znacznik 🛒 w istniejącej komórce Δ obok
`●` dla ręcznych (wzorzec `delta_disp` z `RM_BAZA:8193-8212`);
`ilosc_na_szt` CAŁKOWITA („sztuka to sztuka, nic nie dzielimy");
kartoteka półproduktu nie znika (zwykłe TW) — żadnych ostrzeżeń, jedyny
przypadek to scalenie duplikatów, przepinane jak `mapowania`.
