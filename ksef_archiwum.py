"""
Archiwum faktur KSeF — trwałe składowanie oryginalnych XML-i na dysku
plus indeks SQLite, żeby dało się je przeszukiwać bez otwierania plików.

Dlaczego osobno od istniejącego menu „Sprawdź nowe faktury KSEF (API)":
tamten przepływ jest IMPORTEM CEN — wymaga wybranego projektu i po każdej
fakturze otwiera okno decyzji per pozycja. Archiwum ma inny cel: ściągnąć
wszystko, co przyszło, i to trzymać — niezależnie od tego, czy ktoś akurat
pracuje nad projektem i czy pozycje da się dopasować.

Dlaczego XML, a nie wydruk z Subiekta: Subiekt nexo nie trzyma oryginałów
na dysku — po imporcie przepisuje treść do własnego modelu w bazie SQL.
Z jego biblioteki załączników da się wyciągnąć najwyżej PDF, czyli obraz
tego, co Subiekt sam zmapował. XML z KSeF ma pełną treść źródłową.

Układ na dysku (obok master.sqlite, katalog faktury_ksef/):
    faktury_ksef/
        archiwum.sqlite              indeks
        2026/
            9721002583_RVQ-04895-26__9721002583-20260901-3E25ED800001-6E.xml
        nierozpoznane/               (współdzielone z istniejącym flow importu cen)

Nazwa pliku niesie NIP sprzedawcy, numer faktury i numer KSeF — nawet po
utracie indeksu archiwum da się odtworzyć przez ponowne przeskanowanie
plików (odbuduj_indeks).

Deduplikacja idzie po numerze KSeF, który jest globalnie unikalny.
"""

import re
import sqlite3
import threading
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import ttk, messagebox

from ksef_invoice_parser import parse_ksef_invoice_xml

SCHEMA = """
CREATE TABLE IF NOT EXISTS faktury (
    ksef_number     TEXT PRIMARY KEY,
    numer_faktury   TEXT,
    sprzedawca_nip  TEXT,
    sprzedawca      TEXT,
    data_wystawienia TEXT,
    wartosc_netto   REAL,
    pozycji         INTEGER,
    plik            TEXT,
    pobrano         TEXT
);
CREATE TABLE IF NOT EXISTS pozycje (
    ksef_number     TEXT,
    nr_wiersza      INTEGER,
    nazwa           TEXT,
    jednostka       TEXT,
    ilosc           REAL,
    cena_netto      REAL,
    wartosc_netto   REAL,
    PRIMARY KEY (ksef_number, nr_wiersza)
);
CREATE INDEX IF NOT EXISTS idx_poz_nazwa ON pozycje(nazwa);
CREATE INDEX IF NOT EXISTS idx_fakt_nip  ON faktury(sprzedawca_nip);
CREATE INDEX IF NOT EXISTS idx_fakt_data ON faktury(data_wystawienia);
"""


_OGONKI = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def uprosc(s):
    """Małe litery bez ogonków — nikt nie wpisuje „cięte" w wyszukiwarce."""
    return (s or "").translate(_OGONKI).lower()


def _zl(x):
    """Kwota po polsku: spacja co tysiąc, przecinek dziesiętny."""
    return f"{(x or 0):,.2f}".replace(",", " ").replace(".", ",")


def _bezpieczna_nazwa(s, maks=40):
    """Fragment nazwy pliku — bez znaków, których Windows nie przyjmie."""
    s = re.sub(r"[^A-Za-z0-9_\-]+", "-", (s or "").strip())
    return s.strip("-")[:maks]


class ArchiwumKsef:
    """Indeks + pliki. Bez GUI — da się użyć ze skryptu."""

    def __init__(self, katalog):
        self.katalog = Path(katalog)
        self.katalog.mkdir(parents=True, exist_ok=True)
        self.db_path = self.katalog / "archiwum.sqlite"
        self.con = sqlite3.connect(str(self.db_path), check_same_thread=False)
        # Wbudowane LOWER() w SQLite działa tylko na ASCII — „Cięte" zostałoby
        # „cIęte". Dodatkowo ściągamy ogonki, żeby „ciete" też trafiało.
        self.con.create_function("LOWER_PL", 1, uprosc)
        self.con.executescript(SCHEMA)
        self.con.commit()

    def zamknij(self):
        try:
            self.con.close()
        except Exception:
            pass

    # ── zapis ──────────────────────────────────────────────────────────────
    def zna(self, ksef_number):
        cur = self.con.execute("SELECT 1 FROM faktury WHERE ksef_number=?", (ksef_number,))
        return cur.fetchone() is not None

    def znane_numery(self):
        """Numery KSeF już w archiwum — także te z plików, których nie ma w indeksie."""
        numery = {r[0] for r in self.con.execute("SELECT ksef_number FROM faktury")}
        for plik in self.katalog.rglob("*.xml"):
            # nazwa: <nip>_<numer>__<ksef_number>.xml, ale starszy flow importu
            # cen zapisuje <ksef_number>__<sprzedawca>.xml — obsłuż oba
            trzon = plik.stem
            if "__" in trzon:
                lewo, prawo = trzon.split("__", 1)
                numery.add(prawo)
                numery.add(lewo)
        return numery

    def sciezka_dla(self, faktura, ksef_number):
        rok = (faktura.data_wystawienia or "")[:4] or "bez-daty"
        katalog = self.katalog / rok
        katalog.mkdir(parents=True, exist_ok=True)
        nip = _bezpieczna_nazwa(faktura.sprzedawca_nip, 15) or "brak-nip"
        numer = _bezpieczna_nazwa(faktura.numer_faktury, 30) or "bez-numeru"
        return katalog / f"{nip}_{numer}__{_bezpieczna_nazwa(ksef_number, 60)}.xml"

    def dodaj(self, xml_bytes, ksef_number):
        """
        Zapisuje XML na dysk i indeksuje. Zwraca (Path, KsefInvoice).
        Rzuca ValueError, gdy XML nie jest fakturą — plik i tak zostaje
        zapisany w nierozpoznane/, żeby nic nie przepadło.
        """
        tymczasowy = self.katalog / "nierozpoznane"
        tymczasowy.mkdir(parents=True, exist_ok=True)
        tmp_path = tymczasowy / f"{_bezpieczna_nazwa(ksef_number, 60)}.xml"
        tmp_path.write_bytes(xml_bytes)

        faktura = parse_ksef_invoice_xml(tmp_path)   # ValueError leci wyżej

        docelowy = self.sciezka_dla(faktura, ksef_number)
        tmp_path.replace(docelowy)
        self._zaindeksuj(faktura, ksef_number, docelowy)
        return docelowy, faktura

    def _zaindeksuj(self, faktura, ksef_number, plik):
        wartosc = sum(p.wartosc_netto or 0 for p in faktura.pozycje)
        self.con.execute(
            "INSERT OR REPLACE INTO faktury VALUES (?,?,?,?,?,?,?,?,?)",
            (ksef_number, faktura.numer_faktury, faktura.sprzedawca_nip,
             faktura.sprzedawca_nazwa, faktura.data_wystawienia, wartosc,
             len(faktura.pozycje), str(plik), datetime.now().isoformat(timespec="seconds")))
        self.con.execute("DELETE FROM pozycje WHERE ksef_number=?", (ksef_number,))
        self.con.executemany(
            "INSERT OR REPLACE INTO pozycje VALUES (?,?,?,?,?,?,?)",
            [(ksef_number, p.nr_wiersza, p.nazwa, p.jednostka,
              p.ilosc, p.cena_netto, p.wartosc_netto) for p in faktura.pozycje])
        self.con.commit()

    def odbuduj_indeks(self):
        """
        Przechodzi wszystkie XML-e w katalogu i odtwarza indeks. Numer KSeF
        bierze z nazwy pliku (oba warianty nazewnictwa). Zwraca (ok, bledy).
        """
        ok, bledy = 0, []
        for plik in sorted(self.katalog.rglob("*.xml")):
            trzon = plik.stem
            if "__" in trzon:
                lewo, prawo = trzon.split("__", 1)
                # w nowym układzie numer KSeF jest po "__", w starym przed
                ksef_number = prawo if re.match(r"^\d{10}-\d{8}-", prawo) else lewo
            else:
                ksef_number = trzon
            try:
                faktura = parse_ksef_invoice_xml(plik)
                self._zaindeksuj(faktura, ksef_number, plik)
                ok += 1
            except Exception as e:
                bledy.append((plik.name, str(e)))
        return ok, bledy

    # ── odczyt ─────────────────────────────────────────────────────────────
    def faktury(self, szukaj="", nip="", od="", do=""):
        sql = ["SELECT ksef_number, data_wystawienia, numer_faktury, sprzedawca,"
               " sprzedawca_nip, pozycji, wartosc_netto, plik FROM faktury WHERE 1=1"]
        par = []
        if nip:
            sql.append("AND sprzedawca_nip=?"); par.append(nip)
        if od:
            sql.append("AND data_wystawienia>=?"); par.append(od)
        if do:
            sql.append("AND data_wystawienia<=?"); par.append(do)
        if szukaj:
            # Szukamy też w pozycjach — użytkownik pamięta towar, nie numer faktury.
            # LOWER() z SQLite nie zna polskich znaków (LIKE '%cie%' nie złapie
            # „Cięte"), więc małe litery robimy w Pythonie po obu stronach.
            sql.append("AND (LOWER_PL(numer_faktury) LIKE ? OR LOWER_PL(sprzedawca) LIKE ?"
                       " OR sprzedawca_nip LIKE ?"
                       " OR ksef_number IN (SELECT ksef_number FROM pozycje"
                       "                    WHERE LOWER_PL(nazwa) LIKE ?))")
            wzor = f"%{uprosc(szukaj)}%"
            par += [wzor, wzor, f"%{szukaj}%", wzor]
        sql.append("ORDER BY data_wystawienia DESC, numer_faktury DESC")
        return self.con.execute(" ".join(sql), par).fetchall()

    def pozycje(self, ksef_number):
        return self.con.execute(
            "SELECT nr_wiersza, nazwa, jednostka, ilosc, cena_netto, wartosc_netto"
            " FROM pozycje WHERE ksef_number=? ORDER BY nr_wiersza", (ksef_number,)).fetchall()

    def dostawcy(self):
        return self.con.execute(
            "SELECT DISTINCT sprzedawca_nip, sprzedawca FROM faktury"
            " WHERE sprzedawca_nip<>'' ORDER BY sprzedawca").fetchall()

    def podsumowanie(self):
        r = self.con.execute(
            "SELECT COUNT(*), COALESCE(SUM(wartosc_netto),0), MIN(data_wystawienia),"
            " MAX(data_wystawienia) FROM faktury").fetchone()
        poz = self.con.execute("SELECT COUNT(*) FROM pozycje").fetchone()[0]
        return {"faktur": r[0], "wartosc": r[1], "od": r[2] or "",
                "do": r[3] or "", "pozycji": poz}


def pobierz_nowe(archiwum, nip, token, srodowisko="test", dni=30, postep=None):
    """
    Dociąga z KSeF faktury, których jeszcze nie ma w archiwum.
    Zwraca (nowe: list[(ksef_number, Path)], pominiete: int, bledy: list).

    Przyrostowo: pyta o zakres dat, ale zapisuje tylko nieznane numery KSeF —
    dzięki temu powtórne uruchomienie na zachodzącym zakresie nic nie psuje.
    """
    import ksef_api_client as api

    base_url = api.BASE_URL_PRODUCTION if srodowisko == "production" else api.BASE_URL_TEST
    if postep:
        postep("Uwierzytelnianie w KSeF…")
    sesja = api.authenticate_with_token(nip, token, base_url=base_url)

    nowe, bledy = [], []
    pominiete = 0
    try:
        do_dnia = datetime.now().strftime("%Y-%m-%d")
        od_dnia = (datetime.now() - timedelta(days=dni)).strftime("%Y-%m-%d")

        if postep:
            postep(f"Pobieranie listy faktur {od_dnia} … {do_dnia}")
        meta = []
        offset = 0
        while True:
            strona, wiecej = api.query_purchase_invoices(sesja, od_dnia, do_dnia, page_offset=offset)
            meta.extend(strona)
            if not wiecej:
                break
            offset += len(strona)

        znane = archiwum.znane_numery()
        do_pobrania = [m for m in meta if m.ksef_number not in znane]
        pominiete = len(meta) - len(do_pobrania)

        for i, m in enumerate(do_pobrania, 1):
            if postep:
                postep(f"Pobieranie {i}/{len(do_pobrania)}: {m.invoice_number or m.ksef_number}")
            try:
                xml = api.download_invoice_xml(sesja, m.ksef_number)
                sciezka, _ = archiwum.dodaj(xml, m.ksef_number)
                nowe.append((m.ksef_number, sciezka))
            except Exception as e:
                bledy.append((m.ksef_number, str(e)))
    finally:
        try:
            api.close_session(sesja)
        except Exception:
            pass

    return nowe, pominiete, bledy


# ═══════════════════════════════════════════════════════════════════════════
#  Przeglądarka
# ═══════════════════════════════════════════════════════════════════════════

class OknoArchiwum(tk.Toplevel):
    """
    Dwa panele: lista faktur u góry, pozycje wybranej faktury u dołu.
    Wyszukiwarka przeszukuje także nazwy pozycji — użytkownik zwykle pamięta,
    co kupił, a nie jak faktura była numerowana.
    """

    KOL_FAKTURY = [
        ("data",     "Data",          90,  "c"),
        ("numer",    "Numer faktury", 150, "w"),
        ("sprzedawca", "Sprzedawca",  260, "w"),
        ("nip",      "NIP",           100, "c"),
        ("pozycji",  "Pozycji",        65, "e"),
        ("wartosc",  "Netto",         100, "e"),
        ("ksef",     "Numer KSeF",    290, "w"),
    ]
    KOL_POZYCJE = [
        ("lp",      "Lp.",           45,  "e"),
        ("nazwa",   "Nazwa towaru/usługi", 420, "w"),
        ("jm",      "J.m.",          55,  "c"),
        ("ilosc",   "Ilość",         80,  "e"),
        ("cena",    "Cena netto",    95,  "e"),
        ("wartosc", "Wartość netto", 100, "e"),
    ]

    def __init__(self, parent, katalog, ksef_cfg=None):
        super().__init__(parent)
        self.arch = ArchiwumKsef(katalog)
        self.ksef_cfg = ksef_cfg or {}
        self.title("📚 Archiwum faktur KSeF")
        self.geometry("1250x720")

        self._buduj()
        self._odswiez()
        try:
            self.state("zoomed")
        except Exception:
            pass

    # ── UI ─────────────────────────────────────────────────────────────────
    def _buduj(self):
        top = tk.Frame(self, bg="#34495e", height=44)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="📚 Archiwum faktur KSeF", bg="#34495e", fg="white",
                 font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)

        self.btn_pobierz = tk.Button(top, text="🌐 Pobierz nowe", command=self._pobierz,
                                     bg="#27ae60", fg="white", font=("Arial", 8),
                                     padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_pobierz.pack(side=tk.RIGHT, padx=(4, 10), pady=8)
        tk.Button(top, text="🔧 Odbuduj indeks", command=self._odbuduj,
                  bg="#7f8c8d", fg="white", font=("Arial", 8), padx=8, pady=2,
                  relief=tk.RAISED, bd=1).pack(side=tk.RIGHT, padx=4, pady=8)
        tk.Button(top, text="📂 Otwórz katalog", command=self._otworz_katalog,
                  bg="#7f8c8d", fg="white", font=("Arial", 8), padx=8, pady=2,
                  relief=tk.RAISED, bd=1).pack(side=tk.RIGHT, padx=4, pady=8)

        # pasek filtrów
        f = tk.Frame(self, bg="#ecf0f1")
        f.pack(side=tk.TOP, fill=tk.X)
        tk.Label(f, text="Szukaj:", bg="#ecf0f1", font=("Arial", 8)).pack(side=tk.LEFT, padx=(12, 4), pady=7)
        self.var_szukaj = tk.StringVar()
        e = tk.Entry(f, textvariable=self.var_szukaj, width=28, font=("Arial", 9))
        e.pack(side=tk.LEFT, pady=7)
        e.bind("<KeyRelease>", lambda _ev: self._odswiez())
        tk.Label(f, text="(numer, sprzedawca, NIP lub nazwa pozycji)", bg="#ecf0f1",
                 fg="#7f8c8d", font=("Arial", 7)).pack(side=tk.LEFT, padx=6)

        tk.Label(f, text="Dostawca:", bg="#ecf0f1", font=("Arial", 8)).pack(side=tk.LEFT, padx=(14, 4))
        self.var_dostawca = tk.StringVar(value="— wszyscy —")
        self.cb_dostawca = ttk.Combobox(f, textvariable=self.var_dostawca, width=30,
                                        state="readonly", font=("Arial", 8))
        self.cb_dostawca.pack(side=tk.LEFT, pady=7)
        self.cb_dostawca.bind("<<ComboboxSelected>>", lambda _ev: self._odswiez())

        tk.Label(f, text="Od:", bg="#ecf0f1", font=("Arial", 8)).pack(side=tk.LEFT, padx=(14, 4))
        self.var_od = tk.StringVar()
        tk.Entry(f, textvariable=self.var_od, width=11, font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Label(f, text="Do:", bg="#ecf0f1", font=("Arial", 8)).pack(side=tk.LEFT, padx=(8, 4))
        self.var_do = tk.StringVar()
        tk.Entry(f, textvariable=self.var_do, width=11, font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Button(f, text="Filtruj", command=self._odswiez, font=("Arial", 8),
                  padx=6).pack(side=tk.LEFT, padx=6)
        tk.Button(f, text="🧹 Wyczyść filtry", command=self._wyczysc, font=("Arial", 8),
                  padx=6).pack(side=tk.LEFT, padx=4)

        self.podsum = tk.Label(self, text="", bg="#d6eaf8", fg="#2c3e50",
                               font=("Arial", 9), anchor="w", padx=12, pady=6)
        self.podsum.pack(side=tk.TOP, fill=tk.X)

        panel = ttk.PanedWindow(self, orient=tk.VERTICAL)
        panel.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 4))

        gora = tk.Frame(panel)
        panel.add(gora, weight=3)
        self.tv_f = ttk.Treeview(gora, columns=[k for k, *_ in self.KOL_FAKTURY], show="headings")
        for key, etykieta, szer, kotwica in self.KOL_FAKTURY:
            self.tv_f.heading(key, text=etykieta, command=lambda k=key: self._sortuj(k))
            self.tv_f.column(key, width=szer, anchor=kotwica,
                             stretch=(key == "sprzedawca"), minwidth=45)
        sv = ttk.Scrollbar(gora, orient="vertical", command=self.tv_f.yview)
        self.tv_f.configure(yscrollcommand=sv.set)
        self.tv_f.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sv.pack(side=tk.RIGHT, fill=tk.Y)
        self.tv_f.bind("<<TreeviewSelect>>", self._wybrano)
        self.tv_f.bind("<Double-1>", lambda _ev: self._otworz_xml())

        dol = tk.Frame(panel)
        panel.add(dol, weight=2)
        tk.Label(dol, text="Pozycje faktury", bg="#ecf0f1", anchor="w",
                 font=("Arial", 8, "bold"), padx=8, pady=3).pack(side=tk.TOP, fill=tk.X)
        self.tv_p = ttk.Treeview(dol, columns=[k for k, *_ in self.KOL_POZYCJE], show="headings")
        for key, etykieta, szer, kotwica in self.KOL_POZYCJE:
            self.tv_p.heading(key, text=etykieta)
            self.tv_p.column(key, width=szer, anchor=kotwica,
                             stretch=(key == "nazwa"), minwidth=45)
        sp = ttk.Scrollbar(dol, orient="vertical", command=self.tv_p.yview)
        self.tv_p.configure(yscrollcommand=sp.set)
        self.tv_p.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sp.pack(side=tk.RIGHT, fill=tk.Y)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        self._sort_kol = None
        self._sort_odwr = False

    # ── dane ───────────────────────────────────────────────────────────────
    def _wyczysc(self):
        self.var_szukaj.set("")
        self.var_dostawca.set("— wszyscy —")
        self.var_od.set("")
        self.var_do.set("")
        self._odswiez()

    def _odswiez(self):
        dostawcy = self.arch.dostawcy()
        self.cb_dostawca["values"] = ["— wszyscy —"] + [f"{n} ({nip})" for nip, n in dostawcy]

        nip = ""
        wybrany = self.var_dostawca.get()
        if wybrany and not wybrany.startswith("—"):
            m = re.search(r"\((\d+)\)$", wybrany)
            if m:
                nip = m.group(1)

        wiersze = self.arch.faktury(self.var_szukaj.get().strip(), nip,
                                    self.var_od.get().strip(), self.var_do.get().strip())
        self._wiersze = wiersze
        self._wypelnij(wiersze)

        p = self.arch.podsumowanie()
        zakres = f"{p['od']} … {p['do']}" if p["od"] else "brak faktur"
        self.podsum.config(
            text=f"W archiwum: {p['faktur']} faktur, {p['pozycji']} pozycji, "
                 f"razem {_zl(p['wartosc'])} zł netto   |   zakres dat: {zakres}"
                 f"   |   wyświetlono: {len(wiersze)}")

    def _wypelnij(self, wiersze):
        self.tv_f.delete(*self.tv_f.get_children())
        for ksef, data, numer, sprzed, nip, poz, wart, _plik in wiersze:
            self.tv_f.insert("", "end", iid=ksef, values=(
                data or "", numer or "", sprzed or "", nip or "", poz or 0,
                _zl(wart), ksef))
        self.tv_p.delete(*self.tv_p.get_children())

    def _sortuj(self, kolumna):
        idx = {"data": 1, "numer": 2, "sprzedawca": 3, "nip": 4,
               "pozycji": 5, "wartosc": 6, "ksef": 0}[kolumna]
        self._sort_odwr = not self._sort_odwr if self._sort_kol == kolumna else False
        self._sort_kol = kolumna
        klucz = (lambda w: (w[idx] is None, w[idx])) if idx in (5, 6) else \
                (lambda w: str(w[idx] or "").lower())
        self._wypelnij(sorted(self._wiersze, key=klucz, reverse=self._sort_odwr))

    def _wybrano(self, _ev=None):
        sel = self.tv_f.selection()
        if not sel:
            return
        self.tv_p.delete(*self.tv_p.get_children())
        for lp, nazwa, jm, ilosc, cena, wart in self.arch.pozycje(sel[0]):
            self.tv_p.insert("", "end", values=(
                lp, nazwa, jm, _zl(ilosc), _zl(cena), _zl(wart)))

    def _otworz_xml(self):
        sel = self.tv_f.selection()
        if not sel:
            return
        r = self.arch.con.execute("SELECT plik FROM faktury WHERE ksef_number=?", (sel[0],)).fetchone()
        if r and r[0] and Path(r[0]).exists():
            import os
            os.startfile(r[0])
        else:
            messagebox.showwarning("Archiwum", "Nie znaleziono pliku XML tej faktury.", parent=self)

    def _otworz_katalog(self):
        import os
        os.startfile(str(self.arch.katalog))

    def _odbuduj(self):
        if not messagebox.askyesno(
                "Odbuduj indeks",
                "Przeskanować wszystkie pliki XML w archiwum i odtworzyć indeks?\n\n"
                "Pliki nie zostaną zmienione — przebudowany będzie tylko\n"
                "indeks archiwum.sqlite.", parent=self):
            return
        ok, bledy = self.arch.odbuduj_indeks()
        self._odswiez()
        tresc = f"Zaindeksowano {ok} faktur."
        if bledy:
            tresc += f"\nNie udało się wczytać {len(bledy)} plików (patrz konsola)."
            for nazwa, blad in bledy:
                print(f"⚠️  {nazwa}: {blad}")
        messagebox.showinfo("Odbuduj indeks", tresc, parent=self)

    # ── pobieranie ─────────────────────────────────────────────────────────
    def _pobierz(self):
        nip = re.sub(r"\D", "", self.ksef_cfg.get("nip", ""))
        token = self.ksef_cfg.get("token", "")
        srodowisko = self.ksef_cfg.get("environment", "test")

        if not nip or not token:
            messagebox.showwarning(
                "Brak konfiguracji KSEF",
                "Uzupełnij NIP firmy i token API KSEF w menu\n"
                "'Ustawienia → Ścieżki do baz danych' (sekcja KSEF).", parent=self)
            return

        from tkinter import simpledialog
        dni = simpledialog.askinteger("Pobierz nowe faktury",
                                      "Sprawdzić faktury z ilu ostatnich dni?",
                                      initialvalue=30, minvalue=1, maxvalue=730, parent=self)
        if not dni:
            return

        if srodowisko != "production":
            if not messagebox.askyesno(
                    "Środowisko testowe",
                    "KSeF jest ustawiony na środowisko TESTOWE — pobiorą się\n"
                    "faktury testowe, nie prawdziwe.\n\n"
                    "Aby pobierać prawdziwe faktury, ustaw środowisko na\n"
                    "„produkcyjne\" i wpisz token produkcyjny.\n\nKontynuować mimo to?",
                    parent=self):
                return

        self.btn_pobierz.config(state=tk.DISABLED)
        threading.Thread(target=self._pobierz_worker,
                         args=(nip, token, srodowisko, dni), daemon=True).start()

    def _pobierz_worker(self, nip, token, srodowisko, dni):
        # Osobne połączenie — sqlite3 nie lubi dzielenia kursorów między wątkami.
        arch = ArchiwumKsef(self.arch.katalog)
        try:
            def postep(tekst):
                self.after(0, lambda: self.status.config(text=tekst))
            nowe, pominiete, bledy = pobierz_nowe(arch, nip, token, srodowisko, dni, postep)
            self.after(0, lambda: self._pobrano(nowe, pominiete, bledy, None))
        except Exception as e:
            blad = str(e)
            self.after(0, lambda: self._pobrano([], 0, [], blad))
        finally:
            arch.zamknij()

    def _pobrano(self, nowe, pominiete, bledy, blad):
        self.btn_pobierz.config(state=tk.NORMAL)
        if blad:
            self.status.config(text="Błąd pobierania.")
            messagebox.showerror("Pobieranie z KSeF", blad, parent=self)
            return
        self._odswiez()
        self.status.config(text=f"Pobrano {len(nowe)} nowych faktur "
                                f"({pominiete} już było w archiwum).")
        tresc = f"Nowych faktur: {len(nowe)}\nJuż w archiwum (pominięto): {pominiete}"
        if bledy:
            tresc += f"\nBłędy: {len(bledy)} (patrz konsola)"
            for numer, b in bledy:
                print(f"⚠️  {numer}: {b}")
        messagebox.showinfo("Pobieranie z KSeF", tresc, parent=self)


def open_window(parent, katalog, ksef_cfg=None):
    return OknoArchiwum(parent, katalog, ksef_cfg)
