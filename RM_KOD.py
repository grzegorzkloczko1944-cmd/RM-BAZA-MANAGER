#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RM_KOD - Lightweight PLC Code Editor
Dla programistów PLC - edycja kodów odblokowujących bez całego RM_MANAGER'a
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
from datetime import datetime
from pathlib import Path
import socket

import rm_manager as rmm
from lock_manager_v2 import ProjectLockManager
import hashlib
from tkinter import filedialog

class RMKOD:
    # Colors
    COLOR_GREEN = "#27ae60"
    COLOR_RED = "#e74c3c"
    COLOR_TOPBAR = "#34495e"
    COLOR_WARNING = "#f39c12"

    FONT_DEFAULT = ("Arial", 10)
    FONT_SMALL = ("Arial", 9)
    FONT_BOLD = ("Arial", 10, "bold")

    CONFIG_FILE_PATH = r"C:\RMPAK_CLIENT\manager_sync_config.json"

    def __init__(self, root):
        self.root = root
        self.root.title("RM_KOD - PLC Code Editor v1.0")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        # Create menu
        self._create_menu()

        # Load configuration
        self.config = self._load_config()

        # Paths from config
        self.rm_master_db_path = self.config.get('rm_master_db_path',
            r"C:\RMPAK_CLIENT\RM_BAZY\RM_MANAGER\rm_manager.sqlite")
        self.master_db_path = self.config.get('master_db_path',
            r"C:\RMPAK_CLIENT\RM_BAZY\RM_BAZA\master.sqlite")
        self.rm_projects_dir = self.config.get('rm_projects_dir',
            r"C:\RMPAK_CLIENT\RM_BAZY\RM_MANAGER\RM_MANAGER_projects")
        self.locks_dir = self.config.get('locks_dir',
            r"C:\RMPAK_CLIENT\RM_BAZY\RM_MANAGER\LOCKS")

        # State
        self.selected_project_id = None
        self.project_names = {}
        self.projects = []
        self.combo_to_pid = {}
        self.have_lock = False
        self.current_user = None
        self.current_user_id = None
        self.users = {}  # Dict: id -> {id, username, display_name, role}

        # Initialize lock manager
        try:
            lock_config = {
                'client': {'name': 'RM_KOD'},
                'locks': {'folder': str(self.locks_dir), 'stale_seconds': 300}
            }
            self.lock_manager = ProjectLockManager(lock_config)
        except Exception as err:
            print(f"⚠️ Lock manager init: {err}")
            self.lock_manager = None

        # Build UI
        self._build_ui()
        self._load_users()
        self._load_projects()

        # Handle window closing
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        # Start automatic refresh (every 3 seconds)
        self._schedule_refresh()

    def _load_config(self):
        """Load configuration from JSON file"""
        try:
            if Path(self.CONFIG_FILE_PATH).exists():
                with open(self.CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️ Config load error: {e}")
        return {}

    def _save_last_user(self, user_id):
        """Save last logged-in user to config"""
        try:
            self.config['last_user_id'] = user_id
            with open(self.CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"⚠️ Error saving last user: {e}")

    def _get_last_user_id(self):
        """Get last logged-in user ID from config"""
        return self.config.get('last_user_id')

    def _build_ui(self):
        """Build main window UI"""
        # ── Login section ────────────────────────────────────────────
        login_frame = ttk.LabelFrame(self.root, text="👤 Zaloguj się", padding=10)
        login_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(login_frame, text="Użytkownik:", font=self.FONT_DEFAULT).pack(side=tk.LEFT, padx=5)
        self.user_combo = ttk.Combobox(login_frame, width=30, font=self.FONT_DEFAULT, state='readonly')
        self.user_combo.pack(side=tk.LEFT, padx=5)
        self.user_combo.bind('<<ComboboxSelected>>', self._on_user_selected)

        self.login_status = ttk.Label(login_frame, text="❌ Nie zalogowany", font=self.FONT_SMALL, foreground="red")
        self.login_status.pack(side=tk.LEFT, padx=20)

        # ── Top: Project selector ────────────────────────────────────
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(top_frame, text="📋 Projekt:", font=self.FONT_BOLD).pack(side=tk.LEFT, padx=(0, 5))
        self.project_combo = ttk.Combobox(top_frame, width=45, font=self.FONT_DEFAULT, state='readonly', height=25)
        self.project_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.project_combo.bind('<<ComboboxSelected>>', self._on_project_selected)

        # Refresh button
        tk.Button(top_frame, text="🔄 Odśwież", font=self.FONT_DEFAULT,
                  bg="#3498db", fg="white", command=self._refresh_projects, padx=10).pack(side=tk.LEFT, padx=2)

        # Lock button
        self.btn_lock = tk.Button(top_frame, text="🔒 Przejmij Lock", font=self.FONT_DEFAULT,
                                   bg=self.COLOR_GREEN, fg="white", command=self._acquire_lock, padx=10)
        self.btn_lock.pack(side=tk.LEFT, padx=2)

        self.btn_release = tk.Button(top_frame, text="🔓 Zwolnij Lock", font=self.FONT_DEFAULT,
                                      bg=self.COLOR_RED, fg="white", command=self._release_lock, padx=10, state=tk.DISABLED)
        self.btn_release.pack(side=tk.LEFT, padx=2)

        # ── Filter ────────────────────────────────────────────────────
        filter_frame = ttk.Frame(self.root)
        filter_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

        self.filter_without_code = tk.BooleanVar(value=False)
        self.filter_with_code = tk.BooleanVar(value=False)

        def _on_filter_without():
            if self.filter_without_code.get():
                self.filter_with_code.set(False)
            self._apply_project_filter()

        def _on_filter_with():
            if self.filter_with_code.get():
                self.filter_without_code.set(False)
            self._apply_project_filter()

        ttk.Checkbutton(filter_frame, text="📁 Projekty bez kodu", variable=self.filter_without_code,
                       command=_on_filter_without).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(filter_frame, text="📁 Projekty z kodem", variable=self.filter_with_code,
                       command=_on_filter_with).pack(side=tk.LEFT, padx=5)

        # ── Tabs ─────────────────────────────────────────────────────
        self.tab_control = ttk.Notebook(self.root)
        self.tab_control.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Tab 1: PLC Codes (edit) - FIRST
        self.codes_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.codes_tab, text="🔑 Kody PLC")
        self._build_codes_tab()

        # Tab 2: Payment Milestones (read-only) - SECOND
        self.payment_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.payment_tab, text="💳 Transze Płatności")
        self._build_payment_tab()

        # ── Status bar ───────────────────────────────────────────────
        self.status_bar = tk.Label(self.root, text="Gotowy", relief=tk.SUNKEN, anchor='w',
                                   font=self.FONT_SMALL, bg="#ecf0f1", fg="#34495e")
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _create_menu(self):
        """Create menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Plik", menu=file_menu)
        file_menu.add_command(label="⚙️ Konfiguracja ścieżek...", command=self.edit_config)
        file_menu.add_separator()
        file_menu.add_command(label="❌ Zamknij", command=self.root.quit)

    def edit_config(self):
        """Configuration dialog for database and folder paths"""
        dialog = tk.Toplevel(self.root)
        dialog.title("⚙️ Konfiguracja ścieżek")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("750x500")

        # Center on parent window
        dialog.update_idletasks()
        parent_width = self.root.winfo_width()
        parent_height = self.root.winfo_height()
        parent_x = self.root.winfo_x()
        parent_y = self.root.winfo_y()
        x = parent_x + (parent_width // 2) - (750 // 2)
        y = parent_y + (parent_height // 2) - (500 // 2)
        dialog.geometry(f"750x500+{x}+{y}")

        # Header
        header = tk.Label(dialog, text="KONFIGURACJA ŚCIEŻEK", bg="#34495e", fg="white",
                         font=("Arial", 12, "bold"), pady=8)
        header.pack(fill=tk.X)

        form = tk.Frame(dialog, padx=15, pady=10)
        form.pack(fill=tk.BOTH, expand=True)

        def make_row(parent, row, label, hint, default_val, browse_cmd):
            tk.Label(parent, text=label, font=("Arial", 10, "bold"), anchor="w", width=20).grid(
                row=row * 2, column=0, sticky="w", pady=(8, 0))
            entry = tk.Entry(parent, font=("Arial", 10), width=45)
            entry.insert(0, default_val)
            entry.grid(row=row * 2, column=1, padx=5, sticky="ew", pady=(8, 0))
            tk.Button(parent, text="📂", command=lambda e=entry: browse_cmd(e),
                     bg="#3498db", fg="white", font=("Arial", 9, "bold"), padx=6
                     ).grid(row=row * 2, column=2, padx=5, pady=(8, 0))
            tk.Label(parent, text=hint, font=("Arial", 8), fg="#7f8c8d", anchor="w").grid(
                row=row * 2 + 1, column=1, sticky="w", padx=5)
            return entry

        def browse_file(entry):
            path = filedialog.askopenfilename(
                title="Wybierz plik .sqlite",
                filetypes=[("SQLite Database", "*.sqlite"), ("Wszystkie pliki", "*.*")],
                initialdir=str(Path(entry.get()).parent) if Path(entry.get()).parent.exists() else "."
            )
            if path:
                entry.delete(0, tk.END)
                entry.insert(0, path)

        def browse_folder(entry):
            path = filedialog.askdirectory(
                title="Wybierz folder",
                initialdir=entry.get() if Path(entry.get()).is_dir() else "."
            )
            if path:
                entry.delete(0, tk.END)
                entry.insert(0, path)

        form.columnconfigure(1, weight=1)

        e_master = make_row(form, 0, "master.sqlite (RM_BAZA):",
                           "Wspólna baza projektów RM_BAZA",
                           self.master_db_path, browse_file)
        e_rm_db = make_row(form, 1, "rm_manager.sqlite:",
                          "Główna baza RM_MANAGER z kodami PLC",
                          self.rm_master_db_path, browse_file)
        e_locks = make_row(form, 2, "Folder locków:",
                          "Katalog locków projektów",
                          self.locks_dir, browse_folder)

        def save_and_close():
            self.master_db_path = e_master.get().strip()
            self.rm_master_db_path = e_rm_db.get().strip()
            self.locks_dir = e_locks.get().strip()

            # Create directories if needed
            Path(self.locks_dir).mkdir(parents=True, exist_ok=True)

            # Reinitialize lock manager
            try:
                lock_config = {
                    'client': {'name': 'RM_KOD'},
                    'locks': {'folder': str(self.locks_dir), 'stale_seconds': 300}
                }
                self.lock_manager = ProjectLockManager(lock_config)
            except Exception as err:
                print(f"⚠️ Lock manager reinit: {err}")

            # Save config
            self.config['master_db_path'] = self.master_db_path
            self.config['rm_master_db_path'] = self.rm_master_db_path
            self.config['locks_dir'] = self.locks_dir
            try:
                with open(self.CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=2)
            except Exception as e:
                print(f"⚠️ Config save error: {e}")

            messagebox.showinfo("Sukces", "Konfiguracja zapisana. Przeładuj projekty.")
            dialog.destroy()
            self._load_users()
            self._load_projects()

        # Buttons
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=15, pady=10)
        tk.Button(btn_frame, text="💾 Zapisz", command=save_and_close,
                 bg="#27ae60", fg="white", font=("Arial", 10, "bold"), padx=20, pady=6
                 ).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="❌ Anuluj", command=dialog.destroy,
                 bg="#e74c3c", fg="white", font=("Arial", 10, "bold"), padx=20, pady=6
                 ).pack(side=tk.LEFT, padx=5)

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

        self.btn_add_code = tk.Button(controls, text="➕ Dodaj", font=self.FONT_DEFAULT, bg=self.COLOR_GREEN,
                  fg="white", command=self._add_code, padx=10)
        self.btn_add_code.pack(side=tk.LEFT, padx=2)

        self.btn_edit_code = tk.Button(controls, text="✏️  Edytuj", font=self.FONT_DEFAULT, bg=self.COLOR_WARNING,
                  fg="white", command=self._edit_code, padx=10)
        self.btn_edit_code.pack(side=tk.LEFT, padx=2)

        self.btn_delete_code = tk.Button(controls, text="🗑️  Usuń", font=self.FONT_DEFAULT, bg=self.COLOR_RED,
                  fg="white", command=self._delete_code, padx=10)
        self.btn_delete_code.pack(side=tk.LEFT, padx=2)

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

    def _load_users(self):
        """Load users from master database"""
        try:
            users = rmm.get_users_from_baza(self.master_db_path)
            self.users = {u['id']: u for u in users}

            labels = []
            for u in users:
                label = f"{u['id']} | {u['username']}"
                if u.get('display_name') and u['display_name'] != u['username']:
                    label += f" ({u['display_name']})"
                label += f" [{u['role']}]"
                labels.append(label)

            self.user_combo['values'] = labels

            # Auto-login with last user (silent, no password prompt)
            last_user_id = self._get_last_user_id()
            if last_user_id and last_user_id in self.users:
                user_data = self.users[last_user_id]
                # Find the label for this user
                for label in labels:
                    if label.startswith(f"{last_user_id} |"):
                        self.user_combo.set(label)
                        # Silent login without password prompt
                        self.root.after(100, lambda: self._silent_login(last_user_id, user_data))
                        return

            # No last user or not found - set first user
            if labels:
                self.user_combo.set(labels[0])

        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można załadować użytkowników:\n{e}")
            self.status_bar.config(text="❌ Błąd ładowania użytkowników", fg="red")

    def prompt_password(self, username: str) -> dict:
        """Password dialog (like RM_MANAGER)"""
        dlg = tk.Toplevel(self.root)
        dlg.title(f"Logowanie: {username}")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.geometry("420x180")

        # Center on parent window
        dlg.update_idletasks()
        parent_width = self.root.winfo_width()
        parent_height = self.root.winfo_height()
        parent_x = self.root.winfo_x()
        parent_y = self.root.winfo_y()
        x = parent_x + (parent_width // 2) - (420 // 2)
        y = parent_y + (parent_height // 2) - (180 // 2)
        dlg.geometry(f"420x180+{x}+{y}")

        frm = tk.Frame(dlg, padx=25, pady=20)
        frm.pack(fill=tk.BOTH, expand=True)
        tk.Label(frm, text=f"Podaj hasło dla: {username}",
                 font=("Arial", 11, "bold")).pack(pady=(0, 15))
        tk.Label(frm, text="Hasło:").pack(anchor="w")
        var_pwd = tk.StringVar()
        entry_pwd = tk.Entry(frm, textvariable=var_pwd, show="*", width=35, font=("Arial", 10))
        entry_pwd.pack(pady=5, fill=tk.X)
        dlg.after(50, entry_pwd.focus_force)

        result = {"ok": False, "password": ""}

        def on_ok():
            result["ok"] = True
            result["password"] = var_pwd.get()
            dlg.destroy()

        def on_cancel():
            dlg.destroy()

        entry_pwd.bind("<Return>", lambda e: on_ok())

        btn_frame = tk.Frame(frm)
        btn_frame.pack(pady=15, fill=tk.X)
        tk.Button(btn_frame, text="✅ OK", command=on_ok, width=12, bg="#27ae60", fg="white").pack(side=tk.LEFT, padx=5, expand=True)
        tk.Button(btn_frame, text="❌ Anuluj", command=on_cancel, width=12, bg="#e74c3c", fg="white").pack(side=tk.LEFT, padx=5, expand=True)
        dlg.wait_window()
        return result

    def _silent_login(self, user_id, user_data):
        """Silent auto-login without password prompt"""
        try:
            self.current_user_id = user_id
            self.current_user = user_data['username']

            # Save last user ID
            self._save_last_user(user_id)

            # Update lock manager with real username
            if self.lock_manager:
                self.lock_manager.update_user_name(user_data['username'])

            self.login_status.config(
                text=f"✅ Zalogowany: {user_data['username']} [{user_data['role']}]",
                foreground="green"
            )
            self.status_bar.config(text=f"✅ Zalogowany jako {user_data['username']}", fg="#27ae60")
        except Exception as e:
            print(f"⚠️ Silent login error: {e}")

    def _on_user_selected(self, event=None):
        """Handle user selection from combo"""
        selected = self.user_combo.get()
        if not selected or "|" not in selected:
            return

        try:
            user_id = int(selected.split("|")[0].strip())
        except ValueError:
            return

        user_data = self.users.get(user_id)
        if not user_data:
            messagebox.showerror("Błąd", "Użytkownik nie znaleziony")
            return

        username = user_data['username']
        stored_hash = user_data.get('password_hash')

        # Verify password if set
        if stored_hash:
            result = self.prompt_password(username)
            if not result["ok"]:
                self.user_combo.set("")
                return
            entered_hash = hashlib.sha256(result["password"].encode()).hexdigest()
            if entered_hash != stored_hash:
                messagebox.showerror("Błąd logowania", "Nieprawidłowe hasło!")
                self.user_combo.set("")
                return

        # Login successful
        self.current_user_id = user_id
        self.current_user = username

        # Save last user ID
        self._save_last_user(user_id)

        # Update lock manager with real username
        if self.lock_manager:
            self.lock_manager.update_user_name(username)

        self.login_status.config(
            text=f"✅ Zalogowany: {username} [{user_data['role']}]",
            foreground="green"
        )
        self.status_bar.config(text=f"✅ Zalogowany jako {username}", fg="#27ae60")

    def _on_closing(self):
        """Handle application closing with lock warning"""
        # Cancel refresh job
        if hasattr(self, '_refresh_job'):
            self.root.after_cancel(self._refresh_job)

        # If user has a lock, show warning dialog
        if self.have_lock and self.selected_project_id is not None:
            dlg = tk.Toplevel(self.root)
            dlg.title("⚠️ Masz lock!")
            dlg.transient(self.root)
            dlg.grab_set()
            dlg.resizable(False, False)
            dlg.geometry("600x220")

            result = {"action": None}

            # Main frame
            main_frame = tk.Frame(dlg, bg="#f8f9fa", padx=20, pady=20)
            main_frame.pack(fill=tk.BOTH, expand=True)

            # Message
            project_name = self.project_names.get(
                self.selected_project_id, f"Projekt {self.selected_project_id}"
            )
            tk.Label(
                main_frame,
                text=f"🔒 Masz lock na projekcie: {project_name}",
                bg="#f8f9fa",
                font=("Arial", 12, "bold"),
                fg="#2c3e50"
            ).pack(pady=(0, 10))

            tk.Label(
                main_frame,
                text="Co chcesz zrobić przed zamknięciem aplikacji?",
                bg="#f8f9fa",
                font=("Arial", 10),
                fg="#34495e"
            ).pack(pady=(0, 25))

            # Button frame
            btn_frame = tk.Frame(main_frame, bg="#f8f9fa")
            btn_frame.pack(anchor=tk.CENTER)

            def on_release():
                result["action"] = "release"
                dlg.destroy()

            def on_cancel():
                result["action"] = "cancel"
                dlg.destroy()

            def on_abort():
                result["action"] = "abort"
                dlg.destroy()

            # Buttons
            tk.Button(
                btn_frame,
                text="✅ Zwolnić lock",
                command=on_release,
                width=18,
                height=2,
                bg="#27ae60",
                fg="white",
                font=("Arial", 9, "bold")
            ).grid(row=0, column=0, padx=8, pady=5)

            tk.Button(
                btn_frame,
                text="🗑️ Anulować lock\n(DISCARD)",
                command=on_cancel,
                width=18,
                height=2,
                bg="#e67e22",
                fg="white",
                font=("Arial", 9, "bold")
            ).grid(row=0, column=1, padx=8, pady=5)

            tk.Button(
                btn_frame,
                text="❌ Nie zamykaj",
                command=on_abort,
                width=18,
                height=2,
                bg="#95a5a6",
                fg="white",
                font=("Arial", 9)
            ).grid(row=0, column=2, padx=8, pady=5)

            dlg.wait_window()

            # Handle result
            if result["action"] == "release":
                # Release lock normally
                if self.lock_manager:
                    try:
                        self.lock_manager.release_project_lock(self.selected_project_id)
                    except Exception:
                        pass
            elif result["action"] == "cancel":
                # Discard lock
                if self.lock_manager:
                    try:
                        self.lock_manager.force_delete_lock(self.selected_project_id)
                    except Exception:
                        pass
            elif result["action"] == "abort":
                # Don't close
                return

        # Clean up and close
        self.root.destroy()

    def _schedule_refresh(self):
        """Schedule automatic refresh of lock statuses"""
        self._update_lock_status()
        self._refresh_job = self.root.after(3000, self._schedule_refresh)

    def _update_lock_status(self):
        """Update lock statuses for all projects in combo"""
        try:
            current_values = list(self.project_combo['values'])
            if not current_values:
                return

            current_selection = self.project_combo.get()
            new_values = []

            for combo_text in current_values:
                # Find the PID for this combo text
                pid = None
                for text, p in self.combo_to_pid.items():
                    if text == combo_text:
                        pid = p
                        break

                if not pid:
                    new_values.append(combo_text)
                    continue

                name = self.project_names.get(pid, f"Projekt {pid}")

                # Check current lock status
                try:
                    lock_file = Path(self.locks_dir) / f"project_{pid}.lock"
                    if lock_file.exists():
                        with open(lock_file, 'r', encoding='utf-8') as f:
                            lock_data = json.load(f)
                            if lock_data.get('user'):
                                new_text = f"[A]     {name} 🔒 [{lock_data['user']}]"
                            else:
                                new_text = f"[A]     {name}"
                    else:
                        new_text = f"[A]     {name}"
                except Exception:
                    new_text = combo_text

                new_values.append(new_text)

            # Update combo if changed
            if new_values != current_values:
                # Update mapping
                old_mapping = dict(self.combo_to_pid)
                self.combo_to_pid = {}
                for new_text, old_text in zip(new_values, current_values):
                    if old_text in old_mapping:
                        self.combo_to_pid[new_text] = old_mapping[old_text]

                self.project_combo['values'] = new_values

                # Restore selection
                if current_selection in old_mapping.keys():
                    new_selection = None
                    pid = old_mapping[current_selection]
                    for new_text, p in self.combo_to_pid.items():
                        if p == pid:
                            new_selection = new_text
                            break
                    if new_selection:
                        self.project_combo.set(new_selection)
        except Exception as e:
            print(f"⚠️ Update lock status: {e}")

    def _refresh_projects(self):
        """Manual refresh of projects list"""
        self.status_bar.config(text="🔄 Odświeżanie...")
        self.root.update()
        self._load_projects()
        self.status_bar.config(text="✅ Odświeżono")

    def _apply_project_filter(self):
        """Apply or clear project filter (show only projects without codes)"""
        self._load_projects()

    def _load_projects(self):
        """Load projects from master database"""
        try:
            con = rmm._open_rm_connection(self.master_db_path)

            cursor = con.execute("""
                SELECT
                    project_id as pid,
                    name
                FROM projects
                WHERE COALESCE(active, 1) = 1
                  AND COALESCE(project_type, 'MACHINE') = 'MACHINE'
                  AND LOWER(name) NOT LIKE '%[sym]%'
                ORDER BY name COLLATE NOCASE
            """)

            rows = cursor.fetchall()
            con.close()

            # Build project list
            self.projects = []
            self.project_names = {}

            for row in rows:
                pid = row['pid']
                pname = row['name'] or f"Projekt {pid}"
                self.projects.append(pid)
                self.project_names[pid] = pname

            # Sortowanie identyczne jak RM_BAZA: cyfry malejąco → litery A-Z + numery malejąco
            # PLUS: Projekty [SYM] zawsze na początku
            import re
            def sort_key(pid):
                name_lower = self.project_names.get(pid, '').lower()

                # ⊘ Projekty symulacyjne [SYM] zawsze na samej górze
                if '[sym]' in name_lower:
                    clean_name = name_lower.replace('[sym]', '').strip()
                    return (-1, clean_name, 0, "")

                match = re.match(r'^(\d+)', name_lower)
                if match:
                    return (0, -int(match.group(1)), name_lower)
                match2 = re.match(r'^([a-z]+)(\d+)?', name_lower)
                if match2:
                    letter_part = match2.group(1)
                    num_part = match2.group(2)
                    if num_part:
                        return (1, letter_part, -int(num_part), name_lower)
                    else:
                        return (1, letter_part, 0, name_lower)
                return (1, name_lower, 0, "")

            self.projects.sort(key=sort_key)

            # Add production line names if in a line
            try:
                all_lines = rmm.list_production_lines(self.rm_master_db_path)
                for line in all_lines:
                    for lpid in line['project_ids']:
                        if lpid in self.project_names:
                            self.project_names[lpid] = (
                                f"{self.project_names[lpid]}  [{line['name']}]"
                            )
            except Exception:
                pass

            # Apply filter if enabled
            projects_to_show = self.projects
            if self.filter_without_code.get():
                # Filter: show only projects WITHOUT codes
                projects_to_show = []
                for pid in self.projects:
                    codes = rmm.get_plc_codes(str(self.rm_master_db_path), pid)
                    if not codes:  # No codes
                        projects_to_show.append(pid)
            elif self.filter_with_code.get():
                # Filter: show only projects WITH codes
                projects_to_show = []
                for pid in self.projects:
                    codes = rmm.get_plc_codes(str(self.rm_master_db_path), pid)
                    if codes:  # Has codes
                        projects_to_show.append(pid)

            # Format for combo (like RM_MANAGER does)
            self.combo_to_pid = {}  # Map combo value to project ID
            combo_values = []
            for pid in projects_to_show:
                name = self.project_names.get(pid, f"Projekt {pid}")

                # Add lock info if available (read from lock file)
                try:
                    lock_file = Path(self.locks_dir) / f"project_{pid}.lock"
                    if lock_file.exists():
                        with open(lock_file, 'r', encoding='utf-8') as f:
                            lock_data = json.load(f)
                            if lock_data.get('user'):
                                name = f"{name} 🔒 [{lock_data['user']}]"
                except Exception:
                    pass

                combo_text = f"[A]     {name}"
                combo_values.append(combo_text)
                self.combo_to_pid[combo_text] = pid

            self.project_combo['values'] = combo_values

            if combo_values:
                # Restore previous selection if possible, otherwise select first
                current_selection = self.project_combo.get()
                if current_selection in combo_values:
                    self.project_combo.set(current_selection)
                else:
                    self.project_combo.current(0)
                    if not self.have_lock:  # Only trigger selection callback if not locked
                        self._on_project_selected()

            if self.filter_without_code.get():
                filter_info = " (filtr: bez kodu)"
            elif self.filter_with_code.get():
                filter_info = " (filtr: z kodem)"
            else:
                filter_info = ""
            self.status_bar.config(text=f"✅ Załadowano {len(combo_values)} z {len(self.projects)} projektów{filter_info}")
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można załadować projektów:\n{e}")
            self.status_bar.config(text="❌ Błąd ładowania projektów", fg="red")

    def _on_project_selected(self, event=None):
        """Handle project selection"""
        selection = self.project_combo.get()
        if not selection:
            return

        try:
            new_project_id = self.combo_to_pid.get(selection)
            if not new_project_id:
                return

            # If switching projects while having a lock, warn user
            if self.have_lock and self.selected_project_id is not None and self.selected_project_id != new_project_id:
                current_name = self.project_names.get(self.selected_project_id, f"Projekt {self.selected_project_id}")
                new_name = self.project_names.get(new_project_id, f"Projekt {new_project_id}")

                result = messagebox.askyesnocancel(
                    "Zmiana projektu",
                    f"Masz aktywny lock na projekcie: {current_name}\n\n"
                    f"TAK - zwolnij lock i przejdź do: {new_name}\n"
                    f"ANULUJ - zwolnij lock bez zapisu i przejdź do: {new_name}\n"
                    f"NIE - zostań na projekcie: {current_name}",
                    icon='warning',
                    parent=self.root
                )

                if result is False:  # NIE - stay on current project
                    # Restore previous selection
                    try:
                        old_text = None
                        for text, pid in self.combo_to_pid.items():
                            if pid == self.selected_project_id:
                                old_text = text
                                break
                        if old_text:
                            self.project_combo.set(old_text)
                    except Exception:
                        pass
                    return
                else:  # TAK or ANULUJ - release lock and switch
                    self._release_lock()

            self.selected_project_id = new_project_id
            self.have_lock = False
            self.btn_lock.config(state=tk.NORMAL)
            self.btn_release.config(state=tk.DISABLED)

            # Check if someone else has lock on this project
            try:
                lock_owner = self.lock_manager.get_project_lock_owner(new_project_id) if self.lock_manager else None
                if lock_owner and lock_owner.get('user'):
                    dlg = tk.Toplevel(self.root)
                    dlg.title("⚠️ Projekt zajęty")
                    dlg.transient(self.root)
                    dlg.grab_set()
                    dlg.resizable(False, False)
                    dlg.geometry("500x200")

                    # Center on parent window
                    dlg.update_idletasks()
                    parent_width = self.root.winfo_width()
                    parent_height = self.root.winfo_height()
                    parent_x = self.root.winfo_x()
                    parent_y = self.root.winfo_y()
                    x = parent_x + (parent_width // 2) - (500 // 2)
                    y = parent_y + (parent_height // 2) - (200 // 2)
                    dlg.geometry(f"500x200+{x}+{y}")

                    frm = tk.Frame(dlg, padx=20, pady=20)
                    frm.pack(fill=tk.BOTH, expand=True)

                    project_name = self.project_names.get(new_project_id, f"Projekt {new_project_id}")
                    tk.Label(frm, text=f"🔒 Projekt {project_name} jest zajęty",
                             font=("Arial", 12, "bold")).pack(pady=(0, 10))
                    tk.Label(frm, text=f"Użytkownik: {lock_owner.get('user')}",
                             font=("Arial", 10)).pack(pady=5)
                    tk.Label(frm, text=f"Komputer: {lock_owner.get('computer', 'N/A')}",
                             font=("Arial", 10)).pack(pady=5)

                    locked_at = lock_owner.get('locked_at', 'N/A')
                    tk.Label(frm, text=f"Zalogowany: {locked_at}",
                             font=("Arial", 9), fg="#666").pack(pady=5)

                    btn_frm = tk.Frame(frm)
                    btn_frm.pack(pady=15)
                    tk.Button(btn_frm, text="OK", command=dlg.destroy, width=15,
                              bg="#3498db", fg="white").pack()
            except Exception as e:
                print(f"⚠️ Lock check error: {e}")

            self._load_payment_milestones()
            self._load_codes()

            self.status_bar.config(text=f"✅ Wybrany projekt: {self.project_names.get(new_project_id)}")
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

    def _is_authorized_for_codes(self):
        """Check if current user is authorized to edit PLC codes"""
        if not self.current_user:
            return False
        try:
            # Use same system as RM_MANAGER - check feature permission
            if hasattr(rmm, 'has_feature_permission'):
                return rmm.has_feature_permission(
                    str(self.rm_master_db_path),
                    'plc_codes',
                    self.current_user,
                    self.users.get(self.current_user_id, {}).get('role', 'USER')
                )
            else:
                # Fallback: check plc_authorized_senders
                authorized_senders = rmm.get_plc_authorized_senders(str(self.rm_master_db_path))
                authorized_usernames = {s['username'].upper() for s in authorized_senders}
                return self.current_user.upper() in authorized_usernames
        except Exception as e:
            print(f"⚠️ Authorization check error: {e}")
            return True  # fail-open like RM_MANAGER

    def _load_codes(self):
        """Load PLC codes"""
        if not self.selected_project_id:
            return

        try:
            # Check authorization
            is_authorized = self._is_authorized_for_codes()

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

            # Update button states based on authorization
            if is_authorized:
                self.btn_add_code.config(state=tk.NORMAL)
                self.btn_edit_code.config(state=tk.NORMAL)
                self.btn_delete_code.config(state=tk.NORMAL)
            else:
                self.btn_add_code.config(state=tk.DISABLED)
                self.btn_edit_code.config(state=tk.DISABLED)
                self.btn_delete_code.config(state=tk.DISABLED)

        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można załadować kodów:\n{e}")

    def _acquire_lock(self):
        """Acquire project lock"""
        if not self.selected_project_id:
            messagebox.showwarning("Brak projektu", "Wybierz projekt")
            return

        if not self.current_user:
            messagebox.showerror("Błąd", "Musisz się zalogować")
            return

        try:
            if not self.lock_manager:
                messagebox.showerror("Błąd", "Lock manager nie zainicjalizowany")
                return

            success, error = self.lock_manager.acquire_project_lock(self.selected_project_id)
            if success:
                self.have_lock = True
                self.btn_lock.config(state=tk.DISABLED)
                self.btn_release.config(state=tk.NORMAL)
                self._load_codes()  # Reload codes with lock active
                self.status_bar.config(text=f"🔒 Lock przejęty na projekt {self.selected_project_id}")
            else:
                messagebox.showerror("Błąd", f"Nie można przejąć lock'a:\n{error}")
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można przejąć lock'a:\n{e}")

    def _release_lock(self):
        """Release project lock"""
        if not self.selected_project_id:
            return

        try:
            if self.lock_manager:
                self.lock_manager.release_project_lock(self.selected_project_id)

            self.have_lock = False
            self.btn_lock.config(state=tk.NORMAL)
            self.btn_release.config(state=tk.DISABLED)
            self.status_bar.config(text="🔓 Lock zwolniony")
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można zwolnić lock'a:\n{e}")

    def _add_code(self):
        """Add new PLC code"""
        if not self.selected_project_id:
            messagebox.showwarning("Brak projektu", "Wybierz projekt")
            return

        if not self.current_user:
            messagebox.showerror("Błąd", "Musisz się zalogować")
            return

        if not self._is_authorized_for_codes():
            messagebox.showerror("Brak uprawnień",
                f"Użytkownik '{self.current_user}' nie ma uprawnień do edycji kodów PLC.\n"
                "Skontaktuj się z administratorem.")
            return

        if not self.have_lock:
            messagebox.showerror("Brak lock'a", "Musisz najpierw przejąć lock projektu")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Dodaj nowy kod PLC")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("400x300")

        # Center on parent window (RM_KOD main window)
        dialog.update_idletasks()
        parent_width = self.root.winfo_width()
        parent_height = self.root.winfo_height()
        parent_x = self.root.winfo_x()
        parent_y = self.root.winfo_y()
        x = parent_x + (parent_width // 2) - (400 // 2)
        y = parent_y + (parent_height // 2) - (300 // 2)
        dialog.geometry(f"400x300+{x}+{y}")

        # Main frame with padding
        main_frame = ttk.Frame(dialog, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Configure grid columns for proper centering
        main_frame.columnconfigure(1, weight=1)

        # Type
        ttk.Label(main_frame, text="Typ:", font=self.FONT_DEFAULT).grid(row=0, column=0, sticky='e', padx=(0, 10), pady=10)
        type_var = tk.StringVar(value='PERMANENT')
        ttk.Combobox(main_frame, textvariable=type_var, values=['TEMPORARY', 'PERMANENT'], state='readonly',
                    width=20).grid(row=0, column=1, sticky='w', padx=(0, 10), pady=10)

        # Code
        ttk.Label(main_frame, text="Kod:", font=self.FONT_DEFAULT).grid(row=1, column=0, sticky='e', padx=(0, 10), pady=10)
        code_entry = ttk.Entry(main_frame, width=30, font=self.FONT_DEFAULT)
        code_entry.grid(row=1, column=1, sticky='ew', padx=(0, 10), pady=10)

        # Description
        ttk.Label(main_frame, text="Opis:", font=self.FONT_DEFAULT).grid(row=2, column=0, sticky='ne', padx=(0, 10), pady=10)
        desc_text = tk.Text(main_frame, width=30, height=5, font=self.FONT_DEFAULT)
        desc_text.grid(row=2, column=1, sticky='ew', padx=(0, 10), pady=10)

        def save():
            code = code_entry.get().strip()
            if not code:
                messagebox.showwarning("Błąd", "Podaj kod")
                return

            try:
                rmm.add_plc_code(str(self.rm_master_db_path), self.selected_project_id,
                                type_var.get(), code, desc_text.get('1.0', tk.END).strip(),
                                user=self.current_user or "UNKNOWN")
                self._load_codes()
                dialog.destroy()
                self.status_bar.config(text="✅ Kod dodany")
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można dodać kodu:\n{e}")

        # Buttons - centered
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="Zapisz", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Anuluj", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def _edit_code(self):
        """Edit selected PLC code"""
        if not self._is_authorized_for_codes():
            messagebox.showerror("Brak uprawnień",
                f"Użytkownik '{self.current_user}' nie ma uprawnień do edycji kodów PLC.\n"
                "Skontaktuj się z administratorem.")
            return

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
                rmm.update_plc_code(str(self.rm_master_db_path), code_id,
                                   description=desc_text.get('1.0', tk.END).strip())
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
        if not self._is_authorized_for_codes():
            messagebox.showerror("Brak uprawnień",
                f"Użytkownik '{self.current_user}' nie ma uprawnień do edycji kodów PLC.\n"
                "Skontaktuj się z administratorem.")
            return

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
            rmm.delete_plc_code(str(self.rm_master_db_path), code_id)
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
