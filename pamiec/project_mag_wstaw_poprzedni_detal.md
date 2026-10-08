---
name: project_mag_wstaw_poprzedni_detal
description: BŁĄD MAG do poprawy (zgłoszony 08.10.2026, „nie dzisiaj”) — po wstawieniu detalu pierwszy klik na drugim detalu wstawia znowu PIERWSZY; drugi dopiero po dwóch kliknięciach
metadata:
  type: project
---

Zgłoszenie usera 08.10.2026 (do zrobienia w kolejnej sesji, nie od razu):

> Gdy wstawiam detal, potem drugi, to pierwszym klikiem, gdy wybiorę drugi detal, wstawia mi
> pierwszy. Dopiero dwa kliknięcia na drugim detalu robią drop drugiego detalu do Inventora.

**Odtworzenie:** okno MAG → wstaw detal A (dwuklik / „Wstaw do złożenia”) → wybierz detal B →
klik wstawia **A** ponownie; dopiero kolejne kliknięcie(a) na B wstawia B.

**Gdzie szukać (hipotezy, niesprawdzone):** wstawianie to „Umieść komponent” przez VBS
(etap 4, [[project_mag_wstaw_i_przypisz]]) — podejrzane: ścieżka pliku do wstawienia trzymana
po stronie VBS / pliku pośredniego z poprzedniego wstawienia (odczyt przed nadpisaniem), albo
komenda Inventora „Place Component” wciąż aktywna z modelem A na kursorze, a klik w oknie MAG
tylko ją kończy. Pliki: `NOW/MAKRA/MAG_zrodla/czesci/okno.hta` (`wstawZaznaczony`,
`wstawKartoteke`, blok VBS) i `czesci/modul.vba`.

**Jak sprawdzić bez Inventora usera:** zakaz testów w sesji usera (skill Inventora, zakaz nr 6) —
odtworzyć na testowym Inventorze albo poprosić usera o kroki z obserwacją, co jest na kursorze.
