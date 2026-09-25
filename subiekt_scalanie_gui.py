# -*- coding: utf-8 -*-
"""
Okno „Scal kody handlowe" — połączenie kilku wierszy BOM w jeden.

Wywołanie z RM_BAZA (menu 📦 SUBIEKT), TYLKO przy locku:

    import subiekt_scalanie_gui
    subiekt_scalanie_gui.open_window(parent, project_id=52, project_name="2627 …")

Po co: elementy handlowe nie mają numeru rysunku, więc ich identyfikatorem
jest kod katalogowy wpisywany ręcznie — a ten sam kod bywa zapisany różnie
('UCFL 201' / 'UCFL201-12'). W arkuszu to dwie pozycje, w RFQ dwa zapytania,
w Subiekcie dwie kartoteki z rozbitą historią cen.

Obsługa — trzy kroki, bez ukrytych gestów:
    1. klikasz wiersze, które są tą samą rzeczą (☐ → ☑),
    2. pole „Nazwa po scaleniu" wypełnia się samo najczęstszym zapisem
       z firmy — możesz je poprawić,
    3. „Scal zaznaczone": stare wiersze znikają, powstaje jeden z sumą ilości.

Dlaczego wymagany jest lock i zapis idzie przez db_manager.project_con:
przy locku arkusz pracuje na LOKALNEJ kopii projektu, a zwolnienie locka
kopiuje ją na serwer. Zapis do pliku na serwerze z pominięciem tej kopii
nie byłby widoczny w arkuszu, a przy zwolnieniu locka zostałby NADPISANY.
Ten sam wzorzec ma „Ukryj zaznaczone".
"""

import os
import shutil
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

import subiekt_scalanie as S

# Kopie przed zmianą — osobny podkatalog, żeby nie mieszać z backupami
# RM_BAZA, które mają własny harmonogram i czyszczenie.
BACKUP_DIR = os.path.join(os.path.dirname(S.PROJECTS_DIR), "backups", "scalanie_kodow")


class OknoDialog(tk.Toplevel):
    """Własne okno zamiast messagebox.

    Systemowy messagebox skleja wszystko w jeden akapit jednolitą czcionką —
    przy liście „kod + kod → nazwa (ilość)" nie da się odróżnić nagłówka od
    pozycji ani starego zapisu od nowego. Tutaj każda część ma swój styl,
    a lista scalanych pozycji dostaje czcionkę o stałej szerokości i własne
    tło, żeby kolumny się zgadzały.
    """

    TLO = "#f5f6f7"

    def __init__(self, parent, tytul, naglowek, ikona="ℹ", kolor="#2980b9"):
        super().__init__(parent)
        self.wynik = False
        self.title(tytul)
        self.transient(parent)
        self.configure(bg=self.TLO)
        self.resizable(False, False)

        pasek = tk.Frame(self, bg=kolor, height=54)
        pasek.pack(side=tk.TOP, fill=tk.X)
        pasek.pack_propagate(False)
        tk.Label(pasek, text=ikona, bg=kolor, fg="white",
                 font=("Segoe UI Emoji", 18)).pack(side=tk.LEFT, padx=(14, 8))
        tk.Label(pasek, text=naglowek, bg=kolor, fg="white", anchor="w",
                 font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.tresc = tk.Frame(self, bg=self.TLO)
        self.tresc.pack(fill=tk.BOTH, expand=True, padx=18, pady=(14, 6))

        self.stopka = tk.Frame(self, bg=self.TLO)
        self.stopka.pack(fill=tk.X, padx=18, pady=(4, 14))

    # ── elementy treści ────────────────────────────────────────────────────
    def akapit(self, tekst, pogrubiony=False, kolor="#2c3e50", odstep=(0, 6)):
        tk.Label(self.tresc, text=tekst, bg=self.TLO, fg=kolor, anchor="w",
                 justify=tk.LEFT, wraplength=560,
                 font=("Segoe UI", 10, "bold" if pogrubiony else "normal")
                 ).pack(fill=tk.X, pady=odstep)

    def ramka_pozycji(self, wiersze, wysokosc=9):
        """Lista scalanych pozycji — stała szerokość znaku, żeby się równały."""
        ramka = tk.Frame(self.tresc, bg="white", bd=1, relief=tk.SOLID)
        ramka.pack(fill=tk.BOTH, expand=True, pady=(2, 8))
        txt = tk.Text(ramka, height=min(len(wiersze), wysokosc), width=64,
                      font=("Consolas", 9), bg="white", fg="#2c3e50",
                      bd=0, padx=10, pady=8, wrap="none")
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        if len(wiersze) > wysokosc:
            vs = ttk.Scrollbar(ramka, orient="vertical", command=txt.yview)
            txt.configure(yscrollcommand=vs.set)
            vs.pack(side=tk.RIGHT, fill=tk.Y)
        txt.tag_configure("stare", foreground="#7f8c8d")
        txt.tag_configure("nowe", foreground="#1e8449", font=("Consolas", 9, "bold"))
        txt.tag_configure("strzalka", foreground="#b03a2e")
        for w in wiersze:
            if isinstance(w, tuple):
                stare, nowe = w
                txt.insert("end", f"{stare}", "stare")
                txt.insert("end", "   →   ", "strzalka")
                txt.insert("end", f"{nowe}\n", "nowe")
            else:
                txt.insert("end", f"{w}\n")
        txt.configure(state=tk.DISABLED)

    def ostrzezenie(self, tekst):
        ramka = tk.Frame(self.tresc, bg="#fdf3e3", bd=1, relief=tk.SOLID)
        ramka.pack(fill=tk.X, pady=(2, 8))
        tk.Label(ramka, text=tekst, bg="#fdf3e3", fg="#8a5a00", anchor="w",
                 justify=tk.LEFT, wraplength=540, font=("Segoe UI", 9)
                 ).pack(fill=tk.X, padx=10, pady=7)

    def sciezka(self, etykieta, wartosc):
        tk.Label(self.tresc, text=etykieta, bg=self.TLO, fg="#7f8c8d", anchor="w",
                 font=("Segoe UI", 8)).pack(fill=tk.X, pady=(4, 0))
        tk.Label(self.tresc, text=wartosc, bg=self.TLO, fg="#5d6d7e", anchor="w",
                 justify=tk.LEFT, wraplength=560, font=("Consolas", 8)
                 ).pack(fill=tk.X)

    # ── przyciski ──────────────────────────────────────────────────────────
    def przyciski(self, potwierdz=None, anuluj="Zamknij", kolor="#2980b9"):
        def zamknij(wynik):
            self.wynik = wynik
            self.destroy()

        tk.Button(self.stopka, text=anuluj, command=lambda: zamknij(False),
                  font=("Segoe UI", 9), padx=16, pady=6,
                  bg="#e5e8e8", relief=tk.FLAT).pack(side=tk.RIGHT)
        if potwierdz:
            tk.Button(self.stopka, text=potwierdz, command=lambda: zamknij(True),
                      font=("Segoe UI", 9, "bold"), padx=18, pady=6,
                      bg=kolor, fg="white", relief=tk.FLAT, cursor="hand2"
                      ).pack(side=tk.RIGHT, padx=(0, 8))
            self.bind("<Return>", lambda _e: zamknij(True))
        self.bind("<Escape>", lambda _e: zamknij(False))

    def pokaz(self):
        self.update_idletasks()
        try:
            rodzic = self.master
            x = rodzic.winfo_rootx() + (rodzic.winfo_width() - self.winfo_width()) // 2
            y = rodzic.winfo_rooty() + (rodzic.winfo_height() - self.winfo_height()) // 3
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except Exception:
            pass
        self.grab_set()
        self.wait_window()
        return self.wynik


class ScalanieWindow(tk.Toplevel):
    COLS = [
        ("zaz",      "",                       34, "c"),
        # Uklad jak w arkuszu RM_BAZA: Nr rysunku · Nazwa · Opis · Ilosc —
        # user porownuje oba okna obok siebie i szuka tych samych kolumn
        # w tej samej kolejnosci (zyczenie uzytkownika 25.09.2026).
        ("rysunek",  "Nr rysunku",            110, "w"),
        ("kod",      "Nazwa",                 220, "w"),
        ("opis",     "Opis",                  170, "w"),
        # Ilosc zaraz po Opisie — kolejnosc z arkusza. Material tuz za nia:
        # rozny material to najczestszy sygnal, ze dwa podobne kody to jednak
        # inne elementy, wiec ma byc widoczny przy pozycji, nie na koncu.
        ("ilosc",    "Ilość BOM",              70, "e"),
        ("material", "Materiał",              110, "w"),
        ("subiekt",  "SUBIEKT (kartoteka)",   240, "w"),
        ("baza",     "Najczęściej w firmie",  170, "w"),
        ("podobne",  "Podobne w tym projekcie", 220, "w"),
    ]

    def __init__(self, parent, project_id, project_name=None):
        super().__init__(parent)
        self.project_id = project_id
        self.pozycje = []
        self._zaznaczone = set()      # klucze zaznaczonych pozycji
        # {kod: kartoteka Subiekta albo None}; None w całości = jeszcze nie
        # sprawdzone (odpytanie mostu trwa kilkanaście sekund, więc leci
        # osobnym wątkiem po narysowaniu listy).
        self._subiekt = {}
        self._subiekt_stan = "nie sprawdzono"
        # Pełna kartoteka Subiekta — do ręcznego szukania, gdy dopasowanie
        # automatyczne nic nie znalazło (kartoteka bywa pod innym zapisem).
        self._katalog = []
        # Uchwyt do otwartej wyszukiwarki. grab_set() blokuje klikanie dopiero
        # OD MOMENTU pojawienia się okna, a przy pobieraniu katalogu mija
        # kilkanaście sekund — bez tego dało się otworzyć kilka okien naraz.
        self._okno_wyszukiwania = None
        # Ręcznie wskazane kartoteki, jeszcze NIEzapisane do bazy mapowań.
        # Trafią tam dopiero przy zapisie BOM-u — inaczej przeżywałyby
        # anulowanie locka, mimo że user cofnął wszystkie zmiany.
        self._reczne = {}

        # Połączenie arkusza = LOKALNA kopia projektu (open_project_local przy
        # locku). Cały zapis idzie tędy; plik na serwerze aktualizuje dopiero
        # zwolnienie locka (sync_project_to_server), jak w reszcie RM_BAZA.
        dbm = getattr(parent, "db_manager", None)
        self.con = getattr(dbm, "project_con", None) if dbm else None
        self.local_path = None
        if dbm is not None and getattr(dbm, "local_dir", None) is not None:
            self.local_path = os.path.join(str(dbm.local_dir), f"project_{project_id}.sqlite")
        # Uruchomienie spoza RM_BAZA (test z linii poleceń) nie ma połączenia
        # arkusza — wtedy silnik pisałby wprost do pliku na serwerze, czyli
        # dokładnie tam, gdzie NIE wolno. Taki tryb tylko do odczytu.
        self.tylko_podglad = self.con is None or not getattr(dbm, "is_local", False)

        tytul = f"Scal kody handlowe — projekt {project_id}"
        if project_name:
            tytul += f" ({project_name})"
        self.title(tytul)
        self.transient(parent)
        self._wysrodkuj(parent, 1100, 620)

        self._build_ui()
        # ESC zamyka okno (zyczenie uzytkownika 25.09.2026).
        #
        # ⚠️ `_na_escape`, nie `_zamknij` wprost: w polu nazwy ESC ma NAJPIERW
        # schowac liste podpowiedzi (bind na `ent_nazwa`), a dopiero drugie
        # wcisniecie zamknac okno. Bez tego user zamykalby cale okno,
        # probujac tylko zwinac podpowiedzi.
        self.bind("<Escape>", self._na_escape)
        self._pokaz_wiek_katalogu()
        # Licznik idzie dalej, gdy okno stoi otwarte — inaczej „sprzed 5 min"
        # wisiałoby godzinami.
        self._tykanie_wieku()
        self.after(100, self._load_async)

    def _tykanie_wieku(self):
        try:
            self._pokaz_wiek_katalogu()
        except tk.TclError:
            return                      # okno zamknięte
        self.after(60_000, self._tykanie_wieku)

    def _wysrodkuj(self, parent, szer, wys):
        """Na środku okna RM_BAZA — czyli na tym monitorze, gdzie ono stoi.

        winfo_screenwidth() zwraca wymiar ekranu głównego, więc przy dwóch
        monitorach okno lądowałoby nie tam, gdzie użytkownik patrzy. Liczymy
        od pozycji rodzica; przycinamy tylko tyle, żeby nie wyjść poza
        krawędź jego monitora.
        """
        try:
            parent.update_idletasks()
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            if pw <= 1 or ph <= 1:          # okno jeszcze nierozłożone
                raise ValueError
            x = px + (pw - szer) // 2
            y = py + (ph - wys) // 2
            # Górna krawędź musi zostać widoczna — inaczej nie da się okna
            # przesunąć myszą.
            y = max(y, py - 20 if py > 0 else 0)
        except Exception:
            x = (self.winfo_screenwidth() - szer) // 2
            y = (self.winfo_screenheight() - wys) // 2
        self.geometry(f"{szer}x{wys}+{x}+{y}")

    # ── UI ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        top = tk.Frame(self, bg="#34495e", height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🔗 Scalanie kodów elementów handlowych",
                 bg="#34495e", fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)

        # Wiek kartotek dużą czcionką — od tego zależy, czy temu, co widać
        # w kolumnie SUBIEKT, można ufać. Kolor zmienia się z wiekiem.
        self.lbl_wiek = tk.Label(top, text="", bg="#34495e", fg="#2ecc71",
                                 font=("Arial", 13, "bold"))
        self.lbl_wiek.pack(side=tk.LEFT, padx=(16, 0))

        self.btn_refresh = tk.Button(top, text="🔄 Przelicz", command=self._load_async,
                                     bg="#3498db", fg="white", font=("Arial", 8),
                                     padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_refresh.pack(side=tk.RIGHT, padx=10, pady=8)

        # Kartoteki trzymamy w cache na dysku (12 h) — po założeniu nowych
        # w Subiekcie trzeba móc wymusić ponowne pobranie.
        self.btn_odswiez_kat = tk.Button(top, text="⟳ Kartoteki",
                                         command=self._odswiez_katalog,
                                         bg="#5d6d7e", fg="white", font=("Arial", 8),
                                         padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_odswiez_kat.pack(side=tk.RIGHT, padx=(0, 4), pady=8)

        self.var_tylko_kolizje = tk.BooleanVar(value=True)
        tk.Checkbutton(top, text="Tylko z podobnymi", variable=self.var_tylko_kolizje,
                       command=self._refill, bg="#34495e", fg="white",
                       selectcolor="#e67e22", font=("Arial", 8),
                       activebackground="#34495e", activeforeground="white").pack(side=tk.RIGHT, padx=4)

        self.summary = tk.Label(self, text="Wczytywanie…", bg="#ecf0f1", fg="#2c3e50",
                                font=("Arial", 9), anchor="w", padx=12, pady=6, justify=tk.LEFT)
        self.summary.pack(side=tk.TOP, fill=tk.X)

        wrap = tk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 4))
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in self.COLS], show="headings",
                                 selectmode="none")
        for key, label, width, anchor in self.COLS:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor=anchor,
                             stretch=(key in ("kod", "podobne")), minwidth=30)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.tag_configure("zaz",     background="#d5f5e3")   # zaznaczone do scalenia
        self.tree.tag_configure("szukany", background="#fff3cd")   # trwa szukanie kartoteki
        self.tree.tag_configure("cichy",   foreground="#95a5a6")   # bez podobnych
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<Double-1>", self._on_double_click)

        tk.Label(self,
                 text="Kliknij wiersz, żeby go zaznaczyć (☐ → ☑).   "
                      "Kliknięcie w „— brak kartoteki” otwiera szukanie w Subiekcie.   "
                      "🔗 Scal — łączy zaznaczone w JEDEN wiersz z sumą ilości (nazwa z pola niżej).   "
                      "🏷 Nazwij z Subiekta — wiersze zostają osobno, każdy dostaje nazwę swojej kartoteki.   "
                      "⚠ Różny materiał zwykle znaczy, że to inny element.",
                 anchor="w", padx=12, pady=2, fg="#555", font=("Arial", 8),
                 wraplength=1020, justify=tk.LEFT).pack(side=tk.TOP, fill=tk.X)

        # Dwa rzędy, nie jeden: siedem elementów w jednym pasku nie mieściło
        # się w oknie i „Odznacz wszystko" było przycięte do paru pikseli.
        # Rząd 1 — nazwa i skąd ją wziąć. Rząd 2 — co z tym zrobić.

        # ── rząd 2 (na dole): akcje ─────────────────────────────────────────
        akcje = tk.Frame(self)
        akcje.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(2, 8))

        self.btn_scal = tk.Button(akcje, text="🔗 Scal zaznaczone", command=self._scal,
                                  bg="#e67e22", fg="white", font=("Arial", 9, "bold"),
                                  padx=14, pady=6, relief=tk.RAISED, bd=2,
                                  state=tk.DISABLED, cursor="hand2")
        self.btn_scal.pack(side=tk.RIGHT)

        # Operacja ODWROTNA do scalania: wiersze zostają osobno, każdy dostaje
        # nazwę SWOJEJ kartoteki. Pole nazwy jest tu nieużywane — nazwa bierze
        # się z Subiekta, osobno dla każdej pozycji.
        self.btn_nazwij = tk.Button(akcje, text="🏷 Nazwij z Subiekta",
                                    command=self._nazwij_z_subiekta,
                                    bg="#2980b9", fg="white", font=("Arial", 9, "bold"),
                                    padx=12, pady=6, relief=tk.RAISED, bd=2,
                                    state=tk.DISABLED, cursor="hand2")
        self.btn_nazwij.pack(side=tk.RIGHT, padx=(0, 8))

        tk.Button(akcje, text="Odznacz wszystko", command=self._odznacz,
                  font=("Arial", 9), padx=10, pady=6).pack(side=tk.LEFT)
        tk.Button(akcje, text="Zamknij", command=self._zamknij,
                  font=("Arial", 9), padx=12, pady=6).pack(side=tk.LEFT, padx=(8, 0))

        # ── rząd 1 (nad akcjami): nazwa docelowa ────────────────────────────
        dol = tk.Frame(self)
        dol.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(6, 0))
        tk.Label(dol, text="Nazwa po scaleniu:", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.var_nazwa = tk.StringVar()
        # Zwykłe pole + własna lista podpowiedzi pod spodem. ttk.Combobox
        # rysował listę systemowym stylem: wąską, bez odstępów, z ucinaniem
        # dłuższych nazw — przy kodach katalogowych nie dało się ich odróżnić.
        self.ent_nazwa = tk.Entry(dol, textvariable=self.var_nazwa,
                                  font=("Consolas", 11), relief=tk.SOLID, bd=1)
        self.ent_nazwa.pack(side=tk.LEFT, padx=(8, 6), ipady=4, fill=tk.X, expand=True)
        self.ent_nazwa.bind("<KeyRelease>", self._podpowiedz_nazwy)
        # Reczna edycja rozjezdza pole z wybrana kartoteka — pasek chowamy,
        # zeby nie twierdzil czegos, co juz nieprawda.
        self.ent_nazwa.bind("<KeyRelease>", lambda _e: self._pokaz_wybrana(None),
                            add="+")
        self.ent_nazwa.bind("<FocusOut>", lambda _e: self.after(150, self._ukryj_podpowiedzi))
        self.ent_nazwa.bind("<Escape>", lambda _e: self._ukryj_podpowiedzi())
        self._popup = None
        # Pole zostaje PUSTE, dopóki user sam czegoś nie wpisze albo nie użyje
        # przycisków obok — nazwa docelowa to decyzja, nie domysł programu.

        # Co wybrano z podpowiedzi — Entry pokazuje SAMA NAZWE, wiec symbol,
        # opis, rodzaj, stan i cena znikaly w chwili kliknięcia i nie bylo jak
        # sprawdzic, czy trafilo sie w te kartoteke (zgloszone 25.09.2026).
        # Ten sam uklad kolumn co lista podpowiedzi i co arkusz.
        self.lbl_wybrana = tk.Label(self, text="", anchor="w", padx=12,
                                    font=("Segoe UI", 8), fg="#1e8449",
                                    bg="#eafaf1", justify=tk.LEFT)

        # Gdy któraś z zaznaczonych pozycji ma już kartotekę, najlepszą nazwą
        # docelową jest ta z Subiekta — inaczej scalenie tworzy kolejny wariant
        # zapisu tego samego elementu, czyli dokładnie to, co tu naprawiamy.
        self.btn_z_subiekta = tk.Button(dol, text="⬅ Wklej z Subiekt",
                                        command=self._wklej_z_subiekta,
                                        font=("Arial", 8), padx=8, pady=3,
                                        state=tk.DISABLED, cursor="hand2")
        self.btn_z_subiekta.pack(side=tk.LEFT, padx=(0, 4))

        # Drugie źródło nazwy: zapis, którego firma używa najczęściej w innych
        # projektach (kolumna „Najczęściej w firmie"). Przydatne, gdy kartoteki
        # w Subiekcie jeszcze nie ma.
        self.btn_najczestsze = tk.Button(dol, text="⬅ Wklej najczęstsze",
                                         command=self._wklej_najczestsze,
                                         font=("Arial", 8), padx=8, pady=3,
                                         state=tk.DISABLED, cursor="hand2")
        self.btn_najczestsze.pack(side=tk.LEFT)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    # ── wczytywanie ────────────────────────────────────────────────────────
    def _load_async(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.btn_scal.config(state=tk.DISABLED)
        self._start_kreciolek("Przeglądam BOM-y wszystkich projektów")
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        try:
            poz = S.pozycje_z_podobnymi(self.project_id, con=self.con)
            self.after(0, lambda: self._done(poz, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._done([], err))

    def _done(self, pozycje, error):
        self._stop_kreciolek()
        self.btn_refresh.config(state=tk.NORMAL)
        if error:
            self.status.config(text="Błąd.")
            self.summary.config(text=error.split("\n")[0])
            messagebox.showerror("Scalanie", error, parent=self)
            return
        # Podobne kody obok siebie — sortowanie po znormalizowanym kluczu
        # ustawia 'UCFL201' tuż nad 'UCFL20112'.
        self.pozycje = sorted(pozycje, key=lambda p: p["klucz"])
        self._zaznaczone.clear()
        self.var_nazwa.set("")
        self._refill()
        # Katalog Subiekta dociągamy PO narysowaniu listy — most potrzebuje
        # kilkunastu sekund, a lista jest użyteczna także bez tej kolumny.
        self._subiekt_stan = "sprawdzam…"
        self._start_kreciolek()
        threading.Thread(target=self._subiekt_worker, daemon=True).start()

    # ── wskaźnik pracy w tle ───────────────────────────────────────────────
    _KLATKI = "◐◓◑◒"

    def _start_kreciolek(self, tekst="Pobieram kartoteki z Subiekta"):
        """Kręciołek w pasku stanu — most potrzebuje kilkunastu sekund i bez
        tego okno wygląda, jakby zawisło."""
        self._kreci_tekst = tekst
        self._kreci_klatka = 0
        self._kreci = True
        self._kreciolek_tik()

    def _kreciolek_tik(self):
        if not getattr(self, "_kreci", False):
            return
        znak = self._KLATKI[self._kreci_klatka % len(self._KLATKI)]
        self._kreci_klatka += 1
        try:
            self.status.config(text=f"{znak}  {self._kreci_tekst}…")
        except tk.TclError:
            return                      # okno zamknięte w międzyczasie
        self._kreci_after = self.after(120, self._kreciolek_tik)

    def _stop_kreciolek(self):
        self._kreci = False
        after_id = getattr(self, "_kreci_after", None)
        if after_id:
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
            self._kreci_after = None
        if self.tylko_podglad:
            self.status.config(text="PODGLĄD — brak lokalnej kopii projektu, zapis wyłączony.")
        else:
            self.status.config(
                text="Zapis trafia do lokalnej kopii; na serwer — przy zwolnieniu locka.")

    def _kody_wszystkie(self):
        kody = []
        for p in self.pozycje:
            kody.append(p["kod"])
            kody.extend(p["identyczne"])
        return kody

    def _z_mapowan(self, kody):
        """Kartoteki z LOKALNEJ bazy mapowań — natychmiast, bez sieci.

        subiekt_mapowania.sqlite trzyma to, co już raz ustalono (numer →
        kartoteka). Odczyt to mikrosekundy, więc kolumna SUBIEKT pojawia się
        od razu, a most odpytujemy tylko o to, czego tam nie ma.
        """
        try:
            import subiekt_mapowania as M
            wpisy = M.get_many(kody)
        except Exception:
            return {}
        if not wpisy:
            return {}
        # get_many kluczuje po TRIM+UPPER (_key), a my pytamy oryginalnym
        # zapisem — mapujemy z powrotem, żeby kod z BOM-u trafił na swój wpis.
        out = {}
        for kod in kody:
            w = wpisy.get((kod or "").strip().upper())
            if not w:
                continue
            nazwa = (w["nazwa_subiekt"] or "").strip()
            symbol = (w["symbol_subiekt"] or "").strip()
            # Wpisy zapisane przez subiekt_projekt.py mają sam symbol i bywa,
            # że jest nim numer rysunku — wtedy „nazwa kartoteki" to w istocie
            # to samo, co kod w BOM, i nie ma czego przepisywać.
            out[kod] = {"id": w["id_subiekt"], "symbol": symbol,
                        "nazwa": nazwa, "sposob": w["sposob"]}
        return out

    def _subiekt_worker(self):
        """Kolumna SUBIEKT: najpierw to, co lokalne, most dopiero w razie potrzeby."""
        kody = self._kody_wszystkie()

        # 0. Katalog z dysku — bez sieci, żeby wyszukiwarka działała od razu.
        #    Bez tego pierwsze kliknięcie w kolumnę SUBIEKT oznaczało ~15 s
        #    czekania na most.
        try:
            self._katalog = S.wczytaj_katalog_subiekta(tylko_cache=True)
        except Exception:
            self._katalog = []

        # 1. Lokalne mapowania — natychmiast, pokazujemy je zanim ruszy most.
        lokalne = self._z_mapowan(kody)
        if lokalne:
            self.after(0, lambda: self._subiekt_czesciowo(lokalne, len(kody)))

        # 2. Most — dla kodów bez mapowania albo bez Id/nazwy (stare wpisy
        #    z subiekt_projekt.py mają sam symbol). Katalog pobieramy też
        #    wtedy, gdy braków nie ma: przyda się do ręcznego wyszukiwania
        #    i podpowiedzi nazw, a i tak leci w tle.
        braki = [k for k in kody
                 if k not in lokalne or not lokalne[k].get("id")]
        wiek = S.katalog_wiek_h()
        if not braki and self._katalog and wiek is not None and wiek <= S.KATALOG_WAZNY_H:
            # Wszystko wiadomo z lokalnych źródeł — nie ruszamy Subiekta.
            self.after(0, lambda: self._subiekt_done(lokalne, len(self._katalog), None))
            return
        try:
            katalog = S.wczytaj_katalog_subiekta()
            # Zatrzymujemy całą listę — służy potem do ręcznego wyszukiwania
            # kartoteki i do autouzupełniania nazwy.
            self._katalog = katalog
            mapa = dict(lokalne)
            if braki:
                znalezione = S.dopasuj_katalog(braki, katalog)
                mapa.update({k: v for k, v in znalezione.items() if v})
                self._zapisz_mapowania(znalezione)
            self.after(0, lambda: self._subiekt_done(mapa, len(katalog), None))
        except Exception as e:
            err = str(e)
            # Lokalne dane zostają — brak Subiekta nie kasuje tego, co już wiemy.
            self.after(0, lambda: self._subiekt_done(lokalne, None, err))

    def _zatwierdz_reczne(self):
        """Ręczne przypisania → baza mapowań. Wołane DOPIERO przy zapisie BOM.

        SPOSOB_RECZNY, bo to świadoma decyzja człowieka — put() nie pozwoli
        potem automatowi jej nadpisać.
        """
        if not self._reczne:
            return
        try:
            import subiekt_mapowania as M
            M.put_many([(kod, poz["symbol"], M.SPOSOB_RECZNY,
                         poz.get("id"), poz.get("nazwa"))
                        for kod, poz in self._reczne.items()])
            self._reczne.clear()
        except Exception:
            pass          # brak zapisu mapowania nie może wywalić zapisu BOM

    def _zapisz_mapowania(self, znalezione):
        """Dopisz do lokalnej bazy to, czego most właśnie się dowiedział.

        Dzięki temu następne otwarcie okna ma kolumnę SUBIEKT od razu, bez
        czekania na most. put() nie nadpisuje ręcznych decyzji użytkownika.
        """
        wpisy = [(kod, poz["symbol"], "auto", poz.get("id"), poz.get("nazwa"))
                 for kod, poz in znalezione.items() if poz]
        if not wpisy:
            return
        try:
            import subiekt_mapowania as M
            M.put_many([(k, s, M.SPOSOB_AUTO, i, n) for k, s, _sp, i, n in wpisy])
        except Exception:
            pass          # cache jest udogodnieniem, nie warunkiem działania

    def _pokaz_wiek_katalogu(self):
        """Ile czasu minęło od pobrania kartotek — godziny i minuty.

        Kolor: zielony gdy świeże, pomarańczowy po połowie ważności,
        czerwony gdy przeterminowane albo w ogóle nie pobrane.
        """
        wiek = S.katalog_wiek_h()
        if wiek is None:
            self.lbl_wiek.config(text="⏱ kartoteki: nie pobrane", fg="#e74c3c")
            return
        godz, minuty = int(wiek), int((wiek - int(wiek)) * 60)
        if godz:
            ile = f"{godz} h {minuty} min"
        else:
            ile = f"{minuty} min"
        if wiek > S.KATALOG_WAZNY_H:
            kolor = "#e74c3c"
        elif wiek > S.KATALOG_WAZNY_H / 2:
            kolor = "#f39c12"
        else:
            kolor = "#2ecc71"
        self.lbl_wiek.config(text=f"⏱ kartoteki sprzed {ile}", fg=kolor)

    def _odswiez_katalog(self):
        """Wymuś ponowne pobranie kartotek z Subiekta (pomija cache)."""
        try:
            if os.path.isfile(S.KATALOG_CACHE):
                os.remove(S.KATALOG_CACHE)
        except Exception:
            pass
        self._katalog = []
        self._load_async()

    def _subiekt_czesciowo(self, mapa, ile_kodow):
        """Pokaż to, co już wiadomo z lokalnej bazy; most nadal leci."""
        self._subiekt = mapa
        trafione = sum(1 for v in mapa.values() if v)
        self._subiekt_stan = f"{trafione}/{ile_kodow} z pamięci, sprawdzam resztę…"
        self._refill()

    def _subiekt_done(self, mapa, ile_kartotek, error):
        self._stop_kreciolek()
        self._subiekt = mapa or {}
        trafione = sum(1 for v in self._subiekt.values() if v)
        ile_kodow = len(self._kody_wszystkie())
        if error:
            # Brak Subiekta nie może blokować scalania — to informacja
            # dodatkowa, nie warunek działania. To, co wiemy z lokalnej bazy,
            # zostaje na ekranie.
            self._subiekt_stan = (f"{trafione}/{ile_kodow} z pamięci "
                                  f"(Subiekt niedostępny)")
            self.status.config(text=f"Subiekt nieodpytany: {error.splitlines()[0]}")
        else:
            self._subiekt_stan = f"{trafione}/{ile_kodow} ma kartotekę"
            if ile_kartotek:
                self._subiekt_stan += f"  (z {ile_kartotek} w Subiekcie)"
        self._refill()

    def _opis_subiekt(self, p):
        """Tekst do kolumny SUBIEKT dla jednej pozycji.

        Bez Id — jest mało czytelne dla człowieka, a do niczego w tym oknie
        nie służy: zapisujemy je w bazie mapowań i pokazujemy w potwierdzeniu
        scalania, gdzie jednoznaczność faktycznie ma znaczenie.
        """
        if not self._subiekt:
            return self._subiekt_stan if self._subiekt_stan != "nie sprawdzono" else ""
        for kod in [p["kod"]] + p["identyczne"]:
            poz = self._subiekt.get(kod)
            if poz:
                symbol = (poz.get("symbol") or "").strip()
                nazwa = (poz.get("nazwa") or "").strip()
                # Symbol pokazujemy tylko, gdy różni się od kodu w projekcie —
                # inaczej powtarzalibyśmy to, co widać obok w kolumnie „Kod".
                if symbol and S.norm_kod(symbol) != S.norm_kod(p["kod"]):
                    opis = f"{symbol} · {nazwa}".strip(" ·")
                else:
                    opis = nazwa or symbol
                # Gwiazdka = wybrane ręcznie, ale jeszcze niezapisane; przepadnie
                # przy anulowaniu locka albo zamknięciu okna bez zapisu.
                if kod in self._reczne:
                    opis += "  *niezapisane"
                return opis
        return "— brak kartoteki"

    # ── prezentacja ────────────────────────────────────────────────────────
    def _refill(self):
        self._pokaz_wiek_katalogu()
        # Podpowiedzi to okno bez ramki — musi zniknąć razem z odświeżeniem,
        # inaczej wisi nad listą po zmianie zaznaczenia.
        self._ukryj_podpowiedzi()
        self.tree.delete(*self.tree.get_children())
        tylko = self.var_tylko_kolizje.get()
        pokazane = 0
        for p in self.pozycje:
            # `rodzenstwo` > 0 = ten sam kod stoi w kilku WIERSZACH arkusza
            # i pozycja zostala rozbita na osobne wpisy. Taki wpis nie ma
            # wariantow pisowni (`identyczne` puste), a jest najwazniejszym
            # powodem do scalenia — bez tego znikal z listy (24.09.2026).
            ma_co = bool(p["identyczne"] or p["podobne"] or p.get("rodzenstwo")
                         or p.get("rysunek_dubel"))
            if tylko and not ma_co and p["klucz"] not in self._zaznaczone:
                continue
            pokazane += 1
            zaz = p["klucz"] in self._zaznaczone

            naj = ""
            if p["w_bazie"]:
                w, n = max(p["w_bazie"].items(), key=lambda t: t[1])
                naj = f"{w}  ({n} proj.)"

            podobne = [s["kod"] for s in p["podobne"]] + [f"= {k}" for k in p["identyczne"]]
            # Rozbity duplikat nie ma czego pokazac w tej kolumnie, a wlasnie
            # on jest do scalenia — mowimy o tym wprost.
            if p.get("rodzenstwo"):
                podobne.insert(0, f"⚠ ten sam kod w {p['rodzenstwo']} wierszach")
            # Duplikat po NUMERZE RYSUNKU — nazwy sie roznia, wiec kolumna
            # „Podobne" nie ma czego pokazac, a to wlasnie powod scalania.
            if p.get("rysunek_dubel"):
                podobne.insert(0, "⚠ ten sam nr rysunku %s w %d wierszach"
                               % (p["rysunek_dubel"], p.get("rysunek_ile", 2)))
            tags = ("zaz",) if zaz else (() if ma_co else ("cichy",))
            self.tree.insert("", "end", iid=p["klucz"], tags=tags, values=(
                "☑" if zaz else "☐",
                p.get("rysunek", ""),
                p["kod"],
                p.get("opis", ""),
                f"{p['ilosc_bom']:g}",
                p["material"],
                self._opis_subiekt(p),
                naj,
                "   ·   ".join(podobne),
            ))

        # Pasek „Wybrano" niesie ILOSC z zaznaczonych — po zmianie zaznaczenia
        # trzeba go przeliczyc, inaczej pokazywalby poprzednia sume.
        if getattr(self, "_wybrana_poz", None):
            self._pokaz_wybrana(self._wybrana_poz)

        wybrane = [p for p in self.pozycje if p["klucz"] in self._zaznaczone]
        suma = sum(p["ilosc_bom"] for p in wybrane)
        z_kolizja = sum(1 for p in self.pozycje
                        if p["identyczne"] or p["podobne"] or p.get("rodzenstwo")
                        or p.get("rysunek_dubel"))
        opis = (f"Kodów handlowych: {len(self.pozycje)}    z podobnymi: {z_kolizja}    "
                f"pokazanych: {pokazane}    SUBIEKT: {self._subiekt_stan}    ")
        if wybrane:
            opis += f"ZAZNACZONE: {len(wybrane)}"
            if len(wybrane) >= 2:
                opis += f"  →  scalone dałyby jedną pozycję, ilość {suma:g}"
            # Czemu „Nazwij z Subiekta" bywa szary — inaczej wygląda to na
            # usterkę, a zwykle po prostu nie ma czego zmieniać.
            ile_nazw = len(self._zmiany_nazw())
            if ile_nazw:
                opis += f"    🏷 do przemianowania: {ile_nazw}"
            elif self._kartoteki_zaznaczonych():
                opis += "    🏷 nazwy już zgodne z Subiektem"
            elif self._subiekt:
                opis += "    🏷 brak kartoteki w Subiekcie"
            mats = {p["material"] for p in wybrane if p["material"]}
            if len(mats) > 1:
                opis += f"\n⚠ Zaznaczone różnią się materiałem: {' / '.join(sorted(mats))}"
        else:
            opis += "zaznacz wiersze: 2+ do scalenia albo 1+ do przemianowania"
        self.summary.config(text=opis)

        self.btn_scal.config(
            text=f"🔗 Scal zaznaczone ({len(wybrane)})" if wybrane else "🔗 Scal zaznaczone",
            state=tk.NORMAL if (len(wybrane) >= 2 and not self.tylko_podglad) else tk.DISABLED)

        # Oba przyciski tylko wtedy, gdy mają co wkleić — „z Subiekt" wymaga
        # istniejącej kartoteki, „najczęstsze" danych z innych projektów.
        kartoteki = self._kartoteki_zaznaczonych()
        self.btn_z_subiekta.config(state=tk.NORMAL if kartoteki else tk.DISABLED)
        self.btn_najczestsze.config(
            state=tk.NORMAL if self._najczestszy_zapis() else tk.DISABLED)

        # Nazywanie działa już od JEDNEJ pozycji — nie łączy wierszy, więc nie
        # potrzebuje pary. Aktywne dokładnie wtedy, gdy akcja miałaby co zrobić,
        # więc liczymy to tą samą funkcją (wcześniej osobny warunek porównywał
        # nazwę tylko z p["kod"] i nie widział wariantów pisowni).
        self.btn_nazwij.config(
            state=tk.NORMAL if (self._zmiany_nazw() and not self.tylko_podglad)
            else tk.DISABLED)

    # ── interakcja ─────────────────────────────────────────────────────────
    def _kolumna_subiekt(self, event):
        """Czy kliknięto w kolumnę SUBIEKT?"""
        return (self.tree.identify_column(event.x)
                == f"#{[c[0] for c in self.COLS].index('subiekt') + 1}")

    def _on_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return

        # Pozycja BEZ kartoteki: pojedynczy klik w kolumnę SUBIEKT od razu
        # otwiera szukanie — nie ma tam nic do zaznaczania, a to najczęstsza
        # rzecz, jaką się z takim wierszem robi.
        if self._kolumna_subiekt(event):
            p = next((x for x in self.pozycje if x["klucz"] == iid), None)
            if p and not any(self._subiekt.get(k) for k in [p["kod"]] + p["identyczne"]):
                self._szukaj_w_subiekcie(p, iid)
                return

        if iid in self._zaznaczone:
            self._zaznaczone.discard(iid)
        else:
            self._zaznaczone.add(iid)
        self._refill()
        self.tree.see(iid)

    def _on_double_click(self, event):
        """Podwójny klik w kolumnę SUBIEKT — ZAWSZE otwiera wyszukiwarkę.

        Także dla pozycji, która ma już kartotekę: dopasowanie bywa błędne
        (automat trafia po nazwie w nie tę rzecz) i trzeba móc je poprawić.
        """
        iid = self.tree.identify_row(event.y)
        if not iid or not self._kolumna_subiekt(event):
            return
        p = next((x for x in self.pozycje if x["klucz"] == iid), None)
        if not p:
            return
        # Pojedynczy klik zdążył już przełączyć zaznaczenie — cofamy to,
        # żeby dwuklik nie zostawiał po sobie przypadkowego zaznaczenia.
        if iid in self._zaznaczone:
            self._zaznaczone.discard(iid)
        else:
            self._zaznaczone.add(iid)
        self._szukaj_w_subiekcie(p, iid)

    def _odznacz(self):
        self._zaznaczone.clear()
        self.var_nazwa.set("")      # nowe zaznaczenie = nowa decyzja o nazwie
        self._pokaz_wybrana(None)   # ...wiec i pasek „Wybrano" jest nieaktualny
        self._refill()

    def _kartoteki_zaznaczonych(self):
        """[(pozycja, kartoteka)] — te z zaznaczonych, które Subiekt już zna."""
        out = []
        for p in self.pozycje:
            if p["klucz"] not in self._zaznaczone:
                continue
            for kod in [p["kod"]] + p["identyczne"]:
                poz = self._subiekt.get(kod)
                if poz:
                    out.append((p, poz))
                    break
        return out

    def _wklej_z_subiekta(self):
        """Wstaw do pola nazwy NAZWĘ z kartoteki Subiekta.

        Bez pytania o wybór: symbol bywa przypadkowy ('122UC' dla 'UCFL 201'),
        a nazwa jest tym, co człowiek rozpoznaje — i to ona ma trafić do BOM-u.
        Symbol zostaje w kolumnie SUBIEKT do wglądu.
        """
        for _p, poz in self._kartoteki_zaznaczonych():
            nazwa = (poz.get("nazwa") or "").strip() or (poz.get("symbol") or "").strip()
            if nazwa:
                self._ustaw_nazwe(nazwa)
                # ⚠️ ZAPAMIETUJEMY CALA KARTOTEKE, nie tylko nazwe — z niej
                # bierze sie OPIS przy scalaniu i nazywaniu. Bez tego
                # „Wklej z Subiekt" dawal nazwe, a opis zostawal pusty
                # (zgloszone 25.09.2026). `_ustaw_nazwe` czysci pasek
                # „Wybrano", wiec ustawiamy PO nim.
                self._pokaz_wybrana(poz)
                return

    def _najczestszy_zapis(self):
        """Zapis używany w największej liczbie projektów spośród zaznaczonych."""
        kandydaci = {}
        for p in self.pozycje:
            if p["klucz"] not in self._zaznaczone:
                continue
            for zapis, ile in (p["w_bazie"] or {}).items():
                kandydaci[zapis] = max(kandydaci.get(zapis, 0), ile)
        if not kandydaci:
            return None
        # Przy remisie krótszy zapis — zwykle ten bez przypadkowych dopisków.
        return max(kandydaci.items(), key=lambda t: (t[1], -len(t[0])))[0]

    def _wklej_najczestsze(self):
        zapis = self._najczestszy_zapis()
        if zapis:
            self._ustaw_nazwe(zapis)

    def _na_escape(self, _event=None):
        """ESC — najpierw chowa podpowiedzi, potem zamyka okno."""
        if getattr(self, "_popup", None) is not None:
            self._ukryj_podpowiedzi()
            return "break"
        self._zamknij()
        return "break"

    def _zamknij(self):
        """Zamknięcie okna — sprząta też podpowiedzi (osobne okno bez ramki)."""
        self._ukryj_podpowiedzi()
        self.destroy()

    def _ukryj_podpowiedzi(self):
        # getattr, bo _refill może zadziałać, zanim _build_ui dojdzie do pola
        # nazwy (np. gdy budowa interfejsu przerwie się wyjątkiem).
        popup = getattr(self, "_popup", None)
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
            self._popup = None

    def _podpowiedz_nazwy(self, event=None):
        """Podpowiedzi kartotek pod polem nazwy — symbol i nazwa w dwóch kolumnach.

        Klawisze nawigacji pomijamy, żeby nie przebudowywać listy przy każdym
        ruchu kursora.
        """
        if event is not None and event.keysym in (
                "Up", "Down", "Left", "Right", "Return", "Escape", "Tab"):
            return
        fraza = S.norm_kod(self.var_nazwa.get())
        if not fraza or not self._katalog:
            self._ukryj_podpowiedzi()
            return

        trafienia = []
        widziane = set()
        for poz in self._katalog:
            if fraza in S.norm_kod(poz["symbol"]) or fraza in S.norm_kod(poz["nazwa"]):
                nazwa = (poz["nazwa"] or "").strip() or (poz["symbol"] or "").strip()
                if nazwa and nazwa not in widziane:
                    widziane.add(nazwa)
                    trafienia.append(poz)
            if len(trafienia) >= 12:
                break
        if not trafienia:
            self._ukryj_podpowiedzi()
            return

        self._ukryj_podpowiedzi()
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)          # bez ramki okna — to lista, nie okno
        popup.attributes("-topmost", True)
        self._popup = popup

        x = self.ent_nazwa.winfo_rootx()
        y = self.ent_nazwa.winfo_rooty() + self.ent_nazwa.winfo_height() + 2
        # Szerokosc LICZONA Z UKLADU, nie wpisana na sztywno.
        #
        # ⚠️ Bylo `szer = 730` z wyliczenia „znaki × px czcionki" (Consolas 7,
        # Segoe UI 6). To ZA MALO: Tk dolicza kazdej etykiecie wewnetrzny
        # padding, wiec realny rzad ma 856 px i dwie ostatnie kolumny (Stan,
        # Cena netto) wypadaly poza krawedz — user widzial ucieta liste
        # (zgloszone 25.09.2026). `winfo_reqwidth()` zmierzonego rzadu jest
        # odporny na zmiane czcionki, DPI i szerokosci kolumn.
        szer = self._szerokosc_podpowiedzi()
        wys = min(len(trafienia), 12) * 26 + 24
        # Popup nie moze wyjsc poza prawa krawedz ekranu — przy polu blisko
        # brzegu przesuwamy go w lewo zamiast chowac tresc.
        x = max(0, min(x, popup.winfo_screenwidth() - szer - 8))
        popup.geometry(f"{szer}x{wys}+{x}+{y}")

        ramka = tk.Frame(popup, bg="#b0b8bd", bd=0)
        ramka.pack(fill=tk.BOTH, expand=True)
        wnetrze = tk.Frame(ramka, bg="white")
        wnetrze.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Nagłówek — bez niego sześć kolumn to nieczytelna ściana tekstu.
        hdr = tk.Frame(wnetrze, bg="#f4f6f7", height=20)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        # ⚠️ KAZDA kolumna naglowka TA SAMA czcionka, szerokosc i padx co jej
        # dane — wszystko z `KOL_PODPOWIEDZI`, zeby naglowek, wiersze
        # i szerokosc popupu nie mogly sie rozjechac. `width` w Tk liczy sie
        # w ZNAKACH biezacej czcionki, a Consolas jest szersza od Segoe UI
        # (7 vs 6 px na znak) — stad osobna czcionka per kolumna.
        for txt, szer_k, czcionka, (pl, pr), kotwica in self.KOL_PODPOWIEDZI:
            tk.Label(hdr, text=txt, bg="#f4f6f7", fg="#7f8c8d",
                     anchor=kotwica, font=czcionka, width=szer_k).pack(
                         side=tk.LEFT, padx=(pl, pr))

        def wybierz(nazwa, poz=None):
            self.var_nazwa.set(nazwa)
            self._pokaz_wybrana(poz)
            self._ukryj_podpowiedzi()
            self._refill()

        for poz in trafienia:
            nazwa = (poz["nazwa"] or "").strip() or (poz["symbol"] or "").strip()
            w = tk.Frame(wnetrze, bg="white", height=26)
            w.pack(fill=tk.X)
            w.pack_propagate(False)
            # Symbol na szaro po lewej, nazwa czarna — od razu widać, co jest
            # czym. Dalej Opis/Rodzaj/Stan/Cena: gdy nazwa jest równa
            # symbolowi, dopiero one rozstrzygają wybór (24.09.2026).
            # Wartosci w kolejnosci KOL_PODPOWIEDZI — ta sama stala rzadzi
            # naglowkiem, tymi wierszami i szerokoscia popupu.
            wartosci = (poz["symbol"], nazwa, poz.get("opis") or "",
                        poz.get("rodzaj") or "", self._stan_txt(poz),
                        self._cena_txt(poz.get("cena")))
            kolory = ("#7f8c8d", "#2c3e50", "#566573", "#7f8c8d",
                      "#2c3e50", "#2c3e50")
            for (_t, szer_k, czcionka, (pl, pr), kotwica), tekst, kolor in zip(
                    self.KOL_PODPOWIEDZI, wartosci, kolory):
                tk.Label(w, text=tekst, bg="white", fg=kolor, anchor=kotwica,
                         width=szer_k, font=czcionka).pack(side=tk.LEFT,
                                                           padx=(pl, pr))

            def podswietl(_e, ramka=w, kolor="#eaf2f8"):
                for dziecko in [ramka] + list(ramka.winfo_children()):
                    dziecko.configure(bg=kolor)

            for widget in [w] + list(w.winfo_children()):
                widget.bind("<Enter>", podswietl)
                widget.bind("<Leave>", lambda e, r=w: podswietl(e, r, "white"))
                widget.bind("<Button-1>",
                            lambda _e, n=nazwa, p=poz: wybierz(n, p))
                widget.configure(cursor="hand2")

    #: Kolumny listy podpowiedzi: (naglowek, width w znakach, czcionka, padx).
    #: JEDNO zrodlo prawdy — naglowek, wiersze i szerokosc popupu czytaja
    #: stad, wiec nie da sie ich rozjechac przy zmianie jednej z trzech rzeczy.
    KOL_PODPOWIEDZI = (
        ("Symbol",      16, ("Consolas", 9), (8, 4), "w"),
        ("Nazwa",       30, ("Segoe UI", 9), (0, 4), "w"),
        ("Opis",        40, ("Segoe UI", 9), (0, 4), "w"),
        ("Rodzaj",       9, ("Segoe UI", 9), (0, 4), "w"),
        ("Stan",         7, ("Segoe UI", 9), (0, 4), "e"),
        ("Cena netto",  10, ("Segoe UI", 9), (0, 8), "e"),
    )

    def _szerokosc_podpowiedzi(self):
        """Realna szerokosc rzadu podpowiedzi w pikselach.

        Mierzymy `winfo_reqwidth()` etykiet zbudowanych tak samo jak te
        w liscie — `width` w Tk liczy sie w znakach czcionki, ale do tego
        dochodzi wewnetrzny padding widgetu, ktorego nie da sie policzyc
        z samej czcionki. Wynik pamietamy: pomiar wymaga stworzenia
        widgetow, a uklad nie zmienia sie w trakcie sesji.
        """
        if getattr(self, "_szer_podpowiedzi", None):
            return self._szer_podpowiedzi
        probne = tk.Toplevel(self)
        probne.withdraw()
        rzad = tk.Frame(probne)
        rzad.pack()
        for txt, szer_k, czcionka, (pl, pr), kotwica in self.KOL_PODPOWIEDZI:
            tk.Label(rzad, text=txt, width=szer_k, font=czcionka,
                     anchor=kotwica).pack(side=tk.LEFT, padx=(pl, pr))
        rzad.update_idletasks()
        szer = rzad.winfo_reqwidth() + 2      # ramka popupu: padx 1 + 1
        probne.destroy()
        self._szer_podpowiedzi = szer
        return szer

    @staticmethod
    def _stan_txt(poz):
        """Stan magazynowy z KATALOGU — czysty odczyt, bez pytania Subiekta.

        Ta lista ma tylko WYSWIETLAC to, co juz wiadomo (decyzja uzytkownika,
        24.09.2026). Gdy katalog nie niesie stanu, kolumna zostaje pusta.
        """
        v = poz.get("stan") if isinstance(poz, dict) else None
        if v in (None, ""):
            return ""
        try:
            f = float(v)
        except (TypeError, ValueError):
            return str(v)
        return str(int(f)) if f == int(f) else ("%.2f" % f).rstrip("0").rstrip(".")

    @staticmethod
    def _cena_txt(v):
        """Cena ewidencyjna; zero pokazujemy jako puste — nic nie znaczy."""
        try:
            f = float(v or 0)
        except (TypeError, ValueError):
            return ""
        return f"{f:g}" if f else ""

    def _opis_docelowy(self):
        """Opis z kartoteki wybranej w podpowiedziach albo None.

        None, a nie "", zeby `scal_wiersze` i `zmien_nazwy` wiedzialy, ze
        kolumny opisu NIE NALEZY ruszac — user po prostu nie wskazal
        kartoteki, wiec nie mamy czym jej nadpisac.
        """
        wybrana = getattr(self, "_wybrana_poz", None) or {}
        opis = (wybrana.get("opis") or "").strip()
        if opis:
            return opis
        # Nie klikales podpowiedzi, ale zaznaczone pozycje MAJA juz kartoteke
        # w Subiekcie (kolumna SUBIEKT) — bierzemy opis stamtad. Inaczej opis
        # przepadal wszedzie poza jedna sciezka: klikniecie w podpowiedz.
        for _p, poz in self._kartoteki_zaznaczonych():
            opis = (poz.get("opis") or "").strip()
            if opis:
                return opis
        return None

    def _pokaz_wybrana(self, poz):
        """Pasek pod polem: co dokladnie wybrano z podpowiedzi.

        Entry niesie sama nazwe — reszta danych kartoteki (symbol, opis,
        rodzaj, stan, cena) przepadala po kliknieciu. Pokazujemy je obok,
        w tej samej kolejnosci co lista podpowiedzi i arkusz.
        """
        lbl = getattr(self, "lbl_wybrana", None)
        if lbl is None:
            return
        if not poz:
            self._wybrana_poz = None
            lbl.pack_forget()
            return
        # ⚠️ KAZDE pole pokazujemy ZAWSZE, takze puste — jako „—".
        # Wczesniej puste byly pomijane, wiec pasek raz mial szesc czlonow,
        # raz trzy, a kartoteka z cena 0 wygladala tak samo jak taka, dla
        # ktorej ceny nie znamy (zgloszone 25.09.2026).
        #
        # ILOSC nie jest wlasnoscia kartoteki — to suma z BOM-u tego, co
        # wlasnie scalasz. Bierzemy ja z zaznaczonych pozycji, zeby w jednym
        # miejscu bylo widac: dokad scalam i ile tego jest.
        wybrane = [x for x in self.pozycje if x["klucz"] in self._zaznaczone]
        ilosc = sum(x.get("ilosc_bom") or 0 for x in wybrane)
        self._wybrana_poz = poz     # do przerysowania, gdy zmieni sie ilosc
        czesci = [
            "Wybrano:  %s" % ((poz.get("symbol") or "").strip() or "—"),
            (poz.get("nazwa") or "").strip() or "—",
            (poz.get("opis") or "").strip() or "—",
            (poz.get("rodzaj") or "").strip() or "—",
            "stan %s" % (self._stan_txt(poz) or "—"),
            "ilość %g szt." % ilosc if wybrane else "ilość —",
            "cena %s" % (self._cena_txt(poz.get("cena")) or "—"),
        ]
        lbl.config(text="   ·   ".join(czesci))
        lbl.pack(side=tk.BOTTOM, fill=tk.X, before=self.status)

    def _ustaw_nazwe(self, wartosc):
        self.var_nazwa.set(wartosc)
        self._pokaz_wybrana(None)
        self._refill()

    # ── zapis ──────────────────────────────────────────────────────────────
    def _scal(self):
        if self.tylko_podglad:
            messagebox.showwarning(
                "Scalanie",
                "Brak lokalnej kopii projektu — przejmij lock w RM_BAZA.\n\n"
                "Zapis bez locka szedłby wprost do pliku na serwerze, "
                "z pominięciem arkusza.", parent=self)
            return
        wybrane = [p for p in self.pozycje if p["klucz"] in self._zaznaczone]
        if len(wybrane) < 2:
            return
        nazwa = self.var_nazwa.get().strip()
        if not nazwa:
            messagebox.showwarning("Scalanie", "Wpisz nazwę, jaką ma mieć scalona pozycja.",
                                   parent=self)
            self.ent_nazwa.focus_set()
            return

        # Wszystkie zapisy każdej zaznaczonej pozycji (kod + warianty pisowni).
        kody = []
        for p in wybrane:
            kody.append(p["kod"])
            kody.extend(p["identyczne"])
        wiersze = S.wiersze_kodu(self.project_id, kody, con=self.con)

        # ⚠️ Duplikat w arkuszu jest rozbity na OSOBNE wpisy listy, każdy ze
        # swoim `item_id` (patrz pozycje_z_podobnymi). Wtedy scalamy DOKŁADNIE
        # zaznaczone wiersze — inaczej zaznaczenie jednego wciągnęłoby oba,
        # a wybór ma być jawny (24.09.2026).
        # ⚠️ Filtr dotyczy TYLKO pozycji rozbitych na wiersze. Wpis zbiorczy
        # (`item_id is None`) reprezentuje WSZYSTKIE swoje wiersze, wiec
        # trzeba je zachowac — inaczej zaznaczenie „rozbity + zbiorczy"
        # odsiewalo ten drugi i zostawal JEDEN wiersz: „Do polaczenia trzeba
        # co najmniej dwoch wierszy" przy dwoch zaznaczonych pozycjach
        # (zgloszone 25.09.2026, projekt 75: 6004 + 6004ZZ).
        wskazane = {p["item_id"] for p in wybrane if p.get("item_id")}
        zbiorcze = [p for p in wybrane if not p.get("item_id")]
        if wskazane:
            kody_zbiorczych = set()
            for p in zbiorcze:
                for kod in [p["kod"]] + p["identyczne"]:
                    kody_zbiorczych.add((kod or "").strip().upper())
            wiersze = [w for w in wiersze
                       if w["id"] in wskazane
                       or (w["nazwa"] or "").strip().upper() in kody_zbiorczych]

        if len(wiersze) < 2:
            messagebox.showerror(
                "Scalanie",
                "Do połączenia trzeba co najmniej dwóch wierszy.\n\n"
                "Zaznacz oba wiersze tej pozycji (albo dwie różne pozycje), "
                "a potem kliknij „Scal zaznaczone\".", parent=self)
            return

        suma = sum(p["ilosc_bom"] for p in wybrane)
        zajete = [w for w in wiersze if w["praca"]]

        dlg = OknoDialog(self, "Scalanie — potwierdzenie",
                         f"Połączyć {len(wiersze)} wierszy w jeden?",
                         ikona="🔗", kolor="#e67e22")
        dlg.akapit("Te wiersze znikną z arkusza:", pogrubiony=True, odstep=(0, 2))
        pozycje_txt = []
        for w in wiersze:
            # Jak arkusz: COALESCE(work_qty, src_qty).
            q = w["ilosci"].get("work_qty")
            if q in (None, ""):
                q = w["ilosci"].get("src_qty") or 0
            pozycje_txt.append(f"{w['nazwa']:<44} {float(q):>6g} szt.")
        dlg.ramka_pozycji(pozycje_txt)
        dlg.akapit(f"→   {nazwa}          razem {suma:g} szt.",
                   pogrubiony=True, kolor="#1e8449")
        _opis = self._opis_docelowy()
        if _opis:
            dlg.akapit(f"Opis:   {_opis}", kolor="#5d6d7e", odstep=(0, 4))

        # Id kartoteki dopiero tutaj — w liście byłoby szumem, ale przy
        # zatwierdzaniu pozwala jednoznacznie wskazać pozycję w Subiekcie.
        for _p, poz in self._kartoteki_zaznaczonych():
            opis = " · ".join(x for x in (poz.get("symbol"), poz.get("nazwa")) if x)
            dlg.akapit(f"Kartoteka w Subiekcie:   id {poz['id']}   {opis}",
                       kolor="#5d6d7e", odstep=(2, 2))
        if zajete:
            dlg.ostrzezenie("⚠  Niektóre wiersze mają już wpisane dane robocze "
                            "(dostawca, zamówienie, termin) — po scaleniu PRZEPADNĄ.")
        dlg.sciezka("Kopia pliku przed zmianą:", BACKUP_DIR)
        dlg.przyciski(potwierdz="Połącz wiersze", anuluj="Anuluj", kolor="#e67e22")
        if not dlg.pokaz():
            return

        self.btn_scal.config(state=tk.DISABLED)
        self.status.config(text="Zapisuję…")
        try:
            backup = self._kopia_przed_zmiana()
            # JEDEN CYKL: nazwa + opis + polaczenie wierszy jednym kliknieciem
            # (zyczenie uzytkownika 25.09.2026). Opis z kartoteki wybranej
            # w podpowiedziach / wklejonej / juz przypisanej; None = nie ruszaj.
            r = S.scal_wiersze(self.project_id, [w["id"] for w in wiersze], nazwa,
                               backup_dir=BACKUP_DIR, con=self.con,
                               opis_docelowy=self._opis_docelowy())
            backup = backup or r["backup"]
            self._zapisz_audit(wiersze, nazwa, r)
            self._zatwierdz_reczne()      # dopiero teraz — razem ze zmianą w BOM
        except Exception as e:
            self.status.config(text="Błąd zapisu.")
            messagebox.showerror("Scalanie", str(e), parent=self)
            self._load_async()
            return

        odswiezony = self._odswiez_arkusz()
        wynik = OknoDialog(self, "Scalanie zakończone",
                           f"Połączono {len(wiersze)} wierszy w jeden",
                           ikona="✔", kolor="#1e8449")
        wynik.akapit(nazwa, pogrubiony=True, odstep=(2, 0))
        wynik.akapit(f"razem {suma:g} szt.", kolor="#5d6d7e", odstep=(0, 8))
        if not odswiezony:
            wynik.ostrzezenie("Odśwież arkusz, żeby zobaczyć zmiany.")
        if backup:
            wynik.sciezka("Kopia przed zmianą:", backup)
        wynik.przyciski(anuluj="OK")
        wynik.pokaz()
        self._load_async()

    def _zmiany_nazw(self):
        """[(zapis w BOM, nazwa z pola „Nazwa po scaleniu", opis)].

        ⚠️ NAZWE BIERZEMY Z DOLNEGO POLA, nie z kartoteki per zapis
        (decyzja uzytkownika 25.09.2026).

        Bylo: dla KAZDEGO wariantu pisowni osobno szukalismy kartoteki
        i brali JEJ nazwe. Rozne wiersze trafialy wiec w rozne kartoteki,
        a przez warianty pisowni takze w CUDZE. Na projekcie 75 trzy rozne
        lozyska („6004" = SKF 6004 DIN 625, „6004ZZ", „6004 ZZ 20x42x12")
        dostaly jedna nazwe „Lozysko kulkowe zwykle 20x42x12". Nazwa
        docelowa to decyzja czlowieka — stoi w polu na dole i obowiazuje
        WSZYSTKIE zaznaczone.

        OPIS bierzemy z kartoteki wybranej w podpowiedziach (`_wybrana_poz`),
        gdy user ja wskazal — inaczej zostaje pusty i `zmien_nazwy` go nie
        rusza. Wczesniej opis nie byl przenoszony w ogole.

        Warianty pisowni (`identyczne`) nadal wchodza do listy, zeby po
        operacji nie zostaly rozjechane zapisy tej samej rzeczy.
        """
        nazwa = self.var_nazwa.get().strip()
        if not nazwa:
            return []
        opis = self._opis_docelowy() or ""
        zmiany = []
        for p in self.pozycje:
            if p["klucz"] not in self._zaznaczone:
                continue
            for kod in [p["kod"]] + p["identyczne"]:
                if kod.strip() and kod.strip() != nazwa:
                    zmiany.append((kod, nazwa, opis))
        return zmiany


    def _nazwij_z_subiekta(self):
        """Każda zaznaczona pozycja dostaje nazwę SWOJEJ kartoteki z Subiekta.

        Wiersze zostają osobno — to nie jest scalanie. Służy do ujednolicenia
        nazewnictwa z Subiektem, gdy kartoteka już istnieje.
        """
        if self.tylko_podglad:
            messagebox.showwarning(
                "Nazywanie",
                "Brak lokalnej kopii projektu — przejmij lock w RM_BAZA.",
                parent=self)
            return

        if not self.var_nazwa.get().strip():
            messagebox.showwarning(
                "Nazywanie",
                "Wpisz nazwę w polu „Nazwa po scaleniu” na dole okna —"
                " to ona zostanie nadana zaznaczonym pozycjom.\n\n"
                "Możesz wkleić ją z kartoteki („⬅ Wklej z Subiekt”)"
                " albo wybrać z podpowiedzi pod polem.", parent=self)
            self.ent_nazwa.focus_set()
            return

        zmiany = self._zmiany_nazw()
        if not zmiany:
            messagebox.showinfo(
                "Nazywanie",
                "Zaznaczone pozycje mają już tę nazwę.", parent=self)
            return

        dlg = OknoDialog(self, "Nazywanie — potwierdzenie",
                         f"Zmienić nazwy {len(zmiany)} pozycji?",
                         ikona="🏷", kolor="#2980b9")
        dlg.akapit("Nazwy zostaną przepisane z kartotek Subiekta. "
                   "Wiersze ZOSTAJĄ osobno — to nie jest scalanie.",
                   kolor="#5d6d7e", odstep=(0, 8))
        # `zmiany` to trojki (stary, nowy, opis) — pokazujemy czytelnie,
        # z opisem tylko gdy jakis jest.
        dlg.ramka_pozycji([
            "%s   →   %s%s" % (st, nw, ("   ·   " + op) if op else "")
            for st, nw, op in zmiany])
        dlg.sciezka("Kopia pliku projektu przed zmianą:", BACKUP_DIR)
        dlg.przyciski(potwierdz="Zmień nazwy", anuluj="Anuluj", kolor="#2980b9")
        if not dlg.pokaz():
            return

        self.btn_nazwij.config(state=tk.DISABLED)
        self.status.config(text="Zapisuję…")
        try:
            backup = self._kopia_przed_zmiana()
            r = S.zmien_nazwy(self.project_id, zmiany, backup_dir=BACKUP_DIR, con=self.con)
            self._zatwierdz_reczne()      # dopiero teraz — razem ze zmianą w BOM
        except Exception as e:
            self.status.config(text="Błąd zapisu.")
            messagebox.showerror("Nazywanie", str(e), parent=self)
            self._load_async()
            return

        odswiezony = self._odswiez_arkusz()
        wynik = OknoDialog(self, "Nazwy zmienione",
                           f"Zmieniono {r['zmienionych']} wystąpień",
                           ikona="✔", kolor="#1e8449")
        if r["szczegoly"]:
            wynik.ramka_pozycji([(s, n) for _c, s, n, _i in r["szczegoly"]])
        if not odswiezony:
            wynik.ostrzezenie("Odśwież arkusz, żeby zobaczyć zmiany.")
        if backup:
            wynik.sciezka("Kopia przed zmianą:", backup)
        wynik.przyciski(anuluj="OK")
        wynik.pokaz()
        self.status.config(text=f"Zmieniono {r['zmienionych']} nazw.")
        self._load_async()

    def _szukaj_w_subiekcie(self, p, iid=None):
        """Ręczne wskazanie kartoteki, gdy automat jej nie znalazł albo pomylił.

        Dopasowanie automatyczne wymaga zgodności po normalizacji, a kartoteka
        bywa założona pod zupełnie innym zapisem ('122UC' dla 'UCFL 201').
        Tu user szuka jej sam — lista filtruje się w miarę pisania.
        """
        # Jedna wyszukiwarka naraz. Jeśli już jest otwarta — podnosimy ją
        # zamiast otwierać kolejną.
        if self._okno_wyszukiwania is not None:
            try:
                self._okno_wyszukiwania.lift()
                self._okno_wyszukiwania.focus_force()
                return
            except tk.TclError:
                self._okno_wyszukiwania = None      # okno już nie istnieje

        # Podświetlenie wiersza, żeby było wiadomo, której pozycji dotyczy
        # otwierane okno. Zdejmuje je _refill() po zamknięciu wyszukiwarki.
        if iid:
            try:
                self.tree.item(iid, tags=("szukany",))
                self.tree.see(iid)
                self.update_idletasks()
            except tk.TclError:
                pass

        if not self._katalog:
            # Katalog bywa niepobrany mimo działającego Subiekta: gdy wszystkie
            # kody miały już mapowania lokalne, most nie był w ogóle pytany.
            # Dociągamy go teraz, na żądanie.
            self._pobierz_katalog_i_otworz(p)
            return

        self._okno_szukania(p)

    def _pobierz_katalog_i_otworz(self, p):
        """Ściąga kartoteki (kilkanaście sekund) i dopiero otwiera wyszukiwarkę."""
        # Tu jest najszersze okno na wielokrotne kliknięcie: użytkownik widzi
        # tylko kręciołek i klika dalej. Flaga trzyma jedno pobieranie.
        if getattr(self, "_pobieranie_katalogu", False):
            return
        self._pobieranie_katalogu = True
        self._start_kreciolek("Pobieram kartoteki z Subiekta")
        self.config(cursor="watch")

        def worker():
            try:
                katalog = S.wczytaj_katalog_subiekta()
                self.after(0, lambda: gotowe(katalog, None))
            except Exception as e:
                err = str(e)
                self.after(0, lambda: gotowe(None, err))

        def gotowe(katalog, error):
            self._pobieranie_katalogu = False
            self._stop_kreciolek()
            self.config(cursor="")
            if error:
                self.status.config(text="Subiekt niedostępny.")
                # Zdejmij żółte podświetlenie — wyszukiwarka się nie otworzy,
                # więc nie ma czego oznaczać jako „w toku".
                self._refill()
                messagebox.showerror(
                    "Szukaj w Subiekcie",
                    f"Nie udało się pobrać kartotek z Subiekta:\n\n{error}",
                    parent=self)
                return
            self._katalog = katalog
            self.status.config(text=f"Kartotek w Subiekcie: {len(katalog)}")
            self._okno_szukania(p)

        threading.Thread(target=worker, daemon=True).start()

    def _okno_szukania(self, p):
        okno = tk.Toplevel(self)
        self._okno_wyszukiwania = okno
        okno.title(f"Szukaj w Subiekcie — {p['kod']}")
        okno.transient(self)
        okno.grab_set()
        self._wysrodkuj_wzgledem(okno, self, 640, 420)

        tk.Label(okno, text=f"Pozycja w projekcie:   {p['kod']}",
                 font=("Arial", 9, "bold"), anchor="w").pack(fill=tk.X, padx=12, pady=(12, 2))
        tk.Label(okno, text="Wpisz fragment symbolu albo nazwy — lista zawęża się na bieżąco.",
                 font=("Arial", 8), fg="#555", anchor="w").pack(fill=tk.X, padx=12)

        var = tk.StringVar(value=p["kod"])
        ent = tk.Entry(okno, textvariable=var, font=("Consolas", 10))
        ent.pack(fill=tk.X, padx=12, pady=(6, 8), ipady=3)

        # Zamknięcie okna KAŻDYM sposobem (Anuluj, krzyżyk, Esc, wybór
        # kartoteki) musi zdjąć żółte podświetlenie wiersza — inaczej zostaje
        # na liście i sugeruje, że coś jest w toku.
        def zamknij():
            self._okno_wyszukiwania = None
            okno.destroy()
            self._refill()

        okno.protocol("WM_DELETE_WINDOW", zamknij)
        okno.bind("<Escape>", lambda _e: zamknij())

        # Przyciski i licznik pakowane PRZED listą i przypięte do dołu —
        # inaczej rozciągająca się lista spycha je poza okno i widać z nich
        # tylko górną połowę.
        dol = tk.Frame(okno)
        dol.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(6, 10))
        info = tk.Label(okno, text="", font=("Arial", 8), fg="#555", anchor="w")
        info.pack(side=tk.BOTTOM, fill=tk.X, padx=12)

        ramka = tk.Frame(okno)
        ramka.pack(fill=tk.BOTH, expand=True, padx=12)
        lista = ttk.Treeview(ramka, columns=("symbol", "nazwa"), show="headings", height=10)
        lista.heading("symbol", text="Symbol")
        lista.heading("nazwa", text="Nazwa")
        lista.column("symbol", width=170, stretch=False)
        lista.column("nazwa", width=420)
        vs = ttk.Scrollbar(ramka, orient="vertical", command=lista.yview)
        lista.configure(yscrollcommand=vs.set)
        lista.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)

        def odswiez(*_a):
            fraza = S.norm_kod(var.get())
            lista.delete(*lista.get_children())
            trafienia = []
            for poz in self._katalog:
                if not fraza or (fraza in S.norm_kod(poz["symbol"])
                                 or fraza in S.norm_kod(poz["nazwa"])):
                    trafienia.append(poz)
                if len(trafienia) >= 300:      # dłuższa lista i tak jest bezużyteczna
                    break
            for poz in trafienia:
                lista.insert("", "end", iid=str(poz["id"]),
                             values=(poz["symbol"], poz["nazwa"]))
            info.config(text=f"Pasujących kartotek: {len(trafienia)}"
                             + ("  (pokazano pierwsze 300)" if len(trafienia) >= 300 else ""))

        def wybierz(*_a):
            sel = lista.selection()
            if not sel:
                return
            poz = next((k for k in self._katalog if str(k["id"]) == sel[0]), None)
            if not poz:
                return
            # NIE zapisujemy jeszcze do bazy mapowań. Ta baza jest wspólna dla
            # wszystkich projektów i nie podlega lockowi, więc natychmiastowy
            # zapis przeżywał anulowanie locka — przypisanie zostawało, choć
            # user cofnął zmiany. Wybór trzymamy w pamięci okna; do bazy
            # trafia dopiero razem z zapisem BOM-u (Scal / Nazwij).
            self._subiekt[p["kod"]] = poz
            self._reczne[p["kod"]] = poz
            zamknij()

        def odepnij():
            """Usuwa powiązanie z kartoteką — dla błędnych dopasowań."""
            kody = [p["kod"]] + p["identyczne"]
            # Przypisanie niezatwierdzone (jeszcze nie w bazie) znika po prostu
            # z pamięci; zapisane trzeba usunąć z bazy mapowań.
            tylko_w_pamieci = all(k in self._reczne or k not in self._subiekt for k in kody)
            if not tylko_w_pamieci and not messagebox.askyesno(
                    "Odepnij kartotekę",
                    f"Usunąć powiązanie pozycji {p['kod']!r} z kartoteką Subiekta?\n\n"
                    "Dopasowanie zostanie policzone od nowa przy następnym otwarciu.",
                    parent=okno):
                return
            if not tylko_w_pamieci:
                try:
                    import subiekt_mapowania as M
                    for kod in kody:
                        M.delete(kod)
                except Exception:
                    pass
            for kod in kody:
                self._subiekt.pop(kod, None)
                self._reczne.pop(kod, None)
            zamknij()

        var.trace_add("write", odswiez)
        lista.bind("<Double-1>", wybierz)
        ent.bind("<Return>", lambda _e: (lista.selection_set(lista.get_children()[:1]), wybierz()))

        tk.Button(dol, text="Wybierz tę kartotekę", command=wybierz,
                  bg="#2980b9", fg="white", font=("Arial", 9, "bold"),
                  padx=12, pady=4).pack(side=tk.RIGHT)
        tk.Button(dol, text="Anuluj", command=zamknij,
                  font=("Arial", 9), padx=12, pady=4).pack(side=tk.RIGHT, padx=(0, 8))
        # Odpięcie kartoteki — gdy dopasowanie okazało się błędne. Bez tego
        # jedynym wyjściem byłoby ręczne grzebanie w bazie mapowań.
        if any(self._subiekt.get(k) for k in [p["kod"]] + p["identyczne"]):
            tk.Button(dol, text="Odepnij kartotekę", command=lambda: odepnij(),
                      font=("Arial", 9), padx=12, pady=4).pack(side=tk.LEFT)

        odswiez()
        ent.focus_set()
        ent.selection_range(0, tk.END)

    @staticmethod
    def _wysrodkuj_wzgledem(okno, rodzic, szer, wys):
        try:
            rodzic.update_idletasks()
            x = rodzic.winfo_rootx() + (rodzic.winfo_width() - szer) // 2
            y = rodzic.winfo_rooty() + (rodzic.winfo_height() - wys) // 2
            okno.geometry(f"{szer}x{wys}+{max(x, 0)}+{max(y, 0)}")
        except Exception:
            okno.geometry(f"{szer}x{wys}")

    def _kopia_przed_zmiana(self):
        """Kopia lokalnego pliku projektu (tryb lock). W trybie plikowym robi to silnik."""
        if self.con is None or not self.local_path or not os.path.isfile(self.local_path):
            return None
        self.con.commit()          # żeby kopia miała wszystko, co arkusz już zapisał
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cel = os.path.join(BACKUP_DIR, f"project_{self.project_id}_{stamp}.sqlite")
        shutil.copy2(self.local_path, cel)
        return cel

    def _zapisz_audit(self, wiersze, nazwa, raport):
        """Ślad w items_changes_log, tym samym kanałem co „Ukryj zaznaczone"."""
        log = getattr(self.master, "_log_item_change", None)
        if not callable(log):
            return
        for w in wiersze:
            try:
                log(w["id"], "MERGE", w["kolumna"], w["nazwa"],
                    f"{nazwa} (→ id {raport.get('nowy_id')})")
            except Exception:
                pass

    def _odswiez_arkusz(self):
        """Przeładuj arkusz RM_BAZA. To samo połączenie, więc widzi zmiany od razu."""
        metoda = getattr(self.master, "refresh_data", None)
        if not callable(metoda):
            return False
        try:
            metoda()
            return True
        except Exception:
            return False


def open_window(parent, project_id, project_name=None):
    """Punkt wejścia dla RM_BAZA."""
    if not project_id:
        messagebox.showwarning("Scalanie", "Najpierw wybierz projekt.", parent=parent)
        return None
    return ScalanieWindow(parent, project_id, project_name)


if __name__ == "__main__":
    import sys
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 52
    root = tk.Tk()
    root.withdraw()
    w = open_window(root, pid)
    w.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
