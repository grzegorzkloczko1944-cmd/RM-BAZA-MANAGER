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

    #: Zakładki: (etykieta, stany do pokazania)
    ZAKLADKI = (
        ("Do decyzji", (D.STAN_NAZWA, D.STAN_NIEJEDNOZNACZNE)),
        ("Dopasowane", (D.STAN_ZAPAMIETANE, D.STAN_SYMBOL)),
        ("Brak kartoteki", (D.STAN_BRAK,)),
        ("Wszystkie", tuple(D.OPIS_STANU)),
    )

    def __init__(self, parent, project_id, project_name=None):
        super().__init__(parent)
        self.project_id = project_id
        self.project_name = project_name or str(project_id)
        self.title(f"Dopasowanie kartotek Subiekta — projekt {project_id}"
                   f" ({self.project_name})")
        self.geometry("1320x760")
        self.minsize(1000, 560)
        self.transient(parent)

        self.indeks = None
        self.pozycje = []
        self.decyzje = {}         # {kod: {symbol, id, nazwa}} — do zapisania
        self.zakladka = 0
        self._biezaca = None

        self._buduj()
        self.after(50, self._wczytaj_async)
        wysrodkuj(self, parent)

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
        kol = ("stan", "nazwa_rm", "nr", "ilosc", "symbol", "nazwa", "sposob")
        self.tab = ttk.Treeview(lewa, columns=kol, show="headings", height=20)
        for c, tekst, szer in (("stan", "", 34),
                               ("nazwa_rm", "Nazwa (RM_BAZA)", 230),
                               ("nr", "Nr rysunku", 110),
                               ("ilosc", "Ilość", 50),
                               ("symbol", "Symbol Subiekt", 140),
                               ("nazwa", "Nazwa Subiekt", 210),
                               ("sposob", "Sposób", 120)):
            self.tab.heading(c, text=tekst)
            self.tab.column(c, width=szer, anchor="w")
        for stan, (_opis, kolor) in D.OPIS_STANU.items():
            self.tab.tag_configure(stan, background=kolor)
        self.tab.tag_configure("decyzja", background="#d6eaf8")
        vs = ttk.Scrollbar(lewa, orient="vertical", command=self.tab.yview)
        self.tab.configure(yscrollcommand=vs.set)
        self.tab.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)
        self.tab.bind("<<TreeviewSelect>>", self._pokaz_kandydatow)
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
        kol2 = ("symbol", "nazwa")
        self.tab2 = ttk.Treeview(ramka2, columns=kol2, show="headings", height=14)
        self.tab2.heading("symbol", text="Symbol")
        self.tab2.column("symbol", width=170, anchor="w")
        self.tab2.heading("nazwa", text="Nazwa")
        self.tab2.column("nazwa", width=300, anchor="w")
        vs2 = ttk.Scrollbar(ramka2, orient="vertical", command=self.tab2.yview)
        self.tab2.configure(yscrollcommand=vs2.set)
        self.tab2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs2.pack(side=tk.RIGHT, fill=tk.Y)
        self.tab2.bind("<Double-1>", lambda _e: self._przypisz())
        panel.add(prawa, minsize=440)

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
            blad, indeks, pozycje, wiek = str(e), None, [], None
        self.after(0, lambda: self._wczytano(indeks, pozycje, wiek, blad))

    def _wczytano(self, indeks, pozycje, wiek, blad):
        if not self.winfo_exists():
            return
        if blad:
            self.lbl_licznik.config(text="błąd")
            messagebox.showerror("Dopasowanie", blad, parent=self)
            return
        self.indeks, self.pozycje = indeks, pozycje
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

    def _widoczne(self):
        stany = self.ZAKLADKI[self.zakladka][1]
        fraza = self.var_filtr.get().strip().upper()
        out = []
        for p in self.pozycje:
            if p["stan"] not in stany:
                continue
            if fraza and fraza not in (p["nazwa_rm"] + " " + p["kod"]).upper():
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
            self.tab.insert("", "end", iid=p["kod"], values=(
                znaki.get(p["stan"], ""),
                p["nazwa_rm"] or p["kod"],
                "" if p.get("bez_numeru") else p["kod"],
                p.get("ilosc") or "",
                wyb.get("symbol") or "—",
                (wyb.get("nazwa") or
                 (f"{len(p['kandydaci'])} kandydatów" if len(p["kandydaci"]) > 1
                  else "—")),
                sposob),
                tags=("decyzja",) if decyzja else (p["stan"],))
        for i, (etykieta, stany) in enumerate(self.ZAKLADKI):
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
        self._wypelnij(p["kandydaci"], "Kandydaci z katalogu")

    def _wypelnij(self, lista, tytul):
        self.lbl_kand.config(text=f"{tytul} ({len(lista or [])})")
        self.tab2.delete(*self.tab2.get_children())
        for poz in lista or []:
            self.tab2.insert("", "end",
                             iid=str(poz.get("id") or poz.get("symbol")),
                             values=(poz.get("symbol") or "",
                                     poz.get("nazwa") or ""))

    def _szukaj(self):
        if not self.indeks:
            return
        fraza = self.var_szukaj.get().strip()
        if not fraza:
            p = self._biezaca_pozycja()
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
        messagebox.showinfo("Zapisano", f"Zapisano {n} powiązań.", parent=self)
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
