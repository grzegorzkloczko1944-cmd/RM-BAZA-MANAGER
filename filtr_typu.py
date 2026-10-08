# -*- coding: utf-8 -*-
"""Filtr TYP jak w głównej belce RM_BAZA — dla okien podrzędnych (Wydanie z magazynu).

Dwie części działające RAZEM (AND), dokładnie jak w `MainWindow._apply_filters`:
  • lista „Typ:”  — (WSZYSTKO) / X / XX / Z / ZZ / STANDARD / ZNORMALIZOWANE / LASER / LASER EXPORT,
  • kafelek ✚     — trójstan per typ: obojętny / pokaż ✓ / ukryj ✕ (ukryj wygrywa),
                    LASER(+EXPORT) = X + XX, „(bez typu)” = pusty class_effective.

⚠️ Wartości i reguły MUSZĄ zgadzać się z RM_BAZA_v15_MAG_STATS_ORG.py
(FILTER_CLASS_VALUES, MainWindow.CLASS_MULTI_VALUES, _apply_filters,
open_class_filter_dialog). Główne okno NIE korzysta z tego modułu (08.10.2026:
nie ruszamy działającej belki) — przy zmianie tam, zmienić i tu.
"""
import tkinter as tk

FILTER_CLASS_VALUES = ["(WSZYSTKO)", "X", "XX", "Z", "ZZ", "STANDARD", "ZNORMALIZOWANE",
                       "LASER", "LASER EXPORT"]
CLASS_MULTI_VALUES = ["X", "XX", "Z", "ZZ", "STANDARD", "ZNORMALIZOWANE",
                      "LASER", "LASER EXPORT", "(bez typu)"]
WSZYSTKO = "(WSZYSTKO)"
FILTER_SUPPLIER_ALL = "(WSZYSCY)"


def _rozwin(t):
    if t in ("LASER", "LASER EXPORT"):
        return ("X", "XX")
    if t == "(bez typu)":
        return ("",)
    return (t,)


def pasuje(typ, filtr, tryby):
    """Czy pozycja o typie `typ` (class_effective, '' = brak) przechodzi filtr.

    filtr — wartość listy „Typ:”, tryby — {typ: 'show'|'hide'} z kafelka ✚."""
    typ = typ or ""
    if filtr and filtr != WSZYSTKO:
        if filtr in ("LASER", "LASER EXPORT"):
            if typ not in ("X", "XX"):
                return False
        elif typ != filtr:
            return False
    pokaz, ukryj = set(), set()
    for t, m in (tryby or {}).items():
        (pokaz if m == "show" else ukryj).update(_rozwin(t))
    if typ in ukryj:
        return False
    if pokaz and typ not in pokaz:
        return False
    return True


def wyglad_kafelka(przycisk, tryby):
    """Napis i kolor kafelka ✚ jak w głównej belce: ✓n ✕m, zielony / czerwony."""
    n_show = sum(1 for m in tryby.values() if m == "show")
    n_hide = sum(1 for m in tryby.values() if m == "hide")
    if not n_show and not n_hide:
        przycisk.config(text="✚", bg="#7f8c8d")
        return
    czesci = ([f"✓{n_show}"] if n_show else []) + ([f"✕{n_hide}"] if n_hide else [])
    przycisk.config(text=" ".join(czesci), bg="#c0392b" if n_hide else "#27ae60")


def _odepnij(okno, sekwencja, funcid):
    """Zdejmuje JEDEN bind (po funcid) z okna — reszta bindów tej sekwencji zostaje.
    Tkinter < 3.13 nie umie unbind(seq, funcid) bez kasowania wszystkich."""
    try:
        skrypt = okno.tk.call("bind", okno._w, sekwencja)
        zostaje = "\n".join(l for l in str(skrypt).split("\n") if funcid not in l)
        okno.tk.call("bind", okno._w, sekwencja, zostaje)
        okno.deletecommand(funcid)
    except Exception:
        pass


class PopupTypu:
    """Dymek „Filtr Typ” pod kafelkiem ✚ — ten sam układ i działanie co w głównej belce:
    pokaż / ukryj per typ, filtrowanie od razu (bez OK), Resetuj, klik poza dymkiem zamyka.

    tryby      — słownik {typ: 'show'|'hide'} (modyfikowany w miejscu),
    po_zmianie — wołane po każdej zmianie (odśwież listę + kafelek)."""

    def __init__(self, okno, przycisk, tryby, po_zmianie):
        self.okno, self.przycisk, self.tryby, self.po_zmianie = okno, przycisk, tryby, po_zmianie
        self.dialog = None

    def otwarty(self):
        try:
            return self.dialog is not None and self.dialog.winfo_exists()
        except tk.TclError:
            return False

    def przelacz(self):
        if self.otwarty():
            self.zamknij()
        else:
            self._otworz()

    def zamknij(self):
        d = self.dialog
        self.dialog = None
        if d is None:
            return
        # Najpierw zamknięcie, potem sprzątanie — błąd przy zdejmowaniu bindu
        # nie może zostawić dymka na ekranie (08.10.2026: „nie mogę zamknąć tego
        # okienka” — unbind_all(seq, funcid) rzucał TypeError przed destroy()).
        try:
            if d.winfo_exists():
                d.destroy()
        except Exception:
            pass
        bid = getattr(d, "_click_binding_id", None)
        if bid:
            _odepnij(self.okno, "<Button-1>", bid)

    def _otworz(self):
        d = self.dialog = tk.Toplevel(self.okno)
        d.title("Filtr Typ")
        d.configure(bg="#2c3e50", bd=1, relief=tk.SOLID)
        tk.Label(d, text="Filtr Typ — zaznacz pokaż lub ukryj przy typach:",
                 bg="#2c3e50", fg="#ecf0f1", font=("Arial", 8), anchor="w"
                 ).pack(fill=tk.X, padx=8, pady=(6, 4))
        body = tk.Frame(d, bg="white")
        body.pack(fill=tk.BOTH, expand=True, padx=1, pady=(0, 1))
        hdr = tk.Frame(body, bg="#f0f0f0")
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="", bg="#f0f0f0", width=16, anchor="w").pack(side=tk.LEFT)
        tk.Label(hdr, text="pokaż", bg="#f0f0f0", fg="#27ae60", width=6,
                 font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        tk.Label(hdr, text="ukryj", bg="#f0f0f0", fg="#c0392b", width=6,
                 font=("Arial", 8, "bold")).pack(side=tk.LEFT)

        zmienne = {}

        def wiersz(typ):
            r = tk.Frame(body, bg="white")
            r.pack(fill=tk.X, padx=4, pady=1)
            tk.Label(r, text=typ + ("  (laser)" if typ in ("LASER", "LASER EXPORT") else ""),
                     bg="white", anchor="w", width=16, font=("Arial", 9)).pack(side=tk.LEFT)
            cur = self.tryby.get(typ)
            sv = tk.IntVar(master=d, value=1 if cur == "show" else 0)
            hv = tk.IntVar(master=d, value=1 if cur == "hide" else 0)
            zmienne[typ] = (sv, hv)

            def zastosuj():
                if sv.get():
                    self.tryby[typ] = "show"
                elif hv.get():
                    self.tryby[typ] = "hide"
                else:
                    self.tryby.pop(typ, None)
                self.po_zmianie()

            def na_pokaz():
                if sv.get():
                    hv.set(0)                 # pokaż i ukryj wykluczają się
                zastosuj()

            def na_ukryj():
                if hv.get():
                    sv.set(0)
                zastosuj()

            tk.Checkbutton(r, variable=sv, bg="white", width=5, command=na_pokaz).pack(side=tk.LEFT)
            tk.Checkbutton(r, variable=hv, bg="white", width=5, command=na_ukryj).pack(side=tk.LEFT)

        for typ in CLASS_MULTI_VALUES:
            wiersz(typ)

        stopka = tk.Frame(d, bg="#2c3e50")
        stopka.pack(fill=tk.X, padx=8, pady=(2, 6))

        def resetuj():
            for sv, hv in zmienne.values():
                sv.set(0)
                hv.set(0)
            self.tryby.clear()
            self.po_zmianie()

        tk.Button(stopka, text="Resetuj", command=resetuj, font=("Arial", 8)).pack(side=tk.LEFT)
        tk.Button(stopka, text="Zamknij", command=self.zamknij, font=("Arial", 8)).pack(side=tk.RIGHT)

        # pozycja POD kafelkiem (po zbudowaniu treści, gdy okno zna rozmiar)
        try:
            d.update_idletasks()
            w, h = d.winfo_reqwidth() or 220, d.winfo_reqheight() or 300
            bx = self.przycisk.winfo_rootx()
            by = self.przycisk.winfo_rooty() + self.przycisk.winfo_height()
            if bx <= 0 and by <= 0:
                bx, by = self.okno.winfo_pointerx(), self.okno.winfo_pointery() + 10
            sw, sh = d.winfo_screenwidth(), d.winfo_screenheight()
            d.geometry(f"{w}x{h}+{max(0, min(bx, sw - w))}+{max(0, min(by, sh - h))}")
        except tk.TclError:
            pass
        try:
            d.overrideredirect(True)
            d.transient(self.okno)
            d.lift()
            d.attributes("-topmost", True)
            d.after(10, lambda: d.attributes("-topmost", False))
        except tk.TclError:
            pass
        d.focus_set()
        d.bind("<Escape>", lambda _e: self.zamknij())

        def klik(e):
            try:
                if not self.otwarty():
                    return
                x, y = e.x_root, e.y_root
                w_dymku = (d.winfo_rootx() <= x <= d.winfo_rootx() + d.winfo_width()
                           and d.winfo_rooty() <= y <= d.winfo_rooty() + d.winfo_height())
                b = self.przycisk
                na_kafelku = (b.winfo_rootx() <= x <= b.winfo_rootx() + b.winfo_width()
                              and b.winfo_rooty() <= y <= b.winfo_rooty() + b.winfo_height())
                if not w_dymku and not na_kafelku:
                    self.zamknij()
            except tk.TclError:
                pass

        def uzbroj():                       # po chwili — otwierające kliknięcie nie zamyka
            if self.otwarty():
                # bind na OKNIE (nie bind_all): klik w dowolny widget tego okna,
                # bez ruszania globalnych bindów reszty RM_BAZA
                d._click_binding_id = self.okno.bind("<Button-1>", klik, add="+")
        d.after(200, uzbroj)
