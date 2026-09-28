---
name: reference_matis_cad
description: matis.sk/sk/info/cad — darmowe modele CAD (STEP/IGES/DXF) bez logowania i blokad; oprawy łożysk UC*, prowadnice, tuleje, przekładnie; format linków i jak pobierać
metadata:
  type: reference
---

**Adres:** https://www.matis.sk/sk/info/cad (podał user 29.09.2026)

Jedna strona HTML (~1,2 MB) z ~10 400 linkami do plików — BEZ logowania,
BEZ blokad po kilku pobraniach (w przeciwieństwie do TraceParts /
PARTcommunity). Link: `https://www.matis.sk/data/CAD_modely/<kategoria>/<podkat>/<plik>`
— polskie/czeskie znaki w ścieżce trzeba zakodować (`urllib.parse.quote`).

**Co tam jest (wybór):**
* `Strojní_součásti/Ložisková_tělesa/` — oprawy łożysk ISB/ASKUBAL:
  UCP, UCF, UCFL, UCPA, BPFT (STEP, część jako `*_asm.stp` = złożenie
  oprawa+wkładka) + blaszane BPP/BPF/BPFL (numery 6252…/6264…/6265…) i PDF-y.
  **Brak:** UCFC, UCFB, UCT, rozmiar 201.
* `Strojní_součásti/` — też Volnoběžky (sprzęgła jednokierunkowe),
  Svěrná_pouzdra (tuleje zaciskowe), Spojky (sprzęgła).
* `01_Pouzdra/` — tuleje liniowe (KH, LME, SDE, LMEF…), `05_Kolejnicova_vedeni/`
  — prowadnice (HG, MG, EG, RG), `10_Kulickove_srouby/` — śruby kulowe,
  przekładnie kątowe/ślimakowe, moduły liniowe.
* Formaty: `.stp`, `.igs`, `.dxf`, `.dwg`, część jako `.zip` / `.exe`
  (samorozpakowujące).

**Jak pobierać:** `curl -A "Mozilla/5.0"` strony → regex `href="[^"]*CAD_modely[^"]*"`
→ `html.unescape` → filtr po kategorii → pobieranie z przerwą ~1 s
(88 plików = 72 MB bez żadnego błędu). Konwersja STEP → Inventor:
`katalog_opraw/konwertuj_matis.py` — WYŁĄCZNIE w osobnym ukrytym Inventorze,
patrz [[project_lozyska_w_oprawach]].
