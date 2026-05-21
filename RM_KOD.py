#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RM_KOD - Lightweight PLC Code Editor
Dla programistów PLC - edycja kodów odblokowujących bez całego RM_MANAGER'a
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
from datetime import datetime
from pathlib import Path

import rm_manager as rmm

class RMKOD:
    # Colors
    COLOR_GREEN = "#27ae60"
    COLOR_RED = "#e74c3c"
    COLOR_TOPBAR = "#34495e"
    COLOR_WARNING = "#f39c12"

    FONT_DEFAULT = ("Arial", 10)
    FONT_SMALL = ("Arial", 9)
    FONT_BOLD = ("Arial", 10, "bold")

    def __init__(self, root):
        self.root = root
        self.root.title("RM_KOD - PLC Code Editor v1.0")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        # Paths
        self.rm_master_db_path = Path(os.path.expanduser("~")) / "RM_BAZA" / "rm_master.sqlite"
        self.rm_projects_dir = Path(os.path.expanduser("~")) / "RM_BAZY"

        # State
        self.selected_project_id = None
        self.project_names = {}
        self.have_lock = False
        self.current_user = "PLC_PROGRAMMER"

        self.lock_manager = None  # Will initialize if needed

        # Build UI
        self._build_ui()
        self._load_projects()

    def _build_ui(self):
        """Build main window UI"""
        # ── Top: Project selector ────────────────────────────────────
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(top_frame, text="📋 Projekt:", font=self.FONT_BOLD).pack(side=tk.LEFT, padx=(0, 5))
        self.project_combo = ttk.Combobox(top_frame, width=50, font=self.FONT_DEFAULT, state='readonly')
        self.project_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.project_combo.bind('<<ComboboxSelected>>', self._on_project_selected)

        # Lock button
        self.btn_lock = tk.Button(top_frame, text="🔒 Przejmij Lock", font=self.FONT_DEFAULT,
                                   bg=self.COLOR_GREEN, fg="white", command=self._acquire_lock, padx=10)
        self.btn_lock.pack(side=tk.LEFT, padx=5)

        self.btn_release = tk.Button(top_frame, text="🔓 Zwolnij Lock", font=self.FONT_DEFAULT,
                                      bg=self.COLOR_RED, fg="white", command=self._release_lock, padx=10, state=tk.DISABLED)
        self.btn_release.pack(side=tk.LEFT, padx=5)

        # ── Tabs ─────────────────────────────────────────────────────
        self.tab_control = ttk.Notebook(self.root)
        self.tab_control.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Tab 1: Payment Milestones (read-only)
        self.payment_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.payment_tab, text="💳 Transze Płatności")
        self._build_payment_tab()

        # Tab 2: PLC Codes (edit)
        self.codes_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.codes_tab, text="🔑 Kody PLC")
        self._build_codes_tab()

        # ── Status bar ───────────────────────────────────────────────
        self.status_bar = tk.Label(self.root, text="Gotowy", relief=tk.SUNKEN, anchor='w',
                                   font=self.FONT_SMALL, bg="#ecf0f1", fg="#34495e")
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _build_payment_tab(self):
        """Build read-only payment milestones tab"""
        frame = ttk.LabelFrame(self.payment_tab, text="Transze Płatności (Podgląd)", padding=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Treeview
        columns = ('percentage', 'date', 'type', 'created_by', 'modified_at')
        self.payment_tree = ttk.Treeview(frame, columns=columns, height=15)

        self.payment_tree.column('#0', width=0, stretch=tk.NO)
        self.payment_tree.column('percentage', anchor=tk.CENTER, width=80)
        self.payment_tree.column('date', anchor=tk.W, width=120)
        self.payment_tree.column('type', anchor=tk.CENTER, width=100)
        self.payment_tree.column('created_by', anchor=tk.W, width=100)
        self.payment_tree.column('modified_at', anchor=tk.W, width=180)

        self.payment_tree.heading('#0', text='')
        self.payment_tree.heading('percentage', text='%')
        self.payment_tree.heading('date', text='Data')
        self.payment_tree.heading('type', text='Typ')
        self.payment_tree.heading('created_by', text='Utworzył')
        self.payment_tree.heading('modified_at', text='Zmieniono')

        # Scrollbar
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.payment_tree.yview)
        self.payment_tree.configure(yscroll=scrollbar.set)

        self.payment_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_codes_tab(self):
        """Build PLC codes edit tab"""
        # Controls
        controls = ttk.Frame(self.codes_tab)
        controls.pack(fill=tk.X, padx=10, pady=10)

        tk.Button(controls, text="➕ Dodaj", font=self.FONT_DEFAULT, bg=self.COLOR_GREEN,
                  fg="white", command=self._add_code, padx=10).pack(side=tk.LEFT, padx=2)
        tk.Button(controls, text="✏️  Edytuj", font=self.FONT_DEFAULT, bg=self.COLOR_WARNING,
                  fg="white", command=self._edit_code, padx=10).pack(side=tk.LEFT, padx=2)
        tk.Button(controls, text="🗑️  Usuń", font=self.FONT_DEFAULT, bg=self.COLOR_RED,
                  fg="white", command=self._delete_code, padx=10).pack(side=tk.LEFT, padx=2)

        # Treeview
        frame = ttk.LabelFrame(self.codes_tab, text="Kody PLC", padding=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        columns = ('type', 'code', 'used', 'description', 'created_by')
        self.codes_tree = ttk.Treeview(frame, columns=columns, height=20)

        self.codes_tree.column('#0', width=0, stretch=tk.NO)
        self.codes_tree.column('type', anchor=tk.CENTER, width=100)
        self.codes_tree.column('code', anchor=tk.W, width=120)
        self.codes_tree.column('used', anchor=tk.CENTER, width=80)
        self.codes_tree.column('description', anchor=tk.W, width=250)
        self.codes_tree.column('created_by', anchor=tk.W, width=100)

        self.codes_tree.heading('#0', text='')
        self.codes_tree.heading('type', text='Typ')
        self.codes_tree.heading('code', text='Kod')
        self.codes_tree.heading('used', text='Użyty')
        self.codes_tree.heading('description', text='Opis')
        self.codes_tree.heading('created_by', text='Utworzył')

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.codes_tree.yview)
        self.codes_tree.configure(yscroll=scrollbar.set)

        self.codes_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind double-click to edit
        self.codes_tree.bind('<Double-1>', lambda e: self._edit_code())

    def _load_projects(self):
        """Load projects from database"""
        try:
            projects = rmm.get_projects(str(self.rm_master_db_path))
            self.project_names = {p['id']: p['name'] for p in projects}

            project_list = [f"{p['id']} - {p['name']}" for p in projects]
            self.project_combo['values'] = project_list

            self.status_bar.config(text=f"✅ Załadowano {len(projects)} projektów")
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można załadować projektów:\n{e}")
            self.status_bar.config(text="❌ Błąd ładowania projektów", fg="red")

    def _on_project_selected(self, event=None):
        """Handle project selection"""
        selection = self.project_combo.get()
        if not selection:
            return

        try:
            project_id = int(selection.split(' - ')[0])
            self.selected_project_id = project_id
            self.have_lock = False
            self.btn_lock.config(state=tk.NORMAL)
            self.btn_release.config(state=tk.DISABLED)

            self._load_payment_milestones()
            self._load_codes()

            self.status_bar.config(text=f"✅ Wybrany projekt: {self.project_names.get(project_id)}")
        except Exception as e:
            messagebox.showerror("Błąd", f"Błąd wyboru projektu:\n{e}")

    def _load_payment_milestones(self):
        """Load payment milestones (read-only)"""
        if not self.selected_project_id:
            return

        try:
            # Clear tree
            for item in self.payment_tree.get_children():
                self.payment_tree.delete(item)

            milestones = rmm.get_payment_milestones(str(self.rm_master_db_path), self.selected_project_id)

            for m in milestones:
                pct = f"{m['percentage']}%"
                date = m.get('payment_date') or '—'
                ptype = m.get('payment_type', 'PŁATNOŚĆ')
                created_by = m.get('created_by') or '—'
                modified_at = m.get('modified_at') or '—'

                self.payment_tree.insert('', tk.END, values=(pct, date, ptype, created_by, modified_at))

            self.payment_tree.config(height=min(len(milestones), 15))
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można załadować transz:\n{e}")

    def _load_codes(self):
        """Load PLC codes"""
        if not self.selected_project_id:
            return

        try:
            # Clear tree
            for item in self.codes_tree.get_children():
                self.codes_tree.delete(item)

            codes = rmm.get_plc_codes(str(self.rm_master_db_path), self.selected_project_id)

            for c in codes:
                code_type = c['code_type']
                code = c['unlock_code']
                used = "✅ TAK" if c['is_used'] else "❌ NIE"
                desc = c.get('description') or '—'
                created_by = c.get('created_by') or '—'

                self.codes_tree.insert('', tk.END, values=(code_type, code, used, desc, created_by),
                                      tags=(str(c['id']),))

            self.codes_tree.config(height=min(len(codes), 20))
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można załadować kodów:\n{e}")

    def _acquire_lock(self):
        """Acquire project lock"""
        if not self.selected_project_id:
            messagebox.showwarning("Brak projektu", "Wybierz projekt")
            return

        try:
            # Simple lock implementation
            self.have_lock = True
            self.btn_lock.config(state=tk.DISABLED)
            self.btn_release.config(state=tk.NORMAL)
            self.status_bar.config(text=f"🔒 Lock przejęty na projekt {self.selected_project_id}")
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można przejąć lock'a:\n{e}")

    def _release_lock(self):
        """Release project lock"""
        if not self.selected_project_id:
            return

        self.have_lock = False
        self.btn_lock.config(state=tk.NORMAL)
        self.btn_release.config(state=tk.DISABLED)
        self.status_bar.config(text="🔓 Lock zwolniony")

    def _add_code(self):
        """Add new PLC code"""
        if not self.selected_project_id:
            messagebox.showwarning("Brak projektu", "Wybierz projekt")
            return

        if not self.have_lock:
            messagebox.showerror("Brak lock'a", "Musisz najpierw przejąć lock projektu")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Dodaj nowy kod PLC")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("400x300")

        # Type
        ttk.Label(dialog, text="Typ:", font=self.FONT_DEFAULT).grid(row=0, column=0, sticky='e', padx=10, pady=10)
        type_var = tk.StringVar(value='TEMPORARY')
        ttk.Combobox(dialog, textvariable=type_var, values=['TEMPORARY', 'PERMANENT'], state='readonly',
                    width=20).grid(row=0, column=1, padx=10, pady=10)

        # Code
        ttk.Label(dialog, text="Kod:", font=self.FONT_DEFAULT).grid(row=1, column=0, sticky='e', padx=10, pady=10)
        code_entry = ttk.Entry(dialog, width=30, font=self.FONT_DEFAULT)
        code_entry.grid(row=1, column=1, padx=10, pady=10)

        # Description
        ttk.Label(dialog, text="Opis:", font=self.FONT_DEFAULT).grid(row=2, column=0, sticky='ne', padx=10, pady=10)
        desc_text = tk.Text(dialog, width=30, height=5, font=self.FONT_DEFAULT)
        desc_text.grid(row=2, column=1, padx=10, pady=10)

        def save():
            code = code_entry.get().strip()
            if not code:
                messagebox.showwarning("Błąd", "Podaj kod")
                return

            try:
                rmm.add_plc_code(str(self.rm_master_db_path), self.selected_project_id,
                                type_var.get(), code, desc_text.get('1.0', tk.END).strip(),
                                user=self.current_user)
                self._load_codes()
                dialog.destroy()
                self.status_bar.config(text="✅ Kod dodany")
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można dodać kodu:\n{e}")

        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=20)
        ttk.Button(btn_frame, text="Zapisz", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Anuluj", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _edit_code(self):
        """Edit selected PLC code"""
        if not self.have_lock:
            messagebox.showerror("Brak lock'a", "Musisz najpierw przejąć lock projektu")
            return

        selection = self.codes_tree.selection()
        if not selection:
            messagebox.showwarning("Brak wyboru", "Wybierz kod do edycji")
            return

        code_id = int(self.codes_tree.item(selection[0], 'tags')[0])
        values = self.codes_tree.item(selection[0], 'values')

        dialog = tk.Toplevel(self.root)
        dialog.title("Edytuj kod PLC")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("400x300")

        # Type (read-only)
        ttk.Label(dialog, text="Typ:", font=self.FONT_DEFAULT).grid(row=0, column=0, sticky='e', padx=10, pady=10)
        ttk.Label(dialog, text=values[0], font=self.FONT_DEFAULT).grid(row=0, column=1, padx=10, pady=10, sticky='w')

        # Code (read-only)
        ttk.Label(dialog, text="Kod:", font=self.FONT_DEFAULT).grid(row=1, column=0, sticky='e', padx=10, pady=10)
        ttk.Label(dialog, text=values[1], font=self.FONT_DEFAULT).grid(row=1, column=1, padx=10, pady=10, sticky='w')

        # Description (editable)
        ttk.Label(dialog, text="Opis:", font=self.FONT_DEFAULT).grid(row=2, column=0, sticky='ne', padx=10, pady=10)
        desc_text = tk.Text(dialog, width=30, height=5, font=self.FONT_DEFAULT)
        desc_text.grid(row=2, column=1, padx=10, pady=10)
        desc_text.insert('1.0', values[3])

        def save():
            try:
                # Update description via database
                con = sqlite3.connect(str(self.rm_master_db_path))
                con.execute("UPDATE plc_codes SET description = ? WHERE id = ?",
                          (desc_text.get('1.0', tk.END).strip(), code_id))
                con.commit()
                con.close()

                self._load_codes()
                dialog.destroy()
                self.status_bar.config(text="✅ Kod zaktualizowany")
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można zaktualizować kodu:\n{e}")

        # Buttons
        btn_frame = ttk.Frame(dialog)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=20)
        ttk.Button(btn_frame, text="Zapisz", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Anuluj", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _delete_code(self):
        """Delete selected PLC code"""
        if not self.have_lock:
            messagebox.showerror("Brak lock'a", "Musisz najpierw przejąć lock projektu")
            return

        selection = self.codes_tree.selection()
        if not selection:
            messagebox.showwarning("Brak wyboru", "Wybierz kod do usunięcia")
            return

        if not messagebox.askyesno("Potwierdzenie", "Na pewno usunąć ten kod?"):
            return

        code_id = int(self.codes_tree.item(selection[0], 'tags')[0])

        try:
            con = sqlite3.connect(str(self.rm_master_db_path))
            con.execute("DELETE FROM plc_codes WHERE id = ?", (code_id,))
            con.commit()
            con.close()

            self._load_codes()
            self.status_bar.config(text="✅ Kod usunięty")
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można usunąć kodu:\n{e}")


def main():
    root = tk.Tk()
    app = RMKOD(root)
    root.mainloop()


if __name__ == '__main__':
    main()
