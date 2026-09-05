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
# projects_dir zalezy od maszyny (firma: Y:\RM_BAZA\projects, dom/M-OLD:
# C:/RMPAK_CLIENT/RM_BAZY/RM_BAZA/projects) - RM_BAZA juz to rozwiazuje
# poprawnie na kazdej maszynie przez sync_config.json (patrz np.
# RM_BAZA_v15_MAG_STATS_ORG.py, db_manager.projects_dir). Ten modul
# czytal wlasna, twarda sciezke Y: niezalezna od tego configu, wiec na
# M-OLD (gdzie ten sam zasob siedzi pod V:) pekal - "Y:\RM_BAZA\projects\
# project_71.sqlite" (znalezione 2026-09-03). Czytamy teraz ten sam
# sync_config.json co reszta apki, zamiast duplikowac logike.
_SYNC_CONFIG_PATH = r"C:\RMPAK_CLIENT\sync_config.json"
_PROJECTS_DIR_FALLBACK = r"Y:\RM_BAZA\projects"


def _projects_dir():
    try:
        with open(_SYNC_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg["paths"]["projects_dir"]
    except Exception:
        return _PROJECTS_DIR_FALLBACK


PROJECTS_DIR = _projects_dir()

TIMEOUT_S = 180


def _find_exe():
    for p in EXE_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


# Szerokości kolumn okien Subiekta — jeden plik, klucz per okno.
# Osobno od config.json arkusza głównego, żeby nie mieszać do cudzego pliku.
SZEROKOSCI_PLIK = r"C:\RMPAK_CLIENT\subiekt_kolumny.json"


def wczytaj_szerokosci(klucz):
    """[int] albo None — zapamiętane szerokości kolumn dla danego okna."""
    try:
        if not os.path.isfile(SZEROKOSCI_PLIK):
            return None
        with open(SZEROKOSCI_PLIK, encoding="utf-8") as f:
            return (json.load(f) or {}).get(klucz)
    except Exception:
        return None          # szerokości nie są warte psucia startu okna


def zapisz_szerokosci(klucz, szerokosci):
    try:
        dane = {}
        if os.path.isfile(SZEROKOSCI_PLIK):
            try:
                with open(SZEROKOSCI_PLIK, encoding="utf-8") as f:
                    dane = json.load(f) or {}
            except Exception:
                dane = {}
        dane[klucz] = [int(x) for x in szerokosci]
        os.makedirs(os.path.dirname(SZEROKOSCI_PLIK), exist_ok=True)
        with open(SZEROKOSCI_PLIK, "w", encoding="utf-8") as f:
            json.dump(dane, f, indent=1)
    except Exception:
        pass


def podepnij_szerokosci(okno, sheet, klucz, domyslne=None):
    """Wczytuje zapamiętane szerokości i pilnuje ich zapisu przy zmianie.

    Wzorzec z arkusza głównego RM_BAZA (_on_column_resized): tksheet 7.5.19
    nie ma zdarzenia „kolumna zmieniła szerokość", więc łapiemy puszczenie
    myszy na PASKU NAGŁÓWKÓW — tam kończy się przeciąganie. after_idle, bo
    w momencie ButtonRelease tksheet nie zapisał jeszcze nowej szerokości;
    porównanie z ostatnim stanem, żeby zwykłe klikanie nie waliło w dysk.
    """
    zapisane = wczytaj_szerokosci(klucz)

    # ⚠️ Zapamiętane szerokości pasują TYLKO do tego układu kolumn, w którym
    # powstały. Po dołożeniu kolumny stara lista nakładała się z przesunięciem:
    # nowa kolumna dostawała szerokość sąsiada, a ostatnia wypadała poza ekran
    # — wyglądało to, jakby kolumny w ogóle nie było (zgłoszone 05.09.2026,
    # brak kolumny „PDF"). Przy niezgodnej długości bierzemy domyślne.
    try:
        ile_kolumn = len(sheet.headers())
    except Exception:
        ile_kolumn = len(domyslne or zapisane or [])
    if zapisane and ile_kolumn and len(zapisane) != ile_kolumn:
        print(f"ℹ️  Układ kolumn „{klucz}” zmienił się "
              f"({len(zapisane)} → {ile_kolumn}) — szerokości ustawiam domyślne.")
        zapisane = None

    if zapisane:
        for i, w in enumerate(zapisane):
            try:
                sheet.column_width(column=i, width=int(w))
            except Exception:
                break        # węższa tabela niż zapis — reszta zostaje domyślna
    elif domyslne:
        for i, w in enumerate(domyslne):
            try:
                sheet.column_width(column=i, width=int(w))
            except Exception:
                break

    ostatnie = {"v": None}

    def sprawdz():
        try:
            obecne = list(sheet.get_column_widths())
            if obecne and obecne != ostatnie["v"]:
                ostatnie["v"] = obecne
                zapisz_szerokosci(klucz, obecne)
        except Exception:
            pass

    def po_puszczeniu(_event=None):
        try:
            okno.after_idle(sprawdz)
        except Exception:
            pass

    try:
        sheet.CH.bind("<ButtonRelease-1>", po_puszczeniu, add="+")
    except Exception:
        pass                 # starsze tksheet — szerokości po prostu się nie zapiszą


def jedna_linia(s):
    """Skleja tekst złamany na kilka linii w jedną.

    BOM-y importowane z Excela mają w komórkach twarde entery — nazwa
    „CHEM UPE-\\n050" to JEDNA nazwa zawinięta w arkuszu. Bez sklejenia
    wiersz w tabeli rozjeżdża się na dwie linie, a do Subiekta poszedłby
    symbol ze znakiem nowej linii w środku (zgłoszone 04.09.2026).
    Łącznik na końcu linii („CHEM UPE-\\n050") sklejamy bez spacji.
    """
    s = str(s or "").replace("\r\n", "\n").replace("\r", "\n")
    czesci = [c.strip() for c in s.split("\n") if c.strip()]
    if not czesci:
        return ""
    out = czesci[0]
    for c in czesci[1:]:
        out += c if out.endswith("-") else " " + c
    return " ".join(out.split())          # zwielokrotnione spacje i taby


def wysrodkuj(okno, rodzic, szerokosc=None, wysokosc=None):
    """Ustawia okno na środku okna rodzica (nie ekranu).

    Bez tego Tk stawia Toplevel w lewym górnym rogu ekranu — na dwóch
    monitorach okno potrafi wyskoczyć zupełnie gdzie indziej niż aplikacja.
    Wołać PO zbudowaniu zawartości, żeby okno znało swój rozmiar.
    """
    try:
        okno.update_idletasks()
        w = szerokosc or okno.winfo_width() or okno.winfo_reqwidth()
        h = wysokosc or okno.winfo_height() or okno.winfo_reqheight()

        # Rodzic zmaksymalizowany albo jeszcze nierozłożony — bierzemy ekran.
        rw, rh = rodzic.winfo_width(), rodzic.winfo_height()
        if rw > 1 and rh > 1:
            x = rodzic.winfo_rootx() + (rw - w) // 2
            y = rodzic.winfo_rooty() + (rh - h) // 2
        else:
            x = (okno.winfo_screenwidth() - w) // 2
            y = (okno.winfo_screenheight() - h) // 2

        # Nie wypychamy okna poza ekran (ujemne współrzędne = tytuł poza kadrem).
        x = max(0, min(x, okno.winfo_screenwidth() - w))
        y = max(0, min(y, okno.winfo_screenheight() - h))
        okno.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass          # pozycjonowanie nie może wywalić okna


def most_starszy_niz_zrodla(exe):
    """(True, opis) jeśli .exe jest starszy niż pliki .cs mostu.

    `bin/` jest w .gitignore, więc po `git pull` przychodzą źródła BEZ
    binarki. Python woła wtedy tryb, którego stary .exe nie zna — a ten
    ignoruje nieznany argument i uruchamia domyślne rozpoznanie: kończy się
    kodem 0, nie tworzy pliku --out, i wypluwa listę magazynów i kartotek.
    Wygląda to jak problem z połączeniem, choć połączenie działa (zdarzyło
    się realnie 04.09.2026 po pullu z trybem „katalog").
    """
    try:
        if not exe or not os.path.isfile(exe):
            return False, ""
        t_exe = os.path.getmtime(exe)
        src_dir = os.path.join(_HERE, "subiekt_sfera", "NexoRecon")
        nowsze = []
        for nazwa in os.listdir(src_dir):
            if not nazwa.lower().endswith(".cs"):
                continue
            p = os.path.join(src_dir, nazwa)
            if os.path.getmtime(p) > t_exe + 1:      # 1 s luzu na zaokrąglenia
                nowsze.append(nazwa)
        if not nowsze:
            return False, ""
        return True, ", ".join(sorted(nowsze))
    except Exception:
        return False, ""                              # diagnostyka nie może wywalić wywołania


def blad_mostu(exe, tryb, proc, out_path):
    """Czytelny komunikat błędu wywołania mostu.

    Najpierw sprawdza najczęstszą przyczynę (nieaktualny .exe po pullu),
    bo surowy wypis rozpoznania myli — wygląda jak błąd Subiekta.
    """
    stary, pliki = most_starszy_niz_zrodla(exe)
    if stary and proc.returncode == 0 and not os.path.isfile(out_path):
        return (
            "NIEAKTUALNY MOST — trzeba go przebudować.\n\n"
            f"NexoRecon.exe nie zna trybu „{tryb}”: jest starszy niż źródła\n"
            f"({pliki}). Katalog bin/ nie idzie przez gita, więc po „git pull”\n"
            "binarkę trzeba zbudować u siebie:\n\n"
            "    cd subiekt_sfera\\NexoRecon\n"
            "    dotnet build -c Release -nowarn:MSB3277\n\n"
            "Połączenie z Subiektem jest sprawne — problem jest tylko w wersji mostu."
        )
    msg = (proc.stdout or "").strip() or (proc.stderr or "").strip() or "nieznany błąd"
    return f"Most zwrócił błąd (kod {proc.returncode}):\n\n{msg}"


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
        # Kolumny *_over to FLAGI nadpisania (INTEGER 0/1), nie wartości —
        # brane tutaj dawały nazwę „0” i zerową „Ilość BOM”.
        name_cols = [c for c in ("work_name", "src_name") if c in cols]
        qty_cols = [c for c in ("order_qty", "work_qty", "src_qty") if c in cols]
        sel = ["work_drawing_no", "norm_drawing_no", "src_drawing_no"] + name_cols + qty_cols
        # Ukryte pozycje (przycisk „Ukryj zaznaczone" w arkuszu) nie mają
        # trafiać do Subiekta — COALESCE bo starsze wiersze mogą mieć NULL
        # zamiast 0 (ten sam wzorzec co database_manager.get_project_items).
        where = " WHERE COALESCE(is_hidden, 0) = 0" if "is_hidden" in cols else ""
        rows = con.execute(f"SELECT {', '.join(sel)} FROM items{where}").fetchall()
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
        raise RuntimeError(blad_mostu(exe, "stan", proc, out))

    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    return {p["Pytany"]: p for p in data.get("pozycje", [])}


# ── Okno ────────────────────────────────────────────────────────────────────
class SubiektStanyWindow(tk.Toplevel):
    COLS = [
        ("nr",     "Nr rysunku",     140, "w"),
        ("bom",    "Ilość BOM",       75, "e"),
        ("stan",   "Stan Subiekt",    95, "e"),
        ("brak",   "Do zamówienia",   95, "e"),
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

        tk.Label(top, text="📦 Stany pozycji projektu w Subiekcie",
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
            # Brakuje = ile trzeba dokupic. Bez kartoteki nie ma nic na stanie,
            # wiec brakuje calej ilosci z BOM (wczesniej zostawialo pusto, co
            # wygladalo, jakby modul nic nie policzyl).
            missing = ""
            if need_f is not None:
                brak = need_f - (r["stan"] if r["istnieje"] else 0)
                if brak > 0:
                    missing = f"{brak:g}"

            self.tree.insert("", "end", values=(
                r["nr"],
                "" if need in (None, "") else f"{need:g}" if isinstance(need, (int, float)) else need,
                f"{r['stan']:g}" if r["istnieje"] else "brak kart.",
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
