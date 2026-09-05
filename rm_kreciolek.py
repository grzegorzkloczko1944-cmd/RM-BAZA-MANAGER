# -*- coding: utf-8 -*-
"""
Kręciołek w pasku stanu — wspólny dla okien zakładki SUBIEKT.

Po co: most do Sfery odpowiada po ~10 s (start Sfery, logowanie operatora,
przelot po danych). Przez ten czas okno stoi z nieruchomym napisem
„Pytam Subiekta o zapotrzebowanie (~10 s)…" i wygląda, jakby zawisło
(zgłoszone 05.09.2026). Obracający się znak mówi, że praca trwa.

Użycie — domieszka do klasy okna, która ma `self.status` (etykieta paska
stanu) i jest widgetem Tk (potrzebne `after`/`after_cancel`):

    class OknoCzegos(tk.Toplevel, Kreciolek):
        ...
        def _wczytaj(self):
            self.start_kreciolek("Czytam dokumenty z Subiekta")
            threading.Thread(target=self._worker, daemon=True).start()

        def _gotowe(self, dane):
            self.stop_kreciolek()          # ZAWSZE, także przy błędzie
            self.status.config(text="Gotowe.")

⚠️ `stop_kreciolek()` musi być wołane również w gałęzi błędu — inaczej znak
kręci się w nieskończoność nad komunikatem o niepowodzeniu.
"""

import tkinter as tk

#: Klatki animacji. Znaki o tej samej szerokości, żeby tekst obok nie drgał.
KLATKI = "◐◓◑◒"

#: Co ile ms następna klatka. 120 ms daje płynny obrót bez obciążania pętli.
ODSTEP_MS = 120


class Kreciolek:
    """Domieszka: start_kreciolek() / stop_kreciolek() na pasku stanu."""

    _KLATKI = KLATKI

    def start_kreciolek(self, tekst="Czekam na Subiekta", pasek=None):
        """Zaczyna animację. `pasek` — etykieta inna niż self.status."""
        self._kreci_pasek = pasek if pasek is not None else getattr(self, "status", None)
        if self._kreci_pasek is None:
            return                      # okno bez paska stanu — nie ma gdzie
        self._kreci_tekst = tekst
        self._kreci_klatka = 0
        self._kreci = True
        self._kreciolek_tik()

    def _kreciolek_tik(self):
        if not getattr(self, "_kreci", False):
            return
        znak = self._KLATKI[self._kreci_klatka % len(self._KLATKI)]
        self._kreci_klatka += 1
        try:
            self._kreci_pasek.config(text=f"{znak}  {self._kreci_tekst}…")
        except tk.TclError:
            self._kreci = False         # okno zamknięte w międzyczasie
            return
        self._kreci_after = self.after(ODSTEP_MS, self._kreciolek_tik)

    def stop_kreciolek(self, tekst=None):
        """Zatrzymuje animację. `tekst` — co wpisać w pasek zamiast klatki."""
        self._kreci = False
        after_id = getattr(self, "_kreci_after", None)
        if after_id:
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
            self._kreci_after = None
        if tekst is not None:
            pasek = getattr(self, "_kreci_pasek", None) or getattr(self, "status", None)
            if pasek is not None:
                try:
                    pasek.config(text=tekst)
                except tk.TclError:
                    pass

    # ── wiek danych ────────────────────────────────────────────────────────
    #
    # Dane z Subiekta starzeją się: ktoś w firmie zakłada ZD, zmienia stany,
    # a okno pokazuje stan sprzed kwadransa. Licznik mówi wprost, jak stary
    # jest odczyt — im dłużej, tym bardziej czerwony.

    def zaznacz_odczyt(self, etykieta=None):
        """Zapamiętaj moment odczytu i zacznij odliczać. Wołane po wczytaniu."""
        import time
        self._odczyt_ts = time.time()
        if etykieta is not None:
            self._odczyt_lbl = etykieta
        self._odswiez_wiek()

    def _odswiez_wiek(self):
        lbl = getattr(self, "_odczyt_lbl", None)
        ts = getattr(self, "_odczyt_ts", None)
        if lbl is None or ts is None:
            return
        import time
        sek = int(time.time() - ts)
        # Same MINUTY, bez sekund — tykający licznik sekund niepotrzebnie
        # popędza (zgłoszone 05.09.2026: „sekundy są stresujące").
        minuty = sek // 60
        if minuty < 1:
            tekst = "odczyt przed chwilą"
        elif minuty < 60:
            tekst = f"odczyt {minuty} min temu"
        else:
            g, m = divmod(minuty, 60)
            tekst = f"odczyt {g} h {m} min temu" if m else f"odczyt {g} h temu"
        try:
            lbl.config(text=tekst, fg="#e74c3c")
        except tk.TclError:
            return                      # okno zamknięte
        # Co 10 s wystarczy, skoro i tak pokazujemy pełne minuty.
        self._wiek_after = self.after(10_000, self._odswiez_wiek)
