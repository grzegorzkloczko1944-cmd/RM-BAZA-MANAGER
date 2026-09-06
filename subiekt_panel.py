# -*- coding: utf-8 -*-
"""Panel narzędzi Subiekta — jedno wejście zamiast rozwijanego menu.

    import subiekt_panel
    subiekt_panel.open_window(arkusz)          # arkusz = okno główne RM_BAZA

Dlaczego panel, a nie menu: przy dziewięciu narzędziach problemem nie jest
liczba kliknięć, tylko DECYZJA, które kliknąć. Menu podaje same nazwy —
panel pokazuje obok nich żywe liczby („4 pozycje poniżej minimum”, „5
otwartych ZD”), więc widać stan, zanim się cokolwiek otworzy. Przed stałym
mostem byłoby to nie do pomyślenia: każdy licznik kosztowałby ~10 s.

Kafle niosą też informację, której menu nie dawało wcale: co tylko CZYTA,
a co ZAPISUJE do produkcyjnej bazy Subiekta. Trójkąt ostrzegawczy dostają
wyłącznie operacje NIEODWRACALNE — gdyby miały go wszystkie zapisy, znaczyłby
tyle co nic.
"""

import queue
import threading
import tkinter as tk

from subiekt_stany import wysrodkuj

# ── paleta ──────────────────────────────────────────────────────────────────
TLO = "#f4f6f8"
TLO_SEKCJI = "#ffffff"
OBRAMOWANIE = "#dfe4ea"
TEKST = "#2c3e50"
TEKST_SZARY = "#7f8c8d"

#: Kolory kafla wg rodzaju operacji. Odczyt na chłodno, zapis cieplej,
#: nieodwracalny wyraźnie — user ma to widzieć, nie czytać.
RODZAJE = {
    "odczyt":       dict(ramka="#d6e4f0", tlo="#f2f8fd", etykieta="ODCZYT",
                         kolor_etykiety="#2980b9", tlo_etykiety="#eaf3fb"),
    "zapis":        dict(ramka="#d6e4f0", tlo="#ffffff", etykieta="ZAPIS",
                         kolor_etykiety="#e67e22", tlo_etykiety="#fdf2e6"),
    "nieodwracalny": dict(ramka="#f0b27a", tlo="#fef6f0", etykieta="ZAPIS",
                          kolor_etykiety="#c0392b", tlo_etykiety="#fdedec"),
}


class Kafel(tk.Frame):
    """Klikalny kafel: ikona, tytuł, opis, etykieta rodzaju i miejsce na licznik."""

    def __init__(self, rodzic, ikona, tytul, opis, rodzaj, akcja, szerokosc=250):
        styl = RODZAJE[rodzaj]
        super().__init__(rodzic, bg=styl["tlo"], highlightthickness=1,
                         highlightbackground=styl["ramka"], cursor="hand2")
        self._styl = styl
        self._akcja = akcja
        # ŻADNEGO configure(width=…): kafle stoją w pack(expand=True), więc
        # szerokość ustala rząd. Zadeklarowana szerokość walczyła z packiem
        # przy każdym przerysowaniu (np. gdy dochodził licznik) i okno drżało.

        gora = tk.Frame(self, bg=styl["tlo"])
        gora.pack(fill=tk.X, padx=10, pady=(10, 0))
        tk.Label(gora, text=ikona, bg=styl["tlo"], font=("Segoe UI Emoji", 16)
                 ).pack(side=tk.LEFT, padx=(0, 8))
        podpis = tk.Frame(gora, bg=styl["tlo"])
        podpis.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(podpis, text=tytul, bg=styl["tlo"], fg=TEKST, anchor="w",
                 font=("Arial", 10, "bold")).pack(fill=tk.X)
        tk.Label(podpis, text=opis, bg=styl["tlo"], fg=TEKST_SZARY, anchor="w",
                 font=("Arial", 8), justify="left").pack(fill=tk.X)
        if rodzaj == "nieodwracalny":
            tk.Label(gora, text="⚠", bg=styl["tlo"], fg="#e67e22",
                     font=("Segoe UI Emoji", 12)).pack(side=tk.RIGHT)

        # Licznik dopisuje się po odpytaniu mostu — do tego czasu kropki,
        # żeby panel otwierał się natychmiast, a nie po sekundzie.
        self.lbl_licznik = tk.Label(self, text="", bg=styl["tlo"], fg="#34495e",
                                    anchor="w", font=("Arial", 8, "bold"),
                                    justify="left")
        self.lbl_licznik.pack(fill=tk.X, padx=10, pady=(4, 0))

        dol = tk.Frame(self, bg=styl["tlo"])
        dol.pack(fill=tk.X, padx=10, pady=(6, 10))
        tk.Label(dol, text=f" {styl['etykieta']} ", bg=styl["tlo_etykiety"],
                 fg=styl["kolor_etykiety"], font=("Arial", 7, "bold")
                 ).pack(side=tk.LEFT)
        tk.Label(dol, text="›", bg=styl["tlo"], fg=TEKST_SZARY,
                 font=("Arial", 12)).pack(side=tk.RIGHT)

        self._podepnij(self)

    def _podepnij(self, widget):
        """Cały kafel ma się zachowywać jak JEDEN przycisk.

        Tkinter wysyła Leave także wtedy, gdy kursor wchodzi na dziecko
        (etykietę, ikonę) — kafel „gubił” wtedy obramowanie, choć mysz
        wciąż była nad nim. Dlatego Enter/Leave podpinamy pod WSZYSTKIE
        widgety, a decyzję podejmujemy po tym, gdzie kursor faktycznie
        jest (winfo_containing), nie po tym, który widget zgłosił zdarzenie
        (zgłoszone 06.09.2026).
        """
        widget.bind("<Button-1>", lambda _e: self._akcja())
        widget.bind("<Enter>", lambda _e: self._podswietl(True))
        # Zdarzenie niesie widget, NA KTÓRY kursor wszedł — to pewniejsze niż
        # pytanie o pozycję myszy po fakcie, bo przy szybkim ruchu kursor
        # bywa już gdzie indziej, zanim zdążymy sprawdzić.
        widget.bind("<Leave>", self._sprawdz_wyjscie)
        # Łapka nad CAŁYM kaflem, także nad tekstem — inaczej kursor
        # zmieniał się w strzałkę i kafel przestawał wyglądać na klikalny.
        try:
            widget.configure(cursor="hand2")
        except tk.TclError:
            pass                        # nie każdy widget przyjmuje cursor
        for dziecko in widget.winfo_children():
            self._podepnij(dziecko)

    def _sprawdz_wyjscie(self, event):
        """Gaś podświetlenie tylko, gdy kursor opuścił CAŁY kafel.

        Przy przejściu na dziecko tkinter wysyła Leave z rodzica, ale pole
        `event.widget` zdarzenia Enter, które zaraz nastąpi, wskazuje na to
        dziecko. Zamiast zgadywać kolejność, pytamy wprost, co jest teraz
        pod kursorem — a gdy tkinter nie potrafi odpowiedzieć (kursor
        „pomiędzy”), zostawiamy podświetlenie i sprawdzamy jeszcze raz
        po chwili.
        """
        def sprawdz():
            try:
                if not self.winfo_exists():
                    return
                pod = self.winfo_containing(self.winfo_pointerx(),
                                            self.winfo_pointery())
            except (tk.TclError, KeyError):
                return                  # obcy widget albo kafel zniknął
            if pod is None:
                # Tkinter nie wie, co jest pod kursorem (mysz nad granicą
                # widgetów albo poza oknem). Nie zgadujemy — zostawiamy
                # obramowanie i sprawdzimy przy następnym ruchu; gaszenie
                # „na wszelki wypadek” dawało migotanie w połowie ruchu.
                return
            self._podswietl(self._moje(pod))
        try:
            # Krótka zwłoka, nie after_idle: w chwili Leave kursor bywa
            # jeszcze nad granicą widgetów i winfo_containing zwraca None,
            # co gasiło obramowanie w połowie ruchu.
            self.after(30, sprawdz)
        except tk.TclError:
            pass

    def _moje(self, widget):
        """Czy ten widget to kafel albo cokolwiek w jego środku."""
        while widget is not None:
            if widget is self:
                return True
            widget = getattr(widget, "master", None)
        return False

    def _podswietl(self, wlaczone):
        """Podświetlenie zmienia KOLOR obramowania, nigdy jego grubość.

        Wcześniej to samo robiło configure() na całym kaflu, a kafle stoją
        w pack(fill=BOTH, expand=True) — każda zmiana wymuszała przeliczenie
        układu rzędu i sąsiednie kafle skakały o piksel (zgłoszone
        06.09.2026). Zmiana samego koloru nie rusza geometrii.
        """
        kolor = "#2980b9" if wlaczone else self._styl["ramka"]
        try:
            if self.cget("highlightbackground") != kolor:
                self.configure(highlightbackground=kolor,
                               highlightcolor=kolor)
        except tk.TclError:
            pass                        # kafel zniknął razem z panelem

    def licznik(self, tekst):
        try:
            self.lbl_licznik.config(text=tekst)
        except tk.TclError:
            return                  # panel zamknięty w trakcie liczenia
        # Licznik („109 dokumentów · 7 ZD") jest szerszy niż tytuł kafla,
        # a dochodzi PO wysrodkowaniu okna — geometria byla juz zamrozona
        # na rozmiarze sprzed liczenia, wiec ostatni kafel w rzedzie
        # wychodzil poza kadr (zgloszone 06.09.2026). Panel sam sie
        # dociaga, gdy uklad zaczyna zadac wiecej miejsca.
        try:
            self.winfo_toplevel().dociagnij_szerokosc()
        except (tk.TclError, AttributeError):
            pass


def _etykieta_aktualizacji():
    """„Pobierz" na stanowisku z .exe, „Zbuduj" u dewelopera."""
    try:
        import subiekt_bridge as b
        return "⬇  Pobierz most" if b.czy_z_binarki() else "🔨  Zbuduj teraz"
    except Exception:
        return "🔨  Zbuduj teraz"


class PanelSubiekt(tk.Toplevel):
    """Okno z kaflami. Liczniki dociągane w tle, po otwarciu."""

    def __init__(self, arkusz):
        super().__init__(arkusz)
        self.arkusz = arkusz
        self.title("Subiekt — narzędzia")
        self.configure(bg=TLO)
        self.transient(arkusz)
        self.kafle = {}
        #: Wszystkie kafle — do zgaszenia podświetleń, gdy mysz opuści panel.
        self._wszystkie_kafle = []
        #: Ustawiane przy zamykaniu — wątek liczników sprawdza to między
        #: zapytaniami i przerywa, zamiast trzymać most zajęty dla okna,
        #: którego już nie ma.
        self._przerwane = False

        self._naglowek()
        self._sekcje()
        self._stopka()

        self.update_idletasks()
        wysrodkuj(self, arkusz)
        # Okno nie moze zejsc ponizej tego, czego zada uklad kafli — inaczej
        # ostatni kafel w rzedzie wychodzi poza kadr i widac go w polowie.
        try:
            self.minsize(self.winfo_reqwidth(), self.winfo_reqheight())
        except tk.TclError:
            pass

        # Wyniki z wątku roboczego wracają KOLEJKĄ, nie przez after().
        # Samo after() też dotyka tkintera, więc wołane spoza wątku głównego
        # rzuca „main thread is not in main loop” — a wtedy panel zostaje
        # z pustymi licznikami i nikt nie wie dlaczego.
        # Mysz poza panelem = żaden kafel nie może zostać podświetlony.
        # Bez tego obramowanie potrafiło „zawisnąć”, gdy kursor wyjechał
        # z okna zbyt szybko, żeby złapać to zdarzeniem Leave kafla.
        self.bind("<Leave>", self._zgas_wszystkie)

        self._wyniki = queue.Queue()
        self.after(120, self._odbierz_wyniki)
        threading.Thread(target=self._policz_w_tle, daemon=True).start()

    def _zgas_wszystkie(self, _event=None):
        for k in self._wszystkie_kafle:
            try:
                k._podswietl(False)
            except tk.TclError:
                pass

    def _odbierz_wyniki(self):
        """Puls z wątku głównego: nakłada to, co policzył wątek roboczy."""
        try:
            while True:
                akcja = self._wyniki.get_nowait()
                try:
                    akcja()
                except tk.TclError:
                    return                  # panel zamknięty
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            if self.winfo_exists():
                self.after(120, self._odbierz_wyniki)
        except tk.TclError:
            pass

    def dociagnij_szerokosc(self):
        """Poszerza okno, gdy uklad zaczal zadac wiecej niz okno ma teraz.

        Wolane przez kafle po nalozeniu licznika. Tylko POSZERZA i tylko
        w poziomie: zwezanie szarpaloby oknem przy kazdym liczniku, a wysokosc
        ustala liczba sekcji, ktora sie nie zmienia. Pozycja zostaje ta sama,
        zeby okno nie odskakiwalo uzytkownikowi spod myszy.
        """
        try:
            self.update_idletasks()
            trzeba = self.winfo_reqwidth()
            if trzeba <= self.winfo_width():
                return
            # Nie wypychamy poza ekran — przy bardzo dlugich licznikach
            # lepiej lekko sciesnic kafle niz schowac brzeg okna.
            trzeba = min(trzeba, self.winfo_screenwidth() - 40)
            x = min(self.winfo_x(), max(0, self.winfo_screenwidth() - trzeba - 20))
            self.geometry(f"{trzeba}x{self.winfo_height()}+{x}+{self.winfo_y()}")
            self.minsize(trzeba, self.winfo_reqheight())
        except tk.TclError:
            pass                        # panel zamkniety w trakcie liczenia

    # ── budowa ──────────────────────────────────────────────────────────────
    def _naglowek(self):
        pas = tk.Frame(self, bg=TLO)
        pas.pack(fill=tk.X, padx=14, pady=(14, 0))

        # Skróty: kto wie, czego szuka, nie musi czytać całej siatki.
        skroty = tk.Frame(pas, bg=TLO_SEKCJI, highlightthickness=1,
                          highlightbackground=OBRAMOWANIE)
        skroty.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Label(skroty, text="Szybkie skróty", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 10, "bold"), anchor="w").pack(fill=tk.X, padx=12, pady=(10, 6))
        rzad = tk.Frame(skroty, bg=TLO_SEKCJI)
        rzad.pack(fill=tk.X, padx=12, pady=(0, 4))
        for ikona, etykieta, akcja in (
                ("🏬", "Magazyn", self._akcja("open_subiekt_magazyn")),
                ("🛒", "Zamówienia ZD", self._akcja("open_subiekt_zamowienia")),
                ("📚", "Dokumenty", self._akcja("open_subiekt_dokumenty"))):
            b = tk.Button(rzad, text=f"{ikona}  {etykieta}", command=akcja,
                          bg="white", fg=TEKST, relief=tk.SOLID, bd=1,
                          font=("Arial", 9), padx=12, pady=6, cursor="hand2")
            b.pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(skroty, text="Najczęściej używane. Pełen zestaw poniżej.",
                 bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8), anchor="w"
                 ).pack(fill=tk.X, padx=12, pady=(0, 10))

        # Stan mostu — na stałe, zamiast okienka wyskakującego przy awarii.
        most = tk.Frame(pas, bg="#f0fbf4", highlightthickness=1,
                        highlightbackground="#c8e6d4")
        most.pack(side=tk.LEFT, fill=tk.BOTH, padx=(12, 0))
        tk.Label(most, text="Stan mostu", bg="#f0fbf4", fg=TEKST,
                 font=("Arial", 10, "bold"), anchor="w").pack(fill=tk.X, padx=12, pady=(10, 6))
        self.lbl_most = tk.Label(most, text="⏳  sprawdzam…", bg="#f0fbf4",
                                 fg=TEKST_SZARY, font=("Arial", 9), anchor="w",
                                 justify="left")
        self.lbl_most.pack(fill=tk.X, padx=12, pady=(0, 10))
        # Przycisk budowania pokazujemy TYLKO, gdy binarka jest nieaktualna —
        # widoczny zawsze kusiłby do klikania bez potrzeby.
        # Etykieta zalezy od tego, jak dziala RM_BAZA: ze zrodel most sie
        # BUDUJE, z .exe — POBIERA z serwera (nie ma tam ani zrodel, ani dotneta).
        self.btn_buduj = tk.Button(most, text=_etykieta_aktualizacji(),
                                   command=self._zbuduj, bg="#27ae60", fg="white",
                                   relief=tk.FLAT, font=("Arial", 9, "bold"),
                                   padx=12, pady=5, cursor="hand2")

    def _sekcje(self):
        """Trzy obszary. Bez numeracji — to nie są kroki do wykonania po kolei."""
        uklad = [
            ("Praca z projektem", "Odczyt danych i operacje na projekcie", [
                ("🔍", "Sprawdź w Subiekcie", "kolumna SUBIEKT, szybki odczyt",
                 "odczyt", "sprawdz_w_subiekcie", None),
                ("📊", "Stany projektu", "stany pozycji projektu",
                 "odczyt", "open_subiekt_stany", "stany"),
                ("🏗", "Załóż projekt", "kartoteki + komplety + ZK",
                 "nieodwracalny", "open_subiekt_projekt", None),
            ]),
            ("Zakupy i magazyn", "Stany, zamówienia i dokumenty", [
                ("🏬", "Magazyn", "stany, progi min/opt, zamówienia na skład",
                 "odczyt", "open_subiekt_magazyn", "magazyn"),
                ("🛒", "Zamówienia do dostawców", "ZD",
                 "zapis", "open_subiekt_zamowienia", "zapotrzebowanie"),
                ("📚", "Przegląd dokumentów", "ZK / ZD / RW / WZ",
                 "odczyt", "open_subiekt_dokumenty", "dokumenty"),
            ]),
            ("Kartoteki i mapowania", "Porządkowanie danych podstawowych", [
                ("🗂", "Asortyment", "wszystkie kartoteki, ceny, skład kompletów",
                 "zapis", "open_subiekt_asortyment", "asortyment"),
                ("➕", "Nowa kartoteka", "dodaj do Subiekta",
                 "nieodwracalny", "open_subiekt_nowa_kartoteka", None),
                ("🤝", "Powiąż dostawców", "z kontrahentami",
                 "zapis", "open_subiekt_dostawcy", None),
                ("🔗", "Scal kody handlowe", "w tym projekcie",
                 "zapis", "open_subiekt_scalanie", None),
            ]),
        ]
        for tytul, podtytul, kafle in uklad:
            ramka = tk.Frame(self, bg=TLO_SEKCJI, highlightthickness=1,
                             highlightbackground=OBRAMOWANIE)
            ramka.pack(fill=tk.X, padx=14, pady=(12, 0))

            naglowek = tk.Frame(ramka, bg=TLO_SEKCJI)
            naglowek.pack(fill=tk.X, padx=12, pady=(10, 2))
            tk.Label(naglowek, text=tytul, bg=TLO_SEKCJI, fg=TEKST,
                     font=("Arial", 11, "bold")).pack(side=tk.LEFT)
            tk.Label(naglowek, text="   " + podtytul, bg=TLO_SEKCJI,
                     fg=TEKST_SZARY, font=("Arial", 9)).pack(side=tk.LEFT)

            rzad = tk.Frame(ramka, bg=TLO_SEKCJI)
            rzad.pack(fill=tk.X, padx=12, pady=(4, 12))
            for ikona, nazwa, opis, rodzaj, metoda, klucz in kafle:
                k = Kafel(rzad, ikona, nazwa, opis, rodzaj, self._akcja(metoda))
                k.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
                if klucz:
                    self.kafle[klucz] = k
                self._wszystkie_kafle.append(k)

    def _stopka(self):
        s = tk.Frame(self, bg=TLO)
        s.pack(fill=tk.X, padx=14, pady=10)
        self.status = tk.Label(s, text="", bg=TLO, fg=TEKST_SZARY,
                               font=("Arial", 8), anchor="w")
        self.status.pack(side=tk.LEFT)
        tk.Button(s, text="Zamknij", command=self.destroy, bg="#34495e",
                  fg="white", relief=tk.FLAT, padx=16, pady=4,
                  cursor="hand2").pack(side=tk.RIGHT)

    # ── działanie ───────────────────────────────────────────────────────────
    def _akcja(self, nazwa_metody):
        """Zamyka panel i otwiera właściwe narzędzie."""
        def uruchom():
            metoda = getattr(self.arkusz, nazwa_metody, None)
            if not callable(metoda):
                self.status.config(text=f"Brak funkcji: {nazwa_metody}")
                return
            # Kolejność ma znaczenie: najpierw ZATRZYMAJ liczenie, potem
            # zamknij panel, dopiero na końcu otwórz narzędzie. Wątek
            # liczników potrafi trzymać most zajęty (np. odczytem
            # zapotrzebowania), a wtedy okno otwarte natychmiast czeka
            # w kolejce mostu i wygląda, jakby się nie ładowało
            # (zgłoszone 06.09.2026).
            self._przerwane = True
            self.destroy()
            self.arkusz.after(60, metoda)
        return uruchom

    def _zbuduj(self):
        import subiekt_bridge as b
        self.lbl_most.config(text="⏳  aktualizuję most…")
        self.update_idletasks()

        def w_tle():
            ok, komunikat = b.zaktualizuj_most()
            self._wyniki.put(lambda: self._po_buildzie(ok, komunikat))
        threading.Thread(target=w_tle, daemon=True).start()

    def _po_buildzie(self, ok, komunikat):
        from tkinter import messagebox
        (messagebox.showinfo if ok else messagebox.showerror)(
            "Budowanie mostu", komunikat, parent=self)
        if ok:
            self.btn_buduj.pack_forget()
        threading.Thread(target=self._policz_w_tle, daemon=True).start()

    def odswiez_stan_mostu(self):
        """Przerysowuje stan mostu i liczniki. Wola to okno logowania po
        zmianie danych polaczenia albo wylogowaniu — bez tego panel zostaje
        z napisem ONLINE po ubiciu mostu (06.09.2026)."""
        try:
            self.lbl_most.config(text="⏳  sprawdzam…")
        except tk.TclError:
            return                      # panel zamkniety
        threading.Thread(target=self._policz_w_tle, daemon=True).start()

    def _policz_w_tle(self):
        """Stan mostu i liczniki kafli. W wątku, żeby panel otwierał się od razu."""
        import subiekt_bridge as b

        if self._przerwane:
            return
        try:
            dane = b.ping()
        except Exception:
            dane = None

        if not dane:
            aktualny = True
            try:
                from subiekt_stany import _find_exe
                aktualny = b._zna_tryb_server(_find_exe())
            except Exception:
                pass
            self._wyniki.put(lambda: self._most_offline(aktualny))
            return

        try:
            s = b.status()
        except Exception:
            s = {}
        self._wyniki.put(lambda: self._most_online(s))

        # Most dziala, ale na serwerze moze lezec NOWSZY. Bez tego user
        # zostawal na wersji sprzed optymalizacji i nie mial jak sie
        # dowiedziec, ze istnieje szybsza — ostrzezenie o buildzie wypada
        # tylko wtedy, gdy most w ogole nie wstaje (06.09.2026).
        # Sam odczyt jest bramkowany dobowo w subiekt_bridge, wiec to nie
        # oznacza ruchu po dysku sieciowym przy kazdym otwarciu panelu.
        try:
            nowszy, opis = b.dostepna_nowsza()
        except Exception:
            nowszy, opis = False, ""
        if nowszy and not self._przerwane:
            self._wyniki.put(lambda: self._proponuj_aktualizacje(opis))

        # Liczniki dopiero po potwierdzeniu, że most żyje — inaczej każdy
        # kafel czekałby na timeout osobno.
        self._liczniki()

    def _proponuj_aktualizacje(self, opis):
        """Dopisuje informacje o nowszej wersji i pokazuje przycisk pobrania.

        NIE pobieramy sami: most restartuje sie przy aktualizacji, a user
        moze byc w srodku operacji na Subiekcie. Decyzja nalezy do niego,
        tak jak przy budowaniu.
        """
        try:
            self.lbl_most.config(
                text=self.lbl_most.cget("text") + "\n\u2b06  " + opis)
            # Etykieta z mostu: u usera "Pobierz most", u budujacego
            # "Zbuduj teraz" - zaktualizuj_most() i tak rozpoznaje,
            # co zrobic na tym stanowisku.
            self.btn_buduj.config(text=_etykieta_aktualizacji())
            self.btn_buduj.pack(padx=12, pady=(0, 12))
        except tk.TclError:
            pass                    # panel zamkniety w miedzyczasie

    def _most_offline(self, binarka_aktualna):
        self.lbl_most.config(
            text=("🔴  Most Subiekta: OFFLINE\n"
                  + ("Binarka nieaktualna — zbuduj most."
                     if not binarka_aktualna else
                     "Wystartuje przy pierwszej operacji.")),
            fg="#c0392b")
        if not binarka_aktualna:
            self.btn_buduj.pack(padx=12, pady=(0, 12))

    def _most_online(self, s):
        logins = s.get("logins", "?")
        ms = s.get("last_request_ms") or 0
        # logins > 1 znaczy, że sesja padła i wstała — warto to widzieć,
        # bo inaczej restarty dzieją się po cichu.
        ostrzezenie = "  ⚠ sesja wstawała ponownie" if isinstance(logins, int) and logins > 1 else ""
        self.lbl_most.config(
            text=(f"🟢  Most Subiekta: ONLINE\n"
                  f"Ostatnia operacja: {ms/1000:.1f} s\n"
                  f"Logowań do Sfery: {logins}{ostrzezenie}"),
            fg="#1e8449")

    def _liczniki(self):
        """Żywe liczby na kaflach — to one zmieniają panel w pulpit."""
        def ustaw(klucz, tekst):
            k = self.kafle.get(klucz)
            if k:
                self._wyniki.put(lambda: k.licznik(tekst))

        for klucz in self.kafle:
            ustaw(klucz, "…")

        # Katalog idzie PIERWSZY, bo jest najtańszy z odczytów (~9 s bez
        # stanów) — kafel dostaje liczbę, zanim magazyn dopyta o stany.
        if self._przerwane:
            return
        try:
            import subiekt_asortyment_gui as ag
            kart = ag.pobierz_katalog()
            komplety = sum(1 for p in kart if ag._czy_komplet(p))
            ustaw("asortyment", f"{len(kart)} kartotek"
                                + (f" · {komplety} kompletów" if komplety else ""))
        except Exception:
            ustaw("asortyment", "")

        if self._przerwane:
            return
        try:
            import subiekt_magazyn_gui as mg
            poz = mg.pobierz_magazyn(tylko_niezerowe=True)
            ponizej = sum(1 for p in poz
                          if float(p.get("StanMinimalny") or 0) > 0
                          and float(p.get("Dostepne") or 0) < float(p.get("StanMinimalny") or 0))
            ustaw("magazyn", f"{len(poz)} kartotek ze stanem"
                             + (f" · {ponizej} poniżej minimum" if ponizej else ""))
        except Exception:
            ustaw("magazyn", "")

        if self._przerwane:
            return
        try:
            import subiekt_zamowienia as sz
            pozycje, _podmioty, zamowione = sz.pobierz_zapotrzebowanie()
            ustaw("zapotrzebowanie",
                  f"{len(pozycje)} pozycji do zamówienia"
                  + (f" · {len(zamowione)} już zamówionych" if zamowione else ""))
        except Exception:
            ustaw("zapotrzebowanie", "")

        if self._przerwane:
            return
        try:
            import subiekt_dokumenty_gui as dg
            dokumenty = dg.pobierz_dokumenty()
            zd_otwarte = sum(1 for d in dokumenty
                             if d.get("rodzaj") == "ZD"
                             and "realizacj" in (d.get("status") or "").lower())
            ustaw("dokumenty", f"{len(dokumenty)} dokumentów"
                               + (f" · {zd_otwarte} ZD do realizacji" if zd_otwarte else ""))
        except Exception:
            ustaw("dokumenty", "")

        # „Stany projektu" liczymy z BOM-u, nie z Subiekta — bez otwartego
        # projektu nie ma czego pokazać.
        try:
            pid = getattr(self.arkusz, "current_project_id", None)
            if pid:
                from subiekt_stany import read_project_drawings
                ustaw("stany", f"{len(read_project_drawings(pid))} pozycji w projekcie")
            else:
                ustaw("stany", "otwórz projekt w arkuszu")
        except Exception:
            ustaw("stany", "")

        self._wyniki.put(lambda: self.status.config(text=""))


def open_window(arkusz):
    return PanelSubiekt(arkusz)
