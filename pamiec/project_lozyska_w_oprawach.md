---
name: project_lozyska_w_oprawach
description: Łożyska w oprawach (UCP/UCF/UCFL/UCPA/BPFT) z matis.sk → 55 modeli w B:\Znormalizowane\Łożyska w oprawach (29.09.2026); import STEP wywracał Inventora usera — każdy plik w osobnym ukrytym Inventorze
metadata:
  type: project
---

**Źródło:** https://www.matis.sk/sk/info/cad (link od usera) — katalog
`Strojní_součásti/Ložisková_tělesa`, oprawy ISB/ASKUBAL, BEZPOŚREDNIE linki
bez logowania (88 plików, 72 MB, pobrane z przerwą 1 s do `_STEP_matis\`).
Portale (TraceParts, PARTcommunity) odpadły: klikanie + blokady po kilku
pobraniach; API TraceParts tylko dla partnerów.

**Wynik:** `katalog_opraw/konwertuj_matis.py --zapisz` → 55 modeli:
UCP 202–218 (bez 217), UCF 202–218 (bez 216), UCFL 202–211+214, UCPA 202–210,
BPFT 202–204. Część = `<SYM>.ipt`, złożenie = `<SYM>\<SYM>.iam` + części.
PN = Title = symbol. Biały render + natywna miniatura. Zasiew:
`indeks_oringi_zasiew.py --katalog "B:\Znormalizowane\Łożyska w oprawach"
--lista lozyska_oprawy_modele.csv --zapisz` (zrobione na serwerze DOMOWYM).
BPP/BPF/BPFL (blaszane, numery 6252…/6264…/6265…) pominięte — brak symboli.

⛔ **Import STEP w sesji usera WYWRACAŁ Inventora 2013** (RPC niedostępny po
kilku plikach, 29.09.2026 — user stracił sesję). Teraz: każdy plik w
OSOBNYM ukrytym Inventorze (`DispatchEx`, czekać na `app.Ready`, Quit po
pliku, taskkill tylko własnego PID, druga próba). `SilentOperation = True`,
bo import pokazuje okno „Import danych wymiany". Import zostawia raporty
`<nazwa>.htm` w `OneDrive\Dokumenty\Inventor` — sprzątane.
Wkładka bywa PODZŁOŻENIEM (`UC203_ASM.iam`) — zapis wszystkich poziomów
(AllReferencedDocuments, części przed złożeniami, właściwe rozszerzenia).

**Natywne miniatury:** dokument otwarty niewidocznie nie ma widoku →
brak miniatury w pliku. `SetThumbnailSaveOption(kImportFromFile=79877,
render.png)` + `Save` (PNG i BMP działają) — `katalog_opraw/miniatury_w_plikach.py`.

**Brakuje na Matis:** UCFC, UCFB, UCT, rozmiar 201, UCFL 212+, UCPA 211–212.
Istniejąca biblioteka `B:\Znormalizowane\Łożyska wahliwe\<TYP>\<TYP 20x>\`
(UCP/UCF/UCFL/UCPA/UCFC/UCT 201–206, .iam z 2017–2019) — NIE przypisana w MAG.
W projektach (C:\Projekty / V:) skan po nazwach znalazł 53 symbole, m.in.
UCFC 207–210, UCT 212, UCFL 212, UCPA 207–212, UCFB 203/205 — do zebrania
skryptem skanującym w firmie (propozycja, nie zrobione).

Powiązane: [[project_oringi_wymiarowka]], [[feedback_biblioteka_pytaj_przed_hurtem]],
[[project_mag_wstaw_i_przypisz]].
