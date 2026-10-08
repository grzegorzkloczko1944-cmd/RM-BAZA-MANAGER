"""Porządki w kartotekach — czerwone / żółte / zielone (menu SUBIEKT).

Jedno okno do sprzątania kartotek po audycie z makra MAG (08.10.2026):

  🔴 do usunięcia   — tabela `kartoteki_usun` (symbol + zamiennik),
  🟡 zastrzeżenia   — tabela `kartoteki_ocena`, ocena=zastrzezenia (+ powód),
  🟢 rekomendowane  — tabela `kartoteki_ocena`, ocena=rekomendowane.

Cztery rzeczy, które się tu robi:
  1. nadawanie i zdejmowanie kolorów — tymi samymi adresami HTTP, z których
     korzysta makro MAG (`/mag/usun/*`, `/mag/ocena/*`), więc Inventor i
     RM_BAZA widzą to samo bez żadnej synchronizacji;
  2. przeniesienie stanu z czerwonej kartoteki na jej zamiennik — JEDNO
     zbiorcze PW na zamienniki (ceny z kosztu FIFO starych kartotek), potem
     JEDNO zbiorcze RW ze starych. Dokładnie tak, jak zrobiono ręcznie
     06.10.2026 dla 8 łożysk; odwrotna kolejność dałaby ujemne warstwy;
  3. wiązanie: symbole dostawców ze starej kartoteki przepięte na zamiennik
     (w Subiekcie) i alias stary → zamiennik w mapowaniach RM;
  4. lista „do wyrzucenia w Subiekcie" — dezaktywacja kartoteki to kosz w GUI
     Subiekta, most tego nie umie, więc okno NICZEGO nie kasuje.

⚠️ Stany w tabeli pochodzą z KOPII Subiekta na serwerze (kopia MAG, sprzed
synchronizacji). Przed PW/RW okno pyta most o ŚWIEŻY stan (`stan`) — na kopii
nie wolno opierać dokumentów.

⚠️ Klasa materiału: `S …` / `SS …` na początku symbolu albo „nierdzew" w opisie
= nierdzewne. 06.10.2026 zwykła kartoteka dostała nierdzewny zamiennik i
skasowano niewłaściwą — stąd blokada pary zwykłe ↔ nierdzewne.
"""

import json
import os
import queue
import re
import threading
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from tkinter import messagebox, ttk

from rm_kreciolek import Kreciolek
from subiekt_stany import podepnij_szerokosci, wysrodkuj

try:
    from tksheet import Sheet
except ImportError:                      # pragma: no cover
    Sheet = None

GRANAT = "#34495e"
GRANAT_CIEMNY = "#2c3e50"
SZARY = "#ecf0f1"
TEKST = "#2c3e50"
TEKST_SZARY = "#7f8c8d"
ZIELONY = "#27ae60"
GRANAT_AKCJA = "#2980b9"
STAL = "#7f8c8d"
CZERWONY = "#c0392b"
FONT = ("Arial", 9)
FONT_S = ("Arial", 8)
FONT_B = ("Arial", 9, "bold")

#: Magazyn dla PW/RW — jawnie, bo most przy niezgodnym symbolu CICHO bierze
#: pierwszy magazyn z listy (Pw.cs). Ten sam co w produkcji własnej.
MAGAZYN = "MASTER"

#: Kolory: klucz → (znak, nazwa w tabeli, tło komórki, tekst komórki).
#: Czerwony = osobna tabela niż żółty/zielony; gdy kartoteka ma oba,
#: czerwony wygrywa (tak samo rysuje MAG).
KOLORY = {
    "czerwony": ("🔴", "do usunięcia", "#f5b7b1", "#7b241c"),
    "zolty": ("🟡", "zastrzeżenia", "#fdebd0", "#7d6608"),
    "zielony": ("🟢", "rekomendowana", "#d5f5e3", "#1e8449"),
}
OCENA_DLA_KOLORU = {"zolty": "zastrzezenia", "zielony": "rekomendowane"}
KOLOR_DLA_OCENY = {v: k for k, v in OCENA_DLA_KOLORU.items()}

KOLUMNY = [
    ("kolor", "Kolor", 110), ("symbol", "Symbol", 150), ("nazwa", "Nazwa", 220),
    ("opis", "Opis", 170), ("dostepne", "Stan (kopia MAG)", 95),
    ("zamiennik", "Zamiennik", 150), ("zam_dostepne", "Stan zamiennika", 95),
    ("uwaga", "Powód / uwaga", 200), ("kto", "Kto", 80), ("kiedy", "Kiedy", 115),
]
K_KOLOR, K_SYMBOL, K_ZAMIENNIK = 0, 1, 5

KOL_PRZENIES = [
    ("symbol", "Z kartoteki", 140), ("stan", "Stan świeży", 85),
    ("zamiennik", "Na zamiennik", 140), ("zam_stan", "Stan zamiennika", 95),
    ("koszt", "Koszt jedn. (FIFO)", 110), ("wartosc", "Wartość", 90),
    ("status", "Status", 300),
]


def _kto(app=None):
    """Kto oznacza — UŻYTKOWNIK RM_BAZA (np. ADMIN), nie login Windows.

    Login Windows na stacji to `mongo` niezależnie od tego, kto siedzi przy
    RM_BAZA; w kolumnie „Kto" lądowało przez to `MONGO-…` zamiast
    zalogowanego użytkownika (zgłoszone 08.10.2026). Login Windows zostaje
    tylko jako ostatnia deska, gdy okno otwarto bez RM_BAZA.
    """
    kto = (getattr(app, "current_user", None) or "").strip() if app is not None else ""
    return (kto or os.environ.get("USERNAME") or "?")[:40]


#: Jak POKAZAĆ „Kto" w tabelce — login stacji → użytkownik RM_BAZA.
#: Makro MAG podpisuje się `USERNAME@COMPUTERNAME` (np. `mongo@MONGO`), a
#: wpisy z 06.10.2026 mają `MONGO-claude`; przy RM_BAZA na tej stacji siedzi
#: ADMIN (prośba usera 08.10.2026). Zmienia TYLKO wyświetlanie — w bazie
#: zostaje to, co przysłało makro. Klucze małymi literami.
ALIASY_KTO = {
    "mongo": "ADMIN",
    "mongo@mongo": "ADMIN",
    "mongo-claude": "ADMIN",
}


def _pokaz_kto(kto):
    """Tekst do kolumny „Kto": alias z ALIASY_KTO albo to, co zapisano."""
    k = (kto or "").strip()
    return ALIASY_KTO.get(k.lower(), k)


def _teraz():
    return datetime.now().isoformat(timespec="seconds")


def _liczba(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def _ilosc(x):
    v = _liczba(x)
    return f"{v:g}"


# ── HTTP do serwera MAG (RM_SERWER :5061) ──────────────────────────────────
def _mag_url(sciezka, **q):
    import rm_klient
    from subiekt_kopia_zlecenia import PORT_MAG
    host = getattr(rm_klient, "_host", None) or rm_klient.DOMYSLNY_HOST
    url = "http://%s:%d%s" % (host, PORT_MAG, sciezka)
    q = {k: v for k, v in q.items() if v not in (None, "")}
    return url + ("?" + urllib.parse.urlencode(q) if q else "")


def _mag_odpowiedz(resp):
    surowe = resp.read()
    return json.loads(surowe.decode("utf-8")) if surowe else {}


def mag_get(sciezka, **q):
    """GET /mag/… → JSON. Błąd serwera ({"blad": …}) idzie jako RuntimeError."""
    try:
        with urllib.request.urlopen(_mag_url(sciezka, **q), timeout=30) as r:
            return _mag_odpowiedz(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(_blad_http(e)) from None


def mag_post(sciezka, linie, **q):
    """POST /mag/… — jeden symbol na linię (`symbol` albo `symbol|zamiennik`),
    każda część zakodowana jak w URL. Tak samo czyta to serwer od makra."""
    tresc = "\n".join(
        "|".join(urllib.parse.quote(cz, safe="") for cz in str(l).split("|"))
        for l in linie if str(l).strip())
    zad = urllib.request.Request(_mag_url(sciezka, **q), data=tresc.encode("ascii"),
                                 method="POST")
    try:
        with urllib.request.urlopen(zad, timeout=60) as r:
            return _mag_odpowiedz(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(_blad_http(e)) from None


def _blad_http(e):
    try:
        return json.loads(e.read().decode("utf-8")).get("blad") or f"HTTP {e.code}"
    except Exception:
        return f"HTTP {e.code}"


# ── klasa materiału ────────────────────────────────────────────────────────
_NIERDZEWNY = re.compile(r"^\s*S{1,2}\s*\d")


def klasa_materialu(symbol, opis=""):
    """'nierdzewne' / 'zwykle' — po symbolu (S/SS na początku) i opisie."""
    s = (symbol or "").strip().upper()
    if _NIERDZEWNY.match(s) or "NIERDZEW" in (opis or "").upper():
        return "nierdzewne"
    return "zwykle"


# ── okno ───────────────────────────────────────────────────────────────────
class OknoPorzadki(tk.Toplevel, Kreciolek):

    def __init__(self, parent):
        super().__init__(parent)
        from subiekt_stany import ukryj_do_zbudowania
        ukryj_do_zbudowania(self)
        self.parent_app = parent
        self.title("Porządki w kartotekach — do usunięcia · zastrzeżenia · rekomendowane")
        # Rozmiar po „przywróć w dół" (kwadracik Windows): ~3/4 ekranu. Okno
        # startuje zmaksymalizowane, a `wysrodkuj` bez rozmiaru czytało
        # wymiary JUŻ zmaksymalizowanego okna i zapisywało je jako zwykły
        # rozmiar — po zmniejszeniu okno odpinało się od krawędzi, ale
        # zostawało wielkości całego ekranu (zgłoszone 08.10.2026).
        self._rozmiar_zwykly = (max(1100, int(self.winfo_screenwidth() * 0.75)),
                                max(640, int(self.winfo_screenheight() * 0.75)))
        self.geometry("%dx%d" % self._rozmiar_zwykly)
        self.minsize(1100, 640)
        try:
            self.state("zoomed")
        except Exception:
            pass

        self._wiersze = []          # wszystkie oznaczone kartoteki (dict per wiersz)
        self._widoczne = []         # po filtrze — wiersz i-ty arkusza = _widoczne[i]
        self._katalog = []          # [{"id","symbol","nazwa",…}] z cache
        self._kat_po_symbolu = {}
        self._kandydaci = []
        self._plan_przeniesienia = None   # wynik „Sprawdź" — zużywany przez „Wykonaj"
        self._wyniki = queue.Queue()
        self.filtr_koloru = None

        self._buduj()
        self._pompuj()
        self._start_tla()
        wysrodkuj(self, parent, *self._rozmiar_zwykly)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ── budowa ──────────────────────────────────────────────────────────
    def _buduj(self):
        top = tk.Frame(self, bg=GRANAT, height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🚦 Porządki w kartotekach — czerwone · żółte · zielone",
                 bg=GRANAT, fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)
        self.lbl_most = tk.Label(top, text="most: sprawdzam…", bg=GRANAT, fg="#f5b041",
                                 font=("Arial", 9, "bold"))
        self.lbl_most.pack(side=tk.LEFT, padx=10)

        def akcja(tekst, cmd, kolor):
            tk.Button(top, text=tekst, command=cmd, bg=kolor, fg="white", font=FONT_S,
                      padx=8, pady=2, relief=tk.RAISED, bd=1, cursor="hand2",
                      activebackground=kolor, activeforeground="white"
                      ).pack(side=tk.RIGHT, padx=(0, 8), pady=6)
        akcja("↻ Odśwież", self._odswiez, STAL)
        akcja("☁ Synchronizuj kopię MAG", self._synchronizuj_mag, GRANAT_AKCJA)

        # Legenda JEST filtrem: klik w kolor pokazuje tylko ten kolor, drugi
        # klik (albo „Wszystkie") wraca do całości. Osobne liczniki-filtry po
        # prawej dublowały legendę (zgłoszone 08.10.2026).
        leg = tk.Frame(self, bg=SZARY)
        leg.pack(side=tk.TOP, fill=tk.X)
        tk.Label(leg, text="Pokaż:", bg=SZARY, fg=TEKST_SZARY, font=FONT_S).pack(
            side=tk.LEFT, padx=(12, 4), pady=4)
        self._chipy = {}
        for k in ("czerwony", "zolty", "zielony", None):
            if k is None:
                tekst, tlo, fg = "Wszystkie", "white", TEKST
            else:
                znak, nazwa, tlo, fg = KOLORY[k]
                tekst = f"{znak} {nazwa}"
            l = tk.Label(leg, text=f"{tekst}: –", bg=tlo, fg=fg, font=FONT_S, padx=8, pady=2,
                         cursor="hand2", relief=tk.FLAT, bd=2)
            l.pack(side=tk.LEFT, padx=3)
            l.bind("<Button-1>", lambda _e, kk=k: self._filtruj(kk))
            l._rm_tekst = tekst
            self._chipy[k] = l
        tk.Label(leg, text="Stany w tabeli z kopii MAG — przed PW/RW okno pyta Subiekt o świeże.",
                 bg=SZARY, fg=TEKST_SZARY, font=FONT_S).pack(side=tk.LEFT, padx=16)

        # filtr
        f = tk.Frame(self, bg=SZARY)
        f.pack(side=tk.TOP, fill=tk.X)
        tk.Label(f, text="Szukaj:", bg=SZARY, font=FONT).pack(side=tk.LEFT, padx=(12, 3), pady=6)
        self.var_szukaj = tk.StringVar()
        e = tk.Entry(f, textvariable=self.var_szukaj, font=FONT, width=28, relief=tk.SOLID, bd=1)
        e.pack(side=tk.LEFT)
        e.bind("<KeyRelease>", lambda _e: self._wypelnij_tabele())
        self.var_ze_stanem = tk.BooleanVar(value=False)
        tk.Checkbutton(f, text="tylko ze stanem", variable=self.var_ze_stanem, bg=SZARY,
                       font=FONT_S, command=self._wypelnij_tabele).pack(side=tk.LEFT, padx=10)

        # tabela + panel dolny
        srodek = tk.PanedWindow(self, orient=tk.VERTICAL, sashwidth=6, bg=SZARY)
        srodek.pack(fill=tk.BOTH, expand=True)
        ramka_tab = tk.Frame(srodek, bg="white")
        # Tabela bierze CAŁY nadmiar wysokości (stretch="always"), panel
        # zakładek na dole ma stałą wysokość i siedzi przy dolnej krawędzi.
        # Wcześniej PanedWindow dzielił miejsce po równo i panel zasłaniał
        # ~2/3 okna (zgłoszone 08.10.2026). Belkę nadal można przeciągnąć.
        srodek.add(ramka_tab, minsize=220, stretch="always")
        if Sheet is None:
            tk.Label(ramka_tab, text="Brak biblioteki tksheet", fg=CZERWONY).pack(pady=20)
            self.sheet = None
        else:
            self.sheet = Sheet(ramka_tab, headers=[k[1] for k in KOLUMNY],
                               column_width=120, theme="light blue")
            self.sheet.set_options(show_selected_cells_border=True,
                                   empty_horizontal=0, empty_vertical=0)
            self.sheet.hide("row_index")
            self.sheet.enable_bindings(("single_select", "drag_select", "ctrl_select",
                                        "select_all", "row_select", "column_width_resize",
                                        "arrowkeys", "right_click_popup_menu", "rc_select",
                                        "copy"))
            podepnij_szerokosci(self, self.sheet, "porzadki_kartotek", [k[2] for k in KOLUMNY])
            self.sheet.bind("<ButtonRelease-1>", self._po_zaznaczeniu, add="+")
            self.sheet.pack(fill=tk.BOTH, expand=True)

        dol = tk.Frame(srodek, bg="white")
        srodek.add(dol, minsize=200, height=290, stretch="never")
        self._srodek, self._dol = srodek, dol
        # Belkę ustawiamy jeszcze raz po pokazaniu okna: przy budowie okno jest
        # niezmapowane i PanedWindow nie zna swojej wysokości.
        srodek.bind("<Configure>", self._belka_na_dol, add="+")
        self._belka_ustawiona = False
        self.nb = ttk.Notebook(dol)
        self.nb.pack(fill=tk.BOTH, expand=True)
        self._zakladka_kolor()
        self._zakladka_przeniesienie()
        self._zakladka_wiazanie()

        self.status = tk.Label(self, text="", bg=GRANAT, fg=SZARY, font=FONT_S, anchor="w",
                               padx=10, pady=3)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    def _belka_na_dol(self, e):
        """Jednorazowo: panel zakładek 290 px od dołu, reszta dla tabeli.

        Tylko przy pierwszym sensownym rozmiarze — potem belka należy do
        użytkownika (przeciągnięta ręcznie ma zostać tam, gdzie ją puścił).
        """
        if self._belka_ustawiona or e.height < 600:
            return
        self._belka_ustawiona = True
        try:
            self._srodek.sash_place(0, 0, e.height - 290)
        except tk.TclError:
            pass

    # ── zakładka 1: kolor ───────────────────────────────────────────────
    def _zakladka_kolor(self):
        z = tk.Frame(self.nb, bg="white")
        self.nb.add(z, text="  Kolor  ")
        lewa = tk.Frame(z, bg="white")
        lewa.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=6)
        tk.Label(lewa, text="Symbole (po jednym w wierszu; zaznaczenie w tabeli wypełnia samo, "
                            "można dopisać ręcznie):", bg="white", font=FONT_S, fg=TEKST_SZARY,
                 anchor="w").pack(fill=tk.X)
        self.txt_symbole = tk.Text(lewa, height=7, font=("Consolas", 10), relief=tk.SOLID, bd=1)
        self.txt_symbole.pack(fill=tk.BOTH, expand=True, pady=(2, 4))

        prawa = tk.Frame(z, bg="white")
        prawa.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=6)
        tk.Label(prawa, text="Jaki kolor?", bg="white", font=FONT_B).grid(row=0, column=0, sticky="w")
        self.var_kolor = tk.StringVar(value="czerwony")
        for i, k in enumerate(("czerwony", "zolty", "zielony")):
            znak, nazwa, tlo, fg = KOLORY[k]
            tk.Radiobutton(prawa, text=f"{znak} {nazwa}", variable=self.var_kolor, value=k,
                           bg="white", font=FONT, command=self._zmiana_koloru
                           ).grid(row=1 + i, column=0, sticky="w")
        tk.Label(prawa, text="Zamiennik (dla czerwonych):", bg="white", font=FONT_S,
                 fg=TEKST_SZARY).grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.var_zamiennik = tk.StringVar()
        self.ent_zamiennik = tk.Entry(prawa, textvariable=self.var_zamiennik, font=FONT,
                                      width=34, relief=tk.SOLID, bd=1)
        self.ent_zamiennik.grid(row=5, column=0, sticky="ew")
        self.ent_zamiennik.bind("<KeyRelease>", lambda _e: self._szukaj_w_katalogu())
        self.lb_kandydaci = tk.Listbox(prawa, height=5, font=FONT_S, activestyle="none",
                                       relief=tk.SOLID, bd=1, width=48)
        self.lb_kandydaci.grid(row=6, column=0, sticky="ew", pady=(2, 0))
        self.lb_kandydaci.bind("<<ListboxSelect>>", self._wybrano_kandydata)
        self.lb_kandydaci.bind("<Double-1>", self._wybrano_kandydata)
        tk.Label(prawa, text="Powód (dla żółtych, do 200 znaków):", bg="white", font=FONT_S,
                 fg=TEKST_SZARY).grid(row=7, column=0, sticky="w", pady=(8, 0))
        self.var_uwaga = tk.StringVar()
        self.ent_uwaga = tk.Entry(prawa, textvariable=self.var_uwaga, font=FONT, width=34,
                                  relief=tk.SOLID, bd=1)
        self.ent_uwaga.grid(row=8, column=0, sticky="ew")

        przyciski = tk.Frame(prawa, bg="white")
        przyciski.grid(row=9, column=0, sticky="ew", pady=(10, 0))
        self.btn_nadaj = tk.Button(przyciski, text="🎨 Nadaj kolor", command=self._nadaj_kolor,
                                   bg=GRANAT_AKCJA, fg="white", font=FONT_B, padx=10, pady=4,
                                   relief=tk.RAISED, bd=1, cursor="hand2")
        self.btn_nadaj.pack(side=tk.LEFT)
        self.btn_zdejmij = tk.Button(przyciski, text="✕ Zdejmij kolor", command=self._zdejmij_kolor,
                                     bg=STAL, fg="white", font=FONT_B, padx=10, pady=4,
                                     relief=tk.RAISED, bd=1, cursor="hand2")
        self.btn_zdejmij.pack(side=tk.LEFT, padx=(8, 0))
        self._zmiana_koloru()

    def _zmiana_koloru(self):
        k = self.var_kolor.get()
        self.ent_zamiennik.config(state=tk.NORMAL if k == "czerwony" else tk.DISABLED)
        self.lb_kandydaci.config(state=tk.NORMAL if k == "czerwony" else tk.DISABLED)
        self.ent_uwaga.config(state=tk.NORMAL if k == "zolty" else tk.DISABLED)

    # ── zakładka 2: przeniesienie stanu ────────────────────────────────
    def _zakladka_przeniesienie(self):
        z = tk.Frame(self.nb, bg="white")
        self.nb.add(z, text="  Przeniesienie stanu (PW → RW)  ")
        gora = tk.Frame(z, bg="white")
        gora.pack(fill=tk.X, padx=10, pady=(6, 2))
        tk.Label(gora, text="Zaznacz w tabeli czerwone kartoteki Z ZAMIENNIKIEM. Okno pyta Subiekt "
                            "o świeży stan, liczy koszt FIFO (suchy RW), potem wystawia JEDNO PW na "
                            "zamienniki i JEDNO RW ze starych.",
                 bg="white", font=FONT_S, fg=TEKST_SZARY, anchor="w", justify="left"
                 ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_sprawdz = tk.Button(gora, text="1. Sprawdź (suchy przebieg)",
                                     command=self._sprawdz_przeniesienie, bg=GRANAT_AKCJA,
                                     fg="white", font=FONT_B, padx=10, pady=4, relief=tk.RAISED,
                                     bd=1, cursor="hand2")
        self.btn_sprawdz.pack(side=tk.RIGHT, padx=(6, 0))
        self.btn_wykonaj = tk.Button(gora, text="2. Wykonaj PW → RW", command=self._wykonaj_przeniesienie,
                                     bg=CZERWONY, fg="white", font=FONT_B, padx=10, pady=4,
                                     relief=tk.RAISED, bd=1, cursor="hand2", state=tk.DISABLED)
        self.btn_wykonaj.pack(side=tk.RIGHT, padx=(6, 0))
        self.lbl_przen = tk.Label(z, text="", bg="white", font=FONT_S, fg=TEKST, anchor="w",
                                  justify="left", wraplength=1300)
        self.lbl_przen.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 6))
        if Sheet is None:
            self.sheet_przen = None
            return
        self.sheet_przen = Sheet(z, headers=[k[1] for k in KOL_PRZENIES], height=170,
                                 theme="light blue")
        self.sheet_przen.set_options(show_selected_cells_border=True, empty_horizontal=0,
                                     empty_vertical=0)
        self.sheet_przen.hide("row_index")
        self.sheet_przen.hide("top_left")
        self.sheet_przen.enable_bindings(("single_select", "column_width_resize", "copy"))
        for i, (_k, _n, szer) in enumerate(KOL_PRZENIES):
            self.sheet_przen.column_width(i, szer)
        self.sheet_przen.pack(fill=tk.BOTH, expand=True, padx=10, pady=(2, 2))

    # ── zakładka 3: wiązanie ───────────────────────────────────────────
    def _zakladka_wiazanie(self):
        z = tk.Frame(self.nb, bg="white")
        self.nb.add(z, text="  Wiązanie z kartotekami Subiekta  ")
        gora = tk.Frame(z, bg="white")
        gora.pack(fill=tk.X, padx=10, pady=(6, 2))
        tk.Label(gora, text="Dla zaznaczonych czerwonych z zamiennikiem: symbole dostawców ze starej "
                            "kartoteki przepinane na zamiennik (w Subiekcie, jak w oknie KSeF) i alias "
                            "stary → zamiennik w mapowaniach RM (BOM-y rozpoznają stary kod).",
                 bg="white", font=FONT_S, fg=TEKST_SZARY, anchor="w", justify="left"
                 ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_wiaz_pokaz = tk.Button(gora, text="Pokaż, co zostanie powiązane",
                                        command=self._pokaz_wiazanie, bg=GRANAT_AKCJA, fg="white",
                                        font=FONT_B, padx=10, pady=4, relief=tk.RAISED, bd=1,
                                        cursor="hand2")
        self.btn_wiaz_pokaz.pack(side=tk.RIGHT, padx=(6, 0))
        self.btn_wiaz = tk.Button(gora, text="Powiąż", command=self._wykonaj_wiazanie,
                                  bg=ZIELONY, fg="white", font=FONT_B, padx=10, pady=4,
                                  relief=tk.RAISED, bd=1, cursor="hand2", state=tk.DISABLED)
        self.btn_wiaz.pack(side=tk.RIGHT, padx=(6, 0))
        self.txt_wiaz = tk.Text(z, font=("Consolas", 9), relief=tk.FLAT, bg="#fbfcfc", wrap="word",
                                padx=10, pady=6, state=tk.DISABLED)
        self.txt_wiaz.pack(fill=tk.BOTH, expand=True, padx=10, pady=(2, 6))
        self._plan_wiazania = None

    # ── wątki ──────────────────────────────────────────────────────────
    def _pompuj(self):
        try:
            while True:
                potem, wynik, blad = self._wyniki.get_nowait()
                potem(wynik, blad)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._pompuj)

    def _w_tle(self, praca, potem):
        def run():
            try:
                w, b = praca(), None
            except Exception as e:      # noqa: BLE001 — pokazujemy userowi
                w, b = None, e
            self._wyniki.put((potem, w, b))
        threading.Thread(target=run, daemon=True).start()

    def _start_tla(self):
        self.start_kreciolek("Czytam oznaczone kartoteki z serwera")
        self._w_tle(self._wczytaj_praca, self._wczytaj_gotowe)

        def most():
            import subiekt_bridge
            subiekt_bridge.zapewnij_most()
            return True

        def most_gotowy(w, blad):
            if blad or not w:
                self.lbl_most.config(text="⚠ most niedostępny — tylko kolory, bez PW/RW", fg="#f5b041")
                return
            self.lbl_most.config(text="most: ONLINE", fg="#a9dfbf")
            # Katalog do podpowiedzi zamiennika: z cache natychmiast, a gdy
            # cache pusty/stary — przez most w tle (~9 s), żeby lista nie
            # była pusta na stacji bez pliku `subiekt_katalog.json`.
            if not self._katalog:
                def katalog():
                    import subiekt_scalanie
                    return subiekt_scalanie.wczytaj_katalog_subiekta() or []

                def katalog_gotowy(k, b):
                    if b or not k:
                        return
                    self._katalog = k
                    self._kat_po_symbolu = {(x.get("symbol") or "").strip().upper(): x for x in k}
                    self._wypelnij_tabele()
                    self.status.config(text=f"{self.status.cget('text')}   katalog Subiekta: {len(k)}")
                self._w_tle(katalog, katalog_gotowy)
        self._w_tle(most, most_gotowy)

    # ── odczyt listy ───────────────────────────────────────────────────
    def _wczytaj_praca(self):
        """Cztery GET-y hurtem (nie per wiersz) + katalog z cache."""
        czerw = mag_get("/mag/szukaj", typ="!", limit=500)
        zolte = mag_get("/mag/szukaj", typ="!z", limit=500)
        ziel = mag_get("/mag/szukaj", typ="!r", limit=500)
        usun = {u.get("symbol", "").strip().upper(): u for u in mag_get("/mag/do_usuniecia")}
        oceny = {o.get("symbol", "").strip().upper(): o for o in mag_get("/mag/oceny")}
        wiersze, widziane = [], set()

        def dodaj(k, kolor):
            sym = (k.get("symbol") or "").strip()
            if not sym or sym.upper() in widziane:
                return                   # czerwony wygrywa z oceną (jak w MAG)
            widziane.add(sym.upper())
            u = usun.get(sym.upper(), {})
            o = oceny.get(sym.upper(), {})
            wiersze.append({
                "id": k.get("id"), "symbol": sym, "nazwa": k.get("nazwa") or "",
                "opis": k.get("opis") or "", "dostepne": _liczba(k.get("dostepne")),
                "kolor": kolor,
                "zamiennik": (k.get("zamiennik") or u.get("zamiennik") or "").strip(),
                "zam_dostepne": u.get("zamiennik_dostepne"),
                "uwaga": (k.get("ocena_uwaga") or o.get("uwaga") or "") if kolor != "czerwony" else "",
                "kto": u.get("kto") if kolor == "czerwony" else (k.get("ocena_kto") or o.get("kto") or ""),
                "kiedy": u.get("kiedy") if kolor == "czerwony" else (k.get("ocena_kiedy") or o.get("kiedy") or ""),
            })
        for k in czerw:
            dodaj(k, "czerwony")
        for k in zolte:
            dodaj(k, "zolty")
        for k in ziel:
            dodaj(k, "zielony")
        wiersze.sort(key=lambda w: (("czerwony", "zolty", "zielony").index(w["kolor"]), w["symbol"].upper()))
        try:
            import subiekt_scalanie
            katalog = subiekt_scalanie.wczytaj_katalog_subiekta(tylko_cache=True) or []
        except Exception:
            katalog = []
        return wiersze, katalog

    def _wczytaj_gotowe(self, w, blad):
        self.stop_kreciolek()
        if blad:
            self.status.config(text=f"Nie udało się odczytać listy z serwera MAG: {blad}")
            messagebox.showerror("Porządki", f"Serwer MAG (RM_SERWER :5061) nie odpowiedział:\n\n{blad}",
                                 parent=self)
            return
        self._wiersze, self._katalog = w
        self._kat_po_symbolu = {(k.get("symbol") or "").strip().upper(): k for k in self._katalog}
        self._wypelnij_tabele()
        self.status.config(text=f"Oznaczonych kartotek: {len(self._wiersze)}   "
                                f"(katalog Subiekta z cache: {len(self._katalog)})")

    def _odswiez(self):
        self.start_kreciolek("Odświeżam listę")
        self._plan_przeniesienia = None
        self.btn_wykonaj.config(state=tk.DISABLED)
        self._w_tle(self._wczytaj_praca, self._wczytaj_gotowe)

    def _synchronizuj_mag(self):
        """Zlecenie odświeżenia kopii Subiekta na serwerze — wykona stacja z mostem."""
        def praca():
            return mag_post("/mag/synchronizuj", [], kto=_kto(self.parent_app))

        def potem(w, blad):
            if blad:
                messagebox.showwarning("Synchronizacja", f"Nie udało się zlecić synchronizacji:\n{blad}",
                                       parent=self)
            else:
                self.status.config(text=f"Synchronizacja kopii MAG zlecona: {(w or {}).get('komunikat') or w}")
        self._w_tle(praca, potem)

    # ── tabela ─────────────────────────────────────────────────────────
    def _filtruj(self, kolor):
        # Drugi klik w aktywny kolor wraca do wszystkich; „Wszystkie" zawsze czyści.
        self.filtr_koloru = None if (kolor is None or kolor == self.filtr_koloru) else kolor
        self._wypelnij_tabele()

    def _wypelnij_tabele(self):
        if self.sheet is None:
            return
        szuk = self.var_szukaj.get().strip().lower()
        ze_stanem = self.var_ze_stanem.get()
        self._widoczne = []
        for w in self._wiersze:
            if self.filtr_koloru and w["kolor"] != self.filtr_koloru:
                continue
            if ze_stanem and w["dostepne"] <= 0:
                continue
            if szuk and szuk not in f"{w['symbol']} {w['nazwa']} {w['opis']} {w['zamiennik']}".lower():
                continue
            self._widoczne.append(w)
        dane = []
        for w in self._widoczne:
            znak, nazwa, _t, _f = KOLORY[w["kolor"]]
            dane.append([f"{znak} {nazwa}", w["symbol"], w["nazwa"], w["opis"], _ilosc(w["dostepne"]),
                         w["zamiennik"], "" if w["zam_dostepne"] is None else _ilosc(w["zam_dostepne"]),
                         w["uwaga"], _pokaz_kto(w["kto"]), (w["kiedy"] or "")[:16].replace("T", " ")])
        try:
            self.sheet.dehighlight_all()
        except Exception:
            pass
        self.sheet.set_sheet_data(dane, reset_col_positions=False, redraw=False)
        for i, w in enumerate(self._widoczne):
            _z, _n, tlo, fg = KOLORY[w["kolor"]]
            self.sheet.highlight_cells(row=i, column=K_KOLOR, bg=tlo, fg=fg)
            if w["kolor"] == "czerwony" and w["zamiennik"]:
                zam = self._kat_po_symbolu.get(w["zamiennik"].upper(), {})
                if klasa_materialu(w["symbol"], w["opis"]) != klasa_materialu(
                        w["zamiennik"], zam.get("opis") or ""):
                    # zwykłe ↔ nierdzewne — błąd z 06.10.2026, nie powtarzać
                    self.sheet.highlight_cells(row=i, column=K_ZAMIENNIK, bg="#f1948a", fg="#641e16")
        self.sheet.redraw()
        liczby = {k: sum(1 for w in self._wiersze if w["kolor"] == k) for k in KOLORY}
        # Aktywny filtr: ramka i pogrubienie — tło zostaje kolorem legendy,
        # żeby dalej było widać, który to kolor.
        for klucz, l in self._chipy.items():
            n = len(self._wiersze) if klucz is None else liczby[klucz]
            wl = (klucz == self.filtr_koloru)
            l.config(text=f"{l._rm_tekst}: {n}", relief=tk.SOLID if wl else tk.FLAT,
                     font=FONT_B if wl else FONT_S)

    def _zaznaczone(self):
        """Wiersze (dict) zaznaczone w tabeli — przez `_widoczne`, nie `_wiersze`."""
        if self.sheet is None:
            return []
        try:
            idx = sorted(set(self.sheet.get_selected_rows(get_cells_as_rows=True)))
        except Exception:
            idx = []
        return [self._widoczne[i] for i in idx if i < len(self._widoczne)]

    def _po_zaznaczeniu(self, _e=None):
        zaz = self._zaznaczone()
        self.txt_symbole.delete("1.0", tk.END)
        self.txt_symbole.insert("1.0", "\n".join(w["symbol"] for w in zaz))
        if len(zaz) == 1:
            w = zaz[0]
            self.var_kolor.set(w["kolor"])
            self.var_zamiennik.set(w["zamiennik"])
            self.var_uwaga.set(w["uwaga"])
            self._zmiana_koloru()
        self.status.config(text=f"Zaznaczono: {len(zaz)}")

    # ── zakładka kolor: akcje ──────────────────────────────────────────
    def _symbole_z_pola(self):
        return [l.strip() for l in self.txt_symbole.get("1.0", tk.END).splitlines() if l.strip()]

    def _szukaj_w_katalogu(self):
        fraza = self.var_zamiennik.get().strip().lower()
        self.lb_kandydaci.delete(0, tk.END)
        self._kandydaci = []
        if len(fraza) < 2:
            return
        norm = re.sub(r"[^a-z0-9]", "", fraza)
        for k in self._katalog:
            sym = (k.get("symbol") or "")
            naz = (k.get("nazwa") or "")
            if fraza in sym.lower() or fraza in naz.lower() or (
                    norm and norm == re.sub(r"[^a-z0-9]", "", sym.lower())):
                self._kandydaci.append(k)
                self.lb_kandydaci.insert(tk.END, f"{sym}   —   {naz}")
                if len(self._kandydaci) >= 40:
                    break

    def _wybrano_kandydata(self, _e=None):
        sel = self.lb_kandydaci.curselection()
        if sel and sel[0] < len(self._kandydaci):
            self.var_zamiennik.set(self._kandydaci[sel[0]].get("symbol") or "")

    def _nadaj_kolor(self):
        symbole = self._symbole_z_pola()
        if not symbole:
            messagebox.showinfo("Kolor", "Zaznacz kartoteki w tabeli albo wpisz symbole.", parent=self)
            return
        kolor = self.var_kolor.get()
        zam = self.var_zamiennik.get().strip()
        uwaga = self.var_uwaga.get().strip()[:200]
        if kolor == "czerwony" and zam:
            zle = []
            for s in symbole:
                if s.strip().upper() == zam.upper():
                    zle.append(f"{s}: zamiennik to ta sama kartoteka")
                    continue
                kz = self._kat_po_symbolu.get(zam.upper(), {})
                ks = self._kat_po_symbolu.get(s.upper(), {})
                if kz and klasa_materialu(s, ks.get("opis") or "") != klasa_materialu(zam, kz.get("opis") or ""):
                    zle.append(f"{s} → {zam}: zwykłe ↔ nierdzewne (S/SS)")
            if zle and not messagebox.askyesno(
                    "Zamiennik — wątpliwości",
                    "Sprawdź pary:\n\n" + "\n".join(zle[:15]) + "\n\nOznaczyć mimo to?",
                    icon="warning", default="no", parent=self):
                return
        znak, nazwa, _t, _f = KOLORY[kolor]
        if not messagebox.askyesno("Nadaj kolor",
                                   f"{znak} {nazwa} dla {len(symbole)} kartotek"
                                   + (f"\nzamiennik: {zam}" if kolor == "czerwony" and zam else "")
                                   + (f"\npowód: {uwaga}" if kolor == "zolty" and uwaga else "")
                                   + "\n\nZapisać na serwerze (widoczne też w MAG)?", parent=self):
            return

        def praca():
            raport = []
            if kolor == "czerwony":
                linie = [f"{s}|{zam}" if zam else s for s in symbole]
                w = mag_post("/mag/usun/oznacz", linie, kto=_kto(self.parent_app))
                raport.append(w)
                # Czerwony wygrywa w widoku, ale ocena w drugiej tabeli by została —
                # zdejmujemy, żeby kartoteka miała JEDEN kolor.
                raport.append(mag_post("/mag/ocena/odznacz", symbole, kto=_kto(self.parent_app)))
            else:
                w = mag_post("/mag/ocena/oznacz", symbole, ocena=OCENA_DLA_KOLORU[kolor],
                             kto=_kto(self.parent_app), uwaga=uwaga if kolor == "zolty" else "")
                raport.append(w)
                raport.append(mag_post("/mag/usun/odznacz", symbole, kto=_kto(self.parent_app)))
            return raport

        def potem(w, blad):
            self.stop_kreciolek()
            if blad:
                messagebox.showerror("Kolor", f"Serwer odmówił:\n{blad}", parent=self)
                return
            glowny = w[0] if w else {}
            linie = [f"Oznaczono: {glowny.get('oznaczono', 0)}"]
            if glowny.get("nie_znaleziono"):
                linie.append("Nie ma w kopii Subiekta: " + ", ".join(glowny["nie_znaleziono"][:20]))
            if glowny.get("zly_zamiennik"):
                linie.append("Zły zamiennik: " + "; ".join(glowny["zly_zamiennik"][:20]))
            messagebox.showinfo("Kolor", "\n".join(linie), parent=self)
            self._odswiez()
        self.start_kreciolek("Zapisuję kolory na serwerze")
        self._w_tle(praca, potem)

    def _zdejmij_kolor(self):
        symbole = self._symbole_z_pola()
        if not symbole:
            messagebox.showinfo("Kolor", "Zaznacz kartoteki w tabeli albo wpisz symbole.", parent=self)
            return
        if not messagebox.askyesno("Zdejmij kolor",
                                   f"Zdjąć WSZYSTKIE znaczniki (czerwony/żółty/zielony) z {len(symbole)} kartotek?",
                                   parent=self):
            return

        def praca():
            a = mag_post("/mag/usun/odznacz", symbole, kto=_kto(self.parent_app))
            b = mag_post("/mag/ocena/odznacz", symbole, kto=_kto(self.parent_app))
            return a, b

        def potem(w, blad):
            self.stop_kreciolek()
            if blad:
                messagebox.showerror("Kolor", f"Serwer odmówił:\n{blad}", parent=self)
                return
            a, b = w
            messagebox.showinfo("Kolor", f"Zdjęto: czerwonych {a.get('odznaczono', 0)}, "
                                         f"ocen {b.get('odznaczono', 0)}", parent=self)
            self._odswiez()
        self.start_kreciolek("Zdejmuję kolory")
        self._w_tle(praca, potem)

    # ── zakładka przeniesienie: suchy przebieg ─────────────────────────
    def _pary_do_przeniesienia(self):
        """Zaznaczone czerwone z zamiennikiem; reszta zaznaczenia pomijana z komunikatem."""
        zaz = self._zaznaczone()
        pary, pominiete = [], []
        for w in zaz:
            if w["kolor"] != "czerwony":
                pominiete.append(f"{w['symbol']}: nie jest czerwona")
            elif not w["zamiennik"]:
                pominiete.append(f"{w['symbol']}: brak zamiennika")
            else:
                pary.append(w)
        return pary, pominiete

    def _sprawdz_przeniesienie(self):
        pary, pominiete = self._pary_do_przeniesienia()
        if not pary:
            messagebox.showinfo("Przeniesienie",
                                "Zaznacz w tabeli czerwone kartoteki z zamiennikiem."
                                + ("\n\nPominięte:\n" + "\n".join(pominiete[:10]) if pominiete else ""),
                                parent=self)
            return
        self.nb.select(1)
        self._plan_przeniesienia = None
        self.btn_wykonaj.config(state=tk.DISABLED)
        self.btn_sprawdz.config(state=tk.DISABLED)
        self.start_kreciolek("Pytam Subiekt o świeże stany i koszt FIFO")

        def praca():
            import subiekt_bridge
            import subiekt_produkcja
            from subiekt_zamowienia import zloz_uwagi
            subiekt_bridge.zapewnij_most()
            symbole = sorted({w["symbol"] for w in pary} | {w["zamiennik"] for w in pary})
            # JEDNO pytanie o stan wszystkich symboli (stare + zamienniki).
            st = subiekt_bridge.call("stan", {"symbols": symbole}, timeout=180) or {}
            stany = {}
            for p in st.get("pozycje", []):
                sym = (p.get("Symbol") or p.get("Pytany") or "").strip().upper()
                mag = next((m for m in (p.get("Magazyny") or []) if (m.get("Magazyn") or "").upper() == MAGAZYN), None)
                stany[sym] = {
                    "istnieje": bool(p.get("Istnieje", True)) and p.get("Dopasowanie") != "brak",
                    "dostepne": _liczba((mag or p).get("Dostepne")),
                    "opis": p.get("Opis") or "", "nazwa": p.get("Nazwa") or "",
                    "id": p.get("Id"),
                }
            wiersze = []
            for w in pary:
                s, z = w["symbol"], w["zamiennik"]
                ss, sz = stany.get(s.upper(), {}), stany.get(z.upper(), {})
                r = {"symbol": s, "zamiennik": z, "stan": ss.get("dostepne", 0.0),
                     "zam_stan": sz.get("dostepne", 0.0), "koszt": None, "status": "", "ok": False,
                     "id": ss.get("id"), "zam_id": sz.get("id")}
                if not ss.get("istnieje"):
                    r["status"] = "stara kartoteka nie istnieje w Subiekcie"
                elif not sz.get("istnieje"):
                    r["status"] = "zamiennika nie ma w Subiekcie"
                elif klasa_materialu(s, ss.get("opis")) != klasa_materialu(z, sz.get("opis")):
                    r["status"] = "BLOKADA: zwykłe ↔ nierdzewne (S/SS) — popraw zamiennik"
                elif r["stan"] <= 0:
                    r["status"] = "stan 0 — nie ma czego przenosić"
                else:
                    r["ok"] = True
                wiersze.append(r)
            do_rw = [r for r in wiersze if r["ok"]]
            if do_rw:
                # Suchy RW daje KosztJedn (FIFO) — to będzie cena na PW zamiennika.
                plan_rw = {"pozycje": [{"symbol": r["symbol"], "ilosc": r["stan"]} for r in do_rw],
                           "uwagi": zloz_uwagi("", "PORZĄDKI: stan przeniesiony na zamienniki"),
                           "magazyn": MAGAZYN}
                wyn = subiekt_produkcja.wyslij_rw(plan_rw, zapisz=False)
                kroki = {(k.get("Symbol") or "").strip().upper(): k for k in (wyn or {}).get("kroki", [])}
                for r in do_rw:
                    k = kroki.get(r["symbol"].upper(), {})
                    if k.get("Status") == "blad":
                        r["ok"], r["status"] = False, f"RW: {k.get('Szczegoly') or 'błąd'}"
                        continue
                    r["koszt"] = round(_liczba(k.get("KosztJedn")), 2)
                    r["status"] = "do przeniesienia" + (" (bez wyceny — PW po 0 zł)" if r["koszt"] == 0 else "")
                do_pw = [r for r in do_rw if r["ok"]]
                if do_pw:
                    plan_pw = {"pozycje": [{"symbol": r["zamiennik"], "ilosc": r["stan"], "cena": r["koszt"] or 0}
                                           for r in do_pw],
                               "uwagi": zloz_uwagi("", "PORZĄDKI: przyjęcie stanu z kartotek do usunięcia: "
                                                   + ", ".join(f"{r['symbol']}→{r['zamiennik']}" for r in do_pw)),
                               "magazyn": MAGAZYN}
                    wyn = subiekt_produkcja.wyslij_pw(plan_pw, zapisz=False)
                    kroki = {(k.get("Symbol") or "").strip().upper(): k for k in (wyn or {}).get("kroki", [])}
                    for r in do_pw:
                        k = kroki.get(r["zamiennik"].upper(), {})
                        if k.get("Status") == "blad":
                            r["ok"], r["status"] = False, f"PW: {k.get('Szczegoly') or 'błąd'}"
            return wiersze

        def potem(w, blad):
            self.stop_kreciolek()
            self.btn_sprawdz.config(state=tk.NORMAL)
            if blad:
                messagebox.showerror("Przeniesienie", f"Suchy przebieg nie przeszedł:\n{blad}", parent=self)
                return
            self._plan_przeniesienia = w
            self._pokaz_plan_przeniesienia(w)
            gotowe = [r for r in w if r["ok"]]
            self.btn_wykonaj.config(state=tk.NORMAL if gotowe else tk.DISABLED)
            tekst = (f"Do przeniesienia: {len(gotowe)} z {len(w)}. "
                     + ("Pominięte w zaznaczeniu: " + "; ".join(pominiete) + ". " if pominiete else "")
                     + ("Kliknij „2. Wykonaj” — powstanie JEDNO PW i JEDNO RW." if gotowe else ""))
            self.lbl_przen.config(text=tekst)
        self._w_tle(praca, potem)

    def _pokaz_plan_przeniesienia(self, wiersze, numery=None):
        if self.sheet_przen is None:
            return
        dane = []
        for r in wiersze:
            wart = (r["koszt"] or 0) * r["stan"] if r["koszt"] is not None else 0
            dane.append([r["symbol"], _ilosc(r["stan"]), r["zamiennik"], _ilosc(r["zam_stan"]),
                         "" if r["koszt"] is None else f"{r['koszt']:.2f}",
                         f"{wart:.2f}" if r["koszt"] is not None else "", r["status"]])
        try:
            self.sheet_przen.dehighlight_all()
        except Exception:
            pass
        self.sheet_przen.set_sheet_data(dane, reset_col_positions=False, redraw=False)
        for i, r in enumerate(wiersze):
            tlo, fg = ("#d5f5e3", "#1e8449") if r["ok"] else ("#fadbd8", "#7b241c")
            self.sheet_przen.highlight_cells(row=i, column=6, bg=tlo, fg=fg)
        self.sheet_przen.redraw()

    # ── zakładka przeniesienie: zapis ──────────────────────────────────
    def _wykonaj_przeniesienie(self):
        plan = [r for r in (self._plan_przeniesienia or []) if r["ok"]]
        if not plan:
            return
        suma = sum((r["koszt"] or 0) * r["stan"] for r in plan)
        if not messagebox.askyesno(
                "Wykonaj PW → RW",
                f"Powstaną DWA dokumenty w Subiekcie (magazyn {MAGAZYN}):\n\n"
                f"  PW — {len(plan)} poz. na zamienniki, wartość {suma:.2f} zł\n"
                f"  RW — {len(plan)} poz. ze starych kartotek\n\n"
                + "\n".join(f"  {r['symbol']}  {_ilosc(r['stan'])} szt.  →  {r['zamiennik']}" for r in plan[:20])
                + ("\n  …" if len(plan) > 20 else "")
                + "\n\nDokumentów magazynowych nie cofa się jednym kliknięciem. Wystawić?",
                icon="warning", default="no", parent=self):
            return
        self.btn_wykonaj.config(state=tk.DISABLED)
        self.btn_sprawdz.config(state=tk.DISABLED)
        self.start_kreciolek("Wystawiam PW na zamienniki")

        def praca():
            import subiekt_produkcja
            from subiekt_zamowienia import zloz_uwagi
            wynik = {"pw": None, "rw": None, "uwagi": []}
            plan_pw = {"pozycje": [{"symbol": r["zamiennik"], "ilosc": r["stan"], "cena": r["koszt"] or 0}
                                   for r in plan],
                       "uwagi": zloz_uwagi("", "PORZĄDKI: przyjęcie stanu z kartotek do usunięcia: "
                                           + ", ".join(f"{r['symbol']}→{r['zamiennik']}" for r in plan)),
                       "magazyn": MAGAZYN}
            w_pw = subiekt_produkcja.wyslij_pw(plan_pw, zapisz=True)
            ok, numer_pw, uw = subiekt_produkcja.sprawdz_pw(w_pw, plan_pw)
            wynik["pw"] = numer_pw
            wynik["uwagi"] += uw
            if not ok:
                # PW nie potwierdzone read-backiem — RW NIE wystawiamy. Bez ponawiania:
                # drugie PW to drugie przyjęcie.
                wynik["przerwano"] = "PW nie potwierdzone — RW nie wystawiono"
                return wynik
            self.tekst_kreciolka("Wystawiam RW ze starych kartotek")
            plan_rw = {"pozycje": [{"symbol": r["symbol"], "ilosc": r["stan"]} for r in plan],
                       "uwagi": zloz_uwagi("", f"PORZĄDKI: stan przeniesiony na zamienniki\nPW: {numer_pw}"),
                       "magazyn": MAGAZYN}
            w_rw = subiekt_produkcja.wyslij_rw(plan_rw, zapisz=True)
            ok, numer_rw, uw = subiekt_produkcja.sprawdz_rw(w_rw, plan_rw, numer_pw)
            wynik["rw"] = numer_rw
            wynik["uwagi"] += uw
            if not ok:
                wynik["przerwano"] = f"RW nie potwierdzone — PW {numer_pw} JUŻ ISTNIEJE, sprawdź w Subiekcie"
                return wynik
            try:
                mag_post("/mag/synchronizuj", [], kto=_kto(self.parent_app))
            except Exception as e:      # noqa: BLE001 — kopia MAG to nie dokument
                wynik["uwagi"].append(f"Kopia MAG nie zlecona do odświeżenia: {e}")
            return wynik

        def potem(w, blad):
            self.stop_kreciolek()
            self.btn_sprawdz.config(state=tk.NORMAL)
            if blad:
                messagebox.showerror(
                    "Przeniesienie",
                    f"Błąd w trakcie zapisu:\n{blad}\n\n⚠️ Sprawdź w Subiekcie, czy nie powstało PW — "
                    "nie ponawiaj bez sprawdzenia (drugie PW = drugie przyjęcie).", parent=self)
                return
            linie = [f"PW: {w.get('pw') or '—'}", f"RW: {w.get('rw') or '—'}"]
            if w.get("przerwano"):
                linie.append(f"\n⚠️ {w['przerwano']}")
            if w.get("uwagi"):
                linie.append("\n" + "\n".join(w["uwagi"][:12]))
            if w.get("rw") and not w.get("przerwano"):
                linie.append("\nStan przeniesiony. Stare kartoteki do WYRZUCENIA w Subiekcie (kosz — ręcznie):\n  "
                             + "\n  ".join(r["symbol"] for r in plan))
                for r in plan:
                    r["status"] = f"przeniesiono: {w['pw']} / {w['rw']}"
                self._pokaz_plan_przeniesienia(plan)
            messagebox.showinfo("Przeniesienie", "\n".join(linie), parent=self)
            self._plan_przeniesienia = None
            self._odswiez()
        self._w_tle(praca, potem)

    # ── zakładka wiązanie ──────────────────────────────────────────────
    def _pokaz_wiazanie(self):
        pary, pominiete = self._pary_do_przeniesienia()
        if not pary:
            messagebox.showinfo("Wiązanie", "Zaznacz czerwone kartoteki z zamiennikiem."
                                + ("\n\nPominięte:\n" + "\n".join(pominiete[:10]) if pominiete else ""),
                                parent=self)
            return
        self.nb.select(2)
        self._plan_wiazania = None
        self.btn_wiaz.config(state=tk.DISABLED)
        self.start_kreciolek("Czytam powiązania symboli dostawców")

        def praca():
            import subiekt_bridge
            subiekt_bridge.zapewnij_most()
            odp = subiekt_bridge.call("symbole-dostawcy", {}, timeout=120) or {}
            pow = odp.get("powiazania", [])
            po_symbolu = {}
            for p in pow:
                po_symbolu.setdefault((p.get("Symbol") or "").strip().upper(), []).append(p)
            plan = {"dostawcy": [], "aliasy": {}, "opis": []}
            for w in pary:
                s, z = w["symbol"], w["zamiennik"]
                kz = self._kat_po_symbolu.get(z.upper(), {})
                zam_id = kz.get("id")
                plan["aliasy"][s] = (w["id"], z, zam_id)
                juz = {((p.get("Nip") or ""), (p.get("SymbolDostawcy") or "").upper())
                       for p in po_symbolu.get(z.upper(), [])}
                for p in po_symbolu.get(s.upper(), []):
                    klucz = ((p.get("Nip") or ""), (p.get("SymbolDostawcy") or "").upper())
                    if klucz in juz:
                        plan["opis"].append(f"  {s} → {z}: {p.get('Podmiot')} „{p.get('SymbolDostawcy')}” — zamiennik już ma")
                        continue
                    plan["dostawcy"].append({
                        "nip": p.get("Nip") or "", "symbolDostawcy": (p.get("SymbolDostawcy") or "")[:64],
                        "symbol": z, "asortymentId": zam_id,
                        "nazwaUDostawcy": (p.get("NazwaUDostawcy") or "")[:64]})
                    plan["opis"].append(f"  {s} → {z}: {p.get('Podmiot')} „{p.get('SymbolDostawcy')}” — do przepięcia")
                if not po_symbolu.get(s.upper()):
                    plan["opis"].append(f"  {s}: brak symboli dostawców w Subiekcie")
            return plan

        def potem(w, blad):
            self.stop_kreciolek()
            if blad:
                messagebox.showerror("Wiązanie", f"Nie udało się odczytać powiązań:\n{blad}", parent=self)
                return
            self._plan_wiazania = w
            tekst = ["SYMBOLE DOSTAWCÓW (zapis w Subiekcie):"] + (w["opis"] or ["  —"])
            tekst += ["", "ALIASY W MAPOWANIACH RM (stary symbol → zamiennik):"]
            tekst += [f"  {s} → {z}" + ("" if zid else "   (zamiennika nie ma w cache katalogu — alias bez Id)")
                      for s, (_i, z, zid) in w["aliasy"].items()]
            self._ustaw_tekst(self.txt_wiaz, "\n".join(tekst))
            self.btn_wiaz.config(state=tk.NORMAL)
        self._w_tle(praca, potem)

    def _wykonaj_wiazanie(self):
        plan = self._plan_wiazania
        if not plan:
            return
        if not messagebox.askyesno("Powiąż",
                                   f"Symboli dostawców do przepięcia: {len(plan['dostawcy'])}\n"
                                   f"Aliasów w mapowaniach RM: {len(plan['aliasy'])}\n\nZapisać?",
                                   parent=self):
            return
        self.btn_wiaz.config(state=tk.DISABLED)
        self.start_kreciolek("Zapisuję powiązania")

        def praca():
            raport = []
            if plan["dostawcy"]:
                import subiekt_bridge
                odp = subiekt_bridge.call("symbole-dostawcy",
                                          {"plan": {"powiazania": plan["dostawcy"]}, "zapisz": True},
                                          timeout=120, write=True) or {}
                for k in odp.get("kroki", []):
                    raport.append(f"Subiekt: „{k.get('SymbolDostawcy')}” → {k.get('Symbol')}: "
                                  f"{k.get('Status')} {k.get('Szczegoly') or ''}".rstrip())
            import subiekt_mapowania
            for s, (sid, z, zid) in plan["aliasy"].items():
                n = subiekt_mapowania.zapisz_scalenie(z, zid, {s: sid})
                raport.append(f"Mapowania RM: alias {s} → {z} (przepiętych mapowań BOM: {n})")
            return raport

        def potem(w, blad):
            self.stop_kreciolek()
            if blad:
                messagebox.showerror("Wiązanie", f"Zapis nie przeszedł:\n{blad}", parent=self)
                self.btn_wiaz.config(state=tk.NORMAL)
                return
            self._ustaw_tekst(self.txt_wiaz, "\n".join(w or ["—"]))
            self._plan_wiazania = None
        self._w_tle(praca, potem)

    def _ustaw_tekst(self, widget, tekst):
        widget.config(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", tekst)
        widget.config(state=tk.DISABLED)


def open_window(parent):
    return OknoPorzadki(parent)
