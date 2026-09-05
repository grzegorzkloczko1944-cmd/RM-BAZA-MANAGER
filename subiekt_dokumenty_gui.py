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
import sqlite3
import subprocess
import threading
import tkinter as tk
from pathlib import Path
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
        # Termin dostawy — ta sama nazwa co kolumna w arkuszu głównym RM_BAZA.
        # Mają go tylko zamówienia; przy WZ/RW zostaje pusty.
        "termin": d.get("Termin") or "",
        "magazyn": d.get("Magazyn") or "",
        "wartosc": float(d.get("Wartosc") or 0),
        "pozycje": [{
            "symbol": p.get("Symbol") or "",
            "nazwa": p.get("Nazwa") or "",
            "ilosc": float(p.get("Ilosc") or 0),
            "jm": p.get("Jm") or "szt",
            "cena": float(p.get("Cena") or 0),
            # Projekt pozycji z Uwag ZK, którą realizuje — „2632, 3000" gdy
            # jedno ZD zbiera detale z kilku projektów. Tylko przy ZD.
            "projekt": p.get("Projekt") or "",
        } for p in (d.get("Pozycje") or [])],
    } for d in data.get("dokumenty", [])]


class DokumentyWindow(tk.Toplevel, Kreciolek):
    KOL_DOK = [("rodzaj", "Rodzaj", 70), ("numer", "Numer", 130),
               ("data", "Data", 90), ("projekt", "Projekt", 80),
               ("podmiot", "Podmiot / dostawca", 250), ("tytul", "Tytuł", 220),
               ("pozycji", "Pozycji", 65), ("wartosc", "Wartość", 90),
               ("termin", "Termin dostawy", 100), ("wyslano", "Wysłano", 105),
               ("pdf", "PDF", 40), ("status", "Status", 140)]
    KOL_POZ = [("symbol", "Nr rysunku / symbol", 200), ("nazwa", "Nazwa", 330),
               ("ilosc", "Ilość", 70), ("jm", "J.m.", 50),
               ("cena", "Cena netto", 90), ("wartosc", "Wartość", 90)]

    def __init__(self, parent):
        super().__init__(parent)
        self.dokumenty = []
        self.widoczne = []
        self.biezacy = None
        self._wyslane = {}          # {numer ZD: (kiedy, ile razy)} — kolumna „Wysłano”

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
        # ⚠️ Przyciski dotyczące ZAZNACZONEGO dokumentu (Wyślij ZD, Podgląd PDF)
        # są w pasku filtrów NIŻEJ, nie tutaj. Pasek górny mieści tylko cztery
        # elementy — piąty wyjeżdżał poza prawą krawędź i zostawało z niego
        # ucięte „Podg…” (zgłoszone 05.09.2026).

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

        # Akcje na ZAZNACZONYM dokumencie — po prawej stronie paska filtrów,
        # bo w górnym już się nie mieściły.
        tk.Button(f, text="👁 Podgląd PDF", command=self._podglad_pdf,
                  bg="#7f8c8d", fg="white", font=("Arial", 8), padx=8, pady=2,
                  relief=tk.RAISED, bd=1, cursor="hand2").pack(side=tk.RIGHT, padx=(0, 12), pady=4)
        # Świeży wydruk — gdy dokument zmienił się po ostatnim wygenerowaniu.
        tk.Button(f, text="🔁 Nowy PDF",
                  command=lambda: self._podglad_pdf(wymus_nowy=True),
                  bg="#95a5a6", fg="white", font=("Arial", 8), padx=8, pady=2,
                  relief=tk.RAISED, bd=1, cursor="hand2").pack(side=tk.RIGHT, padx=(0, 4), pady=4)
        tk.Button(f, text="✉ Wyślij ZD", command=self._wyslij_zd,
                  bg="#2980b9", fg="white", font=("Arial", 8), padx=8, pady=2,
                  relief=tk.RAISED, bd=1, cursor="hand2").pack(side=tk.RIGHT, padx=(0, 4), pady=4)

        self.summary = tk.Label(self, text="Wczytywanie…", bg="#ecf0f1", fg="#2c3e50",
                                font=("Arial", 9), anchor="w", padx=12, pady=6)
        self.summary.pack(side=tk.TOP, fill=tk.X)

        # Legenda — kolory same w sobie nic nie mówią, a jest ich sześć.
        # Próbki, nie opis słowny: kolor obok znaczenia czyta się od razu.
        # ⚠️ Wartości MUSZĄ się zgadzać ze słownikiem `kolory` w _refill()
        # i z tłem anulowanych/trafień — inaczej legenda kłamie.
        leg = tk.Frame(self, bg="#ecf0f1")
        leg.pack(side=tk.TOP, fill=tk.X)
        tk.Label(leg, text="Legenda:", bg="#ecf0f1", fg="#7f8c8d",
                 font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=(12, 6), pady=(0, 5))
        for kolor, opis in (("#d6eaf8", "ZK — zamówienie od klienta"),
                            ("#d5f5e3", "ZD — zamówienie do dostawcy"),
                            ("#fdebd0", "RW — wydanie na produkcję"),
                            ("#f4ecf7", "WZ — wydanie zewnętrzne"),
                            ("#eaecee", "anulowany"),
                            ("#fcf3cf", "pasuje do wyszukiwarki")):
            tk.Label(leg, text="  ", bg=kolor, relief=tk.SOLID, bd=1).pack(
                side=tk.LEFT, padx=(6, 3), pady=(0, 5))
            tk.Label(leg, text=opis, bg="#ecf0f1", fg="#2c3e50",
                     font=("Arial", 8)).pack(side=tk.LEFT, pady=(0, 5))
        tk.Label(leg, text="📄 = jest gotowy wydruk PDF (dwuklik otwiera)",
                 bg="#ecf0f1", fg="#7f8c8d", font=("Arial", 8)).pack(
            side=tk.LEFT, padx=(16, 0), pady=(0, 5))

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
        # Dwuklik w kolumnę PDF otwiera gotowy wydruk — bez sięgania po przycisk.
        self.sheet.bind("<Double-Button-1>", self._on_dwuklik, add="+")
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
        # Ślad wysyłki z RM_BAZA — do kolumny „Wysłano”. Odczyt tanio (jedno
        # zapytanie), a odświeża się razem z listą, więc po wysłaniu maila
        # wystarczy „Odśwież”, żeby zobaczyć datę.
        self._wyslane = self._historia_wyslania()
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
              f"{d['wartosc']:.2f}" if d["wartosc"] else "",
              d.get("termin", ""), self._opis_wyslania(d),
              "📄" if self._plik_pdf(d) else "", d["status"]]
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
    def _zaznaczony_dokument(self, tylko_zd=False, akcja="tej operacji"):
        """Jeden dokument spod kursora. None + komunikat, gdy nic nie wybrano."""
        if not self.sheet:
            return None
        try:
            rows = sorted(set(self.sheet.get_selected_rows(get_cells_as_rows=True)))
        except Exception:
            rows = []
        wybrane = [self.widoczne[r] for r in rows if 0 <= r < len(self.widoczne)]
        if not wybrane:
            messagebox.showinfo("Subiekt", f"Zaznacz w tabeli dokument do {akcja}.",
                                parent=self)
            return None
        d = wybrane[0]
        if tylko_zd and d.get("rodzaj") != "ZD":
            messagebox.showinfo(
                "Wyślij ZD",
                f"To działa tylko dla zamówień do dostawcy (ZD).\n\n"
                f"Zaznaczony dokument to {d.get('rodzaj')} {d.get('numer')}.",
                parent=self)
            return None
        return d

    def _podglad_pdf(self, wymus_nowy=False):
        """
        Otwiera PDF zaznaczonego dokumentu — ten sam wydruk, który idzie mailem.

        Gotowy plik z katalogu wydruków otwiera się NATYCHMIAST; generowanie
        z Subiekta trwa ~11 s (uruchomienie mostu i zalogowanie do Sfery), więc
        robimy je tylko, gdy wydruku jeszcze nie ma albo ktoś chce świeży
        (zgłoszone 05.09.2026: „długo otwiera te PDF").
        """
        d = self._zaznaczony_dokument(akcja="podglądu")
        if not d:
            return
        numer = d.get("numer") or ""

        if not wymus_nowy:
            gotowy = self._plik_pdf(d)
            if gotowy:
                from datetime import datetime as _dt
                kiedy = _dt.fromtimestamp(gotowy.stat().st_mtime)
                os.startfile(str(gotowy))
                self.status.config(
                    text=f"Otwarto wydruk {numer} z {kiedy:%d.%m.%Y %H:%M} "
                         f"(gotowy plik; „Nowy PDF” wygeneruje aktualny).")
                return

        self.status.config(text=f"Generowanie PDF {numer}… (~11 s)")
        self.update_idletasks()
        try:
            import subiekt_wyslij_zd
            pdfy, bledy = subiekt_wyslij_zd.eksportuj_pdf([numer], self._katalog_pdf())
        except Exception as e:
            self.status.config(text="Nie udało się wygenerować PDF.")
            messagebox.showerror("Podgląd PDF", str(e), parent=self)
            return
        dane = pdfy.get(numer) or {}
        plik = dane.get("plik")
        if not plik or not Path(plik).exists():
            self.status.config(text="PDF nie powstał.")
            messagebox.showwarning("Podgląd PDF",
                                   "Nie udało się wygenerować wydruku tego dokumentu."
                                   + (f"\n\n{bledy[0]}" if bledy else ""), parent=self)
            return
        os.startfile(plik)
        self.status.config(text=f"Otwarto podgląd {numer}.")

    def _plik_pdf(self, dok):
        """
        Ścieżka gotowego wydruku tego dokumentu albo None.

        Nazwa pliku powstaje z numeru dokumentu tak samo jak w moście
        (ukośniki i spacje zamienione), więc nie trzeba niczego zapamiętywać
        — wystarczy sprawdzić, czy plik jest w katalogu wydruków.
        """
        numer = (dok.get("numer") or "").strip()
        if not numer:
            return None
        nazwa = numer.replace("/", "-").replace("\\", "-").replace(" ", "_") + ".pdf"
        sciezka = self._katalog_pdf() / nazwa
        return sciezka if sciezka.exists() else None

    def _katalog_pdf(self):
        """Wspólny katalog wydruków na dysku Y:, nie lokalny %TEMP%."""
        import subiekt_wyslij_zd
        return subiekt_wyslij_zd._katalog_pdf_domyslny()

    def _historia_wyslania(self):
        """{numer ZD: (kiedy, ile razy)} — pusty słownik, gdy nic nie wysyłano."""
        try:
            import subiekt_wyslij_zd
            return subiekt_wyslij_zd.historia_wyslania()
        except Exception as e:
            print(f"⚠️  Historia wysyłek niedostępna: {e}")
            return {}

    def _opis_wyslania(self, dok):
        """
        Treść kolumny „Wysłano": data ostatniej wysyłki, a przy powtórkach
        licznik („2026-09-05 ×2").

        Ślad pochodzi z RM_BAZA, nie z Subiekta — status dokumentu w Subiekcie
        („Do realizacji") mówi o stanie magazynowym i nie zmienia się po
        wysłaniu maila.
        """
        wpis = (getattr(self, "_wyslane", None) or {}).get(dok.get("numer") or "")
        if not wpis:
            return ""
        kiedy, ile = wpis
        data = (kiedy or "")[:10]
        return f"{data} ×{ile}" if ile > 1 else data

    def _pozycje_z_bomem(self, dok):
        """
        Pozycje ZD w formacie oczekiwanym przez okno wysyłki:
        (symbol, nazwa, ilość, j.m., ma_rysunek, projekty, bom_ref).

        Symbol, nazwa i ilość są z dokumentu w Subiekcie. Reszta z BOM-u
        RM_BAZA: `ma_rysunek` wycisza fałszywe „brak dokumentacji" dla
        elementów katalogowych, `projekty` mówi, gdzie szukać rysunków,
        a `bom_ref` [(project_id, item_id), …] to adresy, pod które po
        wysyłce wraca „Zamówiono" — po jednym na projekt pozycji.

        Projekt POZYCJI idzie z Uwag ZK, którą realizuje (most, tryb
        dokumenty). Wcześniej brany był z Uwag samego ZD — a te są puste,
        więc okno wysyłało bez adresów i „Zamówiono" nie trafiało nigdzie
        (05.09.2026). Ten sam mechanizm co w oknie zamówień: scal_bom/refy_bom.

        Gdy BOM-u nie da się wczytać, zostają same dane z Subiekta: wysyłka
        działa, tylko szukanie plików i „Zamówiono" są słabsze.
        """
        surowe = dok.get("pozycje") or []
        projekt_dok = (dok.get("projekt") or "").strip()

        def _lista(tekst):
            return [x.strip() for x in (tekst or "").split(",") if x.strip()]

        bom = {}
        try:
            import subiekt_zamowienia as sz
            numery = {n for p in surowe for n in _lista(p.get("projekt"))}
            if projekt_dok:
                numery.add(projekt_dok)
            for pid, pname in sz.projekty_po_numerze(numery).items():
                nr = (pname or "").strip().split(" ")[0]
                sz.scal_bom(bom, sz.dane_z_bom(pid, nr), nr)
        except Exception as e:
            print(f"⚠️  Nie udało się doczytać BOM-u dla {dok.get('numer')}: {e}")
            sz = None

        pozycje = []
        for p in surowe:
            symbol = p.get("symbol") or ""
            info = bom.get(symbol.strip().upper()) or {}
            projekty = _lista(p.get("projekt")) or _lista(projekt_dok)
            refy = sz.refy_bom(info, projekty) if (sz and info) else []
            pozycje.append((
                symbol,
                p.get("nazwa") or info.get("nazwa") or "",
                p.get("ilosc") or "",
                p.get("jm") or "szt.",
                # Bez wpisu w BOM-ie nie wiemy — None znaczy „nie orzekam",
                # a nie „nie ma rysunku".
                info.get("ma_rysunek") if info else None,
                ", ".join(projekty),
                refy,
            ))
        return pozycje

    def _email_dostawcy(self, dok):
        """Adres dostawcy z RM_BAZA — po nazwie z dokumentu."""
        try:
            import subiekt_zamowienia as sz
            nazwa = (dok.get("podmiot") or "").strip()
            if not nazwa:
                return ""
            con = sqlite3.connect(f"file:{sz._sciezka_master()}?mode=ro", uri=True)
            try:
                wiersze = con.execute(
                    "SELECT name, COALESCE(NULLIF(TRIM(email),''),"
                    "                      NULLIF(TRIM(email_default),'')) "
                    "FROM suppliers WHERE is_active=1").fetchall()
            finally:
                con.close()
            cel = sz._uprosc_nazwe(nazwa)
            for n, mail in wiersze:
                if mail and sz._uprosc_nazwe(n or "") == cel:
                    return mail
            for n, mail in wiersze:
                u = sz._uprosc_nazwe(n or "")
                if mail and u and (u in cel or cel in u):
                    return mail
        except Exception as e:
            print(f"⚠️  Mail dostawcy: {e}")
        return ""

    def _nadawca(self):
        """Imię i nazwisko zalogowanego użytkownika RM_BAZA."""
        try:
            import subiekt_zamowienia as sz
            uzytkownik = getattr(self.master, "current_user", None)
            if not uzytkownik:
                return ""
            con = sqlite3.connect(f"file:{sz._sciezka_master()}?mode=ro", uri=True)
            try:
                r = con.execute("SELECT display_name FROM users WHERE username=?",
                                (uzytkownik,)).fetchone()
            finally:
                con.close()
            return (r[0] if r and r[0] else uzytkownik) or ""
        except Exception:
            return ""

    def _wyslij_zd(self):
        """
        ✉ → okno wysyłki dla zaznaczonego ZD. To samo okno co w „Zamówieniach
        do dostawców”, tylko dane pozycji pochodzą z dokumentu w Subiekcie,
        a nie z BOM-u — dlatego dobieramy je z RM_BAZA po numerze rysunku
        (patrz _pozycje_z_bomem), żeby panel plików szukał tak samo dobrze.
        """
        d = self._zaznaczony_dokument(tylko_zd=True, akcja="wysłania")
        if not d:
            return
        try:
            import subiekt_wyslij_zd
        except Exception as e:
            messagebox.showerror("Wyślij ZD", f"Brak modułu wysyłki:\n{e}", parent=self)
            return

        pozycje = self._pozycje_z_bomem(d)
        okno = self.master
        subiekt_wyslij_zd.open_window(
            self, d.get("numer") or "", d.get("podmiot") or "",
            self._email_dostawcy(d), d.get("projekt") or "", pozycje, self._nadawca(),
            szukaj_plikow=getattr(okno, "_find_files_for_drawing", None),
            # „Szukaj dalej…" to nie jest samo _rfq_deep_scan — najpierw trzeba
            # zapytać, SKĄD szukać (biblioteka czy serwer), i podać korzeń.
            # Całą tę drogę ma już okno zamówień, więc ją pożyczamy zamiast
            # pisać drugą. Podpięcie _rfq_deep_scan wprost dawało przycisk,
            # który nic nie robił (zgłoszone 05.09.2026).
            szukaj_dalej=self._szukaj_dalej_rysunku,
            szukaj_hurtem=self._szukaj_hurtem_biblioteka,
            needs_dxf=getattr(okno, "_rfq_needs_dxf", None),
            # ⚠️ metoda nazywa się _register_file_drop, nie _register_drop_target
            # — zła nazwa cicho wyłączała przeciąganie plików.
            register_drop=getattr(okno, "_register_file_drop", None),
            dozwolone_ext=getattr(okno, "RFQ_PORTAL_EXTS", None),
            blad_serwera=lambda: getattr(okno, "_rfq_server_error", None),
            agent_portalu=getattr(okno, "_get_rfq_agent", None))

    def _szukaj_dalej_rysunku(self, pozycja):
        """Alternatywne źródło plików — ta sama droga co w oknie zamówień."""
        import subiekt_zamowienia as sz
        return sz.ZamowieniaWindow._szukaj_dalej_rysunku(self, pozycja)

    def _szukaj_hurtem_biblioteka(self, numery, zrodlo="library"):
        """Skan zbiorczy (biblioteka albo serwer) — pożyczony z okna zamówień."""
        import subiekt_zamowienia as sz
        return sz.ZamowieniaWindow._szukaj_hurtem_biblioteka(self, numery, zrodlo)

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
    def _on_dwuklik(self, _event=None):
        """Dwuklik w kolumnie PDF → otwiera gotowy wydruk zaznaczonego dokumentu."""
        if not self.sheet:
            return
        try:
            komorki = self.sheet.get_selected_cells()
            kolumna = next(iter(komorki))[1] if komorki else None
        except Exception:
            kolumna = None
        indeks_pdf = [k for k, *_ in self.KOL_DOK].index("pdf")
        if kolumna != indeks_pdf:
            return
        self._podglad_pdf()

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
