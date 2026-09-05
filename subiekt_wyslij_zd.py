"""
Wysyłka zamówienia do dostawcy (ZD) mailem — PDF z Subiekta + rysunki z dysku.

Przepływ:
    1. most (tryb "wydruk") eksportuje ZD do PDF wzorcem Subiekta — wygląd 1:1
       z tym, co Subiekt drukuje ręcznie
    2. dla każdej pozycji ZD szukamy plików rysunku na serwerze — TĄ SAMĄ
       logiką co RFQ (_find_files_for_drawing z arkusza głównego)
    3. otwieramy gotową wiadomość w Outlooku (COM) z wklejoną treścią
       i podpiętymi plikami — NIC nie wychodzi bez kliknięcia „Wyślij"

Dlaczego Outlook COM, a nie mailto: — mailto nie przenosi załączników (tak
mówi standard i tak zachowuje się Windows). Outlook przez COM przyjmuje je
bez problemu; sprawdzone 04.09.2026 na Outlooku 16.0. Gdy Outlooka nie ma,
schodzimy do mailto: z samą treścią i mówimy wprost, że pliki trzeba dopiąć
ręcznie (katalog otwieramy w Eksploratorze).

⚠️ Wiadomość jest tylko OTWIERANA (Display), nigdy Send() — wysyła człowiek.
"""

import os
import re
import subprocess
import threading
import tkinter as tk
import urllib.parse
from pathlib import Path
from tkinter import ttk, messagebox

import rm_panel_plikow
from subiekt_stany import _find_exe, blad_mostu, wysrodkuj

TIMEOUT_S = 180


def eksportuj_pdf(numery, katalog, timeout=TIMEOUT_S):
    """
    Most: tryb "wydruk". Zwraca {numer ZD: ścieżka PDF} dla udanych eksportów.
    Rzuca RuntimeError z czytelnym komunikatem, gdy most zawiedzie.
    """
    import json
    import tempfile

    exe = _find_exe()
    katalog = Path(katalog)
    katalog.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "wydruk.json"
        proc = subprocess.run(
            [str(exe), "wydruk", f"--numery={';'.join(numery)}",
             f"--pdf={katalog}", f"--out={out}"],
            capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if not out.exists():
            raise RuntimeError(blad_mostu(exe, "wydruk", proc, out))
        dane = json.loads(out.read_text(encoding="utf-8"))

    if dane.get("blad"):
        raise RuntimeError(dane["blad"])

    wynik, bledy = {}, []
    for p in dane.get("pliki", []):
        if p.get("ok") and p.get("plik"):
            wynik[p["numer"]] = {"plik": p["plik"], "nip": p.get("nip") or "",
                                 "dostawca": p.get("dostawca") or ""}
        else:
            bledy.append(f"{p.get('numer')}: {p.get('blad')}")
    if not wynik:
        raise RuntimeError("Nie udało się wyeksportować żadnego PDF-a.\n" + "\n".join(bledy))
    return wynik, bledy


#: Format numeru rysunku RMPAK: prefiks-KKK.NN (+ opcjonalny sufiks X/XX/Z/ZZ).
#: Wzięty wprost z RM_IMPORT (RE_RMPAK_BASE w RM_IMPORT_V17_MOD.py) — to ta
#: sama definicja, której używa import BOM-u, więc oba narzędzia rozumieją
#: „numer rysunku" identycznie.
RE_NUMER_RYSUNKU = re.compile(r"^[A-Za-z0-9]{2,8}-\d{3}\.\d{2}")


def _ma_numer_rysunku(symbol):
    """Czy symbol jest numerem rysunku RMPAK?

    Decyduje FORMAT numeru, nie jego „wygląd". Wcześniejsza reguła („ma
    myślnik i cyfrę") uznawała za rysunki kody handlowe — 'A-8-10-10',
    'DSNU-25-100-P', 'GS14 14-16' — i panel przeczesywał dla nich serwer,
    kończąc czerwonym „nie znaleziono plików" (zgłoszone 05.09.2026).

    Obowiązkowa jest część `.NN` po trzycyfrowym katalogu; to ona odróżnia
    '2627-100.01' od 'A-8-10-10'. Sprawdzone na 24 realnych symbolach
    (10 produkowanych, 14 handlowych) — wszystkie sklasyfikowane poprawnie.
    """
    s = (symbol or "").strip()
    # Spacje wokół myślnika bywają wklejone z Excela ('2556 - 100.07XX').
    s = re.sub(r"\s*-\s*", "-", re.sub(r"\s+", " ", s))
    return bool(RE_NUMER_RYSUNKU.match(s))


def otworz_maila(do, temat, tresc, zalaczniki, dw=""):
    """
    Otwiera wiadomość w domyślnym programie pocztowym. Zwraca nazwę użytej
    drogi: "outlook" albo "mailto". NIE wysyła — użytkownik klika Wyślij sam.
    """
    try:
        import win32com.client as win32
        ol = win32.Dispatch("Outlook.Application")
        mail = ol.CreateItem(0)                 # olMailItem
        mail.To = do or ""
        if dw:
            mail.CC = dw
        mail.Subject = temat
        mail.Body = tresc
        for z in zalaczniki:
            if Path(z).exists():
                mail.Attachments.Add(str(z))
        mail.Display(False)                     # pokaż okno, nie wysyłaj
        return "outlook"
    except Exception:
        # Outlooka nie ma albo COM niedostępny — mailto niesie tylko tekst.
        url = "mailto:" + urllib.parse.quote(do or "") + "?" + urllib.parse.urlencode(
            {"subject": temat, "body": tresc}, quote_via=urllib.parse.quote)
        os.startfile(url)
        return "mailto"


def tresc_wiadomosci(numer_zd, dostawca, projekt, pozycje, nadawca, firma="RM PRODUKCJA"):
    """
    Treść maila. Pozycje wypisane, żeby dostawca widział zamówienie także
    w treści, nie tylko w załączniku.
    """
    linie = [f"Dzień dobry,", ""]
    linie.append(f"w załączeniu przesyłam zamówienie {numer_zd}"
                 + (f" dotyczące projektu {projekt}." if projekt else "."))
    linie.append("")
    if pozycje:
        linie.append("Zamawiane pozycje:")
        # Krotki mają 4 pola, a od 2026-09-05 opcjonalnie piąte (ma_rysunek) —
        # rozpakowanie na sztywno wywalałoby się na dłuższej krotce.
        for i, wiersz in enumerate(pozycje, 1):
            symbol, nazwa, ilosc, jm = (list(wiersz) + ["", "", "", ""])[:4]
            opis = f"{symbol}" + (f" — {nazwa}" if nazwa and nazwa != symbol else "")
            linie.append(f"  {i}. {opis}: {ilosc} {jm}".rstrip())
        linie.append("")
    linie.append("Do wiadomości dołączam rysunki techniczne zamawianych pozycji.")
    linie.append("")
    linie.append("Proszę o potwierdzenie przyjęcia zamówienia oraz podanie terminu realizacji.")
    linie.append("")
    linie.append("Pozdrawiam,")
    linie.append(nadawca)
    linie.append(firma)
    return "\n".join(linie)


class OknoWysylki(tk.Toplevel):
    """
    Podgląd przed wysłaniem: adresat, temat, treść i lista załączników
    z możliwością odznaczenia. Pliki rysunków zbierane są w tle, bo skan
    serwera potrafi potrwać.
    """

    def __init__(self, parent, numer_zd, dostawca, email, projekt, pozycje,
                 nadawca, szukaj_plikow=None, katalog_pdf=None, szukaj_maila=None,
                 szukaj_dalej=None, needs_dxf=None, register_drop=None,
                 dozwolone_ext=None, blad_serwera=None):
        super().__init__(parent)
        self.numer_zd = numer_zd
        self.dostawca = dostawca
        self.projekt = projekt
        self.pozycje = pozycje              # [(symbol, nazwa, ilosc, jm)]
        self.nadawca = nadawca
        self.szukaj_plikow = szukaj_plikow  # callable(symbol[, projekty]) -> [Path]
        #: symbol → [numery projektów]; wypełniane w _pozycje_dla_panelu,
        #: używane przez _szukaj_w_projektach do ustalenia kolejności katalogów.
        self._projekty_pozycji = {}
        self.szukaj_maila = szukaj_maila    # callable(nip) -> str
        # Zależności panelu plików — te same, których używa okno RFQ.
        # Wszystkie opcjonalne: bez nich panel po prostu nie pokazuje
        # „Szukaj dalej…" ani nie przyjmuje przeciągania.
        self.szukaj_dalej = szukaj_dalej
        self.needs_dxf = needs_dxf
        self.register_drop = register_drop
        self.dozwolone_ext = dozwolone_ext
        self.blad_serwera = blad_serwera or (lambda: None)
        self.katalog_pdf = katalog_pdf or Path(os.environ.get("TEMP", ".")) / "rm_baza_zd"
        self.pdf_zd = None
        self._blad_pdf = ""
        self.panel = None

        self.title(f"Wyślij zamówienie {numer_zd}")
        self.geometry("860x680")
        # Panel podpina globalny bind kółka myszy na czas, gdy kursor jest nad
        # listą — zamknięcie okna musi go zdjąć, inaczej uchwyt przeżywa okno.
        self.protocol("WM_DELETE_WINDOW", self._zamknij)
        self._buduj(email)
        wysrodkuj(self, parent, 860, 680)
        self.after(80, self._zbierz_async)

    def _buduj(self, email):
        top = tk.Frame(self, bg="#34495e", height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text=f"📧 Wyślij zamówienie {self.numer_zd}", bg="#34495e",
                 fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)

        f = tk.Frame(self, bg="#ecf0f1")
        f.pack(side=tk.TOP, fill=tk.X, padx=0, pady=0)
        tk.Label(f, text="Do:", bg="#ecf0f1", font=("Arial", 8, "bold")).grid(
            row=0, column=0, sticky="e", padx=(12, 4), pady=6)
        self.var_do = tk.StringVar(value=email or "")
        tk.Entry(f, textvariable=self.var_do, width=48, font=("Arial", 9)).grid(
            row=0, column=1, sticky="w", pady=6)
        tk.Label(f, text=self.dostawca[:44], bg="#ecf0f1", fg="#7f8c8d",
                 font=("Arial", 8)).grid(row=0, column=2, sticky="w", padx=8)

        tk.Label(f, text="Temat:", bg="#ecf0f1", font=("Arial", 8, "bold")).grid(
            row=1, column=0, sticky="e", padx=(12, 4), pady=(0, 6))
        temat = f"Zamówienie {self.numer_zd}" + (f" — projekt {self.projekt}" if self.projekt else "")
        self.var_temat = tk.StringVar(value=temat)
        tk.Entry(f, textvariable=self.var_temat, width=68, font=("Arial", 9)).grid(
            row=1, column=1, columnspan=2, sticky="w", pady=(0, 6))

        # Stopka i pasek stanu MUSZĄ być spakowane przed rozciągliwym panelem.
        # Tk rozdziela miejsce w kolejności pakowania: gdy panel z expand=True
        # idzie pierwszy, zabiera całą wysokość, a przyciski wyjeżdżają poza
        # dolną krawędź okna (zgłoszone 05.09.2026: „pozycja sobie jeździ
        # i psuje dolne klawisze"). Przypięte pierwsze — zostają na miejscu,
        # a kurczy się panel.
        self.status = tk.Label(self, text="Przygotowywanie…", anchor="w", padx=12,
                               pady=3, bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        stopka = tk.Frame(self, bg="#ecf0f1")
        stopka.pack(side=tk.BOTTOM, fill=tk.X)
        self.btn_wyslij = tk.Button(stopka, text="📧 Otwórz w programie pocztowym",
                                    command=self._wyslij, bg="#27ae60", fg="white",
                                    font=("Arial", 9, "bold"), padx=14, pady=5,
                                    state=tk.DISABLED)
        self.btn_wyslij.pack(side=tk.RIGHT, padx=10, pady=8)
        tk.Button(stopka, text="Anuluj", command=self._zamknij,
                  font=("Arial", 9), padx=12, pady=5).pack(side=tk.RIGHT, pady=8)

        panel = ttk.PanedWindow(self, orient=tk.VERTICAL)
        panel.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        gora = tk.Frame(panel)
        panel.add(gora, weight=3)
        tk.Label(gora, text="Treść wiadomości", bg="#ecf0f1", anchor="w",
                 font=("Arial", 8, "bold"), padx=8, pady=3).pack(side=tk.TOP, fill=tk.X)
        self.txt = tk.Text(gora, wrap="word", font=("Consolas", 9), height=14)
        sv = ttk.Scrollbar(gora, orient="vertical", command=self.txt.yview)
        self.txt.configure(yscrollcommand=sv.set)
        self.txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sv.pack(side=tk.RIGHT, fill=tk.Y)
        self.txt.insert("1.0", tresc_wiadomosci(
            self.numer_zd, self.dostawca, self.projekt, self.pozycje, self.nadawca))

        dol = tk.Frame(panel)
        panel.add(dol, weight=2)
        naglowek = tk.Frame(dol, bg="#ecf0f1")
        naglowek.pack(side=tk.TOP, fill=tk.X)
        tk.Label(naglowek, text="Załączniki", bg="#ecf0f1", anchor="w",
                 font=("Arial", 8, "bold"), padx=8, pady=3).pack(side=tk.LEFT)
        tk.Button(naglowek, text="📂 Katalog", command=self._otworz_katalog,
                  font=("Arial", 7), padx=6).pack(side=tk.RIGHT, padx=6, pady=2)

        # Panel „pozycje i znalezione pliki" — ten sam, którego używa okno
        # „Wyślij do RFQ". Wcześniej była tu płaska lista wszystkich plików;
        # nie dało się dorzucić brakującego rysunku ani zobaczyć, której
        # pozycji brakuje dokumentacji.
        self.panel = rm_panel_plikow.PanelPlikow(
            dol,
            pozycje=self._pozycje_dla_panelu(),
            szukaj_plikow=self._szukaj_w_projektach,
            szukaj_dalej=self.szukaj_dalej,
            needs_dxf=self.needs_dxf,
            register_drop=self.register_drop,
            dozwolone_ext=self.dozwolone_ext,
            blad_serwera=self.blad_serwera,
            okno=self,
            on_zmiana=self._po_zmianie_plikow,
        )
        self.panel.zbuduj_ramke().pack(fill=tk.BOTH, expand=True)

    # ── pozycje dla panelu ─────────────────────────────────────────────────
    def _pozycje_dla_panelu(self):
        """Krotki (symbol, nazwa, ilosc, jm) → słowniki, których chce panel.

        `is_catalog` dla pozycji bez numeru rysunku: łożysko czy siłownik nie
        ma dokumentacji na serwerze, więc brak plików to dla nich norma —
        panel nie liczy ich do ostrzeżenia „brak plików".
        """
        out = []
        for wiersz in self.pozycje:
            pola = list(wiersz) + [None] * 6
            symbol, nazwa, ilosc, jm, ma_rysunek, projekty = pola[:6]
            # Czy szukać rysunków na serwerze:
            #   1. `ma_rysunek` z BOM-u — dowód wprost (wiersz miał *_drawing_no),
            #      gdy pozycja dopasowała się do BOM-u,
            #   2. w przeciwnym razie FORMAT numeru (RE_NUMER_RYSUNKU) — ta sama
            #      definicja, której używa import BOM-u.
            # Poprzednia reguła („ma myślnik i cyfrę") brała za rysunki kody
            # handlowe 'A-8-10-10', 'DSNU-25-100-P', 'GS14 14-16' i panel
            # przeczesywał dla nich serwer, kończąc czerwonym „nie znaleziono
            # plików" (zgłoszone 05.09.2026).
            if ma_rysunek is not None:
                katalogowy = not ma_rysunek
            else:
                katalogowy = not _ma_numer_rysunku(symbol)
            # Numery projektów pozycji — po nich szukanie zaczyna od katalogu
            # projektu, w którym detal powstał. ZD zbiera z kilku projektów,
            # więc bez tego trafiało najpierw do projektu otwartego w arkuszu.
            self._projekty_pozycji[str(symbol).strip().upper()] = [
                p.strip() for p in str(projekty or "").split(",") if p.strip()
            ]
            out.append({
                "drawing_no": symbol,
                "name": nazwa or symbol,
                "qty": ilosc,
                "jm": jm,
                "is_catalog": katalogowy,
            })
        return out

    def _szukaj_w_projektach(self, numer):
        """Pliki rysunku — najpierw w katalogach projektów Z KOLUMNY „Projekt".

        Panel woła szukanie jednoargumentowo (tak samo dla RFQ), więc numery
        projektów dokładamy tutaj, z mapy zbudowanej w `_pozycje_dla_panelu`.
        Gdy w projektach pozycji nic nie ma, spada do zwykłego szukania —
        czyli do zachowania sprzed zmiany.
        """
        if not self.szukaj_plikow:
            return []
        projekty = self._projekty_pozycji.get(str(numer).strip().upper()) or []
        # `szukaj_plikow` przyjmuje opcjonalne `projekty`; starsze okno główne
        # może go nie znać — wtedy lecimy po staremu.
        if projekty:
            try:
                znalezione = self.szukaj_plikow(numer, projekty) or []
                if znalezione:
                    return znalezione
            except TypeError:
                pass                    # stara sygnatura — niżej wariant bez projektów
            except Exception as e:
                print(f"⚠️  Szukanie plików {numer} w projektach {projekty}: {e}")
        try:
            return self.szukaj_plikow(numer) or []
        except Exception as e:
            print(f"⚠️  Szukanie plików {numer}: {e}")
            return []

    def _po_zmianie_plikow(self):
        """Panel zmienił listę plików — odśwież licznik w pasku stanu."""
        try:
            pliki = self.panel.wszystkie_zaznaczone() if self.panel else []
        except Exception:
            return
        ile = len(pliki) + (1 if self.pdf_zd else 0)
        tekst = f"Załączników: {ile}"
        if self.pdf_zd:
            tekst += "   (w tym PDF zamówienia)"
        elif self._blad_pdf:
            tekst += f"   |   brak PDF zamówienia: {self._blad_pdf}"
        self.status.config(text=tekst)

    # ── zbieranie plików ───────────────────────────────────────────────────
    def _zbierz_async(self):
        # Panel sam szuka rysunków (z paskiem postępu). W tle zostaje tylko
        # PDF zamówienia z Subiekta — to osobne, wolne wywołanie mostu.
        self.panel.start()
        threading.Thread(target=self._zbierz_worker, daemon=True).start()

    def _zbierz_worker(self):
        bledy = []
        try:
            self.after(0, lambda: self.status.config(
                text="Generowanie PDF zamówienia z Subiekta…"))
            pdfy, bl = eksportuj_pdf([self.numer_zd], self.katalog_pdf)
            dane = pdfy.get(self.numer_zd) or {}
            self.pdf_zd = dane.get("plik")
            # Adres z RM_BAZA po NIP-cie — pewniejszy klucz niż nazwa firmy,
            # która w Subiekcie bywa pełna, a w RM_BAZA skrócona. Ustawiamy
            # tylko wtedy, gdy pole jest jeszcze puste (user mógł już wpisać).
            nip = dane.get("nip")
            if nip and self.szukaj_maila and not self.var_do.get().strip():
                try:
                    mail = self.szukaj_maila(nip)
                    if mail:
                        self.after(0, lambda m=mail: self.var_do.set(m))
                except Exception as e:
                    bledy.append(f"mail po NIP {nip}: {e}")
            bledy.extend(bl)
        except Exception as e:
            bledy.append(f"PDF zamówienia: {e}")

        self.after(0, lambda: self._zbierz_done(bledy))

    def _zbierz_done(self, bledy):
        self._blad_pdf = "; ".join(bledy) if bledy else ""
        for b in bledy:
            print(f"⚠️  {b}")
        self.btn_wyslij.config(state=tk.NORMAL)
        self._po_zmianie_plikow()

    def _zamknij(self):
        if self.panel:
            self.panel.sprzataj()
        self.destroy()

    def _otworz_katalog(self):
        try:
            os.startfile(str(self.katalog_pdf))
        except Exception as e:
            messagebox.showwarning("Katalog", str(e), parent=self)

    # ── wysyłka ────────────────────────────────────────────────────────────
    def _wyslij(self):
        do = self.var_do.get().strip()
        if not do:
            if not messagebox.askyesno(
                    "Brak adresu",
                    "Nie podano adresu e-mail dostawcy.\n\n"
                    "Otworzyć wiadomość bez adresata?", parent=self):
                return

        # Załączniki: PDF zamówienia (jeśli powstał) + rysunki zaznaczone
        # w panelu. PDF jako pierwszy — to główny dokument wiadomości.
        wybrane = []
        if self.pdf_zd:
            wybrane.append(str(self.pdf_zd))
        wybrane += [str(p) for p in (self.panel.wszystkie_zaznaczone() if self.panel else [])]

        # Detal cięty laserem bez DXF-a — kooperant nie ma z czego ciąć.
        braki = self.panel.brakujace_dxf() if self.panel else []
        if braki and not messagebox.askyesno(
                "Brak DXF",
                "Te pozycje są cięte laserem, ale nie mają zaznaczonego DXF-a:\n\n"
                + "\n".join(f"  • {b}" for b in braki[:10])
                + ("\n  …" if len(braki) > 10 else "")
                + "\n\nWysłać mimo to?", parent=self, icon="warning"):
            return

        try:
            droga = otworz_maila(do, self.var_temat.get().strip(),
                                 self.txt.get("1.0", "end-1c"), wybrane)
        except Exception as e:
            messagebox.showerror("Program pocztowy",
                                 f"Nie udało się otworzyć wiadomości:\n{e}", parent=self)
            return

        if droga == "mailto":
            # mailto nie przenosi załączników — powiedz to wprost i pokaż pliki.
            messagebox.showwarning(
                "Załączniki",
                "Nie wykryto Outlooka, więc wiadomość otwarto przez mailto:,\n"
                "które NIE PRZENOSI ZAŁĄCZNIKÓW.\n\n"
                f"Dopnij ręcznie {len(wybrane)} plik(ów) — katalog zaraz się otworzy.",
                parent=self)
            try:
                os.startfile(str(self.katalog_pdf))
            except Exception:
                pass

        self.status.config(text="Wiadomość otwarta w programie pocztowym — wyślij ją stamtąd.")
        self._zamknij()


def open_window(parent, numer_zd, dostawca, email, projekt, pozycje, nadawca,
                szukaj_plikow=None, katalog_pdf=None, szukaj_maila=None,
                szukaj_dalej=None, needs_dxf=None, register_drop=None,
                dozwolone_ext=None, blad_serwera=None):
    return OknoWysylki(parent, numer_zd, dostawca, email, projekt, pozycje,
                       nadawca, szukaj_plikow, katalog_pdf, szukaj_maila,
                       szukaj_dalej=szukaj_dalej, needs_dxf=needs_dxf,
                       register_drop=register_drop, dozwolone_ext=dozwolone_ext,
                       blad_serwera=blad_serwera)
