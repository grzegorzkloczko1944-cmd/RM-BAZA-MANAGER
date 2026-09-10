# -*- coding: utf-8 -*-
"""
Formularz PW (przychód wewnętrzny) wystawiany z Edytora kartotek.

Jedno PW dla wielu pozycji naraz — źródłem są pozycje zaznaczone w drzewie
z sekcji 1 Edytora (SUBIEKT_FORMULARZE_DOKUMENTOW.md §5).

Czym różni się od istniejącej ścieżki PW
────────────────────────────────────────
`rmpak_calculator` wystawia PW produkcji własnej: ceny biorą się z Kalkulatora
RMPAK (koszt wytworzenia per detal), a dokument domyka proces PW → RW. Tutaj
jest PW RĘCZNE — przyjęcie na stan czegoś, co po prostu przyszło albo zostało
zrobione, z ceną wpisywaną przez człowieka.

Cena — inaczej niż w RW
───────────────────────
PW cenę MA i to ona ustala warstwę magazynową, z której Subiekt policzy potem
koszt rozchodu. Dlatego kolumna „Cena" jest edytowalna, a pusta cena to
świadoma decyzja użytkownika, nie niedopatrzenie — ale formularz o niej
ostrzega, bo pozycja przyjęta po 0 zł da później RW o zerowej wartości.
Dokładnie tak powstało 1183 z 1376 kartotek bez ceny (migracja magazynu nr 2,
patrz MAGAZYN.md) — i dokładnie dlatego RW ostrzega dziś o „bez wyceny".

Ceny domyślnej NIE PODPOWIADAMY: jedyne źródło w RM_BAZA (`items.price_pln`)
pokrywa ~31 % pozycji i jest kluczowane numerem rysunku, nie symbolem
kartoteki. Ustalenie z 10.09.2026: ceny uzupełnia się ręcznie w magazynie.
"""

import datetime
import tkinter as tk
from tkinter import ttk, messagebox

from subiekt_dokument_form import (OknoDokumentu, TLO, TLO_SEKCJI, TEKST,
                                   TEKST_SZARY, OK_ZIELONY, BLAD_CZERWONY,
                                   UWAGA_ZOLTY)

MAGAZYN_DOMYSLNY = "MASTER"


class OknoPW(OknoDokumentu):
    TYTUL = "DOKUMENT PW"
    PRZYCISK = "WYSTAW PW"
    KOLOR_PRZYCISKU = "#1e8449"
    PODPOWIEDZ = ("Dwuklik na ilości lub cenie = zmiana   ·   spacja = przełącz ✓   ·   "
                  "cena ustala warstwę magazynową")

    def buduj_naglowek(self, rodzic):
        siatka = tk.Frame(rodzic, bg=TLO_SEKCJI)
        siatka.pack(fill=tk.X, padx=10, pady=8)

        tk.Label(siatka, text="Magazyn:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9), anchor="w", width=10).grid(row=0, column=0, sticky="w")
        self.var_magazyn = tk.StringVar(value=self.kontekst.get("magazyn", MAGAZYN_DOMYSLNY))
        ttk.Combobox(siatka, textvariable=self.var_magazyn, width=18,
                     font=("Arial", 9), state="readonly",
                     values=self.kontekst.get("magazyny") or [MAGAZYN_DOMYSLNY]).grid(
            row=0, column=1, sticky="w", padx=(0, 30))

        tk.Label(siatka, text="Projekt:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9), anchor="w", width=8).grid(row=0, column=2, sticky="w")
        self.var_projekt = tk.StringVar(value=self.kontekst.get("projekt", ""))
        tk.Entry(siatka, textvariable=self.var_projekt, font=("Arial", 9),
                 width=16).grid(row=0, column=3, sticky="w")

        tk.Label(siatka, text="Data:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9), anchor="w", width=10).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.var_data = tk.StringVar(value=datetime.date.today().strftime("%d.%m.%Y"))
        tk.Entry(siatka, textvariable=self.var_data, font=("Arial", 9),
                 width=18, state="readonly").grid(row=1, column=1, sticky="w", pady=(8, 0))
        tk.Label(siatka, text="(dokument wystawia się z datą dzisiejszą)",
                 bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8)).grid(
            row=1, column=2, columnspan=2, sticky="w", pady=(8, 0))

        tk.Label(siatka, text="Opis:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9), anchor="w", width=10).grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.var_uwagi = tk.StringVar(value=self.kontekst.get("uwagi", ""))
        tk.Entry(siatka, textvariable=self.var_uwagi, font=("Arial", 9)).grid(
            row=2, column=1, columnspan=3, sticky="we", pady=(8, 0))
        siatka.grid_columnconfigure(3, weight=1)

        # Ta sama zasada co w RW: Uwagi = sam numer projektu (po nim filtruje
        # cała firma), opis osobnym polem Tytuł.
        tk.Label(rodzic,
                 text="Projekt → pole „Uwagi” dokumentu (sam numer).    "
                      "Opis → pole „Tytuł”.    "
                      "Cena ustala warstwę, z której Subiekt policzy koszt RW.",
                 bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8), anchor="w").pack(
            fill=tk.X, padx=12, pady=(0, 6))

        # Cena hurtem — przy kilkudziesięciu pozycjach wpisywanie jednej
        # wartości do każdej z osobna jest nie do zniesienia.
        pas = tk.Frame(rodzic, bg=TLO_SEKCJI)
        pas.pack(fill=tk.X, padx=12, pady=(0, 8))
        tk.Label(pas, text="Ustaw cenę podświetlonym wierszom "
                           "(nic nie podświetlone = wszystkim ✓):",
                 bg=TLO_SEKCJI, fg=TEKST, font=("Arial", 8)).pack(side=tk.LEFT)
        self.var_cena_hurtem = tk.StringVar()
        tk.Entry(pas, textvariable=self.var_cena_hurtem, width=10,
                 font=("Arial", 9), justify="right").pack(side=tk.LEFT, padx=6)
        tk.Button(pas, text="Zastosuj", font=("Arial", 8),
                  command=self._cena_hurtem).pack(side=tk.LEFT)

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
        # PODŚWIETLONE w tabeli, nie wszystkie z ✓ — patrz TabelaPozycji.
        cele = self.tabela.podswietlone()
        for p in cele:
            p["cena"] = cena
        self._przelicz_wartosci()
        self.tabela.odswiez()
        self.lbl_status.config(
            text=f"Cena {cena:g} ustawiona dla {len(cele)} pozycji", fg=TEKST_SZARY)

    def kolumny(self):
        # Cena EDYTOWALNA — to jedyna rzecz, której PW nie policzy samo,
        # a od niej zależy wartość warstwy magazynowej.
        return [("cena", "Cena", 90, True),
                ("wartosc", "Wartość", 100, False)]

    def waliduj_naglowek(self):
        bledy = []
        if not (self.var_projekt.get().strip() or self.var_uwagi.get().strip()):
            bledy.append("podaj numer projektu albo opis — bez tego nie da się "
                         "później ustalić, skąd wziął się stan")
        for p in self.tabela.uzyte():
            cena = p.get("cena")
            if cena is not None and float(cena) < 0:
                bledy.append(f"{p['symbol']}: cena ujemna ({float(cena):g})")
        return bledy

    def _uwagi_dokumentu(self):
        """Pole Uwagi: WYŁĄCZNIE numer projektu."""
        return self.var_projekt.get().strip() or self.var_uwagi.get().strip()

    def _tytul_dokumentu(self):
        """Pole Tytuł: opis. Puste, gdy opis poszedł już do Uwag."""
        opis = self.var_uwagi.get().strip()
        return opis if self.var_projekt.get().strip() else ""

    def _plan(self, pozycje):
        out = []
        for p in pozycje:
            wpis = {"symbol": p["symbol"], "ilosc": float(p["ilosc"])}
            # Klucz "cena" leci tylko gdy podana: most traktuje jej brak jako
            # przyjęcie po 0 zł, a jawne 0 znaczy to samo — ale bez klucza
            # widać w planie, że nikt ceny nie ustalał.
            if p.get("cena"):
                wpis["cena"] = float(p["cena"])
            out.append(wpis)
        return out

    def sprawdz(self, pozycje):
        import subiekt_produkcja
        return subiekt_produkcja.wyslij_pw(self._plan_dokumentu(pozycje), zapisz=False)

    def wystaw(self, pozycje):
        import subiekt_produkcja
        return subiekt_produkcja.wyslij_pw(self._plan_dokumentu(pozycje), zapisz=True)

    def _plan_dokumentu(self, pozycje):
        plan = {"pozycje": self._plan(pozycje),
                "uwagi": self._uwagi_dokumentu(),
                "magazyn": self.var_magazyn.get()}
        tytul = self._tytul_dokumentu()
        if tytul:
            plan["tytul"] = tytul
        return plan

    # ── reakcje na wynik ────────────────────────────────────────────────

    def _przelicz_wartosci(self):
        """Wartość = ilość × cena. Liczona PRZED rysowaniem wierszy.

        `TabelaPozycji.odswiez()` woła `_na_zmiane` dopiero PO zbudowaniu
        komórek, więc liczenie tam pokazywałoby wartość spóźnioną o jedno
        odświeżenie (cena wpisana — kolumna nadal pusta).
        """
        tabela = getattr(self, "tabela", None)
        if tabela is None:
            return
        for p in tabela.pozycje:
            cena = p.get("cena")
            p["wartosc"] = (round(float(p["ilosc"]) * float(cena), 2)
                            if cena else None)

    def _na_zmiane_tabeli(self):
        # Podpinamy hak przy pierwszym wywołaniu — tabela istnieje dopiero
        # po powrocie z jej konstruktora, a ten woła nas jeszcze w trakcie.
        tabela = getattr(self, "tabela", None)
        if tabela is not None and tabela._przed_rysowaniem is None:
            tabela._przed_rysowaniem = self._przelicz_wartosci
            tabela.odswiez()          # pierwsze rysowanie bylo bez wartosci
        self._przelicz_wartosci()
        super()._na_zmiane_tabeli()

    def po_sprawdzeniu(self, wynik):
        kroki = (wynik or {}).get("kroki") or []
        bledy = [k for k in kroki if k.get("Status") == "blad"]
        for k in bledy:
            self.tabela.ustaw_uwage(k.get("Symbol"), str(k.get("Szczegoly") or "błąd"))

        if bledy:
            opis = "\n".join(f"• {k.get('Symbol') or '—'}: {k.get('Szczegoly')}"
                             for k in bledy[:12])
            messagebox.showerror(
                "PW — sprawdzenie wykryło problemy",
                f"Dokument NIE powstał.\n\n{opis}"
                + ("\n…" if len(bledy) > 12 else ""), parent=self)
            self.lbl_status.config(text=f"Błędów: {len(bledy)} — popraw pozycje",
                                   fg=BLAD_CZERWONY)
            return False

        uzyte = self.tabela.uzyte()
        bez_ceny = [p for p in uzyte if not p.get("cena")]
        razem = sum(float(p.get("wartosc") or 0) for p in uzyte)

        if bez_ceny:
            for p in bez_ceny:
                self.tabela.ustaw_uwage(p["symbol"], "cena 0,00 — RW z tej pozycji "
                                                     "będzie miało zerowy koszt")
            lista = "\n".join(f"   • {p['symbol']}" for p in bez_ceny[:10])
            wiecej = "" if len(bez_ceny) <= 10 else f"\n   … i {len(bez_ceny) - 10} więcej"
            if not messagebox.askyesno(
                    "PW — pozycje bez ceny",
                    f"{len(bez_ceny)} z {len(uzyte)} pozycji wejdzie na stan "
                    f"po CENIE 0,00 zł:\n\n{lista}{wiecej}\n\n"
                    "Taka pozycja tworzy warstwę magazynową bez wartości — "
                    "późniejsze RW\nz niej wyjdzie z zerowym kosztem i zaniży "
                    "wartość projektu.\n"
                    "(Dokładnie tak powstało 1183 kartotek bez ceny przy migracji "
                    "magazynu.)\n\n"
                    "Wystawić mimo to?", parent=self, icon="warning", default="no"):
                self.lbl_status.config(
                    text=f"{len(bez_ceny)} pozycji bez ceny — uzupełnij i sprawdź ponownie",
                    fg=UWAGA_ZOLTY)
                return False
            self.lbl_status.config(
                text=f"Sprawdzone — wartość {razem:,.2f} zł".replace(",", " ")
                     + f"   ·   {len(bez_ceny)} pozycji po 0,00",
                fg=UWAGA_ZOLTY)
            return True

        self.lbl_status.config(
            text=f"Sprawdzone — wartość PW: {razem:,.2f} zł".replace(",", " "),
            fg=OK_ZIELONY)
        return True

    def po_wystawieniu(self, wynik):
        numer = (wynik or {}).get("numer")
        bledy = [k for k in (wynik or {}).get("kroki", []) if k.get("Status") == "blad"]
        if bledy and not numer:
            messagebox.showerror(
                "PW", "Subiekt odrzucił dokument:\n\n"
                + "\n".join(f"• {k.get('Symbol') or '—'}: {k.get('Szczegoly')}"
                            for k in bledy[:10]), parent=self)
            return
        uzyte = self.tabela.uzyte()
        razem = sum(float(p.get("wartosc") or 0) for p in uzyte)
        messagebox.showinfo(
            "PW wystawione",
            f"✅ {numer or 'Dokument utworzony'}\n\n"
            f"Pozycji: {len(uzyte)}\n"
            f"Wartość: {razem:,.2f} zł\n".replace(",", " ")
            + f"Magazyn: {self.var_magazyn.get()}\n"
              f"Uwagi (projekt): {self._uwagi_dokumentu()}\n"
            + (f"Tytuł: {self._tytul_dokumentu()}\n" if self._tytul_dokumentu() else "")
            + "\nStan w Subiekcie wzrósł o te ilości.", parent=self)
        odswiez = self.kontekst.get("po_zapisie")
        if odswiez:
            try:
                odswiez()
            except Exception:
                pass
        self.destroy()


def otworz(parent, pozycje, kontekst=None):
    """Otwiera formularz PW dla podanych pozycji."""
    if not pozycje:
        messagebox.showinfo("PW", "Drzewo jest puste — nie ma czego przyjąć.",
                            parent=parent)
        return None
    return OknoPW(parent, pozycje, kontekst)
