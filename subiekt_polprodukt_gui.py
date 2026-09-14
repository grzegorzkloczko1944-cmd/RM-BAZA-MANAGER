# -*- coding: utf-8 -*-
"""Powiązanie rysunku z kartoteką PÓŁFABRYKATU, który kupujemy.

Detal często powstaje z gotowej, kupionej części: rysunek „Koło 5M_40 fi38"
to zakupione koło zębate 5M/40 + obróbka otworu Ø38. Konstruktor wie o tym
z rysunku i przypina półprodukt raz — logistyk i kalkulator korzystają
z tego w każdym następnym projekcie (POLPRODUKTY_PLAN.md).

Właścicielem kartoteki jest SUBIEKT, właścicielem relacji RM_BAZA: to wiedza
konstrukcyjna („z czego powstaje detal"), nie magazynowa. Relacja leży
w bazie mapowań na serwerze, więc działa globalnie, nie per projekt.

⚠️ Okno NIE pokazuje ceny ani stanu. Te dane zmieniają się co godzinę
i czyta się je na żywo tam, gdzie są potrzebne (kalkulator, ZK) — kopia
w oknie wyboru po dniu kłamie.
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox

import subiekt_mapowania as M
import subiekt_scalanie as S


#: Dłuższa lista i tak jest bezużyteczna — tak samo jak w wyszukiwarce
#: okna scalania, z której wzięty jest ten wzorzec.
LIMIT_TRAFIEN = 300


def _wysrodkuj(okno, rodzic, szer, wys):
    okno.update_idletasks()
    try:
        x = rodzic.winfo_rootx() + (rodzic.winfo_width() - szer) // 2
        y = rodzic.winfo_rooty() + (rodzic.winfo_height() - wys) // 3
    except tk.TclError:
        x = y = 200
    okno.geometry("%dx%d+%d+%d" % (szer, wys, max(0, x), max(0, y)))


class PolproduktWindow(tk.Toplevel):
    """Wyszukiwarka kartotek + lista już powiązanych półproduktów.

    `numer` to klucz relacji — numer rysunku, a dla pozycji znormalizowanej
    jej nazwa. Liczy go WOŁAJĄCY, tą samą regułą co reszta integracji
    (`COALESCE(work_drawing_no, norm_drawing_no, src_drawing_no, name)`),
    żeby ten sam detal nie miał tu innego klucza niż w pozostałych oknach.
    """

    def __init__(self, parent, numer, opis=""):
        super().__init__(parent)
        self.numer = (numer or "").strip()
        self._katalog = []
        self._pobieranie = False

        self.title("Powiąż półprodukt — %s" % self.numer)
        self.transient(parent)
        _wysrodkuj(self, parent, 760, 620)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())

        tk.Label(self, text="Rysunek:   %s" % self.numer,
                 font=("Arial", 10, "bold"), anchor="w").pack(
                     fill=tk.X, padx=12, pady=(12, 0))
        if opis:
            tk.Label(self, text=opis, font=("Arial", 8), fg="#555",
                     anchor="w").pack(fill=tk.X, padx=12)

        self._sekcja_powiazane()
        self._sekcja_szukania()

        self.status = tk.Label(self, text="", font=("Arial", 8), fg="#555",
                               anchor="w")
        self.status.pack(fill=tk.X, padx=12, pady=(0, 10))

        self._odswiez_powiazane()
        self._wczytaj_katalog()
        self.grab_set()
        self.ent_szukaj.focus_set()

    # ── powiązane ────────────────────────────────────────────────────────
    def _sekcja_powiazane(self):
        ramka = tk.LabelFrame(self, text=" Z czego powstaje ten detal ",
                              font=("Arial", 9, "bold"))
        ramka.pack(fill=tk.X, padx=12, pady=(10, 6))

        self.tab_pow = ttk.Treeview(
            ramka, columns=("symbol", "nazwa", "ile"), show="headings",
            height=4)
        for k, n, w, a in (("symbol", "Symbol", 170, "w"),
                           ("nazwa", "Nazwa", 380, "w"),
                           ("ile", "Na 1 detal", 80, "e")):
            self.tab_pow.heading(k, text=n)
            self.tab_pow.column(k, width=w, anchor=a,
                                stretch=(k == "nazwa"))
        self.tab_pow.pack(side=tk.LEFT, fill=tk.X, expand=True,
                          padx=(8, 0), pady=8)

        bok = tk.Frame(ramka)
        bok.pack(side=tk.RIGHT, fill=tk.Y, padx=8, pady=8)
        tk.Button(bok, text="Zmień ilość", command=self._zmien_ilosc,
                  font=("Arial", 9), width=14).pack(pady=(0, 4))
        tk.Button(bok, text="Usuń powiązanie", command=self._usun,
                  font=("Arial", 9), width=14).pack()

    def _odswiez_powiazane(self):
        self.tab_pow.delete(*self.tab_pow.get_children())
        try:
            wiersze = M.polprodukty(self.numer)
        except Exception as e:
            self.status.config(text="Nie odczytano powiązań: %s" % e)
            return
        for w in wiersze:
            self.tab_pow.insert(
                "", tk.END, iid=str(w["id_subiekt"]),
                values=(w["symbol"] or "(id %s)" % w["id_subiekt"],
                        w["nazwa"] or "", w["ilosc_na_szt"]))
        self.status.config(
            text="Powiązanych półproduktów: %d" % len(wiersze)
            if wiersze else "Ten rysunek nie ma jeszcze półproduktu.")

    def _zaznaczony(self):
        sel = self.tab_pow.selection()
        return int(sel[0]) if sel else None

    def _zmien_ilosc(self):
        id_sub = self._zaznaczony()
        if id_sub is None:
            return messagebox.showinfo(
                "Zmień ilość", "Zaznacz najpierw powiązany półprodukt.",
                parent=self)
        biezaca = self.tab_pow.item(str(id_sub), "values")
        ile = self._zapytaj_o_ilosc(int(biezaca[2]))
        if ile is None:
            return
        try:
            M.zapisz_polprodukt(self.numer, id_sub, ile,
                                symbol=biezaca[0], nazwa=biezaca[1])
        except Exception as e:
            return messagebox.showerror("Zmień ilość", str(e), parent=self)
        self._odswiez_powiazane()
        self.status.config(text="%s: %s szt. na 1 detal."
                                % (biezaca[0], ile))

    def _usun(self):
        id_sub = self._zaznaczony()
        if id_sub is None:
            return messagebox.showinfo(
                "Usuń powiązanie", "Zaznacz najpierw powiązany półprodukt.",
                parent=self)
        symbol = self.tab_pow.item(str(id_sub), "values")[0]
        # Kasujemy TYLKO relację. Kartoteka w Subiekcie zostaje nietknięta —
        # to zwykły towar, żyjący własnym życiem jak łożysko czy pasek.
        if not messagebox.askyesno(
                "Usuń powiązanie",
                "Usunąć powiązanie rysunku %s z kartoteką %s?\n\n"
                "Kartoteka w Subiekcie zostaje bez zmian — znika tylko\n"
                "informacja, że ten detal powstaje z kupionego półproduktu."
                % (self.numer, symbol), parent=self):
            return
        try:
            M.usun_polprodukt(self.numer, id_sub)
        except Exception as e:
            return messagebox.showerror("Usuń powiązanie", str(e), parent=self)
        self._odswiez_powiazane()
        self.status.config(text="Usunięto powiązanie z %s." % symbol)

    # ── wyszukiwarka ─────────────────────────────────────────────────────
    def _sekcja_szukania(self):
        ramka = tk.LabelFrame(self, text=" Wskaż kartotekę półproduktu ",
                              font=("Arial", 9, "bold"))
        ramka.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 6))

        tk.Label(ramka,
                 text="Wpisz fragment symbolu albo nazwy — lista zawęża się "
                      "na bieżąco.",
                 font=("Arial", 8), fg="#555", anchor="w").pack(
                     fill=tk.X, padx=8, pady=(6, 2))

        self.var_szukaj = tk.StringVar(value=self.numer)
        self.ent_szukaj = tk.Entry(ramka, textvariable=self.var_szukaj,
                                   font=("Consolas", 10))
        self.ent_szukaj.pack(fill=tk.X, padx=8, pady=(0, 6), ipady=3)

        # Dół przypięty PRZED listą — inaczej rozciągająca się lista spycha
        # przyciski poza okno (ta sama pułapka co w oknie scalania).
        dol = tk.Frame(ramka)
        dol.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(4, 8))
        self.info = tk.Label(ramka, text="", font=("Arial", 8), fg="#555",
                             anchor="w")
        self.info.pack(side=tk.BOTTOM, fill=tk.X, padx=8)

        wnetrze = tk.Frame(ramka)
        wnetrze.pack(fill=tk.BOTH, expand=True, padx=8)
        self.lista = ttk.Treeview(wnetrze, columns=("symbol", "nazwa"),
                                  show="headings", height=9)
        self.lista.heading("symbol", text="Symbol")
        self.lista.heading("nazwa", text="Nazwa")
        self.lista.column("symbol", width=170, stretch=False)
        self.lista.column("nazwa", width=420)
        vs = ttk.Scrollbar(wnetrze, orient="vertical",
                           command=self.lista.yview)
        self.lista.configure(yscrollcommand=vs.set)
        self.lista.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)

        tk.Label(dol, text="Ile sztuk na 1 detal:",
                 font=("Arial", 9)).pack(side=tk.LEFT)
        self.var_ile = tk.StringVar(value="1")
        tk.Spinbox(dol, textvariable=self.var_ile, from_=1, to=9999, width=6,
                   font=("Arial", 10), justify="center").pack(
                       side=tk.LEFT, padx=(6, 0))
        tk.Label(dol, text="(sztuki całkowite)", font=("Arial", 8),
                 fg="#555").pack(side=tk.LEFT, padx=(6, 0))
        tk.Button(dol, text="Powiąż ten półprodukt", command=self._powiaz,
                  bg="#2980b9", fg="white", font=("Arial", 9, "bold"),
                  padx=12, pady=4).pack(side=tk.RIGHT)

        self.var_szukaj.trace_add("write", self._filtruj)
        self.lista.bind("<Double-1>", lambda _e: self._powiaz())

    def _wczytaj_katalog(self):
        """Cache z dysku od razu; gdy pusty — most, w tle."""
        try:
            self._katalog = S.wczytaj_katalog_subiekta(tylko_cache=True) or []
        except Exception:
            self._katalog = []
        if self._katalog:
            self._filtruj()
            return

        self._pobieranie = True
        self.info.config(text="Pobieram kartoteki z Subiekta…")
        self.config(cursor="watch")

        def worker():
            try:
                katalog = S.wczytaj_katalog_subiekta()
                self.after(0, lambda: gotowe(katalog, None))
            except Exception as e:
                blad = str(e)
                self.after(0, lambda: gotowe(None, blad))

        def gotowe(katalog, blad):
            self._pobieranie = False
            try:
                self.config(cursor="")
            except tk.TclError:
                return                      # okno zamknięte w międzyczasie
            if blad:
                self.info.config(text="Subiekt niedostępny.")
                messagebox.showerror(
                    "Powiąż półprodukt",
                    "Nie udało się pobrać kartotek z Subiekta:\n\n%s" % blad,
                    parent=self)
                return
            self._katalog = katalog or []
            self._filtruj()

        threading.Thread(target=worker, daemon=True).start()

    def _filtruj(self, *_a):
        fraza = S.norm_kod(self.var_szukaj.get())
        self.lista.delete(*self.lista.get_children())
        trafienia = []
        for poz in self._katalog:
            if not fraza or (fraza in S.norm_kod(poz["symbol"])
                             or fraza in S.norm_kod(poz["nazwa"])):
                trafienia.append(poz)
            if len(trafienia) >= LIMIT_TRAFIEN:
                break
        for poz in trafienia:
            self.lista.insert("", tk.END, iid=str(poz["id"]),
                              values=(poz["symbol"], poz["nazwa"]))
        self.info.config(
            text="Pasujących kartotek: %d%s"
                 % (len(trafienia),
                    "  (pokazano pierwsze %d)" % LIMIT_TRAFIEN
                    if len(trafienia) >= LIMIT_TRAFIEN else ""))

    def _zapytaj_o_ilosc(self, domyslna=1):
        """Małe okno na liczbę sztuk. None = anulowano."""
        dlg = tk.Toplevel(self)
        dlg.title("Ilość na 1 detal")
        dlg.transient(self)
        dlg.resizable(False, False)
        wynik = {"ile": None}
        tk.Label(dlg, text="Ile sztuk półproduktu na 1 detal?",
                 font=("Arial", 9)).pack(padx=20, pady=(16, 6))
        var = tk.StringVar(value=str(domyslna))
        pole = tk.Spinbox(dlg, textvariable=var, from_=1, to=9999, width=8,
                          font=("Arial", 14), justify="center")
        pole.pack(pady=(0, 4))
        tk.Label(dlg, text="sztuki całkowite — „sztuka to sztuka”",
                 font=("Arial", 8), fg="#555").pack(padx=20)

        def zapisz():
            try:
                ile = int(float(var.get()))
            except ValueError:
                return messagebox.showwarning(
                    "Ilość", "Podaj liczbę sztuk.", parent=dlg)
            if ile < 1:
                return messagebox.showwarning(
                    "Ilość", "Ilość musi być większa od zera.", parent=dlg)
            wynik["ile"] = ile
            dlg.destroy()

        przyciski = tk.Frame(dlg)
        przyciski.pack(pady=(8, 14))
        tk.Button(przyciski, text="OK", command=zapisz, bg="#27ae60",
                  fg="white", font=("Arial", 9, "bold"), padx=18).pack(
                      side=tk.LEFT, padx=4)
        tk.Button(przyciski, text="Anuluj", command=dlg.destroy,
                  font=("Arial", 9), padx=12).pack(side=tk.LEFT, padx=4)
        dlg.bind("<Return>", lambda _e: zapisz())
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        _wysrodkuj(dlg, self, 320, 190)
        pole.focus_set()
        pole.selection_range(0, tk.END)
        dlg.grab_set()
        self.wait_window(dlg)
        return wynik["ile"]

    def _powiaz(self):
        sel = self.lista.selection()
        if not sel:
            return messagebox.showinfo(
                "Powiąż półprodukt",
                "Zaznacz na liście kartotekę półproduktu.", parent=self)
        poz = next((k for k in self._katalog if str(k["id"]) == sel[0]), None)
        if not poz:
            return
        try:
            ile = int(float(self.var_ile.get() or 1))
        except ValueError:
            ile = 0
        if ile < 1:
            return messagebox.showwarning(
                "Powiąż półprodukt",
                "Ilość na 1 detal musi być liczbą całkowitą większą od zera.",
                parent=self)

        # Powiązanie rysunku z samym sobą nie ma sensu i zapętliłoby
        # liczenie zapotrzebowania.
        if S.norm_kod(poz["symbol"]) == S.norm_kod(self.numer):
            return messagebox.showwarning(
                "Powiąż półprodukt",
                "To jest kartoteka TEGO SAMEGO detalu.\n\n"
                "Półprodukt to inna kartoteka — gotowa część, którą kupujesz\n"
                "i dopiero obrabiasz.", parent=self)

        try:
            M.zapisz_polprodukt(self.numer, poz["id"], ile,
                                symbol=poz["symbol"], nazwa=poz["nazwa"])
        except Exception as e:
            return messagebox.showerror("Powiąż półprodukt", str(e),
                                        parent=self)
        self._odswiez_powiazane()
        self.status.config(text="Powiązano: %s × %d szt. na 1 detal."
                                % (poz["symbol"], ile))


def otworz(parent, numer, opis=""):
    """Okno powiązania półproduktu. `numer` = klucz relacji (numer/nazwa)."""
    if not (numer or "").strip():
        messagebox.showinfo("Powiąż półprodukt",
                            "Ta pozycja nie ma numeru ani nazwy.",
                            parent=parent)
        return None
    return PolproduktWindow(parent, numer, opis)
