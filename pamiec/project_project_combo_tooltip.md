---
name: project_project_combo_tooltip
description: Selektor projektu — długie nazwy ucięte; rozwiązane tooltipem (nie poszerzaniem popdown)
metadata: 
  node_type: memory
  type: project
  originSessionId: 82f2a873-9dc2-427e-b90e-cba22eee7c22
---

Selektor PROJEKT (self.project_combo, ttk.Combobox width=40 w top_frame) ucinał długie nazwy (np. "2623 CERAMIZATOR etykieciarka [Linia Ceramizator]" ~60 znaków).

**Czego NIE da się zrobić (sprawdzone 2026-07-18):**
- Poszerzanie rozwijanej listy (popdown) NIE działa: ttk wymusza szerokość popdown = fizyczna szerokość widżetu combobox przy każdym otwarciu (Post). `{combo}.popdown.f.l configure -width N` zmienia reqwidth listboxa, ale `wm geometry {combo}.popdown` jest natychmiast odtwarzane przez ttk. Tk 8.6.15.
- Poszerzanie samego POLA działa (popdown dziedziczy), ALE rozpycha przyciski na górnym pasku — użytkownik tego nie chce.
- Kontener ze stałą szerokością (pack_propagate False) + fill=both zmusza combobox do rozmiaru kontenera → popdown znów wąski. Wyklucza się z poszerzaniem.

**Rozwiązanie: tooltip.** `_setup_project_combo_tooltip()` — Toplevel (overrideredirect) z żółtym labelem. DWA miejsca:
1. Pole (wybrany projekt): bind <Enter>/<Leave> na project_combo, add='+'.
2. Pozycje rozwiniętej listy: przy <Button-1> po 50ms wołane _bind_popdown() — binduje <Motion> na wewnętrznym listboxie `{combo}.popdown.f.l` przez tk.eval(f'bind {lb} <Motion> +[list {cmd} %x %y]'), cmd=register(callback). Callback robi `{lb} index @x,y` → indeks → vals[idx] → tooltip przy kursorze (winfo_pointerx/y).
Ukrywany na <Button-1>, <<ComboboxSelected>>, <Leave>.
UWAGA testowanie: w headless `event generate <Motion>` na popdown NIE wyzwala binda (ograniczenie testu, nie kodu) — trzeba sprawdzić ręcznym ruchem myszy. Zweryfikowane pośrednio: bind rejestruje się w Tcl, `index @x,y` mapuje pozycję na poprawną nazwę.

Powiązane: [[project_disk_layout]].
