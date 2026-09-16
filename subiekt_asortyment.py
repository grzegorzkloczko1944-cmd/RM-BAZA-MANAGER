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
from tkinter import ttk
from tkinter import ttk, messagebox

from subiekt_stany import _find_exe, blad_mostu, wysrodkuj, CONFIG_PATH

TIMEOUT_S = 180

# Ten sam limit co przy symbolach z nazwy w subiekt_projekt — jednolita
# długość kodów kreskowych (numery rysunku mają 11-13 znaków).
MAX_SYMBOL = 13

# Symbol musi być czystym ASCII — Code 128 nie zakoduje „ł", „ś", „ę".
# Ta sama reguła i ta sama funkcja co przy symbolach z nazwy.
from subiekt_projekt import do_ascii

RODZAJE = [("towar", "Towar (materiał, część)"),
           ("usluga", "Usługa (robocizna, transport)"),
           ("komplet", "Komplet (złożenie ze składników)")]
JEDNOSTKI = ["szt", "kpl", "m", "mb", "kg", "l", "op", "rbg"]


def _odmiana_kartotek(n):
    """1 kartotek\u0119 / 2-4 kartoteki / 5+ kartotek.

    Komunikat przed zapisem do bazy PRODUKCYJNEJ ma brzmiec po polsku,
    a nie „2 kartotek" (16.09.2026).
    """
    if n == 1:
        return "kartotek\u0119"
    reszta100, reszta10 = n % 100, n % 10
    if 2 <= reszta10 <= 4 and not 12 <= reszta100 <= 14:
        return "kartoteki"
    return "kartotek"


def zaloz_kartoteke(symbol, nazwa, rodzaj="towar", jm="szt", cena=None, opis="",
                    zapisz=False, timeout=TIMEOUT_S):
    """{status, szczegoly, symbol} — status: istnieje | do-zalozenia | zalozona | blad."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")

    plan = {"symbol": symbol, "nazwa": nazwa, "rodzaj": rodzaj, "jm": jm,
            "cena": cena, "opis": opis}

    # ZAPIS — bez ponawiania (plan, sekcja 14): powtórzenie próbowałoby
    # założyć kartotekę o tym samym symbolu drugi raz.
    args = {"plan": plan}
    if zapisz:
        args["zapisz"] = True
    try:
        import subiekt_bridge
        return subiekt_bridge.call(
            "kartoteka", args, timeout=timeout, write=zapisz,
            fallback=lambda: _kartoteka_cli(plan, zapisz, timeout))
    except ImportError:
        return _kartoteka_cli(plan, zapisz, timeout)


def _kartoteka_cli(plan_dane, zapisz, timeout):
    """Stara ścieżka: osobny proces NexoRecon.exe."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")

    tmpdir = tempfile.mkdtemp(prefix="subiekt_kart_")
    plan = os.path.join(tmpdir, "k.json")
    out = os.path.join(tmpdir, "w.json")
    with open(plan, "w", encoding="utf-8") as f:
        json.dump(plan_dane, f, ensure_ascii=False)

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


def okno_nowa_kartoteka(parent, symbol="", nazwa="", rodzaj="towar",
                        po_zapisie=None, pozycje=None):
    """Formularz nowej kartoteki. Zwraca okno (Toplevel).

    `pozycje` — lista slownikow {symbol, nazwa, opis, rodzaj, jm, cena}
    z zaznaczenia w arkuszu. Gdy jest dluzsza niz 1, nad formularzem staje
    TABELA: klik w wiersz wczytuje go do pol, a „Zaloz wszystkie" przechodzi
    po kolei cala liste (16.09.2026).
    """
    lista = [dict(p) for p in (pozycje or []) if p]
    if lista and not symbol and not nazwa:
        symbol = lista[0].get("symbol") or ""
        nazwa = lista[0].get("nazwa") or ""
        rodzaj = lista[0].get("rodzaj") or rodzaj
    dlg = tk.Toplevel(parent)
    dlg.title("Nowa kartoteka w Subiekcie")
    dlg.transient(parent)
    dlg.grab_set()

    tk.Label(dlg, text="➕ Dodaj asortyment do Subiekta", bg="#34495e", fg="white",
             font=("Arial", 10, "bold"), anchor="w", padx=12, pady=8).pack(fill=tk.X)

    # ── tabela pozycji (tylko przy wielu zaznaczonych) ───────────────
    tabela = None
    if len(lista) > 1:
        ramka_tab = tk.LabelFrame(
            dlg, text=" Pozycje z arkusza (%d) — kliknij, żeby edytować "
                      % len(lista),
            font=("Arial", 9, "bold"), padx=8, pady=6)
        ramka_tab.pack(fill=tk.BOTH, expand=True, padx=14, pady=(10, 0))
        # „Typ" to wartosc Z ARKUSZA (X/XX/Z/ZZ/ZNORM) — pokazujemy ja
        # obok „Rodzaju", zeby bylo widac, skad wzial sie komplet vs towar.
        kol = (("lp", "Lp.", 30), ("symbol", "Symbol", 104),
               ("nazwa", "Nazwa", 170), ("opis", "Opis", 120),
               ("typ", "Typ", 46), ("rodzaj", "Rodzaj", 66),
               ("jm", "JM", 36), ("stan", "Stan", 86),
               ("cena", "Cena", 56))
        wrap_t = tk.Frame(ramka_tab)
        wrap_t.pack(fill=tk.BOTH, expand=True)
        # `extended` — Ctrl / Shift zaznacza wiele pozycji do zalozenia
        # (16.09.2026). Edycja w formularzu dotyczy JEDNEJ zaznaczonej.
        tabela = ttk.Treeview(wrap_t, columns=[k[0] for k in kol],
                              show="headings", height=8,
                              selectmode="extended")
        for klucz, naglowek, szer in kol:
            tabela.heading(klucz, text=naglowek)
            tabela.column(klucz, width=szer, minwidth=30,
                          stretch=(klucz in ("nazwa", "opis")),
                          anchor="e" if klucz == "cena" else "w")
        sc_t = ttk.Scrollbar(wrap_t, orient="vertical", command=tabela.yview)
        tabela.configure(yscrollcommand=sc_t.set)
        tabela.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc_t.pack(side=tk.RIGHT, fill=tk.Y)
        tabela.tag_configure("zalozona", background="#e8f8e8")
        tabela.tag_configure("blad", background="#f2dede")
        tk.Label(ramka_tab,
                 text="Klik = edycja w polach niżej.   "
                      "Ctrl / Shift + klik = zaznacz kilka do założenia.",
                 font=("Arial", 8), fg="#7f8c8d", anchor="w").pack(fill=tk.X)

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

    # OPIS zaraz za NAZWA — tak samo jak w tabeli wyzej. Wczesniej byl na
    # samym koncu i oko szukalo go w dwoch roznych miejscach (16.09.2026).
    wiersz(3, "Opis (opcjonalnie):")
    var_opis = tk.StringVar()
    tk.Entry(body, textvariable=var_opis, font=("Arial", 10)).grid(
        row=3, column=1, sticky="ew", pady=4)

    wiersz(4, "Rodzaj:")
    var_rodzaj = tk.StringVar(value=next((o for k, o in RODZAJE if k == rodzaj), RODZAJE[0][1]))
    ttk.Combobox(body, textvariable=var_rodzaj, values=[o for _, o in RODZAJE],
                 state="readonly", font=("Arial", 9)).grid(row=4, column=1, sticky="ew", pady=4)

    wiersz(5, "Jednostka:")
    var_jm = tk.StringVar(value="szt")
    ttk.Combobox(body, textvariable=var_jm, values=JEDNOSTKI,
                 font=("Arial", 9), width=10).grid(row=5, column=1, sticky="w", pady=4)

    wiersz(6, "Cena ewid. (opcjonalnie):")
    var_cena = tk.StringVar()
    tk.Entry(body, textvariable=var_cena, font=("Arial", 10), width=12).grid(
        row=6, column=1, sticky="w", pady=4)

    status = tk.Label(dlg, text="", font=("Arial", 8), fg="#7f8c8d", anchor="w", padx=14)
    status.pack(fill=tk.X)

    def licznik(*_):
        s = var_symbol.get().strip()
        n = len(s)
        # Kolejność ostrzeżeń: najpierw znaki spoza ASCII, bo one kod kreskowy
        # UNIEMOŻLIWIAJĄ, a nadmiar znaków tylko go rozciąga.
        poza = "".join(sorted({c for c in s if ord(c) > 127}))
        if poza:
            lbl_dl.config(text=f"znaki spoza ASCII ({poza}) — kod kreskowy ich nie zakoduje; "
                               "przy zapisie zamienię je na odpowiedniki", fg="#c0392b")
        elif n > MAX_SYMBOL:
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

        # Symbol z polskimi znakami zapisze się do Subiekta bez protestu, ale
        # kodu kreskowego z niego nie będzie — i wyjdzie to dopiero przy
        # drukowaniu etykiety. Dlatego prostujemy tu, za zgodą użytkownika.
        czysty = do_ascii(s)
        if czysty != s:
            if not messagebox.askyesno(
                    "Symbol a kod kreskowy",
                    f"Symbol „{s}” zawiera znaki, których kod kreskowy\n"
                    f"(Code 128) nie zakoduje — etykiety nie da się wydrukować.\n\n"
                    f"Zapisać jako „{czysty}”?\n\n"
                    "Pełna nazwa z polskimi znakami zostaje w polu Nazwa.",
                    parent=dlg):
                return None
            s = czysty
            var_symbol.set(s)
        if not s:
            messagebox.showwarning("Kartoteka",
                                   "Po usunięciu znaków spoza ASCII symbol jest pusty.\n"
                                   "Wpisz symbol z liter i cyfr.", parent=dlg)
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

    # ── tabela: wypelnienie i dwustronna synchronizacja ──────────────
    biezacy = {"i": 0}          # ktory wiersz listy jest w formularzu
    blokada = {"on": False}     # nie odsylaj do listy w trakcie podstawiania

    def _txt_ceny(c):
        try:
            return ("%.2f" % float(str(c).replace(",", "."))).replace(".", ",")
        except (TypeError, ValueError):
            return ""

    def _etykieta_rodzaju(klucz):
        return next((o for k, o in RODZAJE if k == (klucz or "towar")),
                    RODZAJE[0][1])

    def odswiez_tabele():
        if tabela is None:
            return
        zazn = tabela.selection()
        for w in tabela.get_children():
            tabela.delete(w)
        for i, p in enumerate(lista):
            tabela.insert("", "end", iid=str(i), values=(
                i + 1, p.get("symbol") or "", p.get("nazwa") or "",
                p.get("opis") or "", p.get("typ_arkusz") or "",
                _etykieta_rodzaju(p.get("rodzaj")),
                p.get("jm") or "szt", p.get("stan") or "",
                _txt_ceny(p.get("cena"))),
                tags=(p["tag"],) if p.get("tag") else ())
        if zazn and tabela.exists(zazn[0]):
            tabela.selection_set(zazn[0])

    def z_formularza_do_listy(*_a):
        """Kazda zmiana w polach wraca do wiersza tabeli."""
        if tabela is None or blokada["on"]:
            return
        if not (0 <= biezacy["i"] < len(lista)):
            return
        p = lista[biezacy["i"]]
        p["symbol"] = var_symbol.get().strip()
        p["nazwa"] = var_nazwa.get().strip()
        p["opis"] = var_opis.get().strip()
        p["jm"] = var_jm.get().strip() or "szt"
        p["cena"] = var_cena.get().strip()
        etykieta = var_rodzaj.get()
        p["rodzaj"] = next((k for k, o in RODZAJE if o == etykieta), "towar")
        # Ten wiersz jest teraz EDYTOWANY — przy probie przejscia dalej
        # zapytamy, czy na pewno go zostawiamy (16.09.2026).
        edytowany["i"] = biezacy["i"]
        odswiez_tabele()

    def z_listy_do_formularza(_e=None):
        wyb = tabela.selection() if tabela else ()
        if not wyb:
            return
        if len(wyb) > 1:
            # Wiele zaznaczonych = wybor do ZALOZENIA, nie do edycji —
            # pola zostaja przy ostatnio edytowanej pozycji.
            status.config(text="Zaznaczono %d pozycji do założenia"
                               % len(wyb), fg="#7f8c8d")
            return
        i = int(wyb[0])
        # Opuszczasz wiersz, ktory wlasnie edytowales? Pytamy — tak samo
        # jak edytor kartotek przy zmianie pozycji (16.09.2026).
        poprz = edytowany["i"]
        if (poprz is not None and poprz != i and poprz < len(lista)
                and lista[poprz].get("tag") != "zalozona"):
            pp = lista[poprz]
            if not messagebox.askyesno(
                    "Pozycja w trakcie edycji",
                    "Edytujesz pozycję %d:\n\n    %s — %s\n\n"
                    "Nie założono jej jeszcze w Subiekcie.\n\n"
                    "Przejść do innej pozycji?"
                    % (poprz + 1, pp.get("symbol") or "(brak symbolu)",
                       pp.get("nazwa") or ""),
                    icon="warning", default="no", parent=dlg):
                # Zostajemy — wracamy zaznaczeniem na edytowany wiersz.
                dlg.after_idle(lambda s=str(poprz): tabela.selection_set(s))
                return
            edytowany["i"] = None
        biezacy["i"] = i
        p = lista[i]
        # Bez odsylania do listy w trakcie podstawiania — inaczej `trace`
        # nadpisalby WLASNIE wybrany wiersz danymi poprzedniego.
        blokada["on"] = True
        try:
            var_symbol.set(p.get("symbol") or "")
            var_nazwa.set(p.get("nazwa") or "")
            var_opis.set(p.get("opis") or "")
            var_jm.set(p.get("jm") or "szt")
            var_cena.set(_txt_ceny(p.get("cena")))
            var_rodzaj.set(_etykieta_rodzaju(p.get("rodzaj")))
        finally:
            blokada["on"] = False
        status.config(text="Pozycja %d z %d" % (i + 1, len(lista)),
                      fg="#7f8c8d")

    if tabela is not None:
        for v in (var_symbol, var_nazwa, var_opis, var_jm, var_cena,
                  var_rodzaj):
            v.trace_add("write", z_formularza_do_listy)
        tabela.bind("<<TreeviewSelect>>", z_listy_do_formularza)
        odswiez_tabele()
        tabela.selection_set("0")

    def zaloz_wszystkie():
        """Zaklada ZAZNACZONE pozycje (albo cala liste, gdy nic nie zawezono).

        Wynik kazdej widac w kolumnie „Stan": zielone = zalozona,
        czerwone = blad. Juz zalozone sa pomijane, wiec przycisk mozna
        kliknac drugi raz po poprawieniu bledow.
        """
        zazn = [int(i) for i in (tabela.selection() if tabela else ())]
        # Jeden zaznaczony wiersz to normalny stan po klinieciu w tabele —
        # nie traktujemy go jako „zawezenia do jednego".
        wybrane = zazn if len(zazn) > 1 else list(range(len(lista)))
        do_zrobienia = [i for i in wybrane
                        if lista[i].get("tag") != "zalozona"]
        if not do_zrobienia:
            messagebox.showinfo(
                "Kartoteki",
                "Wybrane pozycje są już założone." if len(zazn) > 1
                else "Wszystkie pozycje są już założone.", parent=dlg)
            return
        podglad = "\n".join(
            "  %s  -  %s" % (lista[i].get("symbol") or "(brak symbolu)",
                             lista[i].get("nazwa") or "")
            for i in do_zrobienia[:12])
        if len(do_zrobienia) > 12:
            podglad += "\n  ... i %d dalszych" % (len(do_zrobienia) - 12)
        if not messagebox.askyesno(
                "Zapis do Subiekta",
                "Baza PRODUKCYJNA.\n\nZa\u0142o\u017cy\u0107 %d %s "
                "(%s):\n\n%s\n\n"
                "Kartoteki nie da si\u0119 \u0142atwo usun\u0105\u0107."
                % (len(do_zrobienia),
                   _odmiana_kartotek(len(do_zrobienia)),
                   "zaznaczone" if len(zazn) > 1 else "ca\u0142a lista",
                   podglad),
                parent=dlg, icon="warning", default="no"):
            return

        btn_zapisz.config(state=tk.DISABLED)
        btn_wszystkie.config(state=tk.DISABLED)

        def krok(nr):
            if nr >= len(do_zrobienia):
                btn_zapisz.config(state=tk.NORMAL)
                btn_wszystkie.config(state=tk.NORMAL)
                ile_ok = sum(1 for p in lista if p.get("tag") == "zalozona")
                status.config(text="Gotowe: %d z %d" % (ile_ok, len(lista)),
                              fg="#1e8449")
                return
            i = do_zrobienia[nr]
            p = lista[i]
            status.config(text="Zakladam %d/%d: %s..."
                               % (nr + 1, len(do_zrobienia), p.get("symbol")),
                          fg="#7f8c8d")
            sym = (p.get("symbol") or "").strip()
            if not sym:
                p["tag"], p["stan"] = "blad", "brak symbolu"
                odswiez_tabele()
                dlg.after(10, lambda: krok(nr + 1))
                return
            surowa = str(p.get("cena") or "").strip()
            try:
                cena = float(surowa.replace(",", ".")) if surowa else None
            except ValueError:
                cena = None

            def gotowe(w, err):
                if err:
                    p["tag"], p["stan"] = "blad", str(err)[:40]
                else:
                    stan = w.get("status")
                    p["tag"] = ("zalozona" if stan in ("zalozona", "istnieje")
                                else "blad")
                    p["stan"] = {"zalozona": "zalozona",
                                 "istnieje": "juz byla"}.get(
                        stan, (w.get("szczegoly") or stan or "blad")[:40])
                    if w.get("symbol"):
                        p["symbol"] = w["symbol"]
                    if po_zapisie and p["tag"] == "zalozona":
                        po_zapisie(dict(p, status=stan))
                odswiez_tabele()
                dlg.after(10, lambda: krok(nr + 1))

            w_tle(lambda: zaloz_kartoteke(
                symbol=sym, nazwa=p.get("nazwa") or sym,
                rodzaj=p.get("rodzaj") or "towar", jm=p.get("jm") or "szt",
                cena=cena, opis=p.get("opis") or "", zapisz=True), gotowe)

        krok(0)

    # ── ochrona przed utrata pracy ───────────────────────────────────
    edytowany = {"i": None}     # ktory wiersz tabeli jest w trakcie edycji

    def _cos_wpisane():
        """Czy w formularzu jest cokolwiek warte ostrzezenia."""
        return any(v.get().strip() for v in
                   (var_symbol, var_nazwa, var_opis, var_cena))

    def _nietkniete(p):
        """Czy wiersz tabeli zostal przy wartosciach z arkusza."""
        return not (p.get("symbol") or "").strip()

    def zamknij():
        """Anuluj / krzyzyk — z pytaniem, gdy cos jest wpisane."""
        if tabela is not None:
            niezalozone = [p for p in lista if p.get("tag") != "zalozona"]
            if niezalozone and not messagebox.askyesno(
                    "Zamknąć okno?",
                    "W tabeli jest %d %s, których NIE założono\n"
                    "w Subiekcie.\n\nZamknąć i porzucić je?"
                    % (len(niezalozone), _odmiana_kartotek(len(niezalozone))),
                    icon="warning", default="no", parent=dlg):
                return
        elif _cos_wpisane() and not messagebox.askyesno(
                "Zamknąć okno?",
                "Formularz jest wypełniony, ale kartoteki NIE założono\n"
                "w Subiekcie.\n\nZamknąć i porzucić dane?",
                icon="warning", default="no", parent=dlg):
            return
        dlg.destroy()

    # ⚠️ Krzyzyk MUSI isc ta sama droga — inaczej omija pytanie.
    dlg.protocol("WM_DELETE_WINDOW", zamknij)

    box = tk.Frame(dlg)
    box.pack(pady=(4, 12))
    tk.Button(box, text="🔍 Sprawdź", command=sprawdz, font=("Arial", 9),
              padx=12, pady=3).pack(side=tk.LEFT, padx=4)
    btn_zapisz = tk.Button(box, text="💾 Załóż w Subiekcie", command=zapisz, bg="#e67e22",
                           fg="white", font=("Arial", 9, "bold"), padx=14, pady=3)
    btn_zapisz.pack(side=tk.LEFT, padx=4)
    btn_wszystkie = tk.Button(box, text="\U0001f4da Załóż zaznaczone w Subiekcie",
                              command=zaloz_wszystkie, bg="#2471a3",
                              fg="white", font=("Arial", 9, "bold"),
                              padx=14, pady=3)
    if tabela is not None:
        btn_wszystkie.pack(side=tk.LEFT, padx=4)
    tk.Button(box, text="Anuluj", command=zamknij, font=("Arial", 9),
              padx=12, pady=3).pack(side=tk.LEFT, padx=4)

    ent_symbol.focus_set()
    # Tabela potrzebuje miejsca — okno rosnie tylko w trybie wsadowym.
    wysrodkuj(dlg, parent, 780 if tabela is not None else 560,
              680 if tabela is not None else 380)
    return dlg
