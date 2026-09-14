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


def _wysrodkuj(okno, rodzic, szer, wys):
    okno.update_idletasks()
    try:
        x = rodzic.winfo_rootx() + (rodzic.winfo_width() - szer) // 2
        y = rodzic.winfo_rooty() + (rodzic.winfo_height() - wys) // 3
    except tk.TclError:
        x = y = 200
    okno.geometry("%dx%d+%d+%d" % (szer, wys, max(0, x), max(0, y)))


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
        self._zmiany[id_sub] = {"symbol": biezaca[0], "nazwa": biezaca[1],
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
            for id_sub in self._do_usuniecia:
                M.usun_polprodukt(self.numer, id_sub)
        except Exception as e:
            return messagebox.showerror("Zatwierdź zmiany", str(e), parent=self)

        ile = len(self._zmiany) + len(self._do_usuniecia)
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
        self._na_zk(po_zapisie=True)

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
        self.lista = ttk.Treeview(wnetrze, columns=("symbol", "nazwa"),
                                  show="headings", height=9)
        self.lista.heading("symbol", text="Symbol")
        self.lista.heading("nazwa", text="Nazwa")
        self.lista.column("symbol", width=170, stretch=False)
        self.lista.column("nazwa", width=420)
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
            self.lista.insert("", tk.END, iid=str(poz["id"]),
                              values=(poz["symbol"], poz["nazwa"]))
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
