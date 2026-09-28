---
name: project_mag_wstaw_i_przypisz
description: MAG etap 4 (29.09.2026) — wstawianie modelu dwuklikiem przez „Umieść komponent" i ręczne przypisanie modelu 3D do kartoteki; HTA woła Inventora przez VBS, bo IE11 nie ma GetObject/VBScript
metadata:
  type: project
---

**Wstawianie (etap 4 PLAN_MAG):** dwuklik w wierszu MAG albo „Wstaw do
złożenia" → Inventor uruchamia zwykłe **Umieść komponent** z plikiem modelu
(model na kursorze, klik = wstaw, Esc = koniec). Kilka modeli → wybór
w pasku. Aktywny dokument nie-.iam → odmowa z komunikatem.
Prawdziwe przeciąganie (D&D) ODRZUCONE: okno VBA/HTA nie da Inventorowi
pliku jak Eksplorator (CF_HDROP), obejście = hooki → [[feedback_bez_hookow_vba]].

**Ręczne przypisanie:** „Przypisz 3D…" → zaznaczony komponent w Inventorze
(bez zaznaczenia: otwarty model) albo z pliku → pytanie z pełną ścieżką
i uwagami (ścieżka lokalna, OldVersions) → `POST /mag/model3d/przypisz`
→ wiersz `zrodlo='reczny'` w `modele_3d` + od razu zlecenie indeksu 3D
(miniatura). „usuń" przy ręcznych w panelu → `POST /mag/model3d/usun`
(automatycznych NIE usuwa). Przy przypisaniu znika automatyczny wpis
„bez modelu" (pusta ścieżka) — indeks pomija symbole z wpisem ręcznym.
Serwer: `C:\BibliotekaRM\` → `B:\` jak w indeksie.

**Jak HTA woła Inventora:** tryb IE11 (edge) NIE MA `GetObject` ani VBScript
(sprawdzone testowym HTA; `typeof ActiveXObject` = "undefined", ale
`new ActiveXObject` działa). Dlatego blok `<script type="text/plain"
id="vbsInventor">` → `%TEMP%\RM_MAG\MAG_inventor.vbs` (UTF-16) → ukryty
`wscript` → wynik w pliku, „!" = błąd. W VBScript `On Error Resume Next`
działa TYLKO w procedurze, w której stoi — każda Sub/Function ma własne.
Stałe z `RxInventor.tlb` (nie zgadywać!): **kFileNameEvent = 6657**,
kAssemblyDocumentObject 12291, kPartDocumentObject 12290,
kComponentOccurrence(Proxy)Object 67113776 / 67113888.

**Stan 29.09.2026:** serwer przetestowany na testowym (przypisz/2x/zły
plik/usuń/automatu nie usuwa); VBS „wskazany" sprawdzony na żywym
Inventorze 2013; „wstaw" NIE testowany automatycznie (wstawiłby komponent
w złożenie usera) — test ręczny u usera. Firma: wdrożyć `rm_serwer_operacje.py`
i `rm_mag_http.py` na W2019S (restart za zgodą) + nowy MAG.vba.

Zobacz też: [[project_mag_vba7_lista_zapasowa]], [[project_mag_indeks3d_zlecenie]],
[[project_lozyska_katalog_28_09]], [[feedback_nic_po_cichu]].
