# -*- coding: utf-8 -*-
"""
Formularz ZK (zamówienie od klienta) wystawiany z Edytora kartotek.

TYLKO NOWE ZK
─────────────
Dopisywanie pozycji do istniejącego zamówienia robi się w arkuszu RM_BAZA
(zapis projektu do Subiekta, tryb mostu „projekt") — decyzja użytkownika
z 10.09.2026. Dlatego z §7 specyfikacji zostaje 7.1, a 7.2 odpada: dublowanie
sprawdzonej ścieżki tylko rozjechałoby dwie implementacje.

JEDEN PROJEKT = JEDNO ZK
────────────────────────
Numer projektu w polu Uwagi jest KLUCZEM, po którym most odnajduje zamówienie
(`Projekt.ZnajdzZkProjektu`). Gdy dla wpisanego numeru ZK już istnieje, most
odmawia utworzenia drugiego, a formularz mówi wprost, gdzie iść — dwa ZK na
jeden projekt rozbijają zapotrzebowanie na dwa dokumenty i ZD przestaje
widzieć całość.

Cena
────
Opcjonalna. ZK bez cen jest poprawne — cenę i tak ustala się przy fakturze.
Kolumna jest edytowalna, bo przy ofercie dla klienta bywa znana od razu.
"""

import datetime
import tkinter as tk
from tkinter import ttk, messagebox

from subiekt_dokument_form import (OknoDokumentu, TLO, TLO_SEKCJI, TEKST,
                                   TEKST_SZARY, OK_ZIELONY, BLAD_CZERWONY,
                                   UWAGA_ZOLTY)


class OknoZK(OknoDokumentu):
    TYTUL = "DOKUMENT ZK"
    PRZYCISK = "UTWÓRZ ZK"
    KOLOR_PRZYCISKU = "#2471a3"
    ROZMIAR = "1040x700"
    PODPOWIEDZ = ("Dwuklik na ilości lub cenie = zmiana   ·   spacja = przełącz ✓   ·   "
                  "jeden projekt = jedno ZK")

    def buduj_naglowek(self, rodzic):
        siatka = tk.Frame(rodzic, bg=TLO_SEKCJI)
        siatka.pack(fill=tk.X, padx=10, pady=8)

        tk.Label(siatka, text="Klient:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9), anchor="w", width=10).grid(row=0, column=0, sticky="w")
        # RMPAK domyślnie i ZAWSZE NA WIERZCHU listy (10.09.2026).
        #
        # ZK z RM_BAZA służy ZAPOTRZEBOWANIU, nie sprzedaży: dokument istnieje
        # po to, żeby Subiekt policzył, czego brakuje, i żeby dało się z tego
        # zrobić ZD do dostawców. Klient końcowy nie ma z tym nic wspólnego —
        # dlatego zapis projektu z arkusza wpisuje „RMPAK" na sztywno
        # (subiekt_projekt.py, var_podmiot). To okno musi być z tym spójne,
        # inaczej powstałyby ZK, których reszta systemu nie rozpozna jako
        # własnych. Innego klienta da się wybrać z listy — stąd combobox,
        # a nie pole tylko do odczytu.
        klienci = list(self.kontekst.get("klienci") or [])
        wlasna = self._nazwa_wlasnej_firmy(klienci, self.kontekst.get("nipy"))
        if wlasna:
            klienci = [wlasna] + [k for k in klienci if k != wlasna]
        self.var_klient = tk.StringVar(
            value=self.kontekst.get("klient") or wlasna or "")
        ttk.Combobox(siatka, textvariable=self.var_klient, width=34, font=("Arial", 9),
                     values=klienci).grid(row=0, column=1, sticky="w", padx=(0, 24))

        tk.Label(siatka, text="Termin:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9), anchor="w", width=8).grid(row=0, column=2, sticky="w")
        self.var_termin = tk.StringVar(value="")
        tk.Entry(siatka, textvariable=self.var_termin, font=("Arial", 9),
                 width=14).grid(row=0, column=3, sticky="w")
        tk.Label(siatka, text="(RRRR-MM-DD — można zostawić puste)",
                 bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8)).grid(
            row=0, column=4, sticky="w", padx=(6, 0))

        tk.Label(siatka, text="Projekt:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9), anchor="w", width=10).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.var_projekt = tk.StringVar(value=self.kontekst.get("projekt", ""))
        tk.Entry(siatka, textvariable=self.var_projekt, font=("Arial", 9),
                 width=16).grid(row=1, column=1, sticky="w", pady=(8, 0))

        tk.Label(siatka, text="Uwagi:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9), anchor="w", width=10).grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.var_uwagi = tk.StringVar(value=self.kontekst.get("uwagi", ""))
        tk.Entry(siatka, textvariable=self.var_uwagi, font=("Arial", 9)).grid(
            row=2, column=1, columnspan=4, sticky="we", pady=(8, 0))
        siatka.grid_columnconfigure(4, weight=1)

        tk.Label(rodzic,
                 text="Projekt i uwagi → pole „Uwagi” (numer w pierwszym wierszu — "
                      "po nim Subiekt odnajduje ZK — uwagi pod nim).",
                 bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8), anchor="w").pack(
            fill=tk.X, padx=12, pady=(0, 4))

        # Ostrzeżenie o regule „jeden projekt = jedno ZK" — widoczne od razu,
        # zanim user zdąży wpisać numer, który koliduje.
        tk.Label(rodzic,
                 text="⚠ Jeden projekt = jedno ZK. Jeśli zamówienie dla tego numeru "
                      "już istnieje, dopisz pozycje przez arkusz RM_BAZA "
                      "(zapis projektu do Subiekta).",
                 bg="#fcf3cf", fg=UWAGA_ZOLTY, font=("Arial", 8),
                 anchor="w", justify="left").pack(fill=tk.X, padx=12, pady=(0, 8))

    #: NIP spółki RMPAK — to NA NIĄ idą ZK z RM_BAZA (zapotrzebowanie własne).
    #:
    #: Po NIP, nie po nazwie: w Subiekcie są DWA podmioty zaczynające się od
    #: „RMPAK" — spółka (1231452843) i jednoosobowa działalność „RMPAK Grzegorz
    #: Kłoczko" (5381617408), czyli zupełnie inny podmiot. Dopasowanie po
    #: fragmencie nazwy brało pierwszy z brzegu, więc o wybór decydowała
    #: kolejność zwracana przez Sferę — przypadek (10.09.2026).
    NIP_WLASNY = "1231452843"

    #: Zapasowe dopasowanie, gdy lista nie niesie NIP-ów: pełna nazwa spółki.
    #: „RMPAK" bez dopisku NIE wystarcza — patrz wyżej.
    NAZWA_WLASNA = "RMPAK SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ"

    @classmethod
    def _nazwa_wlasnej_firmy(cls, klienci, nipy=None):
        """Nazwa spółki RMPAK z listy kontrahentów — albo "" gdy jej nie ma.

        `nipy` to {nazwa: NIP} z Subiekta; gdy jest, rozstrzyga NIP.
        Bez niego szukamy pełnej nazwy spółki, a NIGDY samego „RMPAK",
        bo pod tym prefiksem siedzi też inna firma.
        """
        if nipy:
            czysty = cls.NIP_WLASNY.replace("-", "")
            for nazwa, nip in nipy.items():
                if (nip or "").replace("-", "").strip() == czysty:
                    return nazwa
        for k in klienci:
            if k.strip().upper() == cls.NAZWA_WLASNA:
                return k
        for k in klienci:
            if k.strip().upper().startswith("RMPAK SP"):
                return k
        return ""

    def kolumny(self):
        return [("cena", "Cena", 90, True),
                ("wartosc", "Wartość", 100, False)]

    def waliduj_naglowek(self):
        bledy = []
        if not self.var_klient.get().strip():
            bledy.append("wskaż klienta — bez niego Subiekt nie utworzy zamówienia")
        termin = self.var_termin.get().strip()
        if termin and self._termin_iso() is None:
            bledy.append(f"termin „{termin}” — użyj formatu RRRR-MM-DD")
        return bledy

    def _termin_iso(self):
        """Termin jako RRRR-MM-DD albo None (pusty lub nieczytelny).

        RRRR-MM-DD to format obowiązujący w całym RM_BAZA: tak arkusz zapisuje
        termin dostawy i tego formatu żąda okno wysyłki ZD
        (subiekt_wyslij_zd.py). Pozostałe wzorce przyjmujemy z uprzejmości —
        gdy ktoś wpisze datę po polsku, nie odbijamy jej komunikatem, tylko
        rozumiemy. Kolejność ma znaczenie: format kanoniczny sprawdzamy
        pierwszy.
        """
        tekst = self.var_termin.get().strip()
        if not tekst:
            return None
        for wzor in ("%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                return datetime.datetime.strptime(tekst, wzor).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def _przelicz_wartosci(self):
        tabela = getattr(self, "tabela", None)
        if tabela is None:
            return
        for p in tabela.pozycje:
            cena = p.get("cena")
            p["wartosc"] = (round(float(p["ilosc"]) * float(cena), 2)
                            if cena else None)

    def _na_zmiane_tabeli(self):
        tabela = getattr(self, "tabela", None)
        if tabela is not None and tabela._przed_rysowaniem is None:
            tabela._przed_rysowaniem = self._przelicz_wartosci
            tabela.odswiez()
        self._przelicz_wartosci()
        super()._na_zmiane_tabeli()

    def _plan_dokumentu(self, pozycje):
        # "uwagi" to treść, którą user wpisał w polu Uwagi — most skleja ją
        # z numerem projektu (numer w pierwszym wierszu, uwagi pod nim)
        # i osobno ustawia Tytuł na znacznik RM_BAZA. Patrz Znacznik.cs.
        plan = {
            "projekt": self.var_projekt.get().strip(),
            "podmiot": self.var_klient.get().strip(),
            "uwagi": self.var_uwagi.get().strip(),
            "pozycje": [],
        }
        termin = self._termin_iso()
        if termin:
            plan["termin"] = termin
        for p in pozycje:
            wpis = {"symbol": p["symbol"], "ilosc": float(p["ilosc"])}
            if p.get("cena"):
                wpis["cena"] = float(p["cena"])
            plan["pozycje"].append(wpis)
        return plan

    def sprawdz(self, pozycje):
        import subiekt_zamowienia
        return subiekt_zamowienia.utworz_zk(self._plan_dokumentu(pozycje), zapisz=False)

    def wystaw(self, pozycje):
        import subiekt_zamowienia
        return subiekt_zamowienia.utworz_zk(self._plan_dokumentu(pozycje), zapisz=True)

    # ── reakcje na wynik ────────────────────────────────────────────────

    def po_sprawdzeniu(self, wynik):
        kroki = (wynik or {}).get("kroki") or []
        bledy = [k for k in kroki if k.get("Status") == "blad"]
        for k in bledy:
            if str(k.get("Rodzaj")) == "pozycja":
                self.tabela.ustaw_uwage(k.get("Symbol"), str(k.get("Szczegoly") or "błąd"))

        if bledy:
            opis = "\n".join(f"• {k.get('Szczegoly')}" for k in bledy[:8])
            messagebox.showerror("ZK — sprawdzenie wykryło problemy",
                                 f"Zamówienie NIE powstało.\n\n{opis}", parent=self)
            self.lbl_status.config(text="Sprawdzenie zgłosiło błędy — popraw dane",
                                   fg=BLAD_CZERWONY)
            return False

        uzyte = self.tabela.uzyte()
        razem = sum(float(p.get("wartosc") or 0) for p in uzyte)
        bez_ceny = sum(1 for p in uzyte if not p.get("cena"))
        opis = f"Sprawdzone — {len(uzyte)} pozycji"
        if razem:
            opis += f", wartość {razem:,.2f} zł".replace(",", " ")
        if bez_ceny:
            opis += f"   ·   {bez_ceny} bez ceny (ZK bez cen jest poprawne)"
        self.lbl_status.config(text=opis, fg=OK_ZIELONY)
        return True

    def po_wystawieniu(self, wynik):
        numer = (wynik or {}).get("numer")
        bledy = [k for k in (wynik or {}).get("kroki", []) if k.get("Status") == "blad"]
        if bledy and not numer:
            messagebox.showerror(
                "ZK", "Subiekt odrzucił zamówienie:\n\n"
                + "\n".join(f"• {k.get('Szczegoly')}" for k in bledy[:8]), parent=self)
            return
        uzyte = self.tabela.uzyte()
        razem = sum(float(p.get("wartosc") or 0) for p in uzyte)
        messagebox.showinfo(
            "ZK utworzone",
            f"✅ {numer or 'Zamówienie utworzone'}\n\n"
            f"Klient: {self.var_klient.get().strip()}\n"
            f"Pozycji: {len(uzyte)}\n"
            + (f"Wartość: {razem:,.2f} zł\n".replace(",", " ") if razem else "")
            + (f"Uwagi (projekt): {self.var_projekt.get().strip()}\n"
               if self.var_projekt.get().strip() else "")
            + "\nPozycje dopiszesz później przez arkusz RM_BAZA.", parent=self)
        odswiez = self.kontekst.get("po_zapisie")
        if odswiez:
            try:
                odswiez()
            except Exception:
                pass
        self.destroy()


def otworz(parent, pozycje, kontekst=None):
    """Otwiera formularz nowego ZK dla podanych pozycji."""
    if not pozycje:
        messagebox.showinfo("ZK", "Drzewo jest puste — nie ma czego zamawiać.",
                            parent=parent)
        return None
    return OknoZK(parent, pozycje, kontekst)
