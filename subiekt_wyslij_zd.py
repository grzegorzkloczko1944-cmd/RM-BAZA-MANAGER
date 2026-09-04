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
import subprocess
import threading
import tkinter as tk
import urllib.parse
from pathlib import Path
from tkinter import ttk, messagebox

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
        for i, (symbol, nazwa, ilosc, jm) in enumerate(pozycje, 1):
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
                 nadawca, szukaj_plikow=None, katalog_pdf=None, szukaj_maila=None):
        super().__init__(parent)
        self.numer_zd = numer_zd
        self.dostawca = dostawca
        self.projekt = projekt
        self.pozycje = pozycje              # [(symbol, nazwa, ilosc, jm)]
        self.nadawca = nadawca
        self.szukaj_plikow = szukaj_plikow  # callable(symbol) -> [Path]
        self.szukaj_maila = szukaj_maila    # callable(nip) -> str
        self.katalog_pdf = katalog_pdf or Path(os.environ.get("TEMP", ".")) / "rm_baza_zd"
        self.pliki = {}                     # {ścieżka: BooleanVar}
        self.pdf_zd = None

        self.title(f"Wyślij zamówienie {numer_zd}")
        self.geometry("860x680")
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

        obszar = tk.Frame(dol)
        obszar.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(obszar, highlightthickness=0)
        sp = ttk.Scrollbar(obszar, orient="vertical", command=self.canvas.yview)
        self.lista = tk.Frame(self.canvas)
        self.lista.bind("<Configure>",
                        lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.lista, anchor="nw")
        self.canvas.configure(yscrollcommand=sp.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sp.pack(side=tk.RIGHT, fill=tk.Y)

        stopka = tk.Frame(self, bg="#ecf0f1")
        stopka.pack(side=tk.BOTTOM, fill=tk.X)
        self.btn_wyslij = tk.Button(stopka, text="📧 Otwórz w programie pocztowym",
                                    command=self._wyslij, bg="#27ae60", fg="white",
                                    font=("Arial", 9, "bold"), padx=14, pady=5,
                                    state=tk.DISABLED)
        self.btn_wyslij.pack(side=tk.RIGHT, padx=10, pady=8)
        tk.Button(stopka, text="Anuluj", command=self.destroy,
                  font=("Arial", 9), padx=12, pady=5).pack(side=tk.RIGHT, pady=8)

        self.status = tk.Label(self, text="Przygotowywanie…", anchor="w", padx=12,
                               pady=3, bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    # ── zbieranie plików ───────────────────────────────────────────────────
    def _zbierz_async(self):
        threading.Thread(target=self._zbierz_worker, daemon=True).start()

    def _zbierz_worker(self):
        znalezione, bledy = [], []
        try:
            self.after(0, lambda: self.status.config(text="Generowanie PDF zamówienia z Subiekta…"))
            pdfy, bl = eksportuj_pdf([self.numer_zd], self.katalog_pdf)
            dane = pdfy.get(self.numer_zd) or {}
            self.pdf_zd = dane.get("plik")
            if self.pdf_zd:
                znalezione.append(Path(self.pdf_zd))
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

        if self.szukaj_plikow:
            for i, (symbol, *_rest) in enumerate(self.pozycje, 1):
                self.after(0, lambda s=symbol, i=i: self.status.config(
                    text=f"Szukanie rysunków {i}/{len(self.pozycje)}: {s}"))
                try:
                    for p in self.szukaj_plikow(symbol) or []:
                        if Path(p) not in znalezione:
                            znalezione.append(Path(p))
                except Exception as e:
                    bledy.append(f"{symbol}: {e}")

        self.after(0, lambda: self._zbierz_done(znalezione, bledy))

    def _zbierz_done(self, pliki, bledy):
        for w in self.lista.winfo_children():
            w.destroy()
        self.pliki.clear()

        for p in pliki:
            var = tk.BooleanVar(value=True)
            self.pliki[str(p)] = var
            wiersz = tk.Frame(self.lista)
            wiersz.pack(fill=tk.X, anchor="w")
            tk.Checkbutton(wiersz, variable=var, font=("Arial", 8)).pack(side=tk.LEFT)
            czy_pdf_zd = self.pdf_zd and str(p) == str(self.pdf_zd)
            tk.Label(wiersz, text=("📄 " if czy_pdf_zd else "📐 ") + Path(p).name,
                     font=("Arial", 8, "bold" if czy_pdf_zd else "normal"),
                     anchor="w").pack(side=tk.LEFT, padx=2)
            try:
                kb = Path(p).stat().st_size / 1024
                tk.Label(wiersz, text=f"{kb:,.0f} kB".replace(",", " "), fg="#7f8c8d",
                         font=("Arial", 7)).pack(side=tk.LEFT, padx=6)
            except Exception:
                pass

        if not pliki:
            tk.Label(self.lista, text="Nie znaleziono żadnych plików.",
                     fg="#c0392b", font=("Arial", 8), padx=8, pady=6).pack(anchor="w")

        self.btn_wyslij.config(state=tk.NORMAL)
        komunikat = f"Załączników: {len(pliki)}"
        if bledy:
            komunikat += f"   |   problemy: {len(bledy)} (patrz konsola)"
            for b in bledy:
                print(f"⚠️  {b}")
        self.status.config(text=komunikat)

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

        wybrane = [p for p, v in self.pliki.items() if v.get()]
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
        self.destroy()


def open_window(parent, numer_zd, dostawca, email, projekt, pozycje, nadawca,
                szukaj_plikow=None, katalog_pdf=None, szukaj_maila=None):
    return OknoWysylki(parent, numer_zd, dostawca, email, projekt, pozycje,
                       nadawca, szukaj_plikow, katalog_pdf, szukaj_maila)
