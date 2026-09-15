---
name: project_okna_trzy_monitory
description: "Stanowisko ma 3 monitory; wysrodkuj() musi używać granic wirtualnego pulpitu, nie winfo_screenwidth"
metadata: 
  node_type: memory
  type: project
  originSessionId: 47fa97da-3439-4292-864b-075339162d55
  modified: 2026-09-08T17:48:46.486Z
---

Stanowisko użytkownika ma **trzy monitory**: pulpit sięga od `x=-2560` do
`x=5120` (2560×1440 każdy), monitor główny jest środkowy.

`subiekt_stany.wysrodkuj()` liczyło pozycję względem okna rodzica poprawnie, ale
przycinało ją do `winfo_screenwidth/height` — a Tk zwraca tam rozmiar monitora
**GŁÓWNEGO**, nie całego pulpitu. Każde okno otwierane z aplikacji stojącej na
lewym albo prawym monitorze było więc ściągane z powrotem na środkowy.

Clamp używa teraz `_granice_pulpitu()` → `SM_XVIRTUALSCREEN` (76),
`SM_YVIRTUALSCREEN` (77), `SM_CXVIRTUALSCREEN` (78), `SM_CYVIRTUALSCREEN` (79)
z `ctypes.windll.user32`. Poza Windows albo przy błędzie — stary zakres jednego
ekranu (dla jednego monitora daje ten sam wynik).

**Why:** user pracuje na trzecim monitorze i okna uciekały mu na środkowy
(„mrugaj mi na trzecim monitorze a nie na tym co teraz").

**How to apply:** przy każdym nowym kodzie pozycjonującym okna NIE używaj
`winfo_screenwidth/height` do ograniczania współrzędnych — współrzędne bywają
UJEMNE i to jest poprawne. `wysrodkuj()` jest wspólne dla wszystkich okien
RM_BAZA, więc zwykle wystarczy z niego skorzystać.

Powiązane: [[project_subiekt_edytor_kartotek]].

## Pułapka 1x1 (09.09.2026)

Toplevel `transient` względem rodzica, który sam NIE jest zmapowany (komunikat z `__init__` świeżego okna): po `update_idletasks()` `winfo_width()` i `winfo_reqwidth()` zwracają **1**. `winfo_width() or winfo_reqwidth()` nie ratuje (1 jest prawdziwe) → `geometry("1x1+x+y")` → ramka 17×40 px bez treści. Modalny (`grab_set`+`wait_window`) = pozorne zawieszenie aplikacji. Fix w `subiekt_stany.wysrodkuj`: gdy w/h ≤ 1 ustawiać SAMĄ pozycję `+x+y`. Diagnoza: EnumWindows po PID pokazuje okno 17×40 — zamknąć `PostMessage(WM_CLOSE)`.
