# -*- coding: utf-8 -*-
"""Karta pozycji — nawigator po strukturze złożeń z pełnymi danymi detalu.

Otwierana dwuklikiem z okien Subiekta (Stany, Zamówienia ZD). Pokazuje dla
JEDNEJ pozycji wszystko, co o niej wiemy:

  * gdzie siedzi w złożeniu — ścieżka od korzenia w dół („należy do"),
  * co zawiera — składniki z ilościami (dla Z/ZZ),
  * dane z BOM-u RM_BAZA — id, numer, nazwa, ilość, typ, cena, dostawca…,
  * dane z Subiekta — kartoteka, stany per magazyn, ostatni zakup.

Klik w rodzica albo składnik PRZENOSI do tej pozycji w tym samym oknie
(„Wstecz” wraca). To zastępuje pomysł drzewka w oknie ZD: tamto okno
zapisuje (✓, dostawca, ilości) i adresuje wiersze arkusza wprost, więc
wiersze-węzły złożeń groziły zaznaczeniem cudzej pozycji. Karta jest
tylko do odczytu — nie ma czego popsuć (ustalone 06.09.2026).

Struktura z tego samego źródła co „Załóż projekt” i „Stany”:
arkusz „DRZEWKO TEKST” w *_OUT.xlsx (subiekt_projekt.read_tree).
"""

import os
import queue
import sqlite3
import threading
import tkinter as tk
from tkinter import messagebox

from rm_kreciolek import Kreciolek

TLO = "#ecf0f1"
TLO_SEKCJI = "#ffffff"
TEKST = "#2c3e50"
TEKST_SZARY = "#7f8c8d"
OBRAMOWANIE = "#bdc3c7"
LINK = "#1f618d"

#: Kolory ZRODLA danych. Karta laczy trzy rozne bazy i bez oznaczenia
#: nie bylo widac, co skad pochodzi (zgloszone 06.09.2026) - a to ma
#: znaczenie: rozjazd miedzy Inventorem a Subiektem to realny problem,
#: nie kosmetyka. Pasek w kolorze zrodla + etykieta w naglowku sekcji.
ZRODLA = {
    "inventor": ("#8e44ad", "#f4ecf7", "INVENTOR", "drzewko *_OUT.xlsx"),
    "rmbaza":   ("#1e8449", "#eafaf1", "RM_BAZA",  "arkusz projektu"),
    "subiekt":  ("#1f618d", "#eaf2f8", "SUBIEKT",  "przez most, na zywo"),
}

#: Log diagnostyczny karty - pythonw nie ma konsoli, wiec wyjatki z watkow
#: i z petli odbioru gina bez sladu. Ten sam katalog co logi mostu.
LOG = r"C:\RMPAK_CLIENT\subiekt_logi\karta.log"


def _log(tekst):
    try:
        import datetime
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(datetime.datetime.now().strftime("%H:%M:%S ") + tekst + "\n")
    except OSError:
        pass

#: Jedyne otwarte okno karty. Karta jest nawigatorem — z kazdej pozycji
#: da sie przejsc do rodzica, skladnika i do innego projektu, wiec przy
#: kilkunastu klikach robil sie stos identycznych okien, kazde z wlasnymi
#: watkami pytajacymi most (zgloszone 06.09.2026). Jedno okno, ktore
#: przelacza tresc, zamiast wielu.
_OTWARTA = None


#: Cache struktur per nazwa projektu — read_tree czyta Excela z dysku
#: sieciowego, a nawigacja w obrębie jednego projektu wraca do niego
#: dziesiątki razy.
_DRZEWA = {}


# ── dane ────────────────────────────────────────────────────────────────────
def drzewo(project_name):
    """(kids, nazwy) dla projektu; ({}, {}) gdy brak plików *_OUT.xlsx."""
    if not project_name:
        return {}, {}
    if project_name not in _DRZEWA:
        try:
            from subiekt_projekt import read_tree
            kids, _blad, nazwy = read_tree(project_name)
        except Exception:
            kids, nazwy = {}, {}
        _DRZEWA[project_name] = (
            {k.strip().upper(): v for k, v in (kids or {}).items()},
            {k.strip().upper(): v for k, v in (nazwy or {}).items()},
        )
    return _DRZEWA[project_name]


def rodzice(kids):
    """{dziecko: rodzic} — pierwszy rodzic, gdy detal siedzi w kilku złożeniach."""
    mapa = {}
    for rodzic, lista in kids.items():
        for dziecko, _q in lista:
            mapa.setdefault(dziecko.strip().upper(), rodzic)
    return mapa


def sciezka_w_gore(kids, nr):
    """[korzeń, …, rodzic] dla nr — bez samego nr. Pusta = poza strukturą."""
    mapa = rodzice(kids)
    droga, biezacy, odwiedzone = [], nr.strip().upper(), set()
    while biezacy in mapa and biezacy not in odwiedzone:
        odwiedzone.add(biezacy)
        biezacy = mapa[biezacy]
        droga.append(biezacy)
    droga.reverse()
    return droga


def dane_bom(project_id, nr):
    """Wiersz BOM-u dla numeru (albo nazwy — normalia nie mają numeru)."""
    if project_id is None:
        return None
    try:
        from subiekt_stany import PROJECTS_DIR
    except Exception:
        return None
    sciezka = os.path.join(PROJECTS_DIR, f"project_{project_id}.sqlite")
    if not os.path.isfile(sciezka):
        return None
    try:
        con = sqlite3.connect(f"file:{sciezka}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        try:
            r = con.execute(
                "SELECT * FROM items WHERE COALESCE(is_hidden,0)=0 AND ("
                "work_drawing_no=? COLLATE NOCASE OR norm_drawing_no=? COLLATE NOCASE "
                "OR src_drawing_no=? COLLATE NOCASE OR work_name=? COLLATE NOCASE "
                "OR src_name=? COLLATE NOCASE) LIMIT 1",
                (nr, nr, nr, nr, nr)).fetchone()
        finally:
            con.close()
        return dict(r) if r else None
    except sqlite3.Error:
        return None


#: Cache {NR: [(project_id, nazwa)]} — przeszukanie ~90 baz na Y: trwa
#: kilka sekund, a nawigacja wraca do tych samych numerow.
_PROJEKTY_POZYCJI = {}


def projekty_z_pozycja(nr):
    """[(project_id, nazwa projektu)] — wszystkie projekty, w ktorych BOM-ie
    jest ten numer (albo nazwa, dla normaliow). Ten sam detal bywa w kilku
    maszynach (kopia testowa 3000 ma rysunki 2632 Feniks), a przy zamawianiu
    trzeba wiedziec, na ktore projekty on idzie (zgloszone 06.09.2026).
    """
    nr_up = (nr or "").strip().upper()
    if not nr_up:
        return []
    if nr_up in _PROJEKTY_POZYCJI:
        return _PROJEKTY_POZYCJI[nr_up]
    import glob
    try:
        from subiekt_stany import PROJECTS_DIR
    except Exception:
        return []
    nazwy = {}
    try:
        con = sqlite3.connect(
            f"file:{os.path.join(os.path.dirname(PROJECTS_DIR), 'master.sqlite')}?mode=ro",
            uri=True, timeout=5)
        try:
            nazwy = {pid: (n or "") for pid, n in con.execute("SELECT project_id, name FROM projects")}
        finally:
            con.close()
    except sqlite3.Error:
        pass
    wynik = []
    for sciezka in glob.glob(os.path.join(PROJECTS_DIR, "project_*.sqlite")):
        try:
            pid = int(os.path.basename(sciezka)[8:-7])
        except ValueError:
            continue
        try:
            con = sqlite3.connect(f"file:{sciezka}?mode=ro", uri=True, timeout=3)
            try:
                r = con.execute(
                    "SELECT 1 FROM items WHERE COALESCE(is_hidden,0)=0 AND ("
                    "work_drawing_no=? COLLATE NOCASE OR norm_drawing_no=? COLLATE NOCASE "
                    "OR src_drawing_no=? COLLATE NOCASE OR work_name=? COLLATE NOCASE "
                    "OR src_name=? COLLATE NOCASE) LIMIT 1",
                    (nr_up, nr_up, nr_up, nr_up, nr_up)).fetchone()
            finally:
                con.close()
        except sqlite3.Error:
            continue                    # baza zablokowana/uszkodzona — pomijamy
        if r:
            wynik.append((pid, nazwy.get(pid, f"projekt {pid}")))
    wynik.sort(key=lambda x: x[1])
    _PROJEKTY_POZYCJI[nr_up] = wynik
    return wynik


def _pierwsze(*wartosci):
    for v in wartosci:
        if v not in (None, ""):
            return v
    return ""


# ── okno ────────────────────────────────────────────────────────────────────
class KartaPozycji(tk.Toplevel, Kreciolek):
    def __init__(self, rodzic, nr, project_id=None, project_name=None):
        super().__init__(rodzic)
        self.project_id = project_id
        self.project_name = project_name
        if not self.project_name and project_id is not None:
            try:
                from subiekt_stany import nazwa_projektu
                self.project_name = nazwa_projektu(project_id)
            except Exception:
                self.project_name = ""
        self.kids, self.nazwy = drzewo(self.project_name)
        self.historia = []
        self._subiekt_watek = 0
        # ⚠️ Wyniki z watkow wracaja KOLEJKA, nie przez self.after() z watku.
        # after() dotyka tkintera i wolane spoza watku glownego rzuca
        # "main thread is not in main loop" — bez sladu w pythonw. Sekcja
        # Subiekt zostawala wtedy pusta (po "Wstecz", 06.09.2026). Ten sam
        # wzorzec co w subiekt_panel._odbierz_wyniki.
        self._wyniki = queue.Queue()

        self.title("Karta pozycji")
        self.configure(bg=TLO)
        self.geometry("760x680")
        self.minsize(600, 480)

        self._buduj_szkielet()
        try:
            from subiekt_stany import wysrodkuj
            wysrodkuj(self, rodzic)
        except Exception:
            pass
        self._odbierz_wyniki()
        # Zamkniecie karty (X albo Alt+F4) musi zwolnic uchwyt, inaczej
        # kolejne wywolanie probowaloby ozywic martwe okno.
        self.protocol("WM_DELETE_WINDOW", self._zamknij)
        global _OTWARTA
        _OTWARTA = self
        self.pokaz(nr, zapamietaj=False)

    def _zamknij(self):
        global _OTWARTA
        if _OTWARTA is self:
            _OTWARTA = None
        self.destroy()

    def _odbierz_wyniki(self):
        """Puls z watku glownego: wykonuje to, co odlozyly watki robocze."""
        try:
            while True:
                akcja = self._wyniki.get_nowait()
                try:
                    akcja()
                except Exception:
                    # NIGDY nie przerywac petli odbioru. Wczesniej TclError
                    # z jednej akcji konczyl ja "return" - i wszystkie kolejne
                    # odpowiedzi (po "Wstecz") juz nie dochodzily: sekcja
                    # Subiekt zostawala pusta bez zadnego komunikatu.
                    import traceback
                    _log("akcja z kolejki padla:" + traceback.format_exc())
        except queue.Empty:
            pass
        try:
            if self.winfo_exists():
                self.after(120, self._odbierz_wyniki)
        except tk.TclError:
            pass

    # ── szkielet ────────────────────────────────────────────────────────────
    def _buduj_szkielet(self):
        top = tk.Frame(self, bg="#34495e", height=46)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        self.btn_wstecz = tk.Button(top, text="← Wstecz", command=self.wstecz,
                                    bg="#5499c7", fg="white", font=("Arial", 8),
                                    padx=8, pady=2, relief=tk.RAISED, bd=1,
                                    state=tk.DISABLED)
        self.btn_wstecz.pack(side=tk.LEFT, padx=10, pady=8)
        self.lbl_tytul = tk.Label(top, text="", bg="#34495e", fg="white",
                                  font=("Arial", 11, "bold"), anchor="w")
        self.lbl_tytul.pack(side=tk.LEFT, padx=6)
        self.lbl_projekt = tk.Label(top, text="", bg="#34495e", fg="#d5dbdb",
                                    font=("Arial", 9), anchor="e")
        self.lbl_projekt.pack(side=tk.RIGHT, padx=12)

        # Do jakich projektow nalezy pozycja — pod tytulem, zawsze widoczne.
        # Liczone w tle (przeszukanie wszystkich baz projektow), wiec karta
        # otwiera sie od razu, a lista dochodzi po chwili.
        # Kazdy projekt to LINK: klik przelacza karte na ten projekt (BOM,
        # zlozenie, ID), a wtedy klik w ID skacze do niego. Bez tego przy
        # detalu w kilku maszynach karta zawsze szla do projektu, z ktorego
        # ja otwarto (pytanie 06.09.2026: "co zrobic zeby skakalo do tego,
        # ktory chce"). Aktywny projekt pogrubiony, nieklikalny.
        self.ramka_projekty = tk.Frame(self, bg="#d6dbdf", padx=12, pady=4)
        self.ramka_projekty.pack(side=tk.TOP, fill=tk.X)
        self.lbl_projekty = tk.Label(self.ramka_projekty, text="", bg="#d6dbdf",
                                     fg=TEKST, font=("Arial", 9), anchor="w")
        self.lbl_projekty.pack(side=tk.LEFT)

        # Treść przewijana — sekcje bywają długie (23 składniki w korzeniu).
        ramka = tk.Frame(self, bg=TLO)
        ramka.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(ramka, bg=TLO, highlightthickness=0)
        sb = tk.Scrollbar(ramka, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.wnetrze = tk.Frame(self.canvas, bg=TLO)
        self._okno_canvas = self.canvas.create_window((0, 0), window=self.wnetrze, anchor="nw")
        self.wnetrze.bind("<Configure>", lambda _e: self._przelicz_scroll())
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._okno_canvas, width=e.width))
        # ⚠️ bind() na canvasie i na wnetrzu, NIE bind_all(). bind_all zaklada
        # binding GLOBALNY — karta przechwytywala kolko myszy takze nad innymi
        # oknami, a po jej zamknieciu handler zostawal i sypal bledami.
        # Kolko musi tez dzialac nad dziecmi wnetrza (etykiety zajmuja
        # praktycznie cala powierzchnie), stad _podepnij_kolko rekurencyjnie.
        for w in (self.canvas, self.wnetrze):
            w.bind("<MouseWheel>", self._kolko)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#d6dbdf", fg=TEKST, font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    def _kolko(self, event):
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")
        return "break"

    def _podepnij_kolko(self, widget):
        """Kolko myszy nad KAZDYM widgetem tresci.

        Etykiety i ramki sekcji zakrywaja canvas, a zdarzenie <MouseWheel>
        nie propaguje sie w gore do rodzica — bez tego przewijanie dzialalo
        tylko nad waskim marginesem (06.09.2026, po dodaniu kolorowych ramek).
        """
        try:
            widget.bind("<MouseWheel>", self._kolko)
            for dziecko in widget.winfo_children():
                self._podepnij_kolko(dziecko)
        except tk.TclError:
            pass

    def _przelicz_scroll(self):
        """Aktualizuje obszar przewijania po zmianie tresci."""
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except tk.TclError:
            pass

    def _sekcja(self, tytul, podtytul="", zrodlo=None):
        """Sekcja z paskiem w kolorze ZRODLA danych i plakietka.

        `zrodlo`: "inventor" | "rmbaza" | "subiekt" (patrz ZRODLA).
        Bez niego sekcja jest neutralna.
        """
        kolor, tlo_plakietki, nazwa, opis = ZRODLA.get(zrodlo, (OBRAMOWANIE, TLO_SEKCJI, "", ""))
        zewnetrzna = tk.Frame(self.wnetrze, bg=kolor, highlightthickness=1,
                              highlightbackground=OBRAMOWANIE)
        zewnetrzna.pack(fill=tk.X, padx=12, pady=(10, 0))
        # Pasek 4 px po lewej — w kolorze zrodla.
        ramka = tk.Frame(zewnetrzna, bg=TLO_SEKCJI)
        ramka.pack(fill=tk.X, padx=(4 if zrodlo else 0, 0), pady=0)

        naglowek = tk.Frame(ramka, bg=TLO_SEKCJI)
        naglowek.pack(fill=tk.X, padx=12, pady=(8, 4))
        tk.Label(naglowek, text=tytul, bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        if zrodlo:
            tk.Label(naglowek, text=f" {nazwa} ", bg=tlo_plakietki, fg=kolor,
                     font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=(8, 0))
            tk.Label(naglowek, text="  " + opis, bg=TLO_SEKCJI, fg=kolor,
                     font=("Arial", 8)).pack(side=tk.LEFT)
        if podtytul:
            tk.Label(naglowek, text="   " + podtytul, bg=TLO_SEKCJI, fg=TEKST_SZARY,
                     font=("Arial", 8)).pack(side=tk.LEFT)
        wnetrze = tk.Frame(ramka, bg=TLO_SEKCJI)
        wnetrze.pack(fill=tk.X, padx=12, pady=(0, 10))
        return wnetrze

    def _link(self, rodzic, nr, opis="", wciecie=0):
        """Klikalny wiersz „numer — nazwa”. Klik przenosi do tej pozycji."""
        w = tk.Frame(rodzic, bg=TLO_SEKCJI)
        w.pack(fill=tk.X, pady=1)
        tk.Label(w, text=" " * wciecie, bg=TLO_SEKCJI).pack(side=tk.LEFT)
        b = tk.Label(w, text=nr, bg=TLO_SEKCJI, fg=LINK, cursor="hand2",
                     font=("Consolas", 9, "underline"))
        b.pack(side=tk.LEFT)
        b.bind("<Button-1>", lambda _e, n=nr: self.pokaz(n))
        if opis:
            tk.Label(w, text="   " + opis, bg=TLO_SEKCJI, fg=TEKST,
                     font=("Arial", 9)).pack(side=tk.LEFT)
        return w

    def _wiersz_kv(self, rodzic, klucz, wartosc, wyroznij=False):
        w = tk.Frame(rodzic, bg=TLO_SEKCJI)
        w.pack(fill=tk.X, pady=1)
        tk.Label(w, text=klucz, bg=TLO_SEKCJI, fg=TEKST_SZARY, width=22,
                 anchor="w", font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Label(w, text=str(wartosc), bg=TLO_SEKCJI, fg=TEKST, anchor="w",
                 justify="left", wraplength=480,
                 font=("Arial", 9, "bold" if wyroznij else "normal")).pack(side=tk.LEFT)

    def _wiersz_link(self, rodzic, klucz, wartosc, akcja, podpowiedz=""):
        """Jak _wiersz_kv, ale wartosc jest klikalna."""
        w = tk.Frame(rodzic, bg=TLO_SEKCJI)
        w.pack(fill=tk.X, pady=1)
        tk.Label(w, text=klucz, bg=TLO_SEKCJI, fg=TEKST_SZARY, width=22,
                 anchor="w", font=("Arial", 9)).pack(side=tk.LEFT)
        l = tk.Label(w, text=str(wartosc), bg=TLO_SEKCJI, fg=LINK, cursor="hand2",
                     font=("Arial", 9, "underline"))
        l.pack(side=tk.LEFT)
        l.bind("<Button-1>", lambda _e: akcja())
        if podpowiedz:
            tk.Label(w, text="   " + podpowiedz, bg=TLO_SEKCJI, fg=TEKST_SZARY,
                     font=("Arial", 8)).pack(side=tk.LEFT)

    def _glowne_okno(self):
        """Okno RM_BAZA - po lancuchu master (karta <- Stany/ZD <- RM_BAZA)."""
        w = self.master
        while w is not None and not hasattr(w, "jump_to_bom_item"):
            w = getattr(w, "master", None)
        return w

    def _skocz_do_arkusza(self, item_id):
        """Klik w ID: zaznacz ten wiersz w arkuszu RM_BAZA (przelacza projekt,
        jesli trzeba - z ochrona locka po stronie RM_BAZA)."""
        app = self._glowne_okno()
        if app is None:
            self.status.config(text="Brak polaczenia z oknem RM_BAZA.")
            return
        if app.jump_to_bom_item(self.project_id, item_id):
            self.status.config(text=f"Zaznaczono wiersz {item_id} w arkuszu RM_BAZA.")
        else:
            self.status.config(text="Nie udalo sie przejsc do arkusza (lock na innym projekcie?).")

    # ── nawigacja ───────────────────────────────────────────────────────────
    def pokaz(self, nr, zapamietaj=True):
        nr = (nr or "").strip()
        if not nr:
            return
        if zapamietaj and getattr(self, "biezacy", None) and self.biezacy != nr:
            self.historia.append(self.biezacy)
        self.biezacy = nr
        self.btn_wstecz.config(state=tk.NORMAL if self.historia else tk.DISABLED)
        for w in self.wnetrze.winfo_children():
            w.destroy()
        self.canvas.yview_moveto(0)
        self._wypelnij(nr)
        # Tresc dopiero co powstala — podpinamy kolko do nowych widgetow
        # i przeliczamy obszar przewijania (bbox liczy sie po ulozeniu).
        self.after_idle(self._po_zbudowaniu)

    def _po_zbudowaniu(self):
        self._podepnij_kolko(self.wnetrze)
        self._przelicz_scroll()

    def wstecz(self):
        if self.historia:
            self.pokaz(self.historia.pop(), zapamietaj=False)

    # ── treść ───────────────────────────────────────────────────────────────
    def _wypelnij(self, nr):
        _log(f"wypelnij nr={nr}")
        nr_up = nr.upper()
        bom = dane_bom(self.project_id, nr)
        nazwa = _pierwsze(
            bom and bom.get("work_name"), bom and bom.get("src_name"),
            self.nazwy.get(nr_up, ""))
        self.lbl_tytul.config(text=f"{nr}   {nazwa}" if nazwa else nr)
        self.title(f"Karta pozycji — {nr}")

        droga = sciezka_w_gore(self.kids, nr_up)
        skladniki = self.kids.get(nr_up, [])

        # Czym jest pozycja - wprost, zamiast kazac wnioskowac z braku sekcji
        # "Zawiera" ("jest towarem a nie zlozeniem", 06.09.2026). Typ z BOM-u
        # (X/XX = detal, Z/ZZ = komplet), a gdy go brak - z samej struktury.
        typ_bom = _pierwsze(bom and bom.get("class_manual"), bom and bom.get("class_effective"),
                            bom and bom.get("class_auto"))
        if skladniki:
            rodzaj = f"złożenie{f' ({typ_bom})' if typ_bom else ''} — {len(skladniki)} składników"
        elif typ_bom in ("Z", "ZZ"):
            rodzaj = f"złożenie ({typ_bom}) — bez składników w drzewku"
        elif typ_bom:
            rodzaj = f"detal ({typ_bom})"
        else:
            rodzaj = "detal / towar"
        self.lbl_projekt.config(text=f"{rodzaj}    ·    {self.project_name or ''}")

        # ── należy do ──
        if droga:
            s = self._sekcja("Należy do", "ścieżka od korzenia — klik przenosi", "inventor")
            for glebokosc, wezel in enumerate(droga):
                self._link(s, wezel, self.nazwy.get(wezel, ""), wciecie=glebokosc * 3)
            tk.Label(s, text=" " * (len(droga) * 3) + f"└ {nr}   ← ta pozycja",
                     bg=TLO_SEKCJI, fg=TEKST, font=("Consolas", 9, "bold"),
                     anchor="w").pack(fill=tk.X, pady=(1, 0))
        elif self.kids and nr_up not in self.kids:
            s = self._sekcja("Należy do", "", "inventor")
            tk.Label(s, text="poza strukturą złożeń Inventora (np. normalia — łożyska, paski)",
                     bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 9),
                     anchor="w").pack(fill=tk.X)
        elif not self.kids:
            s = self._sekcja("Należy do", "", "inventor")
            tk.Label(s, text="brak struktury — nie znaleziono arkusza „DRZEWKO TEKST” (*_OUT.xlsx)",
                     bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 9),
                     anchor="w").pack(fill=tk.X)

        # ── zawiera ──
        if skladniki:
            s = self._sekcja("Zawiera", f"{len(skladniki)} składników — klik przenosi", "inventor")
            for dziecko, qty in skladniki:
                d = dziecko.strip().upper()
                ile = f"× {qty:g}" if isinstance(qty, (int, float)) else f"× {qty}"
                self._link(s, d, f"{self.nazwy.get(d, '')}    {ile}")

        # ── RM_BAZA ──
        s = self._sekcja("Dane pozycji", "", "rmbaza")
        if bom:
            typ = _pierwsze(bom.get("class_manual"), bom.get("class_effective"),
                            bom.get("class_auto"))
            ilosc = _pierwsze(bom.get("order_qty"), bom.get("work_qty"), bom.get("src_qty"))
            cena = bom.get("price_pln")
            self._wiersz_link(s, "ID (wiersz BOM)", bom.get("id"),
                              lambda i=bom.get("id"): self._skocz_do_arkusza(i),
                              "klik = pokaz w arkuszu RM_BAZA")
            self._wiersz_kv(s, "Numer rysunku", _pierwsze(
                bom.get("work_drawing_no"), bom.get("norm_drawing_no"),
                bom.get("src_drawing_no")) or "— (pozycja bez numeru)")
            self._wiersz_kv(s, "Nazwa", nazwa, wyroznij=True)
            self._wiersz_kv(s, "Ilość", f"{ilosc}" if ilosc != "" else "—")
            self._wiersz_kv(s, "Typ", typ or "—")
            self._wiersz_kv(s, "Cena PLN", f"{cena:.2f}" if isinstance(cena, (int, float)) else "—")
            self._wiersz_kv(s, "Dostawca (BOM)", _pierwsze(bom.get("src_supplier_text")) or "—")
            self._wiersz_kv(s, "Materiał", _pierwsze(
                bom.get("mat_manual_text"), bom.get("mat_effective_text"),
                bom.get("mat_auto_text"), bom.get("src_material_text")) or "—")
            gr = bom.get("thickness_mm")
            self._wiersz_kv(s, "Grubość [mm]", f"{gr:g}" if isinstance(gr, (int, float)) else "—")
            self._wiersz_kv(s, "Moduł", _pierwsze(bom.get("work_modul"), bom.get("src_modul")) or "—")
            pliki = [n for n, k in (("DXF", "has_dxf"), ("DWF", "has_dwf"),
                                    ("IDW", "has_idw"), ("STP", "has_stp"),
                                    ("STL", "has_stl")) if bom.get(k)]
            self._wiersz_kv(s, "Pliki", ", ".join(pliki) or "—")
            self._wiersz_kv(s, "Zamówiono", _pierwsze(bom.get("ordered_at")) or "—")
            dost = bom.get("delivered_qty")
            self._wiersz_kv(s, "Dostarczono", f"{dost}" if dost not in (None, "") else "—")
            self._wiersz_kv(s, "Termin", _pierwsze(bom.get("deadline_date")) or "—")
            self._wiersz_kv(s, "Status", _pierwsze(bom.get("status")) or "—")
            if bom.get("notes"):
                self._wiersz_kv(s, "Uwagi", bom["notes"])
            self._wiersz_kv(s, "Źródło", f"{bom.get('source') or ''}  {bom.get('src_doc') or ''}".strip())
        else:
            tk.Label(s, text="nie ma tej pozycji w BOM-ie projektu"
                     + ("" if self.project_id is not None else " (okno nie zna projektu)"),
                     bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 9), anchor="w").pack(fill=tk.X)

        # ── Subiekt (w tle) ──
        self.sekcja_subiekt = self._sekcja("Kartoteka i stany", "", "subiekt")
        self.lbl_subiekt = tk.Label(self.sekcja_subiekt, text="",
                                    bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 9), anchor="w")
        self.lbl_subiekt.pack(fill=tk.X)
        # ⚠️ NIE self.lbl_projekty.config(): _projekty_gotowe kasuje WSZYSTKIE
        # dzieci ramki (zeby zbudowac linki), wiec ta etykieta po pierwszym
        # wypelnieniu juz nie istnieje. config() rzucal TclError i _wypelnij
        # konczylo sie TUTAJ - watki Subiekta nigdy nie startowaly, sekcja
        # zostawala pusta po kazdej nawigacji (log: jeden start na cala
        # sesje, 06.09.2026). Ramke budujemy od nowa za kazdym razem.
        try:
            for w in self.ramka_projekty.winfo_children():
                w.destroy()
            self.lbl_projekty = tk.Label(self.ramka_projekty, text="Projekty: szukam…",
                                         bg="#d6dbdf", fg=TEKST, font=("Arial", 9), anchor="w")
            self.lbl_projekty.pack(side=tk.LEFT)
        except tk.TclError:
            pass
        threading.Thread(target=self._projekty_worker, args=(nr, self._subiekt_watek + 1),
                         daemon=True).start()
        self.start_kreciolek("Pytam Subiekta o " + nr)
        self._subiekt_watek += 1
        threading.Thread(target=self._subiekt_worker, args=(nr, self._subiekt_watek),
                         daemon=True).start()

    def _projekty_worker(self, nr, numer_watku):
        lista = projekty_z_pozycja(nr)
        self._wyniki.put(lambda: self._projekty_gotowe(numer_watku, lista))

    def _projekty_gotowe(self, numer_watku, lista):
        if numer_watku != self._subiekt_watek:
            return                      # uzytkownik przeszedl dalej
        try:
            for w in self.ramka_projekty.winfo_children():
                w.destroy()
            if not lista:
                tk.Label(self.ramka_projekty, text="Projekty: nie ma tej pozycji w zadnym BOM-ie",
                         bg="#d6dbdf", fg=TEKST, font=("Arial", 9)).pack(side=tk.LEFT)
                return
            tk.Label(self.ramka_projekty, text=f"Projekty ({len(lista)}):  ",
                     bg="#d6dbdf", fg=TEKST, font=("Arial", 9)).pack(side=tk.LEFT)
            for i, (pid, nazwa) in enumerate(lista):
                if i:
                    tk.Label(self.ramka_projekty, text="  •  ", bg="#d6dbdf",
                             fg=TEKST_SZARY, font=("Arial", 9)).pack(side=tk.LEFT)
                if pid == self.project_id:
                    tk.Label(self.ramka_projekty, text=nazwa, bg="#d6dbdf", fg=TEKST,
                             font=("Arial", 9, "bold")).pack(side=tk.LEFT)
                else:
                    l = tk.Label(self.ramka_projekty, text=nazwa, bg="#d6dbdf", fg=LINK,
                                 cursor="hand2", font=("Arial", 9, "underline"))
                    l.pack(side=tk.LEFT)
                    l.bind("<Button-1>", lambda _e, p=pid, n=nazwa: self._zmien_projekt(p, n))
        except tk.TclError:
            pass

    def _zmien_projekt(self, project_id, nazwa):
        """Przelacza karte na inny projekt tej samej pozycji."""
        self.project_id = project_id
        self.project_name = nazwa
        self.kids, self.nazwy = drzewo(nazwa)
        self.pokaz(self.biezacy, zapamietaj=False)
        self.status.config(text=f"Karta pokazuje teraz projekt: {nazwa}")

    def _subiekt_worker(self, nr, numer_watku):
        _log(f"subiekt_worker start nr={nr} watek={numer_watku}")
        try:
            import subiekt_bridge as most
            odp = most.wywolaj("stan", symbole=[nr], timeout=120)
            poz = (odp or {}).get("pozycje") or []
            dane = poz[0] if poz else {}
            blad = None
        except Exception as e:
            dane, blad = {}, str(e)
        # Sklad kompletu i relacja odwrotna — osobne zapytanie, bo tryb "stan"
        # ich nie zwraca. Blad tutaj nie moze przykryc stanow, wiec lapiemy
        # osobno i pokazujemy sekcje jako "nie sprawdzono".
        sklad = None
        try:
            import subiekt_bridge as most
            odp = most.wywolaj("komplet", symbole=[nr], timeout=120)
            poz = (odp or {}).get("pozycje") or []
            sklad = poz[0] if poz else None
        except Exception:
            sklad = None
        self._wyniki.put(lambda: self._subiekt_gotowe(nr, numer_watku, dane, blad, sklad))

    def _subiekt_gotowe(self, nr, numer_watku, dane, blad, sklad=None):
        _log(f"subiekt_gotowe nr={nr} watek={numer_watku}/{self._subiekt_watek} "
             f"istnieje={bool(dane and dane.get('Istnieje'))} blad={blad!r} "
             f"sklad={'tak' if sklad else 'nie'}")
        # Użytkownik mógł już przejść dalej — odpowiedź na starą pozycję
        # nie może nadpisać sekcji nowej.
        if numer_watku != self._subiekt_watek:
            _log("  -> odrzucona (stary watek)")
            return
        self.stop_kreciolek("")
        # ⚠️ Etykieta "czekam" moze juz nie istniec: przy "Wstecz" _wypelnij
        # kasuje cala tresc i buduje nowa sekcje, wiec self.lbl_subiekt
        # wskazuje na zniszczony widget. destroy() rzucalo wtedy TclError,
        # a wyjatek konczyl metode PRZED wypelnieniem sekcji — po powrocie
        # zakladka Subiekt zostawala pusta (zgloszone 06.09.2026).
        try:
            self.lbl_subiekt.destroy()
        except tk.TclError:
            pass
        s = self.sekcja_subiekt
        try:
            s.winfo_exists()
        except tk.TclError:
            return                      # okno zamkniete w trakcie
        if blad:
            tk.Label(s, text="nie udało się zapytać Subiekta: " + blad.split("\n")[0],
                     bg=TLO_SEKCJI, fg="#c0392b", font=("Arial", 9), anchor="w",
                     wraplength=600, justify="left").pack(fill=tk.X)
            return
        if not dane or not dane.get("Istnieje"):
            tk.Label(s, text="brak kartoteki w Subiekcie — pozycja jest nowa, kartoteka "
                             "powstanie przy pierwszym zamówieniu",
                     bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 9), anchor="w",
                     wraplength=600, justify="left").pack(fill=tk.X)
            return
        dop = dane.get("Dopasowanie") or ""
        self._wiersz_kv(s, "Symbol", str(dane.get("Symbol") or "")
                        + ("   ⚠ dopasowano luźno" if dop == "luzne" else ""), wyroznij=True)
        self._wiersz_kv(s, "Nazwa w Subiekcie", dane.get("Nazwa") or "—")
        self._wiersz_kv(s, "Rodzaj", dane.get("Rodzaj") or "—")
        self._wiersz_kv(s, "Dostępne", f"{float(dane.get('Dostepne') or 0):g}")
        self._wiersz_kv(s, "Zadysponowane", f"{float(dane.get('Zadysponowane') or 0):g}")
        cena = dane.get("OstatniaCenaZakupu")
        self._wiersz_kv(s, "Ostatnia cena zakupu",
                        f"{cena:.2f} PLN  ({dane.get('DataOstatniegoZakupu') or 'data nieznana'})"
                        if isinstance(cena, (int, float)) else "brak danych o zakupach")
        mags = dane.get("Magazyny") or []
        if mags:
            self._wiersz_kv(s, "Stany per magazyn", "")
            for m in mags:
                self._wiersz_kv(
                    s, "    " + str(m.get("Magazyn") or "?"),
                    f"dostępne {float(m.get('Dostepne') or 0):g}   "
                    f"zadysponowane {float(m.get('Zadysponowane') or 0):g}   "
                    f"rezerwacje {float(m.get('RezerwacjaIlosciowa') or 0):g}"
                    f"/{float(m.get('RezerwacjaDostawowa') or 0):g}")
        else:
            self._wiersz_kv(s, "Stany per magazyn", "kartoteka bez ruchu magazynowego")
        self._sklad_subiekta(sklad, nr)
        # Sekcje Subiekta dochodza PO zbudowaniu karty, wiec obszar
        # przewijania trzeba przeliczyc ponownie — inaczej dolne sekcje
        # sa poza zasiegiem suwaka.
        self.after_idle(self._po_zbudowaniu)

        # Wszystko, czego nie wypisaliśmy jawnie — żeby żadne pole z mostu
        # nie przepadło, gdy dojdzie nowe.
        znane = {"Pytany", "Symbol", "Istnieje", "Nazwa", "Rodzaj", "Dostepne",
                 "Zadysponowane", "OstatniaCenaZakupu", "DataOstatniegoZakupu",
                 "Magazyny", "Dopasowanie"}
        for k, v in dane.items():
            if k not in znane and v not in (None, "", [], {}):
                self._wiersz_kv(s, k, v)


    def _sklad_subiekta(self, sklad, nr):
        """Sekcja: co komplet ZAWIERA i W CZYM SIEDZI — wg Subiekta.

        To odpowiedz na obawe "czy komplety nie wisza w powietrzu"
        (06.09.2026): rodzaj kartoteki (Komplet/Towar) nic nie mowi
        o powiazaniach, dopiero sklad i relacja odwrotna. Dane z trybu
        "komplet" mostu — Sfera trzyma je jako SkladnikiKompletu
        i SkladnikiWKompletach.

        Porownujemy TEZ z Inventorem: rozjazd miedzy drzewkiem *_OUT.xlsx
        a struktura w Subiekcie znaczy, ze zlozenie zalozono przed zmiana
        konstrukcji albo czesc skladnikow nie miala kartotek.
        """
        s = self._sekcja("Struktura złożenia", "składniki i komplety nadrzędne", "subiekt")
        if sklad is None:
            tk.Label(s, text="nie sprawdzono (most nie odpowiedział na zapytanie o skład)",
                     bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 9),
                     anchor="w").pack(fill=tk.X)
            return
        if not sklad.get("Istnieje"):
            tk.Label(s, text="brak kartoteki — nie ma czego wiązać",
                     bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 9),
                     anchor="w").pack(fill=tk.X)
            return

        skladniki = sklad.get("Skladniki") or []
        nadrzedne = sklad.get("WchodziW") or []
        rodzaj = sklad.get("Rodzaj") or ""

        # ── zawiera ──
        if skladniki:
            self._wiersz_kv(s, "Zawiera", f"{len(skladniki)} składników", wyroznij=True)
            for x in skladniki:
                self._wiersz_link(
                    s, "    " + str(x.get("Symbol") or ""),
                    f"× {float(x.get('Ilosc') or 0):g}   {x.get('Rodzaj') or ''}   "
                    f"{(x.get('Nazwa') or '')[:34]}",
                    lambda n=x.get("Symbol"): self.pokaz(n))
        elif rodzaj == "Komplet":
            # Komplet BEZ skladnikow to realny problem — Subiekt nie rozbije
            # go na wydaniu, wiec zamowienie takiego kompletu nic nie zdejmie
            # ze stanu skladnikow.
            self._wiersz_kv(s, "Zawiera", "⚠ NIC — komplet bez składników", wyroznij=True)
        else:
            self._wiersz_kv(s, "Zawiera", "— (to nie komplet)")

        # ── wchodzi w ──
        if nadrzedne:
            self._wiersz_kv(s, "Wchodzi w skład", f"{len(nadrzedne)} kompletów", wyroznij=True)
            for x in nadrzedne:
                self._wiersz_link(
                    s, "    " + str(x.get("Symbol") or ""),
                    f"× {float(x.get('Ilosc') or 0):g}   {x.get('Rodzaj') or ''}   "
                    f"{(x.get('Nazwa') or '')[:34]}",
                    lambda n=x.get("Symbol"): self.pokaz(n))
        else:
            self._wiersz_kv(s, "Wchodzi w skład",
                            "nie wchodzi w żaden komplet (pozycja samodzielna)")

        # ── porownanie z Inventorem ──
        nr_up = (nr or "").strip().upper()
        z_drzewka = {(c[0] or "").strip().upper() for c in self.kids.get(nr_up, [])}
        z_subiekta = {(x.get("Symbol") or "").strip().upper() for x in skladniki}

        # PUSTE DRZEWKO = "nie ma z czym porownac", a NIE "w Inventorze nic
        # nie ma". Bez tego kazdy skladnik z Subiekta wypadal jako "nadmiar",
        # bo nie znajdowal sie w pustym zbiorze — i komplet z poprawnym
        # skladem dostawal ostrzezenie na wszystkie pozycje naraz
        # (zgloszone 07.09.2026: 2627-200.08ZZ, 6 skladnikow, wszystkie OK).
        #
        # Drzewko bywa puste z powodow niezaleznych od danych: okno otwarte
        # bez projektu, pozycja spoza tego BOM-u, brak pliku *_OUT.xlsx.
        # W kazdym z tych przypadkow porownanie jest bez podstaw i nie wolno
        # go pokazywac jako rozjazdu.
        if not z_drzewka:
            if z_subiekta:
                self._wiersz_kv(s, "Zgodność z Inventorem",
                                "nie porównano — brak drzewka dla tej pozycji "
                                "(otwórz projekt, żeby sprawdzić skład)")
            return
        if not z_subiekta:
            return
        # Numery w Inventorze i w Subiekcie roznia sie koncowka typu
        # (2632-350.22X vs 2632-350.22) — porownujemy rdzenie.
        brak_w_sub = {x for x in z_drzewka
                      if _bez_ogona(x) not in {_bez_ogona(y) for y in z_subiekta}}
        nadmiar = {x for x in z_subiekta
                   if _bez_ogona(x) not in {_bez_ogona(y) for y in z_drzewka}}
        if not brak_w_sub and not nadmiar:
            if z_drzewka:
                self._wiersz_kv(s, "Zgodność z Inventorem", "✓ skład taki sam jak w drzewku")
            return
        if brak_w_sub:
            self._wiersz_kv(s, "⚠ Brak w Subiekcie",
                            ", ".join(sorted(brak_w_sub)[:8])
                            + (f"  (+{len(brak_w_sub) - 8})" if len(brak_w_sub) > 8 else ""),
                            wyroznij=True)
        if nadmiar:
            self._wiersz_kv(s, "⚠ Nadmiar w Subiekcie",
                            ", ".join(sorted(nadmiar)[:8])
                            + (f"  (+{len(nadmiar) - 8})" if len(nadmiar) > 8 else ""),
                            wyroznij=True)


def _bez_ogona(symbol):
    """Symbol bez koncowki typu (X/XX/Z/ZZ) — do porownania z Inventorem."""
    s = (symbol or "").strip().upper()
    for ogon in ("ZZ", "XX", "Z", "X"):
        if s.endswith(ogon):
            return s[:-len(ogon)]
    return s


def otworz(rodzic, nr, project_id=None, project_name=None):
    """Pokazuje pozycję w karcie. JEDNO okno na całą aplikację.

    Gdy karta już jest otwarta — przełącza ją na nową pozycję i podnosi,
    zamiast otwierać duplikat. Historia „Wstecz" jest wtedy zachowana, więc
    wejście z innego okna dokłada się do ścieżki nawigacji.
    """
    if not (nr or "").strip():
        return None
    global _OTWARTA
    karta = _OTWARTA
    if karta is not None:
        try:
            if not karta.winfo_exists():
                karta = _OTWARTA = None
        except tk.TclError:
            karta = _OTWARTA = None
    if karta is not None:
        try:
            # Inny projekt niz dotad — przestawiamy kontekst karty, zeby BOM
            # i struktura zlozen byly z wlasciwego projektu.
            if project_id is not None and project_id != karta.project_id:
                karta.project_id = project_id
                karta.project_name = project_name or (
                    nazwa_projektu_bezpiecznie(project_id))
                karta.kids, karta.nazwy = drzewo(karta.project_name)
            karta.deiconify()
            karta.lift()
            karta.focus_force()
            karta.pokaz(nr)
            return karta
        except tk.TclError:
            _OTWARTA = None         # okno padlo w miedzyczasie — tworzymy nowe
    try:
        return KartaPozycji(rodzic, nr, project_id, project_name)
    except Exception as e:
        messagebox.showerror("Karta pozycji", "Nie udało się otworzyć karty:\n" + str(e),
                             parent=rodzic)
        return None


def nazwa_projektu_bezpiecznie(project_id):
    try:
        from subiekt_stany import nazwa_projektu
        return nazwa_projektu(project_id)
    except Exception:
        return ""
