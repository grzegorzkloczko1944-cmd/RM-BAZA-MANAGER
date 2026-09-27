---
name: project_indeks_modeli_3d
description: Etap 1 makra Inventor↔Subiekt — indeks_modeli_3d.py + tabela modele_3d; skanować TYLKO na stacji firmowej (M-OLD ma Inventor 2013), C:\BibliotekaRM = B:
metadata:
  type: project
---

# Indeks „numer rysunku → model 3D" (etap 1 makra „Wstaw z magazynu")

Napisany 27.09.2026: `indeks_modeli_3d.py` + tabela `modele_3d`
w `subiekt_mapowania.sqlite` (operacje `map-model3d-*`, koniec
`rm_serwer_operacje.py`). Szczegóły: `PLAN_MAKRO_MAGAZYN_3D.md`, sekcja 6a.

Sprawdzony na serwerze testowym (port 5099, bazy w scratchpadzie), NIE na
produkcji. Serwer na W2019S nie zna jeszcze tych operacji.

## ⛔ Pułapki

**M-OLD ma Inventor 2013.** ApprenticeServer 2013 nie otwiera IDW zapisanych
nowszym Inventorem (firma: 2015) — `Open` rzuca goły `com_error -2147467259`
bez opisu. W `Czujniki RM` 33 z 61 plików. To NIE uszkodzone pliki. Pełny
skan tylko na stacji firmowej.

**IDW pamiętają ścieżkę autora `C:\BibliotekaRM\…`.** Gdzie taki katalog
istnieje lokalnie (M-OLD: `B:` = `\\M-OLD\BibliotekaRM` = `C:\BibliotekaRM`),
Apprentice rozwiązuje referencję na `C:`, nie na `B:`. Skaner przepisuje
jawnie (`TEN_SAM_KATALOG`), gdy plik na `B:` istnieje. `C:\Biblioteka`
(bez „RM") to INNY katalog — nie dopisywać go do mapy.

## Decyzje

* bez modelu = wiersz z `sciezka = ''`; model spoza `B:` też tak;
* `zrodlo` `idw`/`reczny`, ręczne nietykalne (reguła w SQL);
* `part_number` modelu tylko jako kontrola;
* 203 numery w dwóch miejscach na `B:` — wygrywa nowszy IDW.

Powiązane: [[project_znormalia_model_3d_z_zlozen]], [[project_srodowisko_domowe_m_old]]
