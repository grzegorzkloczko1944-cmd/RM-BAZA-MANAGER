# -*- coding: utf-8 -*-
"""
Założenie projektu RM_BAZA w Subiekcie nexo PRO: kartoteki, komplety i ZK.

    import subiekt_projekt
    subiekt_projekt.open_window(parent, project_id=22, project_name="2222 Ceramizator")

Co robi (SUBIEKT_PROJEKTY_WYDANIA.md, sekcje 3 i 5):

  * czyta BOM projektu i klasyfikację X / XX / Z / ZZ (kolumna class_effective),
  * z arkusza „DRZEWKO TEKST" odtwarza, co wchodzi w skład czego,
  * pokazuje drzewo z zaznaczeniem, co powstanie w Subiekcie,
  * po potwierdzeniu zakłada kartoteki, komplety (Z, potem ZZ) i ZK projektu.

Reguła typów — Z i ZZ to komplety, X i XX to zwykłe kartoteki:

    X, XX  → kartoteka-towar (liść drzewa, nie ma składników)
    Z      → komplet ze składników X/XX
    ZZ     → komplet ze składników Z  (komplet w komplecie)

UWAGA: to jedyny moduł RM_BAZA, który ZAPISUJE do Subiekta. Zapis idzie na
bazę produkcyjną, więc: zawsze najpierw suchy przebieg, potwierdzenie z
podsumowaniem, i log co powstało (do ewentualnego cofnięcia w Subiekcie).
"""

import json
import os
import subprocess
import sqlite3
import sys
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

import subiekt_mapowania
from subiekt_stany import _find_exe, CONFIG_PATH, PROJECTS_DIR, looks_like_drawing_no

TIMEOUT_S = 600          # zapis bywa wolniejszy od odczytu — kartoteki idą pojedynczo
LOG_DIR = r"C:\RMPAK_CLIENT\subiekt_logi"

KOMPLETY = ("Z", "ZZ")   # tylko te typy zakładają komplet
LISCIE = ("X", "XX")     # zwykłe kartoteki


# ── Dane projektu ───────────────────────────────────────────────────────────
def read_project_items(project_id):
    """[{nr, nazwa, qty, typ}] — pozycje BOM z klasyfikacją X/XX/Z/ZZ.

    Kolejność kolumn (work > norm > src, *_over pierwsze) jest ta sama co w
    subiekt_stany.read_project_drawings, żeby oba okna widziały to samo.
    """
    path = os.path.join(PROJECTS_DIR, f"project_{project_id}.sqlite")
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info('items')")}
        # UWAGA: kolumny *_over (name_over, order_qty_over…) to FLAGI nadpisania
        # (INTEGER 0/1), NIE wartości — wzięte tutaj dawały nazwę „0” i ilość 0
        # na ZK. Kolejność jak w reszcie RM_BAZA: COALESCE(order_qty, work_qty, src_qty).
        name_cols = [c for c in ("work_name", "src_name") if c in cols]
        qty_cols = [c for c in ("order_qty", "work_qty", "src_qty") if c in cols]
        cls_cols = [c for c in ("class_manual", "class_effective", "class_auto") if c in cols]
        sel = ["work_drawing_no", "norm_drawing_no", "src_drawing_no"] + name_cols + qty_cols + cls_cols
        # Ukryte pozycje (przycisk „Ukryj zaznaczone" w arkuszu) nie mają
        # trafiać do Subiekta — COALESCE bo starsze wiersze mogą mieć NULL
        # zamiast 0 (ten sam wzorzec co database_manager.get_project_items).
        where = " WHERE COALESCE(is_hidden, 0) = 0" if "is_hidden" in cols else ""
        rows = con.execute(f"SELECT {', '.join(sel)} FROM items{where}").fetchall()
    finally:
        con.close()

    n0 = 3
    q0 = n0 + len(name_cols)
    c0 = q0 + len(qty_cols)

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
        typ = first(r[c0:])
        out.append({
            "nr": nr,
            "nazwa": str(first(r[n0:q0]) or "").strip(),
            "qty": first(r[q0:c0]),
            "typ": str(typ).strip().upper() if typ else "UNKNOWN",
        })
    return out


def read_tree(project_name):
    """{rodzic: [(dziecko, ilosc_lokalna)]} z arkusza „DRZEWKO TEKST".

    Zwraca ({}, powod) jeśli drzewa nie da się wczytać — wtedy komplety nie
    powstaną (nie ma z czego zbudować składu), ale kartoteki i ZK owszem.
    """
    try:
        from pathlib import Path
        from import_bom import find_project_folder, find_out_files, find_assembly_tree_rows
    except Exception as e:
        return {}, f"brak import_bom: {e}"

    # Projekty (pliki *_OUT.xlsx) leżą na V:. Ścieżka z konfiguracji ma
    # pierwszeństwo, ale gdy wskazuje na nieistniejący katalog — a tak bywa,
    # bo konfig bywa przestawiony — schodzimy na V: zamiast zgłaszać błąd.
    kandydaci = []
    try:
        from RM_BAZA_v15_MAG_STATS_ORG import get_assembly_tree_root
        kandydaci.append(Path(get_assembly_tree_root()))
    except Exception:
        pass
    kandydaci.append(Path("V:/"))

    v_root = next((p for p in kandydaci if p.exists()), None)
    if v_root is None:
        return {}, f"katalog projektów niedostępny (próbowano: {', '.join(str(p) for p in kandydaci)})"

    folder = find_project_folder(v_root, project_name)
    if not folder:
        return {}, f"nie znaleziono folderu projektu „{project_name}” w {v_root}"

    kids = {}
    found = False
    for out_path in find_out_files(folder):
        rows = find_assembly_tree_rows(out_path)
        if not rows:
            continue
        found = True
        for row in rows:
            sciezka = row.get("sciezka") or []
            if len(sciezka) < 2:
                continue                      # korzeń nie ma rodzica
            parent = sciezka[-2].strip().upper()
            child = row["nr_rysunku"].strip()
            if not parent or not child:
                continue
            qty = row.get("ilosc_lokalna")
            try:
                qty = float(str(qty).replace(",", ".")) if qty not in (None, "") else 1.0
            except (TypeError, ValueError):
                qty = 1.0
            kids.setdefault(parent, [])
            if not any(c[0].upper() == child.upper() for c in kids[parent]):
                kids[parent].append((child, qty))

    if not found:
        return {}, "nie znaleziono arkusza „DRZEWKO TEKST” w plikach *_OUT.xlsx"
    return kids, None


def numer_projektu(project_name, project_id=None):
    """Numer projektu do Uwag na ZK — pierwszy człon nazwy.

    Firma już oznacza dokumenty w Subiekcie samym numerem (Uwagi: „2115",
    „2453", „2509" — patrz SUBIEKT_PROJEKTY_WYDANIA.md sekcja 2.1), więc
    filtrowanie F8 po Uwagach szuka numeru, nie nazwy.

        „2607 Platyn"        → „2607"
        „ZP179 ZTD"          → „ZP179"
        „2558 Olmaj Wciskarka" → „2558"

    Człon musi zawierać cyfrę — inaczej („Kabina testowa") nie jest numerem
    i wtedy lepszy jest project_id niż mylące pierwsze słowo.
    """
    czlon = (project_name or "").strip().split(" ")[0].strip() if project_name else ""
    if czlon and any(c.isdigit() for c in czlon):
        return czlon
    return str(project_id) if project_id is not None else (czlon or "")


def build_plan(project_id, project_name, podmiot, tytul):
    """Buduje plan dla mostu + dane do wyświetlenia. Zwraca (plan, items, ostrzezenie)."""
    items = read_project_items(project_id)
    items = [it for it in items if looks_like_drawing_no(it["nr"])]
    kids, warn = read_tree(project_name)

    by_nr = {it["nr"].upper(): it for it in items}
    pozycje = []
    for it in items:
        skladniki = []
        if it["typ"] in KOMPLETY:
            for child_nr, child_qty in kids.get(it["nr"].upper(), []):
                # Do składu kompletu bierzemy tylko to, co jest w BOM-ie —
                # inaczej wpisalibyśmy do Subiekta pozycję, której RM_BAZA nie zna.
                if child_nr.upper() in by_nr:
                    skladniki.append({"symbol": child_nr, "ilosc": child_qty})
        try:
            qty = float(str(it["qty"]).replace(",", ".")) if it["qty"] not in (None, "") else 1.0
        except (TypeError, ValueError):
            qty = 1.0
        pozycje.append({
            "symbol": it["nr"],
            "nazwa": it["nazwa"] or it["nr"],
            "typ": it["typ"],
            "ilosc": qty,
            "skladniki": skladniki,
        })

    # W Uwagach sam numer — tak firma oznacza dokumenty i tak po nich filtruje
    # (F8 / kolumna Uwagi). Pełna nazwa idzie w Tytule, gdzie jest czytelna.
    numer = numer_projektu(project_name, project_id)
    plan = {
        "projekt": numer,
        "tytul": tytul,
        "podmiot": podmiot,
        "uwagi": numer,
        "pozycje": pozycje,
    }
    return plan, items, warn


# ── Wywołanie mostu ─────────────────────────────────────────────────────────
def run_bridge(plan, zapisz=False, timeout=TIMEOUT_S):
    """Suchy przebieg (zapisz=False) albo realny zapis. Zwraca dict z JSON-a."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError(
            "Nie znaleziono NexoRecon.exe.\n\n"
            "Zbuduj most:\n  cd subiekt_sfera\\NexoRecon\n  dotnet build -c Release")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")

    tmpdir = tempfile.mkdtemp(prefix="subiekt_proj_")
    plan_path = os.path.join(tmpdir, "plan.json")
    out_path = os.path.join(tmpdir, "wynik.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)

    cmd = [exe, "projekt", f"--plan={plan_path}", f"--out={out_path}"]
    if zapisz:
        cmd.append("--zapisz")

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, creationflags=flags)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Subiekt nie odpowiedział w {timeout} s.")

    if proc.returncode != 0 or not os.path.isfile(out_path):
        msg = (proc.stdout or "").strip() or (proc.stderr or "").strip() or "nieznany błąd"
        raise RuntimeError(f"Most zwrócił błąd (kod {proc.returncode}):\n\n{msg}")

    with open(out_path, encoding="utf-8") as f:
        return json.load(f)


def zapisz_mapowania(wynik):
    """Zapamiętuje w globalnej tabeli, co Subiekt potwierdził.

    Dzięki temu następny projekt z tym samym numerem rysunku ma trafienie
    lokalnie, bez pytania Subiekta przez sieć (plan, „Zapamiętanie skojarzenia").
    """
    wpisy = []
    for k in (wynik or {}).get("kroki", []):
        if k.get("Rodzaj") != "kartoteka":
            continue
        symbol = (k.get("Symbol") or "").strip()
        if not symbol:
            continue
        if k.get("Status") == "istnieje":
            wpisy.append((symbol, symbol, subiekt_mapowania.SPOSOB_AUTO))
        elif k.get("Status") == "zalozona":
            wpisy.append((symbol, symbol, subiekt_mapowania.SPOSOB_ZALOZONA))
    try:
        return subiekt_mapowania.put_many(wpisy)
    except Exception:
        return 0          # brak dostępu do bazy mapowań nie może wywalić całego zapisu


def save_log(project_id, wynik):
    """Zapisuje co powstało — bez tego nie da się potem posprzątać w Subiekcie."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(LOG_DIR, f"projekt_{project_id}_{stamp}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(wynik, f, ensure_ascii=False, indent=1)
        return path
    except Exception:
        return None


# ── Okno ────────────────────────────────────────────────────────────────────
class SubiektProjektWindow(tk.Toplevel):
    COLS = [
        ("sel",    "✓",             30, "c"),
        ("nr",     "Nr rysunku",   150, "w"),
        ("typ",    "Typ",           55, "c"),
        ("qty",    "Ilość",         60, "e"),
        ("co",     "Co powstanie", 210, "w"),
        ("nazwa",  "Nazwa",        300, "w"),
    ]

    def __init__(self, parent, project_id, project_name=None):
        super().__init__(parent)
        self.project_id = project_id
        self.project_name = project_name or str(project_id)
        self.plan = None
        self.items = []
        self.dry = None
        # Symbole (UPPER) wybrane do założenia w Subiekcie. Pozycje, które już
        # mają kartotekę, nie są tu trzymane — nie ma czego zakładać.
        self.wybrane = set()

        self.title(f"Załóż projekt w Subiekcie — {self.project_name}")
        self.geometry("1080x680")
        self.transient(parent)

        self._build_ui()
        self.after(100, self._dry_run_async)

    def _build_ui(self):
        top = tk.Frame(self, bg="#34495e", height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🏗 Załóż projekt w Subiekcie (kartoteki + komplety + ZK)",
                 bg="#34495e", fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)

        self.btn_refresh = tk.Button(top, text="🔄 Przelicz", command=self._dry_run_async,
                                     bg="#3498db", fg="white", font=("Arial", 8),
                                     padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_refresh.pack(side=tk.RIGHT, padx=10, pady=8)

        # Parametry ZK — podmiot jest wymagany przez Subiekta (sekcja 4).
        par = tk.Frame(self, bg="#ecf0f1")
        par.pack(side=tk.TOP, fill=tk.X, padx=0, pady=0)
        tk.Label(par, text="Podmiot na ZK:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(12, 4), pady=6)
        self.var_podmiot = tk.StringVar(value="RMPAK")
        tk.Entry(par, textvariable=self.var_podmiot, width=28, font=("Arial", 9)).pack(side=tk.LEFT, pady=6)
        tk.Label(par, text="Tytuł ZK:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(16, 4), pady=6)
        # Tytuł: pełna nazwa projektu (z numerem na początku), bez słowa
        # „Projekt” — na liście dokumentów w Subiekcie od razu widać, o co
        # chodzi. Sam numer idzie osobno w Uwagi, bo po nich się filtruje.
        self.var_tytul = tk.StringVar(value=(self.project_name or str(self.project_id)).strip())
        tk.Entry(par, textvariable=self.var_tytul, width=38, font=("Arial", 9)).pack(side=tk.LEFT, pady=6)

        # Wybór, co zakładać w asortymencie Subiekta. Domyślnie NIE cały BOM —
        # zakładanie 198 kartotek jednym kliknięciem to zmiana reguły „kartoteka
        # na żądanie", a kartotek nie da się potem łatwo usunąć.
        sel = tk.Frame(self, bg="#f4ecf7")
        sel.pack(side=tk.TOP, fill=tk.X)
        tk.Label(sel, text="Zakładaj kartoteki dla:", bg="#f4ecf7",
                 font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(12, 6), pady=5)
        for etykieta, tryb, opis in (
            ("komplety + składniki", "komplety", "tylko Z/ZZ i to, co w nie wchodzi"),
            ("wszystko", "wszystko", "cały BOM"),
            ("nic", "nic", "tylko istniejące kartoteki"),
        ):
            tk.Button(sel, text=etykieta, command=lambda t=tryb: self._zaznacz_tryb(t),
                      bg="#8e44ad", fg="white", font=("Arial", 8), padx=8, pady=1,
                      relief=tk.RAISED, bd=1, cursor="hand2").pack(side=tk.LEFT, padx=3, pady=5)
        tk.Label(sel, text="   (klik w kolumnę ✓ przełącza pojedynczą pozycję)",
                 bg="#f4ecf7", fg="#7f8c8d", font=("Arial", 8)).pack(side=tk.LEFT, padx=6)

        self.summary = tk.Label(self, text="Wczytywanie…", bg="#ecf0f1", fg="#2c3e50",
                                font=("Arial", 9), anchor="w", padx=12, pady=6)
        self.summary.pack(side=tk.TOP, fill=tk.X)

        wrap = tk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 4))
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in self.COLS], show="tree headings")
        self.tree.heading("#0", text="Struktura")
        self.tree.column("#0", width=230, stretch=False)
        for key, label, width, anchor in self.COLS:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "nazwa"), minwidth=50)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Button-1>", self._toggle_pozycja, add="+")
        self.tree.tag_configure("komplet", background="#d4e6f1")   # Z / ZZ
        self.tree.tag_configure("istnieje", background="#d5f5e3")  # jest w Subiekcie
        self.tree.tag_configure("nowy",    background="#fdebd0")   # do założenia
        self.tree.tag_configure("blad",    background="#fadbd8")

        bottom = tk.Frame(self)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))
        self.btn_write = tk.Button(bottom, text="💾 Zapisz do Subiekta", command=self._write_async,
                                   bg="#e67e22", fg="white", font=("Arial", 9, "bold"),
                                   padx=14, pady=5, relief=tk.RAISED, bd=2, state=tk.DISABLED)
        self.btn_write.pack(side=tk.RIGHT)
        tk.Label(bottom, text="Podgląd nie zmienia niczego w Subiekcie. Zapis wymaga potwierdzenia.",
                 fg="#7f8c8d", font=("Arial", 8)).pack(side=tk.LEFT, pady=8)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    # ── suchy przebieg ─────────────────────────────────────────────────────
    def _dry_run_async(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.btn_write.config(state=tk.DISABLED)
        self.status.config(text="Czytam BOM i pytam Subiekta (nic nie zapisuję)…")
        threading.Thread(target=self._dry_run_worker, daemon=True).start()

    def _dry_run_worker(self):
        try:
            plan, items, warn = build_plan(
                self.project_id, self.project_name,
                self.var_podmiot.get().strip(), self.var_tytul.get().strip())
            if not plan["pozycje"]:
                self.after(0, lambda: self._dry_done(None, None, [], "Brak pozycji z numerem rysunku."))
                return
            wynik = run_bridge(plan, zapisz=False)
            # Suchy przebieg też jest okazją do zapamiętania trafień — kolejny
            # projekt z tymi numerami nie będzie musiał pytać Subiekta.
            zapisz_mapowania(wynik)
            self.after(0, lambda: self._dry_done(plan, wynik, items, warn))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._dry_done(None, None, [], err))

    def _dry_done(self, plan, wynik, items, warn):
        self.btn_refresh.config(state=tk.NORMAL)
        if plan is None:
            self.status.config(text="Błąd.")
            self.summary.config(text=(warn or "")[:200])
            if warn:
                messagebox.showerror("Subiekt", warn, parent=self)
            return

        self.plan, self.dry, self.items = plan, wynik, items
        self._fill_tree(plan, wynik)
        self.btn_write.config(state=tk.NORMAL)

        # Domyślnie „komplety + składniki", nie cały BOM: zakładanie wszystkich
        # kartotek naraz to zmiana reguły „kartoteka na żądanie", a kartotek nie
        # da się potem łatwo usunąć. Użytkownik może rozszerzyć jednym kliknięciem.
        self._zaznacz_tryb("komplety")

        pust = sum(1 for k in wynik.get("kroki", [])
                   if k["Rodzaj"] == "komplet" and k["Status"] == "pominiety-brak-skladnikow")
        note = f"   ⚠ {warn}" if warn else ""
        extra = f"   ⚠ {pust} kompletów bez składników w drzewie" if pust else ""
        self.status.config(text=f"Podgląd gotowy — w Subiekcie nic nie zmieniono.{extra}{note}")

    # ── wybór, co zakładać ─────────────────────────────────────────────────
    def _do_zalozenia(self):
        """Symbole (UPPER), które nie mają jeszcze kartoteki w Subiekcie."""
        if not self.dry:
            return set()
        return {k["Symbol"].strip().upper() for k in self.dry.get("kroki", [])
                if k["Rodzaj"] == "kartoteka" and k["Status"] == "do-zalozenia"}

    def _zaznacz_tryb(self, tryb):
        """Szybkie zaznaczenie wg trybu. Działa tylko na pozycjach bez kartoteki."""
        if not self.plan:
            return
        brakujace = self._do_zalozenia()

        if tryb == "nic":
            self.wybrane = set()
        elif tryb == "wszystko":
            self.wybrane = set(brakujace)
        else:   # komplety + ich składniki (rekurencyjnie, bo ZZ zawiera ZZ)
            by = {p["symbol"].strip().upper(): p for p in self.plan["pozycje"]}
            chciane = set()

            def dodaj(sym, sciezka=()):
                s = sym.strip().upper()
                if s in sciezka or s in chciane:
                    return
                chciane.add(s)
                p = by.get(s)
                if not p:
                    return
                for skl in p["skladniki"]:
                    dodaj(skl["symbol"], sciezka + (s,))

            for p in self.plan["pozycje"]:
                if p["typ"] in KOMPLETY and p["skladniki"]:
                    dodaj(p["symbol"])
            self.wybrane = chciane & brakujace

        self._odswiez_znaczniki()

    def _toggle_pozycja(self, event):
        """Klik w kolumnę ✓ przełącza pojedynczą pozycję."""
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":      # kolumna „sel"
            return
        item = self.tree.identify_row(event.y)
        if not item:
            return
        sym = (self.tree.set(item, "nr") or "").strip().upper()
        if not sym or sym not in self._do_zalozenia():
            return                                  # już ma kartotekę — nie ma czego zakładać
        self.wybrane.symmetric_difference_update({sym})
        self._odswiez_znaczniki()

    def _odswiez_znaczniki(self):
        """Przerysowuje kolumnę ✓ i podsumowanie bez przebudowy drzewa."""
        brakujace = self._do_zalozenia()

        def przejdz(node):
            for i in self.tree.get_children(node):
                sym = (self.tree.set(i, "nr") or "").strip().upper()
                if sym:
                    if sym not in brakujace:
                        self.tree.set(i, "sel", "—")     # istnieje, nic nie robimy
                    else:
                        self.tree.set(i, "sel", "✓" if sym in self.wybrane else "☐")
                przejdz(i)

        przejdz("")
        self._przelicz_podsumowanie()

    def _przelicz_podsumowanie(self):
        """Podsumowanie liczy się z aktualnego wyboru, nie z suchego przebiegu."""
        if not self.plan or not self.dry:
            return
        kroki = self.dry.get("kroki", [])
        jest = sum(1 for k in kroki if k["Rodzaj"] == "kartoteka" and k["Status"] == "istnieje")
        brakujace = self._do_zalozenia()
        do_zal = len(self.wybrane)
        pominiete = len(brakujace) - do_zal

        # Komplet powstanie tylko wtedy, gdy on sam i wszystkie jego składniki
        # będą miały kartotekę (istniejącą albo zakładaną teraz).
        dostepne = (set(p["symbol"].strip().upper() for p in self.plan["pozycje"]) - brakujace) | self.wybrane
        pelne = niepelne = 0
        for p in self.plan["pozycje"]:
            if p["typ"] not in KOMPLETY or not p["skladniki"]:
                continue
            if p["symbol"].strip().upper() not in dostepne:
                niepelne += 1
            elif all(s["symbol"].strip().upper() in dostepne for s in p["skladniki"]):
                pelne += 1
            else:
                niepelne += 1

        self.summary.config(text=(
            f"Pozycji: {len(self.plan['pozycje'])}    "
            f"kartoteki — jest: {jest}, do założenia: {do_zal}"
            + (f" (pomijasz {pominiete})" if pominiete else "")
            + f"    komplety: {pelne} pełnych"
            + (f", {niepelne} niepełnych ⚠" if niepelne else "")
        ))

    def _fill_tree(self, plan, wynik):
        self.tree.delete(*self.tree.get_children())
        status = {}
        for k in wynik.get("kroki", []):
            status.setdefault(k["Rodzaj"], {})[k["Symbol"].upper()] = k

        by_symbol = {p["symbol"].upper(): p for p in plan["pozycje"]}
        dzieci = set()
        for p in plan["pozycje"]:
            for s in p["skladniki"]:
                dzieci.add(s["symbol"].upper())

        def opis(p):
            kart = status.get("kartoteka", {}).get(p["symbol"].upper())
            kom = status.get("komplet", {}).get(p["symbol"].upper())
            czesci = []
            if kart:
                czesci.append("kartoteka: " + ("jest" if kart["Status"] == "istnieje" else "NOWA"))
            if kom:
                czesci.append("komplet: " + kom["Status"].replace("do-utworzenia", "utworzy"))
            return "   ".join(czesci) or "—"

        def tag(p):
            kart = status.get("kartoteka", {}).get(p["symbol"].upper())
            if p["typ"] in KOMPLETY:
                return "komplet"
            if kart and kart["Status"] == "istnieje":
                return "istnieje"
            return "nowy"

        def wstaw(parent_id, p, glebokosc=0, sciezka=()):
            node = self.tree.insert(
                parent_id, "end", text=p["symbol"],
                values=("", p["symbol"], p["typ"], f"{p['ilosc']:g}", opis(p), p["nazwa"]),
                open=(glebokosc < 1), tags=(tag(p),))
            # Drzewa bywają głębokie (realnie widziane 4 poziomy, firma mówi
            # o nawet 6), więc nie ucinamy po stałej głębokości — pilnujemy
            # tylko cyklu (ten sam symbol na własnej ścieżce), który zawiesiłby
            # rekurencję. Subiekt ma na to własną walidację przy zapisie.
            klucz = p["symbol"].upper()
            if klucz in sciezka:
                return
            dalej = sciezka + (klucz,)
            for s in p["skladniki"]:
                child = by_symbol.get(s["symbol"].upper())
                if child:
                    wstaw(node, child, glebokosc + 1, dalej)

        # Korzenie: ZZ i Z, które same nie są niczyim składnikiem; potem reszta.
        korzenie = [p for p in plan["pozycje"]
                    if p["typ"] in KOMPLETY and p["symbol"].upper() not in dzieci]
        for p in sorted(korzenie, key=lambda x: (x["typ"] != "ZZ", x["symbol"])):
            wstaw("", p)

        luzne = [p for p in plan["pozycje"]
                 if p["symbol"].upper() not in dzieci and p not in korzenie]
        if luzne:
            grupa = self.tree.insert("", "end", text="Pozostałe pozycje",
                                     values=("", "", "", "", f"{len(luzne)} poz. bez złożenia", ""), open=False)
            for p in sorted(luzne, key=lambda x: x["symbol"]):
                wstaw(grupa, p)

    # ── zapis ──────────────────────────────────────────────────────────────
    def _plan_do_zapisu(self):
        """Plan ograniczony do wybranych pozycji.

        Do Subiekta idzie tylko to, co ma kartotekę (istniejącą) albo zostało
        zaznaczone do założenia. Pozycje pominięte znikają też ze składów
        kompletów i z ZK — inaczej most próbowałby dodać coś, czego nie ma.
        """
        brakujace = self._do_zalozenia()
        dostepne = {p["symbol"].strip().upper() for p in self.plan["pozycje"]}
        dostepne = (dostepne - brakujace) | self.wybrane

        pozycje = []
        for p in self.plan["pozycje"]:
            if p["symbol"].strip().upper() not in dostepne:
                continue
            q = dict(p)
            q["skladniki"] = [s for s in p["skladniki"]
                              if s["symbol"].strip().upper() in dostepne]
            pozycje.append(q)

        plan = dict(self.plan)
        plan["pozycje"] = pozycje
        plan["podmiot"] = self.var_podmiot.get().strip()
        plan["tytul"] = self.var_tytul.get().strip()
        return plan

    def _write_async(self):
        if not self.plan:
            return

        podmiot = self.var_podmiot.get().strip()
        if not podmiot:
            messagebox.showwarning("Subiekt", "Podaj podmiot na ZK.", parent=self)
            return

        plan = self._plan_do_zapisu()
        nowe = len(self.wybrane)
        kompl = sum(1 for p in plan["pozycje"] if p["typ"] in KOMPLETY and p["skladniki"])
        pominiete = len(self._do_zalozenia()) - nowe

        if not plan["pozycje"]:
            messagebox.showwarning(
                "Subiekt",
                "Nic nie zostało wybrane do zapisu.\n\n"
                "Żadna pozycja nie ma kartoteki i nic nie jest zaznaczone —\n"
                "ZK nie miałoby z czego powstać.",
                parent=self)
            return

        # Zapis idzie na bazę produkcyjną — potwierdzenie musi mówić wprost,
        # co powstanie i czego (kartotek) nie da się łatwo cofnąć.
        ok = messagebox.askyesno(
            "Zapis do Subiekta — potwierdzenie",
            f"Baza PRODUKCYJNA.\n\n"
            f"Powstanie:\n"
            f"  • kartoteki: {nowe}"
            + (f"   (pomijasz {pominiete} pozycji bez kartoteki)" if pominiete else "") + "\n"
            f"  • komplety (Z/ZZ): {kompl}\n"
            f"  • ZK „{self.var_tytul.get().strip()}” dla podmiotu „{podmiot}”\n"
            f"    — {len(plan['pozycje'])} pozycji, Uwagi: „{numer_projektu(self.project_name, self.project_id)}”\n\n"
            f"ZK można w Subiekcie usunąć. Kartotek i kompletów tak łatwo nie —\n"
            f"zostaną w kartotece asortymentu.\n\n"
            f"Zapisać?",
            parent=self, icon="warning")
        if not ok:
            return

        self.btn_write.config(state=tk.DISABLED)
        self.btn_refresh.config(state=tk.DISABLED)
        self.status.config(text="Zapisuję do Subiekta — nie zamykaj okna…")
        threading.Thread(target=self._write_worker, daemon=True).start()

    def _write_worker(self):
        try:
            wynik = run_bridge(self._plan_do_zapisu(), zapisz=True)
            self.after(0, lambda: self._write_done(wynik, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._write_done(None, err))

    def _write_done(self, wynik, error):
        self.btn_refresh.config(state=tk.NORMAL)
        if error:
            self.status.config(text="Zapis nieudany.")
            messagebox.showerror("Subiekt — zapis", error, parent=self)
            self.btn_write.config(state=tk.NORMAL)
            return

        kroki = wynik.get("kroki", [])
        zal = sum(1 for k in kroki if k["Status"] == "zalozona")
        kom = sum(1 for k in kroki if k["Rodzaj"] == "komplet" and k["Status"].startswith("utworzony"))
        bledy = [k for k in kroki if k["Status"] == "blad"]
        zk = wynik.get("zk")
        log = save_log(self.project_id, wynik)
        zmap = zapisz_mapowania(wynik)

        lines = [
            f"Kartoteki założone: {zal}",
            f"Komplety utworzone: {kom}",
            f"ZK: {zk or '—'}",
            f"Mapowań zapamiętanych: {zmap}",
        ]
        if bledy:
            lines += ["", f"Błędy ({len(bledy)}):"]
            lines += [f"  • {b['Rodzaj']} {b['Symbol']}: {b.get('Szczegoly') or ''}" for b in bledy[:12]]
            if len(bledy) > 12:
                lines.append(f"  … i {len(bledy) - 12} więcej (szczegóły w logu)")
        if log:
            lines += ["", f"Log: {log}"]

        self.status.config(text=f"Zapisano. ZK: {zk or '—'}" + (f"   ⚠ błędów: {len(bledy)}" if bledy else ""))
        (messagebox.showwarning if bledy else messagebox.showinfo)(
            "Subiekt — zapis zakończony", "\n".join(lines), parent=self)
        self._dry_run_async()      # odśwież — pokaże już założone kartoteki jako istniejące


def open_window(parent, project_id, project_name=None):
    """Punkt wejścia dla RM_BAZA."""
    if not project_id:
        messagebox.showwarning("Subiekt", "Najpierw wybierz projekt.", parent=parent)
        return None
    return SubiektProjektWindow(parent, project_id, project_name)


if __name__ == "__main__":
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 22
    pname = sys.argv[2] if len(sys.argv) > 2 else None
    root = tk.Tk()
    root.withdraw()
    w = open_window(root, pid, pname)
    w.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
