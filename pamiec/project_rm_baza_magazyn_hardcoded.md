---
name: project_rm_baza_magazyn_hardcoded
description: RM_BAZA ma "MAG" na sztywno ale TYLKO w zapisach - odczyt stanow dziala na wszystkich magazynach
metadata:
  type: project
---

`MAGAZYN = "MAG"` w `subiekt_magazyn_gui.py:50`. **Ale dotyczy wylacznie
ZAPISOW** - to wazne rozroznienie, ktore latwo pomylic:

| funkcja | uzywa MAG? | skutek po migracji na magazyn nr 2 |
|---|---|---|
| odczyt stanow (`pobierz_magazyn`, linia ~100) | **NIE** | ✅ dziala - tryb `magazyn` SUMUJE wszystkie magazyny, wiec okno pokazuje dane z "Magazyn" |
| zapis progow (linia ~118) | TAK, `--magazyn={MAGAZYN}` | ⚠️ progi ida na pusty MAG |
| tworzenie RW (linia ~134) | TAK, `magazyn=MAGAZYN` domyslnie | ⚠️ RW zdejmuje z MAG |

Drugie miejsce: `subiekt_sfera/NexoRecon/Zd.cs:219` ->
`.FirstOrDefault(m => m.Symbol == "MAG")` - domyslny magazyn ZD gdy dokument
go nie wskazuje.

**Wniosek:** po uruchomieniu magazynu nr 2 przegladanie stanow w RM_BAZA
dziala poprawnie od reki. Do poprawy sa tylko sciezki zapisu (progi, RW, ZD).

**NIE MYLIC** z `UWAGI_MAGAZYN = "MAGAZYN"` (linia 53 i subiekt_dokumenty_gui.py:154)
- to znacznik tekstowy w Uwagach dokumentow, nie symbol magazynu.

Patrz [[project_magazyn_nr2_migracja]].
