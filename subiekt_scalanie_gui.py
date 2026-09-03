# -*- coding: utf-8 -*-
"""
Okno „Scal kody handlowe" — ujednolicenie zapisu w bieżącym projekcie.

Wywołanie z RM_BAZA (menu 📦 SUBIEKT):

    import subiekt_scalanie_gui
    subiekt_scalanie_gui.open_window(parent, project_id=52, project_name="2627 …")

Co robi: elementy handlowe nie mają numeru rysunku, więc ich identyfikatorem
jest kod katalogowy wpisywany ręcznie — a ten sam kod bywa zapisany różnie
('UCFL 201' / 'UCFL-201' / 'UCFL201'). Każdy wariant zakłada w Subiekcie
osobną kartotekę, z rozbitą historią cen i stanem w kilku miejscach.

Układ: drzewko. Wiersz nadrzędny to kod z projektu, pod nim WSZYSTKIE jego
podobne z tego samego projektu — żeby decyzja zapadała z pełnym kontekstem,
a nie na podstawie dwóch rozłącznych list. Kolumna „Docelowa nazwa" jest
edytowalna (dwuklik): można wybrać istniejący wariant albo wpisać własny,
bo czasem żaden zapis w bazie nie jest dobry ('Nakrętka TR16x4..' z kropkami,
'CFM-TR-G-B.60-SH-' z wiszącym myślnikiem).

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
        ("docelowa", "Docelowa nazwa (dwuklik = edycja)", 300, "w"),
        ("ile",      "Szt.",                               50, "e"),
        ("info",     "Skąd / podobieństwo",               240, "w"),
    ]

    def __init__(self, parent, project_id, project_name=None):
        super().__init__(parent)
        self.project_id = project_id
        self.pozycje = []
        # {klucz pozycji: docelowa nazwa} — tylko to, co user zmienił.
        self._docelowe = {}
        # {klucz pozycji: {kody podpięte do scalenia z tą pozycją}}
        self._podpiete = {}
        self._edytor = None

        tytul = f"Scal kody handlowe — projekt {project_id}"
        if project_name:
            tytul += f" ({project_name})"
        self.title(tytul)
        self.geometry("1040x620")
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
                                font=("Arial", 9), anchor="w", padx=12, pady=6,
                                justify=tk.LEFT)
        self.summary.pack(side=tk.TOP, fill=tk.X)

        wrap = tk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 4))
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in self.COLS], show="tree headings")
        self.tree.heading("#0", text="Kod w projekcie")
        self.tree.column("#0", width=300, minwidth=120, stretch=True)
        for key, label, width, anchor in self.COLS:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor=anchor,
                             stretch=(key == "docelowa"), minwidth=45)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vs.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.tag_configure("duplikat", background="#fdebd0")   # ten sam kod
        self.tree.tag_configure("podobny",  foreground="#7f8c8d")   # może być inny element
        self.tree.tag_configure("podpiety", background="#d5f5e3")   # user scala z rodzicem
        self.tree.tag_configure("zmieniona", background="#eaf2f8")  # własna nazwa docelowa

        self.tree.bind("<Double-1>", self._on_double)
        self.tree.bind("<space>", self._toggle_podpiecie)

        hint = tk.Label(
            self,
            text=("Dwuklik na „Docelowa nazwa” = edycja (wpisz własną albo wybierz istniejącą).    "
                  "Dwuklik / spacja na podobnym = podepnij go do scalenia z pozycją wyżej.    "
                  "Pomarańczowe = ten sam kod, inny zapis.    Szare = podobne, może być innym elementem."),
            anchor="w", padx=12, pady=2, fg="#555", font=("Arial", 8),
            wraplength=1000, justify=tk.LEFT)
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
        self._zamknij_edytor()
        self.btn_refresh.config(state=tk.DISABLED)
        self.btn_scal.config(state=tk.DISABLED)
        self.status.config(text="Przeglądam BOM-y…")
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        try:
            poz = S.pozycje_z_podobnymi(self.project_id)
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
        self.pozycje = pozycje
        self._docelowe.clear()
        self._podpiete.clear()
        # Kilka zapisów tego samego kodu to pewny duplikat — podpinamy od razu.
        for p in pozycje:
            if p["identyczne"]:
                self._podpiete[p["klucz"]] = set(p["identyczne"])
        self._refill()
        self.status.config(text="Nic jeszcze nie zmieniono — zapis dopiero po kliknięciu „Scal”.")

    # ── prezentacja ────────────────────────────────────────────────────────
    def _docelowa(self, p):
        """Nazwa, na którą pójdzie scalenie: wybór usera albo domyślny kod."""
        return self._docelowe.get(p["klucz"], p["kod"])

    def _refill(self):
        self._zamknij_edytor()
        self.tree.delete(*self.tree.get_children())
        tylko_kolizje = self.var_tylko_kolizje.get()

        pokazane = 0
        do_zmiany = 0
        for i, p in enumerate(self.pozycje):
            ma_co = bool(p["identyczne"] or p["podobne"])
            if tylko_kolizje and not ma_co:
                continue
            pokazane += 1
            podpiete = self._podpiete.get(p["klucz"], set())
            docelowa = self._docelowa(p)
            wlasna = docelowa != p["kod"]

            # Ile wystąpień faktycznie zmieni nazwę: podpięte kody + sama
            # pozycja, jeśli user wpisał dla niej inną nazwę.
            zmieni = sum(self._ile(kod) for kod in podpiete)
            if wlasna:
                zmieni += p["ile"]
            do_zmiany += zmieni

            skad = ""
            if p["w_bazie"]:
                naj = max(p["w_bazie"].items(), key=lambda t: t[1])
                skad = f"w bazie: {naj[0]} ({naj[1]} proj.)"
            rid = f"p{i}"
            self.tree.insert("", "end", iid=rid, text=p["kod"], open=bool(podpiete),
                             values=(docelowa + ("   ✎" if wlasna else ""),
                                     p["ile"], skad),
                             tags=("zmieniona",) if wlasna else ())

            for j, kod in enumerate(p["identyczne"]):
                jest = kod in podpiete
                self.tree.insert(rid, "end", iid=f"{rid}i{j}", text=f"   = {kod}",
                                 values=("→ " + docelowa if jest else "(nie scalane)",
                                         self._ile(kod), "ten sam kod, inny zapis"),
                                 tags=("podpiety",) if jest else ("duplikat",))

            for j, s in enumerate(p["podobne"]):
                jest = s["kod"] in podpiete
                opis = f"wspólne {s['wspolne']} zn." + (", prefiks" if s["prefiks"] else "")
                self.tree.insert(rid, "end", iid=f"{rid}s{j}", text=f"   ~ {s['kod']}",
                                 values=("→ " + docelowa if jest else "(nie scalane)",
                                         self._ile(s["kod"]), opis),
                                 tags=("podpiety",) if jest else ("podobny",))

        z_kolizja = sum(1 for p in self.pozycje if p["identyczne"] or p["podobne"])
        self.summary.config(text=(
            f"Kodów handlowych w projekcie: {len(self.pozycje)}    "
            f"z podobnymi: {z_kolizja}    "
            f"pokazanych: {pokazane}    "
            f"wystąpień do zmiany: {do_zmiany}\n"
            f"Zmieniany jest TYLKO projekt {self.project_id}. Podpięte pozycje "
            f"(zielone) dostaną nazwę docelową rodzica."))
        self.btn_scal.config(state=tk.NORMAL if do_zmiany else tk.DISABLED)

    def _ile(self, kod):
        """Ile razy dany zapis występuje w tym projekcie."""
        k = S.norm_kod(kod)
        for p in self.pozycje:
            if p["klucz"] == k:
                return p["ile"]
        return 0

    # ── interakcja ─────────────────────────────────────────────────────────
    def _on_double(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        kol = self.tree.identify_column(event.x)
        parent = self.tree.parent(iid)
        # Dwuklik na dziecku = podpięcie/odpięcie, niezależnie od kolumny.
        if parent:
            self._przelacz(parent, iid)
            return
        # Na rodzicu edytujemy tylko kolumnę „Docelowa nazwa".
        if kol == "#1":
            self._edytuj(iid)

    def _toggle_podpiecie(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        parent = self.tree.parent(sel[0])
        if parent:
            self._przelacz(parent, sel[0])

    def _przelacz(self, rid, child_iid):
        p = self.pozycje[int(rid[1:])]
        kod = self.tree.item(child_iid, "text").strip()[2:].strip()   # bez '= ' / '~ '
        zbior = self._podpiete.setdefault(p["klucz"], set())
        if kod in zbior:
            zbior.discard(kod)
        else:
            zbior.add(kod)
        self._refill()
        self.tree.see(rid)

    def _zamknij_edytor(self):
        if self._edytor is not None:
            self._edytor.destroy()
            self._edytor = None

    def _edytuj(self, rid):
        """Pole edycji nazwy docelowej wprost w komórce."""
        self._zamknij_edytor()
        p = self.pozycje[int(rid[1:])]
        box = self.tree.bbox(rid, "docelowa")
        if not box:
            return
        x, y, w, h = box

        var = tk.StringVar(value=self._docelowa(p))
        # Combobox, nie Entry: user ma pod ręką istniejące zapisy (własne
        # i z całej bazy), ale pole zostaje edytowalne, żeby dało się wpisać
        # nazwę, której jeszcze nigdzie nie ma.
        propozycje = list(dict.fromkeys(
            [p["kod"]] + p["identyczne"] +
            [s["kod"] for s in p["podobne"]] +
            list(p["w_bazie"])))
        ed = ttk.Combobox(self.tree, textvariable=var, values=propozycje,
                          font=("Consolas", 9))
        ed.place(x=x, y=y, width=w, height=h)
        ed.focus_set()
        ed.selection_range(0, tk.END)
        self._edytor = ed

        def zatwierdz(_e=None):
            nowa = var.get().strip()
            if nowa and nowa != p["kod"]:
                self._docelowe[p["klucz"]] = nowa
            else:
                self._docelowe.pop(p["klucz"], None)
            self._zamknij_edytor()
            self._refill()

        ed.bind("<Return>", zatwierdz)
        ed.bind("<<ComboboxSelected>>", zatwierdz)
        ed.bind("<Escape>", lambda _e: self._zamknij_edytor())
        ed.bind("<FocusOut>", lambda _e: zatwierdz())

    # ── zapis ──────────────────────────────────────────────────────────────
    def _zbierz_podmiany(self):
        """[(stary_zapis, nowy_zapis)] — co faktycznie pójdzie do UPDATE."""
        podmiany = []
        for p in self.pozycje:
            docelowa = self._docelowa(p)
            for kod in sorted(self._podpiete.get(p["klucz"], ())):
                if kod != docelowa:
                    podmiany.append((kod, docelowa))
            if docelowa != p["kod"]:
                podmiany.append((p["kod"], docelowa))
        return podmiany

    def _scal(self):
        podmiany = self._zbierz_podmiany()
        if not podmiany:
            return

        linie = [f"Projekt {self.project_id} — zmienić {len(podmiany)} zapisów?", ""]
        for stary, nowy in podmiany[:14]:
            linie.append(f"  {stary}   →   {nowy}")
        if len(podmiany) > 14:
            linie.append(f"  … i {len(podmiany) - 14} więcej")
        linie += ["", "Kopia pliku projektu trafi do:", BACKUP_DIR]
        if not messagebox.askyesno("Scalanie — potwierdzenie", "\n".join(linie),
                                   parent=self, icon="warning"):
            return

        self.btn_scal.config(state=tk.DISABLED)
        self.status.config(text="Zapisuję…")
        try:
            r = S.zastosuj_podmiany(podmiany, project_id=self.project_id,
                                    backup_dir=BACKUP_DIR)
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
