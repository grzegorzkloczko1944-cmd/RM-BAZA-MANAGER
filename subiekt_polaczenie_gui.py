# -*- coding: utf-8 -*-
"""Okno „Połączenie z Subiektem" — logowanie i wylogowanie, bez grzebania w pliku.

Do zakładania stanowisk: administrator wpisuje dane raz, w oknie, zamiast
kopiować `.nexo_sfera.json` po maszynach (zgłoszone 06.09.2026 — „nie będę
przecież pisał po plikach").

Trzy przyciski i trzy różne rzeczy:

  Testuj połączenie — sprawdza dane na KOPII, nie ruszając stanowiska
  Zapisz i zaloguj  — zapisuje i restartuje most (bez restartu nic by się nie
                      zmieniło: most czyta konfigurację raz, przy starcie)
  Wyloguj           — ubija most i kasuje SAME hasła

Kolejność „testuj, potem zapisz" jest celowa: gdyby test szedł po zapisie,
literówka w haśle nadpisywałaby działające połączenie i stanowisko zostawałoby
z niczym.
"""

import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import subiekt_konfig as konfig
from rm_kreciolek import Kreciolek

TLO = "#ecf0f1"
TLO_SEKCJI = "#ffffff"
TEKST = "#2c3e50"
TEKST_SZARY = "#7f8c8d"
OBRAMOWANIE = "#bdc3c7"


class OknoPolaczenia(tk.Toplevel, Kreciolek):
    """Edytor danych logowania do Subiekta. Tylko dla ADMIN-a."""

    def __init__(self, rodzic):
        super().__init__(rodzic)
        self.title("Połączenie z Subiektem")
        self.configure(bg=TLO)
        self.transient(rodzic)
        self.resizable(False, False)

        dane = konfig.wczytaj()
        self.var_serwer = tk.StringVar(value=dane.get("serwer", ""))
        self.var_baza = tk.StringVar(value=dane.get("baza", ""))
        self.var_win_auth = tk.IntVar(value=1 if dane.get("sqlWindowsAuth") else 0)
        self.var_sql_user = tk.StringVar(value=dane.get("sqlUser", ""))
        self.var_sql_haslo = tk.StringVar(value=dane.get("sqlHaslo", ""))
        self.var_nexo_login = tk.StringVar(value=dane.get("nexoLogin", ""))
        self.var_nexo_haslo = tk.StringVar(value=dane.get("nexoHaslo", ""))
        self.var_sdk = tk.StringVar(value=dane.get("sdkBin", ""))

        self._buduj()
        self._przelacz_auth()
        self.update_idletasks()
        try:
            from subiekt_stany import wysrodkuj
            wysrodkuj(self, rodzic)
        except Exception:
            pass
        self.grab_set()

    # ── budowa ─────────────────────────────────────────────────────────────
    def _buduj(self):
        tk.Label(self, text="Połączenie z Subiektem nexo PRO", bg=TLO, fg=TEKST,
                 font=("Arial", 12, "bold")).pack(anchor="w", padx=16, pady=(14, 0))
        tk.Label(self, text="Dane logowania tego stanowiska. Most używa ich przy każdym starcie.",
                 bg=TLO, fg=TEKST_SZARY, font=("Arial", 9)
                 ).pack(anchor="w", padx=16, pady=(2, 10))

        # ── baza ──
        ramka = self._sekcja("Baza danych")
        self._pole(ramka, "Serwer SQL", self.var_serwer,
                   "adres serwera, np. 192.168.100.4")
        self._pole(ramka, "Baza", self.var_baza,
                   "nazwa bazy nexo (z przedrostkiem, jeśli jest)")

        # ── logowanie SQL ──
        ramka = self._sekcja("Logowanie do SQL Servera")
        wiersz = tk.Frame(ramka, bg=TLO_SEKCJI)
        wiersz.pack(fill=tk.X, padx=12, pady=(2, 4))
        tk.Radiobutton(wiersz, text="użytkownik SQL", variable=self.var_win_auth,
                       value=0, command=self._przelacz_auth, bg=TLO_SEKCJI,
                       activebackground=TLO_SEKCJI, font=("Arial", 9)
                       ).pack(side=tk.LEFT)
        tk.Radiobutton(wiersz, text="autoryzacja Windows (bez hasła)",
                       variable=self.var_win_auth, value=1,
                       command=self._przelacz_auth, bg=TLO_SEKCJI,
                       activebackground=TLO_SEKCJI, font=("Arial", 9)
                       ).pack(side=tk.LEFT, padx=(14, 0))
        self.pole_sql_user = self._pole(ramka, "Użytkownik", self.var_sql_user, "")
        self.pole_sql_haslo = self._pole(ramka, "Hasło", self.var_sql_haslo, "",
                                         haslo=True)

        # ── operator nexo ──
        ramka = self._sekcja("Operator nexo")
        tk.Label(ramka, text="To samo, czym logujesz się do Subiekta.",
                 bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8)
                 ).pack(anchor="w", padx=12)
        self._pole(ramka, "Login", self.var_nexo_login,
                   "pole „Login” z Konfiguracja → Użytkownicy")
        self._pole(ramka, "Hasło", self.var_nexo_haslo, "", haslo=True)

        # ── SDK ──
        ramka = self._sekcja("Biblioteki Sfery")
        wiersz = tk.Frame(ramka, bg=TLO_SEKCJI)
        wiersz.pack(fill=tk.X, padx=12, pady=(2, 8))
        tk.Label(wiersz, text="Katalog Bin", bg=TLO_SEKCJI, fg=TEKST,
                 width=14, anchor="w", font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Entry(wiersz, textvariable=self.var_sdk, width=38,
                 font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Button(wiersz, text="Wybierz…", command=self._wybierz_sdk,
                  font=("Arial", 8), cursor="hand2").pack(side=tk.LEFT, padx=(6, 0))

        # ── przyciski ──
        dol = tk.Frame(self, bg=TLO)
        dol.pack(fill=tk.X, padx=16, pady=(6, 4))
        tk.Button(dol, text="Wyloguj", command=self._wyloguj,
                  font=("Arial", 9), cursor="hand2", width=10).pack(side=tk.LEFT)
        tk.Button(dol, text="Zamknij", command=self.destroy,
                  font=("Arial", 9), cursor="hand2", width=10).pack(side=tk.RIGHT)
        tk.Button(dol, text="Zapisz i zaloguj", command=self._zapisz_i_zaloguj,
                  font=("Arial", 9, "bold"), cursor="hand2", width=16,
                  bg="#27ae60", fg="white", activebackground="#1e8449"
                  ).pack(side=tk.RIGHT, padx=(0, 6))
        tk.Button(dol, text="Testuj połączenie", command=self._testuj,
                  font=("Arial", 9), cursor="hand2", width=15
                  ).pack(side=tk.RIGHT, padx=(0, 6))

        self.status = tk.Label(self, text="", bg=TLO, fg=TEKST_SZARY,
                               anchor="w", font=("Arial", 9), wraplength=520,
                               justify="left")
        self.status.pack(fill=tk.X, padx=16, pady=(0, 12))
        self._pokaz_stan_poczatkowy()

    def _sekcja(self, tytul):
        ramka = tk.Frame(self, bg=TLO_SEKCJI, highlightthickness=1,
                         highlightbackground=OBRAMOWANIE)
        ramka.pack(fill=tk.X, padx=16, pady=(0, 8))
        tk.Label(ramka, text=tytul, bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9, "bold")).pack(anchor="w", padx=12, pady=(8, 2))
        return ramka

    def _pole(self, rodzic, etykieta, zmienna, podpowiedz, haslo=False):
        wiersz = tk.Frame(rodzic, bg=TLO_SEKCJI)
        wiersz.pack(fill=tk.X, padx=12, pady=2)
        tk.Label(wiersz, text=etykieta, bg=TLO_SEKCJI, fg=TEKST, width=14,
                 anchor="w", font=("Arial", 9)).pack(side=tk.LEFT)
        entry = tk.Entry(wiersz, textvariable=zmienna, width=28,
                         font=("Arial", 9), show="•" if haslo else "")
        entry.pack(side=tk.LEFT)
        if podpowiedz:
            tk.Label(wiersz, text=podpowiedz, bg=TLO_SEKCJI, fg=TEKST_SZARY,
                     font=("Arial", 8)).pack(side=tk.LEFT, padx=(8, 0))
        if not haslo and rodzic.winfo_children()[-1] is wiersz:
            wiersz.pack_configure(pady=(2, 8) if etykieta in ("Baza",) else 2)
        return entry

    def _przelacz_auth(self):
        """Autoryzacja Windows nie używa loginu i hasła SQL — wyszarzamy je."""
        stan = tk.DISABLED if self.var_win_auth.get() else tk.NORMAL
        for pole in (self.pole_sql_user, self.pole_sql_haslo):
            try:
                pole.config(state=stan)
            except tk.TclError:
                pass

    def _wybierz_sdk(self):
        katalog = filedialog.askdirectory(
            parent=self, title="Katalog Bin z bibliotekami Sfery",
            initialdir=self.var_sdk.get() or r"C:\iLogic")
        if katalog:
            self.var_sdk.set(katalog.replace("/", "\\"))

    # ── stan ───────────────────────────────────────────────────────────────
    def _zebrane(self):
        return {
            "serwer": self.var_serwer.get().strip(),
            "baza": self.var_baza.get().strip(),
            "sqlWindowsAuth": bool(self.var_win_auth.get()),
            "sqlUser": self.var_sql_user.get().strip(),
            "sqlHaslo": self.var_sql_haslo.get(),
            "nexoLogin": self.var_nexo_login.get().strip(),
            "nexoHaslo": self.var_nexo_haslo.get(),
            "sdkBin": self.var_sdk.get().strip(),
        }

    def _pokaz_stan_poczatkowy(self):
        if not konfig.istnieje():
            self.status.config(
                text="Stanowisko nie ma jeszcze skonfigurowanego połączenia.",
                fg="#a04000")
            return
        try:
            import subiekt_bridge as most
            dane = most.ping(timeout=2)
        except Exception:
            dane = None
        if dane:
            self.status.config(text="Most działa — połączenie z Subiektem czynne.",
                               fg="#1e8449")
        else:
            self.status.config(text="Most nie działa. Zapisz i zaloguj, żeby go podnieść.",
                               fg=TEKST_SZARY)

    def _blokuj(self, blokada):
        for w in self.winfo_children():
            for przycisk in getattr(w, "winfo_children", lambda: [])():
                if isinstance(przycisk, tk.Button):
                    try:
                        przycisk.config(state=tk.DISABLED if blokada else tk.NORMAL)
                    except tk.TclError:
                        pass

    # ── akcje ──────────────────────────────────────────────────────────────
    def _testuj(self):
        """Sprawdza dane na KOPII — konfiguracja stanowiska zostaje nietknięta."""
        dane = self._zebrane()
        brak = konfig.braki(dane)
        if brak:
            messagebox.showwarning("Połączenie z Subiektem",
                                   "Uzupełnij:\n\n• " + "\n• ".join(brak),
                                   parent=self)
            return
        self._blokuj(True)
        self.start_kreciolek("Sprawdzam połączenie z Subiektem")
        threading.Thread(target=self._testuj_worker, args=(dane,),
                         daemon=True).start()

    def _testuj_worker(self, dane):
        try:
            sciezka = konfig.zapisz_tymczasowo(dane)
            from subiekt_stany import _find_exe
            import subprocess
            exe = _find_exe()
            if not exe:
                self.after(0, lambda: self._po_tescie(False, "Nie znaleziono NexoRecon.exe."))
                return
            # Tryb „stan" bez symboli: najlżejsza komenda, która i tak przechodzi
            # pełną drogę — połączenie z SQL i logowanie operatora.
            proc = subprocess.run(
                [exe, "kontrahenci", "--limit=1", sciezka],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            ok = proc.returncode == 0
            komunikat = (proc.stdout or "") + (proc.stderr or "")
            self.after(0, lambda: self._po_tescie(ok, komunikat.strip()))
        except Exception as e:
            blad = str(e)
            self.after(0, lambda: self._po_tescie(False, blad))

    def _po_tescie(self, ok, komunikat):
        self.stop_kreciolek("")
        self._blokuj(False)
        if ok:
            self.status.config(text="Połączenie działa. Możesz zapisać.", fg="#1e8449")
            return
        self.status.config(text="Połączenie nie działa — szczegóły w okienku.",
                           fg="#c0392b")
        # Komunikaty mostu rozróżniają poziom błędu (kod 2 = SQL/baza/licencja,
        # kod 3 = zły login operatora) i mówią, co sprawdzić — pokazujemy je
        # wprost, zamiast zastępować własnym „coś poszło nie tak".
        messagebox.showerror("Połączenie nie działa",
                             komunikat[:1500] or "Most nie podał powodu.",
                             parent=self)

    def _zapisz_i_zaloguj(self):
        dane = self._zebrane()
        brak = konfig.braki(dane)
        if brak:
            messagebox.showwarning("Połączenie z Subiektem",
                                   "Uzupełnij:\n\n• " + "\n• ".join(brak),
                                   parent=self)
            return
        self._blokuj(True)
        self.start_kreciolek("Zapisuję i loguję do Subiekta")
        threading.Thread(target=self._zapisz_worker, args=(dane,),
                         daemon=True).start()

    def _zapisz_worker(self, dane):
        try:
            konfig.zapisz(dane)
            # RESTART MOSTU JEST KONIECZNY. Most czyta konfiguracje raz, przy
            # starcie procesu - bez tego dalej uzywalby starych danych
            # i "zapisalem nowe haslo, a nic sie nie zmienilo".
            import subiekt_bridge as most
            most.zatrzymaj_most()
            # Bez tego poprawienie zlego hasla nic nie daje: po pierwszej
            # nieudanej probie most jest zapamietany jako niedostepny do konca
            # procesu RM_BAZA i kolejny start w ogole nie rusza.
            most.pozwol_na_ponowna_probe()
            most.zapewnij_most()
            dziala = bool(most.ping(timeout=5))
            self.after(0, lambda: self._po_zapisie(dziala))
        except Exception as e:
            # ⚠️ LAPIEMY WSZYSTKO. Kazda droga z tego watku MUSI skonczyc sie
            # wywolaniem _po_zapisie, bo tam gasnie kreciolek i odblokowuja sie
            # przyciski. Wyjatek, ktory tu ucieknie, zostawia okno kreccace
            # sie w nieskonczonosc (zgloszone 06.09.2026: "kreci i nic").
            blad = "%s: %s" % (type(e).__name__, e)
            self.after(0, lambda: self._po_zapisie(False, blad))

    def _po_zapisie(self, ok, blad=""):
        self.stop_kreciolek("")
        self._blokuj(False)
        if ok:
            self.status.config(text="Zapisano. Most działa — Subiekt jest połączony.",
                               fg="#1e8449")
            return
        self.status.config(text="Zapisano, ale most nie wstał.", fg="#c0392b")
        messagebox.showerror(
            "Połączenie z Subiektem",
            "Dane zostały zapisane, ale most się nie podniósł.\n\n"
            + (blad[:1000] if blad else
               "Sprawdź „Testuj połączenie” — pokaże powód."),
            parent=self)

    def _wyloguj(self):
        if not messagebox.askyesno(
                "Wylogowanie z Subiektem",
                "Zatrzymac most i skasowac zapisane hasla?\n\n"
                "Serwer, baza i loginy zostana - przy powrocie wystarczy "
                "wpisac hasla ponownie.",
                parent=self):
            return

        # Hasla kasujemy ZAWSZE, nawet gdy mostu nie da sie ubic. Odwrotna
        # kolejnosc zostawialaby hasla na dysku, gdyby ubijanie sie wysypalo.
        konfig.wyczysc_hasla()
        self.var_sql_haslo.set("")
        self.var_nexo_haslo.set("")

        # ⚠️ SPRAWDZAMY, CZY MOST NAPRAWDE PADL. zatrzymaj_most() zwraca
        # False, gdy ping akurat nie odpowie, a wczesniejsza wersja ten wynik
        # ignorowala i pisala "Most zatrzymany" niezaleznie od faktow -
        # uzytkownik wylogowal sie i dalej widzial ONLINE (06.09.2026).
        zyje = True
        try:
            import subiekt_bridge as most
            most.zatrzymaj_most()
            zyje = bool(most.ping(timeout=3))
            if zyje:                    # jedna ponowna proba, ping bywa spozniony
                most.zatrzymaj_most()
                zyje = bool(most.ping(timeout=3))
            most.pozwol_na_ponowna_probe()
        except Exception:
            zyje = False                # mostu nie ma czym zapytac = nie zyje

        if zyje:
            self.status.config(
                text="Hasla skasowane, ale mostu nie udalo sie zatrzymac - "
                     "dziala do konca sesji.", fg="#c0392b")
        else:
            self.status.config(text="Wylogowano. Most zatrzymany, hasla skasowane.",
                               fg="#a04000")
        self._odswiez_panel()

    def _odswiez_panel(self):
        """Kaze otwartemu panelowi Subiekta przerysowac stan mostu.

        Bez tego panel zostaje z napisem "Most Subiekta: ONLINE" po
        wylogowaniu - stan byl odczytany przy jego otwarciu i nikt go nie
        odswieza (06.09.2026).
        """
        try:
            for okno in self.master.winfo_children():
                odswiez = getattr(okno, "odswiez_stan_mostu", None)
                if callable(odswiez):
                    odswiez()
        except Exception:
            pass                        # panel moze byc zamkniety


def _sprawdz_haslo_admina(rodzic, master_con):
    """Pyta o haslo ADMIN-a i porownuje z master.sqlite. True = wpuszczamy.

    Model dostepu (ustalony 06.09.2026): administrator siada na stanowisku
    ZALOGOWANYM NA ZWYKLEGO USERA, swoim haslem odblokowuje to jedno
    narzedzie, konfiguruje polaczenie z Subiektem i odchodzi. Sesja RM_BAZA
    ANI NA MOMENT nie zmienia uzytkownika — nie podnosimy roli, nie
    przelogowujemy, nie dotykamy current_user_role. Odblokowane zostaje
    wylacznie to okno.

    ⚠️ PYTAMY ZA KAZDYM OTWARCIEM. Gdyby odblokowanie zylo do konca sesji,
    user po odejsciu administratora miałby otwarte drzwi do hasel Subiekta.

    Haslo porownujemy tak samo, jak RM_BAZA robi to przy zmianie uzytkownika
    (`on_user_selected`): sha256 wobec `password_hash` z tabeli `users`.
    Zadnej wlasnej kryptografii ani osobnego hasla do zapamietania.
    """
    import hashlib
    import sqlite3

    admini = []
    try:
        master_con.commit()             # zwolnij locki przed SELECT
        kursor = master_con.execute(
            "SELECT username, password_hash FROM users "
            "WHERE role = 'ADMIN' AND is_active = 1 AND password_hash IS NOT NULL")
        admini = [(u, h) for u, h in kursor.fetchall() if h]
    except (sqlite3.Error, AttributeError) as e:
        messagebox.showerror(
            "Polaczenie z Subiektem",
            "Nie udalo sie sprawdzic uprawnien:\n" + str(e), parent=rodzic)
        return False

    if not admini:
        messagebox.showerror(
            "Polaczenie z Subiektem",
            "W bazie nie ma aktywnego konta ADMIN z haslem.\n\n"
            "Bez tego nie da sie potwierdzic uprawnien do zmiany danych "
            "logowania Subiekta.", parent=rodzic)
        return False

    dlg = tk.Toplevel(rodzic)
    dlg.title("Uprawnienia administratora")
    dlg.configure(bg=TLO)
    dlg.transient(rodzic)
    dlg.resizable(False, False)

    tk.Label(dlg, text="Polaczenie z Subiektem", bg=TLO, fg=TEKST,
             font=("Arial", 11, "bold")).pack(anchor="w", padx=20, pady=(16, 0))
    tk.Label(dlg, text="Dane logowania do Subiekta zmienia administrator.\n"
                       "Podaj haslo ADMIN-a, zeby otworzyc okno.",
             bg=TLO, fg=TEKST_SZARY, font=("Arial", 9), justify="left"
             ).pack(anchor="w", padx=20, pady=(4, 12))

    var = tk.StringVar()
    entry = tk.Entry(dlg, textvariable=var, show="*", width=30, font=("Arial", 10))
    entry.pack(padx=20)
    entry.focus_set()

    wynik = {"ok": False}

    def zatwierdz():
        podane = hashlib.sha256(var.get().encode()).hexdigest()
        if any(podane == h for _, h in admini):
            wynik["ok"] = True
            dlg.destroy()
        else:
            messagebox.showerror("Uprawnienia", "Nieprawidlowe haslo.", parent=dlg)
            var.set("")
            entry.focus_set()

    przyciski = tk.Frame(dlg, bg=TLO)
    przyciski.pack(fill=tk.X, padx=20, pady=14)
    tk.Button(przyciski, text="Anuluj", command=dlg.destroy, width=10,
              font=("Arial", 9), cursor="hand2").pack(side=tk.RIGHT)
    tk.Button(przyciski, text="Otworz", command=zatwierdz, width=10,
              font=("Arial", 9, "bold"), cursor="hand2",
              bg="#27ae60", fg="white", activebackground="#1e8449"
              ).pack(side=tk.RIGHT, padx=(0, 6))
    entry.bind("<Return>", lambda _e: zatwierdz())

    dlg.update_idletasks()
    try:
        from subiekt_stany import wysrodkuj
        wysrodkuj(dlg, rodzic)
    except Exception:
        pass
    dlg.grab_set()
    dlg.wait_window()
    return wynik["ok"]


def otworz(rodzic, master_con, rola=None):
    """Otwiera okno po potwierdzeniu haslem ADMIN-a.

    Haslo pytane ZAWSZE, takze gdy sesja jest juz na koncie ADMIN. Powod:
    "zamkniecie narzedzia i ponowne otwarcie — znowu haslo ADMIN"
    (06.09.2026). Wyjatek dla roli ADMIN oznaczalby, ze na stanowisku
    zalogowanym na admina okno stoi otworem bez zadnego potwierdzenia.

    `rola` przyjmowana tylko po to, by nie zmieniac sygnatury przy
    ewentualnym zlagodzeniu tej zasady — dzis nie ma wplywu na dostep.
    """
    if not _sprawdz_haslo_admina(rodzic, master_con):
        return None
    return OknoPolaczenia(rodzic)
