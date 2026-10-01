---
name: project_okna_pokazane_zbudowane
description: Okna Subiekta/KSeF pokazywane dopiero zbudowane (ukryj_do_zbudowania w subiekt_stany), panel SUBIEKT na środku MONITORA; pułapki Tk/Windows zmierzone WinAPI 01.10.2026 — state("zoomed") mapuje withdrawn okno, losowy flash restore ~0,3 s, Tk poprawia pozycję po 1. mapowaniu
metadata:
  type: project
---

01.10.2026. User: „okna budują się na oczach”, „panel SUBIEKT raz na środku, raz z boku i zaraz się przestawia”.

**Rozwiązanie:** `subiekt_stany.ukryj_do_zbudowania(self)` wołane zaraz po `super().__init__()` we WSZYSTKICH 26 oknach `subiekt_*`/`ksef*` (Toplevel). Panel: `wysrodkuj_na_monitorze` (środek monitora z rodzicem, WinAPI `MonitorFromWindow`) zamiast `wysrodkuj` (środek rodzica — user ma RM_BAZA zmniejszoną i przesuniętą; dialogi w oknach dalej na rodzicu). Kafle panelu mają od razu zarezerwowaną szerokość licznika (`SZEROKOSC_LICZNIKA`), bo liczniki poszerzały okno po kolei.

**Pułapki (ZMIERZONE dziennikiem WinAPI w prawdziwej RM_BAZA, nie na oko):**
- `withdraw()` NIE wystarcza: `state("zoomed")` w `__init__` okna znowu je mapuje → cała budowa widoczna. Trzeba `-alpha 0` PRZED tym.
- Okno zmaksymalizowane: ~0,3 s po pokazaniu Tk/Windows **losowo** (co 2–3 otwarcie) przywraca je na chwilę do zwykłego rozmiaru i z powrotem maksymalizuje. Nie zależy od kolejności geometry/zoomed (sprawdzone 12 wariantów czystego Tk). Jedyne pewne: odsłonić, gdy ramka stoi nieruchomo ≥250 ms i ≥400 ms od pokazania.
- Okno zwykłe: Tk poprawia pozycję dopiero po 1. zmapowaniu (uczy się ramki) → skok o kilkadziesiąt px. Fix: po pokazaniu jeszcze raz `geometry(+x+y)` z `okno._rm_pozycja` (ustawia `wysrodkuj*`).
- `-alpha 0` + odczyt `okno.geometry()` na jeszcze niezmapowanym oknie przestawiało je do (0,0) — nie czytać geometry przed mapowaniem.
- Pokazywać `after(1)`, NIE `after_idle` — idle wykonuje się w `update_idletasks()` w trakcie budowy.
- Proces nie jest DPI-aware → WinAPI i Tk zgadzają się we współrzędnych (można mieszać).

**PRÓBOWANE I NIE DZIAŁA:** sama przezroczystość bez withdraw (okno lądowało w (0,0)); `withdraw`+`deiconify` dla zoomed (zdejmuje maksymalizację); odsłanianie po stałym czasie 120 ms (flash przychodził później).

Diagnostyka na przyszłość: hook na `tk.Wm.wm_geometry/wm_state/...` z `traceback.extract_stack` + próbkowanie `GetWindowRect` co 20 ms (wzorzec był w scratchpadzie sesji, łatwo odtworzyć).

Powiązane: [[project_okna_trzy_monitory]], [[project_zrzut_ekranu_dpi]], [[project_zapotrzebowanie_szybkie]].
