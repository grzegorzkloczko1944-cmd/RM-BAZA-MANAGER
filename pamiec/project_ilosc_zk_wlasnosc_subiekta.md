---
name: project_ilosc_zk_wlasnosc_subiekta
description: Po zasiewie ilością na ZK rządzi Subiekt — Projekt/Aktualizacja bierze ilość pozycji z ZK, nie z BOM (sklejenie dubletów NIE podnosi ZK); gdzie user może zmieniać ilości; decyzja 02.10.2026: bez automatu BOM→ZK
metadata:
  type: project
---

**Zasada (potwierdzona 02.10.2026, user: „nie wiem czy jest sens robić aż tak skomplikowane funkcje"):** po zasiewie właścicielem ilości na ZK jest Subiekt. `build_plan(..., bazowe_ilosci=)` — pozycja obecna na ZK startuje z ilością **z dokumentu**; precedencja BOM < ZK < ręczna edycja w oknie. Zmiana BOM (np. sklejenie dwóch wierszy „6004" po 4 → BOM 8) **nie podnosi ZK** — user tego oczekiwał i był zaskoczony.

**Gdzie zmienia się ilość na ZK:**
1. W Subiekcie wprost — RM_BAZA pobierze przy przejęciu locka (`_zapisz_ilosci_z_subiekta` → „Ilość (zam.)").
2. Projekt/Aktualizacja — dwuklik „Ilość": korzeń drzewa (przelicza poddrzewo), pozycja spoza drzewa (pojedynczo); składnik w drzewie — odmowa.
3. Przegląd dokumentów — dwuklik „Ilość" pozycji ZK (od 02.10.2026, [[project_przeglad_dokumentow_edycja_zk]]).
W arkuszu „Ilość (zam.)" po zasiewie zablokowana.

**⛔ Nie zerować** pozycji na ZK zamiast usuwać — zero wraca do arkusza i pozycja wypada z BOM-u.

**Odrzucone warianty (nie proponować bez prośby):** pełny automat BOM→ZK (dwa źródła prawdy, nadpisywałby zmiany z Subiekta); lista „BOM ≠ ZK" w oknie (rzadki przypadek — wystarczy banner dubletów + ręczna poprawka).

**Sklejanie dubletów:** „SUBIEKT → Dopasowanie kartotek → 🔗 Sklej duplikaty" (grupuje po identycznym `subiekt_symbol`) pokazuje od 02.10.2026 **czerwone okno** dla pozycji zasianych: „BOM po sklejeniu X / na ZK Y — popraw ZK ręcznie w Subiekcie". Fałszywy tekst „Ilość na ZK poprawi się przy najbliższym zapisie" usunięty. ⚠️ „Scal kody handlowe" to INNE okno — warianty pisowni (KOŁO/Koło) traktuje jako jeden kod i ujednolica NAZWĘ, nie łączy wierszy.

**Banner dubletów** (`check_and_show_duplicates`): od 02.10.2026 klucz = numer rysunku → `subiekt_symbol` → nazwa, NOCASE, bez ukrytych. Wcześniej tylko numery — znormalia bez numeru (2× „6004") nie świeciły („działało, a nie działa").

Powiązane: [[project_jedno_zrodlo_prawdy_ilosci]], [[project_zk_ilosci_nie_porownywane]], [[project_sklejanie_duplikatow_bom]], [[project_edycja_ilosci_w_oknie]], [[project_powiazania_kolizja_ilosci]].
