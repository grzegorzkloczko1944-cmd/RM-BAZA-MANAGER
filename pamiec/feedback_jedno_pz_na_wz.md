---
name: feedback_jedno_pz_na_wz
description: "ŻELAZNA ZASADA: jedna WZ-tka dostawcy = jedno PZ w Subiekcie. Nigdy nie łączyć pozycji z różnych WZ w jednym przyjęciu"
metadata:
  node_type: memory
  type: feedback
---

Polecenie uzytkownika (18.09.2026), okreslone jako **ZELAZNA ZASADA**:

> **robimy osobne PZ na kazda WZ**

**Why:** PZ w Subiekcie ma JEDNO pole `NumerZewnetrzny`. Gdy do jednego
przyjecia wrzucic pozycje z dwoch WZ-tek, na dokumencie zostaje tylko jeden
numer — drugi przepada i faktury nie da sie rozliczyc co do pozycji.
Dostawca wystawia wiele WZ-tek i fakturuje je zbiorczo (QUAY `RVQ/05195/26`:
55 pozycji = 11 roznych WZ), a TEN SAM produkt potrafi przyjsc na dwoch.
Przy zasadzie 1 WZ = 1 PZ numer zewnetrzny jest kluczem JEDNOZNACZNYM:
pozycja faktury z `Numer wydania = WZ/01676/26` trafia dokladnie w jedno PZ.

**How to apply:**
- Okno przyjecia dostawy (`subiekt_dostawa_gui.py`) ma NIE POZWALAC przyjac
  jednym dokumentem pozycji z roznych WZ — to blokada, nie ostrzezenie.
- Magazynier przyjmuje paczke po paczce: kazda WZ-tka osobno, wlasne PZ.
- Przy rozliczaniu faktury z PZ ([[project_rozliczanie_faktury_z_pz_plan]])
  mozna dzieki temu isc wprost po `NumerZewnetrzny` — bez zgadywania,
  ktora pozycja z ktorego wydania.
- ⚠️ Pozycje SPOZA ZD (dostawca dolozyl cos ekstra) tez naleza do konkretnej
  WZ-tki — obowiazuje ich ta sama zasada.

Patrz [[project_przyjecie_dostawy_pz]], [[project_obieg_przyjec_dostawa_pz]].
