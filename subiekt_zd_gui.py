# -*- coding: utf-8 -*-
"""
Formularz ZD (zamówienia do dostawców) wystawiany z Edytora kartotek.

Inaczej niż RW i PW: jeden formularz tworzy KILKA dokumentów naraz
(SUBIEKT_FORMULARZE_DOKUMENTOW.md §6). Pozycje zebrane w drzewie mają różnych
dostawców, a Subiekt wystawia osobne ZD dla każdego z nich — więc formularz
grupuje po dostawcy i mówi wprost, ile dokumentów powstanie.

Dostawca jest tu polem OBOWIĄZKOWYM — bez niego nie ma na czym oprzeć
dokumentu. Podpowiadamy go z ostatniego zamówienia tej kartoteki, resztę
wpisuje człowiek.

Cena
────
ZD NIESIE CENĘ ZAKUPU (korekta wcześniejszego ustalenia, 10.09.2026):
na zamówieniu do dostawcy cena jest naturalna — z niej bierze się wartość
zamówienia, którą trzeba znać przed wysłaniem. Kolumna jest edytowalna,
a program podpowiada OSTATNIĄ CENĘ ZAKUPU z Subiekta (tryb „stan",
`OstatniaCenaZakupu` — cena z ostatniej faktury zakupu tej kartoteki).

Cena pozostaje OPCJONALNA: ZD z ceną 0 jest poprawne, gdy dostawca ma ją
dopiero podać. Formularz nie blokuje, tylko pokazuje, ile pozycji jej nie ma.

Obsługa po stronie mostu dołożona razem z tym formularzem — `Zd.cs` dotąd
pól cenowych nie miał (wzorzec ustawiania ceny jak w Pw.cs: `PozycjaDokumentu.Cena`
to obiekt, nie liczba, i liczy się `NettoPoRabacie`).

Tryb ręczny
───────────
Pozycje idą do mostu z `reczna: true`. Zwykłe ZD w RM_BAZA powstają
z ZAPOTRZEBOWANIA z ZK (`UtworzNaPodstawieZapotrzebowania` — bez tego Subiekt
uważa zamówienie klienta za niezrealizowane). Tutaj zamawiamy rzeczy, których
na żadnym ZK nie ma, więc most tworzy dokument wprost i dopisuje pozycje —
ta ścieżka jest w `Zd.cs` od początku, obsługiwana obok zapotrzebowania.
"""

import datetime
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from subiekt_dokument_form import (OknoDokumentu, TLO, TLO_SEKCJI, TEKST,
                                   TEKST_SZARY, OK_ZIELONY, BLAD_CZERWONY,
                                   UWAGA_ZOLTY)


class OknoZD(OknoDokumentu):
    TYTUL = "DOKUMENT ZD"
    PRZYCISK = "UTWÓRZ ZD"
    KOLOR_PRZYCISKU = "#8e44ad"
    ROZMIAR = "1200x700"
    PODPOWIEDZ = ("Dwuklik na ilości, dostawcy lub cenie = zmiana   ·   "
                  "spacja = przełącz ✓   ·   jedno ZD na dostawcę")

    def buduj_naglowek(self, rodzic):
        siatka = tk.Frame(rodzic, bg=TLO_SEKCJI)
        siatka.pack(fill=tk.X, padx=10, pady=8)

        tk.Label(siatka, text="Projekt:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9), anchor="w", width=10).grid(row=0, column=0, sticky="w")
        self.var_projekt = tk.StringVar(value=self.kontekst.get("projekt", ""))
        tk.Entry(siatka, textvariable=self.var_projekt, font=("Arial", 9),
                 width=16).grid(row=0, column=1, sticky="w", padx=(0, 30))

        tk.Label(siatka, text="Data:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9), anchor="w", width=8).grid(row=0, column=2, sticky="w")
        self.var_data = tk.StringVar(value=datetime.date.today().strftime("%d.%m.%Y"))
        tk.Entry(siatka, textvariable=self.var_data, font=("Arial", 9),
                 width=14, state="readonly").grid(row=0, column=3, sticky="w")

        tk.Label(siatka, text="Opis:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9), anchor="w", width=10).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.var_uwagi = tk.StringVar(value=self.kontekst.get("uwagi", ""))
        tk.Entry(siatka, textvariable=self.var_uwagi, font=("Arial", 9)).grid(
            row=1, column=1, columnspan=3, sticky="we", pady=(8, 0))
        siatka.grid_columnconfigure(3, weight=1)

        tk.Label(rodzic,
                 text="Projekt → pole „Uwagi” każdego ZD (sam numer).    "
                      "Ceny nie podajemy — ustala się ją przy przyjęciu towaru.",
                 bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8), anchor="w").pack(
            fill=tk.X, padx=12, pady=(0, 4))

        # Dostawca hurtem — przy zamówieniu do jednej firmy nie ma sensu
        # wpisywać go do każdego wiersza z osobna.
        pas = tk.Frame(rodzic, bg=TLO_SEKCJI)
        pas.pack(fill=tk.X, padx=12, pady=(0, 6))
        tk.Label(pas, text="Ustaw dostawcę podświetlonym wierszom "
                           "(nic nie podświetlone = wszystkim ✓):",
                 bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 8)).pack(side=tk.LEFT)
        self.var_dostawca_hurtem = tk.StringVar()
        self.cb_dostawca = ttk.Combobox(
            pas, textvariable=self.var_dostawca_hurtem, width=32, font=("Arial", 9),
            values=self.kontekst.get("dostawcy") or [])
        self.cb_dostawca.pack(side=tk.LEFT, padx=6)
        tk.Button(pas, text="Zastosuj", font=("Arial", 8),
                  command=self._dostawca_hurtem).pack(side=tk.LEFT)

        tk.Label(pas, text="   Cena:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 8)).pack(side=tk.LEFT)
        self.var_cena_hurtem = tk.StringVar()
        tk.Entry(pas, textvariable=self.var_cena_hurtem, width=10,
                 font=("Arial", 9), justify="right").pack(side=tk.LEFT, padx=4)
        tk.Button(pas, text="Zastosuj", font=("Arial", 8),
                  command=self._cena_hurtem).pack(side=tk.LEFT)

        # Podsumowanie „ile ZD powstanie" — najważniejsza liczba tego okna,
        # bo jeden formularz tworzy kilka dokumentów.
        self.lbl_grupy = tk.Label(rodzic, text="", bg=TLO_SEKCJI, fg=TEKST,
                                  font=("Arial", 9), anchor="w", justify="left")
        self.lbl_grupy.pack(fill=tk.X, padx=12, pady=(0, 8))

    def _dostawca_hurtem(self):
        nazwa = self.var_dostawca_hurtem.get().strip()
        if not nazwa:
            return
        # PODŚWIETLONE w tabeli, nie wszystkie z ✓ — patrz TabelaPozycji.
        cele = self.tabela.podswietlone()
        for p in cele:
            p["dostawca"] = nazwa
        self.tabela.odswiez()
        self.lbl_status.config(
            text=f"Dostawca „{nazwa}” ustawiony dla {len(cele)} pozycji",
            fg=TEKST_SZARY)

    def _doczytaj_ceny(self):
        """Podpowiada OSTATNIĄ CENĘ ZAKUPU — w tle, tryb „stan" mostu.

        `OstatniaCenaZakupu` to cena z ostatniej faktury zakupu tej kartoteki
        (Stan.cs filtruje po dokumentach FZ). Dla wielu pozycji będzie pusta —
        kartoteka bez historii zakupu jej nie ma — i to jest w porządku:
        cenę wpisze człowiek. Podpowiedź NIE nadpisuje ceny już wpisanej.

        W tle, bo tryb „stan" pyta punktowo o każdy symbol; przy kilkunastu
        pozycjach to ułamek sekundy, ale nie ma powodu blokować otwarcia okna.
        """
        symbole = [p["symbol"] for p in self.tabela.pozycje if not p.get("cena")]
        if not symbole:
            return

        def worker():
            try:
                from subiekt_asortyment_gui import pobierz_stany
                wyniki = pobierz_stany(symbole)
            except Exception:
                wyniki = []
            self.after(0, lambda: gotowe(wyniki))

        def gotowe(wyniki):
            ceny = {}
            for r in wyniki or []:
                klucz = (r.get("Symbol") or r.get("Pytany") or "").strip().upper()
                cena = r.get("OstatniaCenaZakupu")
                if klucz and cena:
                    ceny[klucz] = float(cena)
            if not ceny:
                return
            ile = 0
            for p in self.tabela.pozycje:
                if not p.get("cena") and p["symbol"].upper() in ceny:
                    p["cena"] = ceny[p["symbol"].upper()]
                    ile += 1
            if ile:
                self._przelicz_wartosci()
                self.tabela.odswiez()
                self.lbl_status.config(
                    text=f"Podpowiedziano ostatnią cenę zakupu dla {ile} pozycji "
                         "— sprawdź i popraw, jeśli trzeba", fg=TEKST_SZARY)

        threading.Thread(target=worker, daemon=True).start()

    def _cena_hurtem(self):
        tekst = self.var_cena_hurtem.get().strip().replace(",", ".")
        if not tekst:
            return
        try:
            cena = float(tekst)
        except ValueError:
            messagebox.showwarning("Cena", f"„{self.var_cena_hurtem.get()}” to nie liczba.",
                                   parent=self)
            return
        if cena < 0:
            messagebox.showwarning("Cena", "Cena nie może być ujemna.", parent=self)
            return
        cele = self.tabela.podswietlone()
        for p in cele:
            p["cena"] = cena
        self._przelicz_wartosci()
        self.tabela.odswiez()
        self.lbl_status.config(
            text=f"Cena {cena:g} ustawiona dla {len(cele)} pozycji", fg=TEKST_SZARY)

    def _przelicz_wartosci(self):
        """Wartość = ilość × cena. Liczona PRZED rysowaniem wierszy."""
        tabela = getattr(self, "tabela", None)
        if tabela is None:
            return
        for p in tabela.pozycje:
            cena = p.get("cena")
            p["wartosc"] = (round(float(p["ilosc"]) * float(cena), 2)
                            if cena else None)

    def kolumny(self):
        # Dostawca EDYTOWALNY — to po nim most grupuje dokumenty.
        # Cena EDYTOWALNA, Wartość liczona (ilość × cena).
        return [("dostawca", "Dostawca", 170, True),
                ("cena", "Cena netto", 90, True),
                ("wartosc", "Wartość", 100, False)]

    def waliduj_naglowek(self):
        bledy = []
        if not (self.var_projekt.get().strip() or self.var_uwagi.get().strip()):
            bledy.append("podaj numer projektu albo opis — bez tego nie da się "
                         "później ustalić, na co poszło zamówienie")
        brak = [p["symbol"] for p in (self.tabela.uzyte()
                                      if getattr(self, "tabela", None) else [])
                if not str(p.get("dostawca") or "").strip()]
        if brak:
            bledy.append("bez dostawcy: " + ", ".join(brak[:8])
                         + ("" if len(brak) <= 8 else f" … (+{len(brak) - 8})"))
        return bledy

    def _uwagi_dokumentu(self):
        """Pole Uwagi każdego ZD: WYŁĄCZNIE numer projektu."""
        return self.var_projekt.get().strip() or self.var_uwagi.get().strip()

    def _grupy(self):
        """{dostawca: [pozycje]} — tyle powstanie dokumentów.

        Tabela moze jeszcze nie istniec: TabelaPozycji wola `_na_zmiane` juz
        ze swojego __init__, a `self.tabela` powstaje dopiero po powrocie
        z konstruktora.
        """
        grupy = {}
        tabela = getattr(self, "tabela", None)
        if tabela is None:
            return grupy
        for p in tabela.uzyte():
            nazwa = str(p.get("dostawca") or "").strip()
            if nazwa:
                grupy.setdefault(nazwa, []).append(p)
        return grupy

    def _na_zmiane_tabeli(self):
        tabela = getattr(self, "tabela", None)
        if tabela is not None and tabela._przed_rysowaniem is None:
            tabela._przed_rysowaniem = self._przelicz_wartosci
            tabela.odswiez()
        self._przelicz_wartosci()
        super()._na_zmiane_tabeli()
        etykieta = getattr(self, "lbl_grupy", None)
        if etykieta is None:
            return
        grupy = self._grupy()
        if not grupy:
            etykieta.config(text="Dokumenty: —  (najpierw przypisz dostawców)",
                            fg=TEKST_SZARY)
            return
        # Wartość per dostawca — to ona idzie na konkretne zamówienie.
        opis = "   ".join(
            f"{d} — {len(poz)} poz." + (
                f" / {sum(float(p.get('wartosc') or 0) for p in poz):,.2f} zł".replace(",", " ")
                if any(p.get("wartosc") for p in poz) else "")
            for d, poz in sorted(grupy.items())[:5])
        wiecej = "" if len(grupy) <= 5 else f"   … i {len(grupy) - 5} więcej"
        razem = sum(float(p.get("wartosc") or 0) for p in self.tabela.uzyte())
        suma = f"   ·   RAZEM {razem:,.2f} zł netto".replace(",", " ") if razem else ""
        etykieta.config(
            text=f"POWSTANIE {len(grupy)} ZD:   {opis}{wiecej}{suma}", fg=TEKST)
        self.btn_wystaw.config(text=f"UTWÓRZ {len(grupy)} ZD"
                               if len(grupy) > 1 else "UTWÓRZ ZD")

    def _plan(self, pozycje):
        # `reczna: true` — pozycji nie ma w zapotrzebowaniu z ZK, więc most
        # tworzy dokument wprost zamiast realizować zestawienie.
        out = []
        for p in pozycje:
            wpis = {"symbol": p["symbol"], "ilosc": float(p["ilosc"]),
                    "dostawca": str(p.get("dostawca") or "").strip(),
                    "reczna": True}
            # Klucz "cena" leci tylko gdy podana — brak znaczy „dostawca poda".
            if p.get("cena"):
                wpis["cena"] = float(p["cena"])
            out.append(wpis)
        return out

    def sprawdz(self, pozycje):
        import subiekt_zamowienia
        return subiekt_zamowienia.utworz_zd(
            self._plan(pozycje), uwagi=self._uwagi_dokumentu(), zapisz=False)

    def wystaw(self, pozycje):
        import subiekt_zamowienia
        return subiekt_zamowienia.utworz_zd(
            self._plan(pozycje), uwagi=self._uwagi_dokumentu(), zapisz=True)

    # ── reakcje na wynik ────────────────────────────────────────────────

    def po_sprawdzeniu(self, wynik):
        kroki = (wynik or {}).get("kroki") or []
        bledy = [k for k in kroki if k.get("Status") == "blad"]
        for k in bledy:
            self.tabela.ustaw_uwage(k.get("Symbol"), str(k.get("Szczegoly") or "błąd"))

        if bledy:
            opis = "\n".join(f"• {k.get('Symbol') or '—'}: {k.get('Szczegoly')}"
                             for k in bledy[:12])
            messagebox.showerror(
                "ZD — sprawdzenie wykryło problemy",
                f"Dokumenty NIE powstały.\n\n{opis}"
                + ("\n…" if len(bledy) > 12 else ""), parent=self)
            self.lbl_status.config(text=f"Błędów: {len(bledy)} — popraw pozycje",
                                   fg=BLAD_CZERWONY)
            return False

        grupy = self._grupy()
        uzyte = self.tabela.uzyte()
        razem = sum(float(p.get("wartosc") or 0) for p in uzyte)
        bez_ceny = sum(1 for p in uzyte if not p.get("cena"))
        opis = f"Sprawdzone — powstanie {len(grupy)} ZD dla {len(uzyte)} pozycji"
        if razem:
            opis += f", razem {razem:,.2f} zł netto".replace(",", " ")
        if bez_ceny:
            opis += f"   ·   {bez_ceny} bez ceny"
        self.lbl_status.config(text=opis, fg=OK_ZIELONY)
        return True

    def po_wystawieniu(self, wynik):
        kroki = (wynik or {}).get("kroki") or []
        bledy = [k for k in kroki if k.get("Status") == "blad"]
        # Numery utworzonych dokumentów — most zwraca je w krokach rodzaju "zd".
        numery = [str(k.get("Szczegoly") or k.get("Symbol") or "")
                  for k in kroki if str(k.get("Rodzaj") or "") == "zd"
                  and k.get("Status") != "blad"]
        if bledy and not numery:
            messagebox.showerror(
                "ZD", "Subiekt odrzucił zamówienia:\n\n"
                + "\n".join(f"• {k.get('Symbol') or '—'}: {k.get('Szczegoly')}"
                            for k in bledy[:10]), parent=self)
            return
        lista = "\n".join(f"   • {n}" for n in numery[:12]) if numery else ""
        messagebox.showinfo(
            "ZD utworzone",
            f"✅ Powstało {len(numery) or len(self._grupy())} zamówień\n\n"
            + (lista + "\n\n" if lista else "")
            + f"Pozycji: {len(self.tabela.uzyte())}\n"
            + (f"Wartość: {sum(float(p.get('wartosc') or 0) for p in self.tabela.uzyte()):,.2f} zł netto\n".replace(",", " ")
               if any(p.get("wartosc") for p in self.tabela.uzyte()) else "")
            + f"Uwagi (projekt): {self._uwagi_dokumentu()}\n"
            + ("\n⚠ Część pozycji odpadła — sprawdź raport w Subiekcie."
               if bledy else ""), parent=self)
        odswiez = self.kontekst.get("po_zapisie")
        if odswiez:
            try:
                odswiez()
            except Exception:
                pass
        self.destroy()


def otworz(parent, pozycje, kontekst=None):
    """Otwiera formularz ZD dla podanych pozycji."""
    if not pozycje:
        messagebox.showinfo("ZD", "Drzewo jest puste — nie ma czego zamawiać.",
                            parent=parent)
        return None
    okno = OknoZD(parent, pozycje, kontekst)
    # Po zbudowaniu okna: podpowiedź cen z Subiekta (w tle).
    okno.after(100, okno._doczytaj_ceny)
    return okno
