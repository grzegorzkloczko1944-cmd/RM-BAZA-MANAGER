# -*- coding: utf-8 -*-
"""
Okno powiązania dostawców RM_BAZA z kontrahentami Subiekta.

    import subiekt_dostawcy_gui
    subiekt_dostawcy_gui.open_window(parent)

Po co (pomiar 04.09.2026): RM_BAZA ma 113 dostawców, Subiekt 629 kontrahentów.
Automat dopasowuje po NIP-ie (pewnie) albo po nazwie (~55 %), ale reszty nie
rozstrzygnie sam — w kolumnie Dostawca RM_BAZA siedzą trzy różne rzeczy:

  * realne firmy bez odpowiednika w Subiekcie  → ➕ założyć kontrahenta
  * operacje i statusy („GIĘCIE", „spawanie", „?")  → 🚫 to nie firma
  * warianty istniejących („Alufrost domówione", „RMPAK+")  → 🔗 wskazać firmę

Tego nie da się zautomatyzować — `GIĘCIE` wygląda dla algorytmu jak `COGNEX`.
Dlatego okno pokazuje wszystko i prosi o decyzję; nierozstrzygnięte są na górze.

Zapis w dwie strony:
  * 🔗 powiązanie → NIP z Subiekta trafia do RM_BAZA (suppliers.nip); od tej
    pory dopasowanie idzie po NIP-ie i nazwa przestaje mieć znaczenie,
  * ➕ założenie → nowy kontrahent w Subiekcie z NIP-em w kartotece
    (Sfera nie pobiera z GUS — użytkownik klika „Pobierz z GUS" w Subiekcie),
  * 🚫 nie firma → zapamiętane w subiekt_mapowania, nie wraca po odświeżeniu.
"""

import sqlite3
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import subiekt_dostawcy as sd
import subiekt_mapowania
from rm_kreciolek import Kreciolek
from subiekt_stany import wysrodkuj, podepnij_szerokosci

try:
    from tksheet import Sheet
except ImportError:
    Sheet = None

# Stan wiersza — to, co widać w kolumnie „Status", jedno słowo na sytuację.
ST_DO_DECYZJI = "❓ do decyzji"
ST_POWIAZANY = "✅ powiązany"
ST_DO_POWIAZANIA = "🔗 powiąż → zapisze NIP"
ST_DO_ZALOZENIA = "➕ załóż w Subiekcie"
ST_NIE_FIRMA = "🚫 nie firma"

FILTR_WSZYSCY = "— wszyscy —"
FILTR_DO_DECYZJI = "❓ do decyzji"
FILTR_POWIAZANI = "✅ powiązani"
FILTR_ZAPLANOWANE = "🔗➕ zaplanowane"
FILTR_NIE_FIRMY = "🚫 nie-firmy"


class DostawcyWindow(tk.Toplevel, Kreciolek):
    HEADERS = ["Status", "Dostawca RM_BAZA", "Kontrahent w Subiekcie",
               "NIP", "Jak dopasowano"]
    (COL_ST, COL_RM, COL_SUB, COL_NIP, COL_JAK) = range(5)
    SZEROKOSCI = [190, 240, 320, 120, 130]

    def __init__(self, parent):
        super().__init__(parent)
        self.wiersze = []
        self.widoczne = []
        self.kontrahenci = []

        self.title("Dostawcy RM_BAZA ↔ kontrahenci Subiekta")
        self.geometry("1200x680")
        self.minsize(900, 400)
        try:
            self.state("zoomed")
        except tk.TclError:
            pass

        self._build_ui()
        self.after(100, self._load_async)

    # ── UI ─────────────────────────────────────────────────────────────────
    def _build_ui(self):
        top = tk.Frame(self, bg="#34495e", height=42)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)
        tk.Label(top, text="🤝 Powiązanie dostawców RM_BAZA z kontrahentami Subiekta",
                 bg="#34495e", fg="white", font=("Arial", 11, "bold")).pack(side=tk.LEFT, padx=12)
        # Wiek odczytu — dane z Subiekta starzeją się, a nic tego nie pokazywało.
        self.lbl_wiek = tk.Label(top, text="", bg="#34495e", fg="#e74c3c",
                                 font=("Arial", 13, "bold"))
        self.lbl_wiek.pack(side=tk.LEFT, padx=(16, 0))
        self.btn_refresh = tk.Button(top, text="🔄 Odśwież", command=self._load_async,
                                     bg="#3498db", fg="white", font=("Arial", 8),
                                     padx=8, pady=2, relief=tk.RAISED, bd=1)
        self.btn_refresh.pack(side=tk.RIGHT, padx=10, pady=8)

        # Filtry
        f = tk.Frame(self, bg="#ecf0f1")
        f.pack(side=tk.TOP, fill=tk.X)
        tk.Label(f, text="Szukaj:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(12, 3), pady=6)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refill())
        tk.Entry(f, textvariable=self.search_var, width=22, font=("Arial", 9)).pack(side=tk.LEFT, pady=6)
        tk.Label(f, text="Pokaż:", bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(14, 3), pady=6)
        self.filter_var = tk.StringVar(value=FILTR_WSZYSCY)
        cmb = ttk.Combobox(f, textvariable=self.filter_var, width=18, state="readonly",
                           font=("Arial", 9),
                           values=[FILTR_WSZYSCY, FILTR_DO_DECYZJI, FILTR_POWIAZANI,
                                   FILTR_ZAPLANOWANE, FILTR_NIE_FIRMY])
        cmb.pack(side=tk.LEFT, pady=6)
        cmb.bind("<<ComboboxSelected>>", lambda _e: self._refill())

        # Czyszczenie filtrów — ta sama ikona i kolor co w arkuszu głównym.
        tk.Button(f, text="🗑️", command=self._wyczysc_filtry, bg="#95a5a6", fg="white",
                  font=("Arial", 11, "bold"), width=3, relief=tk.RAISED, bd=2,
                  cursor="hand2").pack(side=tk.LEFT, padx=(10, 2), pady=4)

        # Akcje — WIDOCZNE przyciski, nie schowane w PPM. Działają na
        # zaznaczonych wierszach (kliknięcie w komórkę wystarczy).
        a = tk.Frame(self, bg="#f4ecf7")
        a.pack(side=tk.TOP, fill=tk.X)
        tk.Label(a, text="Dla zaznaczonych:", bg="#f4ecf7",
                 font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(12, 8), pady=5)
        for txt, cmd, kolor in (
            ("🔗 Powiąż z kontrahentem…", self._powiaz, "#2980b9"),
            ("➕ Załóż w Subiekcie", self._zaloz, "#e67e22"),
            ("🚫 To nie firma", self._nie_firma, "#7f8c8d"),
            ("↩ Cofnij decyzję", self._cofnij, "#95a5a6"),
        ):
            tk.Button(a, text=txt, command=cmd, bg=kolor, fg="white", font=("Arial", 9),
                      padx=10, pady=2, relief=tk.RAISED, bd=1, cursor="hand2"
                      ).pack(side=tk.LEFT, padx=3, pady=5)
        tk.Label(a, text="   (dwuklik w wiersz = powiąż)", bg="#f4ecf7", fg="#7f8c8d",
                 font=("Arial", 8)).pack(side=tk.LEFT, padx=6)

        self.summary = tk.Label(self, text="Wczytywanie…", bg="#ecf0f1", fg="#2c3e50",
                                font=("Arial", 9), anchor="w", padx=12, pady=6)
        self.summary.pack(side=tk.TOP, fill=tk.X)

        wrap = tk.Frame(self)
        wrap.pack(fill=tk.BOTH, expand=True, padx=8, pady=(4, 4))
        if Sheet is None:
            tk.Label(wrap, text="Brak biblioteki tksheet", fg="#c0392b").pack(pady=20)
            self.sheet = None
        else:
            self.sheet = Sheet(wrap, headers=list(self.HEADERS), column_width=140,
                               height=460, theme="light blue")
            self.sheet.set_options(show_selected_cells_border=True,
                                   enable_edit_cell_auto_resize=False,
                                   empty_horizontal=0, empty_vertical=0)
            self.sheet.enable_bindings((
                "single_select", "drag_select", "ctrl_select", "select_all",
                "column_width_resize", "arrowkeys", "right_click_popup_menu",
                "rc_select", "copy",
            ))
            # Szerokości kolumn zapamiętywane między sesjami, jak w arkuszu głównym.
            podepnij_szerokosci(self, self.sheet, "dostawcy", self.SZEROKOSCI)
            self.sheet.bind("<Double-Button-1>", self._on_dblclick, add="+")
            self.sheet.popup_menu_add_command("🔗 Powiąż z kontrahentem…", self._powiaz)
            self.sheet.popup_menu_add_command("➕ Załóż w Subiekcie", self._zaloz)
            self.sheet.popup_menu_add_command("🚫 To nie firma", self._nie_firma)
            self.sheet.popup_menu_add_command("↩ Cofnij decyzję", self._cofnij)
            self.sheet.pack(fill=tk.BOTH, expand=True)

        bottom = tk.Frame(self)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))
        self.btn_wykonaj = tk.Button(bottom, text="💾 Zapisz zaplanowane (NIP → RM_BAZA, nowi → Subiekt)",
                                     command=self._wykonaj, bg="#27ae60", fg="white",
                                     font=("Arial", 9, "bold"), padx=14, pady=5,
                                     relief=tk.RAISED, bd=2, state=tk.DISABLED)
        self.btn_wykonaj.pack(side=tk.RIGHT)
        self.lbl_plan = tk.Label(bottom, text="", fg="#7f8c8d", font=("Arial", 8))
        self.lbl_plan.pack(side=tk.LEFT, pady=8)

        self.status = tk.Label(self, text="", anchor="w", padx=12, pady=3,
                               bg="#34495e", fg="#ecf0f1", font=("Arial", 8))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    # ── wczytywanie ────────────────────────────────────────────────────────
    def _load_async(self):
        self.btn_refresh.config(state=tk.DISABLED)
        self.btn_wykonaj.config(state=tk.DISABLED)
        self.start_kreciolek("Czytam dostawców RM_BAZA i kontrahentów Subiekta (~10 s)")
        threading.Thread(target=self._load_worker, daemon=True).start()

    def _load_worker(self):
        try:
            kontrahenci = sd.pobierz_kontrahentow()
            dostawcy = sd.pobierz_dostawcow()
            pary = sd.dopasuj(dostawcy, kontrahenci)
            wiersze = []
            for d, k, powod in pary:
                if powod == "nie-firma":
                    status = ST_NIE_FIRMA
                elif k and d["nip"] and d["nip"] == k["nip"]:
                    status = ST_POWIAZANY
                elif k and k["nip"]:
                    status = ST_DO_POWIAZANIA      # automat trafił, NIP do zapisania
                elif k:
                    status = ST_POWIAZANY          # kontrahent bez NIP — nic do zapisania
                else:
                    status = ST_DO_DECYZJI
                wiersze.append({
                    "supplier_id": d["supplier_id"], "nazwa": d["name"], "nip_rm": d["nip"],
                    "kontrahent": k["nazwa"] if k else "", "nip_sub": k["nip"] if k else "",
                    "jak": powod, "status": status,
                })
            self.after(0, lambda: self._load_done(wiersze, kontrahenci, None))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._load_done([], [], err))

    def _load_done(self, wiersze, kontrahenci, error):
        self.stop_kreciolek()      # także przy błędzie — inaczej kręci się dalej
        self.zaznacz_odczyt(self.lbl_wiek)
        self.btn_refresh.config(state=tk.NORMAL)
        if error:
            self.status.config(text="Błąd.")
            messagebox.showerror("Dostawcy", error, parent=self)
            return
        self.wiersze = wiersze
        self.kontrahenci = kontrahenci
        self.btn_wykonaj.config(state=tk.NORMAL)
        self._refill()
        self.status.config(text=f"Wczytano. Kontrahentów w Subiekcie: {len(kontrahenci)}. "
                                "Nic jeszcze nie zapisano.")

    # ── prezentacja ────────────────────────────────────────────────────────
    KOLEJNOSC = {ST_DO_DECYZJI: 0, ST_DO_POWIAZANIA: 1, ST_DO_ZALOZENIA: 1,
                 ST_POWIAZANY: 2, ST_NIE_FIRMA: 3}

    def _wyczysc_filtry(self):
        """Filtry do stanu wyjściowego. NIE cofa decyzji (powiązań, „nie firma") —
        to praca użytkownika, nie ustawienie widoku."""
        self.search_var.set("")
        self.filter_var.set(FILTR_WSZYSCY)
        self._refill()

    def _refill(self):
        if not self.sheet:
            return
        szukaj = (self.search_var.get() or "").strip().lower()
        tryb = self.filter_var.get()
        out = []
        for w in self.wiersze:
            if szukaj and szukaj not in f"{w['nazwa']} {w['kontrahent']}".lower():
                continue
            st = w["status"]
            if tryb == FILTR_DO_DECYZJI and st != ST_DO_DECYZJI:
                continue
            if tryb == FILTR_POWIAZANI and st != ST_POWIAZANY:
                continue
            if tryb == FILTR_ZAPLANOWANE and st not in (ST_DO_POWIAZANIA, ST_DO_ZALOZENIA):
                continue
            if tryb == FILTR_NIE_FIRMY and st != ST_NIE_FIRMA:
                continue
            out.append(w)
        # Do decyzji na górze — to jest to, po co user otwiera okno.
        out.sort(key=lambda w: (self.KOLEJNOSC.get(w["status"], 9), w["nazwa"].lower()))
        self.widoczne = out

        try:
            self.sheet.dehighlight_all()
        except Exception:
            pass
        self.sheet.set_sheet_data(
            [[w["status"], w["nazwa"], w["kontrahent"],
              w["nip_rm"] or w["nip_sub"], w["jak"]] for w in out],
            reset_col_positions=False, redraw=False)

        kolory = {ST_DO_DECYZJI: "#fadbd8", ST_DO_POWIAZANIA: "#d6eaf8",
                  ST_DO_ZALOZENIA: "#fdebd0", ST_POWIAZANY: "#d5f5e3",
                  ST_NIE_FIRMA: "#eaecee"}
        for i, w in enumerate(out):
            bg = kolory.get(w["status"])
            if bg:
                for c in range(len(self.HEADERS)):
                    self.sheet.highlight_cells(row=i, column=c, bg=bg)
        self.sheet.redraw()
        self._przelicz()

    def _przelicz(self):
        n = lambda st: sum(1 for w in self.wiersze if w["status"] == st)   # noqa: E731
        do_pow, do_zal = n(ST_DO_POWIAZANIA), n(ST_DO_ZALOZENIA)
        self.summary.config(text=(
            f"Dostawców: {len(self.wiersze)}    "
            f"❓ do decyzji: {n(ST_DO_DECYZJI)}    ✅ powiązani: {n(ST_POWIAZANY)}    "
            f"🚫 nie-firmy: {n(ST_NIE_FIRMA)}    pokazanych: {len(self.widoczne)}"))
        if do_pow or do_zal:
            self.lbl_plan.config(
                text=f"Do zapisania: {do_pow} NIP-ów do RM_BAZA, {do_zal} nowych kontrahentów w Subiekcie",
                fg="#c0392b")
        else:
            self.lbl_plan.config(text="Nic nie zaplanowano — powiąż, załóż albo oznacz nie-firmę.",
                                 fg="#7f8c8d")

    # ── zaznaczenie ────────────────────────────────────────────────────────
    def _zaznaczone(self):
        """Wiersze zaznaczone — LICZĄC kliknięcie w komórkę.

        get_selected_rows() domyślnie zwraca tylko wiersze zaznaczone przez
        nagłówek; klik w komórkę dawał „zaznacz najpierw wiersze" mimo
        widocznego zaznaczenia (zgłoszone 04.09.2026: „nie działa").
        """
        try:
            rows = self.sheet.get_selected_rows(get_cells_as_rows=True)
        except Exception:
            rows = []
        return [self.widoczne[r] for r in sorted(rows) if 0 <= r < len(self.widoczne)]

    def _wymagaj_zaznaczenia(self):
        w = self._zaznaczone()
        if not w:
            messagebox.showinfo("Dostawcy", "Kliknij najpierw wiersz w arkuszu.", parent=self)
        return w

    # ── akcje ──────────────────────────────────────────────────────────────
    def _on_dblclick(self, event):
        try:
            r = self.sheet.identify_row(event, allow_end=False)
        except Exception:
            return
        if r is not None and 0 <= r < len(self.widoczne):
            self._okno_wyboru([self.widoczne[r]])

    def _powiaz(self):
        w = self._wymagaj_zaznaczenia()
        if w:
            self._okno_wyboru(w)

    def _zaloz(self):
        w = self._wymagaj_zaznaczenia()
        if not w:
            return
        juz = [x for x in w if x["kontrahent"]]
        if juz:
            messagebox.showwarning(
                "Załóż", f"{len(juz)} z zaznaczonych ma już kontrahenta w Subiekcie — "
                         "drugiego nie zakładamy. Zaznacz tylko pozycje „do decyzji”.",
                parent=self)
            return
        for x in w:
            x["status"] = ST_DO_ZALOZENIA
        self._refill()

    def _nie_firma(self):
        w = self._wymagaj_zaznaczenia()
        if not w:
            return
        # Zapis od razu — to decyzja lokalna (nic nie idzie do Subiekta), a bez
        # utrwalenia wracała po każdym odświeżeniu.
        for x in w:
            subiekt_mapowania.dostawca_decyzja(x["supplier_id"], x["nazwa"], "nie-firma")
            x["status"] = ST_NIE_FIRMA
            x["kontrahent"], x["nip_sub"], x["jak"] = "", "", "nie-firma"
        self._refill()

    def _cofnij(self):
        w = self._wymagaj_zaznaczenia()
        if not w:
            return
        for x in w:
            if x["status"] == ST_NIE_FIRMA:
                subiekt_mapowania.dostawca_decyzja(x["supplier_id"], x["nazwa"], None)
            if x["status"] in (ST_NIE_FIRMA, ST_DO_ZALOZENIA):
                x["status"] = ST_DO_DECYZJI
                x["kontrahent"], x["nip_sub"], x["jak"] = "", "", "brak"
            elif x["status"] == ST_DO_POWIAZANIA and x["jak"] == "ręczne":
                x["status"] = ST_DO_DECYZJI
                x["kontrahent"], x["nip_sub"], x["jak"] = "", "", "brak"
        self._refill()

    def _okno_wyboru(self, wiersze):
        """Wskazanie kontrahenta z listy — dla wariantów, których automat nie
        złapał („Alufrost domówione" → „Alufrost sp. z o.o.")."""
        if not self.kontrahenci:
            return
        dlg = tk.Toplevel(self)
        dlg.title("Wskaż kontrahenta w Subiekcie")
        dlg.transient(self)
        dlg.grab_set()
        wysrodkuj(dlg, self, 600, 460)

        tk.Label(dlg, text="Dostawca RM_BAZA:  " + ", ".join(w["nazwa"] for w in wiersze[:3])
                 + (" …" if len(wiersze) > 3 else ""),
                 font=("Arial", 9, "bold")).pack(padx=14, pady=(12, 2), anchor="w")
        tk.Label(dlg, text="Wpisz fragment nazwy — lista zawęża się na bieżąco:",
                 fg="#7f8c8d", font=("Arial", 8)).pack(padx=14, anchor="w")
        pierwszy = wiersze[0]["nazwa"].split()
        var = tk.StringVar(value=pierwszy[0] if pierwszy else "")
        ent = tk.Entry(dlg, textvariable=var, font=("Arial", 10))
        ent.pack(fill=tk.X, padx=14, pady=(4, 0))
        ent.focus_set()
        ent.select_range(0, tk.END)

        ramka = tk.Frame(dlg)
        ramka.pack(fill=tk.BOTH, expand=True, padx=14, pady=8)
        lista = tk.Listbox(ramka, font=("Arial", 9))
        sb = ttk.Scrollbar(ramka, orient="vertical", command=lista.yview)
        lista.configure(yscrollcommand=sb.set)
        lista.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        widoczni = []

        def odswiez(*_):
            q = var.get().strip().lower()
            lista.delete(0, tk.END)
            widoczni.clear()
            for k in self.kontrahenci:
                if not q or q in k["nazwa"].lower() or q in (k["nip"] or ""):
                    widoczni.append(k)
                    lista.insert(tk.END, f"{k['nazwa']}    [NIP {k['nip'] or '—'}]")
            if lista.size():
                lista.selection_set(0)

        var.trace_add("write", odswiez)
        odswiez()

        def zastosuj(*_):
            sel = lista.curselection()
            if not sel:
                return
            k = widoczni[sel[0]]
            for w in wiersze:
                w["kontrahent"], w["nip_sub"], w["jak"] = k["nazwa"], k["nip"], "ręczne"
                if k["nip"] and w["nip_rm"] != k["nip"]:
                    w["status"] = ST_DO_POWIAZANIA      # NIP pójdzie do RM_BAZA po „Zapisz"
                else:
                    w["status"] = ST_POWIAZANY
            dlg.destroy()
            self._refill()

        box = tk.Frame(dlg)
        box.pack(pady=(0, 12))
        tk.Button(box, text="Powiąż", command=zastosuj, bg="#2980b9", fg="white",
                  font=("Arial", 9, "bold"), padx=18, pady=3).pack(side=tk.LEFT, padx=4)
        tk.Button(box, text="Anuluj", command=dlg.destroy, font=("Arial", 9),
                  padx=12, pady=3).pack(side=tk.LEFT, padx=4)
        lista.bind("<Double-Button-1>", zastosuj)
        ent.bind("<Return>", zastosuj)
        ent.bind("<Down>", lambda _e: lista.focus_set())

    # ── zapis ──────────────────────────────────────────────────────────────
    def _wykonaj(self):
        nipy = [w for w in self.wiersze if w["status"] == ST_DO_POWIAZANIA and w["nip_sub"]]
        zaloz = [w for w in self.wiersze if w["status"] == ST_DO_ZALOZENIA]
        if not nipy and not zaloz:
            messagebox.showinfo("Zapis", "Nie ma nic do zapisania.\n\n"
                                "Najpierw powiąż, załóż albo oznacz nie-firmę.", parent=self)
            return
        opis = []
        if nipy:
            opis.append(f"RM_BAZA — dopisanie NIP: {len(nipy)} dostawców")
        if zaloz:
            opis.append(f"Subiekt — nowi kontrahenci: {len(zaloz)}")
            opis += [f"      {w['nazwa']}" + (f"  (NIP {w['nip_rm']})" if w["nip_rm"] else "  (bez NIP)")
                     for w in zaloz[:12]]
            if len(zaloz) > 12:
                opis.append(f"      … i {len(zaloz) - 12} więcej")
        ok = messagebox.askyesno(
            "Zapis — potwierdzenie",
            "\n".join(opis)
            + ("\n\n⚠ Kontrahenta w Subiekcie nie da się łatwo usunąć." if zaloz else "")
            + "\n\nZapisać?", parent=self, icon="warning" if zaloz else "question")
        if not ok:
            return
        self.btn_wykonaj.config(state=tk.DISABLED)
        # ZAPIS też idzie przez most i trwa — bez kręciołka okno wygląda,
        # jakby zawisło w połowie zakładania kontrahentów.
        self.start_kreciolek("Zapisuję do Subiekta")
        threading.Thread(target=self._wykonaj_worker, args=(nipy, zaloz), daemon=True).start()

    def _wykonaj_worker(self, nipy, zaloz):
        raport = []
        try:
            if nipy:
                con = sqlite3.connect(sd._master_path(), timeout=15.0)
                try:
                    con.execute("PRAGMA journal_mode=DELETE")     # WAL nie działa przez SMB
                    con.execute("PRAGMA busy_timeout=5000")
                    for w in nipy:
                        con.execute("UPDATE suppliers SET nip = ? WHERE supplier_id = ?",
                                    (w["nip_sub"], w["supplier_id"]))
                    con.commit()
                finally:
                    con.close()
                raport.append(f"✅ NIP dopisany w RM_BAZA: {len(nipy)}")
            if zaloz:
                wynik = sd.zaloz_w_subiekcie(
                    [{"name": w["nazwa"], "nip": w["nip_rm"]} for w in zaloz], zapisz=True)
                kroki = wynik.get("kroki", [])
                zal = [k for k in kroki if k["Status"] == "zalozony"]
                ist = [k for k in kroki if k["Status"] == "istnieje"]
                bled = [k for k in kroki if k["Status"] == "blad"]
                raport.append(f"✅ Założono w Subiekcie: {len(zal)}")
                if ist:
                    raport.append(f"ℹ Już istniało (pominięto): {len(ist)}")
                if bled:
                    raport.append(f"❌ Błędy ({len(bled)}):")
                    raport += [f"      {k['Nazwa']}: {k.get('Szczegoly') or ''}" for k in bled[:8]]
            self.after(0, lambda: self._wykonaj_done("\n".join(raport), None, bool(zaloz)))
        except Exception as e:
            err = str(e)
            self.after(0, lambda: self._wykonaj_done("", err, False))

    def _wykonaj_done(self, raport, error, byli_nowi):
        self.stop_kreciolek()
        self.btn_wykonaj.config(state=tk.NORMAL)
        if error:
            self.status.config(text="Zapis nieudany.")
            messagebox.showerror("Zapis", error, parent=self)
            return
        if byli_nowi:
            raport += ("\n\nW Subiekcie: zaznacz nowych kontrahentów i użyj „Pobierz z GUS”\n"
                       "— NIP jest już w kartotece, nie trzeba go przepisywać.")
        messagebox.showinfo("Zapisano", raport, parent=self)
        self._load_async()


def open_window(parent):
    """Punkt wejścia dla RM_BAZA."""
    return DostawcyWindow(parent)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    root = tk.Tk()
    root.withdraw()
    w = open_window(root)
    w.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
