# -*- coding: utf-8 -*-
"""
Okno „Dopasowanie kartotek Subiekta" — etap 3 pracy z elementami handlowymi.

    1. scalanie zapisów      → jeden kanoniczny kod
    2. scalanie podobnych    → człowiek rozstrzyga duplikaty
    3. TO OKNO               → kod → konkretne Id kartoteki Subiekta

Okno niczego nie scala i nie zmienia BOM-u. Odpowiada na jedno pytanie:
„które dokładnie Id w Subiekcie odpowiada temu kodowi?".

Układ: zakładki stanów u góry (domyślnie „Do decyzji"), tabela pozycji po
lewej, panel kandydatów po prawej. Bez popupów per pozycja — praca idzie
listą, a wybór jest jednym kliknięciem w panelu obok.

Logika w subiekt_dopasowanie.py; tu tylko interfejs.
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox

import subiekt_dopasowanie as D
import subiekt_scalanie as S

try:
    from subiekt_stany import wysrodkuj
except ImportError:
    def wysrodkuj(okno, rodzic, *a, **k):
        pass


class DopasowanieWindow(tk.Toplevel):
    """Lista pozycji + panel kandydatów. Decyduje człowiek, nie automat."""

    #: Zakładka „Podpowiedzi" pokazuje te same pozycje co „Brak kartoteki",
    #: ale tylko te, dla których podobieństwo znalazło kandydatów. Osobna,
    #: bo to INNY rodzaj danych: nie trafienia, tylko propozycje do obejrzenia.
    ZAKL_PODPOWIEDZI = "Podpowiedzi"

    #: Zakładki: (etykieta, stany do pokazania)
    ZAKLADKI = (
        ("Do decyzji", (D.STAN_NAZWA, D.STAN_NIEJEDNOZNACZNE)),
        ("Dopasowane", (D.STAN_ZAPAMIETANE, D.STAN_SYMBOL)),
        ("Brak kartoteki", (D.STAN_BRAK,)),
        (ZAKL_PODPOWIEDZI, (D.STAN_BRAK,)),
        ("Wszystkie", tuple(D.OPIS_STANU)),
    )

    def __init__(self, parent, project_id, project_name=None):
        super().__init__(parent)
        self.project_id = project_id
        self.project_name = project_name or str(project_id)
        self.title(f"Dopasowanie kartotek Subiekta — projekt {project_id}"
                   f" ({self.project_name})")
        # Szersze niż poprzednie 1320: prawy panel ma sześć kolumn (symbol,
        # nazwa, stan, cena, podobieństwo, skąd) i przy węższym oknie ostatnie
        # się ucinały (zgłoszone 15.09.2026). Przy ciasnym ekranie okno i tak
        # zejdzie do minsize, a kolumny same się skurczą.
        self.geometry("1500x800")
        self.minsize(1100, 560)
        # ŚWIADOMIE bez transient(): okno-dziecko z transient dostaje w Windows
        # tylko przycisk „×", bez minimalizacji i maksymalizacji (zgłoszone
        # 15.09.2026: „daj kwadracik robiący full screen"). To pełnoprawne
        # okno robocze, więc ma mieć — □ × jak arkusz główny i okno zamówień,
        # które rozwiązało to tak samo (subiekt_zamowienia.py ~1016).
        # Skutek uboczny (pożądany): okno NIE trzyma się nad rodzicem, więc
        # da się je odłożyć na drugi monitor i pracować w arkuszu.
        self.resizable(True, True)
        self.bind("<F11>", self._przelacz_pelny_ekran)
        self.bind("<Escape>", lambda _e: self.state("normal"))

        self.indeks = None
        self.pozycje = []
        self.katalog = []         # pełna kartoteka — do liczenia podpowiedzi
        self._zajete = set()      # symbole już przypisane w tym projekcie
        self._stany = {}          # {symbol: dane z query_stock} — cache okna
        self.decyzje = {}         # {kod: {symbol, id, nazwa}} — do zapisania
        self.zakladka = 0
        self._biezaca = None

        self._buduj()
        self.after(50, self._wczytaj_async)
        wysrodkuj(self, parent)
        # Szerokości kolumn liczone PO tym, jak Tk nada oknu realne rozmiary.
        # Liczone w __init__ opierałyby się na winfo_width() == 1 i tabela
        # startowała ścięta (zgłoszone 15.09.2026).
        self.after(120, self._dopasuj_kolumny)

    def _przelacz_pelny_ekran(self, _e=None):
        """F11 — pełny ekran i z powrotem."""
        self.state("normal" if self.state() == "zoomed" else "zoomed")
        # Po zmianie stanu okna Tk podaje nowe rozmiary dopiero za chwilę.
        self.after(60, self._dopasuj_kolumny)
        return "break"

    def _dopasuj_kolumny(self):
        """Przelicza szerokości obu tabel na ich AKTUALNEJ szerokości."""
        if not self.winfo_exists():
            return
        try:
            self._rozciagnij(self.tab, self.KOL_LEWA)
            self._rozciagnij(self.tab2, self.KOL_PRAWA)
        except Exception:
            pass          # układ to nie powód, żeby wywalić okno

    # ── budowa ─────────────────────────────────────────────────────────
    def _buduj(self):
        gora = tk.Frame(self, bg="#ffffff")
        gora.pack(fill=tk.X)
        self.lbl_licznik = tk.Label(gora, text="wczytuję…", bg="#ffffff",
                                    font=("Arial", 11), anchor="w", padx=14, pady=10)
        self.lbl_licznik.pack(side=tk.LEFT)
        self.lbl_katalog = tk.Label(gora, text="", bg="#ffffff", fg="#7f8c8d",
                                    font=("Arial", 9), padx=10)
        self.lbl_katalog.pack(side=tk.RIGHT)
        tk.Button(gora, text="⟳ Odśwież", command=self._odswiez_katalog,
                  padx=10, pady=2).pack(side=tk.RIGHT, padx=8, pady=6)

        pasek = tk.Frame(self, bg="#ecf0f1")
        pasek.pack(fill=tk.X, padx=12, pady=(0, 6))
        self.btn_zakladki = []
        for i, (etykieta, _stany) in enumerate(self.ZAKLADKI):
            b = tk.Button(pasek, text=etykieta, relief=tk.FLAT, padx=14, pady=6,
                          font=("Arial", 9, "bold"),
                          command=lambda n=i: self._ustaw_zakladke(n))
            b.pack(side=tk.LEFT, padx=(0, 4), pady=6)
            self.btn_zakladki.append(b)
        tk.Label(pasek, text="Szukaj w tabeli:", bg="#ecf0f1",
                 font=("Arial", 9)).pack(side=tk.LEFT, padx=(20, 4))
        self.var_filtr = tk.StringVar()
        e = tk.Entry(pasek, textvariable=self.var_filtr, width=22)
        e.pack(side=tk.LEFT, pady=6)
        e.bind("<KeyRelease>", lambda _e: self._odswiez_liste())

        # Stopka przed treścią — przyciski nie mogą wypaść poza ekran.
        stopka = tk.Frame(self)
        stopka.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=10)
        tk.Button(stopka, text="Zamknij", command=self.destroy,
                  padx=16, pady=4).pack(side=tk.LEFT)
        self.btn_zapisz = tk.Button(
            stopka, text="💾 Zapisz decyzje", command=self._zapisz,
            bg="#2471a3", fg="white", relief=tk.FLAT, font=("Arial", 10, "bold"),
            padx=20, pady=6, state=tk.DISABLED, cursor="hand2")
        self.btn_zapisz.pack(side=tk.RIGHT)
        tk.Label(stopka, text="Zapis wiąże kod z Id kartoteki — nie zmienia BOM-u.",
                 fg="#7f8c8d", font=("Arial", 8)).pack(side=tk.RIGHT, padx=12)

        panel = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=6)
        panel.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 6))

        lewa = tk.Frame(panel)
        # NAZWA jest pierwsza i najszersza, bo dla pozycji bez numeru rysunku
        # to ONA jest tożsamością — po niej człowiek lokalizuje detal.
        # Kolumna „Nr rysunku" zostaje PUSTA, gdy numeru nie ma: wcześniej
        # pokazywaliśmy tam symbol wyliczony z nazwy („ERTALONTRANSP"),
        # co sugerowało, że taki kod istnieje w bazie — a nie istnieje
        # (zgłoszone 09.09.2026: „po chuj mi on?").
        # NR RYSUNKU PRZED NAZWĄ — tak czyta się BOM i tak stoi w arkuszu
        # (zgłoszone 15.09.2026). Dla pozycji BEZ numeru kolumna zostaje pusta;
        # tożsamością jest wtedy nazwa, dlatego jest szeroka.
        kol = ("stan", "nr", "nazwa_rm", "ilosc", "symbol", "nazwa", "sposob")
        self.tab = ttk.Treeview(lewa, columns=kol, show="headings", height=20)
        # (klucz, nagłówek, szerokość, waga rozciągania)
        # Ostatnia kolumna MA wagę — bez tego zostawała martwa przestrzeń
        # z prawej, a „brak kartoteki" było ucięte do „brak ka…"
        # (zgłoszone 15.09.2026).
        self.KOL_LEWA = (("stan", "", 30, 0),
                         ("nr", "Nr rysunku", 110, 0),
                         ("nazwa_rm", "Nazwa (RM_BAZA)", 200, 3),
                         ("ilosc", "Ilość", 50, 0),
                         ("symbol", "Symbol Subiekt", 120, 2),
                         ("nazwa", "Nazwa Subiekt", 170, 3),
                         ("sposob", "Sposób", 110, 1))
        for c, tekst, szer, waga in self.KOL_LEWA:
            self.tab.heading(c, text=tekst)
            # stretch=False na wąskich kolumnach: bez tego Tk rozdziela
            # nadmiar po równo i „Ilość" robi się szersza niż nazwa.
            self.tab.column(c, width=szer, minwidth=max(30, szer // 2),
                            anchor="w", stretch=bool(waga))
        for stan, (_opis, kolor) in D.OPIS_STANU.items():
            self.tab.tag_configure(stan, background=kolor)
        self.tab.tag_configure("decyzja", background="#d6eaf8")

        # PASEK POZIOMY — bez niego przy wąskim oknie końcówki nazw znikały
        # bez żadnego znaku, że jest tam więcej treści (zgłoszone 15.09.2026).
        # Siatka zamiast pack: pack nie umie ułożyć dwóch pasków wokół tabeli
        # tak, żeby poziomy nie wchodził pod pionowy.
        vs = ttk.Scrollbar(lewa, orient="vertical", command=self.tab.yview)
        hs = ttk.Scrollbar(lewa, orient="horizontal", command=self.tab.xview)
        self.tab.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.tab.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        lewa.rowconfigure(0, weight=1)
        lewa.columnconfigure(0, weight=1)
        self.tab.bind("<<TreeviewSelect>>", self._pokaz_kandydatow)
        # Kolumny mają rosnąć razem z oknem, a nie zostawiać pustkę z prawej.
        self.tab.bind("<Configure>", lambda e: self._rozciagnij(
            self.tab, self.KOL_LEWA, e.width))
        panel.add(lewa, minsize=560)

        prawa = tk.Frame(panel)
        tk.Label(prawa, text="Szczegóły dopasowania", anchor="w",
                 font=("Arial", 10, "bold")).pack(fill=tk.X, pady=(0, 4))
        self.lbl_poz = tk.Label(prawa, text="— wybierz pozycję —", anchor="w",
                                justify="left", font=("Consolas", 10),
                                bg="#f8f9fa", padx=10, pady=8)
        self.lbl_poz.pack(fill=tk.X)

        szuk = tk.Frame(prawa)
        szuk.pack(fill=tk.X, pady=(8, 4))
        tk.Label(szuk, text="Szukaj w Subiekcie:", font=("Arial", 9)).pack(side=tk.LEFT)
        self.var_szukaj = tk.StringVar()
        we = tk.Entry(szuk, textvariable=self.var_szukaj, font=("Consolas", 10))
        we.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        # Filtrowanie w trakcie pisania — fuzzy najwyżej ustawia kolejność,
        # nigdy niczego nie zaznacza.
        we.bind("<KeyRelease>", lambda _e: self._szukaj())

        self.lbl_kand = tk.Label(prawa, text="Kandydaci", anchor="w",
                                 font=("Arial", 9, "bold"))
        self.lbl_kand.pack(fill=tk.X, pady=(6, 2))

        # Przełącznik dla zakładki „Podpowiedzi": numery rysunku z jednej
        # rodziny projektów są do siebie podobne z natury („ZP179-401.00ZZ"
        # vs „ZP196-000.00ZZ" = 0.75) i potrafią wypchnąć trafienie po nazwie.
        # Domyślnie ZOSTAJĄ — bywa, że w kodzie siedzi numer katalogowy
        # producenta („19247_DSNU-25-80-PPV-A"), który jest najlepszym kluczem.
        self.var_bez_numeru = tk.BooleanVar(value=False)
        self.chk_bez_nr = tk.Checkbutton(
            prawa, text="podpowiadaj tylko po nazwie (pomiń nr rysunku)",
            variable=self.var_bez_numeru, font=("Arial", 8), fg="#7f8c8d",
            anchor="w", command=self._przelicz_podpowiedzi)
        self.chk_bez_nr.pack(fill=tk.X)

        # PRZYCISKI PAKOWANE PRZED TABELĄ i przypięte do DOŁU. Tabela ma
        # expand=True, więc zapakowana wcześniej zabierała całą wysokość
        # panelu i wypychała „Przypisz wybraną" poza krawędź
        # (zgłoszone 09.09.2026 — ta sama pułapka co w raporcie po zapisie).
        akcje = tk.Frame(prawa)
        akcje.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))
        tk.Button(akcje, text="Przypisz wybraną", command=self._przypisz,
                  bg="#2471a3", fg="white", relief=tk.FLAT,
                  font=("Arial", 9, "bold"), padx=14, pady=5).pack(side=tk.LEFT)
        tk.Button(akcje, text="⛓ Odepnij", command=self._odepnij,
                  padx=12, pady=5).pack(side=tk.LEFT, padx=6)

        # Tabela + pasek w osobnej ramce: mieszanie side=LEFT/RIGHT z
        # side=BOTTOM w jednym rodzicu daje nieprzewidywalny układ.
        ramka2 = tk.Frame(prawa)
        ramka2.pack(fill=tk.BOTH, expand=True)
        # Dwie ostatnie kolumny wypełnia tylko zakładka „Podpowiedzi";
        # przy zwykłych kandydatach zostają puste (to trafienia dokładne,
        # więc „podobieństwo 1.00" byłoby szumem).
        # Stan i cena obok kandydata: przy wyborze z kilku podobnych kartotek
        # to one mówią, która jest ŻYWA (kupowana, na stanie), a która to
        # martwy duplikat sprzed lat (zgłoszone 15.09.2026).
        # „Podob." i „Dopasowano" wypełnia tylko zakładka „Podpowiedzi".
        kol2 = ("symbol", "nazwa", "stan", "cena", "wynik", "skad")
        self.tab2 = ttk.Treeview(ramka2, columns=kol2, show="headings", height=14)
        # Szerokości bazowe MUSZĄ zmieścić się w minsize panelu (440 px),
        # inaczej tabela startuje ścięta i user musi przewijać w poziomie,
        # żeby w ogóle zobaczyć cenę (zgłoszone 15.09.2026 — „tragedia").
        # Suma niżej: 100+130+55+60+45+70 = 460, a nadmiar rozdziela
        # _rozciagnij(); przy węższym oknie kolumny z wagą się kurczą.
        self.KOL_PRAWA = (("symbol", "Symbol", 95, 2),
                          ("nazwa", "Nazwa", 120, 3),
                          ("stan", "Na st.", 48, 0),
                          ("cena", "Cena", 55, 0),
                          ("wynik", "Podob.", 45, 0),
                          ("skad", "Skąd", 62, 0))
        for c, tekst, szer, waga in self.KOL_PRAWA:
            self.tab2.heading(c, text=tekst)
            self.tab2.column(c, width=szer, minwidth=max(30, szer // 2),
                             anchor=("e" if c in ("stan", "cena") else "w"),
                             stretch=bool(waga))
        vs2 = ttk.Scrollbar(ramka2, orient="vertical", command=self.tab2.yview)
        hs2 = ttk.Scrollbar(ramka2, orient="horizontal", command=self.tab2.xview)
        self.tab2.configure(yscrollcommand=vs2.set, xscrollcommand=hs2.set)
        self.tab2.grid(row=0, column=0, sticky="nsew")
        vs2.grid(row=0, column=1, sticky="ns")
        hs2.grid(row=1, column=0, sticky="ew")
        ramka2.rowconfigure(0, weight=1)
        ramka2.columnconfigure(0, weight=1)
        self.tab2.bind("<Double-1>", lambda _e: self._przypisz())
        self.tab2.bind("<Configure>", lambda e: self._rozciagnij(
            self.tab2, self.KOL_PRAWA, e.width))
        # Suwak PanedWindow zmienia szerokość paneli, a <Configure> tabeli
        # potrafi przyjść, zanim Tk przeliczy układ. Stąd przeliczenie także
        # po ruchu suwaka, z opóźnieniem (zgłoszone 15.09.2026 — kolumny
        # ucięte mimo miejsca w oknie).
        panel.bind("<ButtonRelease-1>",
                   lambda _e: self.after(30, self._dopasuj_kolumny))
        self.bind("<Configure>",
                  lambda e: (self.after(30, self._dopasuj_kolumny)
                             if e.widget is self else None))
        panel.add(prawa, minsize=420)

    @staticmethod
    def _rozciagnij(tabela, opis_kolumn, szerokosc=None):
        """Dopasowuje szerokości kolumn do szerokości tabeli — w obie strony.

        ttk sam rozciąga kolumny ze `stretch=True`, ale PO RÓWNO: nazwa
        dostawała tyle samo co „Ilość". Tu różnica idzie proporcjonalnie do
        wagi, a kolumny liczbowe (stan, cena, podobieństwo) zostają wąskie.

        ⚠️ Działa w OBIE strony. Pierwsza wersja tylko dodawała nadmiar, więc
        gdy suma szerokości bazowych przekraczała panel, tabela zostawała
        ścięta i cena była widoczna dopiero po przewinięciu w poziomie
        (zgłoszone 15.09.2026). Teraz brak miejsca kurczy kolumny z wagą,
        aż do ich `minwidth`.
        """
        if szerokosc is None:
            szerokosc = tabela.winfo_width()
        # Przy budowie okna winfo_width() to jeszcze 1 — nie ma czego liczyć.
        if szerokosc <= 1:
            return
        baza = sum(k[2] for k in opis_kolumn)
        waga = sum(k[3] for k in opis_kolumn)
        if waga <= 0:
            return
        roznica = szerokosc - baza - 4          # 4 px na obramowanie
        for klucz, _t, szer, w in opis_kolumn:
            if not w:
                continue
            nowa = szer + int(roznica * w / waga)
            tabela.column(klucz, width=max(max(30, szer // 2), nowa))

    # ── wczytywanie ────────────────────────────────────────────────────
    def _wczytaj_async(self, wymus=False):
        self.lbl_licznik.config(text="wczytuję…")
        threading.Thread(target=self._worker, args=(wymus,), daemon=True).start()

    def _worker(self, wymus):
        blad = None
        try:
            import subiekt_projekt as sp
            katalog = S.wczytaj_katalog_subiekta(
                tylko_cache=not wymus) or []
            indeks = D.Indeks(katalog)
            items = sp.read_project_items(self.project_id)
            pozycje = D.przygotuj_pozycje(items, indeks)
            wiek = None
            try:
                wiek = S.katalog_wiek_h()
            except Exception:
                pass
        except Exception as e:
            blad, indeks, pozycje, wiek, katalog = str(e), None, [], None, []
        self.after(0, lambda: self._wczytano(indeks, pozycje, wiek, blad, katalog))

    def _wczytano(self, indeks, pozycje, wiek, blad, katalog=()):
        if not self.winfo_exists():
            return
        if blad:
            self.lbl_licznik.config(text="błąd")
            messagebox.showerror("Dopasowanie", blad, parent=self)
            return
        self.indeks, self.pozycje = indeks, pozycje
        # Katalog trzymamy osobno od indeksu: podpowiedzi przechodzą po
        # WSZYSTKICH kartotekach licząc podobieństwo, a indeks umie tylko
        # szukać po dokładnym kluczu.
        self.katalog = list(katalog or [])
        self._zajete = D.zajete_symbole(pozycje)
        p = D.podsumowanie(pozycje)
        gotowe = p[D.STAN_ZAPAMIETANE] + p[D.STAN_SYMBOL]
        decyzji = p[D.STAN_NAZWA] + p[D.STAN_NIEJEDNOZNACZNE]
        self.lbl_licznik.config(text=(
            f"{len(pozycje)} elementów znormalizowanych   ·   "
            f"✓ {gotowe} dopasowanych   ·   "
            f"⚠ {decyzji} do decyzji   ·   "
            f"✕ {p[D.STAN_BRAK]} bez kartoteki"))
        self.lbl_katalog.config(text=(
            f"Kartoteka Subiekta: {len(indeks)} pozycji"
            + (f" · pobrana {wiek:.0f} h temu" if wiek else "")))
        self._ustaw_zakladke(self.zakladka)

    def _odswiez_katalog(self):
        self._wczytaj_async(wymus=True)

    # ── lista ──────────────────────────────────────────────────────────
    def _ustaw_zakladke(self, n):
        self.zakladka = n
        for i, b in enumerate(self.btn_zakladki):
            b.config(bg="#2471a3" if i == n else "#ffffff",
                     fg="white" if i == n else "#2c3e50")
        self._odswiez_liste()

    def _czy_podpowiedzi(self):
        """Czy jesteśmy na zakładce z propozycjami (a nie z trafieniami)."""
        return self.ZAKLADKI[self.zakladka][0] == self.ZAKL_PODPOWIEDZI

    def _podpowiedzi_dla(self, p):
        """Propozycje dla pozycji — liczone raz i trzymane przy pozycji.

        Liczenie jest kosztowne (3254 kartoteki × kilka porównań na pozycję),
        więc wynik zostaje w `p`. Zmiana przełącznika „bez numeru rysunku"
        unieważnia cache — stąd klucz w nazwie pola.
        """
        if not self.katalog:
            return []
        bez_nr = bool(self.var_bez_numeru.get())
        klucz = "_podp_bez_nr" if bez_nr else "_podp"
        if klucz not in p:
            p[klucz] = D.podpowiedzi(
                p, self.katalog, pomijaj_symbole=self._zajete,
                bez_numeru_rysunku=bez_nr)
        return p[klucz]

    def _widoczne(self):
        stany = self.ZAKLADKI[self.zakladka][1]
        fraza = self.var_filtr.get().strip().upper()
        podp = self._czy_podpowiedzi()
        out = []
        for p in self.pozycje:
            if p["stan"] not in stany:
                continue
            if fraza and fraza not in (p["nazwa_rm"] + " " + p["kod"]).upper():
                continue
            # Zakładka „Podpowiedzi" pokazuje TYLKO to, dla czego coś znaleziono
            # — reszta i tak wygląda tam identycznie jak w „Brak kartoteki".
            if podp and not self._podpowiedzi_dla(p):
                continue
            out.append(p)
        return out

    def _odswiez_liste(self):
        self.tab.delete(*self.tab.get_children())
        znaki = {D.STAN_ZAPAMIETANE: "✓", D.STAN_SYMBOL: "✓",
                 D.STAN_NAZWA: "⚠", D.STAN_NIEJEDNOZNACZNE: "?",
                 D.STAN_BRAK: "✕"}
        for p in self._widoczne():
            decyzja = self.decyzje.get(p["kod"])
            wyb = decyzja or p.get("wybrany") or {}
            sposob = ("Twój wybór" if decyzja
                      else D.OPIS_STANU[p["stan"]][0])
            # Pozycja BEZ numeru rysunku: kolumna zostaje pusta, dopóki nie ma
            # przypisania — wyliczony symbol („9261SGS-M10x1") nie istnieje
            # w RM_BAZA i sugerowanie go mylilo (zgłoszone 09.09.2026).
            # Po przypisaniu wchodzi tam symbol Z SUBIEKTA: od tej chwili to
            # ON identyfikuje pozycję (decyzja użytkownika 15.09.2026).
            # ⚠️ To tylko widok — BOM zostaje nietknięty, zapis wiąże kod z Id.
            nr = p["kod"]
            if p.get("bez_numeru"):
                nr = wyb.get("symbol") or ""
            self.tab.insert("", "end", iid=p["kod"], values=(
                znaki.get(p["stan"], ""),
                nr,
                p["nazwa_rm"] or p["kod"],
                p.get("ilosc") or "",
                wyb.get("symbol") or "—",
                (wyb.get("nazwa") or
                 (f"{len(p['kandydaci'])} kandydatów" if len(p["kandydaci"]) > 1
                  else "—")),
                sposob),
                tags=("decyzja",) if decyzja else (p["stan"],))
        for i, (etykieta, stany) in enumerate(self.ZAKLADKI):
            if etykieta == self.ZAKL_PODPOWIEDZI:
                # Licznik = ile pozycji MA propozycję, nie ile jest w stanie.
                # Liczymy tylko przy gotowym katalogu — inaczej każde odświeżenie
                # listy przemielałoby 3254 kartoteki dla wszystkich pozycji.
                ile = (sum(1 for p in self.pozycje
                           if p["stan"] in stany and self._podpowiedzi_dla(p))
                       if self.katalog else 0)
            else:
                ile = sum(1 for p in self.pozycje if p["stan"] in stany)
            self.btn_zakladki[i].config(text=f"{etykieta}  {ile}")
        self.btn_zapisz.config(
            state=tk.NORMAL if self.decyzje else tk.DISABLED,
            text=(f"💾 Zapisz decyzje ({len(self.decyzje)})"
                  if self.decyzje else "💾 Zapisz decyzje"))

    # ── kandydaci ──────────────────────────────────────────────────────
    def _biezaca_pozycja(self):
        sel = self.tab.selection()
        if not sel:
            return None
        return next((p for p in self.pozycje if p["kod"] == sel[0]), None)

    def _pokaz_kandydatow(self, _e=None):
        p = self._biezaca_pozycja()
        if not p:
            return
        self._biezaca = p["kod"]
        if p.get("bez_numeru"):
            # Nie ma numeru rysunku — mówimy wprost, że symbol jest wyliczony,
            # żeby nikt nie szukał go w RM_BAZA.
            opis_id = (f"Nazwa:        {p['nazwa_rm'] or '—'}\n"
                       f"Nr rysunku:   — (pozycja bez numeru)\n"
                       f"Symbol dla Subiekta: {p['kod']}  (wyliczony z nazwy)")
        else:
            opis_id = (f"Nazwa:        {p['nazwa_rm'] or '—'}\n"
                       f"Nr rysunku:   {p['kod']}")
        self.lbl_poz.config(text=(
            f"{opis_id}\n"
            f"Ilość:        {p.get('ilosc') or '—'}\n"
            f"Stan:         {D.OPIS_STANU[p['stan']][0]}"))
        # Szukamy po NAZWIE, gdy nie ma numeru — obcięty symbol („rolkaSITI8010")
        # gubi końcówkę i nie znajdzie nic sensownego.
        self.var_szukaj.set(p["nazwa_rm"] if p.get("bez_numeru") else p["kod"])
        if self._czy_podpowiedzi():
            self._wypelnij_podpowiedzi(p)
        else:
            self._wypelnij(p["kandydaci"], "Kandydaci z katalogu")

    def _wypelnij_podpowiedzi(self, p):
        """Panel z propozycjami — z wynikiem podobieństwa i źródłem trafienia.

        ⚠️ To NIE są kandydaci w sensie reguły jeden-do-jednego. Kolumna
        „Podobieństwo" ma przypominać, że to tylko propozycja: 1.00 znaczy
        „ten sam zapis po normalizacji", 0.70 — „może to to, sprawdź".
        """
        lista = self._podpowiedzi_dla(p)
        # Legenda kolumny „Skąd" w nagłówku — inaczej „N→S" nic nie mówi.
        self.lbl_kand.config(
            text=(f"Podpowiedzi — SPRAWDŹ przed przypisaniem ({len(lista)})"
                  "     Skąd: N=nazwa, S=symbol  (RM_BAZA→Subiekt)"))
        self.tab2.delete(*self.tab2.get_children())
        for d in lista:
            k = d["kartoteka"]
            self.tab2.insert("", "end",
                             iid=str(k.get("id") or k.get("symbol")),
                             values=(k.get("symbol") or "",
                                     k.get("nazwa") or "",
                                     "…", "…",
                                     f"{d['wynik']:.2f}",
                                     d["skad"]))
        self._dociagnij_stany([d["kartoteka"].get("symbol") for d in lista])

    def _wypelnij(self, lista, tytul):
        self.lbl_kand.config(text=f"{tytul} ({len(lista or [])})")
        self.tab2.delete(*self.tab2.get_children())
        for poz in lista or []:
            self.tab2.insert("", "end",
                             iid=str(poz.get("id") or poz.get("symbol")),
                             values=(poz.get("symbol") or "",
                                     poz.get("nazwa") or "", "…", "…", "", ""))
        self._dociagnij_stany([p.get("symbol") for p in lista or []])

    # ── stany i ceny kandydatów ────────────────────────────────────────
    def _dociagnij_stany(self, symbole):
        """Uzupełnia kolumny „Na stanie" i „Ost. cena" — w tle.

        Osobne zapytanie do Subiekta (`query_stock`), bo katalog trzyma tylko
        id/symbol/nazwę. Pyta o kilka symboli naraz, więc idzie ~0,1 s przez
        żywy most. Wynik cache'owany na czas życia okna: te same kartoteki
        wracają przy kolejnych pozycjach.
        """
        symbole = [s for s in (symbole or []) if s]
        brakujace = [s for s in symbole if s not in self._stany]
        if not brakujace:
            self._pokaz_stany(symbole)
            return
        self._pokaz_stany(symbole)   # od razu to, co już wiemy

        def worker():
            try:
                import subiekt_stany as st
                dane = st.query_stock(brakujace) or {}
            except Exception:
                dane = {}
            # Brak odpowiedzi też zapamiętujemy — inaczej każde kliknięcie
            # w tę samą pozycję próbowałoby od nowa.
            for s in brakujace:
                self._stany[s] = dane.get(s) or {}
            self.after(0, lambda: self._pokaz_stany(symbole))

        threading.Thread(target=worker, daemon=True).start()

    def _pokaz_stany(self, symbole):
        """Wpisuje stan i cenę do już narysowanych wierszy."""
        if not self.winfo_exists():
            return
        for iid in self.tab2.get_children():
            wart = list(self.tab2.item(iid, "values"))
            symbol = wart[0] if wart else ""
            d = self._stany.get(symbol)
            if d is None:
                continue          # jeszcze się liczy — zostaje „…"
            ile = d.get("Dostepne")
            cena = d.get("OstatniaCenaZakupu")
            wart[2] = "—" if ile in (None, "") else f"{float(ile):g}"
            wart[3] = "—" if cena in (None, "") else f"{float(cena):.2f}"
            self.tab2.item(iid, values=wart)

    def _przelicz_podpowiedzi(self):
        """Przełącznik „tylko po nazwie" — przelicza i odświeża widok."""
        self._odswiez_liste()
        p = self._biezaca_pozycja()
        if p and self._czy_podpowiedzi():
            self._wypelnij_podpowiedzi(p)

    def _szukaj(self):
        if not self.indeks:
            return
        fraza = self.var_szukaj.get().strip()
        if not fraza:
            p = self._biezaca_pozycja()
            if p and self._czy_podpowiedzi():
                self._wypelnij_podpowiedzi(p)
            else:
                self._wypelnij(p["kandydaci"] if p else [], "Kandydaci z katalogu")
            return
        self._wypelnij(self.indeks.szukaj(fraza), f"Wyniki: „{fraza}”")

    # ── decyzje ────────────────────────────────────────────────────────
    def _przypisz(self):
        p = self._biezaca_pozycja()
        if not p:
            messagebox.showinfo("Dopasowanie",
                                "Najpierw zaznacz pozycję po lewej.", parent=self)
            return
        sel = self.tab2.selection()
        if not sel:
            messagebox.showinfo("Dopasowanie",
                                "Zaznacz kartotekę po prawej.", parent=self)
            return
        symbol = self.tab2.set(sel[0], "symbol")
        nazwa = self.tab2.set(sel[0], "nazwa")
        poz = next((k for k in (self.indeks.katalog if self.indeks else [])
                    if (k.get("symbol") or "") == symbol), None)
        self.decyzje[p["kod"]] = {"symbol": symbol, "nazwa": nazwa,
                                  "id": (poz or {}).get("id")}
        self._odswiez_liste()
        try:
            self.tab.selection_set(p["kod"])
        except tk.TclError:
            pass

    def _odepnij(self):
        """Ta kartoteka NIE pasuje — zapamiętaj, żeby automat nie wracał."""
        p = self._biezaca_pozycja()
        if not p:
            return
        biezacy = self.decyzje.get(p["kod"]) or p.get("wybrany")
        if not biezacy:
            return
        if not messagebox.askyesno(
                "Odepnij",
                f"Zapamiętać, że „{biezacy.get('symbol')}” NIE pasuje\n"
                f"do „{p['kod']}”?\n\n"
                "Bez tego automat przypnie ją ponownie przy następnym otwarciu.",
                parent=self):
            return
        D.odrzuc(p["kod"], biezacy.get("id"), biezacy.get("symbol") or "")
        self.decyzje.pop(p["kod"], None)
        self._wczytaj_async()

    def _zapisz(self):
        if not self.decyzje:
            return
        linie = [f"   {k} → {v['symbol']}" for k, v in
                 sorted(self.decyzje.items())][:15]
        wiecej = len(self.decyzje) - len(linie)
        if not messagebox.askyesno(
                "Zapisz decyzje",
                f"Zapisać {len(self.decyzje)} powiązań?\n\n" + "\n".join(linie)
                + (f"\n   … i {wiecej} więcej" if wiecej > 0 else "")
                + "\n\nWiążemy kod z Id kartoteki. Decyzja ręczna ma\n"
                  "pierwszeństwo — automat jej nie nadpisze.",
                parent=self):
            return
        decyzje = [{"kod": k, **v} for k, v in self.decyzje.items()]
        try:
            n = D.zapisz_decyzje(decyzje)
        except Exception as e:
            messagebox.showerror("Zapis", str(e), parent=self)
            return

        # Pozycje BEZ numeru rysunku dostają symbol Subiekta jako numer —
        # po to, żeby NASTĘPNYM razem trafiły regułą jeden-do-jednego i nie
        # trzeba było ich dopasowywać ręcznie (cel całego okna: uzupełnić
        # BOM PRZED wysyłką do Subiekta, decyzja użytkownika 15.09.2026).
        pary = {}
        for p in self.pozycje:
            d = self.decyzje.get(p["kod"])
            if d and p.get("bez_numeru") and d.get("symbol"):
                pary[p.get("nazwa_rm") or ""] = {"symbol": d["symbol"],
                                                 "nazwa": d.get("nazwa") or ""}
        dopis = {"wpisane": 0, "pominiete": []}
        if pary:
            try:
                dopis = D.wpisz_numery_do_bom(self.project_id, pary)
            except Exception as e:
                # Zapis mapowań już przeszedł — nie udajemy, że wszystko padło.
                messagebox.showwarning(
                    "Numery w BOM",
                    f"Powiązania zapisane ({n}), ale numery rysunku nie:\n{e}",
                    parent=self)

        tekst = f"Zapisano {n} powiązań."
        if dopis["wpisane"]:
            tekst += (f"\n\nW arkuszu przepisano {dopis['wpisane']} pozycji "
                      "na symbol i nazwę z Subiekta.")
        if dopis["pominiete"]:
            szczegoly = "\n".join(f"   • {nz} — {powod}"
                                  for nz, powod in dopis["pominiete"][:8])
            wiecej = len(dopis["pominiete"]) - 8
            tekst += ("\n\nPominięto w BOM-ie:\n" + szczegoly
                      + (f"\n   … i {wiecej} więcej" if wiecej > 0 else ""))
        messagebox.showinfo("Zapisano", tekst, parent=self)
        self.decyzje.clear()
        self._wczytaj_async()


def open_window(parent, project_id, project_name=None):
    """Punkt wejścia dla RM_BAZA."""
    if not project_id:
        messagebox.showwarning("Dopasowanie",
                               "Najpierw wybierz projekt.", parent=parent)
        return None
    return DopasowanieWindow(parent, project_id, project_name)


if __name__ == "__main__":
    import sys
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 89
    root = tk.Tk()
    root.withdraw()
    w = open_window(root, pid, sys.argv[2] if len(sys.argv) > 2 else None)
    w.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
