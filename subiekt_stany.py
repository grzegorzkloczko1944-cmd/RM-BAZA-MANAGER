# -*- coding: utf-8 -*-
"""
Podgląd stanów magazynowych z Subiekta nexo PRO dla pozycji projektu RM_BAZA.
TYLKO ODCZYT — ten moduł nigdy nic nie zapisuje do Subiekta.

Wywołanie z RM_BAZA (przycisk „SUBIEKT" w pasku):

    import subiekt_stany
    subiekt_stany.open_window(parent, project_id=22, only_drawings=[...])

`only_drawings` jest opcjonalne — bez niego okno bierze cały BOM projektu.

Dane idą przez most C# (`NexoRecon.exe stan --symbols-file=... --out=...`),
bo Sfera nexo to .NET 8 x64 i nie da się jej wołać wprost z Pythona.
Szczegóły i uzasadnienie: SUBIEKT_INTEGRACJA_PLAN.md, sekcje 10–12.
"""

import json
import os
import subprocess
import sqlite3
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox

# ── Ścieżki ─────────────────────────────────────────────────────────────────
# Most budowany jest do bin/Release obok repo. W .exe (PyInstaller) __file__
# wskazuje na katalog tymczasowy, więc trzymamy też ścieżkę stałą — ta sama
# pułapka co z kluczem AI (patrz pamięć „Pułapka .exe — trwałe ścieżki").
_HERE = os.path.dirname(os.path.abspath(__file__))
EXE_CANDIDATES = [
    os.path.join(_HERE, "subiekt_sfera", "NexoRecon", "bin", "Release", "NexoRecon.exe"),
    r"C:\RMPAK_CLIENT\Repozytoria\RM-BAZA-MANAGER\subiekt_sfera\NexoRecon\bin\Release\NexoRecon.exe",
    r"C:\RMPAK_CLIENT\NexoRecon\NexoRecon.exe",
]
CONFIG_PATH = r"C:\RMPAK_CLIENT\.nexo_sfera.json"
PROJECTS_DIR = r"Y:\RM_BAZA\projects"

TIMEOUT_S = 180


def _find_exe():
    for p in EXE_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


# ── Odczyt numerów rysunków z bazy projektu ─────────────────────────────────
def read_project_drawings(project_id):
    """[(numer, nazwa, ilosc_bom)] — jedna pozycja na numer rysunku.

    Kolejność work > norm > src jest ta sama, której użyto przy porównaniu
    zbiorów w planie (sekcja 12.2), żeby wyniki się zgadzały.
    """
    path = os.path.join(PROJECTS_DIR, f"project_{project_id}.sqlite")
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info('items')")}
        # Nazwa i ilość mają te same prefiksy co numer rysunku (work_ > src_),
        # a *_over to ręczne nadpisanie przez użytkownika — ma pierwszeństwo.
        name_cols = [c for c in ("name_over", "work_name", "src_name") if c in cols]
        qty_cols = [c for c in ("order_qty_over", "work_qty", "src_qty") if c in cols]
        sel = ["work_drawing_no", "norm_drawing_no", "src_drawing_no"] + name_cols + qty_cols
        rows = con.execute(f"SELECT {', '.join(sel)} FROM items").fetchall()
    finally:
        con.close()

    n0 = 3
    q0 = n0 + len(name_cols)

    def first(vals):
        for v in vals:
            if v is not None and str(v).strip() != "":
                return v
        return None

    out, seen = [], set()
    for r in rows:
        nr = first(r[0:3])
        nr = str(nr).strip() if nr is not None else None
        if not nr or nr in seen:
            continue
        seen.add(nr)
        nazwa = first(r[n0:q0])
        qty = first(r[q0:])
        out.append((nr, str(nazwa).strip() if nazwa is not None else "", qty))
    return out


def looks_like_drawing_no(s):
    """Czy to wygląda na numer rysunku, a nie na opis?

    W BOM-ach trafiają się nazwy wpisane w pole numeru („Przygotowanie
    powietrza", „Obejma") — sprawdzanie ich w Subiekcie nie ma sensu
    (plan, sekcja 12.2). Numer musi mieć cyfrę i nie może mieć spacji.
    """
    s = (s or "").strip()
    return bool(s) and any(c.isdigit() for c in s) and " " not in s


# ── Wywołanie mostu ─────────────────────────────────────────────────────────
def query_stock(symbols, timeout=TIMEOUT_S):
    """Pyta Subiekta o stany. Zwraca {pytany_symbol: dict}. Rzuca RuntimeError."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError(
            "Nie znaleziono NexoRecon.exe.\n\n"
            "Zbuduj most:\n"
            "  cd subiekt_sfera\\NexoRecon\n"
            "  dotnet build -c Release"
        )
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")

    tmpdir = tempfile.mkdtemp(prefix="subiekt_")
    lst = os.path.join(tmpdir, "symbole.txt")
    out = os.path.join(tmpdir, "stan.json")
    with open(lst, "w", encoding="utf-8") as f:
        f.write("\n".join(symbols))

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            [exe, "stan", f"--symbols-file={lst}", f"--out={out}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=flags,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Subiekt nie odpowiedział w {timeout} s.")

    if proc.returncode != 0 or not os.path.isfile(out):
        msg = (proc.stdout or "").strip() or (proc.stderr or "").strip() or "nieznany błąd"
        raise RuntimeError(f"Most zwrócił błąd (kod {proc.returncode}):\n\n{msg}")

    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    return {p["Pytany"]: p for p in data.get("pozycje", [])}


# ── Okno ────────────────────────────────────────────────────────────────────
class SubiektStanyWindow(tk.Toplevel):
    COLS = [
        ("nr",     "Nr rysunku",     140, "w"),
        ("bom",    "Ilość BOM",       75, "e"),
        ("stan",   "Stan Subiekt",    90, "e"),
        ("brak",   "Brakuje",         80, "e"),
        ("nazwa",  "Nazwa w Subiekcie", 260, "w"),
        ("cena",   "Ost. cena zak.",  95, "e"),
        ("data",   "Data zakupu",      90, "c"),
        ("status", "Status",          150, "w"),
    ]

    def __init__(self, parent, project_id, only_drawings=None):
        super().__init__(parent)
        self.project_id = project_id
        self.only_drawings = only_drawings
        self.rows = []

        self.title(f"Stany w Subiekcie — projekt {project_id}")
        self.geometry("1150x650")
        self.transient(parent)

        self._build_ui()
        self.after(100, self._load_async)

    def _build_ui(self):
        top = tk.Frame(self, bg="#34495e", height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)

        tk.Label(top, text="📦 Stany magazynowe z Subiekt nexo PRO",
                 bg="#34495e", fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)

        self.btn_refresh = tk.Button(top, text="🔄 Odśwież", command=self._load_async,
                                     bg="#3498db", fg="white", font=("Arial", 8),
                                     padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_refresh.pack(side=tk.RIGHT, padx=10, pady=8)

        self.var_only_missing = tk.BooleanVar(value=False)
        tk.Checkbutton(top, text="Tylko braki", variable=self.var_only_missing,
                       command=self._refill, bg="#34495e", fg="white", selectcolor="#e67e22",
                       font=("Arial", 8), activebackground="#34495e",
                       activeforeground="white").pack(side=tk.RIGHT, padx=4)

        # Pasek podsumowania — punkt 3: ile ma kartotekę, ile na stanie, ile brakuje
        self.summary = tk.Label(self, text="Wczytywanie…", bg="#ecf0f1", fg="#2c3e50",
                                font=("Arial", 9), anchor="w", padx=12, pady=6)
        self.summary.pack(side=tk.TOP, fill=tk.X)

        wrap = tk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 8))

        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in self.COLS], show="headings")
        for key, label, width, anchor in self.COLS:
            self.tree.heading(key, text=label, command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=width, anchor=anchor,
                             stretch=(key == "nazwa"), minwidth=50)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.tag_configure("ok",      background="#d5f5e3")   # starczy na magazynie
        self.tree.tag_configure("czesc",   background="#fdebd0")   # jest, ale za mało
        self.tree.tag_configure("brak",    background="#fadbd8")   # jest kartoteka, stan 0
        self.tree.tag_configure("nokart",  background="#eaecee")   # brak kartoteki
        self.tree.bind("<Double-1>", self._show_details)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    # ── wczytywanie ────────────────────────────────────────────────────────
    def _load_async(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.status.config(text="Łączenie z Subiektem…")
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        try:
            items = read_project_drawings(self.project_id)
            if self.only_drawings:
                wanted = {str(d).strip() for d in self.only_drawings}
                items = [it for it in items if it[0] in wanted]

            good = [it for it in items if looks_like_drawing_no(it[0])]
            skipped = len(items) - len(good)
            if not good:
                self.after(0, lambda: self._done([], 0, "Brak pozycji z numerem rysunku."))
                return

            stock = query_stock([it[0] for it in good])
            rows = []
            for nr, nazwa, qty in good:
                info = stock.get(nr, {})
                rows.append({
                    "nr": nr, "bom_name": nazwa, "bom_qty": qty,
                    "istnieje": bool(info.get("Istnieje")),
                    "symbol": info.get("Symbol"),
                    "nazwa": info.get("Nazwa") or "",
                    "stan": float(info.get("Dostepne") or 0),
                    "cena": info.get("OstatniaCenaZakupu"),
                    "data": info.get("DataOstatniegoZakupu") or "",
                    "dop": info.get("Dopasowanie") or "brak",
                    "mags": info.get("Magazyny") or [],
                })
            self.after(0, lambda: self._done(rows, skipped, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._done([], 0, err))

    def _done(self, rows, skipped, error):
        self.btn_refresh.config(state=tk.NORMAL)
        self.rows = rows
        if error:
            self.status.config(text="Błąd.")
            self.summary.config(text=error.split("\n")[0])
            messagebox.showerror("Subiekt", error, parent=self)
            return
        self._refill()
        note = f"   ({skipped} pozycji pominięto — w polu numeru jest opis, nie numer)" if skipped else ""
        self.status.config(text=f"Odczyt zakończony. Nic nie zapisano do Subiekta.{note}")

    # ── prezentacja ────────────────────────────────────────────────────────
    @staticmethod
    def _classify(r):
        if not r["istnieje"]:
            return "nokart", "brak kartoteki"
        need = r["bom_qty"]
        try:
            need = float(need) if need not in (None, "") else None
        except (TypeError, ValueError):
            need = None
        if r["stan"] <= 0:
            return "brak", "kartoteka, stan 0"
        if need and r["stan"] < need:
            return "czesc", f"za mało (brakuje {need - r['stan']:g})"
        label = "na stanie"
        if r["dop"] == "luzne":
            label += "  ⚠ dopasowano luźno"
        return "ok", label

    def _refill(self):
        self.tree.delete(*self.tree.get_children())
        only_missing = self.var_only_missing.get()
        n_kart = n_ok = n_czesc = n_brak = n_nokart = 0

        for r in self.rows:
            tag, status = self._classify(r)
            if tag == "ok":
                n_ok += 1
            elif tag == "czesc":
                n_czesc += 1
            elif tag == "brak":
                n_brak += 1
            else:
                n_nokart += 1
            if r["istnieje"]:
                n_kart += 1
            if only_missing and tag == "ok":
                continue

            need = r["bom_qty"]
            try:
                need_f = float(need) if need not in (None, "") else None
            except (TypeError, ValueError):
                need_f = None
            missing = ""
            if r["istnieje"] and need_f is not None and r["stan"] < need_f:
                missing = f"{need_f - r['stan']:g}"

            self.tree.insert("", "end", values=(
                r["nr"],
                "" if need in (None, "") else f"{need:g}" if isinstance(need, (int, float)) else need,
                f"{r['stan']:g}" if r["istnieje"] else "—",
                missing,
                r["nazwa"] or (r["bom_name"] if not r["istnieje"] else ""),
                f"{r['cena']:.2f}" if r["cena"] is not None else "",
                r["data"],
                status,
            ), tags=(tag,))

        total = len(self.rows)
        pct = (n_kart / total * 100) if total else 0
        self.summary.config(text=(
            f"Pozycji: {total}    "
            f"z kartoteką: {n_kart} ({pct:.0f}%)    "
            f"✅ na stanie: {n_ok}    "
            f"⚠ za mało: {n_czesc}    "
            f"❌ stan 0: {n_brak}    "
            f"⬜ brak kartoteki: {n_nokart}    "
            f"→ do zamówienia: {n_czesc + n_brak + n_nokart}"
        ))

    def _sort_by(self, key, _state={}):
        rev = _state[key] = not _state.get(key, False)
        idx = [c[0] for c in self.COLS].index(key)
        items = [(self.tree.set(i, key), i) for i in self.tree.get_children()]

        def conv(v):
            try:
                return (0, float(str(v).replace(",", ".")))
            except ValueError:
                return (1, str(v).lower())
        items.sort(key=lambda t: conv(t[0]), reverse=rev)
        for pos, (_, i) in enumerate(items):
            self.tree.move(i, "", pos)

    def _show_details(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        nr = self.tree.set(sel[0], "nr")
        r = next((x for x in self.rows if x["nr"] == nr), None)
        if not r:
            return
        if not r["istnieje"]:
            messagebox.showinfo(
                "Subiekt",
                f"{nr}\n\nBrak kartoteki w Subiekcie.\n\n"
                "Kartoteka powstanie automatycznie przy pierwszym zamówieniu "
                "tej pozycji (reguła „kartoteka na żądanie”).",
                parent=self)
            return
        lines = [
            f"Numer rysunku:  {nr}",
            f"Symbol w Subiekcie:  {r['symbol']!r}" +
            ("   ⚠ dopasowano luźno (spacje/wielkość liter)" if r["dop"] == "luzne" else ""),
            f"Nazwa:  {r['nazwa']}",
            "",
            f"Ostatnia cena zakupu:  " +
            (f"{r['cena']:.2f} PLN   (netto po rabacie, {r['data']})" if r["cena"] is not None
             else "brak danych o zakupach"),
            "",
            "Stany per magazyn:",
        ]
        for m in r["mags"]:
            lines.append(
                f"   {m['Magazyn']}:  dostępne {m['Dostepne']:g}"
                f"   zadysponowane {m['Zadysponowane']:g}"
                f"   rezerwacje {m['RezerwacjaIlosciowa']:g}/{m['RezerwacjaDostawowa']:g}")
        if not r["mags"]:
            lines.append("   (kartoteka bez ruchu magazynowego)")
        messagebox.showinfo("Subiekt — szczegóły", "\n".join(lines), parent=self)


def open_window(parent, project_id, only_drawings=None):
    """Punkt wejścia dla RM_BAZA."""
    if not project_id:
        messagebox.showwarning("Subiekt", "Najpierw wybierz projekt.", parent=parent)
        return None
    return SubiektStanyWindow(parent, project_id, only_drawings)


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 22
    root = tk.Tk()
    root.withdraw()
    w = open_window(root, pid)
    w.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
