---
name: project-subiekt-zk-komplety
description: Zakładanie projektu w Subiekcie z RM_BAZA — ZK + komplety Z/ZZ; działa na produkcji od 03.09.2026; okno subiekt_projekt.py
metadata: 
  node_type: memory
  type: project
  originSessionId: 1dd1921c-6641-454c-ba67-89c078f07993
  modified: 2026-09-03T18:21:12.605Z
---

**Działa na żywej bazie produkcyjnej od 03.09.2026** — pierwsze realne ZK
(`ZK 1/09/2026`, projekt 2619 CERAMIZATOR Etykieciarka) powstało z pełnym
drzewem kompletów. To pierwszy zapis RM_BAZA → Subiekt w ogóle.

**Wejście:** menu `📦 SUBIEKT ▾` → „🏗 Załóż projekt w Subiekcie".
Pliki: `subiekt_projekt.py` (okno), `subiekt_mapowania.py` (tabela mapowań
na `Y:\RM_BAZA\subiekt_mapowania.sqlite`), `subiekt_sfera/NexoRecon/Projekt.cs`
(tryb `projekt`, jedyne miejsce zapisujące do Subiekta, wymaga `--zapisz`).

**Rozstrzygnięcia (nie otwierać ponownie bez powodu):**
- **Projekt = ZK**, nie osobna encja — Subiekt nie ma pojęcia „projekt".
  Tytuł ZK = pełna nazwa („2619 CERAMIZATOR Etykieciarka"), Uwagi = sam
  numer („2619"), bo firma po Uwagach filtruje (F8).
- **Komplety tylko dla `Z`/`ZZ`**; `X`/`XX` to pojedyncze blachy → zwykłe
  kartoteki. Pytanie „czy X/XX jako komplety" padało dwa razy — odpowiedź nie.
- **Kartoteki NIE dla całego BOM domyślnie.** Okno ma trzy tryby
  (`komplety + składniki` domyślny / `wszystko` / `nic`) i kolumnę ✓ do
  klikania per pozycja. Dla 2619: 158 kartotek zamiast 198, wciąż 19 pełnych
  kompletów. Powód: kartotek nie da się łatwo usunąć, ZK owszem.

**Pułapki wyłapane w praktyce:**
- Kolumny `*_over` (`name_over`, `order_qty_over`) to **flagi 0/1**, nie
  wartości → dawały nazwę „0" i **ilość 0 na ZK**. Kanoniczne:
  `COALESCE(order_qty, work_qty, src_qty)`. Ten sam bug był w `subiekt_stany.py`.
- **`ZZ` zawiera `ZZ`** (23 razy w „2607 Platyn", drzewo na 4 poziomy, firma
  mówi o 6). Nazewnictwo NIE opisuje poziomu → kolejność zapisu kompletów musi
  być **sortowaniem topologicznym**, nie „Z przed ZZ"; rekurencja pilnuje cyklu,
  nie stałej głębokości.
- Drzewo złożeń (skład kompletów) jest **tylko w arkuszu „DRZEWKO TEKST"**
  w `*_OUT.xlsx` — w sqlite projektu nie ma żadnej kolumny hierarchii.
  Projekty leżą na **V:**, nie Y: (konfig wskazywał nieistniejące `Y:/SERVER_PROJEKTY`).
- Zapis w trybie „nic" daje ZK tylko z pozycji, które już miały kartotekę
  (dla 2619 było ich 6 z 204) — łatwo pomylić z błędem.

**How to apply:** przed zmianami czytać `SUBIEKT_PROJEKTY_WYDANIA.md` sekcje
5 i 7. Zapis idzie na produkcję — zawsze suchy przebieg najpierw, log kroków
w `C:\RMPAK_CLIENT\subiekt_logi\`. Powiązane: [[project-subiekt-nexo-sfera]].
