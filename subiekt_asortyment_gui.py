# -*- coding: utf-8 -*-
"""
Asortyment — pełna kartoteka Subiekta: przegląd i edycja.

    import subiekt_asortyment_gui
    subiekt_asortyment_gui.open_window(parent)

Odpowiednik listy „Asortyment" w Subiekcie nexo, z tymi samymi kolumnami
(Rodzaj, Symbol, Nazwa, Stan, Zarezerwowane, Dostępne, Netto), plus to,
czego tam nie ma wygodnie: edycja nazwy i ceny wprost w tabeli oraz podgląd
i poprawianie SKŁADU kompletu.

Czym się różni od okna „Magazyn" (subiekt_magazyn_gui): tamto jest dla
magazyniera i pokazuje TYLKO kartoteki ze stanem albo z progiem — jego
tematem są progi min/opt, domawianie i RW. Tutaj widać WSZYSTKO, co jest
w kartotece Subiekta, łącznie z pozycjami bez ruchu, bo tematem jest sama
kartoteka: czy nazwa się zgadza, czy komplet ma właściwy skład.

STANY SĄ NA ŻĄDANIE. Tryb „katalog" (nazwa, rodzaj, cena) idzie ~9 s na
3444 kartotekach; pełne stany to osobne zapytanie na kartotekę i przy całej
bazie okno wisiałoby minutami (zmierzone 05.09.2026 przy oknie Magazyn).
Dlatego lista otwiera się bez stanów, a stan dociąga się dla tego, co
widać — przyciskiem albo po zaznaczeniu pozycji.

ZAPIS idzie trybem „kartoteka-edytuj" i NIGDY nie rusza symbolu: symbol
jest kluczem w kodach kreskowych, na dokumentach i w składach kompletów.
Od jego zmiany jest osobny tryb „symbole", który wie, co przy tym poprawić.
"""

import json
import os
import subprocess
import tempfile
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

TIMEOUT_S = 600
#: Ile kartotek doczytujemy stanami za jednym razem. Tryb „stan" pyta
#: Subiekta o stany per kartoteka, więc koszt rośnie liniowo — porcja
#: trzyma czekanie w granicach kilku sekund i pozwala pokazać postęp.
PORCJA_STANOW = 300
NL = chr(10)

#: Rodzaje z Subiekta na dwuliterowe kody, jak w kolumnie „Rodzaj" listy
#: Asortymentu (TW/KT/US/OP). Nieznany rodzaj pokazujemy w całości —
#: lepiej dziwny napis niż zgubiona informacja.
KODY_RODZAJU = {"towar": "TW", "komplet": "KT", "usługa": "US",
                "usluga": "US", "opakowanie": "OP"}


def _kod_rodzaju(rodzaj):
    r = (rodzaj or "").strip()
    return KODY_RODZAJU.get(r.lower(), r)


def _czy_komplet(p):
    return (p.get("Rodzaj") or "").strip().lower() == "komplet"


# ── most ────────────────────────────────────────────────────────────────────
def _uruchom(tryb, argv, out, timeout, plan=None, symbole=None, write=False):
    """Wynik komendy mostu. Stały most, w razie czego stare CLI.

    Ten sam wzorzec co w subiekt_magazyn_gui: most trzyma jedną sesję Sfery,
    więc kolejne wywołania nie płacą ~10 s za start procesu i logowanie.
    """
    try:
        import subiekt_bridge
    except ImportError:
        return _uruchom_cli(tryb, argv, out, timeout, plan, symbole)

    return subiekt_bridge.wywolaj(
        tryb, argv, timeout=timeout, plan=plan, symbole=symbole,
        fallback=(None if write else
                  (lambda: _uruchom_cli(tryb, argv, out, timeout, plan, symbole))))


def _uruchom_cli(tryb, argv, out, timeout, plan=None, symbole=None):
    """Stara ścieżka: osobny proces NexoRecon.exe na każde wywołanie."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:{NL}{CONFIG_PATH}")

    argv = list(argv)
    tmp = os.path.dirname(out)
    if plan is not None:
        plan_path = os.path.join(tmp, "plan.json")
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False)
        argv.append(f"--plan={plan_path}")
    if symbole:
        sym_path = os.path.join(tmp, "symbole.txt")
        with open(sym_path, "w", encoding="utf-8") as f:
            f.write(NL.join(symbole))
        argv.append(f"--symbols-file={sym_path}")

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.run([exe, tryb, f"--out={out}", *argv],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=flags)
    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(blad_mostu(exe, tryb, proc, out))
    with open(out, encoding="utf-8") as f:
        return json.load(f)


def pobierz_katalog(timeout=TIMEOUT_S):
    """[{Id, Symbol, Nazwa, Rodzaj, CenaEwidencyjna}] — WSZYSTKIE kartoteki.

    Bez stanów — to najdroższa część odczytu i tutaj świadomie jej nie ma
    (patrz nagłówek modułu)."""
    out = os.path.join(tempfile.mkdtemp(prefix="subiekt_asort_"), "katalog.json")
    return _uruchom("katalog", [], out, timeout).get("pozycje", [])


def pobierz_stany(symbole, timeout=TIMEOUT_S):
    """Stany dla PODANYCH symboli: [{Pytany, Symbol, Istnieje, Dostepne,
    Zadysponowane, Magazyny:[...]}]. Tryb „stan" — punktowy, na żądanie."""
    if not symbole:
        return []
    out = os.path.join(tempfile.mkdtemp(prefix="subiekt_stan_"), "stan.json")
    return _uruchom("stan", [], out, timeout, symbole=list(symbole)).get("pozycje", [])


def pobierz_sklad(symbol, timeout=TIMEOUT_S):
    """{Skladniki:[{Symbol, Nazwa, Ilosc, Rodzaj}], WchodziW:[...]} albo None."""
    out = os.path.join(tempfile.mkdtemp(prefix="subiekt_kpl_"), "komplet.json")
    poz = _uruchom("komplet", [], out, timeout, symbole=[symbol]).get("pozycje", [])
    return poz[0] if poz else None


def zapisz_kartoteki(pozycje, zapisz=False, timeout=TIMEOUT_S):
    """Zmiana istniejących kartotek. pozycje: [{symbol, nazwa?, cena?, sklad?}].
    Zwraca {zapisano, zmienionych, kroki}. zapisz=False = suchy przebieg."""
    tmp = tempfile.mkdtemp(prefix="subiekt_edyt_")
    argv = ["--zapisz"] if zapisz else []
    return _uruchom("kartoteka-edytuj", argv, os.path.join(tmp, "wynik.json"),
                    timeout, plan={"pozycje": pozycje}, write=zapisz)


def _liczba(tekst, domyslna=0.0):
    try:
        return float(str(tekst).replace(",", ".").strip() or 0)
    except (TypeError, ValueError):
        return domyslna


def _f(x):
    """Liczba do komórki: całkowite bez „.0", puste dla zera."""
    x = float(x or 0)
    if x == 0:
        return ""
    return f"{x:g}"


class AsortymentWindow(tk.Toplevel, Kreciolek):
    KOLUMNY = [("rodzaj", "Rodzaj", 60), ("symbol", "Symbol", 150),
               ("nazwa", "Nazwa", 320), ("stan", "Stan", 78),
               ("zarezerwowane", "Zarezerwowane", 100),
               ("dostepne", "Dostępne", 80), ("netto", "Netto", 90),
               ("sklad", "Składników", 78), ("opis", "Opis", 200)]
    (COL_RODZAJ, COL_SYMBOL, COL_NAZWA, COL_STAN, COL_REZERW,
     COL_DOSTEPNE, COL_NETTO, COL_SKLAD, COL_OPIS) = range(9)
    #: Nazwa i Netto — te dwie rzeczy poprawia się z ręki. Symbol NIE
    #: (jest kluczem), stany NIE (biorą się z dokumentów).
    EDYTOWALNE = (COL_NAZWA, COL_NETTO)
    KOL_SKLAD = [("symbol", "Symbol", 150), ("nazwa", "Nazwa", 300),
                 ("ilosc", "Ilość", 80), ("rodzaj", "Rodzaj", 70)]

    def __init__(self, parent):
        super().__init__(parent)
        self.pozycje = []
        self.widoczne = []
        self.stany_wczytane = set()     # symbole, dla których znamy już stan
        self._biezacy = None            # pozycja pokazana w dolnej tabeli
        self._zajete = False            # trwa operacja mostu

        self.title("Subiekt — asortyment: kartoteki, ceny, skład kompletów")
        self.geometry("1360x760")
        self.minsize(980, 480)
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

        self._buduj()
        self.after(100, self._wczytaj_async)

    # ── UI ─────────────────────────────────────────────────────────────────
    def _buduj(self):
        top = tk.Frame(self, bg="#34495e", height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🗂 Asortyment — pełna kartoteka Subiekta",
                 bg="#34495e", fg="white",
                 font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)
        self.lbl_wiek = tk.Label(top, text="", bg="#34495e", fg="#e74c3c",
                                 font=("Arial", 13, "bold"))
        self.lbl_wiek.pack(side=tk.LEFT, padx=(16, 0))
        self.btn_refresh = tk.Button(top, text="🔄 Odśwież", command=self._wczytaj_async,
                                     bg="#3498db", fg="white", font=("Arial", 8),
                                     padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_refresh.pack(side=tk.RIGHT, padx=10, pady=8)

        f = tk.Frame(self, bg="#ecf0f1")
        f.pack(side=tk.TOP, fill=tk.X)
        tk.Label(f, text="Szukaj:", bg="#ecf0f1",
                 font=("Arial", 9)).pack(side=tk.LEFT, padx=(12, 3), pady=6)
        self.var_szukaj = tk.StringVar()
        self.var_szukaj.trace_add("write", lambda *_: self._odswiez_liste())
        tk.Entry(f, textvariable=self.var_szukaj, width=24,
                 font=("Arial", 9)).pack(side=tk.LEFT, pady=6)
        tk.Label(f, text="(symbol albo nazwa)", bg="#ecf0f1", fg="#7f8c8d",
                 font=("Arial", 8)).pack(side=tk.LEFT, padx=(4, 0))

        tk.Label(f, text="Rodzaj:", bg="#ecf0f1",
                 font=("Arial", 9)).pack(side=tk.LEFT, padx=(16, 3), pady=6)
        self.var_rodzaj = tk.StringVar(value="wszystkie")
        self.cb_rodzaj = ttk.Combobox(f, textvariable=self.var_rodzaj, width=14,
                                      state="readonly", font=("Arial", 9),
                                      values=["wszystkie"])
        self.cb_rodzaj.pack(side=tk.LEFT, pady=6)
        self.cb_rodzaj.bind("<<ComboboxSelected>>", lambda _e: self._odswiez_liste())

        self.btn_stany = tk.Button(f, text="📊 Dociągnij stany dla widocznych",
                                   command=self._dociagnij_stany, bg="#16a085",
                                   fg="white", font=("Arial", 8), padx=8, pady=2,
                                   relief=tk.RAISED, bd=1)
        self.btn_stany.pack(side=tk.LEFT, padx=(16, 0), pady=6)

        leg = tk.Frame(self, bg="#ecf0f1")
        leg.pack(side=tk.TOP, fill=tk.X)
        tk.Label(leg, text="Edycja wprost w tabeli: Nazwa, Netto.  Symbol jest kluczem — "
                           "nie zmienia się tutaj.  DWUKLIK w komplet = skład do edycji.",
                 bg="#ecf0f1", fg="#7f8c8d", font=("Arial", 8), anchor="w",
                 padx=12).pack(side=tk.LEFT, pady=(0, 2))
        for kolor, opis in (("#f9e79f", "zmienione — do zapisu"),
                            ("#eaeded", "stan niewczytany")):
            tk.Label(leg, text="  ", bg=kolor, relief=tk.SOLID, bd=1).pack(side=tk.LEFT, padx=(10, 2))
            tk.Label(leg, text=opis, bg="#ecf0f1", fg="#7f8c8d",
                     font=("Arial", 8)).pack(side=tk.LEFT)

        self.podsumowanie = tk.Label(self, text="Wczytywanie…", bg="#ecf0f1",
                                     fg="#2c3e50", font=("Arial", 9), anchor="w",
                                     padx=12, pady=6)
        self.podsumowanie.pack(side=tk.TOP, fill=tk.X)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        bottom = tk.Frame(self)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 6))
        self.btn_zapisz = tk.Button(bottom, text="💾 Zapisz zmiany (0)",
                                    command=self._zapisz, bg="#27ae60", fg="white",
                                    font=("Arial", 9, "bold"), padx=14, pady=5,
                                    relief=tk.RAISED, bd=2, state=tk.DISABLED)
        self.btn_zapisz.pack(side=tk.RIGHT)
        tk.Button(bottom, text="↩ Cofnij zmiany", command=self._cofnij,
                  font=("Arial", 9), padx=10, pady=5,
                  relief=tk.RAISED, bd=1).pack(side=tk.RIGHT, padx=(0, 8))
        tk.Button(bottom, text="➕ Nowa kartoteka…", command=self._nowa_kartoteka,
                  bg="#2980b9", fg="white", font=("Arial", 9), padx=10, pady=5,
                  relief=tk.RAISED, bd=1).pack(side=tk.RIGHT, padx=(0, 8))
        tk.Label(bottom, text="Zapis idzie do bazy PRODUKCYJNEJ — przed nim zobaczysz "
                              "listę zmian do potwierdzenia.",
                 fg="#7f8c8d", font=("Arial", 8)).pack(side=tk.LEFT)

        panel = ttk.PanedWindow(self, orient=tk.VERTICAL)
        panel.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 4))

        gora = tk.Frame(panel)
        panel.add(gora, weight=3)
        if Sheet is None:
            tk.Label(gora, text="Brak biblioteki tksheet", fg="#c0392b").pack(pady=20)
            self.sheet = self.sheet_sklad = None
            return

        self.sheet = Sheet(gora, headers=[k[1] for k in self.KOLUMNY],
                           column_width=140, theme="light blue")
        self.sheet.set_options(show_selected_cells_border=True,
                               enable_edit_cell_auto_resize=False,
                               empty_horizontal=0, empty_vertical=0)
        self.sheet.enable_bindings((
            "single_select", "drag_select", "ctrl_select", "select_all",
            "column_width_resize", "arrowkeys", "right_click_popup_menu",
            "rc_select", "copy", "edit_cell",
        ))
        try:
            self.sheet.readonly_columns(
                columns=[i for i in range(len(self.KOLUMNY)) if i not in self.EDYTOWALNE])
        except Exception:
            pass
        podepnij_szerokosci(self, self.sheet, "asortyment", [k[2] for k in self.KOLUMNY])
        self.sheet.extra_bindings("cell_select", self._wybor_pozycji)
        self.sheet.extra_bindings("row_select", self._wybor_pozycji)
        self.sheet.bind("<<SheetModified>>", self._on_edit)
        self.sheet.bind("<Double-Button-1>", self._on_dblclick, add="+")
        self.sheet.popup_menu_add_command("🔍 Karta pozycji (złożenie, BOM, Subiekt)",
                                          self._karta_pozycji)
        self.sheet.popup_menu_add_command("📊 Dociągnij stan dla wierszy",
                                          self._stan_dla_wybranych)
        self.sheet.pack(fill=tk.BOTH, expand=True)

        dol = tk.Frame(panel)
        panel.add(dol, weight=1)
        pasek = tk.Frame(dol, bg="#ecf0f1")
        pasek.pack(side=tk.TOP, fill=tk.X)
        self.lbl_sklad = tk.Label(pasek, text="Skład kompletu", bg="#ecf0f1", anchor="w",
                                  font=("Arial", 8, "bold"), padx=8, pady=3)
        self.lbl_sklad.pack(side=tk.LEFT)
        self.btn_skl_dodaj = tk.Button(pasek, text="➕ składnik", command=self._sklad_dodaj,
                                       font=("Arial", 8), padx=6, pady=1, state=tk.DISABLED)
        self.btn_skl_dodaj.pack(side=tk.RIGHT, padx=(0, 8), pady=2)
        self.btn_skl_usun = tk.Button(pasek, text="➖ usuń składnik", command=self._sklad_usun,
                                      font=("Arial", 8), padx=6, pady=1, state=tk.DISABLED)
        self.btn_skl_usun.pack(side=tk.RIGHT, padx=(0, 6), pady=2)

        self.sheet_sklad = Sheet(dol, headers=[k[1] for k in self.KOL_SKLAD],
                                 column_width=150, theme="light blue")
        self.sheet_sklad.set_options(show_selected_cells_border=True,
                                     enable_edit_cell_auto_resize=False,
                                     empty_horizontal=0, empty_vertical=0)
        self.sheet_sklad.enable_bindings(("single_select", "drag_select",
                                          "column_width_resize", "arrowkeys",
                                          "copy", "edit_cell"))
        try:
            # Ilość edytowalna; symbol/nazwa/rodzaj to dane składnika z jego
            # własnej kartoteki — poprawia się je na TAMTEJ pozycji, nie tu.
            self.sheet_sklad.readonly_columns(columns=[0, 1, 3])
        except Exception:
            pass
        podepnij_szerokosci(self, self.sheet_sklad, "asortyment_sklad",
                            [k[2] for k in self.KOL_SKLAD])
        self.sheet_sklad.bind("<<SheetModified>>", self._on_edit_sklad)
        self.sheet_sklad.pack(fill=tk.BOTH, expand=True)

    # ── wczytywanie ────────────────────────────────────────────────────────
    def _wczytaj_async(self):
        if self._zajete:
            return
        self._zajete = True
        self.btn_refresh.config(state=tk.DISABLED)
        self.start_kreciolek("Czytam kartoteki z Subiekta")
        threading.Thread(target=self._wczytaj_worker, daemon=True).start()

    def _wczytaj_worker(self):
        try:
            poz = pobierz_katalog()
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._wczytaj_done(None, err))
            return
        self.after(0, lambda: self._wczytaj_done(poz, None))

    def _wczytaj_done(self, poz, error):
        self._zajete = False
        self.stop_kreciolek("")
        try:
            self.btn_refresh.config(state=tk.NORMAL)
        except tk.TclError:
            return                      # okno zamknięte w trakcie odczytu
        if error:
            self.status.config(text="Błąd odczytu.")
            messagebox.showerror("Subiekt", error, parent=self)
            return

        # Odświeżenie nie kasuje niezapisanej pracy — ta sama zasada co
        # w oknie Magazyn: zmienione nazwy, ceny i składy przeżywają
        # przeładowanie, żeby „Odśwież" nie był pułapką.
        poprzednie = {p["Symbol"].strip().upper(): p for p in self.pozycje}
        stany = {s: self._stan_pozycji(p)
                 for s, p in poprzednie.items() if s in self.stany_wczytane}

        nowe = []
        for p in poz or []:
            symbol = (p.get("Symbol") or "").strip()
            if not symbol:
                continue
            p["nazwa"] = (p.get("Nazwa") or "").strip()
            p["nazwa_subiekt"] = p["nazwa"]
            p["netto"] = float(p.get("CenaEwidencyjna") or 0)
            p["netto_subiekt"] = p["netto"]
            p["sklad"] = None           # None = jeszcze nieczytany z Subiekta
            p["sklad_subiekt"] = None
            p["stan"] = None            # None = stan niewczytany
            p["zarezerwowane"] = None
            p["dostepne"] = None
            p["magazyny"] = []

            stare = poprzednie.get(symbol.upper())
            if stare:
                if stare.get("nazwa") != stare.get("nazwa_subiekt"):
                    p["nazwa"] = stare["nazwa"]
                if stare.get("netto") != stare.get("netto_subiekt"):
                    p["netto"] = stare["netto"]
                if stare.get("sklad") is not None:
                    p["sklad"], p["sklad_subiekt"] = stare["sklad"], stare["sklad_subiekt"]
                zap = stany.get(symbol.upper())
                if zap:
                    p.update(zap)
            nowe.append(p)

        self.pozycje = nowe
        # Stany dotyczą kartotek, które mogły zniknąć — zawężamy do istniejących.
        obecne = {p["Symbol"].strip().upper() for p in nowe}
        self.stany_wczytane &= obecne

        rodzaje = sorted({(p.get("Rodzaj") or "").strip() for p in nowe if p.get("Rodzaj")})
        self.cb_rodzaj.config(values=["wszystkie"] + rodzaje)
        if self.var_rodzaj.get() not in ("wszystkie", *rodzaje):
            self.var_rodzaj.set("wszystkie")

        self.zaznacz_odczyt(self.lbl_wiek)
        self._odswiez_liste()

    @staticmethod
    def _stan_pozycji(p):
        return {k: p.get(k) for k in ("stan", "zarezerwowane", "dostepne", "magazyny")}

    # ── stany na żądanie ───────────────────────────────────────────────────
    def _dociagnij_stany(self):
        """Stany dla tego, co widać — brakujące, porcjami."""
        brak = [p["Symbol"] for p in self.widoczne
                if p["Symbol"].strip().upper() not in self.stany_wczytane]
        if not brak:
            self.status.config(text="Stany widocznych pozycji są już wczytane.")
            return
        if len(brak) > PORCJA_STANOW:
            if not messagebox.askyesno(
                    "Stany",
                    f"Do wczytania: {len(brak)} kartotek.{NL}{NL}"
                    f"Subiekt liczy stan osobno dla każdej — przy tej liczbie "
                    f"potrwa to nawet kilka minut.{NL}{NL}"
                    "Zawęź listę szukaniem albo filtrem rodzaju, żeby poszło szybciej."
                    f"{NL}{NL}Czytać mimo to?",
                    parent=self, icon="warning"):
                return
        self._czytaj_stany(brak)

    def _stan_dla_wybranych(self):
        try:
            rows = self.sheet.get_selected_rows(get_cells_as_rows=True)
        except Exception:
            rows = []
        sym = [self.widoczne[r]["Symbol"] for r in sorted(rows)
               if 0 <= r < len(self.widoczne)]
        if sym:
            self._czytaj_stany(sym)

    def _czytaj_stany(self, symbole):
        if self._zajete:
            self.status.config(text="Poczekaj — trwa inna operacja.")
            return
        self._zajete = True
        self.btn_stany.config(state=tk.DISABLED)
        self.start_kreciolek(f"Czytam stany ({len(symbole)} kartotek)")
        threading.Thread(target=self._stany_worker, args=(list(symbole),),
                         daemon=True).start()

    def _stany_worker(self, symbole):
        zebrane, blad = [], None
        # Porcjami — jedno zapytanie o 3000 symboli potrafiłoby przekroczyć
        # timeout mostu i zwrócić nic; przy porcjach tracimy najwyżej ostatnią.
        for i in range(0, len(symbole), PORCJA_STANOW):
            porcja = symbole[i:i + PORCJA_STANOW]
            try:
                zebrane.extend(pobierz_stany(porcja))
            except Exception as e:
                blad = str(e)
                break
            self.after(0, lambda n=len(zebrane): self._kreciolek_postep(n, len(symbole)))
        self.after(0, lambda: self._stany_done(zebrane, blad))

    def _kreciolek_postep(self, ile, razem):
        # Przez tekst_kreciolka, nie przez status.config — pasek należy do
        # kręciołka i wpisanie w niego czegokolwiek wprost zostałoby
        # nadpisane przy najbliższej klatce animacji.
        try:
            self.tekst_kreciolka(f"Czytam stany: {ile} z {razem}")
        except tk.TclError:
            pass

    def _stany_done(self, wyniki, blad):
        self._zajete = False
        self.stop_kreciolek("")
        try:
            self.btn_stany.config(state=tk.NORMAL)
        except tk.TclError:
            return

        wg_symbolu = {p["Symbol"].strip().upper(): p for p in self.pozycje}
        for w in wyniki or []:
            klucz = (w.get("Symbol") or w.get("Pytany") or "").strip().upper()
            p = wg_symbolu.get(klucz)
            if p is None:
                continue
            mag = w.get("Magazyny") or []
            # „Stan" w Subiekcie to całość na magazynie, „Dostępne" to ta część,
            # której nic nie blokuje. Rezerwacje sumujemy z obu rodzajów
            # (ilościowe i dostawowe) — tak samo jak tryb „magazyn".
            rezerw = sum(float(m.get("RezerwacjaIlosciowa") or 0)
                         + float(m.get("RezerwacjaDostawowa") or 0) for m in mag)
            dostepne = float(w.get("Dostepne") or 0)
            p["stan"] = dostepne + rezerw
            p["zarezerwowane"] = rezerw
            p["dostepne"] = dostepne
            p["magazyny"] = mag
            self.stany_wczytane.add(klucz)

        if blad:
            self.status.config(text="Błąd przy czytaniu stanów.")
            messagebox.showerror("Subiekt", blad, parent=self)
        self._odswiez_liste()

    # ── lista ──────────────────────────────────────────────────────────────
    def _zmieniona(self, p):
        return (p["nazwa"] != p["nazwa_subiekt"]
                or p["netto"] != p["netto_subiekt"]
                or (p["sklad"] is not None and p["sklad"] != p["sklad_subiekt"]))

    def _odswiez_liste(self):
        if not self.sheet:
            return
        szukaj = (self.var_szukaj.get() or "").strip().lower()
        rodzaj = self.var_rodzaj.get()
        self.widoczne = [
            p for p in self.pozycje
            if (not szukaj
                or szukaj in str(p.get("Symbol", "")).lower()
                or szukaj in str(p.get("nazwa", "")).lower())
            and (rodzaj == "wszystkie" or (p.get("Rodzaj") or "").strip() == rodzaj)
        ]

        def komorka_stanu(p, klucz):
            # Pusto znaczy „zero", więc dla niewczytanych dajemy kreskę —
            # inaczej cała lista wyglądałaby na wyzerowany magazyn.
            return "–" if p[klucz] is None else _f(p[klucz])

        self.sheet.set_sheet_data([[
            _kod_rodzaju(p.get("Rodzaj")),
            p.get("Symbol", ""), p["nazwa"],
            komorka_stanu(p, "stan"), komorka_stanu(p, "zarezerwowane"),
            komorka_stanu(p, "dostepne"),
            f"{p['netto']:.2f}",
            ("" if p["sklad"] is None else str(len(p["sklad"]))) if _czy_komplet(p) else "",
            (p.get("Opis") or "").strip(),
        ] for p in self.widoczne], reset_col_positions=False, redraw=False)

        try:
            self.sheet.dehighlight_all()
        except Exception:
            pass
        for i, p in enumerate(self.widoczne):
            if p["stan"] is None:
                for c in (self.COL_STAN, self.COL_REZERW, self.COL_DOSTEPNE):
                    self.sheet.highlight_cells(row=i, column=c, bg="#eaeded", fg="#95a5a6")
            if p["nazwa"] != p["nazwa_subiekt"]:
                self.sheet.highlight_cells(row=i, column=self.COL_NAZWA,
                                           bg="#f9e79f", fg="#7d6608")
            if p["netto"] != p["netto_subiekt"]:
                self.sheet.highlight_cells(row=i, column=self.COL_NETTO,
                                           bg="#f9e79f", fg="#7d6608")
            if p["sklad"] is not None and p["sklad"] != p["sklad_subiekt"]:
                self.sheet.highlight_cells(row=i, column=self.COL_SKLAD,
                                           bg="#f9e79f", fg="#7d6608")
        self.sheet.redraw()
        self._przelicz_podsumowanie()

    def _przelicz_podsumowanie(self):
        do_zapisu = sum(1 for p in self.pozycje if self._zmieniona(p))
        bez_stanu = sum(1 for p in self.widoczne if p["stan"] is None)
        komplety = sum(1 for p in self.widoczne if _czy_komplet(p))
        self.podsumowanie.config(
            text=f"Pozycji: {len(self.widoczne)} z {len(self.pozycje)}    "
                 f"kompletów: {komplety}    "
                 + (f"bez wczytanego stanu: {bez_stanu}    " if bez_stanu else "")
                 + f"zmienionych do zapisu: {do_zapisu}")
        try:
            self.btn_zapisz.config(text=f"💾 Zapisz zmiany ({do_zapisu})",
                                   state=tk.NORMAL if do_zapisu else tk.DISABLED)
        except tk.TclError:
            pass

    # ── edycja ─────────────────────────────────────────────────────────────
    def _on_edit(self, _event=None):
        """Nazwa / Netto z tabeli wracają do modelu."""
        if not self.sheet:
            return
        try:
            dane = self.sheet.get_sheet_data()
        except Exception:
            return
        for i, p in enumerate(self.widoczne):
            if i >= len(dane):
                break
            nazwa = str(dane[i][self.COL_NAZWA] or "").strip()
            # Pusta nazwa nie ma sensu — Subiekt jej nie przyjmie, a wpisanie
            # jej tutaj wyglądałoby na skasowanie danych. Wracamy do poprzedniej.
            p["nazwa"] = nazwa or p["nazwa"]
            p["netto"] = _liczba(dane[i][self.COL_NETTO], p["netto"])
        self._odswiez_liste()

    def _cofnij(self):
        """Wszystkie niezapisane zmiany z powrotem do wartości z Subiekta."""
        ile = sum(1 for p in self.pozycje if self._zmieniona(p))
        if not ile:
            return
        if not messagebox.askyesno("Cofnij zmiany",
                                   f"Porzucić {ile} niezapisanych zmian?", parent=self):
            return
        for p in self.pozycje:
            p["nazwa"] = p["nazwa_subiekt"]
            p["netto"] = p["netto_subiekt"]
            p["sklad"] = p["sklad_subiekt"]
        self._odswiez_liste()
        self._pokaz_sklad(self._biezacy)

    # ── skład kompletu ─────────────────────────────────────────────────────
    def _wybor_pozycji(self, _event=None):
        if not self.sheet or not self.sheet_sklad:
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
        p = self.widoczne[r]
        if not getattr(self, "_kreci", False):
            self.status.config(text=f"{p.get('Symbol', '')} — {p['nazwa']}")
        self._pokaz_sklad(p)

    def _pokaz_sklad(self, p):
        """Dolna tabela: skład, jeśli to komplet. Czyta z Subiekta raz."""
        self._biezacy = p
        if not self.sheet_sklad:
            return
        if p is None or not _czy_komplet(p):
            self.sheet_sklad.set_sheet_data([], reset_col_positions=False)
            self.lbl_sklad.config(text="Skład kompletu — zaznacz komplet (KT) na liście")
            self.btn_skl_dodaj.config(state=tk.DISABLED)
            self.btn_skl_usun.config(state=tk.DISABLED)
            return

        self.btn_skl_dodaj.config(state=tk.NORMAL)
        self.btn_skl_usun.config(state=tk.NORMAL)
        if p["sklad"] is None:
            self.lbl_sklad.config(text=f"Skład: {p['Symbol']} — czytam…")
            self.sheet_sklad.set_sheet_data([], reset_col_positions=False)
            self._czytaj_sklad(p)
            return
        self._rysuj_sklad(p)

    def _rysuj_sklad(self, p):
        self.lbl_sklad.config(
            text=f"Skład: {p['Symbol']} — {p['nazwa']}   ({len(p['sklad'])} składników)")
        self.sheet_sklad.set_sheet_data([[
            s.get("Symbol", ""), s.get("Nazwa", ""),
            f"{float(s.get('Ilosc') or 0):g}", _kod_rodzaju(s.get("Rodzaj")),
        ] for s in p["sklad"]], reset_col_positions=False)

    def _czytaj_sklad(self, p):
        if self._zajete:
            return
        self._zajete = True
        symbol = p["Symbol"]
        threading.Thread(target=self._sklad_worker, args=(p, symbol),
                         daemon=True).start()

    def _sklad_worker(self, p, symbol):
        try:
            dane = pobierz_sklad(symbol)
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._sklad_done(p, None, err))
            return
        self.after(0, lambda: self._sklad_done(p, dane, None))

    def _sklad_done(self, p, dane, blad):
        self._zajete = False
        try:
            if blad:
                self.lbl_sklad.config(text=f"Skład: {p['Symbol']} — błąd odczytu")
                self.status.config(text=blad)
                return
            sklad = [{"Symbol": (s.get("Symbol") or "").strip(),
                      "Nazwa": (s.get("Nazwa") or "").strip(),
                      "Ilosc": float(s.get("Ilosc") or 0),
                      "Rodzaj": s.get("Rodzaj") or ""}
                     for s in ((dane or {}).get("Skladniki") or [])]
            p["sklad"] = sklad
            # Kopia GŁĘBOKA jako punkt odniesienia — inaczej edycja ilości
            # zmieniałaby też „stan z Subiekta" i zmiana nigdy nie byłaby widoczna.
            p["sklad_subiekt"] = [dict(s) for s in sklad]
            if self._biezacy is p:
                self._rysuj_sklad(p)
            self._odswiez_liste()
        except tk.TclError:
            pass

    def _on_edit_sklad(self, _event=None):
        """Ilość składnika z dolnej tabeli wraca do modelu."""
        p = self._biezacy
        if not p or p.get("sklad") is None or not self.sheet_sklad:
            return
        try:
            dane = self.sheet_sklad.get_sheet_data()
        except Exception:
            return
        for i, s in enumerate(p["sklad"]):
            if i >= len(dane):
                break
            s["Ilosc"] = _liczba(dane[i][2], s["Ilosc"])
        self._odswiez_liste()

    def _sklad_dodaj(self):
        """Dokłada składnik do kompletu — symbol wybierany z kartoteki."""
        p = self._biezacy
        if not p or not _czy_komplet(p):
            return
        if p.get("sklad") is None:
            self.status.config(text="Poczekaj — skład jeszcze się czyta.")
            return
        wybor = self._wybierz_kartoteke("Składnik do dołożenia")
        if not wybor:
            return
        if any((s["Symbol"] or "").strip().upper() == wybor["Symbol"].strip().upper()
               for s in p["sklad"]):
            messagebox.showinfo("Skład",
                                f"„{wybor['Symbol']}” już jest w składzie.{NL}"
                                "Zmień jego ilość zamiast dokładać drugi wiersz.",
                                parent=self)
            return
        if wybor["Symbol"].strip().upper() == p["Symbol"].strip().upper():
            messagebox.showwarning("Skład", "Komplet nie może zawierać sam siebie.",
                                   parent=self)
            return
        p["sklad"].append({"Symbol": wybor["Symbol"], "Nazwa": wybor["nazwa"],
                           "Ilosc": 1.0, "Rodzaj": wybor.get("Rodzaj") or ""})
        self._rysuj_sklad(p)
        self._odswiez_liste()

    def _sklad_usun(self):
        p = self._biezacy
        if not p or p.get("sklad") is None:
            return
        try:
            rows = sorted(self.sheet_sklad.get_selected_rows(get_cells_as_rows=True))
        except Exception:
            rows = []
        rows = [r for r in rows if 0 <= r < len(p["sklad"])]
        if not rows:
            self.status.config(text="Zaznacz wiersz składnika do usunięcia.")
            return
        for r in reversed(rows):
            p["sklad"].pop(r)
        self._rysuj_sklad(p)
        self._odswiez_liste()

    def _wybierz_kartoteke(self, tytul):
        """Modalny wybór kartoteki z już wczytanej listy. Zwraca pozycję albo None."""
        dlg = tk.Toplevel(self)
        dlg.title(tytul)
        dlg.transient(self)
        dlg.grab_set()
        wynik = {}

        tk.Label(dlg, text=tytul, bg="#34495e", fg="white", font=("Arial", 10, "bold"),
                 anchor="w", padx=12, pady=8).pack(fill=tk.X)
        gora = tk.Frame(dlg, padx=10, pady=8)
        gora.pack(fill=tk.X)
        tk.Label(gora, text="Szukaj:", font=("Arial", 9)).pack(side=tk.LEFT)
        var = tk.StringVar()
        ent = tk.Entry(gora, textvariable=var, font=("Arial", 10))
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        lista = tk.Listbox(dlg, font=("Consolas", 9), height=16)
        lista.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 8))
        pasujace = []

        def odswiez(*_):
            szukaj = (var.get() or "").strip().lower()
            pasujace.clear()
            for p in self.pozycje:
                if (szukaj in p["Symbol"].lower() or szukaj in p["nazwa"].lower()):
                    pasujace.append(p)
                if len(pasujace) >= 300:      # lista ma pomagać wybrać, nie przewijać
                    break
            lista.delete(0, tk.END)
            for p in pasujace:
                lista.insert(tk.END, f"{_kod_rodzaju(p.get('Rodzaj')):<3} "
                                     f"{p['Symbol']:<16} {p['nazwa']}")
        var.trace_add("write", odswiez)
        odswiez()

        def wybierz(_e=None):
            sel = lista.curselection()
            if sel and sel[0] < len(pasujace):
                wynik["p"] = pasujace[sel[0]]
                dlg.destroy()
        lista.bind("<Double-Button-1>", wybierz)

        box = tk.Frame(dlg)
        box.pack(pady=(0, 10))
        tk.Button(box, text="Wybierz", command=wybierz, bg="#27ae60", fg="white",
                  font=("Arial", 9, "bold"), padx=14, pady=3).pack(side=tk.LEFT, padx=4)
        tk.Button(box, text="Anuluj", command=dlg.destroy, font=("Arial", 9),
                  padx=12, pady=3).pack(side=tk.LEFT, padx=4)

        ent.focus_set()
        wysrodkuj(dlg, self, 640, 480)
        self.wait_window(dlg)
        return wynik.get("p")

    # ── pozostałe akcje ────────────────────────────────────────────────────
    def _on_dblclick(self, event):
        """Dwuklik: komplet → skład na dole, reszta → karta pozycji."""
        if not self.sheet:
            return
        try:
            r = self.sheet.identify_row(event, allow_end=False)
        except Exception:
            return
        if r is None or not (0 <= r < len(self.widoczne)):
            return
        p = self.widoczne[r]
        if _czy_komplet(p):
            self._pokaz_sklad(p)
            return
        self._karta_pozycji([r])

    def _karta_pozycji(self, rows=None):
        if not self.sheet:
            return
        if rows is None:
            try:
                rows = sorted(self.sheet.get_selected_rows(get_cells_as_rows=True))
            except Exception:
                rows = []
        rows = [r for r in rows if 0 <= r < len(self.widoczne)]
        if not rows:
            return
        symbol = (self.widoczne[rows[0]].get("Symbol") or "").strip()
        if not symbol:
            return
        import subiekt_pozycja_gui
        subiekt_pozycja_gui.otworz(self, symbol)

    def _nowa_kartoteka(self):
        import subiekt_asortyment
        subiekt_asortyment.okno_nowa_kartoteka(
            self, po_zapisie=lambda _w: self._wczytaj_async())

    # ── zapis ──────────────────────────────────────────────────────────────
    def _zapisz(self):
        zmienione = [p for p in self.pozycje if self._zmieniona(p)]
        if not zmienione:
            return
        if self._zajete:
            self.status.config(text="Poczekaj — trwa inna operacja.")
            return

        opis = []
        for p in zmienione[:25]:
            czesci = []
            if p["nazwa"] != p["nazwa_subiekt"]:
                czesci.append(f"nazwa → „{p['nazwa']}”")
            if p["netto"] != p["netto_subiekt"]:
                czesci.append(f"netto {p['netto_subiekt']:.2f} → {p['netto']:.2f}")
            if p["sklad"] is not None and p["sklad"] != p["sklad_subiekt"]:
                czesci.append(f"skład ({len(p['sklad'])} skł.)")
            opis.append(f"  {p['Symbol']}: " + ", ".join(czesci))
        if len(zmienione) > 25:
            opis.append(f"  … i {len(zmienione) - 25} więcej")

        if not messagebox.askyesno(
                "Zapis do Subiekta",
                f"Baza PRODUKCYJNA.{NL}{NL}Do zapisania: {len(zmienione)} kartotek."
                f"{NL}{NL}" + NL.join(opis) +
                f"{NL}{NL}Zapisać?",
                parent=self, icon="warning"):
            return

        plan = []
        for p in zmienione:
            wpis = {"symbol": p["Symbol"]}
            if p["nazwa"] != p["nazwa_subiekt"]:
                wpis["nazwa"] = p["nazwa"]
            if p["netto"] != p["netto_subiekt"]:
                wpis["cena"] = p["netto"]
            if p["sklad"] is not None and p["sklad"] != p["sklad_subiekt"]:
                wpis["sklad"] = [{"symbol": s["Symbol"], "ilosc": s["Ilosc"]}
                                 for s in p["sklad"]]
            plan.append(wpis)

        self._zajete = True
        self.btn_zapisz.config(state=tk.DISABLED)
        self.start_kreciolek(f"Zapisuję {len(plan)} kartotek")
        threading.Thread(target=self._zapisz_worker, args=(plan,), daemon=True).start()

    def _zapisz_worker(self, plan):
        try:
            wynik = zapisz_kartoteki(plan, zapisz=True)
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._zapisz_done(None, err))
            return
        self.after(0, lambda: self._zapisz_done(wynik, None))

    def _zapisz_done(self, wynik, blad):
        self._zajete = False
        self.stop_kreciolek("")
        try:
            self.btn_zapisz.config(state=tk.NORMAL)
        except tk.TclError:
            return
        if blad:
            self.status.config(text="Błąd zapisu.")
            messagebox.showerror("Subiekt", blad, parent=self)
            return

        kroki = wynik.get("kroki") or []
        udane = {k["Symbol"].strip().upper() for k in kroki if k.get("Status") == "zmieniona"}
        bledy = [k for k in kroki if k.get("Status") in ("blad", "brak")]

        # Nowym punktem odniesienia stają się TYLKO pozycje faktycznie
        # zapisane. Kartoteka z błędem zostaje podświetlona jako zmieniona,
        # żeby nie wyglądało, że poszła — to ta sama zasada co przy „zapisano"
        # w mostach: raport ma mówić, co się UDAŁO.
        for p in self.pozycje:
            if p["Symbol"].strip().upper() not in udane:
                continue
            p["nazwa_subiekt"] = p["nazwa"]
            p["netto_subiekt"] = p["netto"]
            if p["sklad"] is not None:
                p["sklad_subiekt"] = [dict(s) for s in p["sklad"]]

        self._odswiez_liste()
        ile = wynik.get("zmienionych") or 0
        if bledy:
            szczegoly = NL.join(f"  {k['Symbol']}: {k.get('Szczegoly') or k['Status']}"
                                for k in bledy[:20])
            messagebox.showwarning(
                "Zapis częściowy",
                f"Zapisano: {ile}.{NL}Nie udało się: {len(bledy)}.{NL}{NL}{szczegoly}",
                parent=self)
        else:
            self.status.config(text=f"Zapisano {ile} kartotek.")
            messagebox.showinfo("Subiekt", f"Zapisano {ile} kartotek.", parent=self)


def open_window(parent):
    return AsortymentWindow(parent)
