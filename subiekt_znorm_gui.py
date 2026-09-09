# -*- coding: utf-8 -*-
"""
Okno: dopasowanie pozycji ZNORMALIZOWANYCH do kartotek Subiekta.

Bliźniak okna scalania kodów, ale rozwiązuje inny problem. Tam chodzi
o ujednolicenie ZAPISU tego samego kodu w BOM-ie („DIN 7 6m6x16" vs
„DIN7 6m6x16"). Tu — o wskazanie, KTÓRA kartoteka Subiekta odpowiada
pozycji, która żadnej nie ma.

Skąd się biorą takie pozycje: znormalizowane nie mają numeru rysunku, więc
RM_BAZA generuje im symbol przez obcięcie nazwy do 13 znaków („Blokada
GN 822.6-4-M8-C" → „BlokadaGN822."). Dopasowanie 1:1 po takim symbolu nie
ma szans; człowiek patrzy na pełną nazwę i wie, o co chodzi.

Zasada bezpieczeństwa (patrz subiekt_podobne.py): NIC nie dzieje się samo.
Podpowiedzi to lista do kliknięcia, zapis idzie jako SPOSOB_RECZNY —
decyzja człowieka, której automat już nie nadpisze. Kto nie chce żadnej
z podpowiedzi, wpisuje symbol sam (pole na dole) albo szuka po katalogu.

    import subiekt_znorm_gui
    subiekt_znorm_gui.open_window(parent, project_id=89, project_name="3000 …")
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox

import subiekt_mapowania
import subiekt_scalanie as S
import subiekt_znorm_dopasowanie as Z

try:
    from subiekt_stany import wysrodkuj, podepnij_szerokosci
except ImportError:                     # okno ma działać też w oderwaniu
    def wysrodkuj(okno, rodzic, *a, **k):
        pass

    def podepnij_szerokosci(*a, **k):
        pass


class ZnormWindow(tk.Toplevel):
    """Lista pozycji bez kartoteki + podpowiedzi + wpis ręczny."""

    def __init__(self, parent, project_id, project_name=None):
        super().__init__(parent)
        self.project_id = project_id
        self.project_name = project_name or str(project_id)
        self.title(f"Dopasuj elementy znormalizowane — projekt {self.project_id}"
                   f" ({self.project_name})")
        self.geometry("1180x720")
        self.minsize(900, 520)
        self.transient(parent)

        self.indeks = None
        self.braki = []
        self._wybor = {}          # {kod pozycji: symbol kartoteki}
        self._biezaca = None      # pozycja aktualnie zaznaczona

        self._buduj()
        self.after(50, self._wczytaj_async)
        wysrodkuj(self, parent)

    # ── budowa okna ────────────────────────────────────────────────────
    def _buduj(self):
        naglowek = tk.Frame(self, bg="#2c3e50")
        naglowek.pack(fill=tk.X)
        tk.Label(naglowek, text="⚙ Dopasowanie elementów znormalizowanych do kartotek Subiekta",
                 bg="#2c3e50", fg="white", font=("Arial", 12, "bold"),
                 anchor="w", padx=12, pady=8).pack(side=tk.LEFT)
        self.lbl_stan = tk.Label(naglowek, text="wczytuję…", bg="#2c3e50",
                                 fg="#bdc3c7", font=("Arial", 9), padx=12)
        self.lbl_stan.pack(side=tk.RIGHT)

        self.summary = tk.Label(self, text="", anchor="w", padx=12, pady=6,
                                font=("Arial", 9), fg="#2c3e50")
        self.summary.pack(fill=tk.X)

        # ── PASEK STEROWANIA ──────────────────────────────────────────
        # Czułość i filtry są tu, bo dobre dopasowanie zależy od materiału:
        # dla normaliów z czytelnym kodem („GN 822-6") ostry próg odsiewa
        # śmieci, a dla nazw opisowych („Docisk nakrętek") trzeba zejść
        # niżej, żeby cokolwiek zobaczyć. Bez regulatora user musiałby
        # wierzyć jednej wartości dobranej przeze mnie.
        panel = tk.Frame(self, bg="#ecf0f1")
        panel.pack(fill=tk.X, padx=12, pady=(0, 6))

        tk.Label(panel, text="Czułość:", bg="#ecf0f1",
                 font=("Arial", 9)).pack(side=tk.LEFT, padx=(8, 4), pady=6)
        self.var_czulosc = tk.StringVar(value="zwykła")
        cb = ttk.Combobox(panel, textvariable=self.var_czulosc, width=12,
                          state="readonly",
                          values=("ostra", "zwykła", "luźna", "wszystko"))
        cb.pack(side=tk.LEFT, pady=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self._pokaz_podpowiedzi())

        tk.Label(panel, text="Ile podpowiedzi:", bg="#ecf0f1",
                 font=("Arial", 9)).pack(side=tk.LEFT, padx=(14, 4), pady=6)
        self.var_ile = tk.StringVar(value="5")
        cb2 = ttk.Combobox(panel, textvariable=self.var_ile, width=5,
                           state="readonly", values=("3", "5", "10", "20"))
        cb2.pack(side=tk.LEFT, pady=6)
        cb2.bind("<<ComboboxSelected>>", lambda e: self._pokaz_podpowiedzi())

        self.var_tylko_stan = tk.BooleanVar(value=False)
        tk.Checkbutton(panel, text="tylko z zapasem na stanie", bg="#ecf0f1",
                       variable=self.var_tylko_stan, font=("Arial", 9),
                       command=self._pokaz_podpowiedzi).pack(side=tk.LEFT, padx=(16, 0))

        self.var_tylko_uzywane = tk.BooleanVar(value=False)
        tk.Checkbutton(panel, text="tylko już używane", bg="#ecf0f1",
                       variable=self.var_tylko_uzywane, font=("Arial", 9),
                       command=self._pokaz_podpowiedzi).pack(side=tk.LEFT, padx=(10, 0))

        self.var_ukryj_wybrane = tk.BooleanVar(value=False)
        tk.Checkbutton(panel, text="ukryj pozycje z wyborem", bg="#ecf0f1",
                       variable=self.var_ukryj_wybrane, font=("Arial", 9),
                       command=self._odswiez_liste).pack(side=tk.LEFT, padx=(10, 0))

        # STOPKA PRZED tabelami — inaczej przy długiej liście przyciski
        # wypadają poza ekran (ta sama pułapka co w raporcie po zapisie).
        stopka = tk.Frame(self)
        stopka.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=10)
        tk.Button(stopka, text="Zamknij", command=self.destroy,
                  padx=16, pady=4).pack(side=tk.LEFT)
        self.btn_zapisz = tk.Button(
            stopka, text="💾 Zapisz dopasowania", command=self._zapisz,
            bg="#e67e22", fg="white", relief=tk.FLAT, font=("Arial", 10, "bold"),
            padx=20, pady=6, state=tk.DISABLED, cursor="hand2")
        self.btn_zapisz.pack(side=tk.RIGHT)

        # Wpis ręczny — zawsze dostępny, także gdy podpowiedzi są puste.
        reczne = tk.Frame(self)
        reczne.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 4))
        tk.Label(reczne, text="Wpisz symbol sam:", font=("Arial", 9)).pack(side=tk.LEFT)
        self.var_reczny = tk.StringVar()
        wpis = tk.Entry(reczne, textvariable=self.var_reczny, width=34,
                        font=("Consolas", 10))
        wpis.pack(side=tk.LEFT, padx=(6, 6))
        wpis.bind("<Return>", lambda e: self._uzyj_recznego())
        tk.Button(reczne, text="Użyj dla zaznaczonej", command=self._uzyj_recznego,
                  padx=10).pack(side=tk.LEFT)
        tk.Label(reczne, text="   Szukaj w katalogu:", font=("Arial", 9)).pack(side=tk.LEFT)
        self.var_szukaj = tk.StringVar()
        szuk = tk.Entry(reczne, textvariable=self.var_szukaj, width=24,
                        font=("Consolas", 10))
        szuk.pack(side=tk.LEFT, padx=(6, 6))
        szuk.bind("<Return>", lambda e: self._szukaj())
        tk.Button(reczne, text="Szukaj", command=self._szukaj, padx=10).pack(side=tk.LEFT)

        # ── dwie tabele obok siebie: pozycje | podpowiedzi ──
        srodek = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=6)
        srodek.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 6))

        lewa = tk.Frame(srodek)
        tk.Label(lewa, text="Pozycje bez kartoteki w Subiekcie", anchor="w",
                 font=("Arial", 9, "bold")).pack(fill=tk.X)
        kol = ("symbol", "nazwa", "ilosc", "wybor")
        self.tab = ttk.Treeview(lewa, columns=kol, show="headings", height=18)
        # Symbol z arkusza obok nazwy: pozycja MOŻE go już mieć (np. wpisany
        # ręcznie albo obcięty z nazwy do 13 znaków) i trzeba widzieć, z czym
        # się pracuje — bez tego nie wiadomo, czy symbol jest sensowny
        # (zgłoszone 09.09.2026).
        for c, tekst, szer in (("symbol", "Symbol w arkuszu", 150),
                               ("nazwa", "Nazwa z arkusza", 260),
                               ("ilosc", "Ilość", 55),
                               ("wybor", "Wybrana kartoteka", 170)):
            self.tab.heading(c, text=tekst)
            self.tab.column(c, width=szer, anchor="w")
        self.tab.tag_configure("wybrano", background="#d5f5e3")
        vs1 = ttk.Scrollbar(lewa, orient="vertical", command=self.tab.yview)
        self.tab.configure(yscrollcommand=vs1.set)
        self.tab.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs1.pack(side=tk.RIGHT, fill=tk.Y)
        self.tab.bind("<<TreeviewSelect>>", self._pokaz_podpowiedzi)
        srodek.add(lewa, minsize=380)

        prawa = tk.Frame(srodek)
        self.lbl_prawa = tk.Label(prawa, text="Podpowiedzi — kliknij dwukrotnie, żeby wybrać",
                                  anchor="w", font=("Arial", 9, "bold"))
        self.lbl_prawa.pack(fill=tk.X)
        kol2 = ("dop", "symbol", "nazwa", "uzyc", "stan")
        self.tab2 = ttk.Treeview(prawa, columns=kol2, show="headings", height=18)
        for c, tekst, szer in (("dop", "Dopas.", 55), ("symbol", "Symbol", 150),
                               ("nazwa", "Nazwa kartoteki", 230),
                               ("uzyc", "Użyć", 50), ("stan", "Na stanie", 70)):
            self.tab2.heading(c, text=tekst)
            self.tab2.column(c, width=szer, anchor="w")
        # Im mocniejsza przesłanka, tym cieplejszy kolor — ale to tylko
        # podpowiedź, nie rozstrzygnięcie: decyduje człowiek.
        self.tab2.tag_configure("mocne", background="#d5f5e3")
        self.tab2.tag_configure("srednie", background="#fdebd0")
        vs2 = ttk.Scrollbar(prawa, orient="vertical", command=self.tab2.yview)
        self.tab2.configure(yscrollcommand=vs2.set)
        self.tab2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs2.pack(side=tk.RIGHT, fill=tk.Y)
        self.tab2.bind("<Double-1>", self._wybierz_podpowiedz)
        srodek.add(prawa, minsize=420)

        tk.Label(self, anchor="w", justify="left", padx=12, fg="#7f8c8d",
                 font=("Arial", 8),
                 text=("Podpowiedzi liczone po KODZIE w nazwie (tokeny z cyfrą decydują). "
                       "Kolumna Użyć = w ilu projektach firma już użyła tej kartoteki, "
                       "Na stanie = ilość dostępna w Subiekcie.  "
                       "Zapis idzie jako decyzja ręczna — automat jej nie nadpisze."),
                 ).pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 2))

    # ── wczytywanie w tle ──────────────────────────────────────────────
    def _wczytaj_async(self):
        threading.Thread(target=self._wczytaj_worker, daemon=True).start()

    def _wczytaj_worker(self):
        blad = None
        try:
            import subiekt_projekt as sp
            katalog = S.wczytaj_katalog_subiekta() or []
            items = sp.read_project_items(self.project_id)
            braki = Z.pozycje_do_dopasowania(items, katalog, S.dopasuj_katalog)

            uzycia = {}
            try:
                uzycia = Z.policz_uzycia(self._projects_dir())
            except Exception:
                pass            # popularność jest miła, ale nie konieczna

            stany = {}
            try:
                import subiekt_magazyn_gui as MG
                stany = Z.stany_z_magazynu(
                    MG.pobierz_magazyn(tylko_niezerowe=False, timeout=120))
            except Exception:
                pass            # magazyn nieosiągalny — okno ma działać dalej

            indeks = Z.Indeks(katalog, uzycia=uzycia, stany=stany)
        except Exception as e:
            blad, braki, indeks = str(e), [], None
        self.after(0, lambda: self._wczytano(braki, indeks, blad))

    @staticmethod
    def _projects_dir():
        try:
            import subiekt_stany
            return subiekt_stany._projects_dir()
        except Exception:
            return r"Y:\RM_BAZA\projects"

    def _wczytano(self, braki, indeks, blad):
        if not self.winfo_exists():
            return
        if blad:
            self.lbl_stan.config(text="błąd")
            messagebox.showerror("Dopasowanie", blad, parent=self)
            return
        self.braki, self.indeks = braki, indeks
        self.lbl_stan.config(text=f"katalog: {len(indeks)} kartotek")
        self.summary.config(text=(
            f"Pozycji ZNORMALIZOWANYCH bez kartoteki: {len(braki)}"
            + ("   —   nie ma czego dopasowywać, wszystkie mają już kartotekę"
               if not braki else "")))
        self._odswiez_liste()

    def _odswiez_liste(self):
        self.tab.delete(*self.tab.get_children())
        for b in self.braki:
            wybrany = self._wybor.get(b["kod"], "")
            if wybrany and self.var_ukryj_wybrane.get():
                continue          # załatwione — schodzi z oczu, zostaje w wyborze
            self.tab.insert("", "end", iid=b["kod"],
                            values=(b["kod"], b["nazwa"] or b["kod"],
                                    b.get("ilosc") or "", wybrany),
                            tags=("wybrano",) if wybrany else ())
        widoczne = len(self.tab.get_children())
        self.summary.config(text=(
            f"Pozycji ZNORMALIZOWANYCH bez kartoteki: {len(self.braki)}"
            f"   ·   wyświetlanych: {widoczne}"
            f"   ·   z wybraną kartoteką: {len(self._wybor)}"))
        self.btn_zapisz.config(
            state=tk.NORMAL if self._wybor else tk.DISABLED,
            text=(f"💾 Zapisz dopasowania ({len(self._wybor)})"
                  if self._wybor else "💾 Zapisz dopasowania"))

    # ── podpowiedzi ────────────────────────────────────────────────────
    #: Próg minimalnego dopasowania dla każdego poziomu czułości.
    #: Skalibrowane pomiarem na 56 pozycjach projektu 79 (mediana najlepszego
    #: trafienia = 0.455): 0.40 daje podpowiedź dla 32/56 pozycji i prawie
    #: same trafne, 0.15 dla 44/56 ale z szumem. „wszystko" = pokaż cokolwiek
    #: dzieli choć jeden token — ostatnia deska ratunku.
    PROGI = {"ostra": 0.40, "zwykła": 0.20, "luźna": 0.10, "wszystko": 0.0}

    def _filtruj(self, lista):
        """Odsiew wg checkboxów — na gotowej liście, bez pytania katalogu."""
        if self.var_tylko_stan.get():
            lista = [p for p in lista if (p.get("stan") or 0) > 0]
        if self.var_tylko_uzywane.get():
            lista = [p for p in lista if (p.get("uzyc") or 0) > 0]
        return lista

    def _pokaz_podpowiedzi(self, _event=None):
        sel = self.tab.selection()
        if not sel or not self.indeks:
            return
        kod = sel[0]
        self._biezaca = kod
        poz = next((b for b in self.braki if b["kod"] == kod), None)
        if not poz:
            return
        self.var_reczny.set(self._wybor.get(kod, ""))
        prog = self.PROGI.get(self.var_czulosc.get(), 0.15)
        try:
            ile = int(self.var_ile.get())
        except ValueError:
            ile = 5
        # Bierzemy z zapasem, bo checkboxy dopiero potem odsieją część —
        # inaczej „tylko z zapasem na stanie" pokazywałoby 1 wynik z 5.
        lista = self.indeks.podpowiedzi(poz["nazwa"] or kod,
                                        ile=ile * 4, prog=prog)
        lista = self._filtruj(lista)[:ile]
        self._wypelnij_podpowiedzi(lista, f"Podpowiedzi dla: {poz['nazwa'] or kod}")

    def _wypelnij_podpowiedzi(self, lista, tytul):
        # Licznik: ile faktycznie widać PO progu i checkboxach — inaczej nie
        # wiadomo, czy pusto znaczy „nic nie pasuje", czy „filtr uciął"
        # (zgłoszone 09.09.2026).
        ile = len(lista or [])
        self.lbl_prawa.config(
            text=f"{tytul}   —   {ile} dopasowań   —   kliknij dwukrotnie, żeby wybrać")
        self.tab2.delete(*self.tab2.get_children())
        if not lista:
            self.tab2.insert("", "end", values=(
                "", "(brak podpowiedzi)", "wpisz symbol sam albo poszukaj w katalogu",
                "", ""))
            return
        for p in lista:
            w = p.get("wynik")
            tag = ("mocne" if (w or 0) >= 0.5 else
                   "srednie" if (w or 0) >= 0.3 else "")
            self.tab2.insert("", "end", values=(
                f"{w:.2f}" if w is not None else "—",
                p["symbol"], p["nazwa"],
                p["uzyc"] if p["uzyc"] is not None else "—",
                self._fmt_stan(p["stan"])), tags=(tag,) if tag else ())

    @staticmethod
    def _fmt_stan(stan):
        if stan is None:
            return "—"
        return str(int(stan)) if float(stan).is_integer() else f"{stan:g}"

    def _szukaj(self):
        if not self.indeks:
            return
        fraza = self.var_szukaj.get().strip()
        if not fraza:
            return
        self._wypelnij_podpowiedzi(self._filtruj(self.indeks.znajdz_tekstem(fraza)),
                                   f"Wyniki szukania „{fraza}”")

    # ── wybór ──────────────────────────────────────────────────────────
    def _wybierz_podpowiedz(self, _event=None):
        if not self._biezaca:
            messagebox.showinfo("Dopasowanie",
                                "Najpierw zaznacz pozycję po lewej.", parent=self)
            return
        sel = self.tab2.selection()
        if not sel:
            return
        symbol = (self.tab2.set(sel[0], "symbol") or "").strip()
        if not symbol or symbol.startswith("("):
            return
        self._ustaw(self._biezaca, symbol)

    def _uzyj_recznego(self):
        if not self._biezaca:
            messagebox.showinfo("Dopasowanie",
                                "Najpierw zaznacz pozycję po lewej.", parent=self)
            return
        symbol = self.var_reczny.get().strip()
        if not symbol:
            # Puste pole = wycofanie wyboru; user zmienił zdanie.
            self._wybor.pop(self._biezaca, None)
            self._odswiez_liste()
            return
        self._ustaw(self._biezaca, symbol)

    def _ustaw(self, kod, symbol):
        self._wybor[kod] = symbol
        self.var_reczny.set(symbol)
        self._odswiez_liste()
        try:
            self.tab.selection_set(kod)
            self.tab.see(kod)
        except tk.TclError:
            pass

    # ── zapis ──────────────────────────────────────────────────────────
    def _zapisz(self):
        if not self._wybor:
            return
        linie = [f"   {k}  →  {v}" for k, v in sorted(self._wybor.items())][:15]
        wiecej = len(self._wybor) - len(linie)
        if not messagebox.askyesno(
                "Zapisz dopasowania",
                f"Zapisać {len(self._wybor)} dopasowań jako decyzje ręczne?\n\n"
                + "\n".join(linie)
                + (f"\n   … i {wiecej} więcej" if wiecej > 0 else "")
                + "\n\nDecyzja ręczna ma pierwszeństwo — automat jej nie nadpisze.",
                parent=self):
            return
        wpisy = [(kod, symbol, subiekt_mapowania.SPOSOB_RECZNY)
                 for kod, symbol in self._wybor.items()]
        try:
            n = subiekt_mapowania.put_many(wpisy)
        except Exception as e:
            messagebox.showerror("Zapis", f"Nie udało się zapisać:\n\n{e}", parent=self)
            return
        messagebox.showinfo("Zapisano",
                            f"Zapisano {n} dopasowań.\n\n"
                            "Będą użyte przy najbliższym podglądzie projektu\n"
                            "i we wszystkich kolejnych projektach.", parent=self)
        self._wybor.clear()
        self._odswiez_liste()


def open_window(parent, project_id, project_name=None):
    """Punkt wejścia dla RM_BAZA."""
    if not project_id:
        messagebox.showwarning("Dopasowanie",
                               "Najpierw wybierz projekt.", parent=parent)
        return None
    return ZnormWindow(parent, project_id, project_name)


if __name__ == "__main__":
    import sys
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 79
    root = tk.Tk()
    root.withdraw()
    w = open_window(root, pid, sys.argv[2] if len(sys.argv) > 2 else None)
    w.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
