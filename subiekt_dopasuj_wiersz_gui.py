# -*- coding: utf-8 -*-
"""
Okno „Dopasuj kartotekę Subiekta" dla JEDNEGO wiersza arkusza.

Wołane z menu prawego klawisza w arkuszu RM_BAZA. W odróżnieniu od okna
„Dopasowanie kartotek" (lista całego BOM-u) pracuje na pozycji, na którą
patrzysz — porządkowanie elementów znormalizowanych przed importem projektu
do Subiekta idzie sztuka po sztuce (decyzja użytkownika, 24.09.2026).

Układ: co jest w arkuszu (góra) → kandydaci z Subiekta (środek) →
przyciski (dół). Zmiana pokazywana PRZED zapisem, raport po.

Logika w subiekt_dopasuj_wiersz.py; tu tylko interfejs.
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox

import subiekt_dopasuj_wiersz as W
import subiekt_dopasowanie as D
import subiekt_scalanie as S

try:
    from subiekt_stany import wysrodkuj
except ImportError:
    def wysrodkuj(okno, rodzic, *a, **k):
        pass


class DopasujWierszWindow(tk.Toplevel):
    """Jedna pozycja arkusza → kartoteka Subiekta."""

    BTN_WYBIERZ = "✓ Wstaw do arkusza"
    BTN_ZALOZ = "➕ Nowa kartoteka w edytorze…"

    def __init__(self, parent, con, item_id, on_zapisano=None):
        super().__init__(parent)
        self.title("Dopasuj kartotekę Subiekta")
        self.con = con
        self.item_id = item_id
        self.on_zapisano = on_zapisano
        self.indeks = None
        self.kandydaci = []
        self._stany = {}
        self._zadanie_szukania = None

        self.wiersz = W.czytaj_wiersz(con, item_id)
        self.blokada = W.sprawdz_edytowalnosc(self.wiersz)

        self._buduj()
        wysrodkuj(self, parent, 1150, 620)

        # F5 = wymus swiezy katalog. `bind` (nie `bind_all`) — skroty F2-F6
        # glownego okna sa CELOWO odfiltrowane w oknach Toplevel
        # (`_skrot_arkusza` w RM_BAZA), wiec bez tego F5 tutaj nic nie robi.
        self.bind("<F5>", self._na_f5)

        if self.blokada:
            self._pokaz_blokade()
        else:
            self._wczytaj_katalog_async()

    # ── budowa okna ──────────────────────────────────────────────────────

    def _buduj(self):
        # ── co jest w arkuszu
        gora = tk.LabelFrame(self, text=" Pozycja w arkuszu RM_BAZA ",
                             padx=10, pady=8)
        gora.pack(fill=tk.X, padx=10, pady=(10, 6))

        w = self.wiersz or {}
        tk.Label(gora, text="Nazwa:", fg="#555").grid(row=0, column=0, sticky="w")
        tk.Label(gora, text=w.get("nazwa") or "(pusto)",
                 font=("Segoe UI", 10, "bold"), anchor="w").grid(
                     row=0, column=1, sticky="we", padx=(8, 0))
        tk.Label(gora, text="Numer / symbol:", fg="#555").grid(
            row=1, column=0, sticky="w", pady=(2, 0))
        tk.Label(gora, text=w.get("numer") or "(pusto)", anchor="w").grid(
            row=1, column=1, sticky="we", padx=(8, 0), pady=(2, 0))
        gora.columnconfigure(1, weight=1)

        # ── szukanie
        srodek = tk.LabelFrame(self, text=" Kartoteki w Subiekcie ",
                               padx=10, pady=8)
        srodek.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)

        pasek = tk.Frame(srodek)
        pasek.pack(fill=tk.X, pady=(0, 6))
        tk.Label(pasek, text="Szukaj:").pack(side=tk.LEFT)
        self.var_fraza = tk.StringVar(value=W.klucz_szukania(w) if w else "")
        e = tk.Entry(pasek, textvariable=self.var_fraza)
        e.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))
        e.bind("<Return>", lambda ev: self._szukaj())
        # Lista filtruje sie W TRAKCIE PISANIA — tak dziala sekcja 4 Edytora
        # kartotek i tego user oczekuje (zgloszone 24.09.2026). Przycisk
        # zostaje dla tych, ktorzy wola kliknac.
        self.var_fraza.trace_add("write", lambda *_a: self._szukaj_z_opoznieniem())
        tk.Button(pasek, text="Szukaj", command=self._szukaj).pack(side=tk.LEFT)

        # Kolumny jak w sekcji 4 Edytora kartotek — bo to ten sam problem:
        # po samym symbolu i nazwie nie da sie odroznic wariantow tej samej
        # czesci (KFL000/001/002/004 maja nazwe rowna symbolowi). Rozstrzyga
        # opis, rodzaj i cena (zgloszone 24.09.2026).
        kol = ("symbol", "nazwa", "opis", "rodzaj", "stan", "cena")
        self.tabela = ttk.Treeview(srodek, columns=kol, show="headings",
                                   selectmode="browse", height=14)
        for k, tekst, szer in (("symbol", "Symbol", 150),
                               ("nazwa", "Nazwa", 250),
                               ("opis", "Opis", 250),
                               ("rodzaj", "Rodzaj", 80),
                               ("stan", "Stan", 70),
                               ("cena", "Cena netto", 90)):
            self.tabela.heading(k, text=tekst)
            self.tabela.column(k, width=szer,
                               anchor="e" if k in ("stan", "cena") else "w")
        self.tabela.tag_configure("dokladne", background="#d5f5e3")
        self.tabela.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tabela.bind("<Double-1>", lambda ev: self._wybierz())

        sb = ttk.Scrollbar(srodek, orient="vertical", command=self.tabela.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tabela.config(yscrollcommand=sb.set)

        # ── stopka
        stopka = tk.Frame(self)
        stopka.pack(fill=tk.X, padx=10, pady=(0, 10))
        self.lbl_status = tk.Label(stopka, text="", fg="#555", anchor="w")
        self.lbl_status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(stopka, text="Zamknij", command=self.destroy).pack(
            side=tk.RIGHT, padx=(6, 0))
        self.btn_wybierz = tk.Button(stopka, text=self.BTN_WYBIERZ,
                                     command=self._wybierz,
                                     bg="#d5f5e3", state=tk.DISABLED)
        self.btn_wybierz.pack(side=tk.RIGHT, padx=(6, 0))
        self.btn_zaloz = tk.Button(stopka, text=self.BTN_ZALOZ,
                                   command=self._zaloz, state=tk.DISABLED)
        self.btn_zaloz.pack(side=tk.RIGHT)

    def _pokaz_blokade(self):
        """Pozycja nietykalna — mówimy dlaczego i wyłączamy przyciski."""
        self.lbl_status.config(text=f"⛔ {self.blokada['tytul']}", fg="#a33")
        self.btn_wybierz.config(state=tk.DISABLED)
        self.btn_zaloz.config(state=tk.DISABLED)
        messagebox.showinfo(self.blokada["tytul"], self.blokada["tekst"],
                            parent=self)

    # ── katalog Subiekta ─────────────────────────────────────────────────

    def _wczytaj_katalog_async(self):
        """Katalog w wątku — pierwsze pobranie idzie do Subiekta i trwa."""
        self.lbl_status.config(text="Wczytuję katalog Subiekta…", fg="#555")

        def robota():
            try:
                # JEDNO ZRODLO: `wczytaj_katalog_subiekta()` niesie opis,
                # rodzaj, cene i stan (uzupelnione 24.09.2026) oraz ma cache,
                # wiec drugie otwarcie okna jest natychmiastowe. Wlasna
                # sciezka pobierala katalog od nowa za kazdym razem.
                katalog = S.wczytaj_katalog_subiekta()
                indeks = D.Indeks(katalog)
                stany = {str(p.get("symbol") or "").strip().upper(): p.get("stan")
                         for p in katalog if p.get("stan") is not None}
                self.after(0, lambda: self._katalog_gotowy(indeks, stany))
            except Exception as e:
                self.after(0, lambda: self._katalog_blad(e))

        threading.Thread(target=robota, daemon=True).start()

    def _katalog_gotowy(self, indeks, stany=None):
        if not self.winfo_exists():
            return
        self.indeks = indeks
        self._stany = stany or {}
        self.lbl_status.config(text=f"Katalog: {len(indeks)} kartotek",
                               fg="#555")
        self.btn_zaloz.config(state=tk.NORMAL)
        self._szukaj()

    def _katalog_blad(self, e):
        if not self.winfo_exists():
            return
        self.lbl_status.config(text=f"⚠️ Katalog niedostępny: {e}", fg="#a33")

    # ── szukanie i wybór ─────────────────────────────────────────────────

    def _szukaj_z_opoznieniem(self, ms=180):
        """Przeliczenie listy po krotkiej przerwie w pisaniu.

        Bez tego kazdy wciskany znak przeszukuje caly katalog (~3500 pozycji)
        i pisanie zacina sie widocznie.
        """
        if getattr(self, "_zadanie_szukania", None):
            try:
                self.after_cancel(self._zadanie_szukania)
            except Exception:
                pass
        self._zadanie_szukania = self.after(ms, self._szukaj)

    def _szukaj(self):
        if not self.indeks:
            return
        self.kandydaci = W.kandydaci(self.wiersz, self.indeks,
                                     fraza=self.var_fraza.get())
        self.tabela.delete(*self.tabela.get_children())
        for i, poz in enumerate(self.kandydaci):
            sym = poz.get("symbol") or ""
            self.tabela.insert(
                "", "end", iid=str(i),
                values=(sym, poz.get("nazwa") or "", poz.get("opis") or "",
                        poz.get("rodzaj") or "",
                        self._stan_txt(self._stany.get(sym.upper())),
                        self._cena_txt(poz.get("cena"))),
                tags=("dokladne",) if poz.get("dokladne") else ())
        if self.kandydaci:
            self.tabela.selection_set("0")
            self.btn_wybierz.config(state=tk.NORMAL)
            ile_dokl = sum(1 for p in self.kandydaci if p.get("dokladne"))
            self.lbl_status.config(
                text=(f"{len(self.kandydaci)} kandydatów"
                      + (f", w tym {ile_dokl} dokładnych (zielone)"
                         if ile_dokl else "")), fg="#555")
        else:
            self.btn_wybierz.config(state=tk.DISABLED)
            self.lbl_status.config(
                text="Brak trafień — popraw frazę albo załóż nową kartotekę.",
                fg="#a60")

    @staticmethod
    def _stan_txt(v):
        """Stan magazynowy: pusto gdy nieznany, liczba bez zbednego ,0."""
        if v is None:
            return ""
        try:
            f = float(v)
        except (TypeError, ValueError):
            return str(v)
        return str(int(f)) if f == int(f) else ("%.2f" % f).rstrip("0").rstrip(".")

    @staticmethod
    def _cena_txt(v):
        """Cena ewidencyjna. Zero pokazujemy jako puste — nic nie znaczy."""
        try:
            f = float(v or 0)
        except (TypeError, ValueError):
            return ""
        return f"{f:g}" if f else ""

    def _zaznaczona(self):
        sel = self.tabela.selection()
        if not sel:
            return None
        try:
            return self.kandydaci[int(sel[0])]
        except (ValueError, IndexError):
            return None

    def _wybierz(self):
        """Wstawia wybraną kartotekę do wiersza — z podglądem przed zapisem."""
        if self.blokada:
            return
        poz = self._zaznaczona()
        if not poz:
            return

        podglad = W.podglad_wyboru(self.wiersz, poz)
        if podglad["bez_zmian"]:
            messagebox.showinfo(
                "Bez zmian",
                "Ten wiersz ma już dokładnie te wartości — nie ma czego "
                "zmieniać.", parent=self)
            return

        # Dwie linie: stan wiersza teraz i po zmianie. Rozbicie na pola
        # („Numer/symbol: przed… po…") bylo nieczytelne — user musial
        # skladac w glowie, jak ostatecznie bedzie wygladal wiersz.
        if not messagebox.askyesno(
                "Wstawić do arkusza?",
                f"Wiersz zostanie przepisany na dane z Subiekta:\n\n"
                f"    teraz:    {podglad['teraz']}\n"
                f"    będzie:   {podglad['bedzie']}\n\n"
                f"Zmiana dotyczy TYLKO tego wiersza w tym projekcie.\n"
                f"Nazwa z importu (src_name) zostaje nietknięta.",
                parent=self):
            return

        try:
            wynik = W.zastosuj_wybor(self.con, self.item_id, poz)
        except Exception as e:
            messagebox.showerror("Zapis", str(e), parent=self)
            return

        if not wynik.get("ok"):
            blok = wynik.get("blokada") or {}
            messagebox.showwarning(blok.get("tytul", "Nie zapisano"),
                                   blok.get("tekst", "—"), parent=self)
            return

        przed = wynik["przed"]
        messagebox.showinfo(
            "Zapisano",
            f"Wiersz przepisany na kartotekę Subiekta:\n\n"
            f"    było:   {W._opis_wiersza(przed['numer'], przed['nazwa'])}\n"
            f"    jest:   {W._opis_wiersza(wynik['symbol'], wynik['nazwa'])}",
            parent=self)
        if self.on_zapisano:
            self.on_zapisano()
        self.destroy()

    def _zaloz(self):
        """Otwiera Edytor kartotek z polami wypelnionymi z arkusza.

        ⛔ NIE ZAKLADA KARTOTEKI SAMA. Wczesniejsza wersja wolala
        `zaloz_kartoteke()` z czterema wartosciami z automatu — dla pozycji
        bedacej samym kodem („7810210") powstawala kartoteka
        „7810210 / 7810210", czyli dokladnie ten balagan, ktory porzadkowanie
        ma usuwac (zgloszone 24.09.2026).

        Edytor ma komplet pol (rodzaj, jednostka, cena ewid., polozenie,
        opis) i liste istniejacych kartotek obok — user widzi, co zaklada,
        i nadaje nazwe sam. Zapis zostaje pod zielonym przyciskiem edytora.
        """
        if self.blokada:
            return
        plan = W.plan_nowej_kartoteki(self.wiersz)
        try:
            import subiekt_edytor_gui as _E
        except Exception as e:
            messagebox.showerror("Edytor kartotek",
                                 "Nie udalo sie zaladowac edytora:\n" + str(e),
                                 parent=self)
            return

        # Nazwa rowna symbolowi nie niesie informacji — nie podstawiamy jej.
        # Puste pole nazwy w edytorze jest czytelnym sygnalem „uzupelnij".
        nazwa = plan["nazwa"]
        if nazwa and W.norm_kod(nazwa) == W.norm_kod(plan["symbol"]):
            nazwa = ""

        # ⚠️ NIE ZAMYKAMY tego okna. Wczesniej szlo tu `self.destroy()`,
        # wiec lancuch „F4 -> nowa kartoteka -> zapis -> zamkniecie edytora"
        # konczyl sie niczym: wiersz w arkuszu zostawal nietkniety, bo nikt
        # do niego nie wracal (zgloszone 24.09.2026).
        #
        # Zamiast tego edytor dostaje callback i pokazuje przycisk
        # „Podmien w arkuszu RM_BAZA" — to user decyduje, kiedy wiersz
        # ma dostac dane z kartoteki.
        # ⚠️ `po_zamknieciu` DOPIERO OD 25.09.2026 (zgloszenie usera).
        # `_odswiez_katalog_i_szukaj` istniala tu od poczatku, ale NIKT
        # JEJ NIE WOLAL — martwy kod. Efekt: user zakladal kartoteke
        # w edytorze, wracal do tego okna i swojej kartoteki NIE WIDZIAL,
        # bo lista szla dalej ze starego cache.
        #
        # Szukamy po SYMBOLU nowej kartoteki, nie po dotychczasowej frazie:
        # user wlasnie ja zalozyl, wiec chce ja zobaczyc.
        _E.open_window(self.master,
                       nowa={"symbol": plan["symbol"], "nazwa": nazwa},
                       do_arkusza=self._wstaw_z_edytora,
                       po_zamknieciu=lambda: self._po_edytorze(plan["symbol"]))

    def _po_edytorze(self, symbol):
        """Powrot z edytora — katalog moze miec nowa kartoteke."""
        if not self.winfo_exists():
            return          # user zamknal okno w miedzyczasie
        self._odswiez_katalog_i_szukaj(symbol)

    def _wstaw_z_edytora(self, kartoteka):
        """Callback dla edytora: wstawia jego kartoteke do naszego wiersza.

        Zwraca False, gdy zapis nie przeszedl — edytor wtedy milczy, bo
        komunikat pokazalismy juz tutaj.
        """
        if self.blokada:
            messagebox.showwarning(self.blokada["tytul"],
                                   self.blokada["tekst"], parent=self)
            return False
        try:
            wynik = W.zastosuj_wybor(self.con, self.item_id, kartoteka)
        except Exception as e:
            messagebox.showerror("Podmiana w arkuszu", str(e), parent=self)
            return False
        if not wynik.get("ok"):
            blok = wynik.get("blokada") or {}
            messagebox.showwarning(blok.get("tytul", "Nie zapisano"),
                                   blok.get("tekst", "—"), parent=self)
            return False

        przed = wynik["przed"]
        messagebox.showinfo(
            "Podmieniono w arkuszu",
            f"Wiersz przepisany na kartotekę z edytora:\n\n"
            f"    było:   {W._opis_wiersza(przed['numer'], przed['nazwa'], przed.get('opis'))}\n"
            f"    jest:   {W._opis_wiersza(wynik['symbol'], wynik['nazwa'], wynik.get('opis'))}",
            parent=self)
        if self.on_zapisano:
            self.on_zapisano()
        # Wiersz ma juz kartoteke — to okno nie ma tu nic wiecej do roboty.
        self.destroy()
        return True

    def _na_f5(self, event=None):
        """F5 — wymus pobranie katalogu od nowa, z zachowaniem frazy.

        Potrzebne, gdy kartoteka powstala POZA ta sciezka (wprost
        w Subiekcie albo na drugiej maszynie) — wtedy nikt nie skasowal
        naszego cache.
        """
        self._odswiez_katalog_i_szukaj(self.var_fraza.get())
        return "break"

    def _odswiez_katalog_i_szukaj(self, fraza):
        """Po założeniu kartoteki cache katalogu jest nieaktualny."""
        self.var_fraza.set(fraza)
        self.lbl_status.config(text="Odświeżam katalog…", fg="#555")

        def robota():
            try:
                katalog = S.wczytaj_katalog_subiekta(max_wiek_h=0)
                indeks = D.Indeks(katalog)
                self.after(0, lambda: self._katalog_gotowy(indeks))
            except Exception as e:
                self.after(0, lambda: self._katalog_blad(e))

        threading.Thread(target=robota, daemon=True).start()


def open_window(parent, con, item_id, on_zapisano=None):
    """Punkt wejścia z arkusza RM_BAZA."""
    if not item_id:
        messagebox.showwarning("Dopasuj kartotekę",
                               "Najpierw kliknij wiersz w arkuszu.",
                               parent=parent)
        return None
    return DopasujWierszWindow(parent, con, item_id, on_zapisano=on_zapisano)
