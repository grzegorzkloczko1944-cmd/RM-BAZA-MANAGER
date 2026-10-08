---
name: project_tuleje_zaciskowe_bk
description: Tuleje zaciskowe BK/RCK (202 STEP) → IPT w do_SUBIEKT-MAG (08.10.2026, dom, Inventor 2013); Subiekt i MAG jeszcze NIE ruszone
metadata:
  type: project
---

**Co:** `G:\Mój dysk\SUBIEKT\Tuleje zaciskowe BK\<seria>\*.stp` (BK13/15/26/80/95, RCK40/55/60 = 202 pliki)
skonwertowane STEP → IPT w ukrytym, osobnym Inventorze 2013 do
`G:\Mój dysk\SUBIEKT\Tuleje zaciskowe BK\do_SUBIEKT-MAG\` (`<SYMBOL>\<SYMBOL>.ipt`, `miniatury\<SYMBOL>.png` 600×600,
`tuleje_modele.csv`, `README.md` z pełnym opisem).

**Decyzje usera (08.10.2026):** symbol = `BK13 100x145` (seria spacja d×D, nie `RCK13-22/47`); Description „Tuleja zaciskowa";
materiał „Stal" (ustawiony jak w IAM_MACRO_Y: `Materials.Item("Stal")` → `ComponentDefinition.Material` + iProperty Material);
obrazki PNG w UKRYTYM Inventorze (kamera przejściowa `CreateCamera`, `SceneObject = cd`, bez natywnej miniatury w pliku).

**Stan Subiekta:** tylko 12 kartotek RCK (`RCK13-22/47`, `RCK61-…`, `RCK80_…`, opis „Pierścień zaciskowy", R8/P3) — inne symbole,
niezmapowane. Zero kartotek `BK…`.

**Not done / dalej:** zakładanie lub mapowanie kartotek, Opis, Położenie, zdjęcia, zasiew MAG
(`indeks_oringi_zasiew.py --katalog … --lista tuleje_modele.csv`, najpierw bez `--zapisz`) — dopiero na polecenie.

**Pułapki:** dynamiczny obiekt z `Documents.Open` w pywin32 nie ma `ActiveMaterial` — użyj `ComponentDefinition.Material`
i `Materials` dokumentu; start nowego Inventora bywa nieudany („Wykonanie serwera nie powiodło się”) — ponów.
Skrypt seryjny: wzorzec `biblioteka_modeli\wzorce_kodu\konwertuj_stp.py` rozszerzony o pętlę, 3 próby na pozycję.
Powiązane: [[project_mag_wstaw_i_przypisz]], [[feedback_biblioteka_pytaj_przed_hurtem]].

**Aktualizacja 08.10.2026 wieczór (firma, wg wpisów w G:\Mój dysk\KODY\COWORK_WSPOLNE\FIRMA_do_DOMU.md):**
Subiekt i MAG ZROBIONE: kopia modeli na `B:\Znormalizowane\Tuleje zaciskowe\` (natywne miniatury, pliki w formacie 2015), 200 nowych kartotek
(Opis „Tuleja zaciskowa", Położenie R8/P3, zdjęcia z PNG), 2 istniejące RCK55 tylko ze zdjęciem i modelem, 202 przypisania MAG, ocena „Rekomendowane" (autor ADMIN).
Dodatkowo 19 nowych STEP (BK25 ×14 = Sati KLFC, BK80 ×5) skonwertowane w firmie; usunięte warianty `BK15 …_F10` (3 szt., prawie duble); razem 216 kartotek tulei.
Kopia na G: `do_SUBIEKT-MAG` = stan domowy (202 szt., Inventor 2013, z F10, bez 19 nowych). Otwarte: 39 modeli z gabarytem > D (BK26 7, BK80 27, RCK55 5)
mają Rekomendowane — user przejrzy sam w firmie. Obieg dom↔firma: skrzynka `G:\Mój dysk\KODY\COWORK_WSPOLNE\` (`ZASADY.md`, `STAN.md`).
