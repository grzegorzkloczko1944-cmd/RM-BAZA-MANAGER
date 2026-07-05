r"""
============================================================================
Parser_RM_BAZA GUI - okno wyników anomalii cenowych elementów handlowych
============================================================================
Cienka warstwa GUI nad Parser_RM_BAZA.py (logika tam, nie duplikowana tutaj).
READ-ONLY - nie edytuje bazy, jedyny zapis to eksport XLSX na dysk.

Arkusz w stylu RM_BAZA (tksheet, theme "light blue", te same kolory alarmów).

Uruchomienie:
    python Parser_RM_BAZA_gui.py
============================================================================
"""

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime

try:
    from tksheet import Sheet
except ImportError:
    Sheet = None
    print("Brak tksheet! Zainstaluj: pip install tksheet")

from Parser_RM_BAZA import (
    DatabaseManager,
    MASTER_PATH,
    PROJECTS_DIR,
    LOCAL_DIR,
    DEFAULT_THRESHOLD,
    DEFAULT_MIN_GROUP_SIZE,
    load_commercial_items,
    group_items,
    find_anomalies,
    export_xlsx,
)

# Kolory zgodne z paletą RM_BAZA
COLOR_RED_BG = "#F2DEDE"       # odchylenie bardzo wysokie
COLOR_YELLOW_BG = "#FCF8E3"    # odchylenie umiarkowane
COLOR_GRAY_BG = "#D3D3D3"      # separator grupy

HEADERS = [
    "Grupa", "Wariant", "Mediana ceny jedn. [PLN]", "Cena jedn. [PLN]", "Odchylenie",
    "Ilość", "Wartość razem [PLN]", "Projekt", "Dostawca", "Nr rysunku", "Nazwa pozycji",
]


class ParserRMBazaGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Parser_RM_BAZA - Anomalie cenowe elementów handlowych")
        self.geometry("1400x750")

        self.anomalies = []  # lista (group, med, max_price, ratio) z ostatniego przebiegu
        self._row_meta = []  # równoległa lista: (item_id,) per wiersz arkusza

        self._build_toolbar()
        self._build_sheet()
        self._build_statusbar()

    # ------------------------------------------------------------------
    # UI budowa
    # ------------------------------------------------------------------
    def _build_toolbar(self):
        bar = ttk.Frame(self)
        bar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=6)

        ttk.Label(bar, text="Próg odchylenia (x mediany):").pack(side=tk.LEFT, padx=(0, 4))
        self.threshold_var = tk.StringVar(value=str(DEFAULT_THRESHOLD))
        ttk.Entry(bar, textvariable=self.threshold_var, width=6).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(bar, text="Min. pozycji w grupie:").pack(side=tk.LEFT, padx=(0, 4))
        self.min_group_var = tk.StringVar(value=str(DEFAULT_MIN_GROUP_SIZE))
        ttk.Entry(bar, textvariable=self.min_group_var, width=5).pack(side=tk.LEFT, padx=(0, 12))

        self.btn_run = ttk.Button(bar, text="Analizuj bazę", command=self.on_run_clicked)
        self.btn_run.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_export = ttk.Button(bar, text="Eksport XLSX...", command=self.on_export_clicked, state=tk.DISABLED)
        self.btn_export.pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(bar, mode="indeterminate", length=160)
        self.progress.pack(side=tk.LEFT, padx=12)

    def _build_sheet(self):
        frame = ttk.Frame(self)
        frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        if Sheet is None:
            ttk.Label(frame, text="Brak biblioteki tksheet - zainstaluj: pip install tksheet").pack()
            self.sheet = None
            return

        self.sheet = Sheet(
            frame,
            headers=HEADERS,
            column_width=140,
            height=600,
            theme="light blue",
        )
        self.sheet.pack(fill=tk.BOTH, expand=True)

        self.sheet.set_options(
            show_selected_cells_border=True,
            enable_edit_cell_auto_resize=False,
            row_drag_and_drop_perform=False,
        )
        self.sheet.enable_bindings((
            "single_select",
            "select_all",
            "column_width_resize",
            "arrowkeys",
            "right_click_popup_menu",
            "rc_select",
            "copy",
        ))
        # READ-ONLY: brak "edit_cell" w bindings - arkusz tylko do przeglądu

    def _build_statusbar(self):
        self.status_var = tk.StringVar(value="Gotowy.")
        bar = ttk.Label(self, textvariable=self.status_var, anchor="w", relief=tk.SUNKEN)
        bar.pack(side=tk.BOTTOM, fill=tk.X)

    # ------------------------------------------------------------------
    # Akcje
    # ------------------------------------------------------------------
    def on_run_clicked(self):
        try:
            threshold = float(self.threshold_var.get().replace(",", "."))
            min_group_size = int(self.min_group_var.get())
        except ValueError:
            messagebox.showerror("Błąd", "Próg i minimalna liczba pozycji muszą być liczbami.")
            return

        self.btn_run.config(state=tk.DISABLED)
        self.btn_export.config(state=tk.DISABLED)
        self.progress.start(12)
        self.status_var.set("Łączenie z bazą RM_BAZA (read-only)...")

        thread = threading.Thread(
            target=self._run_analysis_worker, args=(threshold, min_group_size), daemon=True
        )
        thread.start()

    def _run_analysis_worker(self, threshold, min_group_size):
        try:
            db = DatabaseManager(master_path=MASTER_PATH, projects_dir=PROJECTS_DIR, local_dir=LOCAL_DIR)

            if not db.connect_master():
                self.after(0, self._on_run_error, "Nie udało się połączyć z master.sqlite")
                return

            self.after(0, self.status_var.set, "Wczytywanie pozycji handlowych ze wszystkich projektów...")
            items = load_commercial_items(db)

            self.after(0, self.status_var.set, f"Wczytano {len(items)} pozycji. Grupowanie...")
            groups = group_items(items)

            anomalies = find_anomalies(groups, threshold=threshold, min_group_size=min_group_size)

            db.close_all()

            self.after(0, self._on_run_done, anomalies, len(items), len(groups))
        except Exception as e:
            self.after(0, self._on_run_error, str(e))

    def _on_run_error(self, message):
        self.progress.stop()
        self.btn_run.config(state=tk.NORMAL)
        self.status_var.set("Błąd.")
        messagebox.showerror("Błąd analizy", message)

    def _on_run_done(self, anomalies, item_count, group_count):
        self.progress.stop()
        self.btn_run.config(state=tk.NORMAL)
        self.anomalies = anomalies

        self._populate_sheet(anomalies)

        if anomalies:
            self.btn_export.config(state=tk.NORMAL)
            self.status_var.set(
                f"Wczytano {item_count} pozycji, {group_count} grup. "
                f"Wykryto {len(anomalies)} grup(y) z anomalią cenową."
            )
        else:
            self.btn_export.config(state=tk.DISABLED)
            self.status_var.set(
                f"Wczytano {item_count} pozycji, {group_count} grup. Brak anomalii przy zadanym progu."
            )

    def _populate_sheet(self, anomalies):
        if self.sheet is None:
            return

        data = []
        row_colors = []  # (row_idx, bg) do podświetlenia po wstawieniu danych

        for g, med, max_price, ratio in anomalies:
            sorted_items = sorted(g.items, key=lambda x: x.unit_price or 0, reverse=True)
            for it in sorted_items:
                up = it.unit_price
                if up is None:
                    continue
                row = [
                    g.key, g.variant_tag, f"{med:.2f}", f"{up:.2f}",
                    f"{up / med:.2f}x" if med else "",
                    f"{it.qty:g}", f"{up * it.qty:.2f}",
                    it.project_name, it.supplier_name, it.drawing_no, it.name,
                ]
                data.append(row)
                if up == max_price:
                    bg = COLOR_RED_BG if ratio >= 2.0 else COLOR_YELLOW_BG
                    row_colors.append((len(data) - 1, bg))

        self.sheet.set_sheet_data(data, reset_col_positions=False, reset_row_positions=True)
        self.sheet.set_all_cell_sizes_to_text()

        for row_idx, bg in row_colors:
            for col in range(len(HEADERS)):
                self.sheet.highlight_cells(row=row_idx, column=col, bg=bg)

        self.sheet.refresh()

    def on_export_clicked(self):
        if not self.anomalies:
            return

        default_name = f"Parser_RM_BAZA_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        path = filedialog.asksaveasfilename(
            title="Eksport XLSX",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=default_name,
        )
        if not path:
            return

        try:
            export_xlsx(self.anomalies, path)
            self.status_var.set(f"Zapisano raport: {path}")
            messagebox.showinfo("Eksport", f"Zapisano raport XLSX:\n{path}")
        except Exception as e:
            messagebox.showerror("Błąd eksportu", str(e))


def main():
    app = ParserRMBazaGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
