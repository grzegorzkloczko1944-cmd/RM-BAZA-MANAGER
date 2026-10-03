---
name: project_okna_pokazane_zbudowane
description: Okna Subiekta/KSeF pokazywane dopiero zbudowane i NA MIEJSCU (ukryj_do_zbudowania pilnuje pozycji/rozmiaru/monitora w pętli), panel SUBIEKT na środku MONITORA; obcy prostokąt 357x693 dla małych dialogów; pułapki Tk/Windows zmierzone WinAPI 01.10.2026 — state("zoomed") mapuje withdrawn okno, losowy flash restore ~0,3 s, Tk poprawia pozycję po 1. mapowaniu
metadata:
  type: project
---

01.10.2026. User: „okna budują się na oczach”, „panel SUBIEKT raz na środku, raz z boku i zaraz się przestawia”.

**Rozwiązanie:** `subiekt_stany.ukryj_do_zbudowania(self)` wołane zaraz po `super().__init__()` we WSZYSTKICH 26 oknach `subiekt_*`/`ksef*` (Toplevel). Panel: `wysrodkuj_na_monitorze` (środek monitora z rodzicem, WinAPI `MonitorFromWindow`) zamiast `wysrodkuj` (środek rodzica — user ma RM_BAZA zmniejszoną i przesuniętą; dialogi w oknach dalej na rodzicu). Kafle panelu mają od razu zarezerwowaną szerokość licznika (`SZEROKOSC_LICZNIKA`), bo liczniki poszerzały okno po kolei.

**Aktualizacja 02.10.2026 — okno PILNUJE miejsca w pętli, nie ustawia go raz:**
- Na 3 monitorach (wszystkie 96 DPI, proces nie-DPI-aware) Tk/Windows ~0,3 s po pokazaniu potrafi przestawić okno jeszcze raz, za każdym razem gdzie indziej: Magazyn maksymalizował się zawsze na LEWYM monitorze, panel przeskakiwał na środkowy — niezależnie od tego, gdzie stała RM_BAZA („wyskakuje na drugim monitorze zamiast na widoku aplikacji").
- `na_miejscu()` w `ukryj_do_zbudowania`: przy każdym ticku (30 ms, okno jeszcze przezroczyste) sprawdza — okno z `_rm_pozycja` (ustawia `wysrodkuj*`): pozycja **i rozmiar** (`_rm_rozmiar`, gdy wysrodkuj dostał w/h wprost); okno bez pozycji / zmaksymalizowane: czy stoi na monitorze RODZICA (`_monitor_okna`, `_na_monitor_rodzica`: restore → przesuń → zoom). Odchyłka → poprawka i odliczanie stabilności od nowa. Odsłonięcie dopiero gdy nieruchome ≥250 ms. Sprawdzone przy RM_BAZA na każdym z 3 monitorów: okno pokazuje się raz, na właściwym monitorze.
- **Obcy prostokąt 357×693 @ (1174,533)** — dostawały go różne małe okna (okno „Nowa kartoteka" 560×380 wychodziło 341×654, „Widoczne kolumny" tak samo). Nie Tk (geometry ustawione poprawnie), nie program do zarządzania oknami (żaden nie działa). Przyczyna NIEZNANA — obejście: dialog przez `ukryj_do_zbudowania` + `wysrodkuj(dlg, rodzic, w, h)`. Podpięte: `subiekt_asortyment.okno_nowa_kartoteka` (`grab_set()` na końcu, nie na początku). Inne małe dialogi spoza 26 okien (np. „Widoczne kolumny" w RM_BAZA) — podpinać tak samo, gdy user zgłosi.
- **Aktualizacja 03.10.2026 — obcy prostokąt dotyczy WSZYSTKICH okien, nie tylko małych** („Szukaj w bazie" 1400x700 → ~665x693, „wyskakuje normalnie, za pół sekundy się zwęża"). Zmierzone GetWindowRect w **CZYSTYM Tk, bez kodu RM_BAZA**: 266–766 ms po pokazaniu okno dostaje prostokąt POPRZEDNIO otwartego okna Tk (także z innego procesu) albo domyślny Windows (893,451 665x693). LOSOWE: w kolejnych 11 próbach ani jednego skoku. `GetWindowPlacement` rcNormal = rzeczywisty prostokąt (to nie „restore do zapamiętanej pozycji"). Hook `SetWinEventHook(EVENT_OBJECT_LOCATIONCHANGE)` nie złapał sprawcy (brak skoku w próbach). Żaden menedżer okien nie działa (sprawdzona lista procesów). **Obejście globalne:** `_pilnuj_geometrii` w `_pilnuj_okien_na_ekranie` (RM_BAZA) — każde `geometry()` uruchamia na 1,5 s od POKAZANIA pilnowanie ROZMIARU I POZYCJI (tylko stan „normal", ponowne geometry przesuwa cel, po 1,5 s pełna swoboda); log `↔️ Okno „…” przestawione na …`. Pierwsza wersja pilnowała samego rozmiaru — okno wracało duże, ale zostawało w (893,451): „otwiera się po dwa razy i nie centralnie". Sprawdzone symulacją SetWindowPos (300/900 ms, zoomed, zmiana usera po 2 s, ujemne X). ⚠️ Odczyt `geometry()` zwraca ujemne jako „+-2560" — wzorzec musi mieć `-?`. Gdy w konsoli pojawi się `↔️` — jest dowód, że sprawca dalej działa; warto wtedy odpalić hook WinEvent w tym samym momencie.
- Okno „Widoczne kolumny" (RM_BAZA) przy drugim kliknięciu tylko `lift()` — jeśli stoi na innym monitorze pod zmaksymalizowanym oknem, wygląda jak zawieszenie aplikacji. Niepoprawione.

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
