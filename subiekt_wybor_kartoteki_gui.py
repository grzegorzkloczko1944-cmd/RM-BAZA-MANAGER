# -*- coding: utf-8 -*-
"""
Okienko „Wstaw z Subiekta" — wybór kartoteki do formularza.

W odróżnieniu od okna „Dopasuj kartotekę Subiekta"
(`subiekt_dopasuj_wiersz_gui.py`) NIC NIE ZAPISUJE do bazy. Dostaje frazę
startową, oddaje wybraną kartotekę wołającemu i znika — decyzja, co z nią
zrobić, należy do formularza, który je otworzył.

Pierwszy użytkownik: „➕ Dodaj pozycję ręcznie" w RM_BAZA (zgłoszone
28.09.2026) — wpisywanie symbolu i nazwy z pamięci kończyło się kartoteką
„KFL001 / KFL001" albo literówką, której zasiew projektu już nie rozpozna.

⚠️ Szukamy po symbolu, nazwie I OPISIE — `subiekt_dopasowanie.Indeks.szukaj`
opisu nie rusza, a jego dwaj pozostali wołający liczą na dzisiejsze wyniki,
więc filtr jest tutaj, nie tam.
"""

import threading
import tkinter as tk
from tkinter import ttk

import subiekt_scalanie as S

try:
    from subiekt_stany import wysrodkuj
except ImportError:
    def wysrodkuj(okno, rodzic, *a, **k):
        pass

#: Ile wierszy pokazujemy. Katalog ma ~3500 kartotek — pełna lista nic nie
#: mówi, a Treeview przy każdym znaku przemalowuje wszystko i pisanie zacina.
LIMIT_WYNIKOW = 200


def szukaj_w_katalogu(katalog, fraza, ile=LIMIT_WYNIKOW):
    """Kartoteki, w których KAŻDY człon frazy siedzi w symbolu, nazwie lub opisie.

    Człony zamiast dosłownej frazy, bo „6004 2rs" ma trafić w „SS 6004 2RS"
    (ta sama pułapka co w `Indeks.szukaj`, 09.09.2026). Kolejność: najpierw
    trafienia w symbol (to identyfikator), potem w nazwę, na końcu te, które
    broni sam opis; w każdej grupie krótszy symbol pierwszy.
    """
    czlony = [c for c in (fraza or "").strip().upper().split() if c]
    if not czlony:
        return []

    w_symbolu, w_nazwie, w_opisie = [], [], []
    for poz in katalog or []:
        symbol = (poz.get("symbol") or "").upper()
        nazwa = (poz.get("nazwa") or "").upper()
        opis = (poz.get("opis") or "").upper()
        if not all(c in symbol + " " + nazwa + " " + opis for c in czlony):
            continue
        if all(c in symbol for c in czlony):
            w_symbolu.append(poz)
        elif all(c in symbol + " " + nazwa for c in czlony):
            w_nazwie.append(poz)
        else:
            w_opisie.append(poz)

    klucz = lambda p: len(p.get("symbol") or "")
    return (sorted(w_symbolu, key=klucz) + sorted(w_nazwie, key=klucz)
            + sorted(w_opisie, key=klucz))[:ile]


class WyborKartotekiWindow(tk.Toplevel):
    """Szukaj → zaznacz → `on_wybor(kartoteka)`. Bez zapisu do bazy."""

    def __init__(self, parent, on_wybor, fraza=""):
        super().__init__(parent)
        from subiekt_stany import ukryj_do_zbudowania
        ukryj_do_zbudowania(self)      # pokazane dopiero zbudowane
        self.title("🔍 Wstaw z Subiekta")
        self.on_wybor = on_wybor
        self.katalog = []
        self.wyniki = []
        self._zadanie_szukania = None

        self._buduj(fraza)
        wysrodkuj(self, parent, 1000, 520)

        self.transient(parent)
        self.grab_set()
        # F5 = katalog od nowa (kartoteka mogla powstac wprost w Subiekcie).
        # `bind`, nie `bind_all` — skroty F2-F6 glownego okna sa celowo
        # odfiltrowane w Toplevelach.
        self.bind("<F5>", self._na_f5)
        self.bind("<Escape>", lambda _e: (self.destroy(), "break")[1])

        self._wczytaj_katalog_async()

    # ── budowa okna ──────────────────────────────────────────────────────

    def _buduj(self, fraza):
        pasek = tk.Frame(self)
        pasek.pack(fill=tk.X, padx=10, pady=(10, 6))
        tk.Label(pasek, text="Szukaj (symbol, nazwa, opis):").pack(side=tk.LEFT)
        self.var_fraza = tk.StringVar(value=fraza or "")
        self.e_fraza = tk.Entry(pasek, textvariable=self.var_fraza)
        self.e_fraza.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))
        self.e_fraza.bind("<Return>", lambda _e: self._szukaj())
        # Strzalka w dol z pola szukania wchodzi w liste — bez tego trzeba
        # siegac po mysz, zeby wybrac cokolwiek poza pierwszym wierszem.
        self.e_fraza.bind("<Down>", self._w_liste)
        self.var_fraza.trace_add("write",
                                 lambda *_a: self._szukaj_z_opoznieniem())
        tk.Button(pasek, text="Szukaj", command=self._szukaj).pack(side=tk.LEFT)
        tk.Label(pasek, text="F5 = odśwież katalog", fg="#888").pack(
            side=tk.LEFT, padx=(10, 0))

        srodek = tk.Frame(self)
        srodek.pack(fill=tk.BOTH, expand=True, padx=10)

        # Te same kolumny co „Dopasuj kartoteke Subiekta": po symbolu
        # i nazwie nie da sie odroznic wariantow tej samej czesci.
        kol = ("symbol", "nazwa", "opis", "rodzaj", "stan", "cena")
        self.tabela = ttk.Treeview(srodek, columns=kol, show="headings",
                                   selectmode="browse", height=16)
        for k, tekst, szer in (("symbol", "Symbol", 150),
                               ("nazwa", "Nazwa", 240),
                               ("opis", "Opis", 240),
                               ("rodzaj", "Rodzaj", 80),
                               ("stan", "Stan", 70),
                               ("cena", "Cena netto", 90)):
            self.tabela.heading(k, text=tekst)
            self.tabela.column(k, width=szer,
                               anchor="e" if k in ("stan", "cena") else "w")
        self.tabela.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tabela.bind("<Double-1>", lambda _e: self._wybierz())
        self.tabela.bind("<Return>", lambda _e: self._wybierz())

        sb = ttk.Scrollbar(srodek, orient="vertical", command=self.tabela.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tabela.config(yscrollcommand=sb.set)

        stopka = tk.Frame(self)
        stopka.pack(fill=tk.X, padx=10, pady=10)
        self.lbl_status = tk.Label(stopka, text="", fg="#555", anchor="w")
        self.lbl_status.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(stopka, text="Zamknij", command=self.destroy).pack(
            side=tk.RIGHT, padx=(6, 0))
        self.btn_wstaw = tk.Button(stopka, text="✓ Wstaw do formularza",
                                   command=self._wybierz, bg="#d5f5e3",
                                   state=tk.DISABLED)
        self.btn_wstaw.pack(side=tk.RIGHT)

    # ── katalog ──────────────────────────────────────────────────────────

    def _wczytaj_katalog_async(self, max_wiek_h=None):
        """Katalog w wątku — pierwsze pobranie idzie do Subiekta i trwa."""
        self.lbl_status.config(text="Wczytuję katalog Subiekta…", fg="#555")

        def robota():
            try:
                if max_wiek_h is None:
                    katalog = S.wczytaj_katalog_subiekta()
                else:
                    katalog = S.wczytaj_katalog_subiekta(max_wiek_h=max_wiek_h)
                self.after(0, lambda: self._katalog_gotowy(katalog))
            except Exception as e:
                self.after(0, lambda: self._katalog_blad(e))

        threading.Thread(target=robota, daemon=True).start()

    def _katalog_gotowy(self, katalog):
        if not self.winfo_exists():
            return
        self.katalog = katalog or []
        self.lbl_status.config(text=f"Katalog: {len(self.katalog)} kartotek",
                               fg="#555")
        self._szukaj()
        self.e_fraza.focus_set()

    def _katalog_blad(self, e):
        if not self.winfo_exists():
            return
        self.lbl_status.config(text=f"⚠️ Katalog niedostępny: {e}", fg="#a33")

    def _na_f5(self, _event=None):
        self._wczytaj_katalog_async(max_wiek_h=0)
        return "break"

    # ── szukanie ─────────────────────────────────────────────────────────

    def _szukaj_z_opoznieniem(self, ms=180):
        """Przeliczenie po przerwie w pisaniu — inaczej pisanie się zacina."""
        if self._zadanie_szukania:
            try:
                self.after_cancel(self._zadanie_szukania)
            except Exception:
                pass
        self._zadanie_szukania = self.after(ms, self._szukaj)

    def _szukaj(self):
        self._zadanie_szukania = None
        if not self.katalog:
            return
        self.wyniki = szukaj_w_katalogu(self.katalog, self.var_fraza.get())
        self.tabela.delete(*self.tabela.get_children())
        for i, poz in enumerate(self.wyniki):
            self.tabela.insert(
                "", "end", iid=str(i),
                values=(poz.get("symbol") or "", poz.get("nazwa") or "",
                        poz.get("opis") or "", poz.get("rodzaj") or "",
                        self._stan_txt(poz.get("stan")),
                        self._cena_txt(poz.get("cena"))))

        if self.wyniki:
            self.tabela.selection_set("0")
            self.btn_wstaw.config(state=tk.NORMAL)
            ile = len(self.wyniki)
            self.lbl_status.config(
                text=(f"{ile} trafień"
                      + (f" (pokazuję pierwsze {LIMIT_WYNIKOW})"
                         if ile >= LIMIT_WYNIKOW else "")), fg="#555")
        else:
            self.btn_wstaw.config(state=tk.DISABLED)
            fraza = self.var_fraza.get().strip()
            self.lbl_status.config(
                text=("Wpisz fragment symbolu, nazwy albo opisu."
                      if not fraza else
                      "Brak trafień — popraw frazę (F5 odświeża katalog)."),
                fg="#555" if not fraza else "#a60")

    def _w_liste(self, _event=None):
        """Strzałka w dół z pola szukania → pierwszy wiersz listy."""
        if self.wyniki:
            self.tabela.focus_set()
            self.tabela.selection_set("0")
            self.tabela.focus("0")
        return "break"

    @staticmethod
    def _stan_txt(v):
        """Stan magazynowy: pusto gdy nieznany, liczba bez zbędnego ,0."""
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

    # ── wybór ────────────────────────────────────────────────────────────

    def _wybierz(self):
        sel = self.tabela.selection()
        if not sel:
            return
        try:
            poz = self.wyniki[int(sel[0])]
        except (ValueError, IndexError):
            return
        self.destroy()
        if self.on_wybor:
            self.on_wybor(poz)


def open_window(parent, on_wybor, fraza=""):
    """Punkt wejścia: `on_wybor(kartoteka)` dostaje wybraną pozycję katalogu."""
    return WyborKartotekiWindow(parent, on_wybor, fraza=fraza)
