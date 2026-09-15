---
name: project_subiekt_scalanie_kartotek
description: "Scalanie duplikatów kartotek Subiekta (edytor, panel 5 + tryb `scal` mostu): symbole nietykalne, cel wygrywa, źródła wycofywane znacznikiem, aliasy w subiekt_mapowania; Sfera NIE MA flagi 'nieaktywna' na asortymencie"
metadata: 
  node_type: memory
  type: project
  originSessionId: b4b4fbd4-107b-4ece-9328-8ca8b8a060fc
  modified: 2026-09-10T13:55:46.245Z
---

Scalanie zduplikowanych kartotek (10.09.2026): edytor kartotek → panel
**„5. Scalanie pozycji"** (pod panelem 2) + tryb mostu **`scal`**
(`subiekt_sfera/NexoRecon/Scal.cs`). Zasady ustalone przez użytkownika:

- **Symbol jest kluczem** — scalanie NIE zmienia symboli i NIE zakłada nowej
  kartoteki. Kartoteka docelowa zostaje 1:1 (nazwa, cena, VAT, JM, opis,
  położenie). Różnice źródło↔cel są tylko RAPORTOWANE.
- Użycie źródeł w kompletach jest przepinane na cel (`SkladnikiWKompletach`
  z SDK); gdy cel już siedzi w tym komplecie — **ilości się sumują**.
- Źródła NIE są kasowane (historia dokumentów): dostają w `Opis` i `Uwagi`
  znacznik `SCALONO DO: <cel>`. **Sfera nie ma na Asortymencie flagi
  nieaktywna/wycofana** — sprawdzone w `InsERT.Moria.ModelDanych.xml`
  (jest `Przeceniony`, `IsInRecycleBin`, `FlagaWlasna`, ale nic o wycofaniu).
- Blokady: tylko Towar→Towar / Usługa→Usługa; **komplety odrzucane**
  (scalanie kompletów = osobny etap, decyzja o obu składach).
- Zawsze najpierw „Sprawdź scalanie" (suchy przebieg) → raport → „Wykonaj".
  Zmiana listy unieważnia raport.

**Why:** duplikaty elementów znormalizowanych (`DN10 K=34` / `1DN10 K=34` /
`DN10 K=50,5` — jedna uszczelka, trzy kartoteki) rozbijają historię cen
i stany; „usuń A, zostaw B" rozspójniłoby dokumenty.

**How to apply:**
- Most: odmowa (komplet, brak kartoteki, różne rodzaje) to RAPORT z
  `ok=false` i kodem wyjścia **0** — kod ≠ 0 rzuca `BridgeError` po stronie
  Pythona i user nie widzi powodu. Ta sama zasada dla nowych trybów.
- Strona RM_BAZA po udanym zapisie: `subiekt_mapowania.zapisz_scalenie()` —
  tabela `aliasy_scalen`, przepięcie `mapowania.symbol_subiekt` stary→cel
  ORAZ wpis `mapowania[numer=stary_symbol] → cel` (`sposob=scalona`), dzięki
  czemu etap 3 ([[project_subiekt_puste_zlozenia_decyzje]]) rozpoznaje stary
  kod z BOM-u bez zmian w `subiekt_dopasowanie`.
- `Skladniki.Usun/Dodaj` wymagają encji o typie STATYCZNYM (`Asortyment`,
  nie `dynamic`) — inaczej binder nie trafia w przeciążenie (pułapka
  z KartotekaEdytuj.cs).
- Przetestowane na żywo suchym przebiegiem: `2621-860.00Z` zawierał oba
  symbole → raport „x1 + x1 → x2 (SUMA)". Zapis z `--zapisz` NIE był jeszcze
  wykonany na produkcji.
