---
name: feedback_bez_hookow_vba
description: ⛔ Żadnych hooków Windows (SetWindowsHookEx / AddressOf-callbacków) w makrach VBA Inventora — 28.09.2026 zawiesiły całą klawiaturę i mysz komputera
metadata:
  type: feedback
---

⛔ W makrach Inventora (VBA) NIE używać hooków Windows — `SetWindowsHookEx`,
callbacków przez `AddressOf`, subclassingu okien.

**Why:** 28.09.2026 kółko myszy w oknie MAG robione hookiem `WH_MOUSE`
(Inventor 2013, VBA 6 w procesie `Inventor32bitHost.exe`) zawiesiło CAŁY
komputer użytkownika: klawiatura i mysz przestały reagować, musiał się
wylogować przyciskiem na obudowie. Stracił otwartą pracę.

**How to apply:**
- Kółko myszy w oknie VBA robi się BEZ hooka: lista jako kontrolka
  WebBrowser (Shell.Explorer.2) przewija się kółkiem natywnie — tak działa
  MAG od 28.09.2026 ([[project_mag_okno_przegladarka]]). Czyste MSForms:
  tylko pasek przewijania.
- Kod, który może zawiesić system, NIE jest uruchamiany na maszynie usera
  „do sprawdzenia" — najpierw pytanie, czy w ogóle go chce, z jasnym ryzykiem.
- Deklaracje API w VBA: jedna linia na `Declare` (łamanie ` _` w gałęzi
  `#If VBA7`, nieaktywnej w VBA 6, dopisywało na końcu modułu śmieć `()`).

Powiązane: [[feedback_makra_ivb_nazwa_mag]]
