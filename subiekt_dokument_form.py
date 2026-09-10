# -*- coding: utf-8 -*-
"""
Wspólny szkielet formularzy dokumentów wystawianych z Edytora kartotek.

Po co osobny moduł
──────────────────
RW, PW, ZD, ZK, MM, PZ i WZ różnią się nagłówkiem i tym, co robi most —
ale środek mają identyczny: tabela wielu pozycji, checkbox „użyj", edycja
ilości, „Sprawdź" przed zapisem, „Anuluj" bez skutków.

Powód wydzielenia jest konkretny, nie estetyczny: **RW ma już dziś TRZY
niezależne implementacje** — Kalkulator RMPAK (`rmpak_calculator._wystaw_rw`),
okno Magazyn (`subiekt_magazyn_gui._zdejmij_rw`) i ręczne wystawianie wprost
w Subiekcie. Rozjechały się: pierwsza pokazuje cenę z PW, druga jej nie zna,
trzecia nie wie nic o ostrzeżeniach. Dokładanie czwartej kopii przy każdym
kolejnym typie dokumentu skończyłoby się tak samo (ustalenie z 10.09.2026,
SUBIEKT_FORMULARZE_DOKUMENTOW.md §9).

Czego ten moduł NIE robi
────────────────────────
Nie zna Subiekta. Nie woła mostu, nie wie, co to RW ani ZD — dostaje listę
pozycji i zwraca to, co user zatwierdził. Cała wiedza o dokumencie siedzi
w module, który go używa. Dzięki temu da się go przetestować bez Sfery.

Źródło pozycji
──────────────
Drzewo z sekcji 1 Edytora („roboczy koszyk", §2 specyfikacji). Konwersję
robi `pozycje_z_drzewa()`, żeby każdy formularz brał dane tak samo —
z rozwijaniem kompletów według wybranego trybu.
"""

import tkinter as tk
from tkinter import ttk, messagebox

# Te same kolory co Edytor — formularz jest jego przedłużeniem, nie osobną
# aplikacją. Import z subiekt_edytor_gui byłby cyklem (to on woła nas).
TLO = "#ecf0f1"
TLO_SEKCJI = "#ffffff"
TEKST = "#2c3e50"
TEKST_SZARY = "#7f8c8d"
OK_ZIELONY = "#1e8449"
BLAD_CZERWONY = "#c0392b"
UWAGA_ZOLTY = "#7d6608"
UWAGA_TLO = "#fcf3cf"

#: Tryby rozwijania kompletów (§8 specyfikacji). Reguła per dokument jest
#: jeszcze do ustalenia, więc formularz tylko PYTA — nie narzuca.
BEZPOSREDNIO = "bezposrednio"
JEDEN_POZIOM = "jeden_poziom"
DO_KONCA = "do_konca"

TRYBY_ROZWIJANIA = [
    (BEZPOSREDNIO, "pozycje bezpośrednio z okna 1"),
    (JEDEN_POZIOM, "rozwiń komplety o jeden poziom"),
    (DO_KONCA, "rozwiń komplety do najniższych składników"),
]


def pozycje_z_drzewa(pozycje, relacje, korzenie, tryb=BEZPOSREDNIO,
                     tylko_symbole=None):
    """[{symbol, nazwa, rodzaj, ilosc}] z modelu Edytora.

    `pozycje` / `relacje` / `korzenie` to model EdytorWindow (graf, nie
    drzewo: ta sama kartoteka może siedzieć w kilku kompletach).

    Rozwijanie kompletów mnoży ilości wzdłuż ścieżki — zespół 2× zawierający
    śrubę 4× daje 8 śrub. **Powtórzone symbole są SUMOWANE**, bo dokument ma
    mieć jeden wiersz na kartotekę (§8 specyfikacji): Subiekt i tak odrzuciłby
    dwa identyczne składniki, a na RW dwa wiersze tej samej pozycji to prosta
    droga do pomyłki przy liczeniu.

    `tylko_symbole` zawęża wynik do wskazanych korzeni — na później, gdyby
    doszedł tryb „tylko zaznaczone w drzewie".
    """
    wynik = {}          # SYMBOL -> {symbol, nazwa, rodzaj, ilosc}
    kolejnosc = []      # zachowujemy kolejność pierwszego wystąpienia

    def dorzuc(sym, ilosc):
        k = pozycje.get(sym)
        if k is None:
            return
        klucz = sym.upper()
        if klucz not in wynik:
            wynik[klucz] = {"symbol": sym, "nazwa": k.nazwa or "",
                            "rodzaj": k.rodzaj, "ilosc": 0.0,
                            "opis": getattr(k, "opis", "") or ""}
            kolejnosc.append(klucz)
        wynik[klucz]["ilosc"] += float(ilosc)

    def dzieci(sym):
        return [(d, il) for (r, d, il) in relacje if r == sym]

    def idz(sym, mnoznik, glebokosc, sciezka):
        # Cykl w składzie — model grafowy na to pozwala, a bez strażnika
        # rozwijanie leciałoby w nieskończoność.
        if sym in sciezka:
            return
        k = pozycje.get(sym)
        if k is None:
            return
        potomkowie = dzieci(sym)
        czy_komplet = k.rodzaj == "komplet" and potomkowie

        rozwijac = (czy_komplet and (
            tryb == DO_KONCA or (tryb == JEDEN_POZIOM and glebokosc == 0)))

        if not rozwijac:
            dorzuc(sym, mnoznik)
            return
        # Komplet ROZWINIĘTY nie trafia na dokument — na RW schodzą składniki,
        # nie sam zespół. Inaczej zdjęlibyśmy stan dwa razy.
        for d, il in potomkowie:
            idz(d, mnoznik * float(il or 1), glebokosc + 1, sciezka | {sym})

    zrodla = tylko_symbole if tylko_symbole is not None else korzenie
    for sym in zrodla:
        idz(sym, 1.0, 0, set())

    return [wynik[k] for k in kolejnosc]


class TabelaPozycji(tk.Frame):
    """Tabela pozycji dokumentu: ✓ | Symbol | Nazwa | … | Ilość.

    Kolumny poza stałymi (`✓`, Symbol, Nazwa, Ilość) podaje wołający —
    RW chce „Stan", PW i ZD chcą „Cena", ZD dodatkowo „Dostawca".

    Edycja ilości i cen idzie przez dwuklik otwierający wpis w komórce.
    Treeview nie ma edycji wbudowanej, a osobne pola Entry pod tabelą przy
    kilkudziesięciu pozycjach są nie do użycia.
    """

    #: Kolumny zawsze obecne, w tej kolejności.
    STALE_PRZED = [("uzyj", "✓", 34), ("symbol", "Symbol", 150),
                   ("nazwa", "Nazwa", 240)]
    STALE_PO = [("ilosc", "Ilość", 70), ("jm", "JM", 45)]

    def __init__(self, rodzic, pozycje, kolumny_dodatkowe=(), edytowalne=("ilosc",),
                 na_zmiane=None):
        """`kolumny_dodatkowe`: [(klucz, nagłówek, szerokość, edytowalna)]."""
        super().__init__(rodzic, bg=TLO_SEKCJI)
        self.pozycje = [dict(p) for p in pozycje]   # kopia: Anuluj nie rusza źródła
        for p in self.pozycje:
            p.setdefault("uzyj", True)
            p.setdefault("jm", "kpl" if p.get("rodzaj") == "komplet" else "szt")
        self._na_zmiane = na_zmiane
        self._edytowalne = set(edytowalne) | {
            k for k, _n, _s, edy in kolumny_dodatkowe if edy}

        kolumny = (self.STALE_PRZED
                   + [(k, n, s) for k, n, s, _e in kolumny_dodatkowe]
                   + self.STALE_PO)
        self._klucze = [k for k, _n, _s in kolumny]

        wrap = tk.Frame(self, bg=TLO_SEKCJI)
        wrap.pack(fill=tk.BOTH, expand=True)
        self.tab = ttk.Treeview(wrap, columns=self._klucze, show="headings",
                                selectmode="extended")
        for klucz, naglowek, szer in kolumny:
            self.tab.heading(klucz, text=naglowek)
            self.tab.column(klucz, width=szer, minwidth=40,
                            stretch=(klucz == "nazwa"),
                            anchor=("center" if klucz == "uzyj"
                                    else "e" if klucz in ("ilosc", "stan", "cena")
                                    else "w"))
        sc = ttk.Scrollbar(wrap, orient="vertical", command=self.tab.yview)
        self.tab.configure(yscrollcommand=sc.set)
        self.tab.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sc.pack(side=tk.RIGHT, fill=tk.Y)

        self.tab.tag_configure("odznaczona", foreground=TEKST_SZARY)
        self.tab.tag_configure("uwaga", background=UWAGA_TLO, foreground=UWAGA_ZOLTY)

        # Spacja przełącza ✓ na zaznaczonych — szybsze niż klikanie po jednej.
        self.tab.bind("<space>", lambda _e: self.przelacz_zaznaczone())
        self.tab.bind("<Button-1>", self._na_klik)
        self.tab.bind("<Double-1>", self._na_dwuklik)

        self.odswiez()

    # ── dane ────────────────────────────────────────────────────────────

    def odswiez(self):
        wybrane = set(self.tab.selection())
        for w in self.tab.get_children():
            self.tab.delete(w)
        for i, p in enumerate(self.pozycje):
            iid = str(i)
            tagi = []
            if not p["uzyj"]:
                tagi.append("odznaczona")
            if p.get("uwaga"):
                tagi.append("uwaga")
            self.tab.insert("", "end", iid=iid, values=self._wiersz(p),
                            tags=tuple(tagi))
            if iid in wybrane:
                self.tab.selection_add(iid)
        if self._na_zmiane:
            self._na_zmiane()

    def _wiersz(self, p):
        out = []
        for k in self._klucze:
            if k == "uzyj":
                out.append("☑" if p["uzyj"] else "☐")
            elif k in ("ilosc", "stan", "cena"):
                v = p.get(k)
                out.append("" if v in (None, "") else f"{float(v):g}")
            else:
                out.append(str(p.get(k) or ""))
        return out

    def uzyte(self):
        """Pozycje zaznaczone ✓ — to one idą na dokument."""
        return [p for p in self.pozycje if p["uzyj"]]

    def ustaw_uwage(self, symbol, tekst):
        """Dopisuje ostrzeżenie do pozycji (żółte tło wiersza)."""
        for p in self.pozycje:
            if p["symbol"].upper() == (symbol or "").upper():
                p["uwaga"] = tekst
        self.odswiez()

    def wyczysc_uwagi(self):
        for p in self.pozycje:
            p.pop("uwaga", None)
        self.odswiez()

    # ── interakcja ──────────────────────────────────────────────────────

    def _na_klik(self, e):
        """Klik w kolumnę ✓ przełącza pozycję — bez wchodzenia w edycję."""
        if self.tab.identify_region(e.x, e.y) != "cell":
            return
        if self.tab.identify_column(e.x) != "#1":       # ✓ jest pierwsza
            return
        iid = self.tab.identify_row(e.y)
        if not iid:
            return
        p = self.pozycje[int(iid)]
        p["uzyj"] = not p["uzyj"]
        self.odswiez()
        return "break"

    def _na_dwuklik(self, e):
        if self.tab.identify_region(e.x, e.y) != "cell":
            return
        iid = self.tab.identify_row(e.y)
        kol = self.tab.identify_column(e.x)
        if not iid or not kol:
            return
        idx = int(kol[1:]) - 1
        if idx < 0 or idx >= len(self._klucze):
            return
        klucz = self._klucze[idx]
        if klucz not in self._edytowalne:
            return
        self._edytuj_komorke(iid, idx, klucz)
        return "break"

    def _edytuj_komorke(self, iid, idx, klucz):
        """Entry NAD komórką — zatwierdza Enter/utrata fokusu, Esc anuluje."""
        x, y, szer, wys = self.tab.bbox(iid, self._klucze[idx])
        p = self.pozycje[int(iid)]
        var = tk.StringVar(value=str(p.get(klucz) or ""))
        e = tk.Entry(self.tab, textvariable=var, justify="right",
                     font=("Arial", 9))
        e.place(x=x, y=y, width=szer, height=wys)
        e.focus_set()
        e.select_range(0, tk.END)

        def zatwierdz(_e=None):
            tekst = var.get().strip().replace(",", ".")
            try:
                wartosc = float(tekst) if tekst else 0.0
            except ValueError:
                messagebox.showwarning("Wartość", f"„{var.get()}” to nie liczba.",
                                       parent=self.winfo_toplevel())
                e.destroy()
                return
            if klucz == "ilosc" and wartosc <= 0:
                messagebox.showwarning("Ilość", "Ilość musi być większa od zera.",
                                       parent=self.winfo_toplevel())
                e.destroy()
                return
            p[klucz] = wartosc
            e.destroy()
            self.odswiez()

        e.bind("<Return>", zatwierdz)
        e.bind("<FocusOut>", zatwierdz)
        e.bind("<Escape>", lambda _e: e.destroy())

    def przelacz_zaznaczone(self):
        wyb = self.tab.selection()
        if not wyb:
            return "break"
        # Jeśli cokolwiek jest odznaczone — zaznaczamy wszystko; inaczej
        # odwrotnie. Przewidywalne przy mieszanym zaznaczeniu.
        docelowo = any(not self.pozycje[int(i)]["uzyj"] for i in wyb)
        for i in wyb:
            self.pozycje[int(i)]["uzyj"] = docelowo
        self.odswiez()
        return "break"

    def zaznacz_wszystko(self, stan=True):
        for p in self.pozycje:
            p["uzyj"] = stan
        self.odswiez()

    def usun_zaznaczone(self):
        """Usuwa z BIEŻĄCEGO dokumentu — model Edytora zostaje nietknięty."""
        wyb = {int(i) for i in self.tab.selection()}
        if not wyb:
            return
        self.pozycje = [p for i, p in enumerate(self.pozycje) if i not in wyb]
        self.odswiez()


class OknoDokumentu(tk.Toplevel):
    """Szkielet okna formularza: nagłówek, tabela, stopka Anuluj/Sprawdź/Wystaw.

    Klasa pochodna buduje pola nagłówka (`buduj_naglowek`), mówi jakie
    kolumny ma tabela (`kolumny`) i co robi „Sprawdź" / „Wystaw"
    (`sprawdz`, `wystaw`). Reszta — układ, walidacja pustego wyboru,
    blokowanie przycisków na czas pracy — jest tu.
    """

    TYTUL = "Dokument"
    PRZYCISK = "WYSTAW"
    KOLOR_PRZYCISKU = "#2980b9"
    ROZMIAR = "1180x700"

    def __init__(self, parent, pozycje, kontekst=None):
        super().__init__(parent)
        self.kontekst = kontekst or {}
        self.title(f"Edytor kartotek — {self.TYTUL}")
        self.configure(bg=TLO)
        self.geometry(self.ROZMIAR)
        self.transient(parent)
        self._sprawdzone = None      # wynik ostatniego suchego przebiegu

        pasek = tk.Frame(self, bg="#34495e", height=44)
        pasek.pack(fill=tk.X)
        pasek.pack_propagate(False)
        tk.Label(pasek, text=f"  {self.TYTUL}", bg="#34495e", fg="white",
                 font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)

        tk.Label(self, text="Dokument tworzony dla pozycji z okna 1 — "
                            "Struktura kartoteki (drzewo)",
                 bg=TLO, fg=TEKST_SZARY, font=("Arial", 8), anchor="w").pack(
            fill=tk.X, padx=12, pady=(6, 0))

        # ── nagłówek dokumentu ──────────────────────────────────────────
        self.ram_naglowek = tk.LabelFrame(
            self, text=f" 1. Dane dokumentu {self.TYTUL.split()[0]} ",
            bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 9, "bold"))
        self.ram_naglowek.pack(fill=tk.X, padx=12, pady=6)
        self.buduj_naglowek(self.ram_naglowek)

        # ── tryb rozwijania kompletów ───────────────────────────────────
        self._pozycje_zrodlowe = pozycje
        ram_tryb = tk.Frame(self, bg=TLO)
        ram_tryb.pack(fill=tk.X, padx=12, pady=(0, 4))
        tk.Label(ram_tryb, text="2. Pozycje:", bg=TLO, fg=TEKST,
                 font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(2, 12))
        self.var_tryb = tk.StringVar(value=BEZPOSREDNIO)
        for wartosc, etykieta in TRYBY_ROZWIJANIA:
            tk.Radiobutton(ram_tryb, text=etykieta, variable=self.var_tryb,
                           value=wartosc, bg=TLO, fg=TEKST, font=("Arial", 9),
                           activebackground=TLO, selectcolor=TLO_SEKCJI,
                           command=self._przelicz_pozycje).pack(side=tk.LEFT, padx=(0, 24))

        # ── stopka PRZED tabelą: rozciągliwa tabela inaczej ją wypycha ──
        stopka = tk.Frame(self, bg=TLO)
        stopka.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=10)
        self.lbl_status = tk.Label(stopka, text="", bg=TLO, fg=TEKST_SZARY,
                                   font=("Arial", 9), anchor="w")
        self.lbl_status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_wystaw = tk.Button(stopka, text=self.PRZYCISK,
                                    command=self._na_wystaw,
                                    bg=self.KOLOR_PRZYCISKU, fg="white",
                                    font=("Arial", 10, "bold"), padx=18, pady=4,
                                    state=tk.DISABLED)
        self.btn_wystaw.pack(side=tk.RIGHT)
        self.btn_sprawdz = tk.Button(stopka, text="Sprawdź", command=self._na_sprawdz,
                                     font=("Arial", 10), padx=14, pady=4)
        self.btn_sprawdz.pack(side=tk.RIGHT, padx=(0, 8))
        tk.Button(stopka, text="Anuluj", command=self.destroy,
                  font=("Arial", 10), padx=14, pady=4).pack(side=tk.RIGHT, padx=(0, 8))

        pasek_dolny = tk.Frame(self, bg=TLO)
        pasek_dolny.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 2))
        tk.Button(pasek_dolny, text="Zaznacz wszystko", font=("Arial", 8),
                  command=lambda: self.tabela.zaznacz_wszystko(True)).pack(side=tk.LEFT)
        tk.Button(pasek_dolny, text="Odznacz wszystko", font=("Arial", 8),
                  command=lambda: self.tabela.zaznacz_wszystko(False)).pack(side=tk.LEFT, padx=6)
        tk.Button(pasek_dolny, text="Usuń z dokumentu", font=("Arial", 8),
                  command=lambda: self.tabela.usun_zaznaczone()).pack(side=tk.LEFT)
        tk.Label(pasek_dolny, text=self.PODPOWIEDZ, bg=TLO, fg=TEKST_SZARY,
                 font=("Arial", 8)).pack(side=tk.RIGHT)

        # ── tabela ──────────────────────────────────────────────────────
        ram_tab = tk.LabelFrame(self, text=" 3. Pozycje dokumentu ", bg=TLO_SEKCJI,
                                fg=TEKST, font=("Arial", 9, "bold"))
        ram_tab.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))
        self.tabela = TabelaPozycji(ram_tab, pozycje,
                                    kolumny_dodatkowe=self.kolumny(),
                                    na_zmiane=self._na_zmiane_tabeli)
        self.tabela.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.bind("<Escape>", lambda _e: self.destroy())
        self._na_zmiane_tabeli()

        # NA ŚRODKU OKNA MATKI, nie ekranu (10.09.2026). Tk stawia Toplevel
        # w lewym górnym rogu monitora GŁÓWNEGO — na stanowisku z trzema
        # monitorami formularz wyskakiwał gdzie indziej niż Edytor, z którego
        # go otwarto. `wysrodkuj` liczy pozycję względem rodzica i przycina
        # do granic pulpitu WIRTUALNEGO (współrzędne bywają ujemne), więc
        # okno ląduje na tym samym monitorze co Edytor.
        #
        # Wołane PO zbudowaniu zawartości — inaczej okno nie zna swojego
        # rozmiaru i wyszłoby przesunięte o połowę.
        try:
            from subiekt_stany import wysrodkuj
            wysrodkuj(self, parent)
        except Exception:
            pass          # pozycjonowanie nie może zablokować formularza

    #: Tekst podpowiedzi w pasku pod tabelą — klasa pochodna może nadpisać.
    PODPOWIEDZ = "Dwuklik na ilości = zmiana   ·   spacja = przełącz ✓"

    # ── do nadpisania ───────────────────────────────────────────────────

    def buduj_naglowek(self, rodzic):
        """Pola nagłówka dokumentu (magazyn, data, projekt, uwagi…)."""
        raise NotImplementedError

    def kolumny(self):
        """[(klucz, nagłówek, szerokość, edytowalna)] — kolumny dodatkowe."""
        return []

    def sprawdz(self, pozycje):
        """Suchy przebieg. Zwraca wynik z mostu albo rzuca wyjątek."""
        raise NotImplementedError

    def wystaw(self, pozycje):
        """Właściwy zapis. Zwraca wynik z mostu albo rzuca wyjątek."""
        raise NotImplementedError

    def po_sprawdzeniu(self, wynik):
        """Reakcja na wynik suchego przebiegu. Zwraca True = można wystawiać."""
        return True

    def po_wystawieniu(self, wynik):
        """Reakcja na udany zapis."""

    def waliduj_naglowek(self):
        """Lista błędów blokujących zapis (pusta = OK)."""
        return []

    # ── mechanika ───────────────────────────────────────────────────────

    def _przelicz_pozycje(self):
        """Zmiana trybu rozwijania przebudowuje listę pozycji."""
        przelicz = self.kontekst.get("przelicz")
        if not przelicz:
            return
        self.tabela.pozycje = [dict(p) for p in przelicz(self.var_tryb.get())]
        for p in self.tabela.pozycje:
            p.setdefault("uzyj", True)
            p.setdefault("jm", "kpl" if p.get("rodzaj") == "komplet" else "szt")
        self._sprawdzone = None
        self.tabela.odswiez()

    def _na_zmiane_tabeli(self):
        # TabelaPozycji wola ten callback juz ze swojego __init__ (pierwsze
        # odswiez()), a wtedy self.tabela jeszcze nie istnieje — przypisanie
        # dzieje sie dopiero po powrocie z konstruktora.
        tabela = getattr(self, "tabela", None)
        if tabela is None:
            return
        uzyte = tabela.uzyte()
        # Każda zmiana unieważnia sprawdzenie — inaczej dałoby się wystawić
        # dokument inny niż ten, który przeszedł suchy przebieg.
        self._sprawdzone = None
        self.btn_wystaw.config(state=tk.DISABLED)
        self.lbl_status.config(
            text=f"Pozycji: {len(tabela.pozycje)}   ·   zaznaczonych: {len(uzyte)}"
                 + ("   — kliknij „Sprawdź”" if uzyte else "   — nic nie zaznaczone"),
            fg=TEKST_SZARY)

    def _zebrane(self):
        """Pozycje do wysłania albo None, gdy coś jest nie tak."""
        bledy = self.waliduj_naglowek()
        if bledy:
            messagebox.showwarning(self.TYTUL, "\n".join(f"• {b}" for b in bledy),
                                   parent=self)
            return None
        uzyte = self.tabela.uzyte()
        if not uzyte:
            messagebox.showinfo(self.TYTUL, "Nie zaznaczono żadnej pozycji.",
                                parent=self)
            return None
        return uzyte

    def _na_sprawdz(self):
        uzyte = self._zebrane()
        if uzyte is None:
            return
        self.tabela.wyczysc_uwagi()
        self._blokuj(True, "Sprawdzam w Subiekcie…")
        try:
            wynik = self.sprawdz(uzyte)
        except Exception as e:
            self._blokuj(False)
            messagebox.showerror(self.TYTUL, f"Nie udało się połączyć z Subiektem:\n\n{e}",
                                 parent=self)
            return
        self._blokuj(False)
        mozna = self.po_sprawdzeniu(wynik)
        self._sprawdzone = wynik if mozna else None
        self.btn_wystaw.config(state=tk.NORMAL if mozna else tk.DISABLED)

    def _na_wystaw(self):
        if self._sprawdzone is None:
            messagebox.showinfo(self.TYTUL, "Najpierw „Sprawdź”.", parent=self)
            return
        uzyte = self._zebrane()
        if uzyte is None:
            return
        self._blokuj(True, "Zapisuję w Subiekcie…")
        try:
            wynik = self.wystaw(uzyte)
        except Exception as e:
            self._blokuj(False)
            messagebox.showerror(
                self.TYTUL,
                f"Zapis nie powiódł się:\n\n{e}\n\n"
                "NIE ponawiaj automatycznie — najpierw sprawdź w Subiekcie, "
                "czy dokument mimo to nie powstał.", parent=self)
            return
        self._blokuj(False)
        self.po_wystawieniu(wynik)

    def _blokuj(self, blokuj, tekst=""):
        stan = tk.DISABLED if blokuj else tk.NORMAL
        self.btn_sprawdz.config(state=stan)
        if blokuj:
            self.btn_wystaw.config(state=tk.DISABLED)
            self.lbl_status.config(text=tekst, fg=TEKST)
        self.config(cursor="watch" if blokuj else "")
        self.update_idletasks()
