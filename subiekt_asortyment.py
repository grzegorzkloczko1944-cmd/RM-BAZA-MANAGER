# -*- coding: utf-8 -*-
"""
Ręczne dodawanie asortymentu do Subiekta — jedno okno, wołane z każdego miejsca.

    import subiekt_asortyment
    subiekt_asortyment.okno_nowa_kartoteka(parent, symbol="DIN 912 M6x20",
                                           nazwa="Śruba", po_zapisie=callback)

`po_zapisie(dict)` dostaje {symbol, nazwa, rodzaj, jm, status} po udanym
założeniu (albo gdy kartoteka już istniała — wtedy status „istnieje").
Dzięki temu okno, które je wywołało (ZD, projekt, przegląd), może od razu
dołożyć pozycję do swojej listy.

Po co wspólny mechanizm zamiast osobnego formularza w każdym oknie: pozycji
spoza BOM-u (śruby, materiał pomocniczy, usługa transportu) dorzuca się z
różnych miejsc, a kartoteka musi wyglądać tak samo niezależnie od tego, skąd
powstała — ten sam szablon Subiekta, ten sam limit symbolu, ta sama walidacja.
"""

import json
import os
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from subiekt_stany import _find_exe, blad_mostu, wysrodkuj, CONFIG_PATH

TIMEOUT_S = 180

# Ten sam limit co przy symbolach z nazwy w subiekt_projekt — jednolita
# długość kodów kreskowych (numery rysunku mają 11-13 znaków).
MAX_SYMBOL = 13

RODZAJE = [("towar", "Towar (materiał, część)"),
           ("usluga", "Usługa (robocizna, transport)"),
           ("komplet", "Komplet (złożenie ze składników)")]
JEDNOSTKI = ["szt", "kpl", "m", "mb", "kg", "l", "op", "rbg"]


def zaloz_kartoteke(symbol, nazwa, rodzaj="towar", jm="szt", cena=None, opis="",
                    zapisz=False, timeout=TIMEOUT_S):
    """{status, szczegoly, symbol} — status: istnieje | do-zalozenia | zalozona | blad."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")

    tmpdir = tempfile.mkdtemp(prefix="subiekt_kart_")
    plan = os.path.join(tmpdir, "k.json")
    out = os.path.join(tmpdir, "w.json")
    with open(plan, "w", encoding="utf-8") as f:
        json.dump({"symbol": symbol, "nazwa": nazwa, "rodzaj": rodzaj, "jm": jm,
                   "cena": cena, "opis": opis}, f, ensure_ascii=False)

    cmd = [exe, "kartoteka", f"--plan={plan}", f"--out={out}"]
    if zapisz:
        cmd.append("--zapisz")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=flags)
    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(blad_mostu(exe, "kartoteka", proc, out))
    with open(out, encoding="utf-8") as f:
        return json.load(f)


def okno_nowa_kartoteka(parent, symbol="", nazwa="", rodzaj="towar", po_zapisie=None):
    """Formularz nowej kartoteki. Zwraca okno (Toplevel)."""
    dlg = tk.Toplevel(parent)
    dlg.title("Nowa kartoteka w Subiekcie")
    dlg.transient(parent)
    dlg.grab_set()

    tk.Label(dlg, text="➕ Dodaj asortyment do Subiekta", bg="#34495e", fg="white",
             font=("Arial", 10, "bold"), anchor="w", padx=12, pady=8).pack(fill=tk.X)

    body = tk.Frame(dlg, padx=14, pady=10)
    body.pack(fill=tk.BOTH, expand=True)
    body.columnconfigure(1, weight=1)

    def wiersz(r, etykieta):
        tk.Label(body, text=etykieta, font=("Arial", 9), anchor="e").grid(
            row=r, column=0, sticky="e", padx=(0, 8), pady=4)

    wiersz(0, "Symbol:")
    var_symbol = tk.StringVar(value=symbol)
    # Pole + przycisk generowania w jednej ramce, żeby przycisk stał TAM,
    # gdzie działa (a nie w rzędzie akcji na dole razem z „Załóż").
    ramka_sym = tk.Frame(body)
    ramka_sym.grid(row=0, column=1, sticky="ew", pady=4)
    ramka_sym.columnconfigure(0, weight=1)
    ent_symbol = tk.Entry(ramka_sym, textvariable=var_symbol, font=("Arial", 10))
    ent_symbol.grid(row=0, column=0, sticky="ew")
    lbl_dl = tk.Label(body, text="", font=("Arial", 8), fg="#7f8c8d", anchor="w")
    lbl_dl.grid(row=1, column=1, sticky="w")

    wiersz(2, "Nazwa:")
    var_nazwa = tk.StringVar(value=nazwa)
    tk.Entry(body, textvariable=var_nazwa, font=("Arial", 10)).grid(
        row=2, column=1, sticky="ew", pady=4)

    def generuj_symbol():
        """Symbol z nazwy — TĄ SAMĄ regułą, którą zakłada kartoteki
        subiekt_projekt (symbol_z_nazwy / rozroznij_symbol).

        Oba miejsca MUSZĄ generować identyczny symbol: kartoteka założona
        tutaj ręcznie i ta sama pozycja idąca automatem z projektu inaczej
        rozjadą się w Subiekcie na dwie różne kartoteki.

        Przy kolizji z symbolem już istniejącym w Subiekcie schodzimy do
        rozroznij_symbol, który zostawia wyróżniki z cyframi (DN40, M6,
        L2525) — to one odróżniają warianty tej samej rzeczy.
        """
        n = (var_nazwa.get() or "").strip()
        if not n:
            messagebox.showinfo("Generuj symbol",
                                "Najpierw wpisz nazwę — symbol powstaje z niej.",
                                parent=dlg)
            return
        try:
            from subiekt_projekt import symbol_z_nazwy, rozroznij_symbol
        except Exception as e:
            messagebox.showerror("Generuj symbol",
                                 f"Brak reguły generowania symbolu:\n{e}", parent=dlg)
            return

        kandydat = symbol_z_nazwy(n)
        # Symbole zajęte w Subiekcie — z cache katalogu, żeby nie czekać na
        # most przy każdym kliknięciu. Gdy cache nie ma, generujemy bez
        # sprawdzania kolizji (przycisk „Sprawdź" i tak je wyłapie).
        zajete = set()
        try:
            from subiekt_scalanie import wczytaj_katalog_subiekta
            zajete = {str(k.get("symbol") or "").strip().upper()
                      for k in (wczytaj_katalog_subiekta(tylko_cache=True) or [])}
        except Exception:
            pass
        if kandydat.upper() in zajete:
            kandydat = rozroznij_symbol(n, zajete)

        var_symbol.set(kandydat)
        status.config(
            text=f"Symbol z nazwy: {kandydat}"
                 + ("   (nazwa zajęta — użyto wyróżników)" if zajete and
                    symbol_z_nazwy(n).upper() in zajete else ""),
            fg="#2c3e50")

    tk.Button(ramka_sym, text="⚙ Generuj", command=generuj_symbol,
              font=("Arial", 8), padx=8, pady=1).grid(row=0, column=1, padx=(6, 0))

    wiersz(3, "Rodzaj:")
    var_rodzaj = tk.StringVar(value=next((o for k, o in RODZAJE if k == rodzaj), RODZAJE[0][1]))
    ttk.Combobox(body, textvariable=var_rodzaj, values=[o for _, o in RODZAJE],
                 state="readonly", font=("Arial", 9)).grid(row=3, column=1, sticky="ew", pady=4)

    wiersz(4, "Jednostka:")
    var_jm = tk.StringVar(value="szt")
    ttk.Combobox(body, textvariable=var_jm, values=JEDNOSTKI,
                 font=("Arial", 9), width=10).grid(row=4, column=1, sticky="w", pady=4)

    wiersz(5, "Cena ewid. (opcjonalnie):")
    var_cena = tk.StringVar()
    tk.Entry(body, textvariable=var_cena, font=("Arial", 10), width=12).grid(
        row=5, column=1, sticky="w", pady=4)

    wiersz(6, "Opis (opcjonalnie):")
    var_opis = tk.StringVar()
    tk.Entry(body, textvariable=var_opis, font=("Arial", 10)).grid(
        row=6, column=1, sticky="ew", pady=4)

    status = tk.Label(dlg, text="", font=("Arial", 8), fg="#7f8c8d", anchor="w", padx=14)
    status.pack(fill=tk.X)

    def licznik(*_):
        n = len(var_symbol.get().strip())
        if n > MAX_SYMBOL:
            lbl_dl.config(text=f"{n} znaków — za długi (max {MAX_SYMBOL}, jak numer rysunku; "
                               "dłuższy da kod kreskowy nie do wydruku)", fg="#c0392b")
        else:
            lbl_dl.config(text=f"{n}/{MAX_SYMBOL} znaków", fg="#7f8c8d")
    var_symbol.trace_add("write", licznik)
    licznik()

    def dane():
        s = var_symbol.get().strip()
        if not s:
            messagebox.showwarning("Kartoteka", "Podaj symbol.", parent=dlg)
            return None
        if len(s) > MAX_SYMBOL:
            messagebox.showwarning("Kartoteka",
                                   f"Symbol ma {len(s)} znaków — max {MAX_SYMBOL}.\n\n"
                                   "Pełną nazwę wpisz w pole Nazwa, symbol skróć.", parent=dlg)
            return None
        rodz = next((k for k, o in RODZAJE if o == var_rodzaj.get()), "towar")
        cena = None
        if var_cena.get().strip():
            try:
                cena = float(var_cena.get().replace(",", "."))
            except ValueError:
                messagebox.showwarning("Kartoteka", "Cena musi być liczbą.", parent=dlg)
                return None
        return dict(symbol=s, nazwa=var_nazwa.get().strip() or s, rodzaj=rodz,
                    jm=var_jm.get().strip() or "szt", cena=cena, opis=var_opis.get().strip())

    def w_tle(fn, gotowe):
        def run():
            try:
                w = fn()
                dlg.after(0, lambda: gotowe(w, None))
            except Exception as e:
                err = str(e)
                dlg.after(0, lambda: gotowe(None, err))
        threading.Thread(target=run, daemon=True).start()

    def sprawdz():
        d = dane()
        if not d:
            return
        status.config(text="Sprawdzam w Subiekcie…")
        def gotowe(w, err):
            if err:
                status.config(text="Błąd."); messagebox.showerror("Kartoteka", err, parent=dlg); return
            if w["status"] == "istnieje":
                status.config(text=f"⚠ {w['szczegoly']}", fg="#e67e22")
            else:
                status.config(text=f"✓ symbol wolny — {w['szczegoly']}", fg="#27ae60")
        w_tle(lambda: zaloz_kartoteke(**d, zapisz=False), gotowe)

    def zapisz():
        d = dane()
        if not d:
            return
        if not messagebox.askyesno(
                "Zapis do Subiekta",
                f"Baza PRODUKCYJNA.\n\nZałożyć kartotekę:\n  {d['symbol']}  —  {d['nazwa']}\n"
                f"  {d['rodzaj']}, {d['jm']}\n\nKartoteki nie da się łatwo usunąć.",
                parent=dlg, icon="warning"):
            return
        btn_zapisz.config(state=tk.DISABLED)
        status.config(text="Zapisuję…")
        def gotowe(w, err):
            btn_zapisz.config(state=tk.NORMAL)
            if err:
                status.config(text="Błąd."); messagebox.showerror("Kartoteka", err, parent=dlg); return
            if w["status"] in ("zalozona", "istnieje"):
                if po_zapisie:
                    po_zapisie(dict(d, symbol=w.get("symbol") or d["symbol"], status=w["status"]))
                if w["status"] == "istnieje":
                    messagebox.showinfo("Kartoteka", f"Już istnieje:\n{w['szczegoly']}\n\nUżyto istniejącej.", parent=dlg)
                dlg.destroy()
            else:
                status.config(text="Błąd.", fg="#c0392b")
                messagebox.showerror("Kartoteka", w.get("szczegoly") or "Nieznany błąd", parent=dlg)
        w_tle(lambda: zaloz_kartoteke(**d, zapisz=True), gotowe)

    box = tk.Frame(dlg)
    box.pack(pady=(4, 12))
    tk.Button(box, text="🔍 Sprawdź", command=sprawdz, font=("Arial", 9),
              padx=12, pady=3).pack(side=tk.LEFT, padx=4)
    btn_zapisz = tk.Button(box, text="💾 Załóż w Subiekcie", command=zapisz, bg="#e67e22",
                           fg="white", font=("Arial", 9, "bold"), padx=14, pady=3)
    btn_zapisz.pack(side=tk.LEFT, padx=4)
    tk.Button(box, text="Anuluj", command=dlg.destroy, font=("Arial", 9),
              padx=12, pady=3).pack(side=tk.LEFT, padx=4)

    ent_symbol.focus_set()
    wysrodkuj(dlg, parent, 560, 380)
    return dlg
