# -*- coding: utf-8 -*-
"""Powiązanie rysunku z kartoteką PÓŁFABRYKATU, który kupujemy.

Detal często powstaje z gotowej, kupionej części: rysunek „Koło 5M_40 fi38"
to zakupione koło zębate 5M/40 + obróbka otworu Ø38. Konstruktor wie o tym
z rysunku i przypina półprodukt raz — logistyk i kalkulator korzystają
z tego w każdym następnym projekcie (POLPRODUKTY_PLAN.md).

Właścicielem kartoteki jest SUBIEKT, właścicielem relacji RM_BAZA: to wiedza
konstrukcyjna („z czego powstaje detal"), nie magazynowa. Relacja leży
w bazie mapowań na serwerze, więc działa globalnie, nie per projekt.

⚠️ Okno NIE pokazuje ceny ani stanu. Te dane zmieniają się co godzinę
i czyta się je na żywo tam, gdzie są potrzebne (kalkulator, ZK) — kopia
w oknie wyboru po dniu kłamie.
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox

import subiekt_mapowania as M
import subiekt_scalanie as S


#: Dłuższa lista i tak jest bezużyteczna — tak samo jak w wyszukiwarce
#: okna scalania, z której wzięty jest ten wzorzec.
LIMIT_TRAFIEN = 300


def _zl(x):
    """Cena ewidencyjna albo pusto. Zero tez pokazujemy — to informacja,
    ze kartoteka nie ma ustalonej ceny."""
    try:
        return ("%.2f" % float(x)).replace(".", ",")
    except (TypeError, ValueError):
        return ""


def _ilo(x):
    try:
        f = float(x)
        return str(int(f)) if f == int(f) else ("%.2f" % f).rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(x)


def _obszar_monitora(widget):
    """(lewo, gora, szer, wys) monitora, na ktorym stoi `widget`.

    Tk zna tylko pulpit wirtualny, wiec pytamy Windows o KONKRETNY ekran.
    `MONITOR_DEFAULTTONEAREST` (2) daje najblizszy monitor takze wtedy, gdy
    okno wystaje poza krawedz. Zwraca None, gdy sie nie uda — wolajacy ma
    wtedy wlasny wariant zapasowy.
    """
    try:
        import ctypes
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                        ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                        ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]

        hwnd = int(widget.winfo_id())
        user32 = ctypes.windll.user32
        # Uchwyt Tk wskazuje okno wewnetrzne — bierzemy okno najwyzszego
        # poziomu, inaczej monitor liczylby sie dla niewlasciwego prostokata.
        gora = user32.GetAncestor(hwnd, 2)          # GA_ROOT
        mon = user32.MonitorFromWindow(gora or hwnd, 2)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(mon, ctypes.byref(info)):
            return None
        # rcWork — bez paska zadan, zeby okno nie chowalo sie pod nim.
        r = info.rcWork
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)
    except Exception:
        return None


def _wysrodkuj(okno, rodzic, szer, wys):
    """Na SRODKU monitora, na ktorym stoi `rodzic`."""
    okno.update_idletasks()
    obszar = _obszar_monitora(rodzic if rodzic is not None else okno)
    if obszar:
        lewo, gora, mszer, mwys = obszar
    else:
        # Bez Win32: srodek pulpitu wirtualnego (moze byc kilka ekranow,
        # ale to i tak lepsze niz roznica wzgledem okna rodzica).
        try:
            lewo, gora = okno.winfo_vrootx(), okno.winfo_vrooty()
            mszer, mwys = okno.winfo_vrootwidth(), okno.winfo_vrootheight()
        except tk.TclError:
            lewo = gora = 0
            mszer, mwys = 1920, 1080
    x = lewo + (mszer - szer) // 2
    y = gora + (mwys - wys) // 2
    # Nie pozwalamy wyjsc poza monitor przy oknie wiekszym niz ekran.
    x = max(lewo, x)
    y = max(gora, y)
    okno.geometry("%dx%d+%d+%d" % (szer, wys, x, y))


class InfoPolproduktWindow(tk.Toplevel):
    """Wiersz JEST polproduktem — pokazujemy, z czego powstaje i gdzie leży.

    Do polproduktu nie dopina sie kolejnego polproduktu, wiec zamiast edycji
    dajemy podglad i przejscie do okna rysunku-rodzica. Uklad i kolory jak
    w oknie wiazania, zeby nie wygladalo jak systemowy komunikat bledu.
    """

    def __init__(self, parent, symbol, nazwa, gdzie, otworz_rysunek=None):
        super().__init__(parent)
        self._otworz_rysunek = otworz_rysunek
        self._rysunek = gdzie[0]["numer_rysunku"] if gdzie else None
        self._kartoteka = {}
        self._symbol = symbol
        self._nazwa = nazwa or symbol

        self.title("Półprodukt — %s" % symbol)
        self.transient(parent)
        self.configure(bg="#f7f9fa")
        _wysrodkuj(self, parent, 760, 430)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())

        # ── naglowek ─────────────────────────────────────────────────────
        gora = tk.Frame(self, bg="#eaf2f8")
        gora.pack(fill=tk.X)
        tk.Label(gora, text="\U0001F4E6", font=("Segoe UI Emoji", 22),
                 bg="#eaf2f8").pack(side=tk.LEFT, padx=(16, 10), pady=12)
        opis = tk.Frame(gora, bg="#eaf2f8")
        opis.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=12)
        tk.Label(opis, text=nazwa or symbol, font=("Arial", 12, "bold"),
                 bg="#eaf2f8", anchor="w").pack(fill=tk.X)
        tk.Label(opis, text="%s   ·   kupowany półfabrykat z Subiekta"
                            % symbol,
                 font=("Arial", 9), fg="#5d6d7e", bg="#eaf2f8",
                 anchor="w").pack(fill=tk.X)
        # Symbol przepisuje sie do Subiekta i do maili — niech da sie kliknac.
        tk.Button(gora, text="Kopiuj symbol", command=self._kopiuj_symbol,
                  font=("Arial", 8), padx=8).pack(side=tk.RIGHT, padx=(0, 14))
        tk.Frame(self, bg="#d5dbdb", height=1).pack(fill=tk.X)

        # ── z czego powstaje / gdzie uzywany ─────────────────────────────
        ramka = tk.LabelFrame(self, text=" Używany w rysunkach ",
                              font=("Arial", 9, "bold"), bg="#f7f9fa")
        ramka.pack(fill=tk.BOTH, expand=True, padx=14, pady=(12, 6))
        tab = ttk.Treeview(ramka, columns=("rysunek", "ile"),
                           show="headings", height=min(max(len(gdzie), 2), 6))
        tab.heading("rysunek", text="Numer rysunku")
        tab.heading("ile", text="Na 1 detal")
        tab.column("rysunek", width=380, anchor="w")
        tab.column("ile", width=100, anchor="e")
        for w in gdzie:
            tab.insert("", tk.END, values=(w["numer_rysunku"],
                                           w["ilosc_na_szt"]))
        tab.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self._tab = tab
        tab.configure(selectmode="extended")
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Kopiuj numer rysunku",
                         command=lambda: self._kopiuj_tabele(True))
        menu.add_command(label="Kopiuj numer i ilość",
                         command=lambda: self._kopiuj_tabele(False))
        menu.add_separator()
        menu.add_command(label="Kopiuj symbol półproduktu",
                         command=self._kopiuj_symbol)
        menu.add_command(label="Kopiuj symbol i nazwę",
                         command=lambda: self._do_schowka(
                             self._symbol + chr(9) + self._nazwa))

        def ppm(e):
            iid = tab.identify_row(e.y)
            if iid and iid not in tab.selection():
                tab.selection_set(iid)
            menu.tk_popup(e.x_root, e.y_root)

        tab.bind("<Button-3>", ppm)
        tab.bind("<Control-c>", lambda _e: self._kopiuj_tabele(False))
        tab.bind("<Control-C>", lambda _e: self._kopiuj_tabele(False))
        tab.bind("<Control-a>",
                 lambda _e: tab.selection_set(tab.get_children()))

        # ── dane z Subiekta ──────────────────────────────────────────────
        self.var_dane = tk.StringVar(value="Cena i stan: wczytuję…")
        tk.Label(self, textvariable=self.var_dane, font=("Arial", 9),
                 fg="#34495e", bg="#f7f9fa", anchor="w").pack(
                     fill=tk.X, padx=16)

        tk.Label(self,
                 text="Do półproduktu nie dopina się kolejnego półproduktu —\n"
                      "powiązania prowadzi się na RYSUNKU."
                      "          (Ctrl+C kopiuje, PPM = menu)",
                 font=("Arial", 9), fg="#7f8c8d", bg="#f7f9fa",
                 justify="left", anchor="w").pack(fill=tk.X, padx=16,
                                                  pady=(8, 0))

        # ── przyciski ────────────────────────────────────────────────────
        dol = tk.Frame(self, bg="#f7f9fa")
        dol.pack(fill=tk.X, padx=14, pady=12)
        tk.Button(dol, text="Zamknij", command=self.destroy,
                  font=("Arial", 9), padx=16, pady=4).pack(side=tk.RIGHT)
        if self._rysunek and callable(otworz_rysunek):
            tk.Button(dol, text="Otwórz rysunek %s" % self._rysunek,
                      command=self._przejdz, bg="#2980b9", fg="white",
                      font=("Arial", 9, "bold"), padx=14, pady=4).pack(
                          side=tk.RIGHT, padx=(0, 8))

        self._wczytaj_dane(symbol)

    def _do_schowka(self, tekst):
        if not tekst:
            return
        self.clipboard_clear()
        self.clipboard_append(tekst)
        self.var_dane.set("Skopiowano do schowka: %s"
                          % (tekst.replace(chr(9), "  ")[:70]))

    def _kopiuj_symbol(self):
        self._do_schowka(self._symbol)

    def _kopiuj_tabele(self, tylko_numer):
        wiersze = []
        for iid in (self._tab.selection() or self._tab.get_children()):
            v = self._tab.item(iid, "values")
            if not v:
                continue
            wiersze.append(str(v[0]) if tylko_numer
                           else (str(v[0]) + chr(9) + str(v[1])))
        self._do_schowka(chr(10).join(wiersze))

    def _przejdz(self):
        rysunek, akcja = self._rysunek, self._otworz_rysunek
        self.destroy()
        if callable(akcja):
            akcja(rysunek)

    def _wczytaj_dane(self, symbol):
        """Cena, stan i lokacja — w tle, jak w oknie wiazania."""
        def worker():
            try:
                import subiekt_bridge
                w = subiekt_bridge.call("magazyn", {}, timeout=200,
                                        write=False)
                k = next((p for p in (w.get("pozycje") or [])
                          if (p.get("Symbol") or "").strip().upper()
                          == symbol.strip().upper()), None)
            except Exception as e:
                print("Polprodukt (info): stany nieodczytane: %s" % e)
                return
            try:
                self.after(0, lambda: pokaz(k))
            except (RuntimeError, tk.TclError):
                pass

        def pokaz(k):
            try:
                if not k:
                    return self.var_dane.set("Nie znaleziono kartoteki "
                                             "w Subiekcie.")
                self.var_dane.set(
                    "Cena: %s zł     ·     Dostępne: %s     ·     "
                    "Zarezerwowane: %s     ·     Lokacja: %s"
                    % (_zl(k.get("CenaEwidencyjna")) or "—",
                       _ilo(k.get("Dostepne")), _ilo(k.get("Zarezerwowane")),
                       k.get("Polozenie") or "—"))
            except tk.TclError:
                pass

        threading.Thread(target=worker, daemon=True).start()


def okno_informacyjne(parent, symbol, nazwa, gdzie, otworz_rysunek=None):
    """Podglad wiersza, ktory SAM jest polproduktem."""
    return InfoPolproduktWindow(parent, symbol, nazwa, gdzie, otworz_rysunek)


class PolproduktWindow(tk.Toplevel):
    """Wyszukiwarka kartotek + lista już powiązanych półproduktów.

    `numer` to klucz relacji — numer rysunku, a dla pozycji znormalizowanej
    jej nazwa. Liczy go WOŁAJĄCY, tą samą regułą co reszta integracji
    (`COALESCE(work_drawing_no, norm_drawing_no, src_drawing_no, name)`),
    żeby ten sam detal nie miał tu innego klucza niż w pozostałych oknach.
    """

    def __init__(self, parent, numer, opis="", po_zmianie=None,
                 projekt_info=None):
        super().__init__(parent)
        self.numer = (numer or "").strip()
        # Wolane po KAZDEJ zmianie relacji — arkusz ma odswiezyc znacznik 🛒
        # w kolumnie Δ. Bez tego znacznik pojawia sie dopiero po recznym
        # odswiezeniu i user nie wie, czy powiazanie w ogole weszlo.
        self._po_zmianie = po_zmianie
        # Skad wziac projekt i jego pozycje do przeliczenia ZK. Callable,
        # bo arkusz moze w miedzyczasie przelaczyc projekt.
        self._projekt_info = projekt_info
        self._cos_zmienione = False
        # ⚠️ NIC NIE ZAPISUJE SIE SAMO (decyzja 14.09.2026). Zmiany czekaja
        # tutaj do „Zatwierdz zmiany": {id_subiekt: {...}} dla dopisania
        # i zmiany ilosci, zbior id do usuniecia. Do bazy ida jedna paczka,
        # wiec anulowanie naprawde nic nie zostawia.
        self._zmiany = {}
        self._do_usuniecia = set()
        # {SYMBOL: dane z trybu `magazyn`} — cena, stany, lokacja. Czytane
        # na zywo, nie przechowywane w relacji.
        self._kartoteki = {}
        self._katalog = []
        self._pobieranie = False

        self.title("Powiąż półprodukt — %s" % self.numer)
        self.transient(parent)
        _wysrodkuj(self, parent, 980, 640)
        self.protocol("WM_DELETE_WINDOW", self._zamknij)
        self.bind("<Escape>", lambda _e: self._zamknij())

        tk.Label(self, text="Rysunek:   %s" % self.numer,
                 font=("Arial", 10, "bold"), anchor="w").pack(
                     fill=tk.X, padx=12, pady=(12, 0))
        if opis:
            tk.Label(self, text=opis, font=("Arial", 8), fg="#555",
                     anchor="w").pack(fill=tk.X, padx=12)

        self._sekcja_powiazane()
        self._sekcja_szukania()

        self.status = tk.Label(self, text="", font=("Arial", 8), fg="#555",
                               anchor="w")
        self.status.pack(fill=tk.X, padx=12, pady=(0, 10))

        self._odswiez_powiazane()
        self._wczytaj_katalog()
        self._wczytaj_stany()
        # ⚠️ BEZ `grab_set()`: okno ma NIE blokowac arkusza glownego —
        # user chce rownolegle przegladac pozycje w RM_BAZA (14.09.2026).
        # `transient` zostaje, zeby okno trzymalo sie arkusza na pulpicie.
        self.ent_szukaj.focus_set()

    def _zamknij(self):
        """Zamknij i daj znac arkuszowi, jesli cokolwiek sie zmienilo."""
        # Niezapisany bufor nie moze zniknac po cichu — user ma go zatwierdzic
        # albo swiadomie porzucic.
        czeka = len(self._zmiany) + len(self._do_usuniecia)
        if czeka and not messagebox.askyesno(
                "Niezapisane zmiany",
                "Masz %d niezatwierdzonych zmian.\n\n"
                "Zamknąć okno i je PORZUCIĆ?" % czeka,
                icon="warning", default="no", parent=self):
            return
        if self._cos_zmienione and callable(self._po_zmianie):
            try:
                self._po_zmianie()
            except Exception:
                pass          # odswiezenie arkusza nie moze wywalic okna
        self.destroy()

    def _wczytaj_stany(self):
        """Cena i stany z Subiekta — w tle, zeby okno wstalo od razu.

        Tryb `magazyn` zwraca CALY katalog jednym zapytaniem (~0,1 s z
        cieplego mostu), wiec nie pytamy per symbol. Brak mostu = kolumny
        zostaja puste; relacji to nie dotyczy.
        """
        def worker():
            try:
                import subiekt_bridge
                w = subiekt_bridge.call("magazyn", {}, timeout=200, write=False)
                dane = {(p.get("Symbol") or "").strip().upper(): p
                        for p in (w.get("pozycje") or [])}
            except Exception as e:
                print("Polprodukt: stany z Subiekta nieodczytane: %s" % e)
                return
            try:
                self.after(0, lambda: gotowe(dane))
            except (RuntimeError, tk.TclError):
                pass          # okno zamkniete zanim most odpowiedzial

        def gotowe(dane):
            try:
                self._kartoteki = dane
                self._odswiez_powiazane()
                self._filtruj()          # dolna lista tez dostaje cene i stan
            except tk.TclError:
                pass                    # okno zamkniete w miedzyczasie

        threading.Thread(target=worker, daemon=True).start()

    # ── kopiowanie ───────────────────────────────────────────────────────
    def _kopiuj_z(self, tabela, tylko_symbol=False):
        """Zaznaczone wiersze do schowka: „SYMBOL<TAB>NAZWA" w wierszach.

        Treeview nie ma wlasnego kopiowania, a symbole kartotek przepisuje
        sie recznie do Subiekta i do maili — stad Ctrl+C i menu pod PPM.
        """
        wiersze = []
        for iid in tabela.selection():
            v = tabela.item(iid, "values")
            if not v:
                continue
            symbol = str(v[0])
            nazwa = str(v[1]).split("  ←")[0].strip() if len(v) > 1 else ""
            wiersze.append(symbol if tylko_symbol
                           else (symbol + chr(9) + nazwa).strip())
        if not wiersze:
            return
        self.clipboard_clear()
        self.clipboard_append(chr(10).join(wiersze))
        self.status.config(text="Skopiowano do schowka: %d wiersz(y)."
                                % len(wiersze))

    def _menu_kopiowania(self, tabela):
        """Ctrl+C, Ctrl+A i menu pod prawym przyciskiem — dla jednej listy."""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Kopiuj symbol",
                         command=lambda: self._kopiuj_z(tabela, True))
        menu.add_command(label="Kopiuj symbol i nazwę",
                         command=lambda: self._kopiuj_z(tabela))
        menu.add_separator()
        menu.add_command(label="Zaznacz wszystko",
                         command=lambda: tabela.selection_set(
                             tabela.get_children()))

        def pokaz(e):
            iid = tabela.identify_row(e.y)
            if iid and iid not in tabela.selection():
                tabela.selection_set(iid)
            menu.tk_popup(e.x_root, e.y_root)

        tabela.configure(selectmode="extended")
        tabela.bind("<Button-3>", pokaz)
        tabela.bind("<Control-c>", lambda _e: self._kopiuj_z(tabela))
        tabela.bind("<Control-C>", lambda _e: self._kopiuj_z(tabela))
        tabela.bind("<Control-a>",
                    lambda _e: tabela.selection_set(tabela.get_children()))

    # ── powiązane ────────────────────────────────────────────────────────
    def _sekcja_powiazane(self):
        ramka = tk.LabelFrame(self, text=" Z czego powstaje ten detal ",
                              font=("Arial", 9, "bold"))
        ramka.pack(fill=tk.X, padx=12, pady=(10, 6))

        self.tab_pow = ttk.Treeview(
            ramka, columns=("symbol", "nazwa", "ile", "cena", "stan",
                            "rezerw", "lokacja"),
            show="headings", height=4)
        # Cena i stany NIE sa przechowywane w relacji — czytamy je na zywo
        # z Subiekta (plan: „kopia po dniu klamie").
        for k, n, w, a in (("symbol", "Symbol", 150, "w"),
                           ("nazwa", "Nazwa", 260, "w"),
                           ("ile", "Na 1 detal", 70, "e"),
                           ("cena", "Cena", 80, "e"),
                           ("stan", "Dostępne", 75, "e"),
                           ("rezerw", "Rezerw.", 70, "e"),
                           ("lokacja", "Lokacja", 80, "w")):
            self.tab_pow.heading(k, text=n)
            self.tab_pow.column(k, width=w, anchor=a,
                                stretch=(k == "nazwa"))
        self.tab_pow.pack(side=tk.LEFT, fill=tk.X, expand=True,
                          padx=(8, 0), pady=8)
        self._menu_kopiowania(self.tab_pow)

        bok = tk.Frame(ramka)
        bok.pack(side=tk.RIGHT, fill=tk.Y, padx=8, pady=8)
        tk.Button(bok, text="Zmień ilość", command=self._zmien_ilosc,
                  font=("Arial", 9), width=14).pack(pady=(0, 4))
        tk.Button(bok, text="Usuń powiązanie", command=self._usun,
                  font=("Arial", 9), width=14).pack()
        # JEDYNE miejsce, w ktorym cokolwiek idzie do bazy i do Subiekta.
        self.btn_zatwierdz = tk.Button(
            bok, text="Zapisz", command=self._zatwierdz,
            bg="#27ae60", fg="white", font=("Arial", 9, "bold"),
            width=14, state=tk.DISABLED)
        self.btn_zatwierdz.pack(pady=(8, 0))

    def _odswiez_powiazane(self):
        self.tab_pow.delete(*self.tab_pow.get_children())
        try:
            wiersze = M.polprodukty(self.numer)
        except Exception as e:
            self.status.config(text="Nie odczytano powiązań: %s" % e)
            return
        # Widok = stan z bazy NALOZONY buforem niezapisanych zmian, zeby
        # user widzial to, co zatwierdzi, a nie to, co jest w bazie.
        laczne = {}
        for w in wiersze:
            laczne[w["id_subiekt"]] = {"symbol": w["symbol"] or "",
                                       "nazwa": w["nazwa"] or "",
                                       "ilosc": w["ilosc_na_szt"],
                                       "stan": ""}
        for id_sub, z in self._zmiany.items():
            stary = laczne.get(id_sub)
            laczne[id_sub] = {"symbol": z["symbol"], "nazwa": z["nazwa"],
                              "ilosc": z["ilosc"],
                              "stan": "zmiana" if stary else "nowy"}
        for id_sub in self._do_usuniecia:
            if id_sub in laczne:
                laczne[id_sub]["stan"] = "usuniecie"

        for id_sub, w in sorted(laczne.items()):
            znacznik = {"nowy": "  ← nowy", "zmiana": "  ← zmiana",
                        "usuniecie": "  ← do usunięcia"}.get(w["stan"], "")
            kart = self._kartoteki.get((w["symbol"] or "").strip().upper(), {})
            self.tab_pow.insert(
                "", tk.END, iid=str(id_sub),
                values=(w["symbol"] or "(id %s)" % id_sub,
                        (w["nazwa"] or "") + znacznik, w["ilosc"],
                        _zl(kart.get("CenaEwidencyjna")),
                        _ilo(kart.get("Dostepne")) if kart else "…",
                        _ilo(kart.get("Zarezerwowane")) if kart else "",
                        kart.get("Polozenie") or ""),
                tags=("czeka",) if w["stan"] else ())
        self.tab_pow.tag_configure("czeka", background="#fff3cd")

        czeka = len(self._zmiany) + len(self._do_usuniecia)
        self.btn_zatwierdz.config(
            state=tk.NORMAL if czeka else tk.DISABLED,
            text="Zapisz (%d)" % czeka if czeka else "Zapisz")
        self.status.config(
            text=("Niezapisanych zmian: %d — kliknij „Zatwierdź zmiany”."
                  % czeka).replace("Zatwierdź zmiany", "Zapisz") if czeka else
                 ("Powiązanych półproduktów: %d" % len(wiersze) if wiersze
                  else "Ten rysunek nie ma jeszcze półproduktu."))

    @staticmethod
    def _bez_znacznika(nazwa):
        """Nazwa bez „← nowy / ← zmiana / ← do usuniecia" z tabeli.

        Tabela dokleja te znaczniki do KOLUMNY NAZWA, zeby bylo widac
        niezapisane zmiany — ale do bazy ma isc czysta nazwa kartoteki.
        """
        return str(nazwa or "").split("  \u2190")[0].strip()

    def _zaznaczony(self):
        sel = self.tab_pow.selection()
        return int(sel[0]) if sel else None

    def _zmien_ilosc(self):
        id_sub = self._zaznaczony()
        if id_sub is None:
            return messagebox.showinfo(
                "Zmień ilość", "Zaznacz najpierw powiązany półprodukt.",
                parent=self)
        biezaca = self.tab_pow.item(str(id_sub), "values")
        ile = self._zapytaj_o_ilosc(int(biezaca[2]))
        if ile is None:
            return
        self._zmiany[id_sub] = {"symbol": biezaca[0],
                                "nazwa": self._bez_znacznika(biezaca[1]),
                                "ilosc": ile}
        self._do_usuniecia.discard(id_sub)
        self._odswiez_powiazane()
        self.status.config(
            text="Do zatwierdzenia: %s → %s szt. na 1 detal."
                 % (biezaca[0], ile))

    def _usun(self):
        id_sub = self._zaznaczony()
        if id_sub is None:
            return messagebox.showinfo(
                "Usuń powiązanie", "Zaznacz najpierw powiązany półprodukt.",
                parent=self)
        symbol = self.tab_pow.item(str(id_sub), "values")[0]
        # Kasujemy TYLKO relację. Kartoteka w Subiekcie zostaje nietknięta —
        # to zwykły towar, żyjący własnym życiem jak łożysko czy pasek.
        if not messagebox.askyesno(
                "Usuń powiązanie",
                "Usunąć powiązanie rysunku %s z kartoteką %s?\n\n"
                "Kartoteka w Subiekcie zostaje bez zmian — znika tylko\n"
                "informacja, że ten detal powstaje z kupionego półproduktu."
                % (self.numer, symbol), parent=self):
            return
        self._do_usuniecia.add(id_sub)
        self._zmiany.pop(id_sub, None)
        self._odswiez_powiazane()
        self.status.config(text="Do zatwierdzenia: usunięcie %s." % symbol)

    def _zatwierdz(self):
        """Zapisuje CALY bufor: relacje do bazy, potem pyta o ZK.

        Do 14.09.2026 kazdy przycisk pisal do bazy od razu — user nie mial
        jak sie rozmyslic. Teraz zapis jest jeden i jawny.
        """
        if not self._zmiany and not self._do_usuniecia:
            return
        opis = []
        for id_sub, z in sorted(self._zmiany.items()):
            opis.append("    %s — %s szt. na 1 detal"
                        % (z["symbol"], _ilo(z["ilosc"])))
        for id_sub in sorted(self._do_usuniecia):
            wiersz = self.tab_pow.item(str(id_sub), "values")
            opis.append("    USUNIĘCIE: %s" % (wiersz[0] if wiersz else id_sub))
        if not messagebox.askyesno(
                "Zapisz powiązania",
                ("Rysunek %s:@N@@N@%s@N@@N@"
                 "Zapis: powiązania → wiersze w arkuszu → ilości na ZK."
                 % (self.numer, chr(10).join(opis))).replace("@N@", chr(10)),
                parent=self):
            return

        try:
            for id_sub, z in self._zmiany.items():
                M.zapisz_polprodukt(self.numer, id_sub, z["ilosc"],
                                    symbol=z["symbol"], nazwa=z["nazwa"])
            # Symbole ODWIAZYWANYCH polproduktow — po `usun_polprodukt` nie
            # bedzie juz skad ich wziac, a trzeba je zdjac z ZK (patrz
            # _zdejmij_z_zk_po_odwiazaniu).
            try:
                _przed = {w["id_subiekt"]: (w["symbol"] or "").strip()
                          for w in M.polprodukty(self.numer)}
            except Exception:
                _przed = {}
            _odwiazane = [_przed[i] for i in self._do_usuniecia if _przed.get(i)]
            for id_sub in self._do_usuniecia:
                M.usun_polprodukt(self.numer, id_sub)
        except Exception as e:
            return messagebox.showerror("Zatwierdź zmiany", str(e), parent=self)

        ile = len(self._zmiany) + len(self._do_usuniecia)
        # Czy zapis COS DODAL/ZMIENIL? Same odwiazania nie maja czego
        # ustawiac na ZK ani rozsylac do innych projektow — a pytanie
        # „Dopisac polprodukt na ICH ZK?" i tak wyskakiwalo (26.09.2026).
        _bylo_dodane = bool(self._zmiany)
        self._zmiany, self._do_usuniecia = {}, set()
        self._cos_zmienione = True
        self._odswiez_powiazane()
        self.status.config(text="Zapisano %d zmian(y)." % ile)

        # Reszta procedury bez dopytywania: user juz raz potwierdzil zapis.
        # Wiersze w arkuszu dopisuje `po_zmianie` (arkusz ma lock), potem ZK.
        if callable(self._po_zmianie):
            try:
                self._po_zmianie()
                self._cos_zmienione = False     # arkusz juz odswiezony
            except Exception:
                pass
        if _bylo_dodane:
            self._na_zk(po_zapisie=True)
        self._zdejmij_z_zk_po_odwiazaniu(_odwiazane)
        self._zdejmij_z_innych_projektow(_odwiazane)
        if _bylo_dodane:
            self._rozeslij_do_projektow()

    def _zdejmij_z_zk_po_odwiazaniu(self, symbole):
        """Odwiazany polprodukt schodzi TAKZE z ZK — inaczej wraca do arkusza.

        `_na_zk` tylko USTAWIA ilosci biezacych polproduktow; pozycji, ktorej
        relacja wlasnie zniknela, nigdy nie zdejmowal. Zostawala na ZK
        w Subiekcie, a arkusz przy nastepnym locku sciagal ja z powrotem
        jako „z zamowienia ZK" (`_dopisz_pozycje_z_zk`) — user odwiazywal,
        a wiersz „nie chcial sie skasowac" (zgloszone 26.09.2026, T5-525/10).

        Zdejmujemy WYLACZNIE symbole, ktorych NIE potrzebuje juz zaden inny
        rysunek w projekcie (relacja jest globalna — to samo kolo moze byc
        polproduktem trzech rysunkow). Bezpiecznik mostu jak wszedzie:
        pozycja, ktora poszla na ZD, zostaje (status „realizowana").
        """
        symbole = [s for s in (symbole or []) if s]
        if not symbole or not callable(self._projekt_info):
            return
        dane = self._projekt_info() or {}
        pid, pnazwa = dane.get("project_id"), dane.get("project_name")
        if not pid:
            return
        try:
            import subiekt_projekt as PR
            import subiekt_bridge
            potrzebne = {(p.get("symbol") or "").strip().upper()
                         for p in PR.pozycje_polproduktow(dane.get("pozycje") or [])}
        except Exception as e:
            messagebox.showwarning(
                "Zdjęcie z ZK",
                "Nie sprawdzono, czy odwiązany półprodukt jest jeszcze potrzebny:\n%s\n\n"
                "Pozycja została na ZK — zdejmij ją z arkusza przez PPM → "
                "„Zdejmij z ZK (Subiekt)…”." % e, parent=self)
            return
        do_zdjecia = [s for s in symbole if s.strip().upper() not in potrzebne]
        if not do_zdjecia:
            return                      # inny rysunek nadal go uzywa — zostaje
        plan = {"projekt": PR.numer_projektu(pnazwa, pid), "symbole": do_zdjecia}
        self.config(cursor="watch")
        self.status.config(text="Zdejmuję odwiązane półprodukty z ZK…")
        self.update_idletasks()
        try:
            wynik = subiekt_bridge.call("zk-poz-usun", {"plan": plan, "zapisz": True},
                                        timeout=PR.TIMEOUT_S, write=True)
        except Exception as e:
            self.config(cursor="")
            messagebox.showwarning(
                "Zdjęcie z ZK",
                "Most nie zdjął pozycji z ZK:\n%s\n\nZostały na dokumencie: %s\n"
                "Zdejmij je z arkusza przez PPM → „Zdejmij z ZK (Subiekt)…”."
                % (e, ", ".join(do_zdjecia)), parent=self)
            return
        self.config(cursor="")
        kroki = (wynik or {}).get("kroki", [])
        zapisane = next((k for k in kroki if k.get("Status") == "zapisane"), None)
        nieusuwalne = [k for k in kroki if k.get("Status") == "nie-do-usuniecia"]
        realizowane = [k for k in kroki if k.get("Status") == "realizowana"]
        czesci = []
        if zapisane:
            czesci.append("✓ " + (zapisane.get("Szczegoly") or "zdjęto z ZK: " + ", ".join(do_zdjecia)))
        if nieusuwalne:
            czesci.append("⚠ ZOSTAŁY NA ZK — usuń ręcznie w Subiekcie: "
                          + ", ".join(k.get("Symbol", "") for k in nieusuwalne))
        if realizowane:
            czesci.append("⚠ NIE usunięto — są już na ZD: "
                          + ", ".join("%s → %s" % (k.get("Symbol", ""), k.get("Szczegoly", ""))
                                      for k in realizowane))
        if not czesci:
            czesci.append("Odwiązanych pozycji nie było na ZK.")
        self.status.config(text="Odwiązane półprodukty: " + czesci[0][:70])
        messagebox.showinfo("Odwiązanie — ZK", "\n".join(czesci), parent=self)
        # Wiersz „z zamowienia ZK" w arkuszu ma znacznik zasiewu, ktory wlasnie
        # przestal byc prawdziwy — arkusz odswiezy go sam przy najblizszym
        # przeliczeniu z ZK; do reki jest PPM -> „Zdejmij z ZK" + „Usun wiersz".
        if callable(self._po_zmianie):
            try:
                self._po_zmianie()
            except Exception:
                pass

    def _zdejmij_z_innych_projektow(self, symbole):
        """Lustrzane odbicie rozsylu: odwiazany polprodukt schodzi z ZK
        POZOSTALYCH projektow z tym rysunkiem.

        Rozsyl („Dopisac polprodukt na ICH ZK?") zaklada pozycje — a nawet
        cale ZK — w innych projektach, ale nie mial drogi powrotnej.
        Po odwiazaniu polprodukt znikal z biezacego projektu, a w tamtych
        zostawal na dokumentach (26.09.2026: T5-525/10 na ZK 3/09/2026
        i ZK 4/09/2026, zalozonych tego dnia przez rozsyl).

        Zdejmujemy tylko tam, gdzie po odwiazaniu ZADEN rysunek projektu
        nie potrzebuje juz tego symbolu (plan polproduktow liczony tak samo,
        jak przy rozsylaniu). Pytamy przed, raportujemy po; pozycje na ZD
        most zostawia (status „realizowana").
        """
        symbole = [s for s in (symbole or []) if s]
        if not symbole:
            return
        try:
            import subiekt_polprodukt_rozsyl as R
            import subiekt_projekt as PR
            import subiekt_bridge
        except Exception as e:
            print("Polprodukty: zdjecie z innych projektow niedostepne (%s)" % e)
            return
        dane = self._projekt_info() if callable(self._projekt_info) else {}
        biezacy = (dane or {}).get("project_id")
        podmiot = (dane or {}).get("podmiot") or ""
        try:
            projekty = [g for g in R.projekty_z_rysunkiem(self.numer)
                        if g[0] != biezacy]
        except Exception as e:
            print("Polprodukty: nie sprawdzono projektow (%s)" % e)
            return
        if not projekty:
            return

        # Gdzie symbol jest jeszcze potrzebny (inny rysunek go uzywa)?
        # Tam NIE ruszamy. Reszta -> kandydaci do zdjecia.
        kandydaci = []
        szukane = {x.strip().upper() for x in symbole}
        for pid, nazwa, _ile in projekty:
            try:
                plan, pozycje = R.plan_polproduktow(pid, nazwa, podmiot)
                potrzebne = {(p.get("symbol") or "").strip().upper()
                             for p in (pozycje or [])}
            except Exception:
                potrzebne = set()
            zbedne = sorted(szukane - potrzebne)
            if zbedne:
                kandydaci.append((pid, nazwa, zbedne))
        if not kandydaci:
            return

        lista = chr(10).join("    %s:  %s" % (n, ", ".join(z))
                             for _p, n, z in kandydaci[:12])
        wiecej = (chr(10) + "    … i %d dalszych" % (len(kandydaci) - 12)
                  if len(kandydaci) > 12 else "")
        if not messagebox.askyesno(
                "Odwiązany półprodukt jest na ZK innych projektów",
                "Rysunek „%s” występuje w %d innych projektach, a odwiązany\n"
                "półprodukt nie jest tam już potrzebny:@N@@N@%s%s@N@@N@"
                "Zdjąć go z ICH ZK teraz?@N@@N@"
                "(Pozycje, które poszły już na ZD, most zostawi i powie o tym.)"
                .replace("@N@", chr(10))
                % (self.numer, len(kandydaci), lista, wiecej),
                parent=self):
            return

        self.config(cursor="watch")
        self.status.config(text="Zdejmuję z ZK pozostałych projektów…")
        self.update_idletasks()
        raport = []
        for pid, nazwa, zbedne in kandydaci:
            plan = {"projekt": PR.numer_projektu(nazwa, pid), "symbole": zbedne}
            try:
                w = subiekt_bridge.call("zk-poz-usun", {"plan": plan, "zapisz": True},
                                        timeout=PR.TIMEOUT_S, write=True)
            except Exception as e:
                raport.append("⚠ %s: most nie wykonał (%s)" % (nazwa, e))
                continue
            kroki = (w or {}).get("kroki", [])
            zap = next((k for k in kroki if k.get("Status") == "zapisane"), None)
            real = [k.get("Symbol", "") for k in kroki if k.get("Status") == "realizowana"]
            brak = [k for k in kroki if k.get("Status") in ("brak", "brak-na-zk")]
            if zap:
                raport.append("✓ %s: %s" % (nazwa, zap.get("Szczegoly") or "zdjęto"))
            elif real:
                raport.append("⚠ %s: na ZD, zostaje: %s" % (nazwa, ", ".join(real)))
            elif brak and len(brak) == len(kroki):
                raport.append("· %s: nie było na ZK" % nazwa)
            else:
                raport.append("· %s: bez zmian" % nazwa)
        self.config(cursor="")
        self.status.config(text="Zdjęto z ZK innych projektów: %d" % len(kandydaci))
        messagebox.showinfo("Odwiązanie — inne projekty", chr(10).join(raport), parent=self)

    def _rozeslij_do_projektow(self):
        """Dopisuje polprodukt na ZK POZOSTALYCH aktywnych projektow.

        Relacja jest globalna, wiec dotyczy kazdego projektu z tym rysunkiem.
        Bez tego trzeba bylo otwierac Projekt/Aktualizacja osobno dla kazdego
        (15.09.2026).

        ⚠️ Piszemy takze do projektow, ktore ktos trzyma na locku — ZK zyje
        w Subiekcie, nie w bazie projektu, a arkusz zaciagnie pozycje sam
        przy najblizszym przejeciu locka. To decyzja uzytkownika.
        """
        try:
            import subiekt_polprodukt_rozsyl as R
        except Exception as e:
            print("Polprodukty: rozsylka niedostepna (%s)" % e)
            return

        dane = self._projekt_info() if callable(self._projekt_info) else {}
        biezacy = (dane or {}).get("project_id")
        try:
            gdzie = [g for g in R.projekty_z_rysunkiem(self.numer)
                     if g[0] != biezacy]
        except Exception as e:
            print("Polprodukty: nie sprawdzono projektow (%s)" % e)
            return
        if not gdzie:
            return

        lista = chr(10).join("    %s  (%g szt.)" % (n, ile)
                             for _p, n, ile in gdzie[:12])
        wiecej = (chr(10) + "    … i %d dalszych" % (len(gdzie) - 12)
                  if len(gdzie) > 12 else "")
        if not messagebox.askyesno(
                "Ten rysunek jest w innych projektach",
                "„%s” występuje jeszcze w %d aktywnych projektach:@N@@N@%s%s@N@@N@"
                "Dopisać półprodukt na ICH ZK teraz?@N@@N@"
                "(Bez tego trzeba otworzyć każdy projekt osobno przez "
                "Projekt / Aktualizacja.)".replace("@N@", chr(10))
                % (self.numer, len(gdzie), lista, wiecej),
                parent=self):
            return

        self.config(cursor="watch")
        self.status.config(text="Dopisuję na ZK pozostałych projektów…")
        self.update_idletasks()
        try:
            wynik = R.rozeslij(self.numer, podmiot=(dane or {}).get("podmiot") or "",
                               pomin_projekt=biezacy, zapisz=True)
        except Exception as e:
            self.config(cursor="")
            return messagebox.showerror("Dopisywanie na ZK", str(e), parent=self)
        self.config(cursor="")

        # NIC PO CICHU: raport z tego, co powstalo w kazdym projekcie.
        ok = [(n, o) for _p, n, o, b in wynik if not b]
        zle = [(n, b) for _p, n, o, b in wynik if b]
        czesci = []
        if ok:
            czesci.append("ZAPISANE (%d):@N@    %s" % (
                len(ok), (chr(10) + "    ").join("%s — %s" % x for x in ok)))
        if zle:
            czesci.append("NIE UDAŁO SIĘ (%d):@N@    %s" % (
                len(zle), (chr(10) + "    ").join("%s — %s" % x for x in zle)))
        messagebox.showinfo(
            "Dopisano na ZK",
            (chr(10) + chr(10)).join(czesci).replace("@N@", chr(10))
            or "Nic nie wymagało zmian.", parent=self)

    def _na_zk(self, po_zapisie=False):
        """Przelicza polprodukty projektu i ustawia ich ilosci na ZK.

        `po_zapisie=True` — wolane w ciagu „Zapisz", wiec bez wlasnego
        pytania: uzytkownik potwierdzil juz cala procedure.

        Most ustawia ilosc WPROST (`UstawIlosc`), wiec dziala w gore i w dol:
        zmiana „na 1 detal" z 1 na 11 podnosi pozycje na dokumencie, a powrot
        do 1 ja obniza. Wysylamy TYLKO polprodukty — reszty planu nie ruszamy,
        zeby przycisk w tym oknie nie robil cichego zapisu calego projektu.
        """
        if not callable(self._projekt_info):
            return messagebox.showinfo(
                "Zapisz na ZK",
                "To okno nie zna projektu — otwórz je z arkusza (PPM na "
                "pozycji).", parent=self)
        dane = self._projekt_info() or {}
        pid, pnazwa = dane.get("project_id"), dane.get("project_name")
        if not pid or not pnazwa:
            return messagebox.showinfo(
                "Zapisz na ZK", "Najpierw wybierz projekt w arkuszu.",
                parent=self)

        try:
            import subiekt_projekt as PR
            pozycje = dane.get("pozycje") or []
            polprodukty = PR.pozycje_polproduktow(pozycje)
        except Exception as e:
            return messagebox.showerror("Zapisz na ZK", str(e), parent=self)
        if not polprodukty:
            return messagebox.showinfo(
                "Zapisz na ZK",
                "Nie ma czego zapisać: żadna pozycja tego projektu nie ma "
                "powiązanego półproduktu.", parent=self)

        opis = chr(10).join("    %s — %s szt." % (p["symbol"], _ilo(p["ilosc"]))
                            for p in polprodukty)
        if not po_zapisie and not messagebox.askyesno(
                "Zapisz na ZK",
                "Na zamówieniu projektu %s zostaną USTAWIONE ilości:@NL@@NL@"
                "%s@NL@@NL@"
                "Ilość jest ustawiana wprost — także w dół, gdy zmniejszyłeś "
                "„na 1 detal”.@NL@Pozostałych pozycji ZK to nie dotyka.@NL@@NL@"
                "Zapisać?".replace("@NL@", chr(10)) % (pnazwa, opis),
                parent=self):
            return

        self.config(cursor="watch")
        self.status.config(text="Zapisuję na ZK…")
        self.update_idletasks()
        try:
            plan = PR.build_plan(pid, pnazwa, dane.get("podmiot") or "",
                                 pnazwa)[0]
            mini = dict(plan)
            mini["pozycje"] = [p for p in plan["pozycje"]
                               if p.get("polprodukt_dla")]
            wynik = PR.run_bridge(mini, zapisz=True)
        except Exception as e:
            self.config(cursor="")
            self.status.config(text="Nie zapisano.")
            return messagebox.showerror("Zapisz na ZK", str(e), parent=self)
        self.config(cursor="")

        blad = (wynik or {}).get("blad")
        if blad:
            self.status.config(text="Subiekt odmówił.")
            return messagebox.showerror("Zapisz na ZK", str(blad), parent=self)

        # NIC PO CICHU: raport z tego, co most naprawde zrobil.
        linie = ["%s — %s" % (k.get("Symbol"), k.get("Szczegoly")
                              or k.get("Status"))
                 for k in (wynik.get("kroki") or [])
                 if k.get("Rodzaj") in ("zk-poz", "zk")]
        self.status.config(text="Zapisano na ZK.")
        messagebox.showinfo(
            "Zapisano na ZK",
            (chr(10).join(linie) if linie else "Brak zmian na dokumencie."),
            parent=self)

    # ── wyszukiwarka ─────────────────────────────────────────────────────
    def _sekcja_szukania(self):
        ramka = tk.LabelFrame(self, text=" Wskaż kartotekę półproduktu ",
                              font=("Arial", 9, "bold"))
        ramka.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 6))

        tk.Label(ramka,
                 text="Wpisz fragment symbolu albo nazwy — lista zawęża się "
                      "na bieżąco.",
                 font=("Arial", 8), fg="#555", anchor="w").pack(
                     fill=tk.X, padx=8, pady=(6, 2))

        self.var_szukaj = tk.StringVar(value=self.numer)
        self.ent_szukaj = tk.Entry(ramka, textvariable=self.var_szukaj,
                                   font=("Consolas", 10))
        self.ent_szukaj.pack(fill=tk.X, padx=8, pady=(0, 6), ipady=3)

        # Dół przypięty PRZED listą — inaczej rozciągająca się lista spycha
        # przyciski poza okno (ta sama pułapka co w oknie scalania).
        dol = tk.Frame(ramka)
        dol.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(4, 8))
        self.info = tk.Label(ramka, text="", font=("Arial", 8), fg="#555",
                             anchor="w")
        self.info.pack(side=tk.BOTTOM, fill=tk.X, padx=8)

        wnetrze = tk.Frame(ramka)
        wnetrze.pack(fill=tk.BOTH, expand=True, padx=8)
        self.lista = ttk.Treeview(
            wnetrze, columns=("symbol", "nazwa", "cena", "stan", "rezerw",
                              "lokacja"),
            show="headings", height=9)
        # Te same dane co w tabeli powiazanych — cena i stan sa potrzebne
        # WLASNIE przy wyborze kartoteki, nie dopiero po powiazaniu.
        for k, n, w, a in (("symbol", "Symbol", 150, "w"),
                           ("nazwa", "Nazwa", 300, "w"),
                           ("cena", "Cena", 80, "e"),
                           ("stan", "Dostępne", 75, "e"),
                           ("rezerw", "Rezerw.", 70, "e"),
                           ("lokacja", "Lokacja", 80, "w")):
            self.lista.heading(k, text=n)
            self.lista.column(k, width=w, anchor=a, stretch=(k == "nazwa"))
        vs = ttk.Scrollbar(wnetrze, orient="vertical",
                           command=self.lista.yview)
        self.lista.configure(yscrollcommand=vs.set)
        self.lista.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)
        self._menu_kopiowania(self.lista)

        tk.Label(dol, text="Ile sztuk na 1 detal:",
                 font=("Arial", 9)).pack(side=tk.LEFT)
        self.var_ile = tk.StringVar(value="1")
        tk.Spinbox(dol, textvariable=self.var_ile, from_=1, to=9999, width=6,
                   font=("Arial", 10), justify="center").pack(
                       side=tk.LEFT, padx=(6, 0))
        tk.Label(dol, text="(sztuki całkowite)   ·   Ctrl+C kopiuje "
                            "zaznaczone, PPM = menu",
                 font=("Arial", 8), fg="#555").pack(side=tk.LEFT, padx=(6, 0))
        tk.Button(dol, text="Powiąż ten półprodukt", command=self._powiaz,
                  bg="#2980b9", fg="white", font=("Arial", 9, "bold"),
                  padx=12, pady=4).pack(side=tk.RIGHT)

        self.var_szukaj.trace_add("write", self._filtruj)
        self.lista.bind("<Double-1>", lambda _e: self._powiaz())

    def _wczytaj_katalog(self):
        """Cache z dysku od razu; gdy pusty — most, w tle."""
        try:
            self._katalog = S.wczytaj_katalog_subiekta(tylko_cache=True) or []
        except Exception:
            self._katalog = []
        if self._katalog:
            self._filtruj()
            return

        self._pobieranie = True
        self.info.config(text="Pobieram kartoteki z Subiekta…")
        self.config(cursor="watch")

        def worker():
            try:
                katalog = S.wczytaj_katalog_subiekta()
                self.after(0, lambda: gotowe(katalog, None))
            except Exception as e:
                blad = str(e)
                self.after(0, lambda: gotowe(None, blad))

        def gotowe(katalog, blad):
            self._pobieranie = False
            try:
                self.config(cursor="")
            except tk.TclError:
                return                      # okno zamknięte w międzyczasie
            if blad:
                self.info.config(text="Subiekt niedostępny.")
                messagebox.showerror(
                    "Powiąż półprodukt",
                    "Nie udało się pobrać kartotek z Subiekta:\n\n%s" % blad,
                    parent=self)
                return
            self._katalog = katalog or []
            self._filtruj()

        threading.Thread(target=worker, daemon=True).start()

    def _filtruj(self, *_a):
        fraza = S.norm_kod(self.var_szukaj.get())
        self.lista.delete(*self.lista.get_children())
        trafienia = []
        for poz in self._katalog:
            if not fraza or (fraza in S.norm_kod(poz["symbol"])
                             or fraza in S.norm_kod(poz["nazwa"])):
                trafienia.append(poz)
            if len(trafienia) >= LIMIT_TRAFIEN:
                break
        for poz in trafienia:
            kart = self._kartoteki.get((poz["symbol"] or "").strip().upper(), {})
            self.lista.insert(
                "", tk.END, iid=str(poz["id"]),
                values=(poz["symbol"], poz["nazwa"],
                        _zl(kart.get("CenaEwidencyjna")),
                        _ilo(kart.get("Dostepne")) if kart else "",
                        _ilo(kart.get("Zarezerwowane")) if kart else "",
                        kart.get("Polozenie") or ""))
        self.info.config(
            text="Pasujących kartotek: %d%s"
                 % (len(trafienia),
                    "  (pokazano pierwsze %d)" % LIMIT_TRAFIEN
                    if len(trafienia) >= LIMIT_TRAFIEN else ""))

    def _zapytaj_o_ilosc(self, domyslna=1):
        """Małe okno na liczbę sztuk. None = anulowano."""
        dlg = tk.Toplevel(self)
        dlg.title("Ilość na 1 detal")
        dlg.transient(self)
        dlg.resizable(False, False)
        wynik = {"ile": None}
        tk.Label(dlg, text="Ile sztuk półproduktu na 1 detal?",
                 font=("Arial", 9)).pack(padx=20, pady=(16, 6))
        var = tk.StringVar(value=str(domyslna))
        pole = tk.Spinbox(dlg, textvariable=var, from_=1, to=9999, width=8,
                          font=("Arial", 14), justify="center")
        pole.pack(pady=(0, 4))
        tk.Label(dlg, text="sztuki całkowite — „sztuka to sztuka”",
                 font=("Arial", 8), fg="#555").pack(padx=20)

        def zapisz():
            try:
                ile = int(float(var.get()))
            except ValueError:
                return messagebox.showwarning(
                    "Ilość", "Podaj liczbę sztuk.", parent=dlg)
            if ile < 1:
                return messagebox.showwarning(
                    "Ilość", "Ilość musi być większa od zera.", parent=dlg)
            wynik["ile"] = ile
            dlg.destroy()

        przyciski = tk.Frame(dlg)
        przyciski.pack(pady=(8, 14))
        tk.Button(przyciski, text="OK", command=zapisz, bg="#27ae60",
                  fg="white", font=("Arial", 9, "bold"), padx=18).pack(
                      side=tk.LEFT, padx=4)
        tk.Button(przyciski, text="Anuluj", command=dlg.destroy,
                  font=("Arial", 9), padx=12).pack(side=tk.LEFT, padx=4)
        dlg.bind("<Return>", lambda _e: zapisz())
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        _wysrodkuj(dlg, self, 320, 190)
        pole.focus_set()
        pole.selection_range(0, tk.END)
        dlg.grab_set()
        self.wait_window(dlg)
        return wynik["ile"]

    def _powiaz(self):
        sel = self.lista.selection()
        if not sel:
            # ⚠️ W oknie sa DWIE listy. Gorna to juz powiazane, dolna to
            # wyszukiwarka — komunikat musi mowic, ktora (14.09.2026: user
            # mial zaznaczony wiersz w gornej i nie wiedzial, czego okno chce).
            return messagebox.showinfo(
                "Powiąż półprodukt",
                "Zaznacz kartotekę na DOLNEJ liście "
                "(„Wskaż kartotekę półproduktu”).@NL@@NL@"
                "Górna tabela pokazuje to, co już jest powiązane."
                .replace("@NL@", chr(10)), parent=self)
        poz = next((k for k in self._katalog if str(k["id"]) == sel[0]), None)
        if not poz:
            return
        try:
            ile = int(float(self.var_ile.get() or 1))
        except ValueError:
            ile = 0
        if ile < 1:
            return messagebox.showwarning(
                "Powiąż półprodukt",
                "Ilość na 1 detal musi być liczbą całkowitą większą od zera.",
                parent=self)

        # Powiązanie rysunku z samym sobą nie ma sensu i zapętliłoby
        # liczenie zapotrzebowania.
        if S.norm_kod(poz["symbol"]) == S.norm_kod(self.numer):
            return messagebox.showwarning(
                "Powiąż półprodukt",
                "To jest kartoteka TEGO SAMEGO detalu.\n\n"
                "Półprodukt to inna kartoteka — gotowa część, którą kupujesz\n"
                "i dopiero obrabiasz.", parent=self)

        self._zmiany[poz["id"]] = {"symbol": poz["symbol"],
                                   "nazwa": poz["nazwa"], "ilosc": ile}
        self._do_usuniecia.discard(poz["id"])
        self._odswiez_powiazane()
        self.status.config(
            text="Do zatwierdzenia: %s x %d szt. — kliknij „Zatwierdź zmiany”."
                 % (poz["symbol"], ile))


def otworz(parent, numer, opis="", po_zmianie=None, projekt_info=None):
    """Okno powiązania półproduktu. `numer` = klucz relacji (numer/nazwa).

    `po_zmianie` — wołane przy zamknięciu, gdy cokolwiek się zmieniło;
    arkusz odświeża wtedy znacznik 🛒 w kolumnie Δ.
    """
    if not (numer or "").strip():
        messagebox.showinfo("Powiąż półprodukt",
                            "Ta pozycja nie ma numeru ani nazwy.",
                            parent=parent)
        return None
    return PolproduktWindow(parent, numer, opis, po_zmianie, projekt_info)
