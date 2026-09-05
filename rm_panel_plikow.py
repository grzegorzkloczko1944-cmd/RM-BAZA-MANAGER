# -*- coding: utf-8 -*-
"""
Panel „pozycje i znalezione pliki" — wspólny dla RFQ i wysyłki ZD.

Kawałek okna, w którym dla każdej pozycji widać znalezione rysunki
(PDF/DXF/DWF/STEP/STL) z checkboxami, a brakujące da się dorzucić ręcznie:
przyciskiem, przeciągnięciem z Eksploratora albo szukaniem w innym źródle.

Dlaczego osobny moduł, a nie kopia:
    Ten panel powstał dla „Wyślij do RFQ" i sprawdził się — pokazuje pliki
    per pozycja, ostrzega gdy detalowi na laser brakuje DXF-a, odróżnia
    „nie ma plików" od „nie ma dostępu do serwera". Wysyłka ZD miała własną,
    uboższą listę (płaska, bez dosypywania). Zamiast przeklejać 600 linii
    i utrzymywać dwie kopie, logika siedzi tutaj, a oba okna ją wołają.

Zależności od okna głównego są WSTRZYKIWANE (szukaj_plikow, needs_dxf,
register_drop…), więc moduł nie importuje RM_BAZA i da się go testować
osobno.

Użycie:

    panel = PanelPlikow(
        rodzic, pozycje,
        szukaj_plikow=okno._find_files_for_drawing,
        szukaj_dalej=okno._ask_rfq_scan_source,      # opcjonalne
        needs_dxf=okno._rfq_needs_dxf,               # opcjonalne
        register_drop=okno._register_file_drop,      # opcjonalne
        dozwolone_ext=okno.RFQ_PORTAL_EXTS,
        blad_serwera=lambda: okno._rfq_server_error,
        pola_edycji=True,                            # ilość/materiał/uwagi
    )
    panel.start()                 # buduje wiersze po jednym, z paskiem postępu
    ...
    panel.zaznaczone_pliki()      # [(pozycja, [Path, ...])]
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# Rozszerzenia, które ma sens wysyłać. Domyślne — wołający może podać własne
# (portal RFQ przyjmuje węższy zbiór niż zwykły mail).
DOMYSLNE_EXT = {"pdf", "dwf", "dxf", "stp", "step", "stl"}


class PanelPlikow:
    """Lista pozycji z plikami. Nie jest widgetem — buduje je w podanym rodzicu."""

    def __init__(self, rodzic, pozycje, szukaj_plikow,
                 szukaj_dalej=None, needs_dxf=None, register_drop=None,
                 dozwolone_ext=None, blad_serwera=None, pola_edycji=False,
                 okno=None, on_zmiana=None, szukaj_hurtem=None):
        """
        `pozycje` — lista słowników; wymagane klucze: 'drawing_no', 'name'.
                    Opcjonalne: 'qty', 'material', 'notes', 'is_catalog'.
                    Panel dopisuje do nich 'files' i (gdy pola_edycji)
                    zmienne Tk z wpisanymi wartościami.
        `szukaj_plikow(numer)` -> [Path]  — właściwe wyszukiwanie na serwerze.
        `szukaj_dalej(pozycja)` -> [Path] — alternatywne źródło (biblioteka,
                    głęboki skan); bez tego przycisk „Szukaj dalej…" nie
                    jest pokazywany.
        `needs_dxf(numer)` -> bool — detal cięty laserem, bez DXF-a nie ma
                    czego wysłać.
        `register_drop(widget, callback)` -> bool — podpięcie drag & drop.
        `blad_serwera()` -> str|None — komunikat, gdy dysk sieciowy jest
                    niedostępny; odróżnia awarię od „detal nie ma rysunków".
        `szukaj_hurtem(numery)` -> {numer: [Path]} — JEDNO przejście po
                    bibliotece dla wszystkich brakujących pozycji naraz.
                    Bez tego przycisk „Szukaj wszystkich…" się nie pokazuje.
        """
        self.rodzic = rodzic
        self.pozycje = pozycje
        self.szukaj_plikow = szukaj_plikow
        self.szukaj_dalej = szukaj_dalej
        self.needs_dxf = needs_dxf or (lambda _nr: False)
        self.register_drop = register_drop
        self.dozwolone_ext = {e.lower().lstrip(".")
                              for e in (dozwolone_ext or DOMYSLNE_EXT)}
        self.blad_serwera = blad_serwera or (lambda: None)
        self.szukaj_hurtem = szukaj_hurtem
        self.pola_edycji = pola_edycji
        self.okno = okno or rodzic          # rodzic dla okien dialogowych
        self.on_zmiana = on_zmiana          # wołane po każdej zmianie plików

        # (numer_rysunku, ścieżka) -> BooleanVar. Klucz z numerem, bo ten sam
        # plik może pasować do dwóch pozycji, a odznaczenie ma dotyczyć jednej.
        self.file_vars = {}
        self._zbudowane = False

    # ── budowa ─────────────────────────────────────────────────────────────
    def zbuduj_ramke(self):
        """Przewijalna lista + pasek postępu. Zwraca ramkę zewnętrzną."""
        zewn = tk.Frame(self.rodzic)

        # Pasek postępu szukania plików — przy wielu pozycjach × wolny serwer
        # przeszukiwanie trwa i bez tego okno wygląda na zawieszone. Etykieta
        # mówi KTÓRA pozycja, pasek — ile jeszcze zostało. Znika po zbudowaniu
        # wszystkich wierszy (pack_forget w _buduj_nastepny).
        self._prog_frame = tk.Frame(zewn)
        self._prog_frame.pack(fill=tk.X, padx=4, pady=(2, 0))
        self._prog_label = tk.Label(self._prog_frame, text="", anchor="w",
                                    font=("Arial", 8), fg="#555")
        self._prog_label.pack(fill=tk.X)
        self._prog_bar = ttk.Progressbar(self._prog_frame, mode="determinate",
                                         maximum=max(len(self.pozycje), 1))
        self._prog_bar.pack(fill=tk.X, pady=(1, 0))

        plotno = tk.Canvas(zewn, highlightthickness=0)
        pasek = tk.Scrollbar(zewn, orient="vertical", command=plotno.yview)
        self.inner = tk.Frame(plotno)
        self.inner.bind("<Configure>",
                        lambda _e: plotno.configure(scrollregion=plotno.bbox("all")))
        okno_id = plotno.create_window((0, 0), window=self.inner, anchor="nw")
        plotno.bind("<Configure>", lambda e: plotno.itemconfig(okno_id, width=e.width))
        plotno.configure(yscrollcommand=pasek.set)
        plotno.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pasek.pack(side=tk.RIGHT, fill=tk.Y)

        # Kółko myszy tylko GDY KURSOR JEST NAD LISTĄ. bind_all podpinało je
        # globalnie i po zamknięciu okna uchwyt zostawał, próbując przewijać
        # nieistniejący canvas — TclError „invalid command name" przy każdym
        # ruchu kółka i wywalone okno główne.
        def _scroll(e):
            try:
                if plotno.winfo_exists():
                    plotno.yview_scroll(int(-1 * (e.delta / 120)), "units")
            except tk.TclError:
                pass
        def _podepnij(_e=None):
            plotno.bind_all("<MouseWheel>", _scroll)

        def _odepnij_ev(_e=None):
            plotno.unbind_all("<MouseWheel>")

        plotno.bind("<Enter>", _podepnij)
        plotno.bind("<Leave>", _odepnij_ev)
        # Także nad zawartością: kółko nad kartą pozycji ma przewijać listę,
        # a nie zostać złapane przez widget wewnątrz.
        self.inner.bind("<Enter>", _podepnij)
        # Sprzątanie przy zniszczeniu — user może zamknąć okno, nie zdejmując
        # wcześniej kursora z listy.
        plotno.bind("<Destroy>", _odepnij_ev)

        def _odepnij():
            try:
                plotno.unbind_all("<MouseWheel>")
            except tk.TclError:
                pass
        self._odepnij_scroll = _odepnij

        self.status = tk.Label(zewn, text="", anchor="w", font=("Arial", 8), fg="#555")
        self.status_warn = tk.Label(zewn, text="", anchor="w",
                                    font=("Arial", 9, "bold"), fg="#b3261e")
        return zewn

    def paski_stanu(self, rodzic):
        """Etykiety licznika i ostrzeżenia — do wstawienia gdzie indziej."""
        self.status = tk.Label(rodzic, text="", anchor="w", font=("Arial", 8), fg="#555")
        self.status_warn = tk.Label(rodzic, text="", anchor="w",
                                    font=("Arial", 9, "bold"), fg="#b3261e")
        return self.status, self.status_warn

    def start(self):
        """Buduje wiersze PO JEDNYM przez after().

        Szukanie plików na wolnym dysku sieciowym potrafi trwać, więc okno
        nie może zamarznąć — user widzi „szukam X/Y" i wie, ile zostało.
        """
        self._buduj_nastepny(0)

    def _buduj_nastepny(self, idx=0):
        try:
            if not self.rodzic.winfo_exists():
                return
        except Exception:
            return
        if idx >= len(self.pozycje):
            try:
                self._prog_frame.pack_forget()
            except Exception:
                pass
            self._zbudowane = True
            self._przelicz()
            # Szukanie plików trwa i okno potrafi w tym czasie zejść pod
            # arkusz (update_idletasks przy każdym wierszu). Na koniec
            # przywracamy je na wierzch — inaczej wygląda, jakby zniknęło.
            wroc = getattr(self.okno, "_na_wierzch", None)
            if callable(wroc):
                try:
                    self.okno.after(1, wroc)
                except Exception:
                    pass
            return
        self._prog_label.config(
            text=f"szukam plików… {idx + 1}/{len(self.pozycje)}   "
                 f"({self.pozycje[idx].get('drawing_no', '')})")
        try:
            self._prog_bar["value"] = idx + 1
        except Exception:
            pass
        self._buduj_jedna(self.pozycje[idx])
        self.rodzic.after(1, lambda: self._buduj_nastepny(idx + 1))

    def _buduj_jedna(self, it):
        # Elementy katalogowe (bez numeru rysunku) nie mają dokumentacji na
        # serwerze — nie ma sensu przeszukiwać dysku.
        it["files"] = [] if it.get("is_catalog") else list(self.szukaj_plikow(it["drawing_no"]) or [])

        box = tk.Frame(self.inner, bd=1, relief=tk.GROOVE, padx=8, pady=6)
        box.pack(fill=tk.X, pady=4, padx=4)

        naglowek = it["drawing_no"]
        if it.get("name") and it["name"] != it["drawing_no"]:
            naglowek += f" — {it['name']}"
        tk.Label(box, text=naglowek, font=("Arial", 10, "bold"),
                 anchor="w").pack(fill=tk.X)

        if self.pola_edycji:
            self._pola_edycji(box, it)

        ramka_plikow = tk.Frame(box)
        ramka_plikow.pack(fill=tk.X)
        it["files_frame"] = ramka_plikow

        it["add_manual_files"] = lambda sciezki, it=it: self._dodaj_reczne(it, sciezki)
        it["pick_manual_files"] = lambda it=it: self._wybierz_pliki(it)
        it["render_files"] = lambda it=it: self._rysuj_pliki(it)

        self._rysuj_pliki(it)
        try:
            self.rodzic.update_idletasks()
        except Exception:
            pass

    def _pola_edycji(self, box, it):
        """Ilość / materiał / uwagi — do poprawienia przed wysłaniem.

        Materiał bywa nieuzupełniony w BOM, a kooperant musi go znać do wyceny.
        """
        form = tk.Frame(box)
        form.pack(fill=tk.X, padx=12, pady=(4, 2))

        tk.Label(form, text="Ilość:", width=8, anchor="w").grid(row=0, column=0, sticky="w")
        qty = tk.StringVar(value=str(it.get("qty") or "1"))
        tk.Entry(form, textvariable=qty, width=8).grid(row=0, column=1, sticky="w")

        tk.Label(form, text="Materiał:", width=9, anchor="w").grid(
            row=0, column=2, sticky="w", padx=(12, 0))
        mat = tk.StringVar(value=it.get("material") or "")
        tk.Entry(form, textvariable=mat, width=22).grid(row=0, column=3, sticky="w")

        tk.Label(form, text="Uwagi:", width=8, anchor="w").grid(
            row=1, column=0, sticky="w", pady=(4, 0))
        uwagi = tk.StringVar(value=it.get("notes") or "")
        tk.Entry(form, textvariable=uwagi, width=58).grid(
            row=1, column=1, columnspan=3, sticky="w", pady=(4, 0))

        it["qty_var"], it["mat_var"], it["notes_var"] = qty, mat, uwagi

    # ── pliki ──────────────────────────────────────────────────────────────
    def _rysuj_pliki(self, it):
        ramka = it["files_frame"]
        for dziecko in ramka.winfo_children():
            dziecko.destroy()
        znalezione = it.get("files") or []

        if not znalezione:
            if it.get("is_catalog"):
                tk.Label(ramka, text="element katalogowy — bez rysunku, "
                                     "kooperant wycenia po nazwie",
                         fg="#777", anchor="w").pack(fill=tk.X, padx=12)
                return
            wiersz = tk.Frame(ramka)
            wiersz.pack(fill=tk.X, padx=12, pady=(2, 0))
            # Brak dostępu do serwera ≠ brak plików. Bez tego rozróżnienia
            # niezamapowany dysk wygląda jak „detal nie ma rysunków".
            blad = self.blad_serwera()
            if blad:
                tekst, kolor = f"⛔ BŁĄD ODCZYTU — {blad}; sprawdź dysk sieciowy", "#b3261e"
            elif self.needs_dxf(it["drawing_no"]):
                tekst, kolor = ("⛔ detal na laser (X/XX) — wymagany DXF, "
                                "bez niego nie wyślesz"), "#b3261e"
            else:
                tekst, kolor = ("⚠ nie znaleziono plików "
                                "(pozycja i tak zostanie wysłana)"), "#b3261e"
            tk.Label(wiersz, text=tekst, fg=kolor, anchor="w").pack(side=tk.LEFT)
            self._wiersz_akcji(ramka, it)
            return

        for f in znalezione:
            klucz = (it["drawing_no"], str(f))
            var = self.file_vars.get(klucz)
            if var is None:
                var = tk.BooleanVar(value=True)
                self.file_vars[klucz] = var
            wiersz_pliku = tk.Frame(ramka)
            wiersz_pliku.pack(fill=tk.X, padx=12)
            tk.Checkbutton(wiersz_pliku, text=f"{f.suffix.upper()[1:]:5} {f.name}",
                           variable=var, anchor="w", font=("Consolas", 9),
                           command=lambda it=it: self._rysuj_pliki(it)
                           ).pack(side=tk.LEFT)
            # Otwarcie pliku — inaczej nie da się sprawdzić, CZY to ten rysunek,
            # bez szukania go w Eksploratorze. Ikona zależy od typu, żeby po
            # rzucie oka widać było PDF-y wśród DXF-ów i STEP-ów.
            ikona = "📄" if f.suffix.lower() == ".pdf" else "📐"
            tk.Button(wiersz_pliku, text=ikona, font=("Arial", 7),
                      relief=tk.FLAT, cursor="hand2", padx=2, pady=0,
                      command=lambda p=f: self._otworz_plik(p)).pack(side=tk.LEFT, padx=(4, 0))

        # Detal na laser bez DXF-a — kooperant nie ma z czego ciąć. Liczymy
        # tylko ZAZNACZONE pliki: odznaczenie DXF-a to też błąd.
        if self.needs_dxf(it["drawing_no"]):
            ma_dxf = any(
                f.suffix.lower() == ".dxf"
                and self.file_vars.get((it["drawing_no"], str(f)))
                and self.file_vars[(it["drawing_no"], str(f))].get()
                for f in znalezione)
            if not ma_dxf:
                tk.Label(ramka, text="⛔ detal na laser (X/XX) — wymagany DXF, "
                                     "bez niego nie wyślesz",
                         fg="#b3261e", font=("Arial", 9, "bold"),
                         anchor="w").pack(fill=tk.X, padx=12, pady=(2, 0))

        self._wiersz_akcji(ramka, it)

    def _wiersz_akcji(self, rodzic, it):
        """[Szukaj dalej…] [⬇ przeciągnij tu plik] [Dodaj plik…]

        Razem, bo to trzy warianty tej samej czynności — „dorzuć dokumentację
        do TEJ pozycji". W osobnych wierszach zjadały tyle pionu, że przy
        kilkunastu pozycjach lista robiła się nieczytelna.

        „Dodaj plik…" jest ZAWSZE, bo drag & drop może być niedostępny (brak
        tkinterdnd2) — inaczej przy braku biblioteki funkcja znikałaby bez śladu.
        """
        wiersz = tk.Frame(rodzic)
        wiersz.pack(fill=tk.X, padx=12, pady=(3, 1))

        if self.szukaj_dalej:
            tk.Button(wiersz, text="Szukaj dalej…", font=("Arial", 8),
                      command=lambda it=it: self._szukaj_dalej(it)).pack(side=tk.LEFT)

        strefa = tk.Frame(wiersz, bd=1, relief=tk.RIDGE, bg="#f4f6f8")
        strefa.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        etykieta = tk.Label(strefa, bg="#f4f6f8", fg="#666", font=("Arial", 8),
                            text="⬇ przeciągnij tu plik z Eksploratora", anchor="center")
        etykieta.pack(fill=tk.X, pady=2)

        # UWAGA: wołamy przez it['pick_manual_files'], nie przez nazwę lokalną —
        # te funkcje powstają w pętli po pozycjach, więc domknięcie po nazwie
        # złapałoby OSTATNIĄ pozycję i pliki lądowałyby przy złym detalu.
        tk.Button(wiersz, text="Dodaj plik…", font=("Arial", 8),
                  command=lambda it=it: it["pick_manual_files"]()).pack(side=tk.LEFT)

        if self.register_drop:
            def _upuszczono(sciezki, it=it):
                it["add_manual_files"](sciezki)
            # Pasek I etykieta jako cel: user celuje w napis, nie w ramkę pod nim.
            ok = self.register_drop(strefa, _upuszczono)
            self.register_drop(etykieta, _upuszczono)
            if not ok:
                etykieta.config(text="(przeciąganie niedostępne — użyj „Dodaj plik…”)")
        else:
            etykieta.config(text="(przeciąganie niedostępne — użyj „Dodaj plik…”)")

    def _otworz_plik(self, sciezka):
        """Otwiera plik domyślnym programem — podgląd przed wysłaniem."""
        import os
        try:
            if not Path(sciezka).exists():
                messagebox.showwarning("Otwieranie",
                                       f"Plik już nie istnieje:\n{sciezka}",
                                       parent=self.okno)
                return
            os.startfile(str(sciezka))
        except Exception as e:
            messagebox.showerror("Otwieranie", f"Nie udało się otworzyć:\n{e}",
                                 parent=self.okno)

    def brakujace_numery(self):
        """Numery pozycji, dla których nie ma jeszcze żadnego pliku."""
        return [it["drawing_no"] for it in self.pozycje
                if it.get("drawing_no") and not it.get("files")]

    def szukaj_wszystkich(self, zrodlo="library"):
        """
        Jedno przejście po wybranym dysku dla WSZYSTKICH pozycji bez plików.

        Pozycja po pozycji oznaczałaby tyle skanów wolnego dysku sieciowego,
        ile brakujących rysunków — stąd jedno wspólne przeszukanie.

        `zrodlo`: "library" (dysk B:) albo "server" (dysk V:).
        """
        if not self.szukaj_hurtem:
            return
        brakujace = self.brakujace_numery()
        if not brakujace:
            messagebox.showinfo("Szukanie",
                                "Wszystkie pozycje mają już pliki.",
                                parent=self.okno)
            return

        gdzie = "bibliotece" if zrodlo == "library" else "serwerze"
        znalezione = self.szukaj_hurtem(brakujace, zrodlo) or {}
        if not znalezione:
            messagebox.showinfo(
                "Szukanie",
                f"Nie znaleziono plików na {gdzie} dla żadnej "
                f"z {len(brakujace)} pozycji.", parent=self.okno)
            return

        # sprawdzaj_ext=False — z biblioteki bierzemy to, co znalazł skan;
        # filtr rozszerzeń zadziałał już przy przeszukiwaniu.
        ile = 0
        for it in self.pozycje:
            pliki = znalezione.get(it.get("drawing_no"))
            if pliki:
                self._dodaj_reczne(it, pliki, sprawdzaj_ext=False)
                ile += 1
        messagebox.showinfo(
            "Szukanie",
            f"Znaleziono pliki dla {ile} z {len(brakujace)} pozycji.",
            parent=self.okno)
        # Skan całego dysku trwa najdłużej — okno wysyłki wraca na wierzch
        # razem z komunikatem, żeby nie zostało pod arkuszem.
        wroc = getattr(self.okno, "_na_wierzch", None)
        if callable(wroc):
            wroc()

    def _szukaj_dalej(self, it):
        nowe = self.szukaj_dalej(it) or []
        if not nowe:
            messagebox.showinfo("Szukanie",
                                f"Nie znaleziono plików dla:\n{it['drawing_no']}",
                                parent=self.okno)
            return
        self._dodaj_reczne(it, nowe, sprawdzaj_ext=False)

    def _wybierz_pliki(self, it):
        wybrane = filedialog.askopenfilenames(
            parent=self.okno, title=f"Dodaj pliki do {it['drawing_no']}",
            filetypes=[("Dokumentacja",
                        " ".join(f"*.{e}" for e in sorted(self.dozwolone_ext))),
                       ("Wszystkie pliki", "*.*")])
        self._dodaj_reczne(it, [Path(p) for p in wybrane])

    def _dodaj_reczne(self, it, sciezki, sprawdzaj_ext=True):
        """Dorzucenie plików ręcznie (drag & drop, przycisk albo inne źródło).

        Awaryjna furtka na wypadek, gdy automat nie trafi: rysunek leży poza
        strukturą projektu, ma inną nazwę niż numer, albo potrzebne jest coś
        spoza standardowych rozszerzeń.
        """
        sciezki = [Path(p) for p in (sciezki or [])]
        if not sciezki:
            return
        if sprawdzaj_ext:
            # Odsiew rozszerzeń, których odbiorca nie przyjmie — inaczej user
            # dodaje plik, wysyła i nikt nie zauważa, że nie dotarł.
            odrzucone = [p for p in sciezki
                         if p.suffix.lstrip(".").lower() not in self.dozwolone_ext]
            sciezki = [p for p in sciezki if p not in odrzucone]
            if odrzucone:
                messagebox.showwarning(
                    "Nieobsługiwany format",
                    "Przyjmowane są tylko: "
                    + ", ".join(sorted(self.dozwolone_ext)).upper()
                    + ".\n\nPominięto:\n"
                    + "\n".join(f"  • {p.name}" for p in odrzucone),
                    parent=self.okno)
        if not sciezki:
            return

        istniejace = it.get("files") or []
        # Dedup po NAZWIE, nie po ścieżce: „Szukaj dalej…" trafia zwykle w tę
        # samą kopię rysunku, którą automat znalazł w innym katalogu — dwie
        # ścieżki, jeden plik. Ręcznie wskazanego pliku (przycisk, drag&drop)
        # nie odsiewamy, bo user wie, co dokłada.
        znane = {Path(f).name.lower() for f in istniejace}
        dodane = []
        for p in sciezki:
            if p in istniejace:
                continue
            if not sprawdzaj_ext and p.name.lower() in znane:
                continue                    # ta sama nazwa z innego katalogu
            istniejace.append(p)
            znane.add(p.name.lower())
            dodane.append(p)
        it["files"] = istniejace
        if dodane:
            # Nowe pliki zaznaczamy do wysyłki — user dodał je świadomie,
            # więc domyślne odznaczenie byłoby pułapką.
            for p in dodane:
                self.file_vars.setdefault((it["drawing_no"], str(p)),
                                          tk.BooleanVar(value=True))
            self._rysuj_pliki(it)
            self._przelicz()

    # ── podsumowanie ───────────────────────────────────────────────────────
    def _przelicz(self):
        razem = sum(len(it.get("files") or []) for it in self.pozycje)
        # Pozycje bez plików — POMIJAMY katalogowe (łożysko, siłownik itd.),
        # bo one z założenia nie mają dokumentacji rysunkowej, więc brak
        # plików to dla nich norma, nie problem.
        z_dok = [it for it in self.pozycje if not it.get("is_catalog")]
        puste = [it for it in z_dok if not (it.get("files") or [])]
        znaleziono_dla = len(z_dok) - len(puste)
        try:
            self.status.config(
                text=f"Znaleziono {razem} plików dla {znaleziono_dla}/{len(z_dok)} pozycji.")
            self.status_warn.config(
                text=f"⚠ brak plików dla {len(puste)} pozycji!" if puste else "")
        except Exception:
            pass
        if self.on_zmiana:
            self.on_zmiana()

    # ── wynik ──────────────────────────────────────────────────────────────
    def zaznaczone_pliki(self):
        """[(pozycja, [Path…])] — tylko zaznaczone checkboxami."""
        wynik = []
        for it in self.pozycje:
            pliki = [f for f in (it.get("files") or [])
                     if self.file_vars.get((it["drawing_no"], str(f)))
                     and self.file_vars[(it["drawing_no"], str(f))].get()]
            wynik.append((it, pliki))
        return wynik

    def wszystkie_zaznaczone(self):
        """Płaska lista zaznaczonych plików, bez duplikatów."""
        widziane, out = set(), []
        for _it, pliki in self.zaznaczone_pliki():
            for p in pliki:
                if str(p) not in widziane:
                    widziane.add(str(p))
                    out.append(p)
        return out

    def brakujace_dxf(self):
        """Pozycje na laser bez zaznaczonego DXF-a — blokada wysyłki."""
        braki = []
        for it, pliki in self.zaznaczone_pliki():
            if not self.needs_dxf(it["drawing_no"]):
                continue
            if not any(p.suffix.lower() == ".dxf" for p in pliki):
                braki.append(it["drawing_no"])
        return braki

    def sprzataj(self):
        """Odepnij globalne bindy (kółko myszy) przy zamykaniu okna."""
        try:
            self._odepnij_scroll()
        except Exception:
            pass
