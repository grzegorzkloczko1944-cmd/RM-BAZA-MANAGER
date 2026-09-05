# -*- coding: utf-8 -*-
"""
Przegląd dokumentów Subiekta: ZK, ZD, RW, WZ — z pozycjami.

    import subiekt_dokumenty_gui
    subiekt_dokumenty_gui.open_window(parent)

Po co: RM_BAZA potrafi już zakładać ZK i tworzyć ZD, ale nie było gdzie
zobaczyć, co w Subiekcie realnie jest. Żeby sprawdzić stan projektu, trzeba
było przełączać się do Subiekta i filtrować listy ręcznie.

Układ dwupanelowy:
  * góra  — lista dokumentów (rodzaj, numer, data, podmiot, projekt, pozycje),
  * dół   — pozycje klikniętego dokumentu.

Wyszukiwarka działa na OBU poziomach: wpisanie numeru rysunku pokazuje
dokumenty, które go zawierają — po tym widać, na którym ZK/ZD siedzi dana
część i czy została już wydana.

Dane idą jednym wywołaniem mostu (~9 s): pozycje przychodzą razem
z nagłówkami, bo most jest bezstanowy i pytanie o każdy dokument osobno
kosztowałoby tyle samo co całość.
"""

import json
import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from rm_kreciolek import Kreciolek
from subiekt_stany import (_find_exe, blad_mostu, wysrodkuj,
                           podepnij_szerokosci, CONFIG_PATH)

try:
    from tksheet import Sheet
except ImportError:
    Sheet = None

TIMEOUT_S = 300

RODZ_WSZYSTKIE = "— wszystkie —"
RODZAJE = ["ZK", "ZD", "RW", "WZ"]
OPIS_RODZAJU = {
    "ZK": "ZK — lista projektu",
    "ZD": "ZD — zamówienie do dostawcy",
    "RW": "RW — wydanie na produkcję",
    "WZ": "WZ — wydanie zewnętrzne",
}
PROJ_WSZYSTKIE = "— wszystkie —"
PROJ_BEZ = "(bez projektu)"


def pobierz_dokumenty(limit=200, timeout=TIMEOUT_S):
    """[{rodzaj, numer, data, podmiot, tytul, uwagi, status, wartosc, pozycje}]."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")

    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="subiekt_dok_")
    out = os.path.join(tmpdir, "dok.json")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.run([exe, "dokumenty", f"--limit={limit}", f"--out={out}"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=flags)
    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(blad_mostu(exe, "dokumenty", proc, out))

    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    return [{
        "rodzaj": d.get("Rodzaj") or "",
        "numer": d.get("Numer") or "",
        "data": d.get("Data") or "",
        "podmiot": (d.get("Podmiot") or "").strip(),
        "tytul": d.get("Tytul") or "",
        "projekt": (d.get("Uwagi") or "").strip(),
        "status": d.get("Status") or "",
        "magazyn": d.get("Magazyn") or "",
        "wartosc": float(d.get("Wartosc") or 0),
        "pozycje": [{
            "symbol": p.get("Symbol") or "",
            "nazwa": p.get("Nazwa") or "",
            "ilosc": float(p.get("Ilosc") or 0),
            "jm": p.get("Jm") or "szt",
            "cena": float(p.get("Cena") or 0),
        } for p in (d.get("Pozycje") or [])],
    } for d in data.get("dokumenty", [])]


class DokumentyWindow(tk.Toplevel, Kreciolek):
    KOL_DOK = [("rodzaj", "Rodzaj", 70), ("numer", "Numer", 130),
               ("data", "Data", 90), ("projekt", "Projekt", 80),
               ("podmiot", "Podmiot / dostawca", 250), ("tytul", "Tytuł", 220),
               ("pozycji", "Pozycji", 65), ("wartosc", "Wartość", 90),
               ("status", "Status", 140)]
    KOL_POZ = [("symbol", "Nr rysunku / symbol", 200), ("nazwa", "Nazwa", 330),
               ("ilosc", "Ilość", 70), ("jm", "J.m.", 50),
               ("cena", "Cena netto", 90), ("wartosc", "Wartość", 90)]

    def __init__(self, parent):
        super().__init__(parent)
        self.dokumenty = []
        self.widoczne = []
        self.biezacy = None

        self.title("Subiekt — przegląd dokumentów (ZK / ZD / RW / WZ)")
        self.geometry("1250x760")
        self.minsize(900, 450)
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

        self._build_ui()
        self.after(100, self._load_async)

    # ── UI ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        top = tk.Frame(self, bg="#34495e", height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="📚 Dokumenty w Subiekcie — zamówienia i wydania",
                 bg="#34495e", fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)
        # Wiek odczytu — dane z Subiekta starzeją się, a nic tego nie pokazywało.
        self.lbl_wiek = tk.Label(top, text="", bg="#34495e", fg="#e74c3c",
                                 font=("Arial", 13, "bold"))
        self.lbl_wiek.pack(side=tk.LEFT, padx=(16, 0))
        self.btn_refresh = tk.Button(top, text="🔄 Odśwież", command=self._load_async,
                                     bg="#3498db", fg="white", font=("Arial", 8),
                                     padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_refresh.pack(side=tk.RIGHT, padx=10, pady=8)
        # Wspólny formularz nowej kartoteki (subiekt_asortyment) — tu bez
        # callbacku, bo przegląd nic nie buduje; kartoteka pojawi się w
        # dokumentach dopiero, gdy ktoś jej użyje.
        tk.Button(top, text="➕ Nowa kartoteka", command=self._nowa_kartoteka,
                  bg="#27ae60", fg="white", font=("Arial", 8),
                  padx=8, pady=2, relief=tk.RAISED, bd=1).pack(side=tk.RIGHT, padx=(0, 4), pady=8)
        # Kasowanie tego, co zaznaczone w tabeli. To okno widzi WSZYSTKIE typy
        # (ZK/ZD/RW/WZ), a most rozpoznaje rodzaj po prefiksie numeru, więc
        # jeden przycisk sprząta mieszany zaznaczony zestaw.
        #
        # ⚠️ ZD kasuj PRZED powiązanym ZK — inaczej Subiekt potrafi odmówić
        # usunięcia ZK. Okno potwierdzenia samo o tym przypomina, gdy w liście
        # są oba typy naraz.
        tk.Button(top, text="🗑 Usuń zaznaczone", command=self._usun_zaznaczone,
                  bg="#c0392b", fg="white", font=("Arial", 8),
                  padx=8, pady=2, relief=tk.RAISED, bd=1).pack(side=tk.RIGHT, padx=(0, 4), pady=8)

        f = tk.Frame(self, bg="#ecf0f1")
        f.pack(side=tk.TOP, fill=tk.X)
        tk.Label(f, text="Szukaj:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(12, 3), pady=6)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refill())
        tk.Entry(f, textvariable=self.search_var, width=26, font=("Arial", 9)).pack(side=tk.LEFT, pady=6)
        tk.Label(f, text="(numer rysunku, nazwa, numer dokumentu)", bg="#ecf0f1",
                 fg="#7f8c8d", font=("Arial", 8)).pack(side=tk.LEFT, padx=(4, 0))

        tk.Label(f, text="Rodzaj:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(14, 3), pady=6)
        self.rodzaj_var = tk.StringVar(value=RODZ_WSZYSTKIE)
        cmb_r = ttk.Combobox(f, textvariable=self.rodzaj_var, width=10, state="readonly",
                             font=("Arial", 9), values=[RODZ_WSZYSTKIE] + RODZAJE)
        cmb_r.pack(side=tk.LEFT, pady=6)
        cmb_r.bind("<<ComboboxSelected>>", lambda _e: self._refill())

        tk.Label(f, text="Projekt:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(14, 3), pady=6)
        self.projekt_var = tk.StringVar(value=PROJ_WSZYSTKIE)
        self.cmb_proj = ttk.Combobox(f, textvariable=self.projekt_var, width=14,
                                     state="readonly", font=("Arial", 9),
                                     values=[PROJ_WSZYSTKIE])
        self.cmb_proj.pack(side=tk.LEFT, pady=6)
        self.cmb_proj.bind("<<ComboboxSelected>>", lambda _e: self._refill())

        self.only_otwarte_var = tk.IntVar(value=0)
        tk.Checkbutton(f, text="tylko niezrealizowane", variable=self.only_otwarte_var,
                       command=self._refill, bg="#ecf0f1", font=("Arial", 8),
                       activebackground="#ecf0f1").pack(side=tk.LEFT, padx=(12, 0), pady=6)

        # Czyszczenie filtrów — ta sama ikona i kolor co w arkuszu głównym.
        tk.Button(f, text="🗑️", command=self._wyczysc_filtry, bg="#95a5a6", fg="white",
                  font=("Arial", 11, "bold"), width=3, relief=tk.RAISED, bd=2,
                  cursor="hand2").pack(side=tk.LEFT, padx=(10, 2), pady=4)

        self.summary = tk.Label(self, text="Wczytywanie…", bg="#ecf0f1", fg="#2c3e50",
                                font=("Arial", 9), anchor="w", padx=12, pady=6)
        self.summary.pack(side=tk.TOP, fill=tk.X)

        # Dwa panele: dokumenty u góry, pozycje klikniętego na dole.
        paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 4))

        gora = tk.Frame(paned)
        dol = tk.Frame(paned)
        paned.add(gora, weight=3)
        paned.add(dol, weight=2)

        if Sheet is None:
            tk.Label(gora, text="Brak biblioteki tksheet", fg="#c0392b").pack(pady=20)
            self.sheet = self.sheet_poz = None
            return

        self.sheet = Sheet(gora, headers=[k[1] for k in self.KOL_DOK],
                           column_width=120, theme="light blue")
        self.sheet.set_options(show_selected_cells_border=True,
                               enable_edit_cell_auto_resize=False,
                               empty_horizontal=0, empty_vertical=0)
        self.sheet.enable_bindings((
            "single_select", "drag_select", "ctrl_select", "select_all",
            "column_width_resize", "arrowkeys", "right_click_popup_menu",
            "rc_select", "copy",
        ))
        # Szerokości kolumn zapamiętywane między sesjami — osobno dla obu
        # arkuszy, bo to niezależne tabele.
        podepnij_szerokosci(self, self.sheet, "dokumenty",
                            [k[2] for k in self.KOL_DOK])
        self.sheet.bind("<ButtonRelease-1>", self._on_wybor_dokumentu, add="+")
        self.sheet.pack(fill=tk.BOTH, expand=True)

        self.lbl_poz = tk.Label(dol, text="Pozycje — kliknij dokument powyżej",
                                bg="#34495e", fg="white", font=("Arial", 9, "bold"),
                                anchor="w", padx=10, pady=4)
        self.lbl_poz.pack(side=tk.TOP, fill=tk.X)

        self.sheet_poz = Sheet(dol, headers=[k[1] for k in self.KOL_POZ],
                               column_width=120, theme="light green")
        self.sheet_poz.set_options(show_selected_cells_border=True,
                                   enable_edit_cell_auto_resize=False,
                                   empty_horizontal=0, empty_vertical=0)
        self.sheet_poz.enable_bindings((
            "single_select", "drag_select", "ctrl_select", "select_all",
            "column_width_resize", "arrowkeys", "right_click_popup_menu",
            "rc_select", "copy",
        ))
        podepnij_szerokosci(self, self.sheet_poz, "dokumenty_pozycje",
                            [k[2] for k in self.KOL_POZ])
        self.sheet_poz.pack(fill=tk.BOTH, expand=True)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    # ── wczytywanie ────────────────────────────────────────────────────────
    def _load_async(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.start_kreciolek("Czytam dokumenty z Subiekta (~10 s)")
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        try:
            dok = pobierz_dokumenty()
            self.after(0, lambda: self._load_done(dok, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._load_done([], err))

    def _load_done(self, dok, error):
        self.stop_kreciolek()      # także przy błędzie — inaczej kręci się dalej
        self.zaznacz_odczyt(self.lbl_wiek)
        self.btn_refresh.config(state=tk.NORMAL)
        if error:
            self.status.config(text="Błąd.")
            messagebox.showerror("Subiekt", error, parent=self)
            return
        self.dokumenty = dok
        projekty = sorted({d["projekt"] for d in dok if d["projekt"]})
        self.cmb_proj["values"] = [PROJ_WSZYSTKIE] + projekty + [PROJ_BEZ]
        self._refill()
        from datetime import datetime
        self.status.config(text=f"Odczyt {datetime.now():%H:%M:%S}. "
                                "Okno tylko czyta — nic nie zapisuje do Subiekta.")

    # ── filtry ─────────────────────────────────────────────────────────────
    def _pasuje(self, d, szukaj):
        """Szukaj obejmuje też POZYCJE — wpisanie numeru rysunku pokazuje
        dokumenty, które go zawierają. To główny sposób odpowiedzi na pytanie
        „gdzie jest ta część"."""
        if not szukaj:
            return True
        w_naglowku = szukaj in " ".join((d["numer"], d["podmiot"], d["tytul"],
                                         d["projekt"], d["status"])).lower()
        if w_naglowku:
            return True
        return any(szukaj in f"{p['symbol']} {p['nazwa']}".lower() for p in d["pozycje"])

    def _nowa_kartoteka(self):
        import subiekt_asortyment
        subiekt_asortyment.okno_nowa_kartoteka(self)

    def _wyczysc_filtry(self):
        """Wszystkie filtry do stanu wyjściowego — jedno odświeżenie na końcu."""
        self.search_var.set("")          # trace odpali _refill, ale poniżej i tak wołamy
        self.rodzaj_var.set(RODZ_WSZYSTKIE)
        self.projekt_var.set(PROJ_WSZYSTKIE)
        self.only_otwarte_var.set(0)
        self._refill()

    def _refill(self):
        if not self.sheet:
            return
        szukaj = (self.search_var.get() or "").strip().lower()
        rodzaj = self.rodzaj_var.get()
        projekt = self.projekt_var.get()
        tylko_otw = bool(self.only_otwarte_var.get())

        out = []
        for d in self.dokumenty:
            if rodzaj != RODZ_WSZYSTKIE and d["rodzaj"] != rodzaj:
                continue
            if projekt == PROJ_BEZ:
                if d["projekt"]:
                    continue
            elif projekt != PROJ_WSZYSTKIE and d["projekt"] != projekt:
                continue
            if tylko_otw and ("zrealizowan" in d["status"].lower()
                              or "anulowan" in d["status"].lower()):
                continue
            if not self._pasuje(d, szukaj):
                continue
            out.append(d)
        self.widoczne = out

        try:
            self.sheet.dehighlight_all()
        except Exception:
            pass
        self.sheet.set_sheet_data(
            [[d["rodzaj"], d["numer"], d["data"], d["projekt"], d["podmiot"],
              d["tytul"], len(d["pozycje"]),
              f"{d['wartosc']:.2f}" if d["wartosc"] else "", d["status"]]
             for d in out], reset_col_positions=False, redraw=False)

        # Kolor po rodzaju — od razu widać, co jest zamówieniem, a co wydaniem.
        kolory = {"ZK": "#d6eaf8", "ZD": "#d5f5e3", "RW": "#fdebd0", "WZ": "#f4ecf7"}
        for i, d in enumerate(out):
            bg = kolory.get(d["rodzaj"])
            if bg:
                self.sheet.highlight_cells(row=i, column=0, bg=bg)
            if "anulowan" in d["status"].lower():
                for c in range(len(self.KOL_DOK)):
                    self.sheet.highlight_cells(row=i, column=c, bg="#eaecee")
        self.sheet.redraw()

        from collections import Counter
        licz = Counter(d["rodzaj"] for d in out)
        poz = sum(len(d["pozycje"]) for d in out)
        self.summary.config(text=(
            f"Dokumentów: {len(out)} z {len(self.dokumenty)}    "
            + "   ".join(f"{r}: {licz.get(r, 0)}" for r in RODZAJE)
            + f"    pozycji łącznie: {poz}"
            + (f"    🔍 znaleziono w pozycjach" if szukaj else "")
        ))

    # ── usuwanie dokumentów ────────────────────────────────────────────────
    def _usun_zaznaczone(self):
        """Kasuje dokumenty zaznaczone w tabeli. Most (tryb zd-usun) rozpoznaje
        rodzaj po prefiksie numeru, więc obsłuży mieszany zestaw ZK/ZD/RW/WZ."""
        if not self.sheet:
            return
        try:
            rows = sorted(set(self.sheet.get_selected_rows(get_cells_as_rows=True)))
        except Exception:
            rows = []
        wybrane = [self.widoczne[r] for r in rows if 0 <= r < len(self.widoczne)]
        if not wybrane:
            messagebox.showinfo(
                "Usuń dokumenty",
                "Zaznacz w tabeli dokumenty do usunięcia.\n\n"
                "Klik w wiersz zaznacza jeden, Ctrl+klik dokłada kolejne.",
                parent=self)
            return

        numery = [d["numer"] for d in wybrane if d.get("numer")]
        opis = "\n".join(
            f"  • {d['rodzaj']} {d['numer']} — {d.get('podmiot') or '—'} "
            f"({len(d.get('pozycje') or [])} poz.)" for d in wybrane[:15])
        if len(wybrane) > 15:
            opis += f"\n  … i {len(wybrane) - 15} więcej"

        # ZD trzyma się ZK — kasowanie ZK przed jego ZD kończy się odmową
        # Subiekta. Ostrzegamy tylko wtedy, gdy w zestawie są oba typy.
        rodzaje = {d.get("rodzaj") for d in wybrane}
        uwaga = ("\n⚠️ W zaznaczeniu są ZK i ZD. Jeśli są powiązane, usuń "
                 "najpierw ZD — Subiekt może nie pozwolić skasować ZK "
                 "z wiszącym zamówieniem.\n"
                 if {"ZK", "ZD"} <= rodzaje else "")

        if not messagebox.askyesno(
                "Usunięcie dokumentów — potwierdzenie",
                "Baza PRODUKCYJNA. Operacja NIEODWRACALNA.\n\n"
                f"Zostaną usunięte ({len(numery)}):\n{opis}\n{uwaga}\nUsunąć?",
                parent=self, icon="warning"):
            return

        self.status.config(text="Usuwam dokumenty…")
        self.start_kreciolek("Usuwam dokumenty w Subiekcie")
        threading.Thread(target=self._usun_worker, args=(numery,),
                         daemon=True).start()

    def _usun_worker(self, numery):
        try:
            from subiekt_zamowienia import usun_zd
            wynik = usun_zd(numery, zapisz=True)
            self.after(0, lambda: self._usun_done(wynik, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._usun_done(None, err))

    def _usun_done(self, wynik, error):
        self.stop_kreciolek()
        if error:
            self.status.config(text="Nie udało się usunąć dokumentów.")
            messagebox.showerror("Usuwanie dokumentów", error, parent=self)
            return
        kroki = wynik.get("kroki", [])
        usuniete = [k for k in kroki if k.get("Status") == "usuniete"]
        bledy = [k for k in kroki if k.get("Status") == "blad"]

        linie = [f"Usunięte dokumenty: {len(usuniete)}"]
        linie += [f"  • {k['Numer']} — {k.get('Szczegoly') or ''}" for k in usuniete[:12]]
        if bledy:
            linie += ["", f"Nieusunięte ({len(bledy)}):"]
            linie += [f"  • {k['Numer']}: {k.get('Szczegoly') or ''}" for k in bledy[:8]]
        (messagebox.showwarning if bledy else messagebox.showinfo)(
            "Usuwanie dokumentów", "\n".join(linie), parent=self)
        self._load_async()      # lista musi pokazać stan po usunięciu

    # ── pozycje wybranego dokumentu ────────────────────────────────────────
    def _on_wybor_dokumentu(self, _event=None):
        if not self.sheet or not self.sheet_poz:
            return
        try:
            rows = self.sheet.get_selected_rows(get_cells_as_rows=True)
        except Exception:
            rows = []
        if not rows:
            return
        r = sorted(rows)[0]
        if not (0 <= r < len(self.widoczne)):
            return
        d = self.widoczne[r]
        self.biezacy = d

        szukaj = (self.search_var.get() or "").strip().lower()
        self.sheet_poz.set_sheet_data(
            [[p["symbol"], p["nazwa"], f"{p['ilosc']:g}", p["jm"],
              f"{p['cena']:.2f}" if p["cena"] else "",
              f"{p['cena'] * p['ilosc']:.2f}" if p["cena"] else ""]
             for p in d["pozycje"]], reset_col_positions=False, redraw=False)

        # Podświetl pozycje pasujące do wyszukiwarki — po to się szukało.
        try:
            self.sheet_poz.dehighlight_all()
        except Exception:
            pass
        if szukaj:
            for i, p in enumerate(d["pozycje"]):
                if szukaj in f"{p['symbol']} {p['nazwa']}".lower():
                    for c in range(len(self.KOL_POZ)):
                        self.sheet_poz.highlight_cells(row=i, column=c, bg="#fcf3cf")
        self.sheet_poz.redraw()

        opis = OPIS_RODZAJU.get(d["rodzaj"], d["rodzaj"])
        self.lbl_poz.config(
            text=f"{opis}   ·   {d['numer']}   ·   {d['podmiot']}"
                 + (f"   ·   projekt {d['projekt']}" if d["projekt"] else "")
                 + f"   ·   {len(d['pozycje'])} poz."
                 + (f"   ·   {d['wartosc']:.2f} zł" if d["wartosc"] else ""))


def open_window(parent):
    """Punkt wejścia dla RM_BAZA."""
    return DokumentyWindow(parent)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    root = tk.Tk()
    root.withdraw()
    w = open_window(root)
    w.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
