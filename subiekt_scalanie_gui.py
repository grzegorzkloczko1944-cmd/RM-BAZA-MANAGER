# -*- coding: utf-8 -*-
"""
Okno „Scal kody handlowe" — ujednolicenie zapisu w bieżącym projekcie.

Wywołanie z RM_BAZA (menu 📦 SUBIEKT):

    import subiekt_scalanie_gui
    subiekt_scalanie_gui.open_window(parent, project_id=52, project_name="2627 …")

Co robi: elementy handlowe nie mają numeru rysunku, więc ich identyfikatorem
jest kod katalogowy wpisywany ręcznie — a ten sam kod bywa zapisany różnie
('UCFL 201' / 'UCFL-201' / 'UCFL201'). Okno pokazuje takie rozbieżności
w BIEŻĄCYM projekcie i pozwala ujednolicić zapis.

Zasięg: podpowiedź liczona z całej bazy (który zapis jest w firmie przyjęty),
ZAPIS tylko w tym projekcie — patrz uzasadnienie w subiekt_scalanie.py.

Zapis do BOM-u jest poprzedzony kopią pliku projektu i jawnym potwierdzeniem;
bez kliknięcia „Scal" okno niczego nie zmienia.
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import subiekt_scalanie as S

# Kopie przed zmianą. Obok baz projektów, w podkatalogu — żeby nie mieszać
# się z backupami RM_BAZA, które mają własny harmonogram i czyszczenie.
BACKUP_DIR = os.path.join(os.path.dirname(S.PROJECTS_DIR), "backups", "scalanie_kodow")


class ScalanieWindow(tk.Toplevel):
    COLS = [
        ("zostaje", "Zostaje (kanoniczny)", 300, "w"),
        ("zmiana",  "Zmieniane warianty",   300, "w"),
        ("tu",      "Tutaj",                 60, "e"),
        ("baza",    "W bazie",              110, "w"),
    ]

    def __init__(self, parent, project_id, project_name=None):
        super().__init__(parent)
        self.project_id = project_id
        self.grupy = []
        self.kandydaci = []          # pary podobne — do oceny, nie do scalenia
        self._pominiete = set()      # klucze grup wyłączonych przez usera

        tytul = f"Scal kody handlowe — projekt {project_id}"
        if project_name:
            tytul += f" ({project_name})"
        self.title(tytul)
        self.geometry("980x560")
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

        self.summary = tk.Label(self, text="Wczytywanie…", bg="#ecf0f1", fg="#2c3e50",
                                font=("Arial", 9), anchor="w", padx=12, pady=6,
                                justify=tk.LEFT)
        self.summary.pack(side=tk.TOP, fill=tk.X)

        wrap = tk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 4))
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in self.COLS], show="headings")
        for key, label, width, anchor in self.COLS:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor=anchor,
                             stretch=(key in ("zostaje", "zmiana")), minwidth=50)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.tag_configure("naglowek",   background="#34495e", foreground="white")
        self.tree.tag_configure("remis",      background="#fdebd0")
        self.tree.tag_configure("pominiete",  background="#eaecee", foreground="#7f8c8d")
        # Kandydaci na szaro — mają wyglądać jak informacja, nie jak coś,
        # co zaraz zostanie zmienione.
        self.tree.tag_configure("kand",       foreground="#7f8c8d")
        self.tree.tag_configure("kand_mocny", background="#eaf2f8")
        self.tree.bind("<Double-1>", self._zmien_kanoniczny)

        hint = tk.Label(
            self,
            text=("Dwuklik na wierszu = wybierz inny wariant jako kanoniczny "
                  "(albo pomiń grupę).    Pomarańczowe = remis: automat nie ma "
                  "podstaw do wyboru, sprawdź ręcznie."),
            anchor="w", padx=12, pady=2, fg="#555", font=("Arial", 8))
        hint.pack(side=tk.TOP, fill=tk.X)

        dol = tk.Frame(self)
        dol.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))
        self.btn_scal = tk.Button(dol, text="🔗 Scal w tym projekcie", command=self._scal,
                                  bg="#e67e22", fg="white", font=("Arial", 9, "bold"),
                                  padx=14, pady=6, relief=tk.RAISED, bd=2,
                                  state=tk.DISABLED, cursor="hand2")
        self.btn_scal.pack(side=tk.RIGHT)
        tk.Button(dol, text="Zamknij", command=self.destroy,
                  font=("Arial", 9), padx=12, pady=6).pack(side=tk.RIGHT, padx=(0, 8))

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    # ── wczytywanie ────────────────────────────────────────────────────────
    def _load_async(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.btn_scal.config(state=tk.DISABLED)
        self.status.config(text="Przeglądam BOM-y wszystkich projektów…")
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        try:
            grupy = S.zaproponuj_dla_projektu(self.project_id)
            kandydaci = S.znajdz_kandydatow(self.project_id)
            self.after(0, lambda: self._done(grupy, kandydaci, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._done([], [], err))

    def _done(self, grupy, kandydaci, error):
        self.btn_refresh.config(state=tk.NORMAL)
        if error:
            self.status.config(text="Błąd.")
            self.summary.config(text=error.split("\n")[0])
            messagebox.showerror("Scalanie", error, parent=self)
            return
        self.grupy = grupy
        self.kandydaci = kandydaci
        self._pominiete.clear()
        self._refill()
        self.status.config(text="Nic jeszcze nie zmieniono — zapis dopiero po kliknięciu „Scal”.")

    # ── prezentacja ────────────────────────────────────────────────────────
    def _refill(self):
        self.tree.delete(*self.tree.get_children())
        aktywne = 0

        # ── Sekcja 1: pewne duplikaty (identyczne po normalizacji) ──────────
        if self.grupy:
            self.tree.insert("", "end", iid="hdr_pewne", values=(
                "▼ DO SCALENIA — ten sam kod, inny zapis", "", "", ""),
                tags=("naglowek",))
        for i, g in enumerate(self.grupy):
            pominieta = g.klucz in self._pominiete
            if not pominieta:
                aktywne += g.wystapien_do_zmiany
            w_bazie = len(g.warianty.get(g.kanoniczny, {}).get("projekty", ()))
            tag = "pominiete" if pominieta else ("remis" if g.remis else "")
            zostaje = g.kanoniczny + ("   (pominięte)" if pominieta else "")
            self.tree.insert("", "end", iid=str(i), values=(
                zostaje,
                "   ·   ".join(sorted(g.do_zmiany)),
                g.wystapien_do_zmiany,
                f"{w_bazie} proj." if w_bazie else "tylko tutaj",
            ), tags=(tag,) if tag else ())

        # ── Sekcja 2: podobne — do oceny, NIE do automatycznego scalenia ────
        if self.kandydaci:
            self.tree.insert("", "end", iid="hdr_kand", values=(
                "▼ DO SPRAWDZENIA — podobne kody (mogą być różnymi elementami)",
                "", "", ""), tags=("naglowek",))
            for j, (zapisy_a, zapisy_b, n, zawiera) in enumerate(self.kandydaci):
                # Para, gdzie jeden kod jest początkiem drugiego, częściej
                # bywa duplikatem — stąd wyróżnienie.
                self.tree.insert("", "end", iid=f"k{j}", values=(
                    zapisy_a[0],
                    zapisy_b[0],
                    "",
                    "prefiks" if zawiera else f"wspólne {n} zn.",
                ), tags=("kand_mocny" if zawiera else "kand",))

        remisy = sum(1 for g in self.grupy if g.remis and g.klucz not in self._pominiete)
        if not self.grupy and not self.kandydaci:
            self.summary.config(text=(
                "Brak kodów do scalenia — zapis w tym projekcie jest spójny "
                "z resztą bazy."))
            self.btn_scal.config(state=tk.DISABLED)
        else:
            self.summary.config(text=(
                f"Do scalenia: {len(self.grupy)}    "
                f"wystąpień do zmiany: {aktywne}    "
                f"⚠ remisów: {remisy}    "
                f"do sprawdzenia: {len(self.kandydaci)}\n"
                f"Zmieniany jest TYLKO projekt {self.project_id}. Sekcja "
                f"„do sprawdzenia” NIE jest scalana — to podpowiedź, wiele z tych "
                f"par to różne rozmiary (KFL001/KFL002)."))
            self.btn_scal.config(state=tk.NORMAL if aktywne else tk.DISABLED)

    def _zmien_kanoniczny(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        g = self.grupy[int(sel[0])]
        WyborWariantu(self, g, self._po_wyborze)

    def _po_wyborze(self, g, wybrany, pomin):
        if pomin:
            self._pominiete.add(g.klucz)
        else:
            self._pominiete.discard(g.klucz)
            g.kanoniczny = wybrany
        self._refill()

    # ── zapis ──────────────────────────────────────────────────────────────
    def _scal(self):
        do_zapisu = [g for g in self.grupy if g.klucz not in self._pominiete and g.do_zmiany]
        if not do_zapisu:
            return
        ile = sum(g.wystapien_do_zmiany for g in do_zapisu)

        linie = [f"Projekt {self.project_id}: zmienić {ile} wystąpień w {len(do_zapisu)} kodach?", ""]
        for g in do_zapisu[:12]:
            linie.append(f"  {' · '.join(sorted(g.do_zmiany))}  →  {g.kanoniczny}")
        if len(do_zapisu) > 12:
            linie.append(f"  … i {len(do_zapisu) - 12} więcej")
        linie += ["", f"Kopia pliku projektu trafi do:", BACKUP_DIR]
        if not messagebox.askyesno("Scalanie — potwierdzenie", "\n".join(linie),
                                   parent=self, icon="warning"):
            return

        self.btn_scal.config(state=tk.DISABLED)
        self.status.config(text="Zapisuję…")
        try:
            r = S.zastosuj(do_zapisu, project_id=self.project_id, backup_dir=BACKUP_DIR)
        except Exception as e:
            self.status.config(text="Błąd zapisu.")
            messagebox.showerror("Scalanie", str(e), parent=self)
            return

        messagebox.showinfo(
            "Scalanie zakończone",
            f"Zmienionych wystąpień: {r['zmienionych']}\n\n"
            f"Kopia przed zmianą:\n{r['backup']}\n\n"
            "Odśwież arkusz, żeby zobaczyć nowe nazwy.",
            parent=self)
        self.status.config(text=f"Zapisano {r['zmienionych']} zmian. Kopia: {r['backup']}")
        self._load_async()


class WyborWariantu(tk.Toplevel):
    """Który wariant zostawić — albo pominąć grupę."""

    def __init__(self, parent, grupa, callback):
        super().__init__(parent)
        self.grupa = grupa
        self.callback = callback
        self.title("Który zapis zostawić?")
        self.transient(parent)
        self.grab_set()

        tk.Label(self, text="Wybierz zapis, który ma zostać w BOM-ie:",
                 font=("Arial", 9, "bold"), anchor="w").pack(fill=tk.X, padx=12, pady=(12, 6))

        self.var = tk.StringVar(value=grupa.kanoniczny)
        ramka = tk.Frame(self)
        ramka.pack(fill=tk.BOTH, expand=True, padx=12)
        # Kolejność jak w propozycji: najczęstszy w bazie na górze.
        for w in sorted(grupa.warianty,
                        key=lambda x: (-len(grupa.warianty[x]["projekty"]), x)):
            v = grupa.warianty[w]
            tu = grupa.w_projekcie.get(w, 0)
            opis = f"{w}      [w bazie: {len(v['projekty'])} proj."
            opis += f", tutaj: {tu}x]" if tu else ", nie ma w tym projekcie]"
            tk.Radiobutton(ramka, text=opis, variable=self.var, value=w,
                           anchor="w", justify=tk.LEFT,
                           font=("Consolas", 9)).pack(fill=tk.X, anchor="w")

        if grupa.remis:
            tk.Label(self, text="⚠ Remis — kilka zapisów jest równie częstych. "
                                "Automat wybrał alfabetycznie.",
                     fg="#c0392b", font=("Arial", 8), anchor="w",
                     wraplength=520, justify=tk.LEFT).pack(fill=tk.X, padx=12, pady=(6, 0))

        dol = tk.Frame(self)
        dol.pack(fill=tk.X, padx=12, pady=12)
        tk.Button(dol, text="Zatwierdź", command=self._ok, bg="#27ae60", fg="white",
                  font=("Arial", 9, "bold"), padx=12, pady=4).pack(side=tk.RIGHT)
        tk.Button(dol, text="Pomiń tę grupę", command=self._pomin,
                  font=("Arial", 9), padx=12, pady=4).pack(side=tk.RIGHT, padx=(0, 8))
        tk.Button(dol, text="Anuluj", command=self.destroy,
                  font=("Arial", 9), padx=12, pady=4).pack(side=tk.LEFT)

    def _ok(self):
        self.callback(self.grupa, self.var.get(), False)
        self.destroy()

    def _pomin(self):
        self.callback(self.grupa, self.grupa.kanoniczny, True)
        self.destroy()


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
