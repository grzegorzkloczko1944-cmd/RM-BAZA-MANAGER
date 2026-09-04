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
        ("kod",      "Kod w projekcie",       220, "w"),
        # Materiał zaraz za kodem — różny materiał to najczęstszy sygnał,
        # że dwa podobne kody to jednak inne elementy, więc ma być widoczny
        # od razu przy nazwie, a nie na końcu wiersza.
        ("material", "Materiał",              110, "w"),
        ("ilosc",    "Ilość BOM",              70, "e"),
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
        self.ent_nazwa.bind("<FocusOut>", lambda _e: self.after(150, self._ukryj_podpowiedzi))
        self.ent_nazwa.bind("<Escape>", lambda _e: self._ukryj_podpowiedzi())
        self._popup = None
        # Pole zostaje PUSTE, dopóki user sam czegoś nie wpisze albo nie użyje
        # przycisków obok — nazwa docelowa to decyzja, nie domysł programu.

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
            ma_co = bool(p["identyczne"] or p["podobne"])
            if tylko and not ma_co and p["klucz"] not in self._zaznaczone:
                continue
            pokazane += 1
            zaz = p["klucz"] in self._zaznaczone

            naj = ""
            if p["w_bazie"]:
                w, n = max(p["w_bazie"].items(), key=lambda t: t[1])
                naj = f"{w}  ({n} proj.)"

            podobne = [s["kod"] for s in p["podobne"]] + [f"= {k}" for k in p["identyczne"]]
            tags = ("zaz",) if zaz else (() if ma_co else ("cichy",))
            self.tree.insert("", "end", iid=p["klucz"], tags=tags, values=(
                "☑" if zaz else "☐",
                p["kod"],
                p["material"],
                f"{p['ilosc_bom']:g}",
                self._opis_subiekt(p),
                naj,
                "   ·   ".join(podobne),
            ))

        wybrane = [p for p in self.pozycje if p["klucz"] in self._zaznaczone]
        suma = sum(p["ilosc_bom"] for p in wybrane)
        z_kolizja = sum(1 for p in self.pozycje if p["identyczne"] or p["podobne"])
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
        szer = max(self.ent_nazwa.winfo_width(), 420)
        popup.geometry(f"{szer}x{min(len(trafienia), 12) * 26 + 2}+{x}+{y}")

        ramka = tk.Frame(popup, bg="#b0b8bd", bd=0)
        ramka.pack(fill=tk.BOTH, expand=True)
        wnetrze = tk.Frame(ramka, bg="white")
        wnetrze.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        def wybierz(nazwa):
            self.var_nazwa.set(nazwa)
            self._ukryj_podpowiedzi()
            self._refill()

        for poz in trafienia:
            nazwa = (poz["nazwa"] or "").strip() or (poz["symbol"] or "").strip()
            w = tk.Frame(wnetrze, bg="white", height=26)
            w.pack(fill=tk.X)
            w.pack_propagate(False)
            # Symbol na szaro po lewej, nazwa czarna — od razu widać, co jest czym.
            tk.Label(w, text=poz["symbol"], bg="white", fg="#7f8c8d", anchor="w",
                     width=16, font=("Consolas", 9)).pack(side=tk.LEFT, padx=(8, 4))
            tk.Label(w, text=nazwa, bg="white", fg="#2c3e50", anchor="w",
                     font=("Segoe UI", 9)).pack(side=tk.LEFT, fill=tk.X, expand=True)

            def podswietl(_e, ramka=w, kolor="#eaf2f8"):
                for dziecko in [ramka] + list(ramka.winfo_children()):
                    dziecko.configure(bg=kolor)

            for widget in [w] + list(w.winfo_children()):
                widget.bind("<Enter>", podswietl)
                widget.bind("<Leave>", lambda e, r=w: podswietl(e, r, "white"))
                widget.bind("<Button-1>", lambda _e, n=nazwa: wybierz(n))
                widget.configure(cursor="hand2")

    def _ustaw_nazwe(self, wartosc):
        self.var_nazwa.set(wartosc)
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
        if len(wiersze) < 2:
            messagebox.showerror("Scalanie", "Nie znaleziono wierszy do połączenia — "
                                 "odśwież i spróbuj ponownie.", parent=self)
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
            r = S.scal_wiersze(self.project_id, [w["id"] for w in wiersze], nazwa,
                               backup_dir=BACKUP_DIR, con=self.con)
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
        """[(zapis w BOM, nazwa kartoteki)] dla zaznaczonych pozycji.

        Bierzemy też warianty pisowni (`identyczne`), żeby po operacji nie
        zostały rozjechane zapisy tej samej rzeczy. Porównanie „czy jest co
        zmieniać" jest dosłowne — 'UCFL201' → 'UCFL 201' to realna zmiana
        zapisu, mimo że po normalizacji to jedno i to samo.
        """
        zmiany = []
        for p in self.pozycje:
            if p["klucz"] not in self._zaznaczone:
                continue
            for kod in [p["kod"]] + p["identyczne"]:
                poz = self._subiekt.get(kod)
                if not poz:
                    continue
                nazwa = (poz.get("nazwa") or "").strip() or (poz.get("symbol") or "").strip()
                if nazwa and nazwa != kod.strip():
                    zmiany.append((kod, nazwa))
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

        zmiany = self._zmiany_nazw()
        if not zmiany:
            messagebox.showinfo(
                "Nazywanie",
                "Zaznaczone pozycje mają już nazwy zgodne z Subiektem\n"
                "albo nie mają jeszcze kartoteki.", parent=self)
            return

        dlg = OknoDialog(self, "Nazywanie — potwierdzenie",
                         f"Zmienić nazwy {len(zmiany)} pozycji?",
                         ikona="🏷", kolor="#2980b9")
        dlg.akapit("Nazwy zostaną przepisane z kartotek Subiekta. "
                   "Wiersze ZOSTAJĄ osobno — to nie jest scalanie.",
                   kolor="#5d6d7e", odstep=(0, 8))
        dlg.ramka_pozycji(list(zmiany))
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
