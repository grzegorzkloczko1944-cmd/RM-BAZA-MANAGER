# -*- coding: utf-8 -*-
"""
Formularz RW (rozchód wewnętrzny) wystawiany z Edytora kartotek.

Jedno RW dla wielu pozycji naraz — źródłem jest drzewo z sekcji 1 Edytora
(SUBIEKT_FORMULARZE_DOKUMENTOW.md §4).

Czym różni się od dwóch istniejących ścieżek RW
───────────────────────────────────────────────
  * `rmpak_calculator` — RW z potwierdzonego PW produkcji własnej, ilości
    biorą się z PW i nie da się ich zmienić. To domknięcie procesu RMPAK.
  * `subiekt_magazyn_gui._zdejmij_rw` — RW „zużyte / uszkodzone", pozycje
    zaznaczane na liście magazynu, domyślna ilość = cały stan.
  * TEN formularz — ręczne RW z pozycji, które user zebrał w drzewie
    Edytora: montaż maszyny, wydanie na projekt. Ilość wpisuje sam.

Ceny NIE MA świadomie
─────────────────────
RW nie niesie ceny netto — wartość dokumentu to KOSZT MAGAZYNOWY, liczony
przez Subiekta z warstw przyjęcia (RMPAK_PRODUKCJA_USTALENIA.md, w. 554-555).
Dlatego formularz pokazuje stan i ostrzega, gdy kartoteka nie ma z czego
policzyć kosztu — patrz `po_sprawdzeniu`.
"""

import datetime
import tkinter as tk
from tkinter import ttk, messagebox

from subiekt_dokument_form import (OknoDokumentu, TLO, TLO_SEKCJI, TEKST,
                                   TEKST_SZARY, OK_ZIELONY, BLAD_CZERWONY,
                                   UWAGA_ZOLTY)

#: Magazyn domyślny — ten sam co w oknie Magazyn (patrz MAGAZYN.md; stary
#: „MAG" jest pusty od migracji z 07.09.2026).
MAGAZYN_DOMYSLNY = "MASTER"


class OknoRW(OknoDokumentu):
    TYTUL = "DOKUMENT RW"
    PRZYCISK = "WYSTAW RW"
    KOLOR_PRZYCISKU = "#d35400"
    PODPOWIEDZ = ("Dwuklik na ilości = zmiana   ·   spacja = przełącz ✓   ·   "
                  "RW bez ceny — koszt magazynowy liczy Subiekt")

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
        # SAM NUMER, bez prefiksów — tak wyglądają dokumenty wystawiane
        # dotąd ręcznie w Subiekcie (RW 24/09/2026 → Uwagi „2645”),
        # ustalenie z 10.09.2026.
        self.var_projekt = tk.StringVar(value=self.kontekst.get("projekt", ""))
        tk.Entry(siatka, textvariable=self.var_projekt, font=("Arial", 9),
                 width=16).grid(row=0, column=3, sticky="w")

        tk.Label(siatka, text="Data:", bg=TLO_SEKCJI, fg=TEKST,
                 font=("Arial", 9), anchor="w", width=10).grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.var_data = tk.StringVar(
            value=datetime.date.today().strftime("%d.%m.%Y"))
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

        # DWA OSOBNE POLA DOKUMENTU, nie jeden sklejony tekst (10.09.2026).
        # Cała firma filtruje dokumenty w Subiekcie po Uwagach, szukając
        # SAMEGO numeru projektu — `numer_projektu_z_uwag()` bierze całą ich
        # treść jako numer. Doklejenie opisu („2741 — Montaż maszyny")
        # zepsułoby ten odczyt, więc opis idzie polem Tytuł.
        tk.Label(rodzic,
                 text="Projekt → pole „Uwagi” dokumentu (sam numer — po nim "
                      "filtruje się dokumenty w Subiekcie).    "
                      "Opis → pole „Tytuł”.",
                 bg=TLO_SEKCJI, fg=TEKST_SZARY, font=("Arial", 8), anchor="w").pack(
            fill=tk.X, padx=12, pady=(0, 6))

    def kolumny(self):
        # Stan i Koszt informacyjnie, NIEEDYTOWALNE.
        #
        # Ceny na RW nie ma i mieć nie będzie: cena netto to parametr
        # HANDLOWY, a rozchód wewnętrzny nic nie sprzedaje. Wartość dokumentu
        # niesie KOSZT MAGAZYNOWY, liczony przez Subiekta z warstw przyjęcia
        # (RMPAK_PRODUKCJA_USTALENIA.md, w. 554-555) — ręczne wpisanie ceny
        # rozjechałoby się z metodą wyceny rozchodu, gdy ten sam detal leży
        # w kilku partiach po różnych cenach.
        #
        # Ale POKAZAĆ ten koszt można i trzeba: kolumna wypełnia się po
        # „Sprawdź” wartościami policzonymi przez most, więc widać wartość
        # dokumentu PRZED wystawieniem, a nie dopiero w Subiekcie.
        # Puste = jeszcze nie sprawdzono (10.09.2026).
        return [("stan", "Stan", 70, False),
                ("koszt", "Koszt", 90, False)]

    def waliduj_naglowek(self):
        bledy = []
        if not (self.var_projekt.get().strip() or self.var_uwagi.get().strip()):
            bledy.append("podaj numer projektu albo uwagi — bez tego nie da się "
                         "później ustalić, po co powstało RW")
        for p in self.tabela.uzyte():
            stan = p.get("stan")
            if stan is not None and float(p["ilosc"]) > float(stan):
                bledy.append(f"{p['symbol']}: ilość {p['ilosc']:g} > stan {float(stan):g}")
        return bledy

    def _uwagi_dokumentu(self):
        """Pole Uwagi: WYŁĄCZNIE numer projektu (patrz komentarz w nagłówku).

        Gdy projektu nie podano, wpada tam opis — lepiej mieć w Uwagach
        cokolwiek niż dokument bez żadnego śladu, po co powstał.
        """
        return self.var_projekt.get().strip() or self.var_uwagi.get().strip()

    def _tytul_dokumentu(self):
        """Pole Tytuł: opis. Puste, gdy opis poszedł już do Uwag."""
        opis = self.var_uwagi.get().strip()
        return opis if self.var_projekt.get().strip() else ""

    def _plan(self, pozycje):
        return [{"symbol": p["symbol"], "ilosc": float(p["ilosc"])} for p in pozycje]

    def sprawdz(self, pozycje):
        from subiekt_magazyn_gui import utworz_rw
        return utworz_rw(self._plan(pozycje), self._uwagi_dokumentu(),
                         magazyn=self.var_magazyn.get(), zapisz=False,
                         tytul=self._tytul_dokumentu())

    def wystaw(self, pozycje):
        from subiekt_magazyn_gui import utworz_rw
        return utworz_rw(self._plan(pozycje), self._uwagi_dokumentu(),
                         magazyn=self.var_magazyn.get(), zapisz=True,
                         tytul=self._tytul_dokumentu())

    # ── reakcje na wynik ────────────────────────────────────────────────

    def po_sprawdzeniu(self, wynik):
        kroki = (wynik or {}).get("kroki") or []
        # Stary koszt dotyczyl POPRZEDNICH ilosci - kasujemy przed wpisaniem
        # nowego, zeby pozycja pominieta w tym przebiegu nie zostala z cudza
        # liczba.
        for p in self.tabela.pozycje:
            p.pop("koszt", None)
        bledy = [k for k in kroki if k.get("Status") == "blad"]
        bez_wyceny = [k for k in kroki if k.get("Status") == "bez-wyceny"]

        # Koszt policzony przez most wchodzi do tabeli — kolumna „Koszt”
        # przestaje być pusta i widać wartość dokumentu przed zapisem.
        wg_symbolu = {str(k.get("Symbol") or "").upper(): k.get("Koszt")
                      for k in kroki if k.get("Koszt") is not None}
        if wg_symbolu:
            for p in self.tabela.pozycje:
                if p["symbol"].upper() in wg_symbolu:
                    p["koszt"] = wg_symbolu[p["symbol"].upper()]
            self.tabela.odswiez()

        # Ostrzeżenia siadają na wierszach — user widzi je przy pozycji,
        # a nie tylko w zbiorczym komunikacie, który zaraz zamknie.
        for k in bez_wyceny:
            self.tabela.ustaw_uwage(k.get("Symbol"), "koszt 0,00 — brak ceny przyjęcia")
        for k in bledy:
            self.tabela.ustaw_uwage(k.get("Symbol"), str(k.get("Szczegoly") or "błąd"))

        if bledy:
            opis = "\n".join(f"• {k.get('Symbol') or '—'}: {k.get('Szczegoly')}"
                             for k in bledy[:12])
            messagebox.showerror(
                "RW — sprawdzenie wykryło problemy",
                f"Dokument NIE powstał.\n\n{opis}"
                + ("\n…" if len(bledy) > 12 else ""), parent=self)
            self.lbl_status.config(text=f"Błędów: {len(bledy)} — popraw pozycje",
                                   fg=BLAD_CZERWONY)
            return False

        if bez_wyceny:
            # Nie blokujemy: RW z zerowym kosztem jest poprawne księgowo,
            # tylko zaniża wartość dokumentu. User ma o tym WIEDZIEĆ przed
            # zapisem — 1183 z 1376 kartotek nie ma dziś ceny przyjęcia
            # (skutek migracji magazynu nr 2, patrz MAGAZYN.md).
            lista = "\n".join(f"   • {k.get('Symbol')}" for k in bez_wyceny[:10])
            wiecej = "" if len(bez_wyceny) <= 10 else f"\n   … i {len(bez_wyceny) - 10} więcej"
            messagebox.showwarning(
                "RW — pozycje bez wyceny",
                f"{len(bez_wyceny)} z {len(self.tabela.uzyte())} pozycji pójdzie "
                f"z KOSZTEM 0,00 zł:\n\n{lista}{wiecej}\n\n"
                "Te kartoteki nie mają ceny przyjęcia, więc nie podniosą wartości "
                "RW — dokument pokaże mniej, niż faktycznie zeszło.\n"
                "Stan magazynu zejdzie normalnie.\n\n"
                "Można wystawić mimo to.", parent=self)
            razem = sum(float(p.get("koszt") or 0) for p in self.tabela.uzyte())
            self.lbl_status.config(
                text=f"Sprawdzone — koszt {razem:,.2f} zł".replace(",", " ")
                     + f"   ·   {len(bez_wyceny)} pozycji bez wyceny (0,00)",
                fg=UWAGA_ZOLTY)
            return True

        razem = sum(float(p.get("koszt") or 0) for p in self.tabela.uzyte())
        self.lbl_status.config(
            text=f"Sprawdzone — koszt magazynowy: {razem:,.2f} zł".replace(",", " "),
            fg=OK_ZIELONY)
        return True

    def po_wystawieniu(self, wynik):
        numer = (wynik or {}).get("numer")
        bledy = [k for k in (wynik or {}).get("kroki", []) if k.get("Status") == "blad"]
        if bledy and not numer:
            messagebox.showerror(
                "RW", "Subiekt odrzucił dokument:\n\n"
                + "\n".join(f"• {k.get('Symbol') or '—'}: {k.get('Szczegoly')}"
                            for k in bledy[:10]), parent=self)
            return
        messagebox.showinfo(
            "RW wystawione",
            f"✅ {numer or 'Dokument utworzony'}\n\n"
            f"Pozycji: {len(self.tabela.uzyte())}\n"
            f"Magazyn: {self.var_magazyn.get()}\n"
            f"Uwagi (projekt): {self._uwagi_dokumentu()}\n"
            + (f"Tytuł: {self._tytul_dokumentu()}\n" if self._tytul_dokumentu() else "")
            + "\n"
            "Stan w Subiekcie zszedł. Wartość dokumentu to koszt magazynowy —\n"
            "sprawdzisz go w Przeglądzie dokumentów.", parent=self)
        odswiez = self.kontekst.get("po_zapisie")
        if odswiez:
            try:
                odswiez()
            except Exception:
                pass
        self.destroy()


def otworz(parent, pozycje, kontekst=None):
    """Otwiera formularz RW dla podanych pozycji."""
    if not pozycje:
        messagebox.showinfo("RW", "Drzewo jest puste — nie ma czego wydać.",
                            parent=parent)
        return None
    okno = OknoRW(parent, pozycje, kontekst)
    return okno
