# -*- coding: utf-8 -*-
"""
Okno „Scal kody handlowe" — połączenie kilku wierszy BOM w jeden.

Wywołanie z RM_BAZA (menu 📦 SUBIEKT), TYLKO przy locku:

    import subiekt_scalanie_gui
    subiekt_scalanie_gui.open_window(parent, project_id=52, project_name="2627 …")

Po co: elementy handlowe nie mają numeru rysunku, więc ich identyfikatorem
jest kod katalogowy wpisywany ręcznie — a ten sam kod bywa zapisany różnie
('UCFL 201' / 'UCFL201-12'). W arkuszu to dwie pozycje, w RFQ dwa zapytania,
w Subiekcie dwie kartoteki z rozbitą historią cen.

Obsługa — trzy kroki, bez ukrytych gestów:
    1. klikasz wiersze, które są tą samą rzeczą (☐ → ☑),
    2. pole „Nazwa po scaleniu" wypełnia się samo najczęstszym zapisem
       z firmy — możesz je poprawić,
    3. „Scal zaznaczone": stare wiersze znikają, powstaje jeden z sumą ilości.

Dlaczego wymagany jest lock i zapis idzie przez db_manager.project_con:
przy locku arkusz pracuje na LOKALNEJ kopii projektu, a zwolnienie locka
kopiuje ją na serwer. Zapis do pliku na serwerze z pominięciem tej kopii
nie byłby widoczny w arkuszu, a przy zwolnieniu locka zostałby NADPISANY.
Ten sam wzorzec ma „Ukryj zaznaczone".
"""

import os
import shutil
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

import subiekt_scalanie as S

# Kopie przed zmianą — osobny podkatalog, żeby nie mieszać z backupami
# RM_BAZA, które mają własny harmonogram i czyszczenie.
BACKUP_DIR = os.path.join(os.path.dirname(S.PROJECTS_DIR), "backups", "scalanie_kodow")


class ScalanieWindow(tk.Toplevel):
    COLS = [
        ("zaz",      "",                       34, "c"),
        ("kod",      "Kod w projekcie",       250, "w"),
        ("ilosc",    "Ilość BOM",              70, "e"),
        ("material", "Materiał",              110, "w"),
        ("baza",     "Najczęściej w firmie",  230, "w"),
        ("podobne",  "Podobne w tym projekcie", 300, "w"),
    ]

    def __init__(self, parent, project_id, project_name=None):
        super().__init__(parent)
        self.project_id = project_id
        self.pozycje = []
        self._zaznaczone = set()      # klucze zaznaczonych pozycji
        self._nazwa_reczna = False    # user poprawił pole nazwy — nie nadpisuj

        # Połączenie arkusza = LOKALNA kopia projektu (open_project_local przy
        # locku). Cały zapis idzie tędy; plik na serwerze aktualizuje dopiero
        # zwolnienie locka (sync_project_to_server), jak w reszcie RM_BAZA.
        dbm = getattr(parent, "db_manager", None)
        self.con = getattr(dbm, "project_con", None) if dbm else None
        self.local_path = None
        if dbm is not None and getattr(dbm, "local_dir", None) is not None:
            self.local_path = os.path.join(str(dbm.local_dir), f"project_{project_id}.sqlite")
        # Uruchomienie spoza RM_BAZA (test z linii poleceń) nie ma połączenia
        # arkusza — wtedy silnik pisałby wprost do pliku na serwerze, czyli
        # dokładnie tam, gdzie NIE wolno. Taki tryb tylko do odczytu.
        self.tylko_podglad = self.con is None or not getattr(dbm, "is_local", False)

        tytul = f"Scal kody handlowe — projekt {project_id}"
        if project_name:
            tytul += f" ({project_name})"
        self.title(tytul)
        self.geometry("1060x600")
        self.transient(parent)

        self._build_ui()
        self.after(100, self._load_async)

    # ── UI ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        top = tk.Frame(self, bg="#34495e", height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🔗 Scalanie kodów elementów handlowych",
                 bg="#34495e", fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)

        self.btn_refresh = tk.Button(top, text="🔄 Przelicz", command=self._load_async,
                                     bg="#3498db", fg="white", font=("Arial", 8),
                                     padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_refresh.pack(side=tk.RIGHT, padx=10, pady=8)

        self.var_tylko_kolizje = tk.BooleanVar(value=True)
        tk.Checkbutton(top, text="Tylko z podobnymi", variable=self.var_tylko_kolizje,
                       command=self._refill, bg="#34495e", fg="white",
                       selectcolor="#e67e22", font=("Arial", 8),
                       activebackground="#34495e", activeforeground="white").pack(side=tk.RIGHT, padx=4)

        self.summary = tk.Label(self, text="Wczytywanie…", bg="#ecf0f1", fg="#2c3e50",
                                font=("Arial", 9), anchor="w", padx=12, pady=6, justify=tk.LEFT)
        self.summary.pack(side=tk.TOP, fill=tk.X)

        wrap = tk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 4))
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in self.COLS], show="headings",
                                 selectmode="none")
        for key, label, width, anchor in self.COLS:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor=anchor,
                             stretch=(key in ("kod", "podobne")), minwidth=30)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.tag_configure("zaz",     background="#d5f5e3")   # zaznaczone do scalenia
        self.tree.tag_configure("cichy",   foreground="#95a5a6")   # bez podobnych
        self.tree.bind("<Button-1>", self._on_click)

        tk.Label(self,
                 text="Kliknij wiersz, żeby go zaznaczyć (☐ → ☑). Zaznaczone wiersze zostaną "
                      "POŁĄCZONE w jeden z sumą ilości.   ⚠ Różny materiał zwykle znaczy, "
                      "że to inny element.",
                 anchor="w", padx=12, pady=2, fg="#555", font=("Arial", 8),
                 wraplength=1020, justify=tk.LEFT).pack(side=tk.TOP, fill=tk.X)

        # ── pasek nazwy i przycisku ──────────────────────────────────────────
        dol = tk.Frame(self)
        dol.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(4, 8))
        tk.Label(dol, text="Nazwa po scaleniu:", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.var_nazwa = tk.StringVar()
        self.ent_nazwa = tk.Entry(dol, textvariable=self.var_nazwa, font=("Consolas", 10), width=40)
        self.ent_nazwa.pack(side=tk.LEFT, padx=(8, 12), ipady=3)
        self.ent_nazwa.bind("<KeyRelease>", lambda _e: setattr(self, "_nazwa_reczna", True))

        self.btn_scal = tk.Button(dol, text="🔗 Scal zaznaczone", command=self._scal,
                                  bg="#e67e22", fg="white", font=("Arial", 9, "bold"),
                                  padx=14, pady=6, relief=tk.RAISED, bd=2,
                                  state=tk.DISABLED, cursor="hand2")
        self.btn_scal.pack(side=tk.RIGHT)
        tk.Button(dol, text="Zamknij", command=self.destroy,
                  font=("Arial", 9), padx=12, pady=6).pack(side=tk.RIGHT, padx=(0, 8))
        tk.Button(dol, text="Odznacz wszystko", command=self._odznacz,
                  font=("Arial", 9), padx=10, pady=6).pack(side=tk.RIGHT, padx=(0, 8))

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    # ── wczytywanie ────────────────────────────────────────────────────────
    def _load_async(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.btn_scal.config(state=tk.DISABLED)
        self.status.config(text="Przeglądam BOM-y…")
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        try:
            poz = S.pozycje_z_podobnymi(self.project_id, con=self.con)
            self.after(0, lambda: self._done(poz, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._done([], err))

    def _done(self, pozycje, error):
        self.btn_refresh.config(state=tk.NORMAL)
        if error:
            self.status.config(text="Błąd.")
            self.summary.config(text=error.split("\n")[0])
            messagebox.showerror("Scalanie", error, parent=self)
            return
        # Podobne kody obok siebie — sortowanie po znormalizowanym kluczu
        # ustawia 'UCFL201' tuż nad 'UCFL20112'.
        self.pozycje = sorted(pozycje, key=lambda p: p["klucz"])
        self._zaznaczone.clear()
        self._nazwa_reczna = False
        self.var_nazwa.set("")
        self._refill()
        if self.tylko_podglad:
            self.status.config(text="PODGLĄD — brak lokalnej kopii projektu, zapis wyłączony.")
        else:
            self.status.config(
                text="Zapis trafia do lokalnej kopii; na serwer — przy zwolnieniu locka.")

    # ── prezentacja ────────────────────────────────────────────────────────
    def _refill(self):
        self.tree.delete(*self.tree.get_children())
        tylko = self.var_tylko_kolizje.get()
        pokazane = 0
        for p in self.pozycje:
            ma_co = bool(p["identyczne"] or p["podobne"])
            if tylko and not ma_co and p["klucz"] not in self._zaznaczone:
                continue
            pokazane += 1
            zaz = p["klucz"] in self._zaznaczone

            naj = ""
            if p["w_bazie"]:
                w, n = max(p["w_bazie"].items(), key=lambda t: t[1])
                naj = f"{w}  ({n} proj.)"

            podobne = [s["kod"] for s in p["podobne"]] + [f"= {k}" for k in p["identyczne"]]
            tags = ("zaz",) if zaz else (() if ma_co else ("cichy",))
            self.tree.insert("", "end", iid=p["klucz"], tags=tags, values=(
                "☑" if zaz else "☐",
                p["kod"],
                f"{p['ilosc_bom']:g}",
                p["material"],
                naj,
                "   ·   ".join(podobne),
            ))

        wybrane = [p for p in self.pozycje if p["klucz"] in self._zaznaczone]
        suma = sum(p["ilosc_bom"] for p in wybrane)
        z_kolizja = sum(1 for p in self.pozycje if p["identyczne"] or p["podobne"])
        opis = (f"Kodów handlowych: {len(self.pozycje)}    z podobnymi: {z_kolizja}    "
                f"pokazanych: {pokazane}    ")
        if wybrane:
            opis += f"ZAZNACZONE: {len(wybrane)}  →  jedna pozycja, ilość {suma:g}"
            mats = {p["material"] for p in wybrane if p["material"]}
            if len(mats) > 1:
                opis += f"\n⚠ Zaznaczone różnią się materiałem: {' / '.join(sorted(mats))}"
        else:
            opis += "zaznacz co najmniej 2 wiersze, które są tą samą rzeczą"
        self.summary.config(text=opis)

        self._zaproponuj_nazwe(wybrane)
        self.btn_scal.config(
            text=f"🔗 Scal zaznaczone ({len(wybrane)})" if wybrane else "🔗 Scal zaznaczone",
            state=tk.NORMAL if (len(wybrane) >= 2 and not self.tylko_podglad) else tk.DISABLED)

    def _zaproponuj_nazwe(self, wybrane):
        """Najczęstszy w firmie zapis spośród zaznaczonych — chyba że user już
        wpisał własny (wtedy nie nadpisujemy mu tekstu pod palcami)."""
        if self._nazwa_reczna and self.var_nazwa.get().strip():
            return
        if not wybrane:
            self.var_nazwa.set("")
            return
        kandydaci = {}
        for p in wybrane:
            for w, n in p["w_bazie"].items():
                kandydaci[w] = max(kandydaci.get(w, 0), n)
            kandydaci.setdefault(p["kod"], 0)
        najlepszy = max(kandydaci.items(), key=lambda t: (t[1], -len(t[0])))[0]
        self.var_nazwa.set(najlepszy)

    # ── interakcja ─────────────────────────────────────────────────────────
    def _on_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        if iid in self._zaznaczone:
            self._zaznaczone.discard(iid)
        else:
            self._zaznaczone.add(iid)
        self._refill()
        self.tree.see(iid)

    def _odznacz(self):
        self._zaznaczone.clear()
        self._nazwa_reczna = False
        self._refill()

    # ── zapis ──────────────────────────────────────────────────────────────
    def _scal(self):
        if self.tylko_podglad:
            messagebox.showwarning(
                "Scalanie",
                "Brak lokalnej kopii projektu — przejmij lock w RM_BAZA.\n\n"
                "Zapis bez locka szedłby wprost do pliku na serwerze, "
                "z pominięciem arkusza.", parent=self)
            return
        wybrane = [p for p in self.pozycje if p["klucz"] in self._zaznaczone]
        if len(wybrane) < 2:
            return
        nazwa = self.var_nazwa.get().strip()
        if not nazwa:
            messagebox.showwarning("Scalanie", "Wpisz nazwę, jaką ma mieć scalona pozycja.",
                                   parent=self)
            self.ent_nazwa.focus_set()
            return

        # Wszystkie zapisy każdej zaznaczonej pozycji (kod + warianty pisowni).
        kody = []
        for p in wybrane:
            kody.append(p["kod"])
            kody.extend(p["identyczne"])
        wiersze = S.wiersze_kodu(self.project_id, kody, con=self.con)
        if len(wiersze) < 2:
            messagebox.showerror("Scalanie", "Nie znaleziono wierszy do połączenia — "
                                 "odśwież i spróbuj ponownie.", parent=self)
            return

        suma = sum(p["ilosc_bom"] for p in wybrane)
        zajete = [w for w in wiersze if w["praca"]]
        linie = [f"Połączyć {len(wiersze)} wierszy w jeden?", ""]
        for w in wiersze:
            # Jak arkusz: COALESCE(work_qty, src_qty).
            q = w["ilosci"].get("work_qty")
            if q in (None, ""):
                q = w["ilosci"].get("src_qty") or 0
            linie.append(f"   {w['nazwa']}    ({float(q):g} szt.)")
        linie += ["", f"   →  {nazwa}    ({suma:g} szt.)", ""]
        if zajete:
            linie += ["⚠ Niektóre wiersze mają już wpisane dane robocze",
                      "   (dostawca, zamówienie, termin) — po scaleniu PRZEPADNĄ.", ""]
        linie.append("Stare wiersze zostaną usunięte. Kopia pliku przed zmianą:")
        linie.append(BACKUP_DIR)
        if not messagebox.askyesno("Scalanie — potwierdzenie", "\n".join(linie),
                                   parent=self, icon="warning"):
            return

        self.btn_scal.config(state=tk.DISABLED)
        self.status.config(text="Zapisuję…")
        try:
            backup = self._kopia_przed_zmiana()
            r = S.scal_wiersze(self.project_id, [w["id"] for w in wiersze], nazwa,
                               backup_dir=BACKUP_DIR, con=self.con)
            backup = backup or r["backup"]
            self._zapisz_audit(wiersze, nazwa, r)
        except Exception as e:
            self.status.config(text="Błąd zapisu.")
            messagebox.showerror("Scalanie", str(e), parent=self)
            self._load_async()
            return

        odswiezony = self._odswiez_arkusz()
        tekst = (f"Połączono {len(wiersze)} wierszy w jeden:\n   {nazwa}   ({suma:g} szt.)"
                 + (f"\n\nKopia przed zmianą:\n{backup}" if backup else "")
                 + ("" if odswiezony else "\n\nOdśwież arkusz, żeby zobaczyć zmiany."))
        messagebox.showinfo("Scalanie zakończone", tekst, parent=self)
        self._load_async()

    def _kopia_przed_zmiana(self):
        """Kopia lokalnego pliku projektu (tryb lock). W trybie plikowym robi to silnik."""
        if self.con is None or not self.local_path or not os.path.isfile(self.local_path):
            return None
        self.con.commit()          # żeby kopia miała wszystko, co arkusz już zapisał
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cel = os.path.join(BACKUP_DIR, f"project_{self.project_id}_{stamp}.sqlite")
        shutil.copy2(self.local_path, cel)
        return cel

    def _zapisz_audit(self, wiersze, nazwa, raport):
        """Ślad w items_changes_log, tym samym kanałem co „Ukryj zaznaczone"."""
        log = getattr(self.master, "_log_item_change", None)
        if not callable(log):
            return
        for w in wiersze:
            try:
                log(w["id"], "MERGE", w["kolumna"], w["nazwa"],
                    f"{nazwa} (→ id {raport.get('nowy_id')})")
            except Exception:
                pass

    def _odswiez_arkusz(self):
        """Przeładuj arkusz RM_BAZA. To samo połączenie, więc widzi zmiany od razu."""
        metoda = getattr(self.master, "refresh_data", None)
        if not callable(metoda):
            return False
        try:
            metoda()
            return True
        except Exception:
            return False


def open_window(parent, project_id, project_name=None):
    """Punkt wejścia dla RM_BAZA."""
    if not project_id:
        messagebox.showwarning("Scalanie", "Najpierw wybierz projekt.", parent=parent)
        return None
    return ScalanieWindow(parent, project_id, project_name)


if __name__ == "__main__":
    import sys
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 52
    root = tk.Tk()
    root.withdraw()
    w = open_window(root, pid)
    w.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
