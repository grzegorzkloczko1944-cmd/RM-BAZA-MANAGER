---
name: reference_dokumentacja_sfery
description: "Dokumentacja Sfery Subiekt nexo PRO - lokalnie na dysku, przeszukiwalny indeks TSV"
metadata: 
  node_type: memory
  type: reference
  originSessionId: bd77b2db-aa7d-4871-a44f-b0388f221230
  modified: 2026-09-09T21:22:43.142Z
---

Dokumentacja API Sfery leży lokalnie: `C:\iLogic\Subiekt_nexo_PRO_dokumentacja\`

* `CHM\sfera_index.tsv` — **indeks 81984 wpisów**, `nazwa TAB html/XXXX.htm`. Grep po nim to najszybsza droga do znalezienia klasy/metody.
* `CHM\sfera\html\` — 50121 rozpakowanych stron HTML. UWAGA: to NIE jest komplet, część stron z indeksu nie ma pliku (np. `Cena Properties`).
* `SDK\InsERT.nexo.Sfera.chm` — pełny CHM, gdy w rozpakowanych brakuje.
* `SDK\Bin\` — biblioteki Sfery (ta sama ścieżka co `sdkBin` w `.nexo_sfera.json`).

Czytanie stron: HTML z BOM, wyjście przez `PYTHONIOENCODING=utf-8`, inaczej leci UnicodeEncodeError na cp1250.

**How to apply:** przy pracy z API Sfery szukać NAJPIERW w `sfera_index.tsv`, zamiast diagnozować przez refleksję na żywym obiekcie. Refleksja zostaje jako uzupełnienie — dokumentacja mówi, co klasa deklaruje, ale nie zawsze co realnie wystawia proxy Sfery.

Sprawdzone 2026-09-09 przy [[project_cena_na_pozycji_pw]]: dokumentacja pokazała `ICena.UstawCene`, ale opis („ceny zgodnie z wybranym poziomem cen") ujawnił, że to metoda cennikowa i do wpisania własnej ceny się NIE nadaje — sama refleksja by tego nie powiedziała.
