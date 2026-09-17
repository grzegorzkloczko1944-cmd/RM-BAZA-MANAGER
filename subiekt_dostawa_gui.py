# -*- coding: utf-8 -*-
"""Przyjęcie dostawy — DOSTAWA → PZ w Subiekcie (panel SUBIEKT, kafel 📦).

    import subiekt_dostawa_gui
    subiekt_dostawa_gui.open_window(arkusz)

Po co: towar wchodzi na stan, gdy PRZYJDZIE — nie gdy przyjdzie faktura.
Faktura pojawia się kilka dni później i tylko KONTROLUJE przyjęcie (okno
Faktury z KSeF dopina ją po numerze WZ). Bez tego okna magazynier nie miał
jak przyjąć paczki od QUAY, dopóki księgowość nie zaksięgowała FZ — i towar
wisiał poza stanem (pomiar 17.09.2026: FZ 24/09/2026, 53 pozycje, 0 na stanie).

Obieg (pamiec/project_obieg_przyjec_dostawa_pz.md):

    ZD → paczka + (WZ | nr zamówienia | własny ID) → DOSTAWA → PZ → stan

Dwa źródła pozycji — oba w jednym oknie (decyzja 18.09.2026):
  * OTWARTE ZD dostawcy: odhaczasz, co przyszło, ilość domyślnie = do
    realizacji. Sfera sama wiąże PZ z ZD (WypelnijNaPodstawieZD), więc
    zamówienie „schodzi" i kolejna dostawa widzi, ile zostało.
  * SPOZA ZD: dostawca dołożył coś ekstra albo zamiennik — pozycja
    z kartoteki, bez powiązania.

⚠️ WZ NIE JEST WYMAGANE — wielu dostawców go nie podaje. Wystarczy
dostawca i data; WZ / nr zamówienia / własny identyfikator są opcjonalne,
ale KTÓRYŚ warto wpisać, bo po nim faktura znajdzie to przyjęcie.

Co się zapisuje i gdzie:
  * DOSTAWA + pozycje       → master (`dostawy`, `dostawy_pozycje`) — zdarzenie
                              operacyjne: co przyszło, kiedy, kto odebrał
  * PZ                      → SUBIEKT (most `pz-utworz`); numer i Id PZ
                              wracają do `dostawy.pz_numer` / `pz_id`
  * relacja ZD ↔ PZ         → SUBIEKT sam (DokumentyRealizowane)

Kolejność zapisu jest celowa: najpierw DOSTAWA na serwerze, potem PZ. Gdy
most odrzuci PZ, dostawa zostaje ze statusem BLAD_PZ — widać ją w historii
i nic nie ginie. Odwrotnie (PZ bez dostawy) nie da się już domknąć.

Szata jak w oknie dokumentów (subiekt_dokumenty_gui) — jeden program,
nie zbiór narzędzi.
"""

import json
import os
import queue
import re
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

from rm_kreciolek import Kreciolek
from subiekt_stany import wysrodkuj, podepnij_szerokosci

try:
    from tksheet import Sheet
except ImportError:
    Sheet = None

# ── paleta: ta sama co subiekt_dokumenty_gui / ksef_faktury_gui ─────────────
GRANAT = "#34495e"
GRANAT_CIEMNY = "#2c3e50"
SZARY = "#ecf0f1"
TEKST = "#2c3e50"
TEKST_SZARY = "#7f8c8d"
NIEBIESKI = "#3498db"
ZIELONY = "#27ae60"
GRANAT_AKCJA = "#2980b9"
SZAROSC_AKCJA = "#95a5a6"
STAL = "#7f8c8d"
CZERWONY = "#c0392b"
POMARANCZ = "#f5b041"

FONT = ("Arial", 9)
FONT_S = ("Arial", 8)
FONT_B = ("Arial", 9, "bold")

#: Kolory wierszy ZD — jak legenda w oknie dokumentów.
KOL_ZD_CALE = "#d5f0dd"       # nic jeszcze nie przyjęto
KOL_ZD_CZESC = "#fdebd0"      # przyjęto część
KOL_ZD_ZERO = "#eaecee"       # zrealizowane — nic do przyjęcia
KOL_DODANE = "#d6eaf8"        # już na liście przyjęcia

DOST_WYBIERZ = "— wybierz dostawcę —"
MAGAZYN_DOMYSLNY = "MASTER"

KOL_ZD = [("zd", "ZD", 130), ("data", "Data ZD", 80), ("symbol", "Nr rysunku / symbol", 150),
          ("nazwa", "Nazwa", 220), ("zam", "Zamówiono", 85), ("doreal", "Do realizacji", 90),
          ("jm", "J.m.", 45), ("cena", "Cena netto", 80), ("projekt", "Projekt", 90)]

KOL_PRZ = [("symbol", "Nr rysunku / symbol", 150), ("nazwa", "Nazwa", 220),
           ("ilosc", "Ilość przyjęta", 90), ("jm", "J.m.", 45), ("cena", "Cena netto", 80),
           ("zd", "Z ZD", 130), ("doreal", "Do realizacji", 85)]
K_PRZ_ILOSC = 2
K_PRZ_CENA = 4

KOL_HIST = [("id", "Nr", 45), ("data", "Data", 80), ("dostawca", "Dostawca", 170),
            ("wz", "WZ dostawcy", 110), ("zam", "Nr zamówienia", 100), ("ident", "Identyfikator", 100),
            ("pz", "PZ w Subiekcie", 150), ("status", "Status", 90), ("poz", "Poz.", 45),
            ("kto", "Przyjął", 80), ("kiedy", "Zapisano", 120)]

STATUS_KOLOR = {"PZ": "#d5f0dd", "BLAD_PZ": "#fdebd0", "PRZYJMOWANA": "#eaecee", "BEZ_PZ": "#fdebd0"}


def _kto():
    return os.environ.get("USERNAME") or "?"


def _liczba(x, domyslne=0.0):
    try:
        return float(str(x).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return domyslne


def _il(x):
    try:
        f = float(x)
        return str(int(f)) if f == int(f) else f"{f:g}"
    except (TypeError, ValueError):
        return str(x or "")


def _zl(x):
    try:
        return f"{float(x):,.2f}".replace(",", " ").replace(".", ",")
    except (TypeError, ValueError):
        return ""


class OknoDostawa(tk.Toplevel, Kreciolek):

    def __init__(self, parent):
        super().__init__(parent)
        self.parent_app = parent
        self.title("Przyjęcie dostawy — DOSTAWA → PZ w Subiekcie")
        self.geometry("1450x860")
        self.minsize(1100, 650)
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

        self.kontrahenci = []          # [{"Id","NazwaSkrocona","NIP"}]
        self.dokumenty = []            # wszystkie z mostu (ZD i reszta)
        self.katalog = []              # [{"id","symbol","nazwa","opis","cena"}]
        self.dostawcy_rm = {}          # nip -> supplier_id (z RM_BAZA)
        self.most_ok = None
        self._zd_wiersze = []          # wiersze tabeli ZD (dicty)
        self._przyjecie = []           # wiersze tabeli przyjęcia (dicty)
        self._historia = []
        self._wyniki = queue.Queue()

        self._buduj()
        self._pompuj()
        self.after(100, self._start_tla)
        wysrodkuj(self, parent)

    # ── UI ─────────────────────────────────────────────────────────────────
    def _buduj(self):
        top = tk.Frame(self, bg=GRANAT, height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="📦 Przyjęcie dostawy — DOSTAWA → PZ w Subiekcie",
                 bg=GRANAT, fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)
        self.lbl_most = tk.Label(top, text="most: sprawdzam…", bg=GRANAT, fg=POMARANCZ,
                                 font=("Arial", 9, "bold"))
        self.lbl_most.pack(side=tk.LEFT, padx=(16, 0))
        self.btn_odswiez = tk.Button(top, text="🔄 Odśwież ZD", command=self._start_tla,
                                     bg=NIEBIESKI, fg="white", font=FONT_S, padx=8, pady=2,
                                     relief=tk.RAISED, bd=1, cursor="hand2")
        self.btn_odswiez.pack(side=tk.RIGHT, padx=10, pady=8)

        # ── pasek nagłówka dostawy ──
        f = tk.Frame(self, bg=SZARY)
        f.pack(side=tk.TOP, fill=tk.X)

        def pole(etykieta, szer, var=None):
            tk.Label(f, text=etykieta, bg=SZARY, font=FONT).pack(side=tk.LEFT, padx=(12, 3), pady=6)
            e = tk.Entry(f, textvariable=var, width=szer, font=FONT)
            e.pack(side=tk.LEFT, pady=6)
            return e

        tk.Label(f, text="Dostawca:", bg=SZARY, font=FONT).pack(side=tk.LEFT, padx=(12, 3), pady=6)
        self.var_dostawca = tk.StringVar(value=DOST_WYBIERZ)
        self.cmb_dost = ttk.Combobox(f, textvariable=self.var_dostawca, width=34,
                                     state="readonly", font=FONT, values=[DOST_WYBIERZ])
        self.cmb_dost.pack(side=tk.LEFT, pady=6)
        self.cmb_dost.bind("<<ComboboxSelected>>", lambda _e: self._wypelnij_zd())

        self.var_data = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        pole("Data przyjęcia:", 11, self.var_data)
        tk.Label(f, text="Magazyn:", bg=SZARY, font=FONT).pack(side=tk.LEFT, padx=(12, 3), pady=6)
        self.var_magazyn = tk.StringVar(value=MAGAZYN_DOMYSLNY)
        self.cmb_mag = ttk.Combobox(f, textvariable=self.var_magazyn, width=10, font=FONT,
                                    values=[MAGAZYN_DOMYSLNY])
        self.cmb_mag.pack(side=tk.LEFT, pady=6)
        self.var_wz = tk.StringVar()
        pole("WZ dostawcy:", 14, self.var_wz)
        self.var_zam = tk.StringVar()
        pole("Nr zamówienia dost.:", 12, self.var_zam)
        self.var_ident = tk.StringVar()
        pole("Identyfikator własny:", 12, self.var_ident)
        tk.Label(f, text="(WZ / zamówienie / identyfikator — któryś warto, żeby faktura znalazła przyjęcie)",
                 bg=SZARY, fg=TEKST_SZARY, font=FONT_S).pack(side=tk.LEFT, padx=(8, 0))

        self.summary = tk.Label(self, text="Wczytywanie…", bg=SZARY, fg=TEKST, font=FONT,
                                anchor="w", padx=12, pady=6)
        self.summary.pack(side=tk.TOP, fill=tk.X)

        leg = tk.Frame(self, bg=SZARY)
        leg.pack(side=tk.TOP, fill=tk.X)
        tk.Label(leg, text="Legenda:", bg=SZARY, fg=TEKST_SZARY,
                 font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=(12, 6), pady=(0, 5))
        for kolor, opis in ((KOL_ZD_CALE, "pozycja ZD w całości do przyjęcia"),
                            (KOL_ZD_CZESC, "przyjęto część — reszta czeka"),
                            (KOL_ZD_ZERO, "zrealizowana — nic do przyjęcia"),
                            (KOL_DODANE, "już na liście przyjęcia")):
            tk.Label(leg, text="  ", bg=kolor, relief=tk.SOLID, bd=1).pack(side=tk.LEFT, padx=(6, 3), pady=(0, 5))
            tk.Label(leg, text=opis, bg=SZARY, fg=TEKST, font=FONT_S).pack(side=tk.LEFT, pady=(0, 5))
        tk.Label(leg, text="Ilość i cenę w tabeli przyjęcia edytujesz dwuklikiem.",
                 bg=SZARY, fg=TEKST_SZARY, font=FONT_S).pack(side=tk.LEFT, padx=(16, 0), pady=(0, 5))

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 4))
        karta = tk.Frame(self.nb)
        self.nb.add(karta, text="Przyjęcie")
        hist = tk.Frame(self.nb)
        self.nb.add(hist, text="Historia przyjęć")
        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self._na_zmiane_karty())

        paned = ttk.PanedWindow(karta, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
        lewy = tk.Frame(paned)
        prawy = tk.Frame(paned)
        paned.add(lewy, weight=5)
        paned.add(prawy, weight=4)

        # ── lewa: otwarte ZD dostawcy ──
        pl = tk.Frame(lewy, bg=GRANAT)
        pl.pack(side=tk.TOP, fill=tk.X)
        self.lbl_zd = tk.Label(pl, text="Otwarte ZD dostawcy — zaznacz, co przyszło",
                               bg=GRANAT, fg="white", font=FONT_B, anchor="w", padx=10, pady=4)
        self.lbl_zd.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.var_zrealizowane = tk.BooleanVar(value=False)
        tk.Checkbutton(pl, text="pokaż zrealizowane", variable=self.var_zrealizowane,
                       command=self._wypelnij_zd, bg=GRANAT, fg="white", selectcolor=GRANAT_CIEMNY,
                       activebackground=GRANAT, activeforeground="white",
                       font=FONT_S).pack(side=tk.RIGHT, padx=(6, 10))
        tk.Button(pl, text="➕ Dodaj zaznaczone →", command=self._dodaj_z_zd, bg=ZIELONY,
                  fg="white", font=FONT_S, padx=8, pady=2, relief=tk.RAISED, bd=1,
                  cursor="hand2").pack(side=tk.RIGHT, padx=(0, 4), pady=3)
        tk.Button(pl, text="➕ Całe ZD →", command=lambda: self._dodaj_z_zd(cale_zd=True),
                  bg=GRANAT_AKCJA, fg="white", font=FONT_S, padx=8, pady=2, relief=tk.RAISED,
                  bd=1, cursor="hand2").pack(side=tk.RIGHT, padx=(0, 4), pady=3)

        if Sheet is None:
            tk.Label(lewy, text="Brak biblioteki tksheet", fg=CZERWONY).pack(pady=20)
            self.sheet_zd = self.sheet_prz = self.sheet_hist = None
            return
        self.sheet_zd = Sheet(lewy, headers=[k[1] for k in KOL_ZD], column_width=110, theme="light blue")
        self._ustaw_arkusz(self.sheet_zd, "dostawa_zd", KOL_ZD)
        self.sheet_zd.bind("<Double-Button-1>", lambda _e: self._dodaj_z_zd(), add="+")
        self.sheet_zd.pack(fill=tk.BOTH, expand=True)

        # ── prawa: pozycje przyjęcia ──
        pp = tk.Frame(prawy, bg=GRANAT)
        pp.pack(side=tk.TOP, fill=tk.X)
        self.lbl_prz = tk.Label(pp, text="Pozycje przyjęcia (0)", bg=GRANAT, fg="white",
                                font=FONT_B, anchor="w", padx=10, pady=4)
        self.lbl_prz.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(pp, text="🗑 Usuń zaznaczone", command=self._usun_z_przyjecia, bg=SZAROSC_AKCJA,
                  fg="white", font=FONT_S, padx=8, pady=2, relief=tk.RAISED, bd=1,
                  cursor="hand2").pack(side=tk.RIGHT, padx=(0, 10), pady=3)
        tk.Button(pp, text="➕ Spoza ZD (z kartoteki)", command=self._dodaj_spoza_zd, bg=STAL,
                  fg="white", font=FONT_S, padx=8, pady=2, relief=tk.RAISED, bd=1,
                  cursor="hand2").pack(side=tk.RIGHT, padx=(0, 4), pady=3)

        self.sheet_prz = Sheet(prawy, headers=[k[1] for k in KOL_PRZ], column_width=110,
                               theme="light green")
        self._ustaw_arkusz(self.sheet_prz, "dostawa_przyjecie", KOL_PRZ, edytowalny=True)
        try:
            self.sheet_prz.readonly_columns(columns=[i for i in range(len(KOL_PRZ))
                                                     if i not in (K_PRZ_ILOSC, K_PRZ_CENA)])
        except Exception:
            pass
        self.sheet_prz.pack(fill=tk.BOTH, expand=True)

        dol = tk.Frame(prawy, bg="white", highlightthickness=1, highlightbackground="#bdc3c7")
        dol.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Label(dol, text="Uwagi do PZ:", bg="white", fg=TEKST_SZARY, font=FONT_S).grid(
            row=0, column=0, sticky="w", padx=(10, 6), pady=6)
        self.var_uwagi = tk.StringVar()
        tk.Entry(dol, textvariable=self.var_uwagi, font=FONT, relief=tk.SOLID, bd=1).grid(
            row=0, column=1, sticky="ew", pady=6)
        dol.columnconfigure(1, weight=1)
        self.btn_przyjmij = tk.Button(dol, text="✔ Przyjmij dostawę → PZ w Subiekcie",
                                      command=self._przyjmij, bg=GRANAT_AKCJA, fg="white",
                                      disabledforeground="#bdc3c7", font=FONT_B, padx=14, pady=6,
                                      relief=tk.RAISED, bd=1, cursor="hand2")
        self.btn_przyjmij.grid(row=0, column=2, padx=10, pady=6)
        self.lbl_plan = tk.Label(dol, text="", bg=SZARY, fg=TEKST, font=FONT_S, anchor="w",
                                 justify="left", padx=10, pady=4)
        self.lbl_plan.grid(row=1, column=0, columnspan=3, sticky="ew")

        # ── historia ──
        ph = tk.Frame(hist, bg=GRANAT)
        ph.pack(side=tk.TOP, fill=tk.X)
        tk.Label(ph, text="Przyjęte dostawy — kliknij, żeby zobaczyć pozycje", bg=GRANAT,
                 fg="white", font=FONT_B, anchor="w", padx=10, pady=4).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(ph, text="🔁 Ponów PZ dla zaznaczonej", command=self._ponow_pz, bg=POMARANCZ,
                  fg="#7d3c00", font=FONT_S, padx=8, pady=2, relief=tk.RAISED, bd=1,
                  cursor="hand2").pack(side=tk.RIGHT, padx=(0, 10), pady=3)
        hp = ttk.PanedWindow(hist, orient=tk.VERTICAL)
        hp.pack(fill=tk.BOTH, expand=True)
        h1 = tk.Frame(hp)
        h2 = tk.Frame(hp)
        hp.add(h1, weight=3)
        hp.add(h2, weight=2)
        self.sheet_hist = Sheet(h1, headers=[k[1] for k in KOL_HIST], column_width=100, theme="light blue")
        self._ustaw_arkusz(self.sheet_hist, "dostawa_historia", KOL_HIST)
        self.sheet_hist.bind("<ButtonRelease-1>", self._wybrano_historie, add="+")
        self.sheet_hist.pack(fill=tk.BOTH, expand=True)
        tk.Label(h2, text="Pozycje dostawy", bg=GRANAT, fg="white", font=FONT_B, anchor="w",
                 padx=10, pady=4).pack(side=tk.TOP, fill=tk.X)
        self.sheet_hist_poz = Sheet(h2, headers=[k[1] for k in KOL_PRZ], column_width=110,
                                    theme="light green")
        self._ustaw_arkusz(self.sheet_hist_poz, "dostawa_historia_poz", KOL_PRZ)
        self.sheet_hist_poz.pack(fill=tk.BOTH, expand=True)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3, bg=GRANAT, fg=SZARY, font=FONT_S)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        # Plan PRZED ma odzwierciedlać pola nagłówka NA BIEŻĄCO — inaczej
        # ostrzeżenie „bez WZ…" wisiało po wpisaniu WZ (zrzut 18.09.2026).
        for v in (self.var_wz, self.var_zam, self.var_ident, self.var_magazyn, self.var_data):
            v.trace_add("write", lambda *_a: self._odswiez_plan())

    def _ustaw_arkusz(self, sheet, klucz, kolumny, edytowalny=False):
        sheet.set_options(show_selected_cells_border=True, enable_edit_cell_auto_resize=False,
                          empty_horizontal=0, empty_vertical=0)
        sheet.hide("row_index")
        bind = ["single_select", "drag_select", "ctrl_select", "select_all", "column_width_resize",
                "arrowkeys", "right_click_popup_menu", "rc_select", "copy"]
        if edytowalny:
            bind += ["edit_cell"]
        sheet.enable_bindings(tuple(bind))
        podepnij_szerokosci(self, sheet, klucz, [k[2] for k in kolumny])

    # ── wątki ──────────────────────────────────────────────────────────────
    def _pompuj(self):
        try:
            while True:
                fn = self._wyniki.get_nowait()
                try:
                    fn()
                except Exception as e:
                    print(f"⚠️  dostawa_gui: {type(e).__name__}: {e}")
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._pompuj)

    def _w_tle(self, praca, potem):
        def run():
            try:
                w = praca()
                self._wyniki.put(lambda: potem(w, None))
            except Exception as e:
                self._wyniki.put(lambda: potem(None, e))
        threading.Thread(target=run, daemon=True).start()

    def _start_tla(self):
        self.btn_odswiez.config(state=tk.DISABLED)
        self.start_kreciolek("Pytam Subiekta o kontrahentów, ZD i kartotekę")

        def praca():
            import subiekt_bridge
            import subiekt_dokumenty_gui
            import rm_klient
            w = {}
            subiekt_bridge.zapewnij_most()
            k = subiekt_bridge.call("kontrahenci", {}, timeout=60)
            w["kontrahenci"] = (k or {}).get("kontrahenci", [])
            # Limit duży: ucięcie odcina STARSZE dokumenty, a otwarte ZD bywają
            # sprzed miesięcy (pamiec: „bez limitu Take() na dokumentach").
            w["dokumenty"] = subiekt_dokumenty_gui.pobierz_dokumenty(limit=2000)
            kat = subiekt_bridge.call("katalog", {}, timeout=120)
            w["katalog"] = [{"id": p.get("Id"), "symbol": (p.get("Symbol") or "").strip(),
                             "nazwa": (p.get("Nazwa") or "").strip(),
                             "opis": (p.get("Opis") or "").strip(),
                             "cena": float(p.get("CenaEwidencyjna") or 0)}
                            for p in (kat or {}).get("pozycje", [])]
            try:
                w["dostawcy_rm"] = {re.sub(r"\D", "", r.get("nip") or ""): r["supplier_id"]
                                    for r in rm_klient.master_read("suppliers-z-nip")}
            except Exception:
                w["dostawcy_rm"] = {}
            return w

        self._w_tle(praca, self._tlo_gotowe)

    def _tlo_gotowe(self, w, blad):
        self.stop_kreciolek()
        self.btn_odswiez.config(state=tk.NORMAL)
        if blad or not w:
            self.most_ok = False
            self.lbl_most.config(text="⚠ most niedostępny — bez mostu nie da się przyjąć dostawy", fg=POMARANCZ)
            self.status.config(text=f"Most: {blad}")
            self.summary.config(text="Bez mostu do Subiekta okno nie może ani czytać ZD, ani wystawić PZ.")
            return
        self.most_ok = True
        self.lbl_most.config(text="most: ONLINE", fg="#a9dfbf")
        self.kontrahenci = [k for k in w["kontrahenci"] if (k.get("NazwaSkrocona") or "").strip()]
        self.dokumenty = w["dokumenty"]
        self.katalog = w["katalog"]
        self.dostawcy_rm = w.get("dostawcy_rm", {})

        zd = [d for d in self.dokumenty if d["rodzaj"] == "ZD"]
        # Dostawcy do wyboru: najpierw ci z OTWARTYMI ZD (u nich coś przyjdzie),
        # potem reszta kontrahentów — dostawa bez ZD też się zdarza.
        z_zd = []
        for d in zd:
            if d["podmiot"] and d["podmiot"] not in z_zd and any(p.get("do_realizacji", 0) > 0 for p in d["pozycje"]):
                z_zd.append(d["podmiot"])
        reszta = sorted({k["NazwaSkrocona"].strip() for k in self.kontrahenci} - set(z_zd))
        wartosci = [DOST_WYBIERZ] + [f"{n}   (otwarte ZD)" for n in sorted(z_zd)] + reszta
        self.cmb_dost["values"] = wartosci
        magazyny = sorted({d["magazyn"] for d in zd if d.get("magazyn")} | {MAGAZYN_DOMYSLNY})
        self.cmb_mag["values"] = magazyny
        self.summary.config(text=(
            f"Kontrahentów: {len(self.kontrahenci)}    ZD w Subiekcie: {len(zd)}"
            f"    dostawców z otwartymi ZD: {len(z_zd)}    kartotek: {len(self.katalog)}"))
        self.status.config(text="Wybierz dostawcę.")
        self._wypelnij_zd()
        if self._historia:
            self._wypelnij_historie()

    # ── dostawca / ZD ──────────────────────────────────────────────────────
    def _nazwa_dostawcy(self):
        v = self.var_dostawca.get()
        if v == DOST_WYBIERZ:
            return ""
        return v.split("   (otwarte ZD)")[0].strip()

    def _kontrahent(self):
        n = self._nazwa_dostawcy()
        return next((k for k in self.kontrahenci if (k.get("NazwaSkrocona") or "").strip() == n), None)

    def _wypelnij_zd(self):
        if self.sheet_zd is None:
            return
        nazwa = self._nazwa_dostawcy()
        pokaz_zreal = self.var_zrealizowane.get()
        dodane = {(r["zd_id"], r["zd_pozycja_id"]) for r in self._przyjecie if r.get("zd_pozycja_id")}
        wiersze, dane, kolory = [], [], []
        for d in self.dokumenty:
            if d["rodzaj"] != "ZD" or (d["podmiot"] or "").strip() != nazwa:
                continue
            if "anulowan" in (d.get("status") or "").lower():
                continue
            for p in d["pozycje"]:
                doreal = float(p.get("do_realizacji") or 0)
                if doreal <= 0 and not pokaz_zreal:
                    continue
                w = {"zd_id": d["Id"], "zd_numer": d["numer"], "zd_data": d["data"],
                     "zd_magazyn": d.get("magazyn") or "", "symbol": p["symbol"], "nazwa": p["nazwa"],
                     "ilosc_zd": float(p["ilosc"]), "do_realizacji": doreal, "jm": p["jm"],
                     "cena": float(p.get("cena") or 0), "projekt": p.get("projekt") or "",
                     "zd_pozycja_id": int(p.get("id") or 0)}
                wiersze.append(w)
                dane.append([w["zd_numer"], w["zd_data"], w["symbol"], w["nazwa"], _il(w["ilosc_zd"]),
                             _il(doreal), w["jm"], _zl(w["cena"]), w["projekt"]])
                if (w["zd_id"], w["zd_pozycja_id"]) in dodane:
                    kolory.append(KOL_DODANE)
                elif doreal <= 0:
                    kolory.append(KOL_ZD_ZERO)
                elif doreal < w["ilosc_zd"]:
                    kolory.append(KOL_ZD_CZESC)
                else:
                    kolory.append(KOL_ZD_CALE)
        self._zd_wiersze = wiersze
        try:
            self.sheet_zd.dehighlight_all()
        except Exception:
            pass
        self.sheet_zd.set_sheet_data(dane, reset_col_positions=False, redraw=False)
        for i, k in enumerate(kolory):
            self.sheet_zd.highlight_cells(row=i, column=0, bg=k)
            self.sheet_zd.highlight_cells(row=i, column=5, bg=k)
        self.sheet_zd.redraw()
        zd_n = len({w["zd_id"] for w in wiersze})
        self.lbl_zd.config(text=(f"Otwarte ZD dostawcy: {zd_n} dok., {len(wiersze)} poz. — zaznacz, co przyszło"
                                 if nazwa else "Otwarte ZD dostawcy — najpierw wybierz dostawcę"))
        # Magazyn z ZD dostawcy — najczęstszy, żeby PZ trafiło tam, gdzie zamówienie.
        if wiersze and self.var_magazyn.get() == MAGAZYN_DOMYSLNY:
            mag = max({w["zd_magazyn"] for w in wiersze if w["zd_magazyn"]} or {MAGAZYN_DOMYSLNY},
                      key=lambda m: sum(1 for w in wiersze if w["zd_magazyn"] == m))
            self.var_magazyn.set(mag)
        # Brak kontrahenta w Subiekcie = PZ nie powstanie; mówimy od razu.
        k = self._kontrahent()
        if nazwa and not k:
            self.status.config(text=f"⚠ „{nazwa}” nie ma w kontrahentach Subiekta — PZ się nie wystawi.")
        elif nazwa:
            self.status.config(text=f"Dostawca: {nazwa} (Id {k.get('Id')}, NIP {k.get('NIP') or '—'}).")
        self._odswiez_plan()

    def _zaznaczone_zd(self):
        try:
            return sorted(set(self.sheet_zd.get_selected_rows(get_cells_as_rows=True)))
        except Exception:
            return []

    def _dodaj_z_zd(self, cale_zd=False):
        if not self._zd_wiersze:
            return
        idx = self._zaznaczone_zd()
        if not idx:
            messagebox.showinfo("Przyjęcie", "Zaznacz pozycje ZD, które przyszły.", parent=self)
            return
        if cale_zd:
            zd_ids = {self._zd_wiersze[i]["zd_id"] for i in idx if i < len(self._zd_wiersze)}
            idx = [i for i, w in enumerate(self._zd_wiersze) if w["zd_id"] in zd_ids]
        juz = {(r["zd_id"], r["zd_pozycja_id"]) for r in self._przyjecie if r.get("zd_pozycja_id")}
        dodano, pominieto = 0, 0
        for i in idx:
            if i >= len(self._zd_wiersze):
                continue
            w = self._zd_wiersze[i]
            if (w["zd_id"], w["zd_pozycja_id"]) in juz or w["do_realizacji"] <= 0:
                pominieto += 1
                continue
            self._przyjecie.append({
                "symbol": w["symbol"], "nazwa": w["nazwa"], "ilosc": w["do_realizacji"],
                "jm": w["jm"], "cena": w["cena"], "zd_numer": w["zd_numer"], "zd_id": w["zd_id"],
                "zd_pozycja_id": w["zd_pozycja_id"], "ilosc_zd": w["ilosc_zd"],
                "do_realizacji": w["do_realizacji"], "asortyment_id": None})
            dodano += 1
        self._wypelnij_przyjecie()
        self._wypelnij_zd()
        self.status.config(text=f"Dodano {dodano} poz. z ZD" + (f", pominięto {pominieto} (już na liście / zrealizowane)" if pominieto else "."))

    def _dodaj_spoza_zd(self):
        """Pozycja z kartoteki bez ZD — dostawca dołożył coś ekstra."""
        if not self.katalog:
            messagebox.showwarning("Kartoteka", "Kartoteka jeszcze się nie wczytała.", parent=self)
            return
        dlg = tk.Toplevel(self)
        dlg.title("Pozycja spoza ZD — z kartoteki Subiekta")
        dlg.transient(self)
        dlg.grab_set()
        tk.Label(dlg, text="Szukaj po symbolu / nazwie:", font=FONT).pack(anchor="w", padx=12, pady=(10, 2))
        var = tk.StringVar()
        e = tk.Entry(dlg, textvariable=var, font=FONT, width=50)
        e.pack(fill=tk.X, padx=12)
        lb = tk.Listbox(dlg, height=12, font=FONT, activestyle="none", selectbackground="#b3d1ec",
                        selectforeground=TEKST)
        lb.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        kand = []

        def szukaj(_e=None):
            fraza = var.get().strip().lower()
            lb.delete(0, tk.END)
            kand.clear()
            if len(fraza) < 2:
                return
            for k in self.katalog:
                if fraza in k["symbol"].lower() or fraza in k["nazwa"].lower():
                    kand.append(k)
                    lb.insert(tk.END, f"{k['symbol']}   —   {k['nazwa']}" + (f"   [{k['opis']}]" if k['opis'] else ""))
                    if len(kand) >= 80:
                        break

        d2 = tk.Frame(dlg)
        d2.pack(fill=tk.X, padx=12, pady=(0, 10))
        tk.Label(d2, text="Ilość:", font=FONT).pack(side=tk.LEFT)
        var_il = tk.StringVar(value="1")
        tk.Entry(d2, textvariable=var_il, width=8, font=FONT).pack(side=tk.LEFT, padx=(4, 12))
        tk.Label(d2, text="Cena netto:", font=FONT).pack(side=tk.LEFT)
        var_c = tk.StringVar(value="")
        tk.Entry(d2, textvariable=var_c, width=10, font=FONT).pack(side=tk.LEFT, padx=(4, 12))

        def dodaj(_e=None):
            sel = lb.curselection()
            if not sel:
                return
            k = kand[sel[0]]
            il = _liczba(var_il.get(), 0)
            if il <= 0:
                messagebox.showwarning("Ilość", "Ilość musi być dodatnia.", parent=dlg)
                return
            cena = _liczba(var_c.get(), k["cena"]) if var_c.get().strip() else k["cena"]
            self._przyjecie.append({
                "symbol": k["symbol"], "nazwa": k["nazwa"], "ilosc": il, "jm": "szt",
                "cena": cena, "zd_numer": "", "zd_id": None, "zd_pozycja_id": None,
                "ilosc_zd": None, "do_realizacji": None, "asortyment_id": k["id"]})
            self._wypelnij_przyjecie()
            dlg.destroy()

        tk.Button(d2, text="➕ Dodaj", command=dodaj, bg=ZIELONY, fg="white", font=FONT_S,
                  padx=10, pady=2, relief=tk.RAISED, bd=1).pack(side=tk.RIGHT)
        e.bind("<KeyRelease>", szukaj)
        lb.bind("<Double-1>", dodaj)
        lb.bind("<Return>", dodaj)
        e.focus_set()
        wysrodkuj(dlg, self, 620, 420)

    def _usun_z_przyjecia(self):
        self._zczytaj_edycje()
        try:
            idx = sorted(set(self.sheet_prz.get_selected_rows(get_cells_as_rows=True)), reverse=True)
        except Exception:
            idx = []
        for i in idx:
            if i < len(self._przyjecie):
                del self._przyjecie[i]
        self._wypelnij_przyjecie()
        self._wypelnij_zd()

    def _wypelnij_przyjecie(self):
        if self.sheet_prz is None:
            return
        dane = [[r["symbol"], r["nazwa"], _il(r["ilosc"]), r["jm"], _zl(r["cena"]),
                 r["zd_numer"] or "(spoza ZD)", _il(r["do_realizacji"]) if r["do_realizacji"] is not None else ""]
                for r in self._przyjecie]
        try:
            self.sheet_prz.dehighlight_all()
        except Exception:
            pass
        self.sheet_prz.set_sheet_data(dane, reset_col_positions=False, redraw=False)
        for i, r in enumerate(self._przyjecie):
            if not r.get("zd_id"):
                self.sheet_prz.highlight_cells(row=i, column=5, bg=KOL_ZD_CZESC, fg="#7d3c00")
        self.sheet_prz.redraw()
        self.lbl_prz.config(text=f"Pozycje przyjęcia ({len(self._przyjecie)})")
        self._odswiez_plan()

    def _zczytaj_edycje(self):
        """Ilość i cena wpisane w arkuszu → do `_przyjecie`."""
        if self.sheet_prz is None:
            return
        try:
            dane = self.sheet_prz.get_sheet_data()
        except Exception:
            return
        for i, r in enumerate(self._przyjecie):
            if i >= len(dane):
                break
            r["ilosc"] = _liczba(dane[i][K_PRZ_ILOSC], r["ilosc"])
            r["cena"] = _liczba(dane[i][K_PRZ_CENA], r["cena"])

    def _odswiez_plan(self):
        n = len(self._przyjecie)
        z_zd = sum(1 for r in self._przyjecie if r.get("zd_id"))
        zd = sorted({r["zd_numer"] for r in self._przyjecie if r.get("zd_numer")})
        if not n:
            self.lbl_plan.config(text="Dodaj pozycje z ZD po lewej albo spoza ZD.", bg=SZARY)
            return
        linie = [f"PZ w Subiekcie: {n} poz. ({z_zd} z ZD {', '.join(zd) if zd else ''}"
                 f"{', ' if zd and n - z_zd else ''}{f'{n - z_zd} spoza ZD' if n - z_zd else ''}),"
                 f" magazyn {self.var_magazyn.get()}, data {self.var_data.get()}."]
        if z_zd:
            linie.append("Subiekt sam powiąże PZ z ZD (realizacja) — zamówienie zejdzie o przyjęte ilości.")
        if not (self.var_wz.get().strip() or self.var_zam.get().strip() or self.var_ident.get().strip()):
            linie.append("⚠️ Bez WZ / nr zamówienia / identyfikatora faktura nie znajdzie tego przyjęcia automatycznie.")
        self.lbl_plan.config(text="\n".join(linie), bg="#fdf2e6" if any(l.startswith("⚠️") for l in linie) else SZARY)

    # ── przyjęcie → DOSTAWA + PZ ───────────────────────────────────────────
    def _przyjmij(self):
        self._zczytaj_edycje()
        nazwa = self._nazwa_dostawcy()
        k = self._kontrahent()
        if not nazwa or not k:
            messagebox.showwarning("Przyjęcie", "Wybierz dostawcę, który jest kontrahentem w Subiekcie.", parent=self)
            return
        if not self._przyjecie:
            messagebox.showwarning("Przyjęcie", "Brak pozycji do przyjęcia.", parent=self)
            return
        zle = [r["symbol"] for r in self._przyjecie if r["ilosc"] <= 0]
        if zle:
            messagebox.showwarning("Przyjęcie", "Ilość musi być dodatnia:\n" + ", ".join(zle), parent=self)
            return
        try:
            datetime.strptime(self.var_data.get().strip(), "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("Przyjęcie", "Data przyjęcia w formacie RRRR-MM-DD.", parent=self)
            return
        nadwyzki = [f"{r['symbol']} ({_il(r['ilosc'])} > {_il(r['do_realizacji'])})"
                    for r in self._przyjecie if r.get("zd_id") and r["ilosc"] > (r["do_realizacji"] or 0)]

        # PRZED — pełna lista tego, co powstanie (zasada: nic po cichu).
        wiersze = "\n".join(f"  {_il(r['ilosc'])} {r['jm']}  {r['symbol']}  — {r['nazwa'][:40]}"
                            f"{'  [ZD ' + r['zd_numer'] + ']' if r.get('zd_numer') else '  [spoza ZD]'}"
                            for r in self._przyjecie[:25])
        if len(self._przyjecie) > 25:
            wiersze += f"\n  … i {len(self._przyjecie) - 25} więcej"
        tresc = (f"Dostawca: {nazwa}\nData przyjęcia: {self.var_data.get()}    Magazyn: {self.var_magazyn.get()}\n"
                 f"WZ: {self.var_wz.get() or '—'}    Nr zam.: {self.var_zam.get() or '—'}    "
                 f"Identyfikator: {self.var_ident.get() or '—'}\n\nPozycje ({len(self._przyjecie)}):\n{wiersze}\n\n")
        if nadwyzki:
            tresc += "⚠️ Ilość większa niż do realizacji na ZD:\n  " + "\n  ".join(nadwyzki) + "\n\n"
        tresc += "Powstanie PZ w Subiekcie — dokumentu nie da się cofnąć z RM_BAZA.\nWystawić?"
        if not messagebox.askyesno("Przyjęcie dostawy — PRZED zapisem", tresc, parent=self):
            return

        plan = self._plan_pz(k)
        naglowek = {
            "supplier_id": self.dostawcy_rm.get(re.sub(r"\D", "", k.get("NIP") or "")),
            "nip": re.sub(r"\D", "", k.get("NIP") or ""), "dostawca": nazwa,
            "data_przyjecia": self.var_data.get().strip(),
            "identyfikator_wlasny": self.var_ident.get().strip(),
            "nr_wz_dostawcy": self.var_wz.get().strip(), "nr_zamowienia": self.var_zam.get().strip(),
            "magazyn": self.var_magazyn.get().strip() or MAGAZYN_DOMYSLNY,
            "status": "PRZYJMOWANA", "zrodlo_przyjecia": "NORMALNE",
            "uwagi": self.var_uwagi.get().strip(), "kto": _kto(),
            "kiedy": datetime.now().isoformat(timespec="seconds")}
        pozycje = [dict(r) for r in self._przyjecie]
        self.btn_przyjmij.config(state=tk.DISABLED)
        self.start_kreciolek("Suchy przebieg w Subiekcie")

        def praca():
            import subiekt_bridge
            import rm_klient
            wynik = {}
            # 1. suchy przebieg — Subiekt sprawdza ZD, pozycje, kartoteki
            suchy = subiekt_bridge.call("pz-utworz", {"plan": plan}, timeout=120)
            bledy = [k_ for k_ in (suchy or {}).get("kroki", []) if k_.get("Status") == "blad"]
            if bledy:
                wynik["suchy_bledy"] = bledy
                return wynik
            # 2. DOSTAWA na serwerze — PRZED PZ, żeby nic nie zginęło
            self._wyniki.put(lambda: self.tekst_kreciolka("Zapisuję dostawę na serwerze"))
            r = rm_klient.master_exec("dostawa-zapisz", naglowek)
            dostawa_id = (r or {}).get("lastrowid")
            wynik["dostawa_id"] = dostawa_id
            for p in pozycje:
                rm_klient.master_exec("dostawa-pozycja-zapisz", {
                    "dostawa_id": dostawa_id, "symbol": p["symbol"], "nazwa": p["nazwa"],
                    "asortyment_id": p.get("asortyment_id"), "ilosc": p["ilosc"], "jednostka": p["jm"],
                    "cena": p["cena"], "zd_numer": p.get("zd_numer") or None, "zd_id": p.get("zd_id"),
                    "zd_pozycja_id": p.get("zd_pozycja_id"), "ilosc_zd": p.get("ilosc_zd")})
            # 3. PZ w Subiekcie — ZAPIS, bez ponawiania
            self._wyniki.put(lambda: self.tekst_kreciolka("Wystawiam PZ w Subiekcie"))
            plan["uwagi"] = f"DOSTAWA {dostawa_id}" + (f" WZ {naglowek['nr_wz_dostawcy']}" if naglowek["nr_wz_dostawcy"] else "") \
                            + (f"\n{naglowek['uwagi']}" if naglowek["uwagi"] else "")
            odp = subiekt_bridge.call("pz-utworz", {"plan": plan, "zapisz": True}, timeout=180, write=True)
            wynik["pz"] = odp or {}
            numer = (odp or {}).get("numer") or ""
            status = "PZ" if (odp or {}).get("zapisano") else "BLAD_PZ"
            rm_klient.master_exec("dostawa-pz-ustaw", {
                "pz_numer": numer or None, "pz_id": (odp or {}).get("pzId"), "status": status, "id": dostawa_id})
            wynik["status"] = status
            return wynik

        self._w_tle(praca, self._przyjeto)

    def _plan_pz(self, kontrahent):
        return {
            "nip": re.sub(r"\D", "", kontrahent.get("NIP") or ""),
            "zd_pozycje": [{"zd_id": r["zd_id"], "pozycja_id": r["zd_pozycja_id"], "ilosc": r["ilosc"]}
                           for r in self._przyjecie if r.get("zd_id") and r.get("zd_pozycja_id")],
            "reczne": [{"symbol": r["symbol"], "ilosc": r["ilosc"], "cena": r["cena"] if r["cena"] else None}
                       for r in self._przyjecie if not r.get("zd_id")],
            "magazyn": self.var_magazyn.get().strip() or MAGAZYN_DOMYSLNY,
            "nr_wz": self.var_wz.get().strip(),
            "data": self.var_data.get().strip(),
            "uwagi": self.var_uwagi.get().strip()}

    def _przyjeto(self, w, blad):
        self.stop_kreciolek()
        self.btn_przyjmij.config(state=tk.NORMAL)
        if blad:
            self.status.config(text=f"Błąd: {blad}")
            messagebox.showerror("Przyjęcie dostawy", str(blad), parent=self)
            return
        if w.get("suchy_bledy"):
            tresc = "\n".join(f"• {b.get('Symbol') or b.get('Rodzaj')}: {b.get('Szczegoly')}" for b in w["suchy_bledy"])
            messagebox.showwarning("Subiekt odrzucił plan (suchy przebieg)",
                                   f"Nic nie zapisano.\n\n{tresc}", parent=self)
            self.status.config(text="Suchy przebieg: Subiekt odrzucił plan — nic nie zapisano.")
            return
        pz = w.get("pz", {})
        kroki = pz.get("kroki", [])
        uwagi = [k_ for k_ in kroki if k_.get("Status") in ("uwaga", "blad")]
        if w.get("status") == "PZ":
            # PO — raport tego, co faktycznie powstało
            realizacja = next((k_.get("Szczegoly") for k_ in kroki if k_.get("Status") == "realizacja-zd"), "")
            tresc = (f"DOSTAWA nr {w['dostawa_id']} zapisana.\nPZ w Subiekcie: {pz.get('numer')}"
                     f"{'  (' + realizacja + ')' if realizacja else ''}")
            if uwagi:
                tresc += "\n\nUwagi:\n" + "\n".join(f"• {k_.get('Symbol')}: {k_.get('Szczegoly')}" for k_ in uwagi)
            messagebox.showinfo("Przyjęcie dostawy — PO zapisie", tresc, parent=self)
            self.status.config(text=f"✔ DOSTAWA {w['dostawa_id']} → {pz.get('numer')}")
            self._przyjecie = []
            for v in (self.var_wz, self.var_zam, self.var_ident, self.var_uwagi):
                v.set("")
            self._wypelnij_przyjecie()
            self._start_tla()                     # ZD zeszły — świeże do realizacji
            self._wczytaj_historie()
        else:
            powod = "\n".join(f"• {k_.get('Symbol') or k_.get('Rodzaj')}: {k_.get('Szczegoly')}" for k_ in uwagi) or "brak szczegółów"
            messagebox.showerror("PZ nie powstało",
                                 f"DOSTAWA nr {w['dostawa_id']} zapisana ze statusem BLAD_PZ — nic nie zginęło.\n"
                                 f"Subiekt odrzucił PZ:\n{powod}\n\n"
                                 f"Popraw przyczynę i użyj „Ponów PZ” w historii.", parent=self)
            self.status.config(text=f"DOSTAWA {w['dostawa_id']} zapisana, PZ ODRZUCONE.")
            self._wczytaj_historie()
            self.nb.select(1)

    # ── historia ───────────────────────────────────────────────────────────
    def _na_zmiane_karty(self):
        if self.nb.index(self.nb.select()) == 1 and not self._historia:
            self._wczytaj_historie()

    def _wczytaj_historie(self):
        def praca():
            import rm_klient
            return rm_klient.master_read("dostawy-lista")

        def potem(w, blad):
            if blad:
                self.status.config(text=f"Historia: {blad}")
                return
            self._historia = w or []
            self._wypelnij_historie()
        self._w_tle(praca, potem)

    def _wypelnij_historie(self):
        if self.sheet_hist is None:
            return
        dane = [[d["id"], d.get("data_przyjecia") or "", d.get("dostawca") or "", d.get("nr_wz_dostawcy") or "",
                 d.get("nr_zamowienia") or "", d.get("identyfikator_wlasny") or "", d.get("pz_numer") or "",
                 d.get("status") or "", d.get("pozycji") or 0, d.get("kto") or "",
                 (d.get("kiedy") or "")[:16].replace("T", " ")] for d in self._historia]
        try:
            self.sheet_hist.dehighlight_all()
        except Exception:
            pass
        self.sheet_hist.set_sheet_data(dane, reset_col_positions=False, redraw=False)
        for i, d in enumerate(self._historia):
            k = STATUS_KOLOR.get(d.get("status") or "")
            if k:
                self.sheet_hist.highlight_cells(row=i, column=7, bg=k)
        self.sheet_hist.redraw()

    def _wybrano_historie(self, _e=None):
        try:
            idx = sorted(set(self.sheet_hist.get_selected_rows(get_cells_as_rows=True)))
        except Exception:
            idx = []
        if not idx or idx[0] >= len(self._historia):
            return
        d = self._historia[idx[0]]

        def praca():
            import rm_klient
            return rm_klient.master_read("dostawy-pozycje", {"dostawa_id": d["id"]})

        def potem(w, blad):
            if blad or self.sheet_hist_poz is None:
                return
            self.sheet_hist_poz.set_sheet_data(
                [[p["symbol"], p["nazwa"], _il(p["ilosc"]), p["jednostka"], _zl(p["cena"]),
                  p.get("zd_numer") or "(spoza ZD)", _il(p["ilosc_zd"]) if p.get("ilosc_zd") is not None else ""]
                 for p in (w or [])], reset_col_positions=False)
        self._w_tle(praca, potem)

    def _ponow_pz(self):
        """Dostawa zapisana, PZ odrzucone — druga próba z tych samych pozycji."""
        try:
            idx = sorted(set(self.sheet_hist.get_selected_rows(get_cells_as_rows=True)))
        except Exception:
            idx = []
        if not idx or idx[0] >= len(self._historia):
            messagebox.showinfo("Ponów PZ", "Zaznacz dostawę w historii.", parent=self)
            return
        d = self._historia[idx[0]]
        if d.get("status") == "PZ":
            messagebox.showinfo("Ponów PZ", f"Ta dostawa ma już PZ: {d.get('pz_numer')}.", parent=self)
            return
        if not messagebox.askyesno("Ponów PZ", f"Wystawić PZ dla DOSTAWY nr {d['id']} ({d.get('dostawca')}, "
                                                f"{d.get('data_przyjecia')})?\n\nPowstanie dokument w Subiekcie.",
                                    parent=self):
            return
        self.start_kreciolek("Wystawiam PZ w Subiekcie")

        def praca():
            import rm_klient
            import subiekt_bridge
            poz = rm_klient.master_read("dostawy-pozycje", {"dostawa_id": d["id"]})
            plan = {"nip": d.get("nip") or "",
                    "zd_pozycje": [{"zd_id": p["zd_id"], "pozycja_id": p["zd_pozycja_id"], "ilosc": p["ilosc"]}
                                   for p in poz if p.get("zd_id") and p.get("zd_pozycja_id")],
                    "reczne": [{"symbol": p["symbol"], "ilosc": p["ilosc"], "cena": p["cena"] or None}
                               for p in poz if not p.get("zd_id")],
                    "magazyn": d.get("magazyn") or MAGAZYN_DOMYSLNY, "nr_wz": d.get("nr_wz_dostawcy") or "",
                    "data": d.get("data_przyjecia") or "",
                    "uwagi": f"DOSTAWA {d['id']}" + (f" WZ {d['nr_wz_dostawcy']}" if d.get("nr_wz_dostawcy") else "")}
            odp = subiekt_bridge.call("pz-utworz", {"plan": plan, "zapisz": True}, timeout=180, write=True)
            status = "PZ" if (odp or {}).get("zapisano") else "BLAD_PZ"
            rm_klient.master_exec("dostawa-pz-ustaw", {"pz_numer": (odp or {}).get("numer") or None,
                                                       "pz_id": (odp or {}).get("pzId"), "status": status, "id": d["id"]})
            return {"pz": odp or {}, "status": status, "dostawa_id": d["id"]}

        self._w_tle(praca, self._przyjeto)

    def _zamknij(self):
        self.destroy()


def open_window(parent):
    return OknoDostawa(parent)
