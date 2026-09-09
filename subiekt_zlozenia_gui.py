# -*- coding: utf-8 -*-
"""
Złożenia (komplety) projektu — czy to, co jest w Subiekcie, zgadza się z drzewkiem.

    import subiekt_zlozenia_gui
    subiekt_zlozenia_gui.open_window(parent, project_id, project_name)

Po co: komplet w Subiekcie NIE MA własnego stanu — jego dostępność wynika ze
stanu składników. Dlatego złożenia nie trafiają na żaden dokument (ani ZK,
ani PW, ani RW) i istnieją wyłącznie jako kartoteki ze składem. Nie było
miejsca, gdzie widać je wszystkie naraz: po zasiewie zostawał suchy komunikat
„25 kompletów do utworzenia”, a potem trzeba było klikać pojedynczo w kartę
pozycji (OKNO_ZLOZENIA_SPEC.md, 10.09.2026).

Okno jest TYLKO DO ODCZYTU. Zakładanie i naprawa składów dzieje się w oknie
„Projekt / Aktualizacja” — tu tylko sprawdzamy, czy to, co tam poszło,
faktycznie jest.

Układ (trzy panele, wg makiety):
  * góra        — płaska lista złożeń, problemy NA POCZĄTKU,
  * dół-lewo    — skład wybranego złożenia (komplety osobno, towary osobno),
  * dół-prawo   — szczegóły wybranego z przyciskiem „do rodzica”.

Świadomie bez drzewka jako drugiego widoku: na żywych danych problematyczne
złożenia to biblioteczne, które NIE mają rodzica w projekcie — ścieżka
„YamCandle → Kabina → ⚠” nie istnieje. Kolumna „Wchodzi w” plus skok do
rodzica załatwiają to, po co ktoś chciałby drzewa.

Skład komplet ↔ drzewko porównujemy PARAMI (symbol, ilość), nie samą liczbą
składników: 4 na 4 może znaczyć podmienioną pozycję albo zmienioną ilość —
ten sam wniosek co w Projekt.cs (SkladTakiSam).
"""

import json
import os
import sqlite3
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from rm_kreciolek import Kreciolek
from subiekt_stany import (PROJECTS_DIR, CONFIG_PATH, _find_exe, blad_mostu,
                           wysrodkuj, podepnij_szerokosci)

try:
    from tksheet import Sheet
except ImportError:
    Sheet = None

TIMEOUT_S = 300
KOMPLETY = ("Z", "ZZ")

STATUS_OK = "OK"
STATUS_PUSTY = "PUSTY"
STATUS_BRAK = "BRAK KARTOTEKI"
STATUS_ROZJAZD = "ROZJAZD"
PROBLEMY = (STATUS_BRAK, STATUS_PUSTY, STATUS_ROZJAZD)
#: Kolejność na liście: problemy na górze, bo to jedyny powód, dla którego
#: ktoś tu zagląda. Wewnątrz grupy — po symbolu.
RANGA = {STATUS_BRAK: 0, STATUS_PUSTY: 1, STATUS_ROZJAZD: 2, STATUS_OK: 3}
#: Ta sama paleta co w przeglądzie dokumentów (subiekt_dokumenty_gui):
#: zielone = w porządku, żółte = wymaga uwagi, czerwone = brak.
KOLOR = {STATUS_OK: "#d5f0dd", STATUS_PUSTY: "#fcf3cf",
         STATUS_BRAK: "#f2dede", STATUS_ROZJAZD: "#fad7a0"}
#: SIEROTA — pozycja oznaczona jako produkcja własna, która MIMO TO siedzi
#: na ZK. Nie jest statusem składu (tamte mówią o kartotece), tylko osobną
#: flagą: skład może być w porządku, a pozycja i tak być w złym torze.
#:
#: Bierze się stąd, że Projekt.cs NIE USUWA z dokumentu pozycji, które
#: wypadły z planu — pętla przechodzi wyłącznie po tym, co plan zawiera.
#: Więc przepięcie dostawcy „kupowane → RMPAK" PO ZASIEWIE zostawia detal
#: jednocześnie na ZK (zamówiony u dostawcy) i na liście do PW (robiony
#: u siebie). Zamówisz i zrobisz to samo.
#:
#: Lekarstwo jest ręczne: usunąć pozycję z ZK w Subiekcie albo cofnąć
#: dostawcę w arkuszu. Dlatego tu tylko OSTRZEGAMY — okno jest read-only,
#: a automatyczne czyszczenie cudzego zamówienia byłoby gorsze od problemu.
KOLOR_SIEROTA = "#e8b5b5"
KOLOR_NAGLOWKA_GRUPY = "#eaecee"

WSZYSTKIE = "— wszystkie —"
PROD_WLASNA = "produkcja własna (RMPAK)"
PROD_KUPOWANE = "kupowane gotowe (dostawca)"


# ── warstwa danych (bez Tk) ──────────────────────────────────────────────────
def _dostawcy_pozycji(project_id):
    """{SYMBOL: nazwa dostawcy} dla wszystkich pozycji projektu.

    Nazwy dostawców mieszkają w master.sqlite, baza projektu trzyma tylko
    supplier_id — ten sam podział co w subiekt_zamowienia.
    """
    path = os.path.join(PROJECTS_DIR, f"project_{project_id}.sqlite")
    if not os.path.isfile(path):
        return {}
    try:
        from subiekt_zamowienia import _nazwy_dostawcow
        nazwy = _nazwy_dostawcow()
    except Exception:
        nazwy = {}
    out = {}
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            cols = {r[1] for r in con.execute("PRAGMA table_info('items')")}
            if "supplier_id" not in cols:
                return {}
            for nr, sid in con.execute(
                    "SELECT COALESCE(work_drawing_no, norm_drawing_no, src_drawing_no, ''), "
                    "supplier_id FROM items WHERE COALESCE(is_hidden, 0) = 0"):
                nr = (nr or "").strip().upper()
                if nr and sid is not None:
                    out[nr] = nazwy.get(sid, "") or ""
        finally:
            con.close()
    except sqlite3.Error:
        pass
    return out


def _komplet_cli(symbole, timeout):
    """Stara ścieżka: osobny proces NexoRecon.exe."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")
    import tempfile
    out = os.path.join(tempfile.mkdtemp(prefix="subiekt_zloz_"), "komplet.json")
    argv = [exe, "komplet"] + [f"--symbol={s}" for s in symbole] + [f"--out={out}"]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=flags)
    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(blad_mostu(exe, "komplet", proc, out))
    with open(out, encoding="utf-8") as f:
        return json.load(f)


def _komplet_z_mostu(symbole, timeout=TIMEOUT_S):
    """{SYMBOL: {Istnieje, Rodzaj, Skladniki, WchodziW}} — jednym wywołaniem.

    Wszystkie złożenia naraz, nie po jednym: most liczy „WchodziW” przelotem
    po ~150 kompletach w bazie i robiłby to 27 razy zamiast raz.
    """
    if not symbole:
        return {}
    try:
        import subiekt_bridge
        dane = subiekt_bridge.wywolaj(
            "komplet", [], timeout=timeout, symbole=list(symbole),
            fallback=lambda: _komplet_cli(symbole, timeout))
    except ImportError:
        dane = _komplet_cli(symbole, timeout)
    return {(p.get("Pytany") or p.get("Symbol") or "").strip().upper(): p
            for p in (dane or {}).get("pozycje", [])}


def _pozycje_zk_projektu(numer_projektu, timeout=TIMEOUT_S):
    """({SYMBOL: ilość}, numer_ZK) — co realnie stoi na ZK tego projektu.

    Do wykrywania SIEROT: pozycji produkcji własnej, które mimo filtra
    siedzą na zamówieniu do dostawcy (patrz KOLOR_SIEROTA).

    Brak ZK albo brak mostu NIE jest błędem — wtedy po prostu nie ma czego
    porównywać i wykrywanie sierot się nie odpala. Okno ma działać także
    przed zasiewem i na stanowisku bez Subiekta.
    """
    if not str(numer_projektu or "").strip():
        return {}, None
    try:
        import subiekt_dokumenty_gui
        dok = subiekt_dokumenty_gui.pobierz_dokumenty(limit=400, timeout=timeout)
    except Exception:
        return {}, None
    cel = str(numer_projektu).strip().upper()
    for d in dok:
        if d.get("rodzaj") != "ZK":
            continue
        if str(d.get("projekt") or "").strip().upper() != cel:
            continue
        poz = {}
        for p in d.get("pozycje") or []:
            k = str(p.get("symbol") or "").strip().upper()
            if k:
                poz[k] = poz.get(k, 0) + float(p.get("ilosc") or 0)
        return poz, d.get("numer")
    return {}, None


def _para(symbol, ilosc):
    try:
        ile = round(float(ilosc), 3)
    except (TypeError, ValueError):
        ile = 0.0
    return (str(symbol or "").strip().upper(), ile)


def _roznice_skladu(drzewko, subiekt):
    """[(symbol, w_drzewku, w_subiekcie)] — puste = zgodne.

    Porównanie PARAMI (symbol, ilość). Sama liczba składników nie wystarczy:
    4 na 4 może kryć podmienioną pozycję albo zmienioną ilość.
    """
    d = {}
    for s in drzewko or []:
        k, ile = _para(s.get("symbol"), s.get("ilosc"))
        d[k] = d.get(k, 0) + ile
    s_ = {}
    for s in subiekt or []:
        k, ile = _para(s.get("Symbol"), s.get("Ilosc"))
        s_[k] = s_.get(k, 0) + ile
    out = []
    for k in sorted(set(d) | set(s_)):
        if abs(d.get(k, 0) - s_.get(k, 0)) > 0.0005:
            out.append((k, d.get(k, 0), s_.get(k, 0)))
    return out


def zbierz_zlozenia(project_id, project_name, timeout=TIMEOUT_S):
    """Wszystko, co okno pokazuje. Zwraca (wiersze, info).

    wiersze — lista słowników, problemy na początku;
    info    — {"drzewko_ok": bool, "uwaga_drzewka": str|None,
               "razem", "ok", "puste", "brak", "rozjazd"}.

    Gdy drzewka z V:\\ nie ma, porównanie składu jest WYŁĄCZONE, a nie
    „wszystko ROZJAZD”: bez drzewka każdy komplet miałby 0 składników po
    stronie projektu i wyglądał na zepsuty, choć w Subiekcie jest w porządku.
    """
    import subiekt_projekt
    plan, _items, uwaga, _poza, _ukr, _bez = subiekt_projekt.build_plan(
        project_id, project_name, "RMPAK", project_name)
    drzewko_ok = not uwaga
    poz = plan["pozycje"]
    by = {p["symbol"].strip().upper(): p for p in poz}
    zloz = [p for p in poz if str(p["typ"]).strip().upper() in KOMPLETY]

    # Rodzic Z DRZEWKA PROJEKTU — a nie z mostu. Most liczy „WchodziW” po
    # całej bazie Subiekta, więc pokazałby też zespoły z innych projektów,
    # w których ten sam komplet występuje. Tu interesuje nas ta maszyna.
    rodzic = {}
    for p in zloz:
        for s in p.get("skladniki") or []:
            k = str(s.get("symbol") or "").strip().upper()
            if k in by and str(by[k]["typ"]).strip().upper() in KOMPLETY:
                rodzic.setdefault(k, p["symbol"])

    dostawcy = _dostawcy_pozycji(project_id)
    z_mostu = _komplet_z_mostu([p["symbol"] for p in zloz], timeout)
    # Co stoi na ZK — do wykrycia SIEROT (produkcja własna mimo to zamówiona).
    # Osobne wywołanie mostu, ale tanie: ~1 s przy 31 dokumentach.
    na_zk, zk_numer = _pozycje_zk_projektu(
        subiekt_projekt.numer_projektu(project_name, project_id), timeout)

    wiersze = []
    for p in zloz:
        sym = p["symbol"]
        k = sym.strip().upper()
        d = z_mostu.get(k, {})
        istnieje = bool(d.get("Istnieje"))
        skl_sub = d.get("Skladniki") or []
        skl_drz = p.get("skladniki") or []
        roznice = []
        if not istnieje:
            status = STATUS_BRAK
        elif not skl_sub:
            status = STATUS_PUSTY
        elif drzewko_ok and (roznice := _roznice_skladu(skl_drz, skl_sub)):
            status = STATUS_ROZJAZD
        else:
            status = STATUS_OK
        wchodzi = rodzic.get(k, "")
        if not wchodzi:
            # Poza drzewkiem projektu — może siedzieć w komplecie z innego
            # projektu (biblioteka). Bierzemy pierwszy z mostu, informacyjnie.
            w = d.get("WchodziW") or []
            if w:
                wchodzi = str(w[0].get("Symbol") or "").strip()
        wiersze.append({
            "symbol": sym,
            "nazwa": p.get("nazwa") or sym,
            "typ": str(p["typ"]).strip().upper(),
            "ilosc": p.get("ilosc") or 0,
            "skl_drzewko": len(skl_drz) if drzewko_ok else None,
            "skl_subiekt": len(skl_sub),
            "istnieje": istnieje,
            "status": status,
            "roznice": roznice,
            "wchodzi_w": wchodzi,
            "w_projekcie": wchodzi.strip().upper() in by if wchodzi else False,
            "produkcja_wlasna": bool(p.get("produkcja_wlasna")),
            "dostawca": dostawcy.get(k, ""),
            "biblioteczne": bool(p.get("biblioteczne")),
            "sklad_subiekt": skl_sub,
            "sklad_drzewko": skl_drz,
            # SIEROTA: robimy u siebie, a mimo to jest na ZK u dostawcy.
            # Osobno od `status`, bo skład może być całkiem w porządku.
            "sierota": bool(p.get("produkcja_wlasna")) and k in na_zk,
            "na_zk_ile": na_zk.get(k),
        })
    # Sieroty PRZED wszystkim innym: to błąd danych, który sam się nie
    # naprawi przy ponownym zasiewie, więc ma być pierwszy na ekranie.
    wiersze.sort(key=lambda w: (0 if w["sierota"] else 1,
                                RANGA[w["status"]], w["symbol"]))

    info = {
        "drzewko_ok": drzewko_ok,
        "uwaga_drzewka": uwaga,
        "razem": len(wiersze),
        "ok": sum(1 for w in wiersze if w["status"] == STATUS_OK),
        "puste": sum(1 for w in wiersze if w["status"] == STATUS_PUSTY),
        "brak": sum(1 for w in wiersze if w["status"] == STATUS_BRAK),
        "rozjazd": sum(1 for w in wiersze if w["status"] == STATUS_ROZJAZD),
        "sieroty": sum(1 for w in wiersze if w["sierota"]),
        "zk_numer": zk_numer,
        "dostawcy": dostawcy,
        "typy": {k: str(v["typ"]).strip().upper() for k, v in by.items()},
    }
    return wiersze, info


# ── okno ─────────────────────────────────────────────────────────────────────
class ZlozeniaWindow(tk.Toplevel, Kreciolek):
    KOL = [("symbol", "Numer rysunku", 140), ("nazwa", "Nazwa", 240),
           ("typ", "Typ", 45), ("ilosc", "Ilość w proj.", 85),
           ("skl_drzewko", "Składników (drzewko)", 120),
           ("skl_subiekt", "Składników (Subiekt)", 120),
           ("istnieje", "Stan kartoteki", 100), ("status", "Zgodność", 110),
           ("wchodzi_w", "Wchodzi w", 140), ("produkcja", "Produkcja", 170),
           ("na_zk", "Na ZK", 110)]
    KOL_SKL = [("symbol", "Symbol", 140), ("nazwa", "Nazwa", 240),
               ("ilosc", "Ilość", 60), ("rodzaj", "Rodzaj", 110),
               ("dostawca", "Dostawca", 130)]

    def __init__(self, parent, project_id, project_name):
        super().__init__(parent)
        self.project_id = project_id
        self.project_name = project_name or ""
        self.wiersze = []
        self.widoczne = []
        self.info = {}
        self.biezacy = None

        self.title(f"Złożenia projektu — {self.project_name}")
        self.geometry("1280x800")
        self.minsize(900, 500)
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

        self._build_ui()
        self.after(100, self._load_async)

    # ── UI ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        bar = tk.Frame(self, bg="#2c3e50")
        bar.pack(side=tk.TOP, fill=tk.X)
        tk.Label(bar, text="🧩 Złożenia (komplety)", bg="#2c3e50", fg="white",
                 font=("Arial", 12, "bold"), padx=12, pady=8).pack(side=tk.LEFT)
        tk.Label(bar, text=f"Projekt: {self.project_id}   {self.project_name}",
                 bg="#2c3e50", fg="#bdc3c7", font=("Arial", 10)).pack(side=tk.LEFT, padx=(8, 0))
        self.lbl_wiek = tk.Label(bar, text="", bg="#2c3e50", fg="#e74c3c",
                                 font=("Arial", 10, "bold"))
        self.lbl_wiek.pack(side=tk.LEFT, padx=(16, 0))
        tk.Button(bar, text="✕ Zamknij", command=self.destroy, bg="#7f8c8d", fg="white",
                  font=("Arial", 9, "bold"), padx=10).pack(side=tk.RIGHT, padx=(4, 10), pady=6)
        self.btn_refresh = tk.Button(bar, text="⟳ Odśwież", command=self._load_async,
                                     bg="#2980b9", fg="white", font=("Arial", 9, "bold"), padx=10)
        self.btn_refresh.pack(side=tk.RIGHT, padx=4, pady=6)

        # filtry
        f = tk.Frame(self, padx=10, pady=6)
        f.pack(side=tk.TOP, fill=tk.X)
        tk.Label(f, text="Szukaj:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refill())
        tk.Entry(f, textvariable=self.search_var, width=32).pack(side=tk.LEFT, padx=(4, 4))
        tk.Label(f, text="(numer, nazwa)", fg="gray50", font=("Arial", 8)).pack(side=tk.LEFT, padx=(0, 14))

        tk.Label(f, text="Typ:").pack(side=tk.LEFT)
        self.typ_var = tk.StringVar(value=WSZYSTKIE)
        ttk.Combobox(f, textvariable=self.typ_var, state="readonly", width=12,
                     values=[WSZYSTKIE, "Z", "ZZ"]).pack(side=tk.LEFT, padx=(4, 14))
        tk.Label(f, text="Zgodność:").pack(side=tk.LEFT)
        self.status_var = tk.StringVar(value=WSZYSTKIE)
        ttk.Combobox(f, textvariable=self.status_var, state="readonly", width=16,
                     values=[WSZYSTKIE, STATUS_OK, STATUS_PUSTY, STATUS_BRAK, STATUS_ROZJAZD]
                     ).pack(side=tk.LEFT, padx=(4, 14))
        tk.Label(f, text="Produkcja:").pack(side=tk.LEFT)
        self.prod_var = tk.StringVar(value=WSZYSTKIE)
        ttk.Combobox(f, textvariable=self.prod_var, state="readonly", width=26,
                     values=[WSZYSTKIE, PROD_WLASNA, PROD_KUPOWANE]).pack(side=tk.LEFT, padx=(4, 14))
        self.problemy_var = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="Tylko problemy", variable=self.problemy_var,
                       command=self._refill).pack(side=tk.LEFT)
        for v in (self.typ_var, self.status_var, self.prod_var):
            v.trace_add("write", lambda *_: self._refill())

        # legenda + podsumowanie (podsumowanie NIE zależy od filtrów)
        leg = tk.Frame(self, bg="#ecf0f1")
        leg.pack(side=tk.TOP, fill=tk.X)
        tk.Label(leg, text="Legenda:", bg="#ecf0f1", fg="#7f8c8d",
                 font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=(12, 6), pady=(0, 5))
        for kolor, opis in ((KOLOR[STATUS_OK], "OK — skład zgodny z drzewkiem"),
                            (KOLOR[STATUS_PUSTY], "PUSTY — kartoteka jest, składu brak"),
                            (KOLOR[STATUS_BRAK], "BRAK — kartoteki nie ma w Subiekcie"),
                            (KOLOR[STATUS_ROZJAZD], "ROZJAZD — skład inny niż w drzewku"),
                            (KOLOR_SIEROTA, "SIEROTA — robimy u siebie, a jest na ZK")):
            tk.Label(leg, text="  ", bg=kolor, relief=tk.SOLID, bd=1).pack(
                side=tk.LEFT, padx=(6, 3), pady=(0, 5))
            tk.Label(leg, text=opis, bg="#ecf0f1", fg="#2c3e50",
                     font=("Arial", 8)).pack(side=tk.LEFT, pady=(0, 5))
        self.summary = tk.Label(leg, text="", bg="#ecf0f1", fg="#2c3e50",
                                font=("Arial", 9, "bold"))
        self.summary.pack(side=tk.RIGHT, padx=12, pady=(0, 5))

        self.lbl_uwaga = tk.Label(self, text="", bg="#fcf3cf", fg="#7d6608",
                                  font=("Arial", 9), anchor="w", padx=12, pady=4)
        # pakowany dopiero, gdy jest co pokazać (brak drzewka)

        # Ostrzeżenie o sierotach — osobny pasek, czerwony, NAD tabelą.
        # To jedyny problem w tym oknie, który wymaga ręcznej naprawy
        # w Subiekcie, więc nie może się chować w kolumnie.
        self.lbl_sieroty = tk.Label(self, text="", bg="#f2dede", fg="#a94442",
                                    font=("Arial", 9, "bold"), anchor="w",
                                    justify="left", padx=12, pady=6)

        if Sheet is None:
            tk.Label(self, text="Brak biblioteki tksheet", fg="#c0392b").pack(pady=20)
            self.sheet = self.sheet_skl = None
            return

        paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 4))
        gora = tk.Frame(paned)
        dol = ttk.PanedWindow(paned, orient=tk.HORIZONTAL)
        paned.add(gora, weight=3)
        paned.add(dol, weight=2)

        self.sheet = Sheet(gora, headers=[k[1] for k in self.KOL],
                           column_width=120, theme="light blue")
        self.sheet.set_options(show_selected_cells_border=True,
                               enable_edit_cell_auto_resize=False,
                               empty_horizontal=0, empty_vertical=0)
        self.sheet.enable_bindings(("single_select", "drag_select", "select_all",
                                    "column_width_resize", "arrowkeys", "copy",
                                    "right_click_popup_menu", "rc_select"))
        podepnij_szerokosci(self, self.sheet, "zlozenia_lista", [k[2] for k in self.KOL])
        self.sheet.bind("<ButtonRelease-1>", self._on_select, add="+")
        self.sheet.bind("<KeyRelease-Up>", self._on_select, add="+")
        self.sheet.bind("<KeyRelease-Down>", self._on_select, add="+")
        self.sheet.bind("<Double-Button-1>", self._on_dwuklik_lista, add="+")
        self.sheet.popup_menu_add_command("↑ Pokaż rodzica (w co wchodzi)", self._do_rodzica)
        self.sheet.popup_menu_add_command("🔍 Karta pozycji", self._karta_z_listy)
        self.sheet.pack(fill=tk.BOTH, expand=True)

        # dół-lewo: skład
        lewo = tk.Frame(dol)
        prawo = tk.Frame(dol)
        dol.add(lewo, weight=3)
        dol.add(prawo, weight=2)
        self.lbl_skl = tk.Label(lewo, text="Skład — kliknij złożenie powyżej",
                                bg="#34495e", fg="white", font=("Arial", 9, "bold"),
                                anchor="w", padx=10, pady=4)
        self.lbl_skl.pack(side=tk.TOP, fill=tk.X)
        self.sheet_skl = Sheet(lewo, headers=[k[1] for k in self.KOL_SKL],
                               column_width=120, theme="light green")
        self.sheet_skl.set_options(show_selected_cells_border=True,
                                   enable_edit_cell_auto_resize=False,
                                   empty_horizontal=0, empty_vertical=0)
        self.sheet_skl.enable_bindings(("single_select", "drag_select", "select_all",
                                        "column_width_resize", "arrowkeys", "copy",
                                        "right_click_popup_menu", "rc_select"))
        podepnij_szerokosci(self, self.sheet_skl, "zlozenia_sklad", [k[2] for k in self.KOL_SKL])
        self.sheet_skl.bind("<Double-Button-1>", self._karta_ze_skladu, add="+")
        self.sheet_skl.popup_menu_add_command("🔍 Karta pozycji", self._karta_ze_skladu)
        self.sheet_skl.pack(fill=tk.BOTH, expand=True)

        # dół-prawo: szczegóły
        tk.Label(prawo, text="Szczegóły złożenia", bg="#34495e", fg="white",
                 font=("Arial", 9, "bold"), anchor="w", padx=10, pady=4).pack(side=tk.TOP, fill=tk.X)
        det = tk.Frame(prawo, padx=12, pady=8)
        det.pack(fill=tk.BOTH, expand=True)
        det.columnconfigure(1, weight=1)
        self.det = {}
        pola = [("symbol", "Numer rysunku:"), ("nazwa", "Nazwa:"), ("typ", "Typ:"),
                ("ilosc", "Ilość w projekcie:"), ("skl_drzewko", "Składników (drzewko):"),
                ("skl_subiekt", "Składników (Subiekt):"), ("istnieje", "Stan kartoteki:"),
                ("status", "Zgodność składu:"), ("wchodzi_w", "Wchodzi w:"),
                ("produkcja", "Produkcja własna:")]
        for r, (klucz, etykieta) in enumerate(pola):
            tk.Label(det, text=etykieta, anchor="e", fg="#555", font=("Arial", 9)).grid(
                row=r, column=0, sticky="e", padx=(0, 8), pady=2)
            if klucz == "wchodzi_w":
                ramka = tk.Frame(det)
                ramka.grid(row=r, column=1, sticky="w", pady=2)
                lab = tk.Label(ramka, text="—", anchor="w", font=("Arial", 9, "bold"))
                lab.pack(side=tk.LEFT)
                self.btn_rodzic = tk.Button(ramka, text="↑ pokaż rodzica", font=("Arial", 8),
                                            command=self._do_rodzica, state=tk.DISABLED)
                self.btn_rodzic.pack(side=tk.LEFT, padx=(8, 0))
            else:
                lab = tk.Label(det, text="—", anchor="w", font=("Arial", 9, "bold"))
                lab.grid(row=r, column=1, sticky="w", pady=2)
            self.det[klucz] = lab
        tk.Label(det, text="Uwagi:", anchor="ne", fg="#555", font=("Arial", 9)).grid(
            row=len(pola), column=0, sticky="ne", padx=(0, 8), pady=(8, 2))
        self.det_uwagi = tk.Text(det, height=6, wrap="word", font=("Arial", 9),
                                 relief=tk.SOLID, bd=1, bg="#fdfefe", state=tk.DISABLED)
        self.det_uwagi.grid(row=len(pola), column=1, sticky="nsew", pady=(8, 2))
        det.rowconfigure(len(pola), weight=1)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#ecf0f1", fg="#2c3e50", font=("Arial", 9))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    # ── ładowanie ─────────────────────────────────────────────────────────
    def _load_async(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.start_kreciolek("Czytam złożenia (drzewko + Subiekt)")
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        try:
            wiersze, info = zbierz_zlozenia(self.project_id, self.project_name)
            self.after(0, lambda: self._load_done(wiersze, info, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._load_done([], {}, err))

    def _load_done(self, wiersze, info, error):
        self.stop_kreciolek()
        self.zaznacz_odczyt(self.lbl_wiek)
        self.btn_refresh.config(state=tk.NORMAL)
        if error:
            self.status.config(text="Błąd.")
            messagebox.showerror("Złożenia", error, parent=self)
            return
        self.wiersze, self.info = wiersze, info
        self.biezacy = None
        if info.get("drzewko_ok"):
            self.lbl_uwaga.pack_forget()
        else:
            self.lbl_uwaga.config(
                text="⚠ Brak drzewka projektu — porównanie składu WYŁĄCZONE. "
                     f"Zgodność pokazuje tylko, czy Subiekt ma skład. ({info.get('uwaga_drzewka')})")
            self.lbl_uwaga.pack(side=tk.TOP, fill=tk.X, before=self.status)
        self.summary.config(text=(
            f"Złożeń: {info['razem']}   |   OK: {info['ok']}   |   Puste: {info['puste']}"
            f"   |   Brak: {info['brak']}   |   Rozjazd: {info['rozjazd']}"
            + (f"   |   ⚠ SIEROTY: {info['sieroty']}" if info.get("sieroty") else "")))

        sieroty = [w for w in wiersze if w["sierota"]]
        if sieroty:
            zk = info.get("zk_numer") or "ZK projektu"
            self.lbl_sieroty.config(
                text=f"⚠ {len(sieroty)} poz. produkcji własnej SIEDZI NA {zk} — "
                     "zamówione u dostawcy i jednocześnie robione u siebie.\n"
                     "Zwykle skutek zmiany dostawcy PO zasiewie: ponowny zapis projektu "
                     "NIE zdejmie ich z dokumentu. Usuń pozycję z ZK w Subiekcie albo "
                     "cofnij dostawcę w arkuszu.   →   "
                     + ", ".join(w["symbol"] for w in sieroty[:8])
                     + (" …" if len(sieroty) > 8 else ""))
            self.lbl_sieroty.pack(side=tk.TOP, fill=tk.X, before=self.status)
        else:
            self.lbl_sieroty.pack_forget()
        self._refill()

    # ── filtrowanie ───────────────────────────────────────────────────────
    def _pasuje(self, w, szukaj, typ, status, prod, tylko_problemy):
        if typ != WSZYSTKIE and w["typ"] != typ:
            return False
        if status != WSZYSTKIE and w["status"] != status:
            return False
        if prod == PROD_WLASNA and not w["produkcja_wlasna"]:
            return False
        if prod == PROD_KUPOWANE and w["produkcja_wlasna"]:
            return False
        if tylko_problemy and w["status"] not in PROBLEMY and not w["sierota"]:
            return False
        if szukaj and szukaj not in f"{w['symbol']} {w['nazwa']}".lower():
            return False
        return True

    def _refill(self):
        if not self.sheet:
            return
        szukaj = (self.search_var.get() or "").strip().lower()
        typ, status, prod = self.typ_var.get(), self.status_var.get(), self.prod_var.get()
        tylko = bool(self.problemy_var.get())
        self.widoczne = [w for w in self.wiersze
                         if self._pasuje(w, szukaj, typ, status, prod, tylko)]

        dane = []
        for w in self.widoczne:
            prod_txt = ("tak (RMPAK)" if w["produkcja_wlasna"]
                        else f"nie ({w['dostawca']})" if w["dostawca"] else "nie (kupowane)")
            dane.append([
                w["symbol"], w["nazwa"], w["typ"], f"{w['ilosc']:g}",
                "—" if w["skl_drzewko"] is None else str(w["skl_drzewko"]),
                str(w["skl_subiekt"]),
                "istnieje" if w["istnieje"] else "BRAK",
                w["status"], w["wchodzi_w"] or "—", prod_txt,
                (f"⚠ {w['na_zk_ile']:g} szt." if w["sierota"]
                 else f"{w['na_zk_ile']:g} szt." if w["na_zk_ile"] else "—")])
        self.sheet.set_sheet_data(dane, reset_col_positions=False, redraw=False)
        try:
            self.sheet.dehighlight_all()
        except Exception:
            pass
        i_status = [k for k, *_ in self.KOL].index("status")
        i_ist = [k for k, *_ in self.KOL].index("istnieje")
        i_zk = [k for k, *_ in self.KOL].index("na_zk")
        for i, w in enumerate(self.widoczne):
            # SIEROTA bije status składu: skład może być zgodny, a pozycja
            # i tak jest w złym torze — to ważniejsza informacja.
            bg = KOLOR_SIEROTA if w["sierota"] else KOLOR[w["status"]]
            # Cały wiersz kolorem statusu, żeby problem był widoczny bez
            # czytania kolumny „Zgodność” — ale kolumny status/stan mocniej.
            for c in range(len(self.KOL)):
                self.sheet.highlight_cells(row=i, column=c, bg=bg)
            if w["sierota"]:
                self.sheet.highlight_cells(row=i, column=i_zk, bg=KOLOR_SIEROTA, fg="#a94442")
            if szukaj:
                self.sheet.highlight_cells(row=i, column=0, bg="#fcf3cf")
            if not w["istnieje"]:
                self.sheet.highlight_cells(row=i, column=i_ist, bg=KOLOR[STATUS_BRAK], fg="#a94442")
            self.sheet.highlight_cells(row=i, column=i_status, bg=bg,
                                       fg="#1e8449" if w["status"] == STATUS_OK else "#a94442")
        self.sheet.redraw()

        wid = f"Widocznych: {len(self.widoczne)} z {len(self.wiersze)}"
        prob = sum(1 for w in self.widoczne if w["status"] in PROBLEMY)
        self.status.config(text=wid + (f"   ·   problemów w widoku: {prob}" if prob else ""))

        # Bieżący zniknął z widoku → panele czyścimy, żeby nie opisywały
        # czegoś, czego nie ma na liście.
        if self.biezacy and self.biezacy not in self.widoczne:
            self.biezacy = None
            self._pokaz_szczegoly(None)

    # ── wybór / szczegóły ─────────────────────────────────────────────────
    def _wiersz_zaznaczony(self):
        try:
            sel = self.sheet.get_currently_selected()
            r = getattr(sel, "row", None)
            if r is not None and 0 <= r < len(self.widoczne):
                return r
        except Exception:
            pass
        return None

    def _on_select(self, _event=None):
        r = self._wiersz_zaznaczony()
        if r is None:
            return
        w = self.widoczne[r]
        if w is self.biezacy:
            return
        self.biezacy = w
        self._pokaz_szczegoly(w)

    def _on_dwuklik_lista(self, _event=None):
        """Dwuklik w kolumnę „Wchodzi w” → skok do rodzica."""
        try:
            sel = self.sheet.get_currently_selected()
            col = getattr(sel, "column", None)
        except Exception:
            col = None
        if col == [k for k, *_ in self.KOL].index("wchodzi_w"):
            self._do_rodzica()

    def _do_rodzica(self):
        """Zaznacza rodzica bieżącego złożenia. Ukryty filtrem → filtry w dół.

        To jest to, po co ktoś chciałby drzewa: „gdzie to siedzi”. Gdy rodzic
        wypadł przez „Tylko problemy”, zdejmujemy filtry, zamiast mówić
        „nie widać” — użytkownik chciał go zobaczyć, nie usłyszeć o filtrze.
        """
        w = self.biezacy
        if not w or not w["wchodzi_w"]:
            return
        cel = w["wchodzi_w"].strip().upper()
        if not w["w_projekcie"]:
            messagebox.showinfo(
                "Wchodzi w",
                f"{w['wchodzi_w']} nie jest złożeniem TEGO projektu — "
                "to komplet z innego projektu albo z biblioteki, w którym ten "
                "symbol występuje w Subiekcie.", parent=self)
            return
        idx = next((i for i, x in enumerate(self.widoczne)
                    if x["symbol"].strip().upper() == cel), None)
        if idx is None:
            self.problemy_var.set(False)
            self.status_var.set(WSZYSTKIE)
            self.typ_var.set(WSZYSTKIE)
            self.prod_var.set(WSZYSTKIE)
            self.search_var.set("")          # trace odświeży listę
            idx = next((i for i, x in enumerate(self.widoczne)
                        if x["symbol"].strip().upper() == cel), None)
        if idx is None:
            return
        try:
            self.sheet.select_row(idx)
            self.sheet.see(row=idx, column=0)
        except Exception:
            pass
        self.biezacy = self.widoczne[idx]
        self._pokaz_szczegoly(self.biezacy)

    def _pokaz_szczegoly(self, w):
        if not self.sheet_skl:
            return
        if w is None:
            for lab in self.det.values():
                lab.config(text="—", fg="black")
            self.btn_rodzic.config(state=tk.DISABLED)
            self._ustaw_uwagi("")
            self.sheet_skl.set_sheet_data([], reset_col_positions=False)
            self.lbl_skl.config(text="Skład — kliknij złożenie powyżej")
            return

        self.det["symbol"].config(text=w["symbol"])
        self.det["nazwa"].config(text=w["nazwa"])
        self.det["typ"].config(text=w["typ"])
        self.det["ilosc"].config(text=f"{w['ilosc']:g} szt.")
        self.det["skl_drzewko"].config(
            text="— (brak drzewka)" if w["skl_drzewko"] is None else str(w["skl_drzewko"]))
        self.det["skl_subiekt"].config(text=str(w["skl_subiekt"]))
        self.det["istnieje"].config(text="istnieje" if w["istnieje"] else "BRAK",
                                    fg="#1e8449" if w["istnieje"] else "#a94442")
        self.det["status"].config(text=w["status"],
                                  fg="#1e8449" if w["status"] == STATUS_OK else "#a94442")
        self.det["wchodzi_w"].config(text=w["wchodzi_w"] or "— (korzeń albo poza drzewkiem)")
        self.btn_rodzic.config(state=tk.NORMAL if w["wchodzi_w"] else tk.DISABLED)
        self.det["produkcja"].config(
            text="tak (RMPAK)" if w["produkcja_wlasna"]
            else f"nie — dostawca {w['dostawca']}" if w["dostawca"] else "nie (kupowane)")

        # uwagi — po co komuś ten wiersz
        if w["status"] == STATUS_BRAK:
            uw = ("Kartoteki nie ma w Subiekcie. Projekt nie został zasiany albo zasiew "
                  "pominął tę pozycję — sprawdź w oknie „Projekt / Aktualizacja”.")
        elif w["status"] == STATUS_PUSTY and w["biblioteczne"]:
            uw = ("Złożenie BIBLIOTECZNE bez składu: jego skład mieszka w bibliotece B:\\, "
                  "drzewko projektu go nie zna. Magazynier nie ma z czego go złożyć. "
                  "Do rozstrzygnięcia w „Projekt / Aktualizacja” → Decyzje "
                  "(założyć bez składu / uzupełnić / pominąć).")
        elif w["status"] == STATUS_PUSTY:
            uw = ("Kartoteka jest, ale bez składu — komplet wygląda na poprawny, a nie da się "
                  "go zrealizować. Skład wpisuje zasiew w „Projekt / Aktualizacja”.")
        elif w["status"] == STATUS_ROZJAZD:
            linie = [f"  {s}:  drzewko {d:g}  ↔  Subiekt {sb:g}" for s, d, sb in w["roznice"][:12]]
            uw = ("Skład w Subiekcie RÓŻNI SIĘ od drzewka:\n" + "\n".join(linie)
                  + ("\n  …" if len(w["roznice"]) > 12 else "")
                  + "\n\nPonowny zapis w „Projekt / Aktualizacja” nadpisze skład planem.")
        else:
            uw = "Zgodny z drzewkiem. Brak uwag."
        if w["sierota"]:
            zk = self.info.get("zk_numer") or "ZK projektu"
            uw = (f"⚠ SIEROTA: pozycja jest oznaczona jako produkcja własna (RMPAK), "
                  f"a mimo to stoi na {zk} w ilości {w['na_zk_ile']:g} szt. — "
                  "zamówiona u dostawcy i jednocześnie robiona u siebie.\n\n"
                  "Skąd się bierze: zmiana dostawcy PO zasiewie. Zapis projektu dodaje "
                  "i poprawia pozycje, ale NIE USUWA z dokumentu tych, które wypadły "
                  "z planu — ponowny zapis tego nie naprawi.\n\n"
                  "Co zrobić: usunąć pozycję z ZK w Subiekcie albo cofnąć dostawcę "
                  "w arkuszu, jeśli jednak kupujemy.\n\n" + uw)
        self._ustaw_uwagi(uw)

        # skład: komplety osobno, towary osobno
        typy = self.info.get("typy", {})
        dostawcy = self.info.get("dostawcy", {})
        if w["sklad_subiekt"]:
            zrodlo = "Subiekt"
            skl = [(s.get("Symbol") or "", s.get("Nazwa") or "", s.get("Ilosc") or 0,
                    s.get("Rodzaj") or "") for s in w["sklad_subiekt"]]
        else:
            zrodlo = "wg drzewka — w Subiekcie PUSTY"
            skl = []
            for s in w["sklad_drzewko"]:
                k = str(s.get("symbol") or "").strip().upper()
                skl.append((s.get("symbol") or "", "", s.get("ilosc") or 0,
                            "Komplet" if typy.get(k) in KOMPLETY else "Towar"))
        komplety = [s for s in skl if str(s[3]).lower().startswith("komplet")]
        towary = [s for s in skl if s not in komplety]
        dane, naglowki = [], []
        for tytul, grupa in ((f"Komplety ({len(komplety)})", komplety),
                             (f"Towary ({len(towary)})", towary)):
            if not grupa:
                continue
            naglowki.append(len(dane))
            dane.append([tytul, "", "", "", ""])
            for sym, naz, ile, rodz in sorted(grupa, key=lambda s: str(s[0])):
                try:
                    ile_txt = f"{float(ile):g}"
                except (TypeError, ValueError):
                    ile_txt = str(ile)
                dane.append([sym, naz, ile_txt, rodz, dostawcy.get(str(sym).strip().upper(), "")])
        self.sheet_skl.set_sheet_data(dane, reset_col_positions=False, redraw=False)
        try:
            self.sheet_skl.dehighlight_all()
        except Exception:
            pass
        for r in naglowki:
            for c in range(len(self.KOL_SKL)):
                self.sheet_skl.highlight_cells(row=r, column=c, bg=KOLOR_NAGLOWKA_GRUPY, fg="#2c3e50")
        self.sheet_skl.redraw()
        self.lbl_skl.config(
            text=f"Skład:  {w['symbol']} — {w['nazwa']}   ·   {len(skl)} poz. ({zrodlo})")

    def _ustaw_uwagi(self, tekst):
        self.det_uwagi.config(state=tk.NORMAL)
        self.det_uwagi.delete("1.0", tk.END)
        self.det_uwagi.insert("1.0", tekst)
        self.det_uwagi.config(state=tk.DISABLED)

    # ── karta pozycji ─────────────────────────────────────────────────────
    def _karta(self, symbol):
        symbol = (symbol or "").strip()
        if not symbol or symbol.startswith(("Komplety (", "Towary (")):
            return
        try:
            import subiekt_pozycja_gui
            subiekt_pozycja_gui.otworz(self, symbol)
        except Exception as e:
            messagebox.showerror("Karta pozycji", str(e), parent=self)

    def _karta_z_listy(self, _event=None):
        if self.biezacy:
            self._karta(self.biezacy["symbol"])

    def _karta_ze_skladu(self, _event=None):
        try:
            sel = self.sheet_skl.get_currently_selected()
            r = getattr(sel, "row", None)
            if r is None:
                return
            self._karta(str(self.sheet_skl.get_cell_data(r, 0) or ""))
        except Exception:
            pass


def open_window(parent, project_id, project_name=""):
    """Punkt wejścia dla RM_BAZA."""
    w = ZlozeniaWindow(parent, project_id, project_name)
    try:
        wysrodkuj(w, parent)
    except Exception:
        pass
    return w


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 71
    nazwa = sys.argv[2] if len(sys.argv) > 2 else "3500 Dupal"
    root = tk.Tk()
    root.withdraw()
    w = open_window(root, pid, nazwa)
    w.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
