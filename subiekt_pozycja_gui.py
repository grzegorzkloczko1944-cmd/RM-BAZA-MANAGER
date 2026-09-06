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
        self.pokaz(nr, zapamietaj=False)

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
        self.wnetrze.bind("<Configure>",
                          lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._okno_canvas, width=e.width))
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#d6dbdf", fg=TEKST, font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    def _sekcja(self, tytul, podtytul=""):
        ramka = tk.Frame(self.wnetrze, bg=TLO_SEKCJI, highlightthickness=1,
                         highlightbackground=OBRAMOWANIE)
        ramka.pack(fill=tk.X, padx=12, pady=(10, 0))
        naglowek = tk.Frame(ramka, bg=TLO_SEKCJI)
        naglowek.pack(fill=tk.X, padx=12, pady=(8, 4))
        tk.Label(naglowek, text=tytul, bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 10, "bold")).pack(side=tk.LEFT)
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

    def wstecz(self):
        if self.historia:
            self.pokaz(self.historia.pop(), zapamietaj=False)

    # ── treść ───────────────────────────────────────────────────────────────
    def _wypelnij(self, nr):
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
            s = self._sekcja("Należy do", "ścieżka od korzenia złożenia — klik przenosi")
            for glebokosc, wezel in enumerate(droga):
                self._link(s, wezel, self.nazwy.get(wezel, ""), wciecie=glebokosc * 3)
            tk.Label(s, text=" " * (len(droga) * 3) + f"└ {nr}   ← ta pozycja",
                     bg=TLO_SEKCJI, fg=TEKST, font=("Consolas", 9, "bold"),
                     anchor="w").pack(fill=tk.X, pady=(1, 0))
        elif self.kids and nr_up not in self.kids:
            s = self._sekcja("Należy do")
            tk.Label(s, text="poza strukturą złożeń Inventora (np. normalia — łożyska, paski)",
                     bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 9),
                     anchor="w").pack(fill=tk.X)
        elif not self.kids:
            s = self._sekcja("Należy do")
            tk.Label(s, text="brak struktury — nie znaleziono arkusza „DRZEWKO TEKST” (*_OUT.xlsx)",
                     bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 9),
                     anchor="w").pack(fill=tk.X)

        # ── zawiera ──
        if skladniki:
            s = self._sekcja("Zawiera", f"{len(skladniki)} składników — klik przenosi")
            for dziecko, qty in skladniki:
                d = dziecko.strip().upper()
                ile = f"× {qty:g}" if isinstance(qty, (int, float)) else f"× {qty}"
                self._link(s, d, f"{self.nazwy.get(d, '')}    {ile}")

        # ── RM_BAZA ──
        s = self._sekcja("RM_BAZA", "dane z arkusza projektu")
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
        self.sekcja_subiekt = self._sekcja("Subiekt", "kartoteka i stany — z mostu")
        self.lbl_subiekt = tk.Label(self.sekcja_subiekt, text="",
                                    bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 9), anchor="w")
        self.lbl_subiekt.pack(fill=tk.X)
        self.lbl_projekty.config(text="Projekty: szukam…")
        threading.Thread(target=self._projekty_worker, args=(nr, self._subiekt_watek + 1),
                         daemon=True).start()
        self.start_kreciolek("Pytam Subiekta o " + nr)
        self._subiekt_watek += 1
        threading.Thread(target=self._subiekt_worker, args=(nr, self._subiekt_watek),
                         daemon=True).start()

    def _projekty_worker(self, nr, numer_watku):
        lista = projekty_z_pozycja(nr)
        self.after(0, lambda: self._projekty_gotowe(numer_watku, lista))

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
        try:
            import subiekt_bridge as most
            odp = most.wywolaj("stan", symbole=[nr], timeout=120)
            poz = (odp or {}).get("pozycje") or []
            dane = poz[0] if poz else {}
            blad = None
        except Exception as e:
            dane, blad = {}, str(e)
        self.after(0, lambda: self._subiekt_gotowe(nr, numer_watku, dane, blad))

    def _subiekt_gotowe(self, nr, numer_watku, dane, blad):
        # Użytkownik mógł już przejść dalej — odpowiedź na starą pozycję
        # nie może nadpisać sekcji nowej.
        if numer_watku != self._subiekt_watek:
            return
        self.stop_kreciolek("")
        try:
            self.lbl_subiekt.destroy()
        except tk.TclError:
            return                      # okno zamknięte w trakcie
        s = self.sekcja_subiekt
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
        # Wszystko, czego nie wypisaliśmy jawnie — żeby żadne pole z mostu
        # nie przepadło, gdy dojdzie nowe.
        znane = {"Pytany", "Symbol", "Istnieje", "Nazwa", "Rodzaj", "Dostepne",
                 "Zadysponowane", "OstatniaCenaZakupu", "DataOstatniegoZakupu",
                 "Magazyny", "Dopasowanie"}
        for k, v in dane.items():
            if k not in znane and v not in (None, "", [], {}):
                self._wiersz_kv(s, k, v)


def otworz(rodzic, nr, project_id=None, project_name=None):
    """Otwiera kartę pozycji. Bez numeru — nic."""
    if not (nr or "").strip():
        return None
    try:
        return KartaPozycji(rodzic, nr, project_id, project_name)
    except Exception as e:
        messagebox.showerror("Karta pozycji", f"Nie udało się otworzyć karty:\n{e}", parent=rodzic)
        return None
