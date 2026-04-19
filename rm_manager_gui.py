#!/usr/bin/env python3
"""
============================================================================
RM_MANAGER GUI - Zarządzanie procesami projektów
============================================================================
Interfejs graficzny do zaawansowanego zarządzania statusami projektów:
- START/END etapów
- Multi-period tracking (powroty)
- Timeline visualization
- Critical path analysis
- Dashboard (variance, forecast)
- Sync z RM_BAZA (master.sqlite)

Zgodnie z PROJECT_STATS_MANAGER_SPEC.md
============================================================================
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog, simpledialog
import sqlite3
import os
import json
import glob
import hashlib
import threading
from datetime import datetime, timedelta
from pathlib import Path
import importlib
import calendar as cal_module  # Built-in calendar for date picker

# Plotly for charts
try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.offline import plot
    PLOTLY_AVAILABLE = True
except ImportError:
    print("⚠️ Plotly nie jest zainstalowane. Wykres nie będzie dostępny.")
    print("Zainstaluj: pip install plotly")
    PLOTLY_AVAILABLE = False
    go = px = plot = None

# Matplotlib for embedded charts
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    from matplotlib.figure import Figure
    import matplotlib.patches as patches
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    print("⚠️ Matplotlib nie jest zainstalowane. Wbudowane wykresy nie będą dostępne.")
    print("Zainstaluj: pip install matplotlib")
    MATPLOTLIB_AVAILABLE = False
    plt = mdates = FigureCanvasTkAgg = NavigationToolbar2Tk = Figure = patches = None

import rm_manager as rmm
from rm_manager import ProjectStatus

# Kolejność etapów na wykresach (od góry do dołu)
STAGE_ORDER = {code: idx for idx, (code, _, _, _) in enumerate(rmm.STAGE_DEFINITIONS)}

# Przeładuj moduł aby mieć najnowsze funkcje
try:
    importlib.reload(rmm)
    print("✅ Przeładowano moduł rm_manager")
except Exception as e:
    print(f"⚠️ Nie można przeładować rm_manager: {e}")

# Drag-and-drop support (opcjonalnie)
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False
    print("⚠️ tkinterdnd2 nie zainstalowane - drag-and-drop wyłączony (pip install tkinterdnd2)")
from project_manager import (
    colnames, pick_col, create_project, update_project, delete_project,
    set_project_active, get_project_statuses, set_project_statuses,
    ensure_project_type_column, ensure_projects_stats_columns,
    get_project_db_path as pm_get_project_db_path,
    PROJECT_STATUSES_NEW,
)

try:
    from lock_manager_v2 import ProjectLockManager
    _LOCK_MANAGER_AVAILABLE = True
except ImportError:
    _LOCK_MANAGER_AVAILABLE = False

    class ProjectLockManager:
        """Stub – lock_manager_v2.py niedostępny (tryb jednousytkownikowy)"""
        _STUB = True  # Marker – stub bez prawdziwych locków
        def __init__(self, config):
            self.my_name = config.get('client', {}).get('name', 'Unknown')
            self.locks_folder = None
            print("⚠️  lock_manager_v2.py niedostępny – locki wyłączone (tryb jednousytkownikowy)")

        def update_user_name(self, name): self.my_name = name
        def acquire_project_lock(self, project_id, force=False): return (True, "no-lock")
        def release_project_lock(self, project_id): pass
        def have_project_lock(self, project_id): return True
        def get_project_lock_owner(self, project_id):
            # Zwróć dane własne (nie None!) żeby nie triggerować lock-lost
            return {"user": self.my_name, "computer": "local", "lock_id": "no-lock"}
        def refresh_heartbeat(self, project_id): return True
        def refresh_all_my_locks(self): pass
        def cleanup_all_my_locks(self): pass
        def cleanup_stale_locks(self): return 0
        def force_delete_lock(self, project_id): return False

try:
    from backup_manager import BackupManager
    _BACKUP_MANAGER_AVAILABLE = True
except ImportError:
    _BACKUP_MANAGER_AVAILABLE = False
    print("⚠️  backup_manager.py niedostępny – backupy wyłączone")
    BackupManager = None


# ============================================================================
# Konfiguracja
# ============================================================================

# Ścieżka do pliku konfiguracyjnego (na sztywno)
CONFIG_FILE_PATH = r"C:\RMPAK_CLIENT\manager_sync_config.json"

# Domyślne wartości (jeśli brak JSON)
DEFAULT_MASTER_DB_PATH = "master.sqlite"          # MASTER RM_BAZA (wspólny!)
DEFAULT_RM_MANAGER_DIR = r"C:\RMPAK_CLIENT\RM_MANAGER\rm_manager"  # Folder RM_MANAGER (master + LOCKS)
DEFAULT_RM_MANAGER_DB_PATH = r"C:\RMPAK_CLIENT\RM_MANAGER\rm_manager\rm_manager.sqlite"  # Główna baza RM_MANAGER
DEFAULT_RM_PROJECTS_DIR = r"C:\RMPAK_CLIENT\RM_MANAGER\RM_MANAGER_projects"  # Folder per-projekt baz
DEFAULT_PROJECTS_PATH  = r"Z:\FoldeR\projects"   # Folder projektów RM_BAZA
DEFAULT_BACKUP_DIR = r"C:\RMPAK_CLIENT\RM_MANAGER\backups"  # Folder backupów
DEFAULT_LOCKS_DIR = r"C:\RMPAK_CLIENT\RM_MANAGER\RM_MANAGER_projects\LOCKS"  # Folder locków

# Użytkownik (możesz pobrać z systemu)
CURRENT_USER = os.environ.get('USERNAME', os.environ.get('USER', 'System'))

# Default stage configuration (dla auto-init)
DEFAULT_STAGE_SEQUENCE = [
    'PRZYJETY', 'PROJEKT', 'ELEKTROPROJEKT', 'KOMPLETACJA', 'MONTAZ', 'ELEKTROMONTAZ',
    'TRANSPORT', 'URUCHOMIENIE', 'URUCHOMIENIE_U_KLIENTA', 'FAT',
    'ODBIORY', 'ODBIOR_1', 'ODBIOR_2', 'ODBIOR_3', 'POPRAWKI', 'ZAKONCZONY'
]

# Sub-milestones: milestones wyświetlane WEWNĄTRZ ramki etapu-rodzica (nie jako oddzielne okienka)
# Klucz = etap-rodzic, wartość = lista kodów sub-milestones
SUB_MILESTONES = {
    'ODBIORY': ['FAT', 'ODBIOR_1', 'ODBIOR_2', 'ODBIOR_3', 'TRANSPORT', 'URUCHOMIENIE_U_KLIENTA'],
}
# Flat set kody child milestones (do szybkiego lookup)
_CHILD_MILESTONE_CODES = {code for children in SUB_MILESTONES.values() for code in children}

# Default dependencies (workflow)
# 🔵 Automatyczny graf zależności - zgodny z rm_manager.DEFAULT_DEPENDENCIES
DEFAULT_DEPENDENCIES = [
    # START PROJEKTU
    {'from': 'PRZYJETY',      'to': 'PROJEKT',       'type': 'FS', 'lag': 0},
    
    # SEKWENCJA GŁÓWNA
    {'from': 'PROJEKT',       'to': 'KOMPLETACJA',   'type': 'FS', 'lag': 0},
    {'from': 'KOMPLETACJA',   'to': 'MONTAZ',        'type': 'FS', 'lag': 0},
    
    # ELEKTROPROJEKT → ELEKTROMONTAŻ (niezależny start, blokuje elektromontaż)
    {'from': 'ELEKTROPROJEKT', 'to': 'ELEKTROMONTAZ', 'type': 'FS', 'lag': 0},
    
    # RÓWNOLEGŁOŚĆ - ELEKTROMONTAŻ i MONTAŻ mogą iść równolegle
    {'from': 'MONTAZ',        'to': 'ELEKTROMONTAZ', 'type': 'SS', 'lag': 0},  # SS = Start-to-Start
    
    # URUCHOMIENIE WYMAGA OBU MONTAŻY
    {'from': 'MONTAZ',        'to': 'URUCHOMIENIE',  'type': 'FS', 'lag': 0},
    {'from': 'ELEKTROMONTAZ', 'to': 'URUCHOMIENIE',  'type': 'FS', 'lag': 0},
    
    # KOŃCÓWKA
    {'from': 'URUCHOMIENIE',  'to': 'ODBIORY',       'type': 'FS', 'lag': 0},
    {'from': 'ODBIORY',       'to': 'POPRAWKI',      'type': 'FS', 'lag': 0}
]


# ============================================================================
# Główne okno aplikacji
# ============================================================================

class RMManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("RM_MANAGER - Zarządzanie procesami projektów")
        self.root.geometry("1400x900")
        
        # Okno edycji (referencja)
        self.edit_window = None
        
        # Kolory RM_BAZA theme
        self.COLOR_TOPBAR = "#2c3e50"       # Ciemnoszary top bar
        self.COLOR_GREEN = "#27ae60"        # START button
        self.COLOR_RED = "#e74c3c"          # END button
        self.COLOR_BLUE = "#3498db"         # Info/Charts button
        self.COLOR_LIGHT_BLUE = "#e8f4fd"   # Aktywne etapy (tło)
        self.COLOR_PURPLE = "#9b59b6"       # Inne akcje
        self.COLOR_ORANGE = "#f39c12"       # Warning
        self.COLOR_ORANGE_LIGHT = "#e67e22" # Info
        self.COLOR_TEXT_DARK = "#2c3e50"    # Ciemny tekst
        self.FONT_DEFAULT = ("Arial", 10)
        self.FONT_BOLD = ("Arial", 10, "bold")
        self.FONT_SMALL = ("Arial", 9)
        
        # Ścieżki (wczytane z JSON)
        self.config_file = CONFIG_FILE_PATH
        self.window_geometry = {}  # Zapamiętane pozycje i rozmiary okien
        self.column_widths = {}    # Zapamiętane szerokości kolumn
        self.load_config()
        
        # Inicjalizacja bazy
        self.init_database()
        
        # Stan
        self.selected_project_id = None
        self.projects = []
        self.project_names = {}
        self.read_only_mode = False  # Tryb tylko do odczytu gdy plik nieprawidłowy
        self.file_verification_message = ""  # Wiadomość o weryfikacji
        self._locked_project_id = None  # Aktualnie zablokowany projekt
        self.have_lock = False           # Czy mamy aktywny lock
        self.current_lock_id = None      # ID locka do detekcji wymuszenia przez kogoś
        self.viewing_backup = False      # Czy oglądamy backup (read-only podgląd)
        self.backup_date = None          # Data backupu (np. "2026-04-12")
        self.received_percent = None     # % odebranych elementów (z RM_BAZA)
        self.backup_db_path = None       # Ścieżka do pliku backupu (gdy viewing_backup==True)
        self.timeline_entries = {}       # Słownik Entry widgets z timeline: {stage_code: (start_entry, end_entry)}
        self.last_chart_path = None      # Ścieżka ostatniego wygenerowanego wykresu Plotly
        
        # Matplotlib widgets (wbudowane wykresy)
        self.matplotlib_canvas = None
        self.matplotlib_toolbar = None
        self.embedded_chart_frame = None

        # Debounce odświeżania combo projektów (przy kliknięciu)
        self._projects_last_refresh_ts = 0
        self._projects_refresh_interval_s = 5

        # Użytkownik (logowanie z RM_BAZA)
        self.current_user: str = None          # username
        self.current_user_id: int = None       # id z tabeli users
        self.current_user_role: str = "GUEST"  # rola (ADMIN/USER$$/USER$/USER/GUEST)
        self.user_permissions: dict = {}       # cache uprawnień bieżącego użytkownika
        self._login_thread = None
        self._login_in_progress = False

        # Lock manager (kopia mechanizmu z RM_BAZA)
        lock_config = {
            'client': {'name': CURRENT_USER},
            'locks': {
                'folder': str(Path(self.locks_dir)),
                'stale_seconds': 300
            }
        }
        self.lock_manager = ProjectLockManager(lock_config)

        # Backup manager (kopia mechanizmu z RM_BAZA)
        self.backup_manager = None
        if _BACKUP_MANAGER_AVAILABLE:
            try:
                print("  → Tworzę BackupManager...")
                self.backup_manager = BackupManager(
                    master_path=Path(self.rm_master_db_path),
                    projects_dir=Path(self.rm_projects_dir),
                    backup_dir=Path(self.backup_dir),
                    db_manager=None  # RM_MANAGER nie ma db_manager (bazy per-projekt)
                )
                print("  ✅ BackupManager OK")
            except Exception as e:
                print(f"  ⚠️ Błąd inicjalizacji BackupManager: {e}")
                self.backup_manager = None

        # Heartbeat co 30 sekund (jak RM_BAZA) + cleanup stale locków
        self._heartbeat_job = None
        # Startup: wyczyść locki tego komputera z poprzednich crashów
        # (cleanup_stale_locks sprawdza timeout — nie pomoże przy szybkim restarcie;
        #  cleanup_my_computer_locks kasuje po nazwie komputera — zawsze skuteczny)
        try:
            self.lock_manager.cleanup_my_computer_locks()
        except Exception as e:
            print(f"⚠️ Startup cleanup error: {e}")
        self._start_heartbeat()
        
        # Alarmy - sprawdzaj co 5 minut
        self._alarm_check_job = None
        self._shown_alarm_ids = set()  # ID alarmów już pokazanych użytkownikowi

        # Synchronizacja z RM_BAZA - sprawdzanie codziennie o 23:00
        self._sync_check_job = None
        self._last_sync_check_date = None
        self._start_sync_timer()

        # UI
        self.create_menu()
        self.create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # Przywróć geometrię głównego okna
        state = self.window_geometry.get('main_window_state', 'normal')
        if state == 'zoomed':
            self.root.after(0, lambda: self.root.state('zoomed'))
        else:
            if 'main_window' in self.window_geometry:
                self.root.geometry(self.window_geometry['main_window'])
        
        # Przywróć szerokość lewego panelu (po wyrenderowaniu) - stałe 400px
        def _set_sash():
            self.root.update_idletasks()
            self.main_paned.sash_place(0, 400, 1)
        self.root.after(500, _set_sash)

        # Load data
        self.load_projects()
        # Logowanie użytkownika (auto-login ostatniego)
        self.load_users()
        
        # Sprawdź czy potrzebna synchronizacja przy starcie (w tle, po załadowaniu projektów)
        self.root.after(2000, self._check_startup_sync)
        
        # Sprawdź czy potrzebny codzienny backup (w tle)
        self.root.after(3000, self.run_backup_in_background)

    # ========================================================================
    # Per-projekt helpers + lock lifecycle
    # ========================================================================

    def get_project_db_path(self, project_id: int) -> str:
        """Zwraca ścieżkę do per-projekt bazy: RM_MANAGER_projects/rm_manager_project_{id}.sqlite
        Jeśli viewing_backup==True, zwraca ścieżkę do backupu."""
        if self.viewing_backup and self.backup_db_path:
            return self.backup_db_path
        return rmm.get_project_db_path(self.rm_projects_dir, project_id)

    def _get_all_alarms(self) -> list:
        """Zbierz wszystkie alarmy ze wszystkich projektów (včetně odłożonych)"""
        all_alarms = []
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            pattern = os.path.join(self.rm_projects_dir, "rm_manager_project_*.sqlite")
            for db_path in glob.glob(pattern):
                try:
                    basename = os.path.basename(db_path)
                    pid = int(basename.replace('rm_manager_project_', '').replace('.sqlite', ''))
                    alarms = rmm.get_all_alarms_with_snoozed(db_path, pid, current_time, for_user=self.current_user)
                    for a in alarms:
                        a['_project_db'] = db_path
                        a['_project_name'] = self.project_names.get(pid, f'Projekt {pid}')
                    all_alarms.extend(alarms)
                except Exception:
                    pass
            all_alarms.sort(key=lambda a: a.get('alarm_datetime', ''))
        except Exception:
            pass
        return all_alarms

    def check_alarms(self):
        """Sprawdź aktywne alarmy ze WSZYSTKICH projektów (filtrowane po użytkowniku)"""
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            all_alarms = []
            
            # Przeskanuj wszystkie per-projekt bazy
            pattern = os.path.join(self.rm_projects_dir, "rm_manager_project_*.sqlite")
            for db_path in glob.glob(pattern):
                try:
                    basename = os.path.basename(db_path)
                    pid = int(basename.replace('rm_manager_project_', '').replace('.sqlite', ''))
                    
                    alarms = rmm.get_active_alarms(
                        db_path, pid, current_time,
                        for_user=self.current_user
                    )
                    for a in alarms:
                        a['_project_db'] = db_path
                        a['_project_name'] = self.project_names.get(pid, f'Projekt {pid}')
                    all_alarms.extend(alarms)
                except Exception as e:
                    # Cicho ignoruj błędy (np. brak tabeli stage_alarms w starszych bazach)
                    pass
            
            if all_alarms:
                # Sortuj po dacie alarmu
                all_alarms.sort(key=lambda a: a.get('alarm_datetime', ''))
                
                # Pokazuj okno TYLKO dla NOWYCH alarmów (jeszcze nie pokazanych)
                new_alarms = [a for a in all_alarms if a['id'] not in self._shown_alarm_ids]
                if new_alarms:
                    # Zapisz ID nowych alarmów jako pokazane
                    for alarm in new_alarms:
                        self._shown_alarm_ids.add(alarm['id'])
                    self.show_alarms_notification(all_alarms)  # Pokaż wszystkie (włącznie z nowymi)
        except Exception as e:
            print(f"⚠️ Błąd sprawdzania alarmów: {e}")
        
        # Ustaw następne sprawdzenie za 5 minut
        if hasattr(self, '_alarm_check_job') and self._alarm_check_job is not None:
            self.root.after_cancel(self._alarm_check_job)
        self._alarm_check_job = self.root.after(300_000, self.check_alarms)

    def show_alarms_notification(self, alarms: list):
        """Wyświetl powiadomienie o alarmach z pełnymi informacjami"""
        if not alarms:
            return
        
        # Okno powiadomienia
        notify_win = tk.Toplevel(self.root)
        notify_win.title("⏰ ALARMY")
        notify_win.resizable(True, True)
        notify_win.transient(self.root)
        notify_win.attributes('-topmost', True)
        self._center_window(notify_win, 920, 520)
        
        # Header - licz tylko aktywne alarmy (nie odłożone)
        active_alarms_count = sum(1 for alarm in alarms if not alarm.get('is_snoozed', False))
        header = tk.Frame(notify_win, bg=self.COLOR_RED, pady=10)
        header.pack(fill=tk.X)
        
        alarm_count_label = tk.Label(
            header,
            text=f"⏰ Masz {active_alarms_count} aktywnych alarmów!" + 
                 (f" (+ {len(alarms) - active_alarms_count} odłożonych)" if len(alarms) - active_alarms_count > 0 else ""),
            bg=self.COLOR_RED,
            fg="white",
            font=("Arial", 14, "bold")
        )
        alarm_count_label.pack()
        
        # Funkcja do aktualizacji licznika alarmów
        def update_alarm_count():
            active_count = sum(1 for iid, alarm in alarm_data_map.items() if not alarm.get('is_snoozed', False))
            snoozed_count = len(alarm_data_map) - active_count
            alarm_count_label.config(text=f"⏰ Masz {active_count} aktywnych alarmów!" + 
                                   (f" (+ {snoozed_count} odłożonych)" if snoozed_count > 0 else ""))
        
        # Tabela alarmów (Treeview)
        tree_frame = tk.Frame(notify_win, bg="white")
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        tree_scroll_y = tk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        tree_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        columns = ("check", "project", "datetime", "topic", "message", "created_by", "assigned_to")
        alarms_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            yscrollcommand=tree_scroll_y.set,
            selectmode='extended'
        )
        alarms_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll_y.config(command=alarms_tree.yview)
        
        # Konfiguracja tagów dla kolorów
        alarms_tree.tag_configure('snoozed', foreground='#3498db')  # niebieski dla odłożonych
        alarms_tree.tag_configure('active', foreground='black')     # czarny dla aktywnych
        
        alarms_tree.heading("check", text="✓")
        alarms_tree.heading("project", text="Projekt")
        alarms_tree.heading("datetime", text="Data/czas")
        alarms_tree.heading("topic", text="Temat")
        alarms_tree.heading("message", text="Wiadomość")
        alarms_tree.heading("created_by", text="Ustawił")
        alarms_tree.heading("assigned_to", text="Dla kogo")
        
        alarms_tree.column("check", width=30, anchor='center', stretch=False)
        alarms_tree.column("project", width=140, stretch=False)
        alarms_tree.column("datetime", width=120, anchor='center', stretch=False)
        alarms_tree.column("topic", width=150)
        alarms_tree.column("message", width=200)
        alarms_tree.column("created_by", width=90)
        alarms_tree.column("assigned_to", width=90)
        
        # Przechowuj dane alarmów wg iid
        alarm_data_map = {}
        checked_items = set()
        
        for alarm in alarms:
            pid = alarm.get('project_id', '?')
            pname = alarm.get('_project_name', self.project_names.get(pid, ''))
            project_display = pname or f"Projekt {pid}"
            if len(project_display) > 25:
                project_display = project_display[:22] + '...'
            
            topic_title = alarm.get('topic_title', '—')
            stage = alarm.get('stage_code', '')
            topic_display = f"[{stage}] {topic_title}" if stage else topic_title
            
            msg = alarm.get('message', '') or ''
            if alarm['target_type'] == 'NOTE' and alarm.get('note_text'):
                msg = msg or alarm['note_text']
            if len(msg) > 50:
                msg = msg[:47] + '...'
            
            assigned = alarm.get('assigned_to', 'ALL') or 'ALL'
            if assigned == 'ALL':
                assigned = 'Wszyscy'
            
            # Określ tag dla kolorowania
            row_tag = 'snoozed' if alarm.get('is_snoozed', False) else 'active'
            
            iid = alarms_tree.insert('', tk.END, values=(
                '☐',
                project_display,
                alarm['alarm_datetime'][:16],
                topic_display,
                msg,
                alarm.get('created_by', '—') or '—',
                assigned
            ), tags=(row_tag,))
            alarm_data_map[iid] = alarm
        
        # Toggle checkbox po kliknięciu
        def on_tree_click(event):
            region = alarms_tree.identify_region(event.x, event.y)
            if region != 'cell':
                return
            col = alarms_tree.identify_column(event.x)
            item = alarms_tree.identify_row(event.y)
            if not item:
                return
            # Kolumna #1 = check
            if col == '#1':
                if item in checked_items:
                    checked_items.discard(item)
                    vals = list(alarms_tree.item(item, 'values'))
                    vals[0] = '☐'
                    alarms_tree.item(item, values=vals)
                else:
                    checked_items.add(item)
                    vals = list(alarms_tree.item(item, 'values'))
                    vals[0] = '☑'
                    alarms_tree.item(item, values=vals)
        
        alarms_tree.bind('<ButtonRelease-1>', on_tree_click)
        
        # Podwójne kliknięcie → otwórz Notatki z podświetlonym tematem/notatką
        def on_tree_double_click(event):
            item = alarms_tree.identify_row(event.y)
            if not item or item not in alarm_data_map:
                return
            alarm = alarm_data_map[item]
            self._open_notes_from_alarm(alarm)
        
        alarms_tree.bind('<Double-1>', on_tree_double_click)
        
        # Info: kliknij dwukrotnie aby otworzyć notatki
        info_label = tk.Label(
            notify_win,
            text="💡 Zaznacz checkbox ✓ aby wybrać do potwierdzenia  •  Kliknij dwukrotnie wiersz aby otworzyć Notatki",
            font=("Arial", 8, "italic"),
            fg="gray"
        )
        info_label.pack(pady=(0, 5))
        
        # Helper: pobierz DB path dla alarmu (per-alarm, nie per-selected)
        def _get_alarm_db(alarm):
            return alarm.get('_project_db') or self.get_project_db_path(alarm['project_id'])
        
        # Przyciski
        btn_frame = tk.Frame(notify_win, bg="white", pady=10)
        btn_frame.pack(fill=tk.X)
        
        def acknowledge_checked():
            if not checked_items:
                messagebox.showwarning("Brak wyboru", "Zaznacz alarmy do potwierdzenia (checkbox ✓)")
                return
            
            try:
                count = 0
                for iid in list(checked_items):
                    alarm = alarm_data_map.get(iid)
                    if alarm:
                        rmm.acknowledge_alarm(_get_alarm_db(alarm), alarm['id'], self.current_user)
                        # Usuń z listy pokazanych (alarm już nie istnieje)
                        self._shown_alarm_ids.discard(alarm['id'])
                        count += 1
                        # Usuń z listy po potwierdzeniu
                        alarms_tree.delete(iid)
                        checked_items.discard(iid)
                        del alarm_data_map[iid]
                
                update_alarm_count()
                if hasattr(self, 'timeline_frame'):
                    self.refresh_timeline()
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można potwierdzić alarmu:\n{e}")
        
        def acknowledge_all():
            try:
                for iid, alarm in list(alarm_data_map.items()):
                    rmm.acknowledge_alarm(_get_alarm_db(alarm), alarm['id'], self.current_user)
                    # Usuń z listy pokazanych (alarm już nie istnieje)
                    self._shown_alarm_ids.discard(alarm['id'])
                    # Usuń z listy po potwierdzeniu
                    alarms_tree.delete(iid)
                
                # Wyczyść mapy
                alarm_data_map.clear()
                checked_items.clear()
                
                update_alarm_count()
                if hasattr(self, 'timeline_frame'):
                    self.refresh_timeline()
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można potwierdzić alarmów:\n{e}")
        
        def snooze_checked():
            """Powiadom później - odłóż zaznaczone alarmy na następny dzień"""
            if not checked_items:
                messagebox.showwarning("Brak wyboru", "Zaznacz alarmy do odłożenia (checkbox ✓)")
                return
            
            try:
                tomorrow = (datetime.now() + timedelta(days=1)).replace(
                    hour=9, minute=0, second=0
                ).strftime("%Y-%m-%d %H:%M:%S")
                
                count = 0
                for iid in list(checked_items):
                    alarm = alarm_data_map.get(iid)
                    if alarm:
                        rmm.snooze_alarm(_get_alarm_db(alarm), alarm['id'], tomorrow)
                        # Usuń z listy pokazanych (alarm pojawi się ponownie później)
                        self._shown_alarm_ids.discard(alarm['id'])
                        count += 1
                        # Oznacz jako odłożony w danych i wizualnie
                        alarm['is_snoozed'] = True
                        alarms_tree.item(iid, tags=('snoozed',))
                        checked_items.discard(iid)
                
                messagebox.showinfo("🔔 Odłożono", f"Odłożono {count} alarmów.\nPowiadomienie pojawi się jutro o 9:00")
                update_alarm_count()
                
                # Odśwież oś czasu
                if hasattr(self, 'refresh_timeline'):
                    self.refresh_timeline()
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można odłożyć alarmu:\n{e}")
        
        def snooze_all():
            """Powiadom później - odłóż wszystkie alarmy na następny dzień"""
            try:
                tomorrow = (datetime.now() + timedelta(days=1)).replace(
                    hour=9, minute=0, second=0
                ).strftime("%Y-%m-%d %H:%M:%S")
                
                for alarm in alarms:
                    if not alarm.get('is_snoozed', False):  # Tylko aktywne alarmy można odłożyć
                        rmm.snooze_alarm(_get_alarm_db(alarm), alarm['id'], tomorrow)
                        # Usuń z listy pokazanych (alarm pojawi się ponownie później)
                        self._shown_alarm_ids.discard(alarm['id'])
                
                # Oznacz wszystkie aktywne jako odłożone
                for iid, alarm in alarm_data_map.items():
                    if not alarm.get('is_snoozed', False):
                        alarm['is_snoozed'] = True
                        alarms_tree.item(iid, tags=('snoozed',))
                
                active_count = sum(1 for a in alarms if not a.get('is_snoozed', False))
                messagebox.showinfo("🔔 Odłożono", f"Odłożono {active_count} aktywnych alarmów.\nPowiadomienie pojawi się jutro o 9:00")
                checked_items.clear()
                update_alarm_count()
                
                # Odśwież oś czasu
                if hasattr(self, 'refresh_timeline'):
                    self.refresh_timeline()
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można odłożyć alarmów:\n{e}")
        
        tk.Button(
            btn_frame,
            text="✅ Potwierdź zaznaczone",
            command=acknowledge_checked,
            bg=self.COLOR_GREEN,
            fg="white",
            font=self.FONT_BOLD,
            width=20
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="✅ Potwierdź wszystkie",
            command=acknowledge_all,
            bg=self.COLOR_ORANGE,
            fg="white",
            font=self.FONT_BOLD,
            width=20
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="🔔 Powiadom później (zaznaczone)",
            command=snooze_checked,
            bg="#3498db",
            fg="white",
            font=self.FONT_BOLD,
            width=26
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="🔔 Odłóż wszystkie",
            command=snooze_all,
            bg="#2980b9",
            fg="white",
            font=self.FONT_BOLD,
            width=18
        ).pack(side=tk.LEFT, padx=5)
        
        def close_notification():
            """Zamknij okno powiadomienia i przywróć focus do głównego okna"""
            notify_win.destroy()
            self.root.focus_force()
        
        tk.Button(
            btn_frame,
            text="❌ Zamknij",
            command=close_notification,
            bg=self.COLOR_RED,
            fg="white",
            font=self.FONT_BOLD,
            width=12
        ).pack(side=tk.RIGHT, padx=5)

    def _open_notes_from_alarm(self, alarm: dict):
        """Otwórz okno Notatki z podświetlonym tematem lub notatką z alarmu"""
        alarm_project_id = alarm.get('project_id')
        if not alarm_project_id:
            return
        
        # Przełącz na projekt alarmu jeśli inny niż bieżący
        if alarm_project_id != self.selected_project_id:
            # Ustaw projekt w combo (jeśli jest na liście)
            if alarm_project_id in self.projects:
                self.selected_project_id = alarm_project_id
                # Odśwież UI (opcjonalnie - show_notes_window i tak działa per project_db)
        
        project_db = self.get_project_db_path(alarm_project_id)
        stage_code = alarm.get('stage_code', '')
        
        if alarm['target_type'] == 'TOPIC':
            # Znajdź indeks tematu w liście
            topic_id = alarm['target_id']
            topics = rmm.get_topics(project_db, alarm_project_id, stage_code)
            topic_index = None
            for i, t in enumerate(topics):
                if t['id'] == topic_id:
                    topic_index = i
                    break
            self.show_notes_window(stage_code=stage_code, topic_index=topic_index)
        
        elif alarm['target_type'] == 'NOTE':
            # Znajdź temat nadrzędny notatki
            topic_id = alarm.get('topic_id')
            if not topic_id:
                # Pobierz topic_id z bazy
                try:
                    con = rmm._open_rm_connection(project_db)
                    note = con.execute(
                        "SELECT topic_id FROM stage_notes WHERE id = ?",
                        (alarm['target_id'],)
                    ).fetchone()
                    con.close()
                    if note:
                        topic_id = note['topic_id']
                except Exception:
                    pass
            
            if topic_id and stage_code:
                topics = rmm.get_topics(project_db, alarm_project_id, stage_code)
                topic_index = None
                for i, t in enumerate(topics):
                    if t['id'] == topic_id:
                        topic_index = i
                        break
                self.show_notes_window(stage_code=stage_code, topic_index=topic_index)
            else:
                self.show_notes_window(stage_code=stage_code)

    def _start_heartbeat(self):
        """Uruchom cykliczne odświeżanie heartbeat (co 30 s) + cleanup stale locków.
        
        Wzór z RM_BAZA: heartbeat w osobnym wątku (nie blokuje GUI),
        cleanup_stale_locks() przy każdym ticku.
        """
        import threading

        def _heartbeat_worker():
            try:
                self.lock_manager.refresh_all_my_locks()
                self.lock_manager.cleanup_stale_locks()

                # Detekcja wymuszenia: sprawdź czy lock_id się zmienił
                # Pomijaj dla stuba (tryb jednousytkownikowy – brak prawdziwych locków)
                if (self.have_lock and self.current_lock_id and self.selected_project_id
                        and not getattr(self.lock_manager, '_STUB', False)):
                    current_owner = self.lock_manager.get_project_lock_owner(self.selected_project_id)
                    lock_lost = False
                    reason = ""
                    if not current_owner:
                        lock_lost = True
                        reason = "Lock wygasł lub został zwolniony przez innego użytkownika"
                    elif current_owner.get('lock_id') != self.current_lock_id:
                        new_owner = current_owner.get('user', 'Unknown')
                        new_comp  = current_owner.get('computer', 'Unknown')
                        lock_lost = True
                        reason = f"Lock został wymuszony przez:\n{new_owner}@{new_comp}"
                    if lock_lost:
                        # _on_lock_lost musi być wywołane z GUI thread
                        self.root.after(0, lambda r=reason: self._on_lock_lost(r))
            except Exception as e:
                print(f"⚠️ Heartbeat error: {e}")

        # Uruchom w osobnym wątku (nie blokuj GUI - wzór RM_BAZA)
        t = threading.Thread(target=_heartbeat_worker, daemon=True)
        t.start()

        # Zaplanuj następny tick co 30 sekund (jak RM_BAZA)
        self._heartbeat_job = self.root.after(30_000, self._start_heartbeat)

    def _on_closing(self):
        """Zwolnij locki i zamknij aplikację"""
        if self._heartbeat_job:
            self.root.after_cancel(self._heartbeat_job)
        
        # Anuluj sprawdzanie alarmów
        if hasattr(self, '_alarm_check_job') and self._alarm_check_job is not None:
            self.root.after_cancel(self._alarm_check_job)
        
        # Dialog ostrzegawczy gdy użytkownik ma lock (wzór RM_BAZA)
        if self.have_lock and self._locked_project_id is not None:
            dlg = tk.Toplevel(self.root)
            dlg.title("⚠️ Masz lock!")
            dlg.transient(self.root)
            dlg.grab_set()
            dlg.resizable(False, False)
            self._center_window(dlg, 650, 250)
            
            result = {"action": None}
            
            # Główny frame
            main_frame = tk.Frame(dlg, bg="#f8f9fa")
            main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
            
            # Komunikat
            project_name = self.project_names.get(
                self._locked_project_id, f"Projekt {self._locked_project_id}"
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
            
            # Frame na przyciski
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
            
            # Przyciski - 3 w poziomie
            tk.Button(
                btn_frame,
                text="✅ Zwolnić lock\n(zapisz do bazy)",
                command=on_release,
                width=16,
                height=3,
                bg="#27ae60",
                fg="white",
                font=("Arial", 9, "bold"),
                relief=tk.RAISED,
                bd=2,
                cursor="hand2"
            ).grid(row=0, column=0, padx=8, pady=5)
            
            tk.Button(
                btn_frame,
                text="🗑️ Anulować lock\n(DISCARD zmiany)",
                command=on_cancel,
                width=16,
                height=3,
                bg="#e67e22",
                fg="white",
                font=("Arial", 9, "bold"),
                relief=tk.RAISED,
                bd=2,
                cursor="hand2"
            ).grid(row=0, column=1, padx=8, pady=5)
            
            tk.Button(
                btn_frame,
                text="❌ Nie zamykaj\n(pozostaw otwarty)",
                command=on_abort,
                width=16,
                height=3,
                bg="#95a5a6",
                fg="white",
                font=("Arial", 9),
                relief=tk.RAISED,
                bd=2,
                cursor="hand2"
            ).grid(row=0, column=2, padx=8, pady=5)
            
            # Czekaj na wybór
            dlg.wait_window()
            
            # Wykonaj akcję
            if result["action"] == "release":
                try:
                    self.save_all_templates()  # Zapisz zmiany
                    self.lock_manager.release_project_lock(self._locked_project_id)
                except Exception as e:
                    messagebox.showerror("Błąd", f"Nie można zwolnić locka:\n{e}")
                    return  # NIE zamykaj aplikacji
            elif result["action"] == "cancel":
                try:
                    self.lock_manager.release_project_lock(self._locked_project_id)
                except Exception:
                    pass
            elif result["action"] == "abort":
                return  # NIE zamykaj aplikacji
            else:
                return  # Zamknięto dialog bez wyboru - NIE zamykaj
        
        # Cleanup wszystkich locków przed zamknięciem
        self.lock_manager.cleanup_all_my_locks()
        
        # Zapisz geometrię głównego okna
        try:
            state = self.root.state()
            self.window_geometry['main_window_state'] = state
            if state not in ('zoomed', 'iconic'):
                self.window_geometry['main_window'] = self.root.geometry()
            # Zapisz szerokość lewego panelu
            try:
                paned_pos = self.main_paned.sash_coord(0)[0]
                if paned_pos > 0:
                    self.window_geometry['main_paned_sash'] = paned_pos
            except Exception:
                pass
            self.save_config()
        except Exception:
            pass
        
        self.root.destroy()

    def _start_sync_timer(self):
        """Uruchom timer sprawdzania synchronizacji (cel: raz dziennie o 23:00)
        
        Timer sprawdza co 60 sekund czy:
        1. Jest godzina 23:00 → oznacz że potrzebny sync
        2. Dzień się zmienił od ostatniego sprawdzenia → jeśli nie było sync dzisiaj, wykonaj
        """
        try:
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            current_hour = now.hour
            
            # Sprawdź czy potrzebna synchronizacja
            if rmm.should_sync_today(self.rm_master_db_path):
                # Jeśli godzina 23:00 lub aplikacja właśnie wystartowała (różny dzień od ostatniego sprawdzenia)
                if current_hour == 23 or (self._last_sync_check_date and self._last_sync_check_date != today):
                    print(f"🔄 Automatyczna synchronizacja: {today} {now.strftime('%H:%M')}")
                    self._run_background_sync()
            
            # Zapamiętaj dzisiejszą datę
            self._last_sync_check_date = today
            
        except Exception as e:
            print(f"⚠️ Błąd sync timer: {e}")
        
        # Następne sprawdzenie za 60 sekund
        self._sync_check_job = self.root.after(60_000, self._start_sync_timer)

    def _check_startup_sync(self):
        """Sprawdź przy starcie aplikacji czy potrzebna synchronizacja dzisiaj
        
        Jeśli nie było synchronizacji dzisiaj, uruchom w tle.
        """
        try:
            if rmm.should_sync_today(self.rm_master_db_path):
                print("🔄 Startup: wykryto brak synchronizacji dzisiaj, uruchamiam w tle...")
                self._run_background_sync()
        except Exception as e:
            print(f"⚠️ Błąd startup sync: {e}")

    def check_and_run_daily_backup(self):
        """Sprawdź czy backup dzisiaj był wykonany, jeśli nie - wykonaj
        
        Wzorowane na RM_BAZA - sprawdza czy istnieje backup z dzisiejszą datą.
        """
        if not self.backup_manager:
            return
        
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            master_backup_file = self.backup_manager.master_backup_dir / f"master_{today}.sqlite"
            
            if master_backup_file.exists():
                print(f"  ℹ️  Backup już wykonany dzisiaj ({today}), pomijam")
                return
            
            # Wykonaj codzienny backup (master + wszystkie projekty)
            print(f"  📦 Wykonuję codzienny backup ({today})...")
            self.backup_manager.run_daily_backup()
            print(f"  ✅ Codzienny backup zakończony")
        
        except Exception as e:
            print(f"  ⚠️  Błąd backupu (niegroźne): {e}")
            import traceback
            traceback.print_exc()
    
    def run_backup_in_background(self):
        """Uruchom backup w tle bez blokowania GUI"""
        if not self.backup_manager:
            return
        
        def do_backup():
            try:
                self.check_and_run_daily_backup()
            except Exception as e:
                print(f"⚠️ Błąd backupu w tle: {e}")
        
        # Backup w osobnym wątku (NIE dotyka GUI, więc bezpieczne)
        import threading
        backup_thread = threading.Thread(target=do_backup, daemon=True)
        backup_thread.start()
        print("🔄 Backup uruchomiony w tle...")

    def _run_background_sync(self):
        """Uruchom synchronizację wszystkich projektów w tle (thread)"""
        def sync_worker():
            try:
                print("🔄 Background sync rozpoczęty...")
                synced = rmm.sync_all_projects(
                    self.rm_master_db_path,
                    self.rm_projects_dir,
                    self.master_db_path,
                    user=self.current_user,
                    lock_manager=self.lock_manager
                )
                print(f"✅ Background sync zakończony: {synced} projektów")
                
                # Zaktualizuj status bar w głównym wątku
                self.root.after(0, lambda: self.status_bar.config(
                    text=f"🔄 Zsynchronizowano {synced} projektów z RM_BAZA",
                    fg="#27ae60"
                ))
            except Exception as e:
                print(f"❌ Błąd background sync: {e}")
                import traceback
                traceback.print_exc()
                
                self.root.after(0, lambda: self.status_bar.config(
                    text=f"⚠️ Błąd synchronizacji: {e}",
                    fg="#e74c3c"
                ))
        
        # Uruchom w osobnym wątku aby nie blokować GUI
        sync_thread = threading.Thread(target=sync_worker, daemon=True)
        sync_thread.start()

    def _acquire_project_lock(self, project_id: int, force: bool = False) -> bool:
        """Wewnętrzna próba przejęcia locka projektu. Ustawia have_lock + current_lock_id."""
        success, lock_id = self.lock_manager.acquire_project_lock(project_id, force=force)
        if success:
            self._locked_project_id = project_id
            self.have_lock = True
            self.current_lock_id = lock_id
        return success

    def _release_current_lock(self):
        """Zwolnij lock aktualnie wybranego projektu"""
        # Zapisz wszystkie niezapisane zmiany z timeline
        self.save_all_templates()
        
        # Backup projektu przed zwolnieniem locka
        if self._locked_project_id is not None and self.backup_manager:
            try:
                print(f"📦 Backup projektu {self._locked_project_id} przed zwolnieniem locka...")
                self.backup_manager.backup_project(self._locked_project_id, skip_checkpoint=True)
                print(f"✅ Backup projektu {self._locked_project_id} zakończony")
            except Exception as e:
                print(f"⚠️ Błąd backupu projektu (niegroźne): {e}")
        
        if self._locked_project_id is not None:
            self.lock_manager.release_project_lock(self._locked_project_id)
            self._locked_project_id = None
        self.have_lock = False
        self.current_lock_id = None

    # ========================================================================
    # Funkcje pomocnicze dla dat DD-MM-YYYY
    # ========================================================================
    
    def parse_date_ddmmyyyy(self, date_str):
        """Parse DD-MM-YYYY format to datetime object"""
        if not date_str or not date_str.strip():
            return None
        try:
            return datetime.strptime(date_str.strip(), '%d-%m-%Y')
        except ValueError:
            raise ValueError(f"Nieprawidłowy format daty: '{date_str}'. Użyj formatu: DD-MM-YYYY (np. 01-04-2026)")
    
    def format_date_ddmmyyyy(self, date_obj_or_str):
        """Format datetime or ISO string (YYYY-MM-DD) to DD-MM-YYYY for display"""
        if not date_obj_or_str:
            return ""
        if isinstance(date_obj_or_str, datetime):
            return date_obj_or_str.strftime('%d-%m-%Y')
        # If it's ISO string YYYY-MM-DD from database, convert it
        try:
            # Obsługa formatu z godziną (YYYY-MM-DD HH:MM)
            date_str = str(date_obj_or_str)
            if ' ' in date_str:
                date_str = date_str.split()[0]  # Weź tylko datę, pomiń godzinę
            dt = datetime.fromisoformat(date_str)
            return dt.strftime('%d-%m-%Y')
        except:
            return str(date_obj_or_str)  # Return as-is if can't parse
    
    def validate_and_convert_date(self, date_str):
        """Validate DD-MM-YYYY or YYYY-MM-DD and convert to YYYY-MM-DD (ISO) for database storage
        Returns: (is_valid, iso_date_or_error_msg)
        """
        if not date_str or not date_str.strip():
            return (True, None)  # Empty is valid (NULL in DB)
        
        date_str = date_str.strip()
        
        # Try DD-MM-YYYY format first (original)
        try:
            dt = self.parse_date_ddmmyyyy(date_str)
            return (True, dt.strftime('%Y-%m-%d'))  # ISO format for DB
        except ValueError:
            pass  # Try other format
        
        # Try YYYY-MM-DD format (ISO)
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            return (True, dt.strftime('%Y-%m-%d'))  # Already ISO
        except ValueError:
            pass
        
        # Neither format worked
        return (False, f"Nieprawidłowy format daty: '{date_str}'. Użyj formatu: DD-MM-YYYY lub YYYY-MM-DD")

    def open_calendar_picker(self, entry_widget, initial_date=None):
        """Otwórz okno z kalendarzem (czysty tkinter, bez zewnętrznych bibliotek)
        
        Args:
            entry_widget: Widget Entry, do którego zostanie wstawiona wybrana data
            initial_date: Początkowa data (DD-MM-YYYY lub datetime), domyślnie dzisiaj
        """
        # Ustal początkową datę
        if initial_date:
            if isinstance(initial_date, str):
                try:
                    initial_dt = self.parse_date_ddmmyyyy(initial_date)
                except Exception:
                    initial_dt = datetime.now()
            elif isinstance(initial_date, datetime):
                initial_dt = initial_date
            else:
                initial_dt = datetime.now()
        else:
            current_val = entry_widget.get().strip()
            if current_val:
                try:
                    initial_dt = self.parse_date_ddmmyyyy(current_val)
                except Exception:
                    try:
                        initial_dt = datetime.strptime(current_val, '%Y-%m-%d')
                    except Exception:
                        initial_dt = datetime.now()
            else:
                initial_dt = datetime.now()

        cal_window = tk.Toplevel(self.root)
        cal_window.title("📅 Wybierz datę")
        cal_window.resizable(False, False)
        cal_window.transient(self.root)
        cal_window.grab_set()

        # Stan kalendarza
        state = {'year': initial_dt.year, 'month': initial_dt.month, 'selected_day': initial_dt.day}
        DAY_NAMES = ['Pn', 'Wt', 'Śr', 'Cz', 'Pt', 'So', 'Nd']
        MONTH_NAMES = [
            '', 'Styczeń', 'Luty', 'Marzec', 'Kwiecień', 'Maj', 'Czerwiec',
            'Lipiec', 'Sierpień', 'Wrzesień', 'Październik', 'Listopad', 'Grudzień'
        ]

        # ── Nagłówek z nawigacją ──
        nav_frame = tk.Frame(cal_window, bg=self.COLOR_BLUE, pady=6)
        nav_frame.pack(fill=tk.X)

        btn_prev_year = tk.Button(nav_frame, text="«", font=("Arial", 12, "bold"),
                                  bg=self.COLOR_BLUE, fg="white", bd=0, padx=8,
                                  activebackground="#1a5276", activeforeground="white")
        btn_prev_year.pack(side=tk.LEFT, padx=2)

        btn_prev = tk.Button(nav_frame, text="‹", font=("Arial", 14, "bold"),
                             bg=self.COLOR_BLUE, fg="white", bd=0, padx=8,
                             activebackground="#1a5276", activeforeground="white")
        btn_prev.pack(side=tk.LEFT, padx=2)

        month_label = tk.Label(nav_frame, text="", font=("Arial", 11, "bold"),
                               bg=self.COLOR_BLUE, fg="white")
        month_label.pack(side=tk.LEFT, expand=True)

        btn_next = tk.Button(nav_frame, text="›", font=("Arial", 14, "bold"),
                             bg=self.COLOR_BLUE, fg="white", bd=0, padx=8,
                             activebackground="#1a5276", activeforeground="white")
        btn_next.pack(side=tk.RIGHT, padx=2)

        btn_next_year = tk.Button(nav_frame, text="»", font=("Arial", 12, "bold"),
                                  bg=self.COLOR_BLUE, fg="white", bd=0, padx=8,
                                  activebackground="#1a5276", activeforeground="white")
        btn_next_year.pack(side=tk.RIGHT, padx=2)

        # ── Siatka dni ──
        grid_frame = tk.Frame(cal_window, bg="white", padx=5, pady=5)
        grid_frame.pack(fill=tk.BOTH, expand=True)

        # Nagłówki dni tygodnia
        for col, name in enumerate(DAY_NAMES):
            fg_color = "#e74c3c" if col >= 5 else "#2c3e50"
            tk.Label(grid_frame, text=name, font=("Arial", 9, "bold"),
                     bg="white", fg=fg_color, width=4).grid(row=0, column=col, pady=(2, 4))

        # Przyciski dni (6 wierszy x 7 kolumn)
        day_buttons = []
        for r in range(6):
            row_btns = []
            for c in range(7):
                btn = tk.Button(grid_frame, text="", width=4, font=("Arial", 9),
                                bd=1, relief=tk.FLAT, bg="white",
                                activebackground=self.COLOR_GREEN, activeforeground="white")
                btn.grid(row=r + 1, column=c, padx=1, pady=1)
                row_btns.append(btn)
            day_buttons.append(row_btns)

        def fill_calendar():
            """Wypełnij siatkę dniami aktualnego miesiąca"""
            y, m = state['year'], state['month']
            month_label.config(text=f"{MONTH_NAMES[m]} {y}")

            # Pierwszy dzień miesiąca i liczba dni
            first_weekday, num_days = cal_module.monthrange(y, m)
            # cal_module.monthrange: first_weekday 0=Monday

            today = datetime.now()

            day = 1
            for r in range(6):
                for c in range(7):
                    btn = day_buttons[r][c]
                    cell_index = r * 7 + c
                    if cell_index < first_weekday or day > num_days:
                        btn.config(text="", state=tk.DISABLED, bg="white", relief=tk.FLAT)
                    else:
                        d = day
                        is_weekend = c >= 5
                        is_today = (d == today.day and m == today.month and y == today.year)
                        is_selected = (d == state['selected_day'] and m == initial_dt.month and y == initial_dt.year)

                        if is_selected:
                            bg = self.COLOR_GREEN
                            fg = "white"
                        elif is_today:
                            bg = "#d5f5e3"
                            fg = "#27ae60"
                        elif is_weekend:
                            bg = "#fdf2f2"
                            fg = "#e74c3c"
                        else:
                            bg = "white"
                            fg = "#2c3e50"

                        btn.config(text=str(d), state=tk.NORMAL, bg=bg, fg=fg, relief=tk.RIDGE,
                                   command=lambda dd=d: select_day(dd))
                        day += 1

        def select_day(d):
            state['selected_day'] = d
            # od razu wstaw datę
            selected_date = f"{d:02d}-{state['month']:02d}-{state['year']}"
            _set_entry_value(selected_date)
            cal_window.destroy()

        def prev_month():
            if state['month'] == 1:
                state['month'] = 12
                state['year'] -= 1
            else:
                state['month'] -= 1
            state['selected_day'] = 0
            fill_calendar()

        def next_month():
            if state['month'] == 12:
                state['month'] = 1
                state['year'] += 1
            else:
                state['month'] += 1
            state['selected_day'] = 0
            fill_calendar()

        def prev_year():
            state['year'] -= 1
            state['selected_day'] = 0
            fill_calendar()

        def next_year():
            state['year'] += 1
            state['selected_day'] = 0
            fill_calendar()

        btn_prev.config(command=prev_month)
        btn_next.config(command=next_month)
        btn_prev_year.config(command=prev_year)
        btn_next_year.config(command=next_year)

        def _set_entry_value(date_str):
            original_state = str(entry_widget.cget('state'))
            if original_state in ('readonly', 'disabled'):
                entry_widget.config(state='normal')
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, date_str)
            if original_state in ('readonly', 'disabled'):
                entry_widget.config(state=original_state)

        # ── Przyciski dolne ──
        btn_frame = tk.Frame(cal_window, bg="white")
        btn_frame.pack(fill=tk.X, padx=8, pady=(2, 8))

        tk.Button(
            btn_frame, text="📅 Dziś", command=lambda: (
                _set_entry_value(datetime.now().strftime('%d-%m-%Y')),
                cal_window.destroy()
            ),
            bg=self.COLOR_BLUE, fg="white", font=self.FONT_SMALL, padx=8, pady=3
        ).pack(side=tk.LEFT, padx=3)

        tk.Button(
            btn_frame, text="🗑️ Wyczyść", command=lambda: (
                _set_entry_value(''),
                cal_window.destroy()
            ),
            bg=self.COLOR_ORANGE, fg="white", font=self.FONT_SMALL, padx=8, pady=3
        ).pack(side=tk.LEFT, padx=3)

        tk.Button(
            btn_frame, text="❌ Anuluj", command=cal_window.destroy,
            bg="#95a5a6", fg="white", font=self.FONT_SMALL, padx=8, pady=3
        ).pack(side=tk.LEFT, padx=3)

        # Keyboard shortcuts
        cal_window.bind('<Escape>', lambda e: cal_window.destroy())
        cal_window.bind('<Left>', lambda e: prev_month())
        cal_window.bind('<Right>', lambda e: next_month())
        # Mouse wheel: scroll months
        cal_window.bind('<MouseWheel>', lambda e: prev_month() if e.delta > 0 else next_month())
        cal_window.bind('<Button-4>', lambda e: prev_month())   # Linux scroll up
        cal_window.bind('<Button-5>', lambda e: next_month())   # Linux scroll down

        # Wypełnij i wyśrodkuj
        fill_calendar()
        cal_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (cal_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (cal_window.winfo_height() // 2)
        cal_window.geometry(f'+{x}+{y}')

    def _update_lock_buttons_state(self):
        """Aktualizuje stan przycisków lock i etykietę statusu"""
        if not hasattr(self, 'btn_acquire_lock'):
            return

        no_project = not self.selected_project_id
        not_logged_in = not self.current_user or self.current_user_role == "GUEST"

        if no_project or not_logged_in:
            # Brak projektu lub niezalogowany - wszystko wyłączone
            self.lock_status_label.config(text="🔓 Wolny", fg="#95a5a6")
            self.btn_acquire_lock.config(state=tk.DISABLED)
            self.btn_force_lock.config(state=tk.DISABLED)
            self.btn_cancel_lock.config(state=tk.DISABLED)
            self.btn_release_lock.config(state=tk.DISABLED)
            return

        if self.have_lock:
            # Mamy lock
            self.lock_status_label.config(text="🟢 ZABLOKOWANY", fg="#27ae60")
            self.btn_acquire_lock.config(state=tk.DISABLED)
            self.btn_force_lock.config(state=tk.DISABLED)
            self.btn_cancel_lock.config(state=tk.NORMAL)
            self.btn_release_lock.config(state=tk.NORMAL)
        else:
            # Nie mamy locka - sprawdź czy ktoś inny ma
            owner = self.lock_manager.get_project_lock_owner(self.selected_project_id)
            if owner:
                locked_by = self._get_user_display_name(owner.get('user', '?'))
                self.lock_status_label.config(text=f"🔴 {locked_by}", fg="#e74c3c")
            else:
                self.lock_status_label.config(text="🔓 Wolny", fg="#95a5a6")
            self.btn_acquire_lock.config(state=tk.NORMAL)
            self.btn_force_lock.config(state=tk.NORMAL)
            self.btn_cancel_lock.config(state=tk.DISABLED)
            self.btn_release_lock.config(state=tk.DISABLED)

    def acquire_lock(self):
        """Przejmij lock projektu (przycisk 🔓 Przejmij Lock)"""
        if not self.selected_project_id:
            messagebox.showwarning("Brak projektu", "Wybierz projekt najpierw!", parent=self.root)
            return
        if not self.current_user or self.current_user_role == "GUEST":
            messagebox.showinfo("Logowanie", "Poczekaj na zalogowanie lub zaloguj się.", parent=self.root)
            return

        try:
            success, lock_id = self.lock_manager.acquire_project_lock(self.selected_project_id, force=False)
            if not success:
                owner = self.lock_manager.get_project_lock_owner(self.selected_project_id)
                locked_by = self._get_user_display_name(owner.get('user', 'Unknown')) if owner else 'Unknown'
                owner_comp = owner.get('computer', 'Unknown') if owner else 'Unknown'
                owner_at   = owner.get('locked_at', 'Unknown') if owner else 'Unknown'
                self.root.lift()
                self.root.focus_force()
                messagebox.showwarning(
                    "Projekt zajęty",
                    f"Projekt {self.selected_project_id} jest zajęty przez:\n"
                    f"{locked_by}@{owner_comp}\n"
                    f"Lock od: {owner_at}\n\n"
                    f"Użyj przycisku ⚡ Wymuś jeśli lock jest nieaktywny.",
                    parent=self.root
                )
                return

            self._locked_project_id = self.selected_project_id
            self.have_lock = True
            self.current_lock_id = lock_id
            self.read_only_mode = False
            self._snapshot_stage_dates()  # Snapshot dat do cofnięcia przy Anuluj
            self.status_bar.config(
                text=f"🟢 Lock przejęty dla projektu {self.selected_project_id}",
                fg="#27ae60"
            )
            self._update_lock_buttons_state()
            self.load_project_stages()  # Odśwież panel etapów (enable/disable)
            self.refresh_timeline()  # Odśwież aby włączyć edycję pól
            self._refresh_combo_lock_info()  # Odśwież combo projektów (pokaż lock)
            self._sync_mp_chart_lock_state()  # Synchronizuj Multi-project chart
            print(f"✅ Lock przejęty: projekt {self.selected_project_id}, lock_id={lock_id}")

        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się przejąć locka:\n{e}", parent=self.root)

    def force_acquire_lock(self):
        """Wymuś przejęcie locka (przycisk ⚡ Wymuś)"""
        if not self.selected_project_id:
            messagebox.showwarning("Brak projektu", "Wybierz projekt najpierw!", parent=self.root)
            return
        if not self.current_user or self.current_user_role == "GUEST":
            messagebox.showinfo("Logowanie", "Poczekaj na zalogowanie lub zaloguj się.", parent=self.root)
            return

        owner = self.lock_manager.get_project_lock_owner(self.selected_project_id)
        if not owner:
            messagebox.showinfo(
                "Brak locka",
                "Brak aktywnego locka - użyj przycisku '🔓 Przejmij Lock'.",
                parent=self.root
            )
            return

        locked_by = self._get_user_display_name(owner.get('user', 'Unknown'))
        owner_comp = owner.get('computer', 'Unknown')
        acquired_at = owner.get('locked_at', 'Unknown')

        self.root.lift()
        self.root.focus_force()
        response = messagebox.askyesno(
            "⚡ Wymuś przejęcie locka",
            f"⚠️ UWAGA! Wymuszasz przejęcie locka.\n\n"
            f"Aktualny właściciel: {locked_by}@{owner_comp}\n"
            f"Lock założony: {acquired_at}\n\n"
            f"Użyj tej opcji TYLKO gdy:\n"
            f"• Poprzednia sesja zawiesiła się\n"
            f"• Lock \"wisi w powietrzu\"\n"
            f"• Nie ma innego aktywnego użytkownika\n\n"
            f"Czy na pewno wymusić przejęcie?",
            icon='warning',
            parent=self.root
        )
        if not response:
            return

        try:
            success, lock_id = self.lock_manager.acquire_project_lock(self.selected_project_id, force=True)
            if not success:
                messagebox.showerror("Błąd", "Nie udało się wymusić przejęcia locka!", parent=self.root)
                return

            self._locked_project_id = self.selected_project_id
            self.have_lock = True
            self.current_lock_id = lock_id
            self.read_only_mode = False
            self._snapshot_stage_dates()  # Snapshot dat do cofnięcia przy Anuluj
            self.status_bar.config(
                text=f"⚡ Lock wymuszony dla projektu {self.selected_project_id}",
                fg="#9b59b6"
            )
            self._update_lock_buttons_state()
            self.load_project_stages()  # Odśwież panel etapów (enable/disable)
            self.refresh_timeline()  # Odśwież aby włączyć edycję pól
            self._refresh_combo_lock_info()  # Odśwież combo projektów (pokaż lock)
            self._sync_mp_chart_lock_state()  # Synchronizuj Multi-project chart
            print(f"⚡ Lock wymuszony: projekt {self.selected_project_id}, lock_id={lock_id}")

        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się wymusić przejęcia locka:\n{e}", parent=self.root)

    def _snapshot_stage_dates(self):
        """Zapisz snapshot wszystkich dat stage_schedule dla bieżącego projektu.
        Używane do przywracania przy Anuluj."""
        self._dates_snapshot = None
        try:
            _pdb = self.get_project_db_path(self.selected_project_id)
            con = rmm._open_rm_connection(_pdb, row_factory=False)
            rows = con.execute("""
                SELECT ps.stage_code, ss.template_start, ss.template_end
                FROM stage_schedule ss
                JOIN project_stages ps ON ss.project_stage_id = ps.id
                WHERE ps.project_id = ?
            """, (self.selected_project_id,)).fetchall()
            con.close()
            self._dates_snapshot = {row[0]: (row[1], row[2]) for row in rows}
            print(f"📸 Snapshot dat zapisany ({len(self._dates_snapshot)} etapów)")
        except Exception as e:
            print(f"⚠️ Nie udało się zapisać snapshotu dat: {e}")

    def _restore_stage_dates_from_snapshot(self):
        """Przywróć daty z snapshotu (cofnięcie wszystkich zmian)."""
        if not self._dates_snapshot:
            print("⚠️ Brak snapshotu dat do przywrócenia")
            return False
        try:
            _pdb = self.get_project_db_path(self.selected_project_id)
            con = rmm._open_rm_connection(_pdb, row_factory=False)
            for stage_code, (t_start, t_end) in self._dates_snapshot.items():
                con.execute("""
                    UPDATE stage_schedule
                    SET template_start = ?, template_end = ?
                    WHERE project_stage_id = (
                        SELECT id FROM project_stages
                        WHERE project_id = ? AND stage_code = ?
                    )
                """, (t_start, t_end, self.selected_project_id, stage_code))
            con.commit()
            con.close()
            rmm.recalculate_forecast(_pdb, self.selected_project_id)
            print(f"♻️ Przywrócono daty z snapshotu ({len(self._dates_snapshot)} etapów)")
            self._dates_snapshot = None
            return True
        except Exception as e:
            print(f"🔥 Błąd przywracania snapshotu: {e}")
            return False

    def cancel_lock(self):
        """Anuluj lock - cofnij WSZYSTKIE zmiany dat i zwolnij lock (przycisk ✖ Anuluj)"""
        if not self.have_lock or not self.selected_project_id:
            return

        if not messagebox.askyesno(
            "Potwierdź anulowanie",
            f"Czy na pewno anulować WSZYSTKIE zmiany w projekcie {self.selected_project_id}?\n\n"
            "♻️ Daty etapów zostaną przywrócone do stanu\n"
            "sprzed przejęcia locka (także z wykresu).\n\n"
            "⚠️ Tej operacji nie można cofnąć!",
            icon='warning',
            parent=self.root
        ):
            return

        try:
            # Przywróć daty ze snapshotu PRZED zwolnieniem locka
            restored = self._restore_stage_dates_from_snapshot()

            # Zwolnij lock
            self.lock_manager.release_project_lock(self.selected_project_id)
            self._locked_project_id = None
            self.have_lock = False
            self.current_lock_id = None
            self.read_only_mode = True

            msg = "✖ Anulowano - daty przywrócone" if restored else "✖ Lock anulowany"
            self.status_bar.config(
                text=f"{msg} dla projektu {self.selected_project_id}",
                fg="#f39c12"
            )
            self._update_lock_buttons_state()
            self.load_project_stages()
            self.refresh_timeline()
            self._refresh_combo_lock_info()
            self._sync_mp_chart_lock_state()  # Synchronizuj Multi-project chart
            print(f"✖ Lock anulowany (daty przywrócone={restored}): projekt {self.selected_project_id}")

        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się anulować locka:\n{e}", parent=self.root)

    def release_lock(self):
        """Zwolnij lock projektu (przycisk 🔒 Zwolnij Lock)"""
        if not self.have_lock or not self.selected_project_id:
            return

        # Sprawdź czy nadal mamy lock (detekcja wymuszenia)
        # Pomijaj sprawdzanie dla stuba (tryb jednousytkownikowy)
        if self.current_lock_id and not getattr(self.lock_manager, '_STUB', False):
            current_owner = self.lock_manager.get_project_lock_owner(self.selected_project_id)
            lock_lost = False
            reason = ""
            if not current_owner:
                lock_lost = True
                reason = "Lock został zwolniony przez innego użytkownika"
            elif current_owner.get('lock_id') != self.current_lock_id:
                new_owner = current_owner.get('user', 'Unknown')
                new_comp  = current_owner.get('computer', 'Unknown')
                lock_lost = True
                reason = f"Lock został wymuszony przez:\n{new_owner}@{new_comp}"
            if lock_lost:
                print(f"⚠️  Wykryto utratę locka przy zwalnianiu: {reason}")
                self._on_lock_lost(reason)
                return

        try:
            # Zapisz wszystkie niezapisane zmiany przed zwolnieniem
            self.save_all_templates()
            
            self.lock_manager.release_project_lock(self.selected_project_id)
            self._locked_project_id = None
            self.have_lock = False
            self.current_lock_id = None
            self.read_only_mode = True
            self.status_bar.config(
                text=f"🔓 Lock zwolniony dla projektu {self.selected_project_id} (zmiany zapisane)",
                fg="#e74c3c"
            )
            self._update_lock_buttons_state()
            self.load_project_stages()  # Odśwież panel etapów (disable)
            self.refresh_timeline()  # Odśwież aby zablokować edycję pól
            self._refresh_combo_lock_info()  # Odśwież combo projektów (usuń lock)
            self._sync_mp_chart_lock_state()  # Synchronizuj Multi-project chart
            print(f"🔓 Lock zwolniony: projekt {self.selected_project_id}")

        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się zwolnić locka:\n{e}", parent=self.root)

    def _on_lock_lost(self, reason: str):
        """Obsługa utraty locka (ktoś wymuszył przejęcie)"""
        print(f"🚨 UTRATA LOCKA: {reason}")
        self._locked_project_id = None
        self.have_lock = False
        self.current_lock_id = None
        self.read_only_mode = True
        self._update_lock_buttons_state()
        self.load_project_stages()  # Odśwież panel etapów (disable)
        self.refresh_timeline()  # Odśwież aby zablokować edycję pól
        self._refresh_combo_lock_info()  # Odśwież combo projektów (pokaż nowy lock)
        self._sync_mp_chart_lock_state()  # Synchronizuj Multi-project chart
        self.status_bar.config(
            text=f"⚠️ Utracono lock projektu {self.selected_project_id} - tryb READ-ONLY",
            fg="#e74c3c"
        )
        messagebox.showwarning(
            "⚠️ Utrata locka",
            f"Twój lock projektu {self.selected_project_id} został przejęty!\n\n"
            f"Powód:\n{reason}\n\n"
            f"Tryb: READ-ONLY",
            parent=self.root
        )

    @staticmethod
    def format_datetime(dt_str: str) -> str:
        """Formatuj datetime bez sekund: DD-MM-YYYY HH:MM"""
        if not dt_str:
            return "N/A"
        try:
            dt = datetime.fromisoformat(dt_str)
            return dt.strftime("%d-%m-%Y %H:%M")
        except:
            # Jeśli już jest w formacie date-only (YYYY-MM-DD), konwertuj do DD-MM-YYYY
            if len(dt_str) == 10:  # YYYY-MM-DD
                try:
                    dt = datetime.fromisoformat(dt_str)
                    return dt.strftime("%d-%m-%Y")
                except:
                    return dt_str
            # Dla datetime strings próbuj skonwertować
            try:
                dt = datetime.fromisoformat(dt_str[:19])  # Obetnij mikrosekundy
                return dt.strftime("%d-%m-%Y %H:%M")
            except:
                return dt_str[:16]  # Fallback

    def load_config(self):
        """Wczytaj konfigurację z JSON"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # Przechowaj cały dict dla modułów (np. SMS)
                    self.config = config
                    self.master_db_path  = config.get('master_db_path',  DEFAULT_MASTER_DB_PATH)
                    self.rm_manager_dir  = config.get('rm_manager_dir',  DEFAULT_RM_MANAGER_DIR)
                    self.projects_path   = config.get('projects_path',   DEFAULT_PROJECTS_PATH)
                    # Stara konfiguracja (rm_db_path) – migracja w locie
                    if 'rm_db_path' in config and 'rm_manager_dir' not in config:
                        old = config['rm_db_path']
                        self.rm_manager_dir = os.path.dirname(old) or DEFAULT_RM_MANAGER_DIR
                    # rm_master_db_path: jawna ścieżka lub pochodna z katalogu
                    self.rm_master_db_path = config.get(
                        'rm_master_db_path',
                        os.path.join(self.rm_manager_dir, 'rm_manager.sqlite')
                    )
                    # rm_projects_dir: osobny katalog na per-projekt bazy
                    self.rm_projects_dir = config.get(
                        'rm_projects_dir',
                        os.path.join(os.path.dirname(self.rm_manager_dir), 'RM_MANAGER_projects')
                    )
                    # backup_dir: katalog backupów
                    self.backup_dir = config.get(
                        'backup_dir',
                        os.path.join(os.path.dirname(self.rm_manager_dir), 'backups')
                    )
                    # locks_dir: katalog locków
                    self.locks_dir = config.get(
                        'locks_dir',
                        os.path.join(self.rm_projects_dir, 'LOCKS')
                    )
                    # Geometria okien i szerokości kolumn
                    self.window_geometry = config.get('window_geometry', {})
                    self.column_widths = config.get('column_widths', {})
                    print(f"✅ Konfiguracja wczytana z: {self.config_file}")
                    print(f"   master_db_path:   {self.master_db_path}")
                    print(f"   rm_manager_dir:   {self.rm_manager_dir}")
                    print(f"   rm_master_db_path:{self.rm_master_db_path}")
                    print(f"   rm_projects_dir:  {self.rm_projects_dir}")
                    print(f"   backup_dir:       {self.backup_dir}")
                    print(f"   locks_dir:        {self.locks_dir}")
                    print(f"   projects_path:    {self.projects_path}")
            else:
                # Brak pliku - użyj domyślnych
                self.config = {}
                self.master_db_path    = DEFAULT_MASTER_DB_PATH
                self.rm_manager_dir    = DEFAULT_RM_MANAGER_DIR
                self.projects_path     = DEFAULT_PROJECTS_PATH
                self.rm_master_db_path = DEFAULT_RM_MANAGER_DB_PATH
                self.rm_projects_dir   = DEFAULT_RM_PROJECTS_DIR
                self.backup_dir        = DEFAULT_BACKUP_DIR
                self.locks_dir         = DEFAULT_LOCKS_DIR
                print(f"⚠️ Brak pliku konfiguracyjnego: {self.config_file}")
                print(f"   Użyto domyślnych ścieżek")
                # Utwórz domyślny plik
                self.save_config()
        except Exception as e:
            print(f"⚠️ Błąd wczytywania konfiguracji: {e}")
            self.config = {}
            self.master_db_path    = DEFAULT_MASTER_DB_PATH
            self.rm_manager_dir    = DEFAULT_RM_MANAGER_DIR
            self.projects_path     = DEFAULT_PROJECTS_PATH
            self.rm_master_db_path = DEFAULT_RM_MANAGER_DB_PATH
            self.rm_projects_dir   = DEFAULT_RM_PROJECTS_DIR
            self.backup_dir        = DEFAULT_BACKUP_DIR
            self.locks_dir         = DEFAULT_LOCKS_DIR

    def save_config(self):
        """Zapisz konfigurację do JSON"""
        try:
            # Upewnij się że katalog istnieje
            config_dir = os.path.dirname(self.config_file)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)
            
            config = {
                'master_db_path': self.master_db_path,
                'rm_manager_dir': self.rm_manager_dir,
                'rm_master_db_path': self.rm_master_db_path,
                'rm_projects_dir': self.rm_projects_dir,
                'backup_dir': self.backup_dir,
                'locks_dir': self.locks_dir,
                'projects_path': self.projects_path,
                'window_geometry': self.window_geometry,
                'column_widths': self.column_widths,
                '_comment': 'RM_MANAGER configuration file – edit paths as needed'
            }
            
            # Zachowaj last_user_id (auto-login)
            if self.current_user_id is not None:
                config['last_user_id'] = self.current_user_id
            
            # Zachowaj ustawienia SMS (jeśli są w self.config)
            if hasattr(self, 'config'):
                for key in ['sms_enabled', 'sms_api_token', 'sms_sender_name', 'sms_default_country_code']:
                    if key in self.config:
                        config[key] = self.config[key]
            
            # Aktualizuj self.config
            self.config = config
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            
            print(f"✅ Konfiguracja zapisana: {self.config_file}")
        except Exception as e:
            print(f"⚠️ Błąd zapisu konfiguracji: {e}")
    
    # -----------------------------------------------------------------------
    # Narzędzie pomocnicze – centrowanie okien dialogowych
    # -----------------------------------------------------------------------

    def _center_window(self, win: tk.Toplevel, w: int, h: int):
        """Wyśrodkuj okno dialogowe na monitorze, na którym wyświetla się
        aplikacja główna (poprawna obsługa wielomonitorowa)."""
        win.update_idletasks()
        self.root.update_idletasks()
        try:
            rx = self.root.winfo_rootx()
            ry = self.root.winfo_rooty()
            rw = self.root.winfo_width()
            rh = self.root.winfo_height()
            x = rx + (rw - w) // 2
            y = ry + (rh - h) // 2
        except Exception:
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            x = (sw - w) // 2
            y = (sh - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

    def save_window_geometry(self, window_name: str, window: tk.Toplevel):
        """Zapisz geometrię okna do konfiguracji"""
        try:
            geometry = window.geometry()
            self.window_geometry[window_name] = geometry
            self.save_config()
        except Exception as e:
            print(f"⚠️ Błąd zapisu geometrii okna {window_name}: {e}")
    
    def restore_window_geometry(self, window_name: str, window: tk.Toplevel, default_w: int, default_h: int):
        """Przywróć zapamiętaną geometrię okna lub wycentruj z domyślnymi wymiarami"""
        try:
            if window_name in self.window_geometry:
                geometry = self.window_geometry[window_name]
                window.geometry(geometry)
            else:
                self._center_window(window, default_w, default_h)
        except Exception as e:
            print(f"⚠️ Błąd przywracania geometrii okna {window_name}: {e}")
            self._center_window(window, default_w, default_h)
    
    def save_column_widths(self, tree_name: str, tree: ttk.Treeview):
        """Zapisz szerokości kolumn treeview do konfiguracji"""
        try:
            widths = {}
            for col in tree['columns']:
                widths[col] = tree.column(col, 'width')
            self.column_widths[tree_name] = widths
            self.save_config()
        except Exception as e:
            print(f"⚠️ Błąd zapisu szerokości kolumn {tree_name}: {e}")
    
    def restore_column_widths(self, tree_name: str, tree: ttk.Treeview):
        """Przywróć zapamiętane szerokości kolumn treeview"""
        try:
            if tree_name in self.column_widths:
                widths = self.column_widths[tree_name]
                for col, width in widths.items():
                    if col in tree['columns']:
                        tree.column(col, width=width)
        except Exception as e:
            print(f"⚠️ Błąd przywracania szerokości kolumn {tree_name}: {e}")

    def init_database(self):
        """Inicjalizacja bazy danych RM_MANAGER (master + katalog projektów)"""
        try:
            Path(self.rm_manager_dir).mkdir(parents=True, exist_ok=True)
            Path(self.rm_projects_dir).mkdir(parents=True, exist_ok=True)
            rmm.ensure_rm_master_tables(self.rm_master_db_path)
            print(f"✅ Master baza zainicjalizowana: {self.rm_master_db_path}")
            print(f"✅ Katalog projektów: {self.rm_projects_dir}")
        except Exception as e:
            messagebox.showerror("Błąd bazy", f"Nie można zainicjalizować bazy:\n{e}")

    # ========================================================================
    # Logowanie użytkowników (mechanizm z RM_BAZA – read-only z master.sqlite)
    # ========================================================================

    def get_last_user_from_config(self):
        """Odczytaj ID ostatniego zalogowanego użytkownika z pliku JSON"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                return config.get('last_user_id')
        except Exception:
            pass
        return None

    def save_last_user_to_config(self, user_id):
        """Zapisz ID ostatniego użytkownika do pliku JSON"""
        try:
            config = {}
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            config['last_user_id'] = user_id
            config_dir = os.path.dirname(self.config_file)
            if config_dir and not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️  Nie udało się zapisać ostatniego użytkownika: {e}")

    def load_users(self, auto_login=True):
        """Załaduj listę użytkowników z master.sqlite RM_BAZA do combo"""
        rows = rmm.get_users_from_baza(self.master_db_path)
        if not rows:
            print(f"⚠️  Brak użytkowników lub niedostępna baza: {self.master_db_path}")
            self.user_combo['values'] = []
            self.user_var.set("")
            return

        labels = []
        for r in rows:
            label = f"{r['id']} | {r['username']}"
            if r.get('display_name') and r['display_name'] != r['username']:
                label += f" ({r['display_name']})"
            label += f" [{r['role']}]"
            labels.append(label)

        self.user_combo['values'] = labels
        print(f"📋 Załadowano {len(labels)} użytkowników")

        if auto_login:
            last_id = self.get_last_user_from_config()
            if last_id:
                for lbl in labels:
                    if lbl.startswith(f"{last_id} |"):
                        self.user_var.set(lbl)
                        self._silent_login(last_id)
                        return
            # Brak zapisanego – auto-loguj pierwszego użytkownika
            if labels and rows:
                self.user_var.set(labels[0])
                self._silent_login(rows[0]['id'])

    def _silent_login(self, user_id):
        """Ciche zalogowanie w tle (bez pytania o hasło – tylko przywrócenie sesji)"""
        if getattr(self, '_login_in_progress', False):
            return
        self._login_in_progress = True
        t = threading.Thread(target=self._silent_login_worker, args=(user_id,), daemon=True)
        self._login_thread = t
        t.start()

    def _silent_login_worker(self, user_id):
        """Wątek: pobierz dane usera i wywołaj _finish_login w GUI-thread"""
        try:
            rows = rmm.get_users_from_baza(self.master_db_path)
            for r in rows:
                if r['id'] == user_id:
                    self.root.after(0, lambda r=r: self._finish_login(r['id'], r['username'],
                                                                       r['role']))
                    return
            self.root.after(0, lambda: self._finish_login_failed("Brak użytkownika"))
        except Exception as e:
            self.root.after(0, lambda: self._finish_login_failed(str(e)))

    def _finish_login(self, uid, username, role):
        """Aktualizacja stanu GUI po zalogowaniu"""
        self._login_in_progress = False
        self.current_user_id = uid
        self.current_user = username
        self.current_user_role = role
        # Zapamiętaj ostatniego usera (auto-login przy restarcie)
        self.save_last_user_to_config(uid)
        # Reload uprawnień
        self.user_permissions = rmm.get_user_permissions(self.rm_master_db_path, role)
        # Zaktualizuj lock_manager
        if hasattr(self, 'lock_manager') and self.lock_manager:
            self.lock_manager.update_user_name(username)
        # Wyczyść listę pokazanych alarmów po zmianie użytkownika
        if hasattr(self, '_shown_alarm_ids'):
            self._shown_alarm_ids.clear()
        self._update_action_buttons_state()
        # Odśwież combo projektów (lock info mogło się zmienić po update_user_name)
        self._refresh_combo_lock_info()
        # Odblokuj przyciski lock (były zablokowane do czasu logowania)
        self._update_lock_buttons_state()
        print(f"✅ Zalogowano: {username} (ID={uid}, Rola={role})")
        if hasattr(self, 'status_bar'):
            self.status_bar.config(
                text=f"👤 {username} [{role}]",
                fg="#27ae60" if role != "GUEST" else "#f39c12"
            )
        # Sprawdź nieprzeczytane powiadomienia o płatnościach
        self.check_unread_notifications()

    def _finish_login_failed(self, reason):
        """Obsługa błędu logowania – fallback GUEST"""
        self._login_in_progress = False
        self.current_user = None
        self.current_user_id = None
        self.current_user_role = "GUEST"
        self.user_permissions = rmm.get_user_permissions(self.rm_master_db_path, "GUEST")
        # Wyczyść listę pokazanych alarmów przy fallback GUEST
        if hasattr(self, '_shown_alarm_ids'):
            self._shown_alarm_ids.clear()
        self._update_action_buttons_state()
        print(f"⚠️  Logowanie nieudane: {reason} – tryb GUEST")

    def prompt_password(self, username: str) -> dict:
        """Dialog zapytania o hasło (identyczny jak RM_BAZA)"""
        dlg = tk.Toplevel(self.root)
        dlg.title(f"Logowanie: {username}")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        self._center_window(dlg, 400, 180)

        frm = tk.Frame(dlg, padx=25, pady=20)
        frm.pack(fill=tk.BOTH, expand=True)
        tk.Label(frm, text=f"Podaj hasło dla: {username}",
                 font=("Arial", 10, "bold")).pack(pady=(0, 15))
        tk.Label(frm, text="Hasło:").pack(anchor="w")
        var_pwd = tk.StringVar()
        entry_pwd = tk.Entry(frm, textvariable=var_pwd, show="*", width=35)
        entry_pwd.pack(pady=5, fill=tk.X)
        entry_pwd.focus()

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
        tk.Button(btn_frame, text="OK", command=on_ok, width=12).pack(side=tk.LEFT, padx=10, expand=True)
        tk.Button(btn_frame, text="Anuluj", command=on_cancel, width=12).pack(side=tk.LEFT, padx=10, expand=True)
        dlg.wait_window()
        return result

    def on_user_selected(self, event=None):
        """Obsługa wyboru użytkownika z combo"""
        selected = self.user_var.get()
        if not selected or "|" not in selected:
            return

        try:
            new_user_id = int(selected.split("|")[0].strip())
        except ValueError:
            return

        if self.current_user_id == new_user_id:
            return  # Nie zmieniono użytkownika

        # Pobierz dane użytkownika z bazy
        rows = rmm.get_users_from_baza(self.master_db_path)
        user_row = None
        for r in rows:
            if r['id'] == new_user_id:
                user_row = r
                break

        if not user_row:
            messagebox.showerror("Błąd", f"Nie znaleziono użytkownika ID={new_user_id}")
            return

        username = user_row['username']
        role = user_row['role']
        stored_hash = user_row.get('password_hash')

        # Weryfikacja hasła (jeśli ustawione)
        if stored_hash:
            result = self.prompt_password(username)
            if not result["ok"]:
                # Przywróć poprzedniego usera w combo
                self._restore_combo_to_current_user()
                return
            entered_hash = hashlib.sha256(result["password"].encode()).hexdigest()
            if entered_hash != stored_hash:
                messagebox.showerror("Błąd logowania", "Nieprawidłowe hasło!")
                self._restore_combo_to_current_user()
                return

        self.save_last_user_to_config(new_user_id)
        self._finish_login(new_user_id, username, role)

    def _restore_combo_to_current_user(self):
        """Przywróć poprzedniego użytkownika w combo po anulowaniu / błędzie"""
        if self.current_user_id is None:
            self.user_var.set("")
            return
        for lbl in self.user_combo['values']:
            if lbl.startswith(f"{self.current_user_id} |"):
                self.user_combo.unbind('<<ComboboxSelected>>')
                self.user_var.set(lbl)
                self.user_combo.bind('<<ComboboxSelected>>', self.on_user_selected)
                return

    # ========================================================================
    # Uprawnienia użytkowników
    # ========================================================================

    def _has_permission(self, perm_key: str) -> bool:
        """Sprawdź czy bieżący użytkownik ma dane uprawnienie.
        Odczyt z cache self.user_permissions (załadowane przy logowaniu).
        """
        return bool(self.user_permissions.get(perm_key, False))

    def _update_action_buttons_state(self):
        """Włącz/wyłącz przyciski akcji w zależności od uprawnień użytkownika.
        Wywoływane po zalogowaniu. Działa tylko jeśli widgety już istnieją.
        """
        # Locki – blokada dla GUEST
        is_guest = (self.current_user_role == "GUEST")
        for btn_attr in ('btn_acquire_lock', 'btn_force_lock'):
            btn = getattr(self, btn_attr, None)
            if btn:
                btn.config(state=tk.DISABLED if is_guest else tk.NORMAL)
        # Przyciski etapów – przebuduj panel (zostaną przebudowane przy load_stages)
        # Nie przebudowujemy tu – load_stages wywoła _can_start / _can_end przy tworzeniu btns

    def create_menu(self):
        """Menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Plik", menu=file_menu)
        file_menu.add_command(label="Konfiguracja ścieżek...", command=self.edit_config)
        file_menu.add_separator()
        file_menu.add_command(label="➕ Nowy projekt...", command=self.add_project_dialog)
        file_menu.add_command(label="📋 Lista projektów...", command=self.projects_list_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Zamknij", command=self.root.quit)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Widok", menu=view_menu)
        view_menu.add_command(label="Odśwież", command=self.refresh_all)
        view_menu.add_separator()
        view_menu.add_command(label="🔄 Odśwież listę projektów", command=self.force_reload_projects)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Narzędzia", menu=tools_menu)
        tools_menu.add_command(label="Synchronizuj z RM_BAZA", command=self.sync_to_master)
        tools_menu.add_command(label="🔄 Synchronizuj wszystkie projekty", command=self.sync_all_to_master)
        tools_menu.add_command(label="Ścieżka krytyczna", command=self.show_critical_path)
        tools_menu.add_separator()
        tools_menu.add_command(label="Edytuj daty szablonu i prognozy", command=self.edit_dates_dialog)
        tools_menu.add_separator()
        tools_menu.add_command(label="📧 Konfiguracja powiadomień płatności...", command=self.payment_notifications_config)
        tools_menu.add_command(label="📱 Konfiguracja SMS...", command=self.sms_config_dialog)
        tools_menu.add_command(label="📱 Wyślij SMS testowy...", command=self.send_test_sms_dialog)
        tools_menu.add_command(label="🔐 Zarządzaj uprawnieniami wysyłki kodów PLC...", command=self.manage_plc_senders_dialog)
        tools_menu.add_command(label="🔧 Migruj bazę kodów PLC (dodaj kolumny)", command=self.migrate_plc_codes_ui)
        tools_menu.add_command(label="🔧 Migruj odbiorców kodów PLC", command=self.migrate_plc_recipients_ui)
        tools_menu.add_separator()
        tools_menu.add_command(label="🔄 Resetuj śledzenie wszystkich projektów", command=self.reset_all_file_tracking_ui)
        tools_menu.add_separator()
        tools_menu.add_command(label="🔍 Diagnostyka projektów", command=self.diagnose_projects)
        tools_menu.add_command(label="🎯 Diagnostyka milestone'ów", command=self.diagnose_milestones)

        # Users menu
        users_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Użytkownicy", menu=users_menu)
        users_menu.add_command(label="🔄 Odśwież listę użytkowników", command=self.load_users)
        users_menu.add_separator()
        users_menu.add_command(label="🔑 Uprawnienia kategorii...", command=self.edit_permissions_dialog)

        # Backup menu
        backup_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Backupy", menu=backup_menu)
        backup_menu.add_command(label="📋 Podgląd backupów…", command=self.menu_view_backups)
        backup_menu.add_command(label="💾 Wykonaj backup teraz", command=self.menu_run_backup_now)

        # Lists menu
        lists_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Listy", menu=lists_menu)
        lists_menu.add_command(label="👷 Pracownicy...", command=self.employees_dialog)
        lists_menu.add_command(label="🚚 Transport...", command=self.transports_dialog)
    
    def create_widgets(self):
        """Główny layout"""
        
        # Top bar - Project selector (styl RM_BAZA)
        self.top_frame = tk.Frame(self.root, bg=self.COLOR_TOPBAR, height=60)
        self.top_frame.pack(fill=tk.X)
        self.top_frame.pack_propagate(False)
        
        tk.Label(
            self.top_frame, 
            text="PROJEKT:", 
            bg=self.COLOR_TOPBAR, 
            fg="white", 
            font=self.FONT_BOLD
        ).pack(side=tk.LEFT, padx=(10, 5), pady=10)
        
        self.project_combo = ttk.Combobox(
            self.top_frame, 
            width=40, 
            state='readonly', 
            font=self.FONT_DEFAULT
        )
        self.project_combo.pack(side=tk.LEFT, padx=5, pady=10)
        self.project_combo.bind('<<ComboboxSelected>>', self.on_project_selected)
        self.project_combo.bind('<Button-1>', self._on_project_combo_click)
        
        tk.Button(
            self.top_frame, 
            text="🔄 Odśwież", 
            command=self.refresh_all,
            bg=self.COLOR_PURPLE,
            fg="white",
            font=self.FONT_BOLD,
            padx=15,
            pady=5,
            relief=tk.RAISED,
            bd=2
        ).pack(side=tk.LEFT, padx=5, pady=10)

        # Separator
        tk.Frame(self.top_frame, bg="#4a6278", width=2, height=40).pack(side=tk.LEFT, padx=8, pady=10)

        # Lock status label
        self.lock_status_label = tk.Label(
            self.top_frame,
            text="🔓 Wolny",
            bg=self.COLOR_TOPBAR,
            fg="#95a5a6",
            font=("Arial", 9),
            padx=4
        )
        self.lock_status_label.pack(side=tk.LEFT, padx=(0, 4), pady=10)

        # Przejmij Lock button
        self.btn_acquire_lock = tk.Button(
            self.top_frame,
            text="🔓 Przejmij Lock",
            command=self.acquire_lock,
            bg="#27ae60",
            fg="white",
            font=self.FONT_BOLD,
            padx=12,
            pady=5,
            relief=tk.RAISED,
            bd=2,
            state=tk.DISABLED
        )
        self.btn_acquire_lock.pack(side=tk.LEFT, padx=(0, 3), pady=10)

        # Wymuś button
        self.btn_force_lock = tk.Button(
            self.top_frame,
            text="⚡ Wymuś",
            command=self.force_acquire_lock,
            bg="#9b59b6",
            fg="white",
            font=("Arial", 9, "bold"),
            padx=8,
            pady=5,
            relief=tk.RAISED,
            bd=2,
            state=tk.DISABLED
        )
        self.btn_force_lock.pack(side=tk.LEFT, padx=(0, 3), pady=10)

        # Przycisk Anuluj (zwolnij lock bez zapisywania zmian)
        self.btn_cancel_lock = tk.Button(
            self.top_frame,
            text="✖ Anuluj",
            command=self.cancel_lock,
            bg="#f39c12",
            fg="white",
            font=("Arial", 9, "bold"),
            padx=8,
            pady=5,
            relief=tk.RAISED,
            bd=2,
            state=tk.DISABLED
        )
        self.btn_cancel_lock.pack(side=tk.LEFT, padx=(0, 3), pady=10)

        # Zdejmij Lock button
        self.btn_release_lock = tk.Button(
            self.top_frame,
            text="🔒 Zdejmij Lock",
            command=self.release_lock,
            bg="#e74c3c",
            fg="white",
            font=self.FONT_BOLD,
            padx=12,
            pady=5,
            relief=tk.RAISED,
            bd=2,
            state=tk.DISABLED
        )
        self.btn_release_lock.pack(side=tk.LEFT, padx=(0, 3), pady=10)

        # Separator przed przyciskiem alarmów
        tk.Frame(self.top_frame, bg="#4a6278", width=2, height=40).pack(side=tk.LEFT, padx=8, pady=10)

        # Przycisk ALARMY
        def _open_alarms():
            alarms = self._get_all_alarms()
            if alarms:
                self.show_alarms_notification(alarms)
        
        tk.Button(
            self.top_frame,
            text="⏰ Alarmy",
            command=_open_alarms,
            bg="#e67e22",
            fg="white",
            font=self.FONT_BOLD,
            padx=12,
            pady=5,
            relief=tk.RAISED,
            bd=2
        ).pack(side=tk.LEFT, padx=(0, 3), pady=10)

        # Przycisk MULTI-PROJEKT
        tk.Button(
            self.top_frame,
            text="📊 Multi-projekt",
            command=self.open_multi_project_chart,
            bg="#8e44ad",
            fg="white",
            font=self.FONT_BOLD,
            padx=12,
            pady=5,
            relief=tk.RAISED,
            bd=2
        ).pack(side=tk.LEFT, padx=(0, 3), pady=10)

        # Separator przed comboboxem backupu
        tk.Frame(self.top_frame, bg="#4a6278", width=2, height=40).pack(side=tk.LEFT, padx=8, pady=10)

        # Podgląd backupu
        tk.Label(
            self.top_frame,
            text="📅 Backup:",
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 9)
        ).pack(side=tk.LEFT, padx=(5, 3), pady=10)
        
        self.backup_date_var = tk.StringVar(value="Aktualny stan")
        self.backup_combo = ttk.Combobox(
            self.top_frame,
            textvariable=self.backup_date_var,
            width=14,
            state="readonly",
            font=("Arial", 9)
        )
        self.backup_combo.pack(side=tk.LEFT, padx=5, pady=10)
        self.backup_combo.bind("<<ComboboxSelected>>", self.on_backup_selected)

        # Separator przed user combo
        tk.Frame(self.top_frame, bg="#4a6278", width=2, height=40).pack(side=tk.RIGHT, padx=(0, 8), pady=10)

        # Label i combo użytkownika (po prawej stronie top baru)
        tk.Label(
            self.top_frame,
            text="UŻYTKOWNIK:",
            bg=self.COLOR_TOPBAR,
            fg="#bdc3c7",
            font=("Arial", 9, "bold")
        ).pack(side=tk.RIGHT, padx=(0, 4), pady=10)

        self.user_var = tk.StringVar()
        self.user_combo = ttk.Combobox(
            self.top_frame,
            textvariable=self.user_var,
            state='readonly',
            width=28,
            font=self.FONT_DEFAULT
        )
        self.user_combo.pack(side=tk.RIGHT, padx=(0, 5), pady=10)
        self.user_combo.bind('<<ComboboxSelected>>', self.on_user_selected)

        # Warning frame - File integrity alert (initially hidden)
        self.warning_frame = tk.Frame(self.root, bg="#e74c3c", height=40)
        self.warning_label = tk.Label(
            self.warning_frame,
            text="",
            bg="#e74c3c",
            fg="white",
            font=("Arial", 11, "bold"),
            pady=8
        )
        self.warning_label.pack(fill=tk.X, expand=True)
        
        reset_btn = tk.Button(
            self.warning_frame,
            text="🔄 Resetuj śledzenie",
            command=self.reset_file_tracking_ui,
            bg="#c0392b",
            fg="white",
            font=self.FONT_BOLD,
            padx=10,
            pady=3,
            relief=tk.RAISED
        )
        reset_btn.pack(side=tk.RIGHT, padx=10)
        # Warning frame is packed dynamically in show_file_warning()
        
        # Notifications banner (for payment notifications)
        self.notifications_banner = tk.Frame(self.root, bg="#3498db", height=50)
        self.notifications_label = tk.Label(
            self.notifications_banner,
            text="",
            bg="#3498db",
            fg="white",
            font=("Arial", 11, "bold"),
            anchor=tk.W,
            padx=20
        )
        self.notifications_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tk.Button(
            self.notifications_banner,
            text="❌ Zamknij",
            command=self.hide_notifications_banner,
            bg="#2980b9",
            fg="white",
            font=("Arial", 9, "bold"),
            padx=10,
            pady=5
        ).pack(side=tk.RIGHT, padx=10)
        
        tk.Button(
            self.notifications_banner,
            text="📋 Zobacz wszystkie",
            command=self.show_all_notifications,
            bg="#27ae60",
            fg="white",
            font=("Arial", 9, "bold"),
            padx=10,
            pady=5
        ).pack(side=tk.RIGHT, padx=5)
        
        # Banner hidden by default
        # self.notifications_banner.pack() - will be shown when notifications exist
        
        # Main content - PanedWindow (horizontal split)
        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=6)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.main_paned = paned  # referencja do przywracania szerokości
        
        # LEFT PANEL - Stage buttons
        left_frame = tk.Frame(paned, bg="white")
        paned.add(left_frame, minsize=620, stretch='first')
        
        header = tk.Label(
            left_frame, 
            text="ETAPY PROJEKTU", 
            bg=self.COLOR_TOPBAR, 
            fg="white", 
            font=("Arial", 12, "bold"),
            pady=8
        )
        header.pack(fill=tk.X)
        
        # Scrollable frame dla buttons
        self.left_canvas = tk.Canvas(left_frame, highlightthickness=0, bg="white")
        scrollbar = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.left_canvas.yview)
        self.stages_frame = tk.Frame(self.left_canvas, bg="white")
        
        self.stages_frame.bind(
            "<Configure>",
            lambda e: self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))
        )
        
        self.left_canvas.create_window((0, 0), window=self.stages_frame, anchor="nw")
        self.left_canvas.configure(yscrollcommand=scrollbar.set)
        
        # Obsługa kółka myszy (Windows + Linux)
        def on_mousewheel_left(event):
            if event.num == 4:  # Linux scroll up
                self.left_canvas.yview_scroll(-3, "units")
            elif event.num == 5:  # Linux scroll down
                self.left_canvas.yview_scroll(3, "units")
            else:  # Windows
                self.left_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        def bind_mousewheel_left(event):
            self.left_canvas.bind_all("<MouseWheel>", on_mousewheel_left)
            self.left_canvas.bind_all("<Button-4>", on_mousewheel_left)
            self.left_canvas.bind_all("<Button-5>", on_mousewheel_left)

        def unbind_mousewheel_left(event):
            self.left_canvas.unbind_all("<MouseWheel>")
            self.left_canvas.unbind_all("<Button-4>")
            self.left_canvas.unbind_all("<Button-5>")
        
        self.left_canvas.bind("<Enter>", bind_mousewheel_left)
        self.left_canvas.bind("<Leave>", unbind_mousewheel_left)
        self.stages_frame.bind("<Enter>", bind_mousewheel_left)
        
        self.left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # RIGHT PANEL - Timeline & Info
        right_frame = tk.Frame(paned)
        paned.add(right_frame, minsize=400, stretch='last')
        
        # Zapisz pozycję sasha po przeciągnięciu (wyłączone - stała szerokość 400px)
        # paned.bind('<ButtonRelease-1>', on_sash_released)
        
        # Tabs
        tab_control = ttk.Notebook(right_frame)
        self.tab_control = tab_control
        
        # Tab 1: Oś czasu (interaktywny)
        self.timeline_tab = ttk.Frame(tab_control)
        tab_control.add(self.timeline_tab, text="📅 Oś czasu")
        
        # Canvas + scrollbar dla przewijania
        self.timeline_canvas = tk.Canvas(self.timeline_tab, highlightthickness=0)
        timeline_scrollbar = ttk.Scrollbar(self.timeline_tab, orient=tk.VERTICAL, command=self.timeline_canvas.yview)
        self.timeline_frame = tk.Frame(self.timeline_canvas, bg="white")
        
        self.timeline_frame.bind(
            "<Configure>",
            lambda e: self.timeline_canvas.configure(scrollregion=self.timeline_canvas.bbox("all"))
        )
        
        self.timeline_canvas.create_window((0, 0), window=self.timeline_frame, anchor="nw")
        self.timeline_canvas.configure(yscrollcommand=timeline_scrollbar.set)
        
        # Obsługa kółka myszy (Windows + Linux)
        def on_mousewheel_timeline(event):
            if event.num == 4:  # Linux scroll up
                self.timeline_canvas.yview_scroll(-3, "units")
            elif event.num == 5:  # Linux scroll down
                self.timeline_canvas.yview_scroll(3, "units")
            else:  # Windows
                self.timeline_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        def bind_mousewheel_timeline(event):
            self.timeline_canvas.bind_all("<MouseWheel>", on_mousewheel_timeline)
            self.timeline_canvas.bind_all("<Button-4>", on_mousewheel_timeline)
            self.timeline_canvas.bind_all("<Button-5>", on_mousewheel_timeline)

        def unbind_mousewheel_timeline(event):
            self.timeline_canvas.unbind_all("<MouseWheel>")
            self.timeline_canvas.unbind_all("<Button-4>")
            self.timeline_canvas.unbind_all("<Button-5>")
        
        self.timeline_canvas.bind("<Enter>", bind_mousewheel_timeline)
        self.timeline_canvas.bind("<Leave>", unbind_mousewheel_timeline)
        self.timeline_frame.bind("<Enter>", bind_mousewheel_timeline)
        
        self.timeline_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        timeline_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        
        # Tab 2: Podsumowanie
        self.dashboard_tab = ttk.Frame(tab_control)
        tab_control.add(self.dashboard_tab, text="📊 Podsumowanie")
        
        self.dashboard_text = scrolledtext.ScrolledText(
            self.dashboard_tab,
            font=('Courier New', 10),
            wrap=tk.WORD,
            state='disabled'
        )
        self.dashboard_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Tab 3: Wykresy (Plotly lub Matplotlib)
        if PLOTLY_AVAILABLE or MATPLOTLIB_AVAILABLE:
            self.chart_tab = ttk.Frame(tab_control)
            tab_control.add(self.chart_tab, text="📈 Wykresy")
            
            # Frame dla przycisków wykresu
            chart_controls = tk.Frame(self.chart_tab, bg=self.COLOR_TOPBAR, pady=5)
            chart_controls.pack(fill=tk.X, padx=5, pady=5)
            
            # Wbudowany wykres (matplotlib)
            if MATPLOTLIB_AVAILABLE:
                tk.Button(
                    chart_controls,
                    text="📊 Wykres wbudowany",
                    command=self.create_embedded_gantt_chart,
                    bg=self.COLOR_GREEN,
                    fg="white",
                    font=("Arial", 10, "bold"),
                    relief=tk.FLAT,
                    padx=15,
                    pady=5
                ).pack(side=tk.LEFT, padx=5)
                
                tk.Button(
                    chart_controls,
                    text="💾 Zapisz wykres",
                    command=self.save_embedded_chart,
                    bg=self.COLOR_ORANGE,
                    fg="white",
                    font=("Arial", 10),
                    relief=tk.FLAT,
                    padx=15,
                    pady=5
                ).pack(side=tk.LEFT, padx=5)
                
                tk.Button(
                    chart_controls,
                    text="📊 Multi-projekt",
                    command=self.open_multi_project_chart,
                    bg="#8e44ad",
                    fg="white",
                    font=("Arial", 10, "bold"),
                    relief=tk.FLAT,
                    padx=15,
                    pady=5
                ).pack(side=tk.LEFT, padx=5)
            
            # Plotly wykresy
            if PLOTLY_AVAILABLE:
                tk.Button(
                    chart_controls,
                    text="🌐 Gantt (przeglądarka)",
                    command=self.create_gantt_chart,
                    bg=self.COLOR_BLUE,
                    fg="white",
                    font=("Arial", 10),
                    relief=tk.FLAT,
                    padx=15,
                    pady=5
                ).pack(side=tk.LEFT, padx=5)
                
                tk.Button(
                    chart_controls,
                    text="💾 Eksport HTML",
                    command=self.export_chart_html,
                    bg=self.COLOR_ORANGE,
                    fg="white", 
                    font=("Arial", 10),
                    relief=tk.FLAT,
                    padx=15,
                    pady=5
                ).pack(side=tk.LEFT, padx=5)
                
                tk.Button(
                    chart_controls,
                    text="📈 Multi-projekt",
                    command=self.create_multi_project_gantt,
                    bg=self.COLOR_PURPLE,
                    fg="white",
                    font=("Arial", 10),
                    relief=tk.FLAT,
                    padx=15,
                    pady=5
                ).pack(side=tk.LEFT, padx=5)
                
                tk.Button(
                    chart_controls,
                    text="📊 Segmented Bar",
                    command=self.create_segmented_bar_chart,
                    bg="#16a085",
                    fg="white",
                    font=("Arial", 10),
                    relief=tk.FLAT,
                    padx=15,
                    pady=5
                ).pack(side=tk.LEFT, padx=5)
            
            # Status message dla wykresów
            self.chart_status = tk.Label(
                chart_controls,
                text="Wybierz projekt i utwórz wykres",
                bg=self.COLOR_TOPBAR,
                fg=self.COLOR_TEXT_DARK,
                font=("Arial", 9)
            )
            self.chart_status.pack(side=tk.LEFT, padx=20)
            
            # Matplotlib canvas (wbudowany wykres)
            if MATPLOTLIB_AVAILABLE:
                self.embedded_chart_frame = tk.Frame(self.chart_tab)
                self.embedded_chart_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                
                # Placeholder - canvas zostanie utworzony w create_embedded_gantt_chart()
                self.matplotlib_canvas = None
                self.matplotlib_toolbar = None
            
        # Tab 4: Historia
        self.history_tab = ttk.Frame(tab_control)
        tab_control.add(self.history_tab, text="📜 Historia")
        
        self.history_tree = ttk.Treeview(
            self.history_tab,
            columns=('stage', 'started', 'ended', 'duration', 'status'),
            show='headings',
            height=20
        )
        self.history_tree.heading('stage', text='Etap')
        self.history_tree.heading('started', text='Start')
        self.history_tree.heading('ended', text='Koniec')
        self.history_tree.heading('duration', text='Czas trwania')
        self.history_tree.heading('status', text='Status')
        
        self.history_tree.column('stage', width=120)
        self.history_tree.column('started', width=150)
        self.history_tree.column('ended', width=150)
        self.history_tree.column('duration', width=100)
        self.history_tree.column('status', width=100)
        
        history_scroll = ttk.Scrollbar(self.history_tab, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=history_scroll.set)
        
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        history_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        
        # Usuń podświetlenie przy kliknięciu poza wierszami lub utracie focusu
        self.history_tree.bind('<Button-1>', self._clear_history_selection_if_empty)
        self.history_tree.bind('<FocusOut>', lambda e: self.history_tree.selection_remove(self.history_tree.selection()))
        self.history_tree.bind('<Escape>', lambda e: self.history_tree.selection_remove(self.history_tree.selection()))
        
        # Tab 5: Płatności
        self.payment_tab = ttk.Frame(tab_control)
        tab_control.add(self.payment_tab, text="💳 Płatności")
        
        # === SEKCJA 1: PŁATNOŚCI ===
        payment_section = ttk.LabelFrame(self.payment_tab, text="Transze płatności", padding=10)
        payment_section.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Górny panel - kontrolki płatności
        payment_controls = tk.Frame(payment_section, bg=self.COLOR_TOPBAR, pady=10)
        payment_controls.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Button(
            payment_controls,
            text="➕ Dodaj transzę",
            command=self.add_payment_milestone,
            bg=self.COLOR_GREEN,
            fg="white",
            font=("Arial", 10, "bold"),
            relief=tk.FLAT,
            padx=15,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            payment_controls,
            text="✏️ Edytuj datę",
            command=self.edit_payment_milestone,
            bg=self.COLOR_ORANGE,
            fg="white",
            font=("Arial", 10),
            relief=tk.FLAT,
            padx=15,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            payment_controls,
            text="🗑️ Usuń transzę",
            command=self.delete_payment_milestone,
            bg=self.COLOR_RED,
            fg="white",
            font=("Arial", 10),
            relief=tk.FLAT,
            padx=15,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            payment_controls,
            text="📜 Historia zmian",
            command=self.show_payment_history,
            bg=self.COLOR_BLUE,
            fg="white",
            font=("Arial", 10),
            relief=tk.FLAT,
            padx=15,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        # Kontener dla treeview płatności
        payment_tree_frame = tk.Frame(payment_section)
        payment_tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Treeview z transzami płatności
        self.payment_tree = ttk.Treeview(
            payment_tree_frame,
            columns=('percentage', 'payment_date', 'created_by', 'modified_at'),
            show='headings',
            height=8
        )
        self.payment_tree.heading('percentage', text='Procent (%)')
        self.payment_tree.heading('payment_date', text='Data płatności')
        self.payment_tree.heading('created_by', text='Utworzył')
        self.payment_tree.heading('modified_at', text='Ostatnia zmiana')
        
        self.payment_tree.column('percentage', width=100, anchor='center')
        self.payment_tree.column('payment_date', width=120)
        self.payment_tree.column('created_by', width=100)
        self.payment_tree.column('modified_at', width=150)
        
        payment_scroll = ttk.Scrollbar(payment_tree_frame, orient=tk.VERTICAL, command=self.payment_tree.yview)
        self.payment_tree.configure(yscrollcommand=payment_scroll.set)
        
        self.payment_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        payment_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Double-click na treeview = edycja
        self.payment_tree.bind('<Double-1>', lambda e: self.edit_payment_milestone())
        
        # Usuń podświetlenie przy kliknięciu poza wierszami lub utracie focusu
        self.payment_tree.bind('<Button-1>', self._clear_payment_selection_if_empty)
        self.payment_tree.bind('<FocusOut>', lambda e: self.payment_tree.selection_remove(self.payment_tree.selection()))
        self.payment_tree.bind('<Escape>', lambda e: self.payment_tree.selection_remove(self.payment_tree.selection()))
        
        # === SEKCJA 2: KODY PLC ===
        plc_section = ttk.LabelFrame(self.payment_tab, text="Kody odblokowujące PLC", padding=10)
        plc_section.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Górny panel - kontrolki kodów PLC
        plc_controls = tk.Frame(plc_section, bg=self.COLOR_TOPBAR, pady=10)
        plc_controls.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Button(
            plc_controls,
            text="➕ Dodaj kod",
            command=self.add_plc_code,
            bg=self.COLOR_GREEN,
            fg="white",
            font=("Arial", 10, "bold"),
            relief=tk.FLAT,
            padx=15,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            plc_controls,
            text="✏️ Edytuj",
            command=self.edit_plc_code,
            bg=self.COLOR_ORANGE,
            fg="white",
            font=("Arial", 10),
            relief=tk.FLAT,
            padx=15,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            plc_controls,
            text="🗑️ Usuń",
            command=self.delete_plc_code,
            bg=self.COLOR_RED,
            fg="white",
            font=("Arial", 10),
            relief=tk.FLAT,
            padx=15,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            plc_controls,
            text="✅ Oznacz jako użyty",
            command=self.mark_plc_code_as_used,
            bg=self.COLOR_BLUE,
            fg="white",
            font=("Arial", 10),
            relief=tk.FLAT,
            padx=15,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            plc_controls,
            text="📤 Wyślij (użyj)",
            command=self.send_plc_code,
            bg="#9b59b6",
            fg="white",
            font=("Arial", 10, "bold"),
            relief=tk.FLAT,
            padx=15,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        # Kontener dla treeview kodów PLC
        plc_tree_frame = tk.Frame(plc_section)
        plc_tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Treeview z kodami PLC
        self.plc_codes_tree = ttk.Treeview(
            plc_tree_frame,
            columns=('code_type', 'unlock_code', 'description', 'is_used', 'used_at', 'expiry_date', 'created_by'),
            show='headings',
            height=8
        )
        self.plc_codes_tree.heading('code_type', text='Typ')
        self.plc_codes_tree.heading('unlock_code', text='Kod')
        self.plc_codes_tree.heading('description', text='Opis')
        self.plc_codes_tree.heading('is_used', text='Użyty')
        self.plc_codes_tree.heading('used_at', text='Data użycia')
        self.plc_codes_tree.heading('expiry_date', text='Ważny do')
        self.plc_codes_tree.heading('created_by', text='Utworzył')
        
        self.plc_codes_tree.column('code_type', width=100, anchor='center')
        self.plc_codes_tree.column('unlock_code', width=140)
        self.plc_codes_tree.column('description', width=180)
        self.plc_codes_tree.column('is_used', width=60, anchor='center')
        self.plc_codes_tree.column('used_at', width=110)
        self.plc_codes_tree.column('expiry_date', width=110)
        self.plc_codes_tree.column('created_by', width=100)
        
        plc_scroll = ttk.Scrollbar(plc_tree_frame, orient=tk.VERTICAL, command=self.plc_codes_tree.yview)
        self.plc_codes_tree.configure(yscrollcommand=plc_scroll.set)
        
        self.plc_codes_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        plc_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Double-click na treeview = edycja
        self.plc_codes_tree.bind('<Double-1>', lambda e: self.edit_plc_code())
        
        # Usuń podświetlenie przy kliknięciu poza wierszami lub utracie focusu
        self.plc_codes_tree.bind('<Button-1>', self._clear_plc_codes_selection_if_empty)
        self.plc_codes_tree.bind('<FocusOut>', lambda e: self.plc_codes_tree.selection_remove(self.plc_codes_tree.selection()))
        self.plc_codes_tree.bind('<Escape>', lambda e: self.plc_codes_tree.selection_remove(self.plc_codes_tree.selection()))
        
        tab_control.pack(fill=tk.BOTH, expand=True)
        
        # Status bar (styl RM_BAZA)
        self.status_bar = tk.Label(
            self.root, 
            text="🟢 Gotowy", 
            bg=self.COLOR_TOPBAR, 
            fg="white", 
            font=self.FONT_DEFAULT,
            anchor=tk.W,
            padx=10,
            pady=5
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    # ========================================================================
    # Data loading
    # ========================================================================

    def _get_user_display_name(self, username: str) -> str:
        """Pobierz display_name użytkownika na podstawie loginu (z tabeli users w master.sqlite)"""
        if not username:
            return "Nieznany"
        try:
            con = rmm._open_rm_connection(self.master_db_path, row_factory=False)
            row = con.execute(
                "SELECT display_name FROM users WHERE username = ?", (username,)
            ).fetchone()
            con.close()
            if row and row[0]:
                return row[0]
        except Exception:
            pass
        return username

    def _on_project_combo_click(self, event=None):
        """Odśwież listę projektów przy kliknięciu dropdown (debounce 5s) - identycznie jak RM_BAZA"""
        try:
            import time
            now = time.time()
            if now - self._projects_last_refresh_ts < self._projects_refresh_interval_s:
                return
            self._projects_last_refresh_ts = now
            old_selection = self.project_combo.get()
            self._refresh_combo_lock_info()
        except Exception as e:
            print(f"⚠️  _on_project_combo_click error: {e}")
            import traceback
            traceback.print_exc()

    def _refresh_combo_lock_info(self):
        """Odśwież display values combo projektów (lock info) bez resetu selekcji"""
        if not self.projects:
            return
        current_idx = self.project_combo.current()
        is_stub = getattr(self.lock_manager, '_STUB', False)
        combo_values = []
        for pid in self.projects:
            name = self.project_names.get(pid, f"Projekt {pid}")

            # Zachowaj prefiks statusu jak w load_projects: [A]/[W]/[Z]
            status_prefix = "[A]"  # Aktywny
            try:
                project_db = self.get_project_db_path(pid)
                if os.path.exists(project_db):
                    is_finished = rmm.is_milestone_set(project_db, pid, 'ZAKONCZONY')
                    if is_finished:
                        status_prefix = "[Z]"  # Zakończony
                    else:
                        is_paused = rmm.is_project_paused(project_db, pid)
                        if is_paused:
                            status_prefix = "[W]"  # Wstrzymany
            except Exception:
                pass

            if not is_stub:
                try:
                    lock_info = self.lock_manager.get_project_lock_owner(pid)
                    if lock_info and lock_info.get('user'):
                        locked_by = self._get_user_display_name(lock_info['user'])
                        name = f"{name} 🔒 [{locked_by}]"
                except Exception:
                    pass
            combo_values.append(f"{status_prefix}     {name}")
        self.project_combo['values'] = combo_values
        if current_idx >= 0:
            self.project_combo.current(current_idx)

    def load_projects(self):
        """Załaduj listę projektów z RM_BAZA master.sqlite"""
        try:
            if not os.path.exists(self.master_db_path):
                # Zapytaj użytkownika czy chce skonfigurować ścieżkę
                result = messagebox.askyesno(
                    "⚠️ Brak master.sqlite",
                    f"Nie znaleziono bazy RM_BAZA:\n{self.master_db_path}\n\nCzy chcesz skonfigurować ścieżkę?"
                )
                if result:
                    self.edit_config()
                    if not os.path.exists(self.master_db_path):
                        self.status_bar.config(text="⚠️ Nieprawidłowa ścieżka", fg="#f39c12")
                        return
                else:
                    self.status_bar.config(text="⚠️ Brak master.sqlite", fg="#f39c12")
                    return
            
            con = rmm._open_rm_connection(self.master_db_path)
            
            # Bezpośrednie SQL - bez project_manager
            cursor = con.execute("""
                SELECT 
                    project_id as pid,
                    name,
                    COALESCE(active, 1) as active
                FROM projects
                WHERE COALESCE(active, 1) = 1
                  AND COALESCE(project_type, 'MACHINE') = 'MACHINE'
                ORDER BY name COLLATE NOCASE
            """)
            
            rows = cursor.fetchall()
            con.close()
            
            # Format projektów
            self.projects = []
            self.project_names = {}
            
            for row in rows:
                pid = row['pid']
                pname = row['name'] or f"Projekt {pid}"
                self.projects.append(pid)
                self.project_names[pid] = pname
            
            # Sortowanie identyczne jak RM_BAZA: cyfry malejąco → litery A-Z + numery malejąco
            def sort_key(pid):
                name_lower = self.project_names.get(pid, '').lower()
                import re
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
            
            combo_values = []
            is_stub = getattr(self.lock_manager, '_STUB', False)
            for pid in self.projects:
                name = self.project_names.get(pid, f"Projekt {pid}")
                
                # Sprawdź status projektu i dodaj stałoszerokościowy prefiks
                status_prefix = "[A]"  # Aktywny
                try:
                    project_db = self.get_project_db_path(pid)
                    if os.path.exists(project_db):
                        # Sprawdź czy zakończony
                        is_finished = rmm.is_milestone_set(project_db, pid, 'ZAKONCZONY')
                        if is_finished:
                            status_prefix = "[Z]"  # Zakończony
                        else:
                            # Sprawdź czy wstrzymany
                            is_paused = rmm.is_project_paused(project_db, pid)
                            if is_paused:
                                status_prefix = "[W]"  # Wstrzymany
                except Exception:
                    pass
                
                # Sprawdź lock (pomiń stub - nie ma prawdziwych locków)
                if not is_stub:
                    try:
                        lock_info = self.lock_manager.get_project_lock_owner(pid)
                        if lock_info and lock_info.get('user'):
                            locked_by = self._get_user_display_name(lock_info['user'])
                            name = f"{name} 🔒 [{locked_by}]"
                    except Exception:
                        pass
                combo_values.append(f"{status_prefix}     {name}")
            
            self.project_combo['values'] = combo_values
            
            if self.projects:
                self.project_combo.current(0)
                self.on_project_selected(None)
            
            self.status_bar.config(
                text=f"🟢 Załadowano {len(self.projects)} projektów z RM_BAZA", 
                fg="#27ae60"
            )
            
        except Exception as e:
            print(f"🔴 Błąd ładowania projektów z {self.master_db_path}:")
            print(f"   Błąd: {e}")
            print(f"   Plik istnieje: {os.path.exists(self.master_db_path)}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("❌ Błąd", f"Nie można załadować projektów z master.sqlite:\n{e}")
            self.status_bar.config(text=f"🔴 Błąd ładowania", fg="#e74c3c")
    
    def on_project_selected(self, event):
        """Obsługa wyboru projektu"""
        idx = self.project_combo.current()
        if idx < 0:
            return

        new_project_id = self.projects[idx]

        # Jeśli ten sam projekt - skip
        if self.selected_project_id == new_project_id:
            return

        # Jeśli mamy lock na obecnym projekcie - dialog 3-opcyjny (wzór RM_BAZA)
        if self.have_lock and self.selected_project_id is not None:
            current_name = self.project_names.get(
                self.selected_project_id, f"Projekt {self.selected_project_id}"
            )
            new_name = self.project_names.get(new_project_id, f"Projekt {new_project_id}")

            result = messagebox.askyesnocancel(
                "Zmiana projektu",
                f"Masz aktywny lock na projekcie: {current_name}\n\n"
                f"TAK - zwolnij lock i przejdź do: {new_name}\n"
                f"ANULUJ / zamknięcie okna - zwolnij lock bez zapisu i przejdź do: {new_name}\n"
                f"NIE - zostań na projekcie: {current_name}",
                icon='warning',
                parent=self.root
            )

            if result is None:  # ANULUJ (lub krzyżyk) - zdejmij lock i przejdź
                self._release_current_lock()
            elif result is True:  # TAK - zwolnij lock (z zapisem) i przejdź
                self._release_current_lock()
            else:  # NIE (False) - zostań, przywróć dropdown
                try:
                    current_idx = self.projects.index(self.selected_project_id)
                    self.project_combo.current(current_idx)
                except ValueError:
                    pass
                return

        self.selected_project_id = new_project_id

        # Wyzeruj stan locka - nowy projekt zawsze zaczyna w READ-ONLY
        self.have_lock = False
        self.current_lock_id = None
        self._locked_project_id = None
        self.read_only_mode = True
        
        # Reset flag renderowania komponentów (zapobiega duplikacji transport)
        self._transport_rendered_for_project = None
        
        # Odczytaj % ODEBRANO z master.sqlite (kolumna received_percent)
        try:
            con = rmm._open_rm_connection(self.master_db_path)
            cursor = con.execute(
                "SELECT received_percent FROM projects WHERE project_id = ?",
                (new_project_id,)
            )
            row = cursor.fetchone()
            con.close()
            if row and row['received_percent']:
                self.received_percent = row['received_percent']
            else:
                self.received_percent = "?"
        except Exception:
            # Błąd odczytu (np. kolumna nie istnieje) - ustaw "?" jako placeholder
            self.received_percent = "?"

        # LAZY INIT: Utwórz per-projekt bazę jeśli nie istnieje
        self.ensure_project_initialized()

        # Pobierz status projektu
        ui_rules = self._get_ui_button_states()
        status_text = ui_rules.get('status_text', '')
        
        # Sprawdź czy ktoś ma lock (informacja do status bar)
        owner = self.lock_manager.get_project_lock_owner(self.selected_project_id)
        if owner:
            locked_by = self._get_user_display_name(owner.get('user', '?'))
            self.status_bar.config(
                text=f"🔒 Projekt {self.selected_project_id} [{status_text}] - zajęty przez {locked_by} (READ-ONLY)",
                fg="#e74c3c"
            )
        else:
            self.status_bar.config(
                text=f"🔓 Projekt {self.selected_project_id} [{status_text}] - READ-ONLY (kliknij 'Przejmij Lock' aby edytować)",
                fg="#f39c12"
            )

        # Aktualizuj przyciski lock
        self._update_lock_buttons_state()

        # FILE INTEGRITY: Weryfikuj plik projektu
        self.verify_project_file_integrity()

        # 🧹 Migracja: zamknij osierocone WSTRZYMANY stage periods (stary mechanizm)
        try:
            rmm.cleanup_orphaned_wstrzymany(
                self.get_project_db_path(self.selected_project_id), self.selected_project_id)
        except Exception:
            pass

        self.load_project_stages()
        self.refresh_timeline()
        self.refresh_dashboard()
        self.refresh_history()
        self.create_embedded_gantt_chart(preserve_view=False)
        
        # Sprawdź alarmy dla tego projektu
        self.check_alarms()
        
        # Załaduj dostępne backupy do combobox
        self.load_backup_dates()

    
    def ensure_project_initialized(self):
        """Upewnij się że projekt istnieje w RM_MANAGER (lazy init)"""
        if not self.selected_project_id:
            return
        
        try:
            project_db = self.get_project_db_path(self.selected_project_id)
            # Zawsze inicjalizuj tabele (idempotentne - CREATE IF NOT EXISTS)
            rmm.ensure_project_tables(project_db)

            # Diagnostyka: sprawdź czy plik bazy istnieje
            if not os.path.exists(project_db):
                print(f"📁 Plik bazy projektu nie istnieje: {project_db}")
                print(f"   Katalog RM: {os.path.exists(self.rm_projects_dir)}")
                print(f"   Uprawnienia do zapisu: {os.access(os.path.dirname(project_db), os.W_OK) if os.path.exists(os.path.dirname(project_db)) else 'katalog nie istnieje'}")
                count = 0
            else:
                print(f"📁 Sprawdzam projekt w bazie: {project_db}")
                print(f"   Rozmiar pliku: {os.path.getsize(project_db)} B")
                
                con = rmm._open_rm_connection(project_db, row_factory=False)
                try:
                    # Sprawdź czy tabele istnieją
                    cursor = con.execute("""
                        SELECT name FROM sqlite_master WHERE type='table' AND name='project_stages'
                    """)
                    has_table = cursor.fetchone() is not None
                    
                    if not has_table:
                        print(f"⚠️ Tabela project_stages nie istnieje - tworzę strukturę")
                        con.close()
                        rmm.ensure_project_tables(project_db)
                        con = rmm._open_rm_connection(project_db, row_factory=False)
                    
                    cursor = con.execute("""
                        SELECT COUNT(*) FROM project_stages WHERE project_id = ?
                    """, (self.selected_project_id,))
                    count = cursor.fetchone()[0]
                    print(f"📊 Znaleziono {count} etapów dla projektu {self.selected_project_id}")
                except sqlite3.Error as db_error:
                    print(f"🔴 Błąd SQLite: {db_error}")
                    count = 0
                finally:
                    con.close()

            if count == 0:
                # Projekt nie istnieje w RM_MANAGER - pytaj użytkownika czy tworzyć
                result = messagebox.askyesno(
                    "🆕 Utworzyć projekt RM_MANAGER?",
                    f"Projekt {self.selected_project_id} nie istnieje jeszcze w RM_MANAGER.\n\n"
                    f"Czy chcesz utworzyć nowy projekt RM_MANAGER z domyślnymi etapami?\n\n"
                    f"TAK - Utwórz nowy projekt\n"
                    f"NIE - Pozostań w trybie tylko do odczytu",
                    icon='question'
                )
                
                if result:
                    # TAK - utwórz projekt
                    self.status_bar.config(text=f"⏳ Tworzenie projektu {self.selected_project_id}...", fg="#f39c12")
                    self.root.update()
                    self.auto_initialize_project()
                    
                    # 🔧 Nowy projekt w RM_MANAGER → ZAWSZE reset statusu na NEW
                    # (stary status w master.sqlite mógł być ACCEPTED/IN_PROGRESS z poprzedniej sesji)
                    print(f"🔧 Reset statusu projektu {self.selected_project_id} na NEW (nowo utworzony w RM_MANAGER)")
                    try:
                        rmm.set_project_status(self.master_db_path, self.selected_project_id, ProjectStatus.NEW)
                    except Exception as e:
                        print(f"⚠️ Nie udało się ustawić statusu: {e}")
                    
                    self.status_bar.config(text=f"🟢 Projekt {self.selected_project_id} utworzony", fg="#27ae60")
                else:
                    # NIE - tryb read-only
                    self.read_only_mode = True
                    self.status_bar.config(text=f"👁️ Projekt {self.selected_project_id} - TYLKO ODCZYT (nie ma w RM_MANAGER)", fg="#f39c12")
                    return
            else:
                # Projekt istnieje - upewnij się że ma wszystkie etapy, poprawne sequence i zależności
                rmm.ensure_all_stages_for_all_projects(project_db)
                rmm.fix_stage_sequence_for_all_projects(project_db)
                rmm.ensure_default_dependencies_for_project(project_db, self.selected_project_id)

        except Exception as e:
            print(f"⚠️ Błąd ensure_project_initialized dla projektu {self.selected_project_id}: {e}")
            print(f"   Ścieżka bazy: {project_db}")
            print(f"   Plik istnieje: {os.path.exists(project_db) if 'project_db' in locals() else 'N/A'}")
            import traceback
            traceback.print_exc()
            
            # Ustaw tryb read-only przy błędzie
            self.read_only_mode = True
            self.status_bar.config(text=f"🔴 Błąd inicjalizacji projektu {self.selected_project_id}", fg="#e74c3c")
    
    def load_backup_dates(self):
        """Załaduj dostępne daty backupów dla bieżącego projektu"""
        if not self.selected_project_id or not self.backup_manager:
            self.backup_combo['values'] = ["Aktualny stan"]
            self.backup_combo.set("Aktualny stan")
            return
        
        try:
            # Pobierz listę backupów projektu
            backups = self.backup_manager.list_project_backups(self.selected_project_id)
            
            # Sortuj od najnowszych
            dates = [b['date'] for b in backups]
            
            # Dodaj "Aktualny stan" na początku
            values = ["Aktualny stan"] + dates
            
            self.backup_combo['values'] = values
            self.backup_combo.set("Aktualny stan")
            
        except Exception as e:
            print(f"⚠️  Błąd ładowania backupów: {e}")
            self.backup_combo['values'] = ["Aktualny stan"]
            self.backup_combo.set("Aktualny stan")
    
    def on_backup_selected(self, event=None):
        """Wybrano datę backupu do podglądu"""
        selected = self.backup_date_var.get()
        
        if selected == "Aktualny stan":
            # Wróć do aktualnego stanu
            if self.viewing_backup:
                self.viewing_backup = False
                self.backup_date = None
                self.backup_db_path = None  # Wyczyść ścieżkę backupu
                
                # Reaktywuj przyciski lock (jeśli nie mamy locka)
                if not self.have_lock:
                    self.btn_acquire_lock.config(state=tk.NORMAL)
                    self.btn_force_lock.config(state=tk.NORMAL)
                
                # PEŁNE ODŚWIEŻENIE wszystkich sekcji
                print("📄 Powrót do aktualnego stanu - odświeżam wszystko...")
                self.refresh_all()
                
                # Przywróć prawidłowy status
                ui_rules = self._get_ui_button_states()
                status_text = ui_rules.get('status_text', '')
                owner = self.lock_manager.get_project_lock_owner(self.selected_project_id)
                if owner:
                    locked_by = self._get_user_display_name(owner.get('user', '?'))
                    self.status_bar.config(
                        text=f"🔒 Projekt {self.selected_project_id} [{status_text}] - zajęty przez {locked_by} (READ-ONLY)",
                        fg="#e74c3c"
                    )
                else:
                    self.status_bar.config(
                        text=f"🔓 Projekt {self.selected_project_id} [{status_text}] - READ-ONLY (kliknij 'Przejmij Lock' aby edytować)",
                        fg="#f39c12"
                    )
                
                print("✅ Powrót do aktualnego stanu zakończony")
        else:
            # Załaduj podgląd backupu
            self.viewing_backup = True
            self.backup_date = selected
            self.load_backup_preview(selected)
    
    def load_backup_preview(self, backup_date: str):
        """Załaduj dane z backupu do podglądu"""
        if not self.selected_project_id or not self.backup_manager:
            return
        
        try:
            # Ścieżka do backupu
            project_backup_subdir = self.backup_manager.projects_backup_dir / f"project_{self.selected_project_id}"
            backup_file = project_backup_subdir / f"project_{self.selected_project_id}_{backup_date}.sqlite"
            
            if not backup_file.exists():
                messagebox.showerror("Błąd", f"Backup z {backup_date} nie istnieje!")
                self.backup_combo.set("Aktualny stan")
                return
            
            # Wczytaj dane z backupu
            print(f"\n📅 Ładuję podgląd backupu z {backup_date}...")
            self.status_bar.config(
                text=f"PODGLĄD BACKUPU z {backup_date} (TYLKO ODCZYT)",
                fg="#f39c12"
            )
            
            # Dezaktywuj przyciski Lock
            self.btn_acquire_lock.config(state=tk.DISABLED)
            self.btn_force_lock.config(state=tk.DISABLED)
            self.btn_cancel_lock.config(state=tk.DISABLED)
            
            # Ustaw ścieżkę do backupu (żeby get_project_db_path zwracała backup)
            self.backup_db_path = str(backup_file)
            
            # Pobierz statystyki backupu
            stats_info = self._get_backup_stats(backup_file)
            
            # ODŚWIEŻ CAŁY GUI danymi z backupu
            print("🔄 Odświeżam GUI danymi z backupu...")
            self.refresh_all()
            
            messagebox.showinfo(
                "Podgląd backupu",
                f"Wyświetlam dane z backupu projektu z dnia:\n{backup_date}\n\n"
                f"{stats_info}\n\n"
                "To jest tylko PODGLĄD - nie możesz edytować.\n"
                "Aby wrócić do aktualnego stanu, wybierz 'Aktualny stan'."
            )
            
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się załadować backupu:\n{e}")
            self.backup_combo.set("Aktualny stan")
            self.viewing_backup = False
            self.backup_date = None
            self.backup_db_path = None
            import traceback
            traceback.print_exc()
    
    def _get_backup_stats(self, backup_path):
        """Pobierz statystyki z backupu (ile etapów, okresów, aktywnych etapów)"""
        from pathlib import Path
        
        try:
            backup_con = rmm._open_rm_connection(str(backup_path), row_factory=True)
            try:
                # Sprawdź schemat
                cursor = backup_con.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                
                if 'project_stages' not in tables:
                    return "Backup nie zawiera danych RM_MANAGER"
                
                cursor = backup_con.execute("PRAGMA table_info(project_stages)")
                cols = [row[1] for row in cursor.fetchall()]
                has_project_id = 'project_id' in cols
                
                if has_project_id:
                    where_clause = "WHERE project_id = ?"
                    params = (self.selected_project_id,)
                else:
                    where_clause = ""
                    params = ()
                
                # Statystyki
                cursor = backup_con.execute(f"SELECT COUNT(*) FROM project_stages {where_clause}", params)
                stages_count = cursor.fetchone()[0]
                
                cursor = backup_con.execute(f"""
                    SELECT COUNT(*) FROM stage_actual_periods
                    {f"WHERE project_stage_id IN (SELECT id FROM project_stages {where_clause})" if has_project_id else ""}
                """, params)
                periods_count = cursor.fetchone()[0]
                
                # Aktywne etapy
                if 'stage_definitions' in tables:
                    query = f"""
                        SELECT sd.display_name, sap.started_at, sap.ended_at
                        FROM project_stages ps
                        JOIN stage_definitions sd ON ps.stage_code = sd.code
                        LEFT JOIN stage_actual_periods sap ON sap.project_stage_id = ps.id AND sap.ended_at IS NULL
                        {where_clause}
                        ORDER BY ps.sequence
                    """
                    cursor = backup_con.execute(query, params)
                    stages = cursor.fetchall()
                    active_stages = [s for s in stages if s['started_at']]
                else:
                    active_stages = []
                
                # Formatuj statystyki
                stats = f"📊 Etapy: {stages_count}, Okresy: {periods_count}\n"
                if active_stages:
                    stats += f"🔄 Aktywne: {len(active_stages)}\n"
                    for s in active_stages[:3]:  # Pokaż max 3
                        stats += f"  • {s['display_name']}\n"
                    if len(active_stages) > 3:
                        stats += f"  ... i {len(active_stages) - 3} więcej"
                
                return stats
                
            finally:
                backup_con.close()
        except Exception as e:
            return f"Błąd odczytu statystyk: {e}"
    
    def _load_stages_from_backup(self, backup_path):
        """Załaduj etapy z pliku backupu i wyświetl w timeline/dashboard"""
        import time
        from pathlib import Path
        
        # DEBUG - wypisz info o pliku
        time.sleep(0.2)
        
        print(f"\n  📂 Backup file: {backup_path}")
        print(f"  📏 Rozmiar: {backup_path.stat().st_size / 1024:.1f} KB")
        print(f"  🕐 Modyfikacja: {datetime.fromtimestamp(backup_path.stat().st_mtime)}")
        
        # Połącz z backupem
        backup_con = rmm._open_rm_connection(str(backup_path), row_factory=True)
        
        try:
            # Sprawdź jakie tabele są w backupie
            cursor = backup_con.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            print(f"  📋 Tabele w backupie: {tables}")
            
            # Sprawdź kolumny w project_stages
            if 'project_stages' in tables:
                cursor = backup_con.execute("PRAGMA table_info(project_stages)")
                cols = [row[1] for row in cursor.fetchall()]
                print(f"  📋 Kolumny w project_stages: {cols}")
                has_project_id = 'project_id' in cols
            else:
                print(f"  ⚠️  Brak tabeli project_stages - to nie jest backup RM_MANAGER!")
                messagebox.showerror("Błąd", "Ten backup nie zawiera danych RM_MANAGER")
                return
            
            # Dostosuj zapytania w zależności od schematu
            if has_project_id:
                # Nowy format - z project_id
                where_clause = "WHERE project_id = ?"
                params = (self.selected_project_id,)
            else:
                # Stary format - bez project_id (cała baza dla jednego projektu)
                where_clause = ""
                params = ()
            
            # Pobierz statystyki backupu
            cursor = backup_con.execute(f"""
                SELECT COUNT(*) as cnt FROM project_stages {where_clause}
            """, params)
            stages_count = cursor.fetchone()[0]
            
            cursor = backup_con.execute(f"""
                SELECT COUNT(*) as cnt FROM stage_actual_periods
                {f"WHERE project_stage_id IN (SELECT id FROM project_stages {where_clause})" if has_project_id else ""}
            """, params)
            periods_count = cursor.fetchone()[0]
            
            if 'stage_dependencies' in tables:
                cursor = backup_con.execute(f"""
                    SELECT COUNT(*) as cnt FROM stage_dependencies {where_clause}
                """, params)
                dependencies_count = cursor.fetchone()[0]
            else:
                dependencies_count = 0
            
            # Sprawdź czy stage_definitions jest w backupie czy trzeba łączyć z master
            has_stage_definitions = 'stage_definitions' in tables
            
            # Pobierz aktywne etapy z backupu
            if has_stage_definitions:
                # Backup zawiera stage_definitions
                # UWAGA: stage_definitions ma kolumny 'code' i 'display_name' (nie 'stage_code' i 'stage_name')
                if has_project_id:
                    # Nowy format - z project_id
                    cursor = backup_con.execute("""
                        SELECT 
                            ps.stage_code,
                            sd.display_name as stage_name,
                            sap.started_at,
                            sap.ended_at
                        FROM project_stages ps
                        JOIN stage_definitions sd ON ps.stage_code = sd.code
                        LEFT JOIN stage_actual_periods sap ON sap.project_stage_id = ps.id 
                            AND sap.ended_at IS NULL
                        WHERE ps.project_id = ?
                        ORDER BY ps.sequence
                    """, (self.selected_project_id,))
                else:
                    # Stary format - bez project_id
                    cursor = backup_con.execute("""
                        SELECT 
                            ps.stage_code,
                            sd.display_name as stage_name,
                            sap.started_at,
                            sap.ended_at
                        FROM project_stages ps
                        JOIN stage_definitions sd ON ps.stage_code = sd.code
                        LEFT JOIN stage_actual_periods sap ON sap.project_stage_id = ps.id 
                            AND sap.ended_at IS NULL
                        ORDER BY ps.sequence
                    """)
                
                stages_data = cursor.fetchall()
            else:
                # Backup per-projekt - stage_definitions w master DB
                # Pobierz stage_codes z backupu
                if has_project_id:
                    cursor = backup_con.execute("""
                        SELECT 
                            ps.stage_code,
                            ps.sequence,
                            sap.started_at,
                            sap.ended_at
                        FROM project_stages ps
                        LEFT JOIN stage_actual_periods sap ON sap.project_stage_id = ps.id 
                            AND sap.ended_at IS NULL
                        WHERE ps.project_id = ?
                        ORDER BY ps.sequence
                    """, (self.selected_project_id,))
                else:
                    cursor = backup_con.execute("""
                        SELECT 
                            ps.stage_code,
                            ps.sequence,
                            sap.started_at,
                            sap.ended_at
                        FROM project_stages ps
                        LEFT JOIN stage_actual_periods sap ON sap.project_stage_id = ps.id 
                            AND sap.ended_at IS NULL
                        ORDER BY ps.sequence
                    """)
                
                stages_raw = cursor.fetchall()
                
                # Pobierz nazwy etapów z master DB (RM_MANAGER)
                # UWAGA: rm_manager.sqlite ma stage_definitions z kolumnami 'code' i 'display_name'
                master_con = rmm._open_rm_connection(self.rm_db_path, row_factory=True)
                try:
                    stage_names = {}
                    cursor = master_con.execute("SELECT code, display_name FROM stage_definitions")
                    for row in cursor.fetchall():
                        stage_names[row['code']] = row['display_name']
                finally:
                    master_con.close()
                
                # Połącz dane
                stages_data = []
                for stage in stages_raw:
                    stages_data.append({
                        'stage_code': stage['stage_code'],
                        'stage_name': stage_names.get(stage['stage_code'], stage['stage_code']),
                        'started_at': stage['started_at'],
                        'ended_at': stage['ended_at']
                    })
            
            # Wyświetl podsumowanie w message box
            summary = f"📊 STATYSTYKI BACKUPU z {self.backup_date}:\n\n"
            summary += f"• Etapy: {stages_count}\n"
            summary += f"• Okresy: {periods_count}\n"
            summary += f"• Zależności: {dependencies_count}\n\n"
            summary += f"🔄 AKTYWNE ETAPY:\n\n"
            
            for stage in stages_data:
                # Obsługa zarówno Row jak i dict
                if isinstance(stage, dict):
                    stage_name = stage.get('stage_name', '?')
                    started_at = stage.get('started_at')
                    ended_at = stage.get('ended_at')
                else:
                    stage_name = stage['stage_name']
                    started_at = stage['started_at']
                    ended_at = stage['ended_at']
                
                if started_at:
                    end_info = f" → {ended_at[:10]}" if ended_at else " → (w trakcie)"
                    summary += f"• {stage_name}: {started_at[:10]}{end_info}\n"
            
            # Wyświetl w status_bar skróconą wersję
            active_count = sum(1 for s in stages_data if (s.get('started_at') if isinstance(s, dict) else s['started_at']) and not (s.get('ended_at') if isinstance(s, dict) else s['ended_at']))
            self.status_bar.config(
                text=f"📅 PODGLĄD BACKUPU {self.backup_date}: {active_count} etapów aktywnych",
                fg="#f39c12"
            )
            
            # Wyświetl pełne podsumowanie w konsoli
            print(summary)
            
            # WAŻNE: W trybie backupu NIE odświeżamy timeline/dashboard
            # (dane są w aktualnej bazie, backup jest tylko informacyjny)
            
        finally:
            backup_con.close()
    
    def auto_initialize_project(self):
        """Automatyczna inicjalizacja projektu w RM_MANAGER"""
        print(f"🔨 Rozpoczynam auto-inicjalizację projektu {self.selected_project_id}")
        
        # Pobierz daty z master.sqlite (jeśli są)
        master_data = self.get_project_dates_from_master()
        print(f"📅 Dane z master.sqlite: {master_data}")
        
        # Sprawdź czy katalog istnieje
        if not os.path.exists(self.rm_projects_dir):
            print(f"📁 Tworzę katalog RM_MANAGER: {self.rm_projects_dir}")
            os.makedirs(self.rm_projects_dir, exist_ok=True)
        
        # Wygeneruj stages_config
        stages_config = []
        base_date = master_data.get('started_at') or datetime.now().isoformat()[:10]
        current_date = datetime.fromisoformat(base_date)
        print(f"📅 Data bazowa: {base_date}")
        
        for seq, stage_code in enumerate(DEFAULT_STAGE_SEQUENCE, 1):
            # 🔵 Punkty kontrolne (sub-milestones) NIE dostają domyślnych dat
            is_sub_milestone = stage_code in _CHILD_MILESTONE_CODES
            
            if is_sub_milestone:
                # Punkty kontrolne - bez dat (użytkownik wypełni ręcznie)
                stages_config.append({
                    'code': stage_code,
                    'sequence': seq
                })
            else:
                # Normalne etapy - szacuj domyślną długość
                duration_days = 7
                if stage_code == 'PROJEKT':
                    duration_days = 14
                elif stage_code == 'KOMPLETACJA':
                    duration_days = 10
                elif stage_code == 'MONTAZ':
                    duration_days = 21
                elif stage_code == 'ELEKTROMONTAZ':
                    duration_days = 14
                elif stage_code == 'ZAKONCZONY':
                    duration_days = 1
                
                end_date = current_date + timedelta(days=duration_days)
                
                stages_config.append({
                    'code': stage_code,
                    'template_start': current_date.isoformat()[:10],
                    'template_end': end_date.isoformat()[:10],
                    'sequence': seq
                })
                
                current_date = end_date
        
        # Inicjalizuj projekt (per-projekt baza)
        rmm.init_project(
            self.get_project_db_path(self.selected_project_id),
            self.selected_project_id,
            stages_config,
            DEFAULT_DEPENDENCIES
        )
        
        print(f"✅ Auto-initialized projekt {self.selected_project_id} w RM_MANAGER")
    
    def get_project_dates_from_master(self) -> dict:
        """Pobierz daty projektu z master.sqlite"""
        try:
            con = rmm._open_rm_connection(self.master_db_path)
            
            cursor = con.execute("""
                SELECT started_at, expected_delivery, completed_at
                FROM projects
                WHERE project_id = ?
            """, (self.selected_project_id,))
            
            row = cursor.fetchone()
            con.close()
            
            if row:
                return {
                    'started_at': row['started_at'],
                    'expected_delivery': row['expected_delivery'],
                    'completed_at': row['completed_at']
                }
        except Exception as e:
            print(f"⚠️ Błąd get_project_dates_from_master: {e}")
        
        return {}
    
    def verify_project_file_integrity(self):
        """Weryfikuj integralność pliku projektu RM_BAZA"""
        if not self.selected_project_id:
            return
        
        project_name = self.project_names.get(self.selected_project_id, f"Projekt_{self.selected_project_id}")
        
        # Sprawdź czy projekt jest zarejestrowany w systemie śledzenia
        try:
            con = rmm._open_rm_connection(self.rm_master_db_path, row_factory=False)
            cursor = con.execute("""
                SELECT COUNT(*) FROM project_file_tracking WHERE project_id = ?
            """, (self.selected_project_id,))
            count = cursor.fetchone()[0]
            con.close()

            if count == 0:
                # Pierwszy dostęp - zarejestruj plik
                print(f"📝 Rejestracja pliku projektu {self.selected_project_id}...")
                rmm.register_project_file(
                    self.rm_master_db_path,
                    self.selected_project_id,
                    project_name,
                    self.master_db_path,
                    projects_path=self.projects_path
                )

            # Weryfikuj plik (ścieżka konstruowana z LOKALNEJ konfiguracji!)
            is_valid, status, message = rmm.verify_project_file(
                self.rm_master_db_path,
                self.selected_project_id,
                projects_path=self.projects_path  # ⚡ KLUCZOWE: przekaż lokalny config!
            )
            
            if is_valid:
                # Plik OK
                self.read_only_mode = False
                self.hide_file_warning()
                self.status_bar.config(text=f"🟢 Projekt {self.selected_project_id} - plik prawidłowy", fg="#27ae60")
            else:
                # Plik nieprawidłowy - tryb READ-ONLY
                self.read_only_mode = True
                self.file_verification_message = message
                self.show_file_warning(status, message)
                self.status_bar.config(text=f"⚠️ TRYB TYLKO DO ODCZYTU", fg="#e74c3c")
        
        except Exception as e:
            print(f"⚠️ Błąd weryfikacji pliku projektu {self.selected_project_id}: {e}")
            print(f"   Master DB: {self.rm_master_db_path}")
            print(f"   Projects path: {getattr(self, 'projects_path', 'N/A')}")
            import traceback
            traceback.print_exc()
            self.read_only_mode = False
            self.hide_file_warning()
    
    def show_file_warning(self, status: str, message: str):
        """Pokaż ostrzeżenie o nieprawidłowym pliku"""
        if status == 'MISSING':
            warning_text = f"⚠️ PLIK PROJEKTU NIE ISTNIEJE - Tryb tylko do odczytu"
        elif status == 'BIRTH_MISMATCH':
            warning_text = f"⚠️ PLIK PROJEKTU ZMIENIONY - Tryb tylko do odczytu"
        elif status == 'CONTENT_MISMATCH':
            warning_text = f"⚠️ PLIK PROJEKTU PODMIENIONY (inny project_id) - Tryb tylko do odczytu"
        else:
            warning_text = f"⚠️ {message}"
        
        self.warning_label.config(text=warning_text)
        self.warning_frame.pack(fill=tk.X, after=self.top_frame)
    
    def hide_file_warning(self):
        """Ukryj ostrzeżenie o nieprawidłowym pliku"""
        self.warning_frame.pack_forget()
    
    def reset_file_tracking_ui(self):
        """Reset śledzenia pliku (wywołanie z GUI)"""
        if not self.selected_project_id:
            messagebox.showwarning("⚠️ Ostrzeżenie", "Nie wybrano projektu")
            return
        
        # Zapytaj użytkownika
        result = messagebox.askyesno(
            "🔄 Resetuj śledzenie pliku",
            f"Czy na pewno chcesz zresetować śledzenie pliku projektu {self.selected_project_id}?\n\n"
            f"To spowoduje ponowną rejestrację pliku projektu w systemie.\n"
            f"Użyj tej opcji jeśli przywróciłeś usunięty plik lub chcesz śledzić nowy plik."
        )
        
        if result:
            try:
                rmm.reset_project_tracking(
                    self.rm_master_db_path,
                    self.selected_project_id,
                    self.master_db_path,
                    projects_path=self.projects_path
                )
                
                # Ponowna weryfikacja
                self.verify_project_file_integrity()
                
                self.status_bar.config(text=f"🔄 Reset śledzenia projektu {self.selected_project_id}", fg="#27ae60")
                
            except Exception as e:
                messagebox.showerror("❌ Błąd", f"Nie można zresetować śledzenia:\n{e}")
    
    def reset_all_file_tracking_ui(self):
        """Reset śledzenia pliku dla WSZYSTKICH projektów (po zmianie ścieżki)"""
        result = messagebox.askyesno(
            "🔄 Resetuj śledzenie WSZYSTKICH projektów",
            f"Czy na pewno chcesz zresetować śledzenie plików dla WSZYSTKICH projektów?\n\n"
            f"Użyj tej opcji po zmianie folderu projektów.\n"
            f"Folder projektów: {self.projects_path}\n\n"
            f"Wszystkie projekty zostaną ponownie zweryfikowane."
        )
        if not result:
            return
        try:
            # Zbierz ID projektów ze WSZYSTKICH per-projekt baz w rm_projects_dir
            import glob
            project_dbs = glob.glob(os.path.join(self.rm_projects_dir, 'rm_manager_project_*.sqlite'))
            project_ids_from_files = []
            for db_path in project_dbs:
                fname = os.path.basename(db_path)
                # rm_manager_project_6.sqlite → 6
                try:
                    pid = int(fname.replace('rm_manager_project_', '').replace('.sqlite', ''))
                    project_ids_from_files.append(pid)
                except ValueError:
                    pass

            con = rmm._open_rm_connection(self.rm_master_db_path, row_factory=False)
            con.execute("DELETE FROM project_file_tracking")
            con.commit()
            con.close()

            # Użyj również ID z listy projektów GUI
            all_pids = set(project_ids_from_files) | set(self.projects)
            for pid in sorted(all_pids):
                pname = self.project_names.get(pid, f"Projekt_{pid}")
                rmm.register_project_file(
                    self.rm_master_db_path, pid, pname,
                    self.master_db_path, projects_path=self.projects_path
                )

            self.status_bar.config(
                text=f"✅ Zresetowano śledzenie {len(all_pids)} projektów", fg="#27ae60"
            )
            messagebox.showinfo(
                "✅ Gotowe",
                f"Zresetowano śledzenie dla {len(all_pids)} projektów.\n"
                f"Folder: {self.projects_path}"
            )
            if self.selected_project_id:
                self.verify_project_file_integrity()
        except Exception as e:
            messagebox.showerror("❌ Błąd", f"Nie można zresetować śledzenia:\n{e}")

    def update_stage_definitions_ui(self):
        """Aktualizuj definicje etapów w bazie (po dodaniu nowych etapów w kodzie)"""
        result = messagebox.askyesno(
            "🔄 Aktualizuj definicje etapów",
            "Operacja:\n\n"
            "1️⃣ Zsynchronizuje definicje etapów z kodem\n\n"
            "2️⃣ Doda brakujące etapy do wszystkich projektów\n\n"
            "3️⃣ Doda brakujące zależności (dependencies)\n\n"
            "Stare etapy pozostaną bez zmian.\n"
            "Istniejące dane nie zostaną usunięte.\n\n"
            "Kontynuować?"
        )
        if not result:
            return
        
        try:
            # KROK 1: Aktualizuj definicje w master DB i per-project bazach
            added_master = rmm.update_stage_definitions(self.rm_master_db_path)
            
            import glob
            project_dbs = glob.glob(os.path.join(self.rm_projects_dir, 'rm_manager_project_*.sqlite'))
            total_added_defs = 0
            for db_path in sorted(project_dbs):
                added = rmm.update_project_stage_definitions(db_path)
                total_added_defs += added
            
            # KROK 2: Dodaj etapy do struktury projektów
            total_added_stages = 0
            total_projects = 0
            for db_path in sorted(project_dbs):
                info = rmm.ensure_all_stages_for_all_projects(db_path)
                total_added_stages += info['stages_added']
                total_projects += info['projects_updated']
            
            # KROK 3: Dodaj brakujące zależności (dependencies) dla wszystkich projektów
            total_added_deps = 0
            for db_path in sorted(project_dbs):
                # Pobierz listę projektów z tej bazy
                con = rmm._open_rm_connection(db_path, row_factory=False)
                project_ids = [r[0] for r in con.execute(
                    "SELECT DISTINCT project_id FROM project_stages"
                ).fetchall()]
                con.close()
                
                # Dodaj dependencies dla każdego projektu
                for pid in project_ids:
                    added_deps = rmm.ensure_default_dependencies_for_project(db_path, pid)
                    total_added_deps += added_deps
            
            # KROK 4: Napraw kolejność (sequence) dla WSZYSTKICH etapów
            total_seq_updated = 0
            for db_path in sorted(project_dbs):
                info = rmm.fix_stage_sequence_for_all_projects(db_path)
                total_seq_updated += info['stages_updated']
            
            self.status_bar.config(
                text=f"✅ Zaktualizowano: +{added_master} definicji, +{total_added_stages} etapów, +{total_added_deps} zależności, ~{total_seq_updated} sequence",
                fg="#27ae60"
            )
            messagebox.showinfo(
                "✅ Aktualizacja zakończona!",
                f"Zaktualizowano definicje etapów:\n"
                f"• Master: +{added_master} nowych definicji\n"
                f"• Projekty: +{total_added_defs} definicji w {len(project_dbs)} bazach\n\n"
                f"Dodano do struktury projektów:\n"
                f"• {total_added_stages} nowych etapów w {total_projects} projektach\n"
                f"• {total_added_deps} nowych zależności (dependencies)\n"
                f"• {total_seq_updated} etapów - naprawiono kolejność\n\n"
                f"✅ Wszystko gotowe! Nowe etapy są już dostępne."
            )
            
            if self.selected_project_id:
                self.load_project_stages()
                self.refresh_all()
                
        except Exception as e:
            messagebox.showerror("❌ Błąd", f"Nie można zaktualizować definicji:\n{e}")

    def fix_stage_sequence_ui(self):
        """Napraw kolejność etapów (sequence) dla wszystkich projektów"""
        result = messagebox.askyesno(
            "🔢 Napraw kolejność etapów",
            "Operacja:\n\n"
            "1️⃣ Zaktualizuje numerację sequence we WSZYSTKICH projektach\n\n"
            "2️⃣ Ustawi zgodnie z kanoniczną kolejnością:\n"
            "   PRZYJETY → PROJEKT → KOMPLETACJA → MONTAŻ → ELEKTROMONTAŻ → ...\n\n"
            "Operacja jest bezpieczna - nie rusza innych danych.\n\n"
            "Kontynuować?"
        )
        if not result:
            return
        
        try:
            # Napraw sequence w per-project bazach
            import glob
            project_dbs = glob.glob(os.path.join(self.rm_projects_dir, 'rm_manager_project_*.sqlite'))
            total_updated_stages = 0
            total_projects = 0
            for db_path in sorted(project_dbs):
                info = rmm.fix_stage_sequence_for_all_projects(db_path)
                total_updated_stages += info['stages_updated']
                total_projects += info['projects_updated']
            
            self.status_bar.config(
                text=f"✅ Naprawiono kolejność: {total_updated_stages} etapów w {total_projects} projektach",
                fg="#27ae60"
            )
            messagebox.showinfo(
                "✅ Naprawa zakończona!",
                f"Naprawiono kolejność etapów:\n"
                f"• {total_updated_stages} etapów zaktualizowanych\n"
                f"• {total_projects} projektów przetworzonych\n"
                f"• {len(project_dbs)} baz danych\n\n"
                f"✅ Kolejność etapów jest teraz zgodna z kanoniczną."
            )
            
            if self.selected_project_id:
                # Wymuś pełne przeładowanie projektu
                self.load_project_stages()
                self.refresh_timeline()
                self.refresh_dashboard()
                self.refresh_history()
                
        except Exception as e:
            messagebox.showerror("❌ Błąd", f"Nie można naprawić kolejności:\n{e}")

    def migrate_milestones_ui(self):
        """Migruj PRZYJĘTY i ZAKOŃCZONY na instant (ended_at = started_at)"""
        result = messagebox.askyesno(
            "⚡ Migruj milestones na instant",
            "Operacja:\n\n"
            "1️⃣ Znajdzie wszystkie PRZYJĘTY i ZAKOŃCZONY\n\n"
            "2️⃣ Ustawi ended_at = started_at (zdarzenia instant)\n\n"
            "3️⃣ Stare dane z czasem trwania będą konwertowane\n\n"
            "   PRZED: PRZYJĘTY: 01-03 14:30 → 01-03 15:00 (30 min)\n"
            "   PO:    PRZYJĘTY: 01-03 14:30 ✔ (instant)\n\n"
            "Operacja jest bezpieczna dla danych.\n\n"
            "Kontynuować?"
        )
        if not result:
            return
        
        try:
            # Migruj w per-project bazach
            import glob
            project_dbs = glob.glob(os.path.join(self.rm_projects_dir, 'rm_manager_project_*.sqlite'))
            total_periods = 0
            total_projects = 0
            for db_path in sorted(project_dbs):
                info = rmm.migrate_milestones_to_instant(db_path)
                total_periods += info['periods_updated']
                total_projects += info['projects_affected']
            
            self.status_bar.config(
                text=f"✅ Migrowano milestones: {total_periods} okresów w {total_projects} projektach",
                fg="#27ae60"
            )
            messagebox.showinfo(
                "✅ Migracja zakończona!",
                f"Migrowano milestones na instant:\n"
                f"• {total_periods} okresów zaktualizowanych\n"
                f"• {total_projects} projektów przetworzonych\n"
                f"• {len(project_dbs)} baz danych\n\n"
                f"✅ PRZYJĘTY i ZAKOŃCZONY są teraz zdarzeniami instant.\n\n"
                f"📚 Zobacz MILESTONES_QUICKSTART.md dla szczegółów."
            )
            
            if self.selected_project_id:
                self.refresh_all()
                
        except Exception as e:
            messagebox.showerror("❌ Błąd", f"Nie można migrować milestones:\n{e}")
    
    def migrate_plc_codes_ui(self):
        """Migruj bazę kodów PLC - dodaj nowe kolumny i tabelę uprawnień.
        
        Menu: Narzędzia → 🔧 Migruj bazę kodów PLC (dodaj kolumny)
        """
        result = messagebox.askyesno(
            "🔧 Migracja bazy kodów PLC",
            "Operacja:\n\n"
            "1️⃣ Doda nowe kolumny do tabeli plc_unlock_codes:\n"
            "   • sent_at (data wysłania)\n"
            "   • sent_by (kto wysłał)\n"
            "   • sent_via (EMAIL/SMS)\n"
            "   • expiry_date (data wygaśnięcia)\n\n"
            "2️⃣ Utworzy tabelę plc_authorized_senders:\n"
            "   • lista użytkowników uprawnionych do wysyłki\n\n"
            "WYMAGANE DO:\n"
            "  ✅ Automatycznej wysyłki kodów (przycisk UŻYJ)\n"
            "  ✅ Wyświetlania kolumny 'Ważny do'\n"
            "  ✅ Zarządzania uprawnieniami\n\n"
            "BEZPIECZEŃSTWO:\n"
            "  • Jeśli kolumny/tabele już istnieją, zostaną pominięte\n"
            "  • Istniejące dane NIE zostaną usunięte\n"
            "  • Operacja jest bezpieczna do powtórzenia\n\n"
            "Kontynuować?"
        )
        if not result:
            return
        
        try:
            self.status_bar.config(text="⏳ Migracja bazy kodów PLC...", fg="#f39c12")
            self.root.update()
            
            # Wykonaj migrację
            con = sqlite3.connect(self.rm_master_db_path, timeout=30.0)
            con.row_factory = sqlite3.Row
            
            stats = {
                'columns_added': 0,
                'tables_created': 0,
                'errors': []
            }
            
            try:
                # Sprawdź czy tabela plc_unlock_codes istnieje
                cursor = con.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='plc_unlock_codes'
                """)
                
                if not cursor.fetchone():
                    stats['errors'].append("Tabela plc_unlock_codes nie istnieje")
                    raise ValueError("Tabela plc_unlock_codes nie istnieje w bazie danych")
                
                # Sprawdź jakie kolumny już istnieją
                cursor = con.execute("PRAGMA table_info(plc_unlock_codes)")
                existing_columns = {row['name'] for row in cursor.fetchall()}
                
                # Dodaj nowe kolumny jeśli nie istnieją
                new_columns = [
                    ('sent_at', 'DATETIME'),
                    ('sent_by', 'TEXT'),
                    ('sent_via', 'TEXT'),
                    ('expiry_date', 'DATETIME')
                ]
                
                for col_name, col_type in new_columns:
                    if col_name not in existing_columns:
                        con.execute(f"ALTER TABLE plc_unlock_codes ADD COLUMN {col_name} {col_type}")
                        stats['columns_added'] += 1
                
                # Utwórz tabelę plc_authorized_senders jeśli nie istnieje
                cursor = con.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='plc_authorized_senders'
                """)
                
                if not cursor.fetchone():
                    con.execute("""
                        CREATE TABLE plc_authorized_senders (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            username TEXT NOT NULL UNIQUE,
                            added_by TEXT,
                            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            notes TEXT
                        )
                    """)
                    con.execute("CREATE INDEX IF NOT EXISTS idx_plc_senders_username ON plc_authorized_senders(username)")
                    stats['tables_created'] += 1
                
                con.commit()
                
                self.status_bar.config(
                    text=f"✅ Migracja zakończona: {stats['columns_added']} kolumn, {stats['tables_created']} tabel",
                    fg="#27ae60"
                )
                
                messagebox.showinfo(
                    "✅ Migracja zakończona!",
                    f"Migracja bazy kodów PLC:\n\n"
                    f"• Dodano kolumn: {stats['columns_added']}\n"
                    f"• Utworzono tabel: {stats['tables_created']}\n\n"
                    f"✅ Baza gotowa do wysyłki kodów przez email/SMS!\n\n"
                    f"Następne kroki:\n"
                    f"1️⃣ Dodaj użytkowników: Narzędzia → Zarządzaj uprawnieniami\n"
                    f"2️⃣ Skonfiguruj SMTP: Narzędzia → Konfiguracja powiadomień\n"
                    f"3️⃣ Skonfiguruj SMS: Narzędzia → Konfiguracja SMS\n\n"
                    f"📚 Zobacz PLC_CODES_README.md dla szczegółów."
                )
                
                # Odśwież dane jeśli projekt jest wybrany
                if self.selected_project_id:
                    self.load_plc_codes()
                    
            except Exception as e:
                stats['errors'].append(f"Błąd główny: {e}")
                con.rollback()
                raise
            
            finally:
                con.close()
                
        except Exception as e:
            self.status_bar.config(text="❌ Błąd migracji", fg="#e74c3c")
            messagebox.showerror("❌ Błąd", f"Nie można migrować bazy kodów PLC:\n{e}")

    def migrate_plc_recipients_ui(self):
        """Migruj bazę kodów PLC - dodaj kolumnę default_recipients.
        
        Menu: Narzędzia → 🔧 Migruj odbiorców kodów PLC
        """
        result = messagebox.askyesno(
            "🔧 Migracja odbiorców kodów PLC (PRZESTARZAŁE)",
            "⚠️ UWAGA: Ta funkcja jest PRZESTARZAŁA!\n\n"
            "Od tej wersji odbiorcy kodów PLC są GLOBALNI dla wszystkich projektów\n"
            "i zarządzane przez tabelę plc_global_recipients.\n\n"
            "Stara kolumna default_recipients jest zachowana dla kompatybilności,\n"
            "ale nie jest już aktywnie używana.\n\n"
            "OBECNE DZIAŁANIE:\n"
            "  ✅ Jedna lista odbiorców dla WSZYSTKICH projektów\n"
            "  ✅ Zapisywane w tabeli plc_global_recipients\n"
            "  ✅ Automatyczne tworzenie przy inicjalizacji bazy\n\n"
            "Kontynuować migrację starych kolumn?"
        )
        if not result:
            return
        
        try:
            self.status_bar.config(text="⏳ Migracja odbiorców kodów PLC...", fg="#f39c12")
            self.root.update()
            
            # Wykonaj migrację
            con = sqlite3.connect(self.rm_master_db_path, timeout=30.0)
            con.row_factory = sqlite3.Row
            
            try:
                # Sprawdź czy tabela plc_unlock_codes istnieje
                cursor = con.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='plc_unlock_codes'
                """)
                
                if not cursor.fetchone():
                    raise ValueError("Tabela plc_unlock_codes nie istnieje w bazie danych")
                
                # Sprawdź czy kolumna już istnieje
                cursor = con.execute("PRAGMA table_info(plc_unlock_codes)")
                existing_columns = {row['name'] for row in cursor.fetchall()}
                
                if 'default_recipients' in existing_columns:
                    messagebox.showinfo(
                        "ℹ️ Kolumna już istnieje",
                        "Kolumna 'default_recipients' już istnieje w tabeli plc_unlock_codes.\n\n"
                        "Migracja nie jest wymagana."
                    )
                    self.status_bar.config(text="✅ Kolumna już istnieje", fg="#27ae60")
                    return
                
                # Dodaj kolumnę
                con.execute("ALTER TABLE plc_unlock_codes ADD COLUMN default_recipients TEXT")
                con.commit()
                
                messagebox.showinfo(
                    "✅ Migracja zakończona",
                    "Kolumna 'default_recipients' została dodana pomyślnie!\n\n"
                    "Teraz lista odbiorców będzie zapisywana automatycznie\n"
                    "przy każdej wysyłce kodu PLC."
                )
                
                self.status_bar.config(text="✅ Migracja odbiorców zakończona", fg="#27ae60")
                
                # Odśwież dane jeśli projekt jest wybrany
                if self.selected_project_id:
                    self.load_plc_codes()
                    
            except Exception as e:
                con.rollback()
                raise
            
            finally:
                con.close()
                
        except Exception as e:
            self.status_bar.config(text="❌ Błąd migracji", fg="#e74c3c")
            messagebox.showerror("❌ Błąd", f"Nie można migrować odbiorców kodów PLC:\n{e}")

    def migrate_central_to_per_project_ui(self):
        """Migracja danych z centralnej rm_manager.sqlite do per-projekt baz.
        
        Menu: Narzędzia → 📦 Migruj centralną bazę → per-projekt
        """
        result = messagebox.askyesno(
            "📦 Migracja: centralna → per-projekt",
            "Ta operacja przeniesie dane projektów z centralnej bazy\n"
            "rm_manager.sqlite do osobnych plików per-projekt:\n\n"
            "  rm_manager_project_1.sqlite\n"
            "  rm_manager_project_2.sqlite\n"
            "  ...\n\n"
            "KORZYŚCI:\n"
            "  ✅ Każdy projekt w osobnym pliku\n"
            "  ✅ Locki per-projekt (użytkownicy nie blokują się)\n"
            "  ✅ Izolacja danych\n\n"
            "BEZPIECZEŃSTWO:\n"
            "  • Projekty już istniejące w per-projekt bazach NIE zostaną nadpisane\n"
            "  • Centralna baza NIE zostanie usunięta automatycznie\n"
            "  • Operacja jest bezpieczna do powtórzenia\n\n"
            "Kontynuować?"
        )
        if not result:
            return
        
        try:
            self.status_bar.config(text="⏳ Migracja centralnej bazy...", fg="#f39c12")
            self.root.update()
            
            migration_result = rmm.migrate_central_to_per_project(
                self.rm_projects_dir,
                self.rm_master_db_path
            )
            
            migrated = migration_result['projects_migrated']
            skipped = migration_result['projects_skipped']
            errors = migration_result['errors']
            
            # Buduj raport
            report_lines = [
                f"✅ Zmigrowano: {migrated} projektów",
                f"⏭️ Pominięto: {skipped} projektów (już istniały)",
            ]
            
            if migration_result['details']:
                report_lines.append("\nSzczegóły:")
                for pid, detail in migration_result['details'].items():
                    total = sum(detail.values())
                    report_lines.append(
                        f"  • Projekt {pid}: {total} rekordów "
                        f"({detail['stages']} etapów, {detail['periods']} okresów)"
                    )
            
            if errors:
                report_lines.append(f"\n❌ Błędy ({len(errors)}):")
                for err in errors:
                    report_lines.append(f"  • {err}")
            
            report = "\n".join(report_lines)
            
            if migrated > 0:
                self.status_bar.config(
                    text=f"✅ Migracja zakończona: {migrated} projektów",
                    fg=self.COLOR_GREEN
                )
                
                # Zapytaj czy wyczyścić centralne tabele
                if messagebox.askyesno(
                    "🗑️ Wyczyścić centralną bazę?",
                    f"Migracja zakończona pomyślnie!\n\n{report}\n\n"
                    "Czy chcesz usunąć tabele projektowe z centralnej bazy?\n\n"
                    "⚠️ To jest opcjonalne - centralna baza może zostać jako backup.\n"
                    "Tabele master (employees, permissions) NIE zostaną usunięte."
                ):
                    cleanup = rmm.cleanup_central_project_tables(
                        self.rm_master_db_path, dry_run=False
                    )
                    report += f"\n\n🗑️ Usunięto tabele z centralnej bazy: {cleanup['tables_removed']}"
                
                messagebox.showinfo("📦 Migracja zakończona", report)
            else:
                self.status_bar.config(
                    text=f"ℹ️ Brak danych do migracji (pominięto {skipped})",
                    fg="#95a5a6"
                )
                messagebox.showinfo("📦 Migracja", report)
            
            # Odśwież widoki
            if self.selected_project_id:
                self.refresh_all()
                
        except Exception as e:
            messagebox.showerror("❌ Błąd", f"Nie można wykonać migracji:\n{e}")
            self.status_bar.config(text=f"🔴 Błąd migracji", fg=self.COLOR_RED)

    def sync_all_projects_stages_ui(self):
        """🔄 Aktualizuj etapy we wszystkich projektach - doda brakujące milestones/etapy.
        Narzędzia → Aktualizuj etapy we wszystkich projektach
        """
        msg = (
            "Ta funkcja:\n"
            "• Doda brakujące etapy/milestones ze STAGE_DEFINITIONS\n"
            "• Naprawi brakujące wpisy stage_schedule (potrzebne do zapisu dat)\n\n"
            "Zostanie wykonana dla WSZYSTKICH projektów w RM_MANAGER.\n\n"
            "⚠️ WYMAGANE po dodaniu nowych milestones (Transport, FAT, etc.)\n\n"
            "Czy kontynuować?"
        )
        if not messagebox.askyesno("🔄 Aktualizuj etapy", msg, icon='question'):
            return

        try:
            # Przeskanuj wszystkie projekty
            total_added = 0
            projects_updated = 0

            for pid in self.projects:
                project_db = self.get_project_db_path(pid)
                if not os.path.exists(project_db):
                    continue

                try:
                    added = rmm.sync_project_stages_with_definitions(project_db, pid)
                    if added > 0:
                        total_added += added
                        projects_updated += 1
                except Exception as e:
                    print(f"⚠️  Błąd sync projektu {pid}: {e}")

            # Odśwież bieżący projekt
            if self.selected_project_id:
                self.load_project_stages()
                self.refresh_timeline()

            msg = (
                f"✅ Aktualizacja zakończona!\n\n"
                f"Zaktualizowano: {projects_updated} projektów\n"
                f"Dodano nowych etapów/milestones: {total_added}\n"
                f"Naprawiono wpisy stage_schedule dla wszystkich projektów"
            )
            messagebox.showinfo("✅ Zakończono", msg)
            self.status_bar.config(text=f"🔄 Naprawiono stage_schedule", fg="#27ae60")

        except Exception as e:
            messagebox.showerror("❌ Błąd", f"Nie udało się zaktualizować etapów:\n{e}")

    def ensure_dependencies_ui(self):
        """🔗 Uzupełnij domyślne zależności workflow dla wszystkich projektów.
        Narzędzia → Uzupełnij zależności
        """
        msg = (
            "Ta funkcja doda brakujące zależności workflow\n"
            "(np. POPRAWKI → ZAKOŃCZONY) do WSZYSTKICH projektów.\n\n"
            "Bezpieczne: nie nadpisuje istniejących zależności\n"
            "(INSERT OR IGNORE).\n\n"
            "Czy kontynuować?"
        )
        if not messagebox.askyesno("🔗 Uzupełnij zależności", msg, icon='question'):
            return

        try:
            total_added = 0
            projects_updated = 0

            for pid in self.projects:
                project_db = self.get_project_db_path(pid)
                if not os.path.exists(project_db):
                    continue

                try:
                    added = rmm.ensure_default_dependencies_for_project(project_db, pid)
                    if added > 0:
                        total_added += added
                        projects_updated += 1
                except Exception as e:
                    print(f"⚠️  Błąd zależności projektu {pid}: {e}")

            msg = (
                f"✅ Uzupełnianie zakończone!\n\n"
                f"Zaktualizowano: {projects_updated} projektów\n"
                f"Dodano zależności: {total_added}"
            )
            messagebox.showinfo("✅ Zakończono", msg)
            self.status_bar.config(text=f"🔗 Dodano {total_added} zależności", fg="#27ae60")

        except Exception as e:
            messagebox.showerror("❌ Błąd", f"Nie udało się uzupełnić zależności:\n{e}")

    def migrate_notes_system_ui(self):
        """Migruj system notatek do wszystkich projektów.
        
        Menu: Narzędzia → 📝 Migruj system notatek do projektów
        """
        try:
            # Podgląd
            result = rmm.migrate_notes_system_to_projects(self.rm_projects_dir)
            
            # Podsumowanie
            summary = f"Migracja zakończona!\n\n"
            summary += f"✅ Zaktualizowano: {result['projects_updated']} projektów\n"
            summary += f"⏭️ Pominięto: {result['projects_skipped']} projektów\n"
            
            if result['errors']:
                summary += f"\n❌ Błędy ({len(result['errors'])}):\n"
                for err in result['errors'][:10]:  # Max 10 pierwszych błędów
                    summary += f"  • {err}\n"
                if len(result['errors']) > 10:
                    summary += f"  ... i {len(result['errors']) - 10} więcej\n"
            
            # Szczegóły
            if result['details']:
                summary += f"\nSzczegóły:\n"
                for pid, status in list(result['details'].items())[:15]:  # Max 15
                    summary += f"  Projekt {pid}: {status}\n"
                if len(result['details']) > 15:
                    summary += f"  ... i {len(result['details']) - 15} więcej\n"
            
            if result['errors']:
                messagebox.showwarning(
                    "⚠️ Migracja z błędami",
                    summary
                )
            else:
                messagebox.showinfo(
                    "✅ Migracja zakończona",
                    summary
                )
            
            # Odśwież widok jeśli projekt jest wybrany
            if self.selected_project_id:
                self.refresh_all()
            
        except Exception as e:
            messagebox.showerror("❌ Błąd migracji", f"Nie można zmigrować systemu notatek:\n{e}")

    def diagnose_projects(self):
        """Diagnostyka projektów - sprawdź stan plików i baz RM_MANAGER"""
        try:
            # Zbierz informacje diagnostyczne
            report_lines = []
            report_lines.append("🔍 DIAGNOSTYKA PROJEKTÓW RM_MANAGER")
            report_lines.append("=" * 50)
            
            # 1. Sprawdź katalog RM_MANAGER
            report_lines.append(f"\n📁 Katalog RM_MANAGER: {self.rm_projects_dir}")
            report_lines.append(f"   Istnieje: {'✅' if os.path.exists(self.rm_projects_dir) else '❌'}")
            
            if os.path.exists(self.rm_projects_dir):
                # Lista plików w katalogu
                project_files = glob.glob(os.path.join(self.rm_projects_dir, "rm_manager_project_*.sqlite"))
                report_lines.append(f"   Pliki projektów: {len(project_files)}")
                
                for file_path in sorted(project_files):
                    basename = os.path.basename(file_path)
                    try:
                        project_id = int(basename.replace('rm_manager_project_', '').replace('.sqlite', ''))
                        file_size = os.path.getsize(file_path)
                        report_lines.append(f"     • {basename} ({file_size} B) → projekt ID {project_id}")
                        
                        # Sprawdź czy można otworzyć bazę
                        try:
                            con = rmm._open_rm_connection(file_path, row_factory=False)
                            cursor = con.execute("SELECT COUNT(*) FROM project_stages WHERE project_id = ?", (project_id,))
                            stage_count = cursor.fetchone()[0]
                            con.close()
                            report_lines.append(f"       ✅ SQLite OK, etapów: {stage_count}")
                        except sqlite3.Error as db_err:
                            report_lines.append(f"       ❌ Błąd SQLite: {db_err}")
                        
                    except ValueError:
                        report_lines.append(f"     • {basename} (nieprawidłowy format nazwy)")
            
            # 2. Sprawdź projekty z master.sqlite
            report_lines.append(f"\n📄 Master DB: {self.master_db_path}")
            report_lines.append(f"   Istnieje: {'✅' if os.path.exists(self.master_db_path) else '❌'}")
            
            if os.path.exists(self.master_db_path):
                try:
                    con = rmm._open_rm_connection(self.master_db_path)
                    cursor = con.execute("""
                        SELECT project_id, name, active 
                        FROM projects 
                        WHERE COALESCE(active, 1) = 1
                        ORDER BY project_id
                    """)
                    master_projects = cursor.fetchall()
                    con.close()
                    
                    report_lines.append(f"   Aktywnych projektów: {len(master_projects)}")
                    
                    for row in master_projects:
                        pid = row['project_id']
                        pname = row['name']
                        rm_file = os.path.join(self.rm_projects_dir, f"rm_manager_project_{pid}.sqlite")
                        has_rm_file = os.path.exists(rm_file)
                        
                        report_lines.append(f"     • ID {pid}: {pname}")
                        report_lines.append(f"       RM_MANAGER baza: {'✅ istnieje' if has_rm_file else '❌ brak'}")
                        
                        if has_rm_file:
                            try:
                                con2 = rmm._open_rm_connection(rm_file, row_factory=False)
                                cursor2 = con2.execute("""
                                    SELECT COUNT(*) FROM project_stages WHERE project_id = ?
                                """, (pid,))
                                stages = cursor2.fetchone()[0]
                                con2.close()
                                report_lines.append(f"       Etapów w RM: {stages}")
                            except Exception as e:
                                report_lines.append(f"       ❌ Błąd odczytu: {e}")
                        
                except sqlite3.Error as db_err:
                    report_lines.append(f"   ❌ Błąd master.sqlite: {db_err}")
            
            # 3. Sprawdź aktualny projekt
            if self.selected_project_id:
                report_lines.append(f"\n🎯 Aktualny projekt: {self.selected_project_id}")
                current_rm_file = self.get_project_db_path(self.selected_project_id)
                report_lines.append(f"   Ścieżka RM: {current_rm_file}")
                report_lines.append(f"   Plik istnieje: {'✅' if os.path.exists(current_rm_file) else '❌'}")
                report_lines.append(f"   Read-only mode: {'✅' if self.read_only_mode else '❌'}")
                
                if hasattr(self, 'file_verification_message'):
                    report_lines.append(f"   File verification: {self.file_verification_message}")
            
            # 4. Sprawdź memory/cache
            report_lines.append(f"\n💾 Pamięć aplikacji:")
            report_lines.append(f"   Załadowanych projektów: {len(getattr(self, 'projects', []))}")
            if hasattr(self, 'projects') and self.projects:
                report_lines.append(f"   Lista ID: {self.projects[:10]}{'...' if len(self.projects) > 10 else ''}")
            
            # Wyświetl raport
            report_text = "\n".join(report_lines)
            
            # Dialog z raportem
            dialog = tk.Toplevel(self.root)
            dialog.title("🔍 Diagnostyka projektów")
            dialog.geometry("800x600")
            dialog.transient(self.root)
            dialog.grab_set()
            
            # Text widget z scrollbarem
            frame = tk.Frame(dialog)
            frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            text_widget = scrolledtext.ScrolledText(frame, wrap=tk.WORD, font=('Consolas', 10))
            text_widget.pack(fill=tk.BOTH, expand=True)
            text_widget.insert(tk.END, report_text)
            text_widget.config(state=tk.DISABLED)
            
            # Przyciski
            button_frame = tk.Frame(dialog)
            button_frame.pack(fill=tk.X, padx=10, pady=5)
            
            tk.Button(button_frame, text="🔄 Odśwież projekty", 
                     command=lambda: [dialog.destroy(), self.force_reload_projects()]).pack(side=tk.LEFT)
            tk.Button(button_frame, text="📋 Kopiuj do schowka", 
                     command=lambda: dialog.clipboard_append(report_text)).pack(side=tk.LEFT, padx=(10, 0))
            tk.Button(button_frame, text="Zamknij", 
                     command=dialog.destroy).pack(side=tk.RIGHT)
            
            # Wyśrodkuj dialog
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
            y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")
            
        except Exception as e:
            messagebox.showerror("❌ Błąd diagnostyki", f"Nie można wykonać diagnostyki:\n{e}")

    def diagnose_milestones(self):
        """Diagnostyka milestone'ów - sprawdź stan zapisu i walidacji"""
        if not self.selected_project_id:
            messagebox.showwarning("Uwaga", "Wybierz projekt do diagnostyki milestone'ów.")
            return
            
        try:
            report_lines = []
            report_lines.append("🎯 DIAGNOSTYKA MILESTONE'ÓW")
            report_lines.append("=" * 50)
            
            # 1. Podstawowe info
            report_lines.append(f"\n📋 Projekt: {self.selected_project_id}")
            report_lines.append(f"   Lock: {'✅ TAK' if self.have_lock else '❌ NIE'}")
            report_lines.append(f"   Read-only: {'❌ TAK' if self.read_only_mode else '✅ NIE'}")
            report_lines.append(f"   User: {self.current_user} ({self.current_user_role})")
            
            # 2. Sprawdź uprawnienia
            can_start = self._has_permission('can_start_stage')
            can_end = self._has_permission('can_end_stage')
            report_lines.append(f"   Uprawnienia set milestone: {'✅' if can_start else '❌'}")
            report_lines.append(f"   Uprawnienia unset milestone: {'✅' if can_end else '❌'}")
            
            # 3. Sprawdź bazy danych
            project_db = self.get_project_db_path(self.selected_project_id)
            report_lines.append(f"\n📁 Baza RM_MANAGER: {project_db}")
            report_lines.append(f"   Istnieje: {'✅' if os.path.exists(project_db) else '❌'}")
            
            if not os.path.exists(project_db):
                report_lines.append("   ❌ Baza nie istnieje - nie można kontynuować diagnostyki")
            else:
                file_size = os.path.getsize(project_db)
                report_lines.append(f"   Rozmiar: {file_size} B")
                
                # 4. Sprawdź milestones w bazie
                con = rmm._open_rm_connection(project_db)
                
                try:
                    # Lista wszystkich milestone'ów (stage_definitions)
                    cursor = con.execute("""
                        SELECT code, display_name, is_milestone 
                        FROM stage_definitions 
                        WHERE is_milestone = 1 
                        ORDER BY code
                    """)
                    milestones_def = cursor.fetchall()
                    
                    report_lines.append(f"\n🏁 Milestone'y w definicjach: {len(milestones_def)}")
                    
                    for row in milestones_def:
                        code = row['code']
                        name = row['display_name']
                        report_lines.append(f"     • {code} ({name})")
                        
                        # Sprawdź czy milestone istnieje w project_stages
                        cursor2 = con.execute("""
                            SELECT id FROM project_stages 
                            WHERE project_id = ? AND stage_code = ?
                        """, (self.selected_project_id, code))
                        stage_exists = cursor2.fetchone() is not None
                        
                        if stage_exists:
                            # Sprawdź czy milestone jest ustawiony (ma rekord w stage_actual_periods)
                            cursor3 = con.execute("""
                                SELECT sap.started_at, sap.ended_at, sap.started_by, sap.ended_by
                                FROM stage_actual_periods sap
                                JOIN project_stages ps ON sap.project_stage_id = ps.id
                                WHERE ps.project_id = ? AND ps.stage_code = ?
                            """, (self.selected_project_id, code))
                            
                            period = cursor3.fetchone()
                            if period:
                                started = period['started_at'] or 'NULL'
                                ended = period['ended_at'] or 'NULL'
                                started_by = period['started_by'] or 'NULL'
                                ended_by = period['ended_by'] or 'NULL'
                                report_lines.append(f"       ✅ USTAWIONY: {started} - {ended}")
                                report_lines.append(f"       👤 Przez: {started_by} / {ended_by}")
                                
                                # Sprawdź czy start == end (poprawność milestone)
                                if started == ended and started != 'NULL':
                                    report_lines.append(f"       ✅ Poprawny milestone (start == end)")
                                elif started != 'NULL':
                                    report_lines.append(f"       ⚠️  Niepoprawny milestone (start != end)")
                            else:
                                report_lines.append(f"       ❌ NIE USTAWIONY")
                        else:
                            report_lines.append(f"       ❌ Brak w project_stages")
                    
                    # 5. Sprawdź template dates dla milestone'ów
                    report_lines.append(f"\n📅 Template dates (stage_schedule):")
                    cursor = con.execute("""
                        SELECT ps.stage_code, ss.template_start, ss.template_end
                        FROM project_stages ps
                        JOIN stage_schedule ss ON ps.id = ss.project_stage_id
                        JOIN stage_definitions sd ON ps.stage_code = sd.code
                        WHERE ps.project_id = ? AND sd.is_milestone = 1
                        ORDER BY ps.stage_code
                    """, (self.selected_project_id,))
                    
                    templates = cursor.fetchall()
                    if not templates:
                        report_lines.append(f"     ❌ Brak rekordów template dla milestone'ów")
                        report_lines.append(f"     To może powodować błąd 'rows_affected: 0' przy zapisie")
                    
                    for row in templates:
                        code = row['stage_code']
                        t_start = row['template_start'] or 'NULL'
                        t_end = row['template_end'] or 'NULL'
                        
                        report_lines.append(f"     • {code}:")
                        report_lines.append(f"       Template: {t_start} - {t_end}")
                        
                        # Walidacja milestone (start == end)
                        if t_start == t_end and t_start != 'NULL':
                            report_lines.append(f"       ✅ Template poprawny (start == end)")
                        elif t_start != 'NULL' and t_end != 'NULL':
                            report_lines.append(f"       ⚠️  Template niepoprawny (start != end)")
                        else:
                            report_lines.append(f"       ❌ Template pusty - to powoduje rows_affected=0!")
                    
                    # 6. Sprawdź project status w master.sqlite
                    report_lines.append(f"\n📊 Status projektu w master.sqlite:")
                    if os.path.exists(self.master_db_path):
                        master_con = rmm._open_rm_connection(self.master_db_path)
                        
                        try:
                            cursor_master = master_con.execute("""
                                SELECT status FROM projects WHERE project_id = ?
                            """, (self.selected_project_id,))
                            status_row = cursor_master.fetchone()
                            
                            if status_row:
                                status = status_row['status'] or 'NULL'
                                report_lines.append(f"   Status: {status}")
                                
                                # Weryfikacja logiki
                                przyjety = rmm.is_milestone_set(project_db, self.selected_project_id, 'PRZYJETY')
                                zakonczony = rmm.is_milestone_set(project_db, self.selected_project_id, 'ZAKONCZONY')
                                
                                report_lines.append(f"   PRZYJETY ustawiony: {'✅' if przyjety else '❌'}")
                                report_lines.append(f"   ZAKONCZONY ustawiony: {'✅' if zakonczony else '❌'}")
                                
                                # Sprawdź zgodność status <-> milestone
                                consistent = True
                                if przyjety and status == 'NEW':
                                    report_lines.append(f"   ⚠️  NIEZGODNOŚĆ: PRZYJĘTY ustawiony ale status=NEW")
                                    consistent = False
                                if zakonczony and status != 'DONE':
                                    report_lines.append(f"   ⚠️  NIEZGODNOŚĆ: ZAKOŃCZONY ustawiony ale status≠DONE")
                                    consistent = False
                                if status == 'DONE' and not zakonczony:
                                    report_lines.append(f"   ⚠️  NIEZGODNOŚĆ: status=DONE ale ZAKOŃCZONY nie ustawiony")
                                    consistent = False
                                
                                if consistent:
                                    report_lines.append(f"   ✅ Status i milestone'y zgodne")
                            else:
                                report_lines.append(f"   ❌ Projekt nie znaleziony w master.sqlite")
                            
                            master_con.close()
                        except sqlite3.Error as e:
                            report_lines.append(f"   ❌ Błąd master.sqlite: {e}")
                            master_con.close()
                    else:
                        report_lines.append(f"   ❌ master.sqlite nie istnieje")
                    
                    con.close()
                    
                except sqlite3.Error as db_err:
                    report_lines.append(f"\n❌ Błąd SQLite: {db_err}")
                    con.close()
            
            # 7. Sprawdź problemy z komponentami transport
            report_lines.append(f"\n🚛 Diagnostyka Transport:")
            try:
                transport_count = 0
                project_db = self.get_project_db_path(self.selected_project_id)
                con = rmm._open_rm_connection(project_db, row_factory=False)
                
                # Sprawdź ile jest etapów TRANSPORT
                cursor = con.execute("""
                    SELECT ps.stage_code FROM project_stages ps
                    JOIN stage_definitions sd ON ps.stage_code = sd.code
                    WHERE ps.project_id = ? AND ps.stage_code = 'TRANSPORT'
                """, (self.selected_project_id,))
                transport_stages = cursor.fetchall()
                transport_count = len(transport_stages)
                
                report_lines.append(f"   Etapów TRANSPORT: {transport_count}")
                
                # Sprawdź zapisane transport_id
                for t_stage in transport_stages:
                    try:
                        transport_id = rmm.get_stage_transport_id(project_db, self.selected_project_id, 'TRANSPORT')
                        report_lines.append(f"   Zapisany transport_id: {transport_id}")
                        
                        # Sprawdź czy firma istnieje
                        if transport_id:
                            transport_companies = rmm.get_transports(self.rm_master_db_path, active_only=True)
                            company_names = {t['id']: t['name'] for t in transport_companies}
                            if transport_id in company_names:
                                report_lines.append(f"   Firma: {company_names[transport_id]} ✅")
                            else:
                                report_lines.append(f"   Firma: ID {transport_id} ❌ (nie istnieje)")
                        
                    except Exception as ex:
                        report_lines.append(f"   ❌ Błąd odczytu transport: {ex}")
                
                # Sprawdź dostępne firmy transportowe
                try:
                    all_transports = rmm.get_transports(self.rm_master_db_path, active_only=True)
                    report_lines.append(f"   Dostępnych firm: {len(all_transports)}")
                    for t in all_transports[:3]:  # Pierwsze 3
                        report_lines.append(f"     • {t['name']} (ID: {t['id']})")
                    if len(all_transports) > 3:
                        report_lines.append(f"     ... i {len(all_transports) - 3} więcej")
                        
                except Exception as ex:
                    report_lines.append(f"   ❌ Błąd ładowania firm: {ex}")
                
                con.close()
                
            except Exception as ex:
                report_lines.append(f"   ❌ Błąd diagnostyki transport: {ex}")
            
            # 8. Ostatnia akcja z logów
            report_lines.append(f"\n🔄 Ostatnie działania:")
            # TODO: Można dodać czytanie project_events jeśli istnieje
            
            # Wyświetl raport
            report_text = "\n".join(report_lines)
            
            # Dialog z raportem
            dialog = tk.Toplevel(self.root)
            dialog.title("🎯 Diagnostyka milestone'ów")
            dialog.geometry("900x700")
            dialog.transient(self.root)
            dialog.grab_set()
            
            # Text widget z scrollbarem
            frame = tk.Frame(dialog)
            frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            text_widget = scrolledtext.ScrolledText(frame, wrap=tk.WORD, font=('Consolas', 9))
            text_widget.pack(fill=tk.BOTH, expand=True)
            text_widget.insert(tk.END, report_text)
            text_widget.config(state=tk.DISABLED)
            
            # Przyciski
            button_frame = tk.Frame(dialog)
            button_frame.pack(fill=tk.X, padx=10, pady=5)
            
            tk.Button(button_frame, text="🔄 Test zapisu PRZYJĘTY", 
                     command=lambda: self.test_milestone_save('PRZYJETY')).pack(side=tk.LEFT)
            tk.Button(button_frame, text="🔄 Test zapisu ZAKOŃCZONY", 
                     command=lambda: self.test_milestone_save('ZAKONCZONY')).pack(side=tk.LEFT, padx=(5, 0))
            tk.Button(button_frame, text="� Test transport", 
                     command=self.test_transport_components).pack(side=tk.LEFT, padx=(5, 0))
            tk.Button(button_frame, text="�📋 Kopiuj do schowka", 
                     command=lambda: dialog.clipboard_append(report_text)).pack(side=tk.LEFT, padx=(10, 0))
            tk.Button(button_frame, text="Zamknij", 
                     command=dialog.destroy).pack(side=tk.RIGHT)
            
            # Wyśrodkuj dialog
            dialog.update_idletasks()
            x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
            y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")
            
        except Exception as e:
            messagebox.showerror("❌ Błąd diagnostyki milestone'ów", f"Nie można wykonać diagnostyki:\n{e}")

    def test_milestone_save(self, stage_code: str):
        """Test zapisu milestone z pełnym logowaniem"""
        if not self.selected_project_id:
            return
            
        try:
            print(f"\n🧪 TEST ZAPISU MILESTONE {stage_code} - projekt {self.selected_project_id}")
            print(f"   Lock: {self.have_lock}")
            print(f"   Read-only: {self.read_only_mode}")
            print(f"   User: {self.current_user}")
            print(f"   Uprawnienia start: {self._has_permission('can_start_stage')}")
            
            # Sprawdź czy już ustawiony
            project_db = self.get_project_db_path(self.selected_project_id)
            is_set = rmm.is_milestone_set(project_db, self.selected_project_id, stage_code)
            print(f"   Już ustawiony: {is_set}")
            
            if is_set:
                messagebox.showinfo("Test", f"Milestone {stage_code} już ustawiony - nie można testować zapisu.")
                return
            
            # Walidacje GUI
            if not self.have_lock:
                print("   ❌ Brak locka")
                messagebox.showerror("Test", "Brak locka - nie można testować.")
                return
                
            if self.read_only_mode:
                print("   ❌ Read-only mode")
                messagebox.showerror("Test", "Read-only mode - nie można testować.")
                return
            
            if not self._has_permission('can_start_stage'):
                print("   ❌ Brak uprawnień")
                messagebox.showerror("Test", "Brak uprawnień - nie można testować.")
                return
            
            # Wykonaj zapis
            print(f"   🚀 Wykonuję rmm.set_milestone...")
            
            try:
                period_id = rmm.set_milestone(
                    project_db,
                    self.selected_project_id,
                    stage_code,
                    user=self.current_user,
                    notes=f"TEST SAVE @ {datetime.now()}",
                    master_db_path=self.master_db_path
                )
                
                print(f"   ✅ Sukces! period_id = {period_id}")
                
                # Sprawdź czy rzeczywiście zapisany
                is_now_set = rmm.is_milestone_set(project_db, self.selected_project_id, stage_code)
                print(f"   Weryfikacja zapisu: {is_now_set}")
                
                # Pokaż szczegóły
                milestone_data = rmm.get_milestone(project_db, self.selected_project_id, stage_code)
                print(f"   Dane milestone: {milestone_data}")
                
                messagebox.showinfo("✅ Test sukces", 
                    f"Milestone {stage_code} zapisany pomyślnie!\n"
                    f"Period ID: {period_id}\n"
                    f"Data: {milestone_data.get('started_at', 'N/A')}\n\n"
                    f"Sprawdź konsolę dla szczegółów."
                )
                
                # Odśwież widoki
                self.refresh_all()
                
            except Exception as save_error:
                print(f"   ❌ Błąd zapisu: {save_error}")
                import traceback
                traceback.print_exc()
                messagebox.showerror("❌ Test nieudany", 
                    f"Błąd zapisu milestone {stage_code}:\n{save_error}\n\n"
                    f"Sprawdź konsolę dla szczegółów."
                )
                
        except Exception as e:
            print(f"   🔥 Błąd testu: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("❌ Błąd testu", f"Nie można wykonać testu:\n{e}")

    def cleanup_central_db_ui(self):
        """Wyczyść centralną rm_manager.sqlite z tabel projektowych.
        
        Menu: Narzędzia → 🗑️ Wyczyść centralną bazę z danych projektów
        """
        try:
            # Dry run - pokaż co zostanie usunięte
            preview = rmm.cleanup_central_project_tables(
                self.rm_master_db_path, dry_run=True
            )
            
            if not preview['tables_found']:
                messagebox.showinfo(
                    "🗑️ Czyszczenie centralnej bazy",
                    "Centralna baza jest już czysta.\n\n"
                    "Brak tabel projektowych do usunięcia."
                )
                return
            
            # Pokaż podgląd
            lines = ["Tabele projektowe znalezione w centralnej bazie:\n"]
            total_records = 0
            for table in preview['tables_found']:
                count = preview['table_stats'].get(table, '?')
                lines.append(f"  • {table}: {count} rekordów")
                if isinstance(count, int):
                    total_records += count
            
            lines.append(f"\nŁącznie: {total_records} rekordów w {len(preview['tables_found'])} tabelach")
            lines.append("\nTe tabele to relikt starej architektury (centralna baza).")
            lines.append("Dane projektów powinny być w per-projekt bazach.")
            lines.append("\n⚠️ Tabele master (employees, permissions, tracking)")
            lines.append("NIE zostaną usunięte.")
            lines.append("\nUsunąć te tabele?")
            
            if not messagebox.askyesno(
                "🗑️ Wyczyść centralną bazę",
                "\n".join(lines),
                icon='warning'
            ):
                return
            
            # Wykonaj czyszczenie
            result = rmm.cleanup_central_project_tables(
                self.rm_master_db_path, dry_run=False
            )
            
            report = f"✅ Usunięto {len(result['tables_removed'])} tabel:\n"
            for table in result['tables_removed']:
                count = preview['table_stats'].get(table, '?')
                report += f"  • {table} ({count} rekordów)\n"
            
            messagebox.showinfo("🗑️ Czyszczenie zakończone", report)
            self.status_bar.config(
                text=f"✅ Wyczyszczono {len(result['tables_removed'])} tabel z centralnej bazy",
                fg=self.COLOR_GREEN
            )
            
        except Exception as e:
            messagebox.showerror("❌ Błąd", f"Nie można wyczyścić centralnej bazy:\n{e}")

    def _get_ui_button_states(self):
        """Określ reguły enable/disable dla przycisków w oparciu o project status
        
        Returns:
            dict: {
                'przyjety_enabled': bool,
                'stages_start_enabled': bool,
                'zakonczony_enabled': bool,
                'pause_enabled': bool,
                'resume_enabled': bool,
                'status_text': str  # Tekst do wyświetlenia
            }
        """
        if not self.selected_project_id:
            return {
                'przyjety_enabled': False,
                'stages_start_enabled': False,
                'zakonczony_enabled': False,
                'pause_enabled': False,
                'resume_enabled': False,
                'status_text': 'Brak projektu'
            }
        
        # 🔒 WYMÓG LOCKA - wszystkie przyciski wyłączone gdy brak locka lub tryb read-only
        if not self.have_lock or self.read_only_mode:
            try:
                status = rmm.get_project_status(self.master_db_path, self.selected_project_id)
            except Exception:
                status = ProjectStatus.NEW
            
            status_labels = {
                ProjectStatus.NEW: '🆕 Nowy projekt (nieprzyję ty)',
                ProjectStatus.ACCEPTED: '✅ Przyjęty - gotowy do pracy',
                ProjectStatus.IN_PROGRESS: '🔄 W trakcie realizacji',
                ProjectStatus.PAUSED: '⏸️  Wstrzymany',
                ProjectStatus.DONE: '🏁 Zakończony'
            }
            
            suffix = ' 🔒 READ-ONLY' if self.read_only_mode else ' 🔒 BRAK LOCKA'
            
            return {
                'przyjety_enabled': False,
                'stages_start_enabled': False,
                'zakonczony_enabled': False,
                'pause_enabled': False,
                'resume_enabled': False,
                'status_text': status_labels.get(status, 'Projekt') + suffix
            }
        
        try:
            status = rmm.get_project_status(self.master_db_path, self.selected_project_id)
            
            # 🔧 Inicjalizacja statusu dla projektów bez statusu (stary schemat lub nowe projekty)
            if status is None:
                print(f"🔧 Projekt {self.selected_project_id} nie ma statusu - inicjalizuję na NEW")
                try:
                    rmm.set_project_status(self.master_db_path, self.selected_project_id, ProjectStatus.NEW)
                    status = ProjectStatus.NEW
                except Exception as e:
                    print(f"⚠️ Nie udało się ustawić statusu: {e}")
                    status = ProjectStatus.NEW  # Fallback
            
            # 🔧 Korekta niespójności: status ACCEPTED/IN_PROGRESS ale milestone PRZYJĘTY
            #    nie istnieje w RM_MANAGER (np. po usunięciu i odtworzeniu bazy per-projekt)
            if status in (ProjectStatus.ACCEPTED, ProjectStatus.IN_PROGRESS):
                try:
                    _pdb = self.get_project_db_path(self.selected_project_id)
                    if not rmm.is_milestone_set(_pdb, self.selected_project_id, 'PRZYJETY'):
                        print(f"🔧 Niespójność: status={status} ale PRZYJĘTY nie ustawiony → resetuję na NEW")
                        rmm.set_project_status(self.master_db_path, self.selected_project_id, ProjectStatus.NEW)
                        status = ProjectStatus.NEW
                except Exception as e:
                    print(f"⚠️ Błąd korekty statusu: {e}")
                    
        except Exception as e:
            print(f"⚠️ _get_ui_button_states: get_project_status rzucił wyjątek: {e}")
            status = ProjectStatus.NEW  # Default fallback
        
        print(f"🎛️ _get_ui_button_states: project={self.selected_project_id}, status='{status}', have_lock={self.have_lock}, read_only={self.read_only_mode}")
        
        # Status mapping do UI
        rules = {
            ProjectStatus.NEW: {
                'przyjety_enabled': True,
                'stages_start_enabled': False,
                'zakonczony_enabled': False,
                'pause_enabled': False,
                'resume_enabled': False,
                'status_text': '🆕 Nowy projekt (nieprzyję ty)'
            },
            ProjectStatus.ACCEPTED: {
                'przyjety_enabled': False,  # Już przyjęty
                'stages_start_enabled': True,
                'zakonczony_enabled': False,  # ❌ Nie można zakończyć bez realizacji - musi być IN_PROGRESS
                'pause_enabled': False,
                'resume_enabled': False,
                'status_text': '✅ Przyjęty - gotowy do pracy'
            },
            ProjectStatus.IN_PROGRESS: {
                'przyjety_enabled': False,  # Już przyjęty
                'stages_start_enabled': True,  # + sprawdzane per etap czy nieaktywny
                'zakonczony_enabled': True,  # + dynamicznie sprawdzane czy są aktywne etapy
                'pause_enabled': True,
                'resume_enabled': False,
                'status_text': '🔄 W trakcie realizacji'
            },
            ProjectStatus.PAUSED: {
                'przyjety_enabled': False,
                'stages_start_enabled': False,  # Blokada podczas pauzy
                'zakonczony_enabled': False,
                'pause_enabled': False,
                'resume_enabled': True,
                'status_text': '⏸️  Wstrzymany'
            },
            ProjectStatus.DONE: {
                'przyjety_enabled': False,
                'stages_start_enabled': False,
                'zakonczony_enabled': True,  # ✅ Można odznaczyć żeby wznowić projekt
                'pause_enabled': False,
                'resume_enabled': False,
                'status_text': '🏁 Zakończony'
            }
        }
        
        result = rules.get(status, rules[ProjectStatus.NEW])
        print(f"🎛️ UI rules: {result}")
        return result

    def load_project_stages(self):
        """Załaduj etapy projektu i wygeneruj buttony"""
        if not self.selected_project_id:
            return

        # Zapamiętaj pozycję scrolla przed przebudową
        _scroll_pos = self.left_canvas.yview()

        # Reset flag renderowania komponentów (zapobiega duplikacji transport)
        # UWAGA: Nie resetuj tutaj - transport może być w kilku SUB_MILESTONES w tej samej funkcji
        # self._transport_rendered_for_project = None

        # Wyczyść stare buttony
        for widget in self.stages_frame.winfo_children():
            widget.destroy()

        try:
            # Pobierz reguły enable/disable w oparciu o project status
            ui_rules = self._get_ui_button_states()
            
            con = rmm._open_rm_connection(self.get_project_db_path(self.selected_project_id))
            cursor = con.execute("""
                SELECT ps.stage_code, sd.display_name, sd.color, sd.is_milestone
                FROM project_stages ps
                JOIN stage_definitions sd ON ps.stage_code = sd.code
                WHERE ps.project_id = ?
                ORDER BY ps.sequence
            """, (self.selected_project_id,))
            stages = cursor.fetchall()
            con.close()

            active_stages = rmm.get_active_stages(self.get_project_db_path(self.selected_project_id), self.selected_project_id)
            active_codes = [s['stage_code'] for s in active_stages]
            is_suspended = rmm.is_project_paused(self.get_project_db_path(self.selected_project_id), self.selected_project_id)
            is_finished  = 'ZAKONCZONY' in active_codes
            
            print(f"📋 load_project_stages: active_codes={active_codes}, is_suspended={is_suspended}, is_finished={is_finished}")
            print(f"📋 ui_rules: przyjety_enabled={ui_rules['przyjety_enabled']}, pause_enabled={ui_rules['pause_enabled']}")
            
            # 🛡️ DYNAMICZNA WALIDACJA: ZAKOŃCZONY tylko jeśli brak aktywnych etapów (tylko regularne etapy, nie milestones, nie WSTRZYMANY)
            # Pobierz milestones codes
            milestone_codes = {s['stage_code'] for s in stages if s['is_milestone']}
            has_active_regular_stages = any(
                code not in milestone_codes and code != 'WSTRZYMANY'
                for code in active_codes
            )
            if has_active_regular_stages:
                ui_rules['zakonczony_enabled'] = False  # Są aktywne etapy - blokada ZAKOŃCZONY
            
            # Sprawdź milestones (PRZYJĘTY, ZAKOŃCZONY)
            przyjety_set = rmm.is_milestone_set(self.get_project_db_path(self.selected_project_id), 
                                                 self.selected_project_id, 'PRZYJETY')
            zakonczony_set = rmm.is_milestone_set(self.get_project_db_path(self.selected_project_id), 
                                                   self.selected_project_id, 'ZAKONCZONY')
            
            # ── PRZYJĘTY – milestone (zdarzenie instant) ──────────────────────
            przyjety_frame = tk.Frame(self.stages_frame, bg="#e8f4fd", relief=tk.GROOVE, bd=2)
            przyjety_frame.pack(fill=tk.X, padx=8, pady=(8, 4))
            
            przyjety_info = rmm.get_milestone(self.get_project_db_path(self.selected_project_id),
                                              self.selected_project_id, 'PRZYJETY')
            
            przyjety_var = tk.BooleanVar(value=przyjety_set)
            przyjety_cb = tk.Checkbutton(
                przyjety_frame,
                text="✔ PROJEKT PRZYJĘTY",
                variable=przyjety_var,
                bg="#e8f4fd",
                font=("Arial", 10, "bold"),
                fg="#3498db",
                state=tk.NORMAL if ui_rules['przyjety_enabled'] else tk.DISABLED,
                command=lambda: self.toggle_milestone('PRZYJETY', przyjety_var.get())
            )
            przyjety_cb.pack(side=tk.LEFT, padx=10, pady=6)
            
            # Przycisk "Karta maszyny" - renderuj PRZED info (side=RIGHT)
            przyjety_att_count = self.get_stage_attachments_count('PRZYJETY')
            tk.Button(
                przyjety_frame,
                text=f"📋 Karta maszyny ({przyjety_att_count})",
                command=lambda: self.show_stage_attachments_window('PRZYJETY', 'Karta maszyny'),
                bg=self.COLOR_PURPLE,
                fg="white",
                font=self.FONT_SMALL,
                padx=8,
                pady=2
            ).pack(side=tk.RIGHT, padx=10, pady=6)
            
            if przyjety_info:
                timestamp = self.format_datetime(przyjety_info['timestamp'])
                user = przyjety_info['user'] or '?'
                tk.Label(
                    przyjety_frame,
                    text=f"📅 {timestamp} | 👤 {user}",
                    bg="#e8f4fd",
                    fg="#7f8c8d",
                    font=self.FONT_SMALL
                ).pack(side=tk.LEFT, padx=10)

            # ── WSTRZYMANY – master toggle ──────────────────────
            pause_frame = tk.Frame(self.stages_frame, bg="#fdf2f8", relief=tk.GROOVE, bd=2)
            pause_frame.pack(fill=tk.X, padx=8, pady=(8, 4))

            if is_suspended:
                pause_lbl_text = "⏸  PROJEKT WSTRZYMANY"
                pause_lbl_color = "#c0392b"
                pause_btn_text = "▶  WZNÓW PROJEKT"
                pause_btn_bg = self.COLOR_GREEN
                pause_btn_state = tk.NORMAL if ui_rules['resume_enabled'] else tk.DISABLED
                pause_btn_cmd = lambda: self.resume_project()
            elif is_finished:
                pause_lbl_text = "Projekt zakończony"
                pause_lbl_color = "#7f8c8d"
                pause_btn_text = "⏸  WSTRZYMAJ PROJEKT"
                pause_btn_bg = "#c0392b"
                pause_btn_state = tk.DISABLED
                pause_btn_cmd = lambda: None
            else:
                pause_lbl_text = "Projekt aktywny"
                pause_lbl_color = "#7f8c8d"
                pause_btn_text = "⏸  WSTRZYMAJ PROJEKT"
                pause_btn_bg = "#c0392b"
                pause_btn_state = tk.NORMAL if ui_rules['pause_enabled'] else tk.DISABLED
                pause_btn_cmd = lambda: self.pause_project()

            tk.Label(
                pause_frame, text=pause_lbl_text,
                bg="#fdf2f8", fg=pause_lbl_color,
                font=("Arial", 10, "bold"), pady=4
            ).pack(side=tk.LEFT, padx=10)

            tk.Button(
                pause_frame, text=pause_btn_text,
                command=pause_btn_cmd,
                bg=pause_btn_bg, fg="white",
                state=pause_btn_state,
                font=self.FONT_BOLD, padx=14, pady=4,
                relief=tk.RAISED, bd=2
            ).pack(side=tk.RIGHT, padx=10, pady=6)

            # ── Etapy (wszystko poza PRZYJETY, WSTRZYMANY, ZAKONCZONY i child milestones) ────────
            for stage in stages:
                stage_code = stage['stage_code']
                if stage_code in ('PRZYJETY', 'WSTRZYMANY', 'ZAKONCZONY'):
                    continue
                # Pomiń child milestones - widoczne tylko na osi czasu wewnątrz parent stage
                if stage_code in _CHILD_MILESTONE_CODES:
                    continue

                display_name = stage['display_name']
                is_active = stage_code in active_codes
                # Tło dla aktywnych etapów
                bg_color = self.COLOR_LIGHT_BLUE if is_active else "white"

                frame = tk.LabelFrame(
                    self.stages_frame,
                    text=f"  {display_name}  ",
                    bg=bg_color, font=self.FONT_BOLD, fg=self.COLOR_TOPBAR,
                    relief=tk.GROOVE, bd=2, padx=10, pady=2
                )
                frame.pack(fill=tk.X, padx=8, pady=4)

                tk.Label(
                    frame,
                    text="● TRWA" if is_active else "○ Nieaktywny",
                    bg=bg_color,
                    fg=self.COLOR_GREEN if is_active else 'gray',
                    font=self.FONT_BOLD
                ).pack(anchor=tk.W, pady=(0, 4))

                btn_frame = tk.Frame(frame, bg=bg_color)
                btn_frame.pack(fill=tk.X, pady=2)

                # State dla START: musi być enabled w rules I nieaktywny
                start_btn_state = tk.NORMAL if (ui_rules['stages_start_enabled'] and not is_active) else tk.DISABLED
                
                tk.Button(
                    btn_frame, text="🟢 ROZPOCZNIJ",
                    state=start_btn_state,
                    command=lambda sc=stage_code: self.start_stage(sc),
                    bg=self.COLOR_GREEN, fg="white",
                    font=self.FONT_BOLD, padx=12, pady=4,
                    relief=tk.RAISED, bd=2, width=12
                ).pack(side=tk.LEFT, padx=3)

                # Przycisk FORCE START (tylko dla ADMIN)
                if self.current_user_role == 'ADMIN':
                    force_state = tk.NORMAL if (self.have_lock and not self.read_only_mode and not is_active) else tk.DISABLED
                    tk.Button(
                        btn_frame, text="⚡ WYMUŚ START",
                        state=force_state,
                        command=lambda sc=stage_code: self.start_stage(sc, force=True),
                        bg=self.COLOR_ORANGE, fg="white",
                        font=self.FONT_SMALL, padx=6, pady=2,
                        relief=tk.RAISED, bd=1, width=12
                    ).pack(side=tk.LEFT, padx=3)

                # State dla END: musi mieć lock I etap aktywny
                end_btn_state = tk.NORMAL if (ui_rules['stages_start_enabled'] and is_active) else tk.DISABLED
                tk.Button(
                    btn_frame, text="🔴 ZAKOŃCZ",
                    state=end_btn_state,
                    command=lambda sc=stage_code: self.end_stage(sc),
                    bg=self.COLOR_RED, fg="white",
                    font=self.FONT_BOLD, padx=12, pady=4,
                    relief=tk.RAISED, bd=2, width=12
                ).pack(side=tk.LEFT, padx=3)

            # ── ZAKOŃCZONY – milestone (zdarzenie instant) ─────────
            finish_frame = tk.Frame(self.stages_frame, bg="#eafaf1", relief=tk.GROOVE, bd=2)
            finish_frame.pack(fill=tk.X, padx=8, pady=(4, 8))
            
            zakonczony_info = rmm.get_milestone(self.get_project_db_path(self.selected_project_id),
                                                self.selected_project_id, 'ZAKONCZONY')
            
            zakonczony_var = tk.BooleanVar(value=zakonczony_set)
            zakonczony_cb = tk.Checkbutton(
                finish_frame,
                text="✓ PROJEKT ZAKOŃCZONY",
                variable=zakonczony_var,
                bg="#eafaf1",
                font=("Arial", 10, "bold"),
                fg="#27ae60",
                state=tk.NORMAL if ui_rules['zakonczony_enabled'] else tk.DISABLED,
                command=lambda: self.toggle_milestone('ZAKONCZONY', zakonczony_var.get())
            )
            zakonczony_cb.pack(side=tk.LEFT, padx=10, pady=6)
            
            if zakonczony_info:
                timestamp = self.format_datetime(zakonczony_info['timestamp'])
                user = zakonczony_info['user'] or '?'
                tk.Label(
                    finish_frame,
                    text=f"📅 {timestamp} | 👤 {user}",
                    bg="#eafaf1",
                    fg="#7f8c8d",
                    font=self.FONT_SMALL
                ).pack(side=tk.LEFT, padx=10)
                
                # Przycisk Protokół odbioru
                zakonczony_att_count = self.get_stage_attachments_count('ZAKONCZONY')
                tk.Button(
                    finish_frame,
                    text=f"📋 Protokół odbioru ({zakonczony_att_count})",
                    command=lambda: self.show_stage_attachments_window('ZAKONCZONY', 'Protokół odbioru'),
                    bg=self.COLOR_PURPLE,
                    fg="white",
                    font=self.FONT_SMALL,
                    relief=tk.RAISED,
                    padx=8,
                    pady=3
                ).pack(side=tk.LEFT, padx=10)

            # Przywróć pozycję scrolla po przebudowie widgetów
            self.stages_frame.update_idletasks()
            self.left_canvas.yview_moveto(_scroll_pos[0])
            
            # Załaduj transze płatności i kody PLC
            self.load_payment_milestones()
            self.load_plc_codes()

        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można załadować etapów:\n{e}")
    
    # ========================================================================
    # Stage operations
    # ========================================================================

    def pause_project(self):
        """Wstrzymaj projekt (pauza overlay - nie etap!)"""
        if not self.selected_project_id:
            return

        if not self.have_lock:
            messagebox.showerror("🔒 Brak locka", "Musisz najpierw przejąć lock projektu.")
            return

        if self.read_only_mode:
            messagebox.showerror("🔒 Tryb tylko do odczytu", "Nie można wstrzymać projektu w trybie read-only.")
            return

        reason = simpledialog.askstring("⏸ Wstrzymanie projektu", "Powód wstrzymania (opcjonalnie):")

        try:
            self.status_bar.config(text="⏳ Wstrzymywanie projektu...", fg="#f39c12")
            self.root.update()

            rmm.pause_project(
                self.get_project_db_path(self.selected_project_id),
                self.selected_project_id,
                reason=reason,
                paused_by=CURRENT_USER,
                master_db_path=self.master_db_path
            )

            self.refresh_all()

            self.status_bar.config(text="⏸️  Projekt wstrzymany", fg="#c0392b")

        except ValueError as e:
            self.status_bar.config(text="⚠️ Już wstrzymany", fg="#f39c12")
            messagebox.showwarning("⚠️ Uwaga", str(e))
        except Exception as e:
            self.status_bar.config(text="🔴 Błąd wstrzymania", fg="#e74c3c")
            messagebox.showerror("❌ Błąd", f"Nie można wstrzymać projektu:\n{e}")

    def resume_project(self):
        """Wznów projekt (zakończ aktywną pauzę)"""
        if not self.selected_project_id:
            return

        if not self.have_lock:
            messagebox.showerror("🔒 Brak locka", "Musisz najpierw przejąć lock projektu.")
            return

        if self.read_only_mode:
            messagebox.showerror("🔒 Tryb tylko do odczytu", "Nie można wznowić projektu w trybie read-only.")
            return

        try:
            self.status_bar.config(text="⏳ Wznawianie projektu...", fg="#f39c12")
            self.root.update()

            rmm.resume_project(
                self.get_project_db_path(self.selected_project_id),
                self.selected_project_id,
                resumed_by=CURRENT_USER,
                master_db_path=self.master_db_path
            )

            self.refresh_all()

            self.status_bar.config(text="▶️  Projekt wznowiony", fg="#27ae60")

        except ValueError as e:
            self.status_bar.config(text="⚠️ Nie wstrzymany", fg="#f39c12")
            messagebox.showwarning("⚠️ Uwaga", str(e))
        except Exception as e:
            self.status_bar.config(text="🔴 Błąd wznowienia", fg="#e74c3c")
            messagebox.showerror("❌ Błąd", f"Nie można wznowić projektu:\n{e}")

    def start_stage(self, stage_code, force=False):
        """Rozpocznij etap
        
        Args:
            stage_code: kod etapu
            force: jeśli True, pomija walidację zależności (tylko ADMIN)
        """
        if not self.selected_project_id:
            return

        # Sprawdź lock
        if not self.have_lock:
            messagebox.showerror("🔒 Brak locka", "Musisz najpierw przejąć lock projektu.")
            return

        # Sprawdź uprawnienia
        if not self._has_permission('can_start_stage'):
            messagebox.showerror(
                "🚫 Brak uprawnień",
                f"Twoja rola [{self.current_user_role}] nie ma prawa do uruchamiania etapów.\n"
                "Skontaktuj się z administratorem (Użytkownicy → Uprawnienia kategorii)."
            )
            return
        
        # Force start tylko dla ADMIN
        if force and self.current_user_role != 'ADMIN':
            messagebox.showerror(
                "🚫 Brak uprawnień",
                "Wymuszony start jest dostępny tylko dla administratorów."
            )
            return

        # Sprawdź tryb READ-ONLY
        if self.read_only_mode:
            messagebox.showerror(
                "🔒 Tryb tylko do odczytu",
                f"Nie można rozpocząć etapu - plik projektu nieprawidłowy.\n\n"
                f"{self.file_verification_message}\n\n"
                f"Przywróć plik projektu i użyj 'Resetuj śledzenie' lub skontaktuj się z administratorem."
            )
            return
        
        try:
            self.status_bar.config(text=f"⏳ Rozpoczynanie {stage_code}...", fg="#f39c12")
            self.root.update()
            
            # Walidacja zależności (pomiń jeśli force=True)
            if not force:
                can_start, reason = rmm.can_start_stage(
                    self.get_project_db_path(self.selected_project_id),  # rm_db_path
                    self.selected_project_id,                             # project_id
                    stage_code,                                           # stage_code
                    master_db_path=self.master_db_path                    # master_db_path (keyword!)
                )
                
                if not can_start:
                    self.status_bar.config(text=f"⚠️ Nie można uruchomić {stage_code}", fg="#f39c12")
                    messagebox.showwarning("⚠️ Walidacja zależności", reason)
                    return
            else:
                # Ostrzeżenie dla force start
                if not messagebox.askyesno(
                    "⚡ Wymuszony start",
                    f"Czy na pewno chcesz wymusić start etapu {stage_code}?\n\n"
                    "Ta operacja pominie sprawdzanie zależności i może\n"
                    "zakłócić logiczny przepływ projektu.\n\n"
                    "Używaj tylko w wyjątkowych sytuacjach!"
                ):
                    self.status_bar.config(text="Anulowano", fg="gray")
                    return
            
            # START
            period_id = rmm.start_stage(
                self.get_project_db_path(self.selected_project_id),  # rm_db_path
                self.selected_project_id,                             # project_id
                stage_code,                                           # stage_code
                started_by=self.current_user,                         # started_by (keyword) - zalogowany użytkownik
                master_db_path=self.master_db_path                    # master_db_path (keyword)
            )
            
            # Refresh
            self.refresh_all()
            
            if force:
                self.status_bar.config(text=f"⚡ WYMUSZONO start {stage_code}", fg="#f39c12")
            else:
                self.status_bar.config(text=f"🟢 Rozpoczęto {stage_code}", fg="#27ae60")
            
        except ValueError as e:
            self.status_bar.config(text=f"⚠️ Błąd: {stage_code}", fg="#f39c12")
            messagebox.showwarning("⚠️ Uwaga", str(e))
        except Exception as e:
            self.status_bar.config(text=f"🔴 Błąd: {stage_code}", fg="#e74c3c")
            messagebox.showerror("❌ Błąd", f"Nie można rozpocząć etapu:\n{e}")
    
    def end_stage(self, stage_code):
        """Zakończ etap"""
        if not self.selected_project_id:
            return

        # Sprawdź lock
        if not self.have_lock:
            messagebox.showerror("🔒 Brak locka", "Musisz najpierw przejąć lock projektu.")
            return

        # Sprawdź uprawnienia
        if not self._has_permission('can_end_stage'):
            messagebox.showerror(
                "🚫 Brak uprawnień",
                f"Twoja rola [{self.current_user_role}] nie ma prawa do kończenia etapów.\n"
                "Skontaktuj się z administratorem (Użytkownicy → Uprawnienia kategorii)."
            )
            return

        # Sprawdź tryb READ-ONLY
        if self.read_only_mode:
            messagebox.showerror(
                "🔒 Tryb tylko do odczytu",
                f"Nie można zakończyć etapu - plik projektu nieprawidłowy.\n\n"
                f"{self.file_verification_message}\n\n"
                f"Przywróć plik projektu i użyj 'Resetuj śledzenie' lub skontaktuj się z administratorem."
            )
            return
        
        try:
            self.status_bar.config(text=f"⏳ Kończenie {stage_code}...", fg="#f39c12")
            self.root.update()
            
            # END
            rmm.end_stage(
                self.get_project_db_path(self.selected_project_id),  # rm_db_path
                self.selected_project_id,                             # project_id
                stage_code,                                           # stage_code
                ended_by=self.current_user,                           # ended_by (keyword) - zalogowany użytkownik
                master_db_path=self.master_db_path                    # master_db_path (keyword)
            )
            # 🔄 AUTO-UPDATE status projektu jest wewnątrz end_stage()
            
            # Variance
            variance = rmm.get_stage_variance(self.get_project_db_path(self.selected_project_id), self.selected_project_id, stage_code)
            var_days = variance.get('variance_days', 0)
            
            # Refresh
            self.refresh_all()
            
            # Komunikat
            if var_days > 0:
                self.status_bar.config(text=f"⚠️ {stage_code} zakończony (+{var_days}d opóźnienie)", fg="#f39c12")
                messagebox.showwarning(
                    "⚠️ Zakończono z opóźnieniem",
                    f"Etap {stage_code} zakończony\n\nOpóźnienie: +{var_days} dni"
                )
            else:
                self.status_bar.config(text=f"🟢 {stage_code} zakończony", fg="#27ae60")
            
        except ValueError as e:
            self.status_bar.config(text=f"⚠️ Błąd: {stage_code}", fg="#f39c12")
            messagebox.showwarning("⚠️ Uwaga", str(e))
        except Exception as e:
            self.status_bar.config(text=f"🔴 Błąd: {stage_code}", fg="#e74c3c")
            messagebox.showerror("❌ Błąd", f"Nie można zakończyć etapu:\n{e}")
    
    def toggle_milestone(self, stage_code, is_checked):
        """Ustaw/usuń milestone (checkbox handler)
        
        Args:
            stage_code: kod milestone (PRZYJETY, ZAKONCZONY)
            is_checked: True = zaznaczony, False = odznaczony
        """
        if not self.selected_project_id:
            return

        # Sprawdź lock
        if not self.have_lock:
            messagebox.showerror("🔒 Brak locka", "Musisz najpierw przejąć lock projektu.")
            self.load_project_stages()
            return

        # Sprawdź uprawnienia (używamy can_start_stage dla set, can_end_stage dla unset)
        if is_checked and not self._has_permission('can_start_stage'):
            messagebox.showerror(
                "🚫 Brak uprawnień",
                f"Twoja rola [{self.current_user_role}] nie ma prawa do ustawiania milestones.\n"
                "Skontaktuj się z administratorem."
            )
            self.load_project_stages()  # Refresh żeby cofnąć checkbox
            return
        
        if not is_checked and not self._has_permission('can_end_stage'):
            messagebox.showerror(
                "🚫 Brak uprawnień",
                f"Twoja rola [{self.current_user_role}] nie ma prawa do usuwania milestones.\n"
                "Skontaktuj się z administratorem."
            )
            self.load_project_stages()  # Refresh żeby cofnąć checkbox
            return

        # Sprawdź tryb READ-ONLY
        if self.read_only_mode:
            messagebox.showerror(
                "🔒 Tryb tylko do odczytu",
                f"Nie można modyfikować milestone - plik projektu nieprawidłowy.\n\n"
                f"{self.file_verification_message}"
            )
            self.load_project_stages()  # Refresh żeby cofnąć checkbox
            return
        
        try:
            print(f"\n🎯 TOGGLE_MILESTONE: {stage_code}, checked={is_checked}, projekt={self.selected_project_id}")
            print(f"   Lock: {self.have_lock}, Read-only: {self.read_only_mode}")
            print(f"   User: {self.current_user} ({self.current_user_role})")
            
            if is_checked:
                # Sprawdź czy już ustawiony (może być race condition)
                project_db = self.get_project_db_path(self.selected_project_id)
                already_set = rmm.is_milestone_set(project_db, self.selected_project_id, stage_code)
                print(f"   Już ustawiony w bazie: {already_set}")
                
                if already_set:
                    print(f"   ⚠️ Milestone {stage_code} już ustawiony - pomijam")
                    self.load_project_stages()  # Refresh checkbox
                    return
                
                # Ustaw milestone
                print(f"   🚀 Wywołuję rmm.set_milestone...")
                self.status_bar.config(text=f"⏳ Ustawianie milestone: {stage_code}...", fg="#f39c12")
                self.root.update()
                
                period_id = rmm.set_milestone(
                    self.get_project_db_path(self.selected_project_id),  # rm_db_path
                    self.selected_project_id,                             # project_id
                    stage_code,                                           # stage_code
                    user=self.current_user,                               # user (keyword) - zalogowany użytkownik
                    master_db_path=self.master_db_path                    # master_db_path (keyword)
                )
                
                print(f"   ✅ Milestone {stage_code} ustawiony, period_id={period_id}")
                self.status_bar.config(text=f"✅ Milestone {stage_code} ustawiony", fg="#27ae60")
                
            else:
                # Usuń milestone (cofnij / wznów projekt)
                if stage_code == 'ZAKONCZONY':
                    message = (
                        "Czy na pewno chcesz wznowić zakończony projekt?\n\n"
                        "Ta operacja:\n"
                        "• Usunie milestone ZAKOŃCZONY\n"
                        "• Zmieni status projektu na IN_PROGRESS lub ACCEPTED\n"
                        "• Umożliwi dalszą pracę nad projektem\n\n"
                        "Używaj gdy trzeba wrócić do zakończonego projektu."
                    )
                    title = "🔄 Wznowić zakończony projekt?"
                else:
                    message = (
                        f"Czy na pewno chcesz cofnąć milestone {stage_code}?\n\n"
                        f"Ta operacja usunie zapis zdarzenia."
                    )
                    title = "⚠️ Cofnąć milestone?"
                
                result = messagebox.askyesno(title, message)
                
                if not result:
                    print(f"   ❌ Użytkownik anulował usunięcie milestone {stage_code}")
                    self.load_project_stages()  # Refresh żeby przywrócić checkbox
                    return
                
                print(f"   🗑️ Wywołuję rmm.unset_milestone...")
                self.status_bar.config(text=f"⏳ Usuwanie milestone: {stage_code}...", fg="#f39c12")
                self.root.update()
                
                rmm.unset_milestone(
                    self.get_project_db_path(self.selected_project_id),  # rm_db_path
                    self.selected_project_id,                             # project_id
                    stage_code,                                           # stage_code
                    master_db_path=self.master_db_path                    # master_db_path (keyword)
                )
                
                print(f"   ✅ Milestone {stage_code} usunięty")
                
                if stage_code == 'ZAKONCZONY':
                    self.status_bar.config(text=f"🔄 Projekt wznowiony", fg="#27ae60")
                else:
                    self.status_bar.config(text=f"✅ Milestone {stage_code} usunięty", fg="#27ae60")
            
            # Refresh
            self.refresh_all()
            
        except ValueError as e:
            print(f"   ⚠️ ValueError w toggle_milestone: {e}")
            self.status_bar.config(text=f"⚠️ Błąd: {stage_code}", fg="#f39c12")
            messagebox.showwarning("⚠️ Uwaga", str(e))
            self.load_project_stages()  # Refresh żeby cofnąć checkbox
        except Exception as e:
            print(f"   🔥 Exception w toggle_milestone: {e}")
            import traceback
            traceback.print_exc()
            self.status_bar.config(text=f"🔴 Błąd: {stage_code}", fg="#e74c3c")
            messagebox.showerror("❌ Błąd", f"Nie można zmienić milestone:\n{e}")
            self.load_project_stages()  # Refresh żeby cofnąć checkbox
    
    # ========================================================================
    # Visualization
    # ========================================================================
    
    def refresh_timeline(self):
        """Odśwież timeline - interaktywny panel z edycją dat"""
        if not self.selected_project_id:
            return
        
        # Zapisz pozycję scrolla przed odświeżeniem
        scroll_pos = self.timeline_canvas.yview()
        
        # Reset flagi renderowania transportu - widgety i tak są niszczone poniżej
        self._transport_rendered_for_project = None
        
        # Wyczyść stare widgety i słownik Entry widgets
        for widget in self.timeline_frame.winfo_children():
            widget.destroy()
        self.timeline_entries.clear()
        
        try:
            forecast = rmm.recalculate_forecast(self.get_project_db_path(self.selected_project_id), self.selected_project_id)
            
            # Pobierz display_name, sequence i is_milestone dla wszystkich etapów z bazy danych
            con = rmm._open_rm_connection(self.get_project_db_path(self.selected_project_id))
            
            # Stage names i milestones
            cursor = con.execute("SELECT code, display_name, is_milestone FROM stage_definitions")
            stage_data = {}
            for row in cursor.fetchall():
                stage_data[row['code']] = {
                    'display_name': row['display_name'],
                    'is_milestone': bool(row['is_milestone'])
                }
            
            # Stage sequence (z project_stages)
            cursor = con.execute("""
                SELECT stage_code, sequence 
                FROM project_stages 
                WHERE project_id = ?
            """, (self.selected_project_id,))
            stage_sequence = {row['stage_code']: row['sequence'] for row in cursor.fetchall()}
            con.close()
            
            # Nagłówek
            header = tk.Frame(self.timeline_frame, bg=self.COLOR_TOPBAR, pady=8)
            header.pack(fill=tk.X, padx=5, pady=(5, 10))
            
            project_name = self.project_names.get(self.selected_project_id, f'Projekt {self.selected_project_id}')
            tk.Label(
                header,
                text=f"OŚ CZASU - {project_name}",
                bg=self.COLOR_TOPBAR,
                fg="white",
                font=("Arial", 12, "bold")
            ).pack()
            
            # Sortuj etapy według sequence z bazy danych (lub DEFAULT_STAGE_SEQUENCE jako fallback)
            stage_order = {code: idx for idx, code in enumerate(DEFAULT_STAGE_SEQUENCE)}
            # Dodaj alias AUTOMATYKA dla kompatybilności wstecznej (stare bazy)
            if 'ELEKTROMONTAZ' in DEFAULT_STAGE_SEQUENCE:
                elektromontaz_idx = DEFAULT_STAGE_SEQUENCE.index('ELEKTROMONTAZ')
                stage_order['AUTOMATYKA'] = elektromontaz_idx
            
            def get_stage_sort_key(stage_code):
                """Zwróć klucz sortowania: najpierw sequence z bazy, potem DEFAULT_STAGE_SEQUENCE"""
                if stage_code in stage_sequence:
                    return stage_sequence[stage_code]
                return stage_order.get(stage_code, 999)
            
            sorted_stages = sorted(forecast.keys(), key=get_stage_sort_key)
            
            # Dla każdego etapu utwórz wiersz z edytowalnymi polami
            for idx, stage_code in enumerate(sorted_stages):
                # Pomiń child milestones - renderowane wewnątrz ramki parent stage
                if stage_code in _CHILD_MILESTONE_CODES:
                    continue
                
                fc = forecast[stage_code]
                stage_info = stage_data.get(stage_code, {'display_name': stage_code, 'is_milestone': False})
                display_name = stage_info['display_name']
                is_milestone = stage_info['is_milestone']
                
                # DEBUG: Wypisz dane dla PROJEKT
                if stage_code == 'PROJEKT':
                    print(f"🎯 DEBUG refresh_timeline PROJEKT:")
                    print(f"    forecast data: {fc}")
                    print(f"    template_start: {fc.get('template_start')}")
                    print(f"    template_end: {fc.get('template_end')}")
                    print(f"    forecast_start: {fc.get('forecast_start')}")
                    print(f"    forecast_end: {fc.get('forecast_end')}")
                    print(f"    is_milestone: {is_milestone}")
                    print(f"    is_actual: {fc.get('is_actual')}")
                    print(f"    actual_periods: {fc.get('actual_periods')}")
                    
                    # DEBUGGING: Sprawdź dane w bazie
                    try:
                        con_debug = rmm._open_rm_connection(self.get_project_db_path(self.selected_project_id))
                        
                        # Actual periods
                        cursor = con_debug.execute('''
                            SELECT sap.started_at, sap.ended_at
                            FROM stage_actual_periods sap
                            JOIN project_stages ps ON sap.project_stage_id = ps.id
                            WHERE ps.project_id = ? AND ps.stage_code = ?
                        ''', (self.selected_project_id, 'PROJEKT'))
                        actual_rows = cursor.fetchall()
                        print(f"    🔍 ACTUAL PERIODS z bazy: {[dict(r) for r in actual_rows]}")
                        
                        con_debug.close()
                    except Exception as e:
                        print(f"    ❌ Error checking DB: {e}")

                # DEBUG: Etapy które mogą nie mieć template
                if stage_code in ['ODBIORY', 'FAT', 'TRANSPORT']:
                    print(f"📋 DEBUG etap {stage_code}:")
                    print(f"    template_start: '{fc.get('template_start')}'")
                    print(f"    template_end: '{fc.get('template_end')}'") 
                    print(f"    forecast_start: '{fc.get('forecast_start')}'")
                    print(f"    forecast_end: '{fc.get('forecast_end')}'")
                    print(f"    is_milestone: {is_milestone}")
                    print(f"    is_actual: {fc.get('is_actual')}")
                
                status_icon = "🟢" if fc.get('is_active') else "⏺️"
                actual_icon = "✔️" if fc.get('is_actual') else "📋"
                variance = fc.get('variance_days', 0)
                variance_str = f"+{variance}" if variance > 0 else str(variance)
                variance_icon = "⚠️" if variance > 0 else "✅"
                # Tło dla aktywnych etapów
                bg_color = self.COLOR_LIGHT_BLUE if fc.get('is_active') else "white"
                
                # Frame dla etapu/milestone
                stage_frame = tk.LabelFrame(
                    self.timeline_frame,
                    text=f"  {status_icon} {actual_icon} {display_name}  ",
                    font=self.FONT_BOLD,
                    fg=self.COLOR_TOPBAR,
                    bg=bg_color,
                    relief=tk.GROOVE,
                    bd=2,
                    padx=10,
                    pady=2
                )
                stage_frame.pack(fill=tk.X, padx=5, pady=5)
                stage_frame._stage_code = stage_code
                
                # ── NAGŁÓWEK z przyciskami akcji (notatki) ──
                header_row = tk.Frame(stage_frame, bg=bg_color)
                header_row.pack(fill=tk.X, pady=(0, 5))
                
                # Pobierz statystyki notatek
                try:
                    notes_stats = rmm.get_topic_stats(
                        self.get_project_db_path(self.selected_project_id),
                        self.selected_project_id,
                        stage_code
                    )
                    topic_count = notes_stats['total_topics']
                    notes_count = notes_stats['total_notes']
                    alarms_count = notes_stats['active_alarms']
                except Exception as ex:
                    print(f"⚠️ get_topic_stats({stage_code}): {ex}")
                    topic_count = 0
                    notes_count = 0
                    alarms_count = 0
                
                # Przycisk notatnika z licznikiem - tematy + notatki
                if topic_count > 0 or notes_count > 0:
                    notes_btn_text = f"📝 {topic_count}T/{notes_count}N"
                else:
                    notes_btn_text = "📝"
                if alarms_count > 0:
                    notes_btn_text += f" ⏰{alarms_count}"
                
                # Przyciski notatek zawsze aktywne (umożliwiają przeglądanie)
                notes_btn = tk.Button(
                    header_row,
                    text=notes_btn_text,
                    command=lambda sc=stage_code: self.show_notes_window(sc),
                    bg=self.COLOR_PURPLE if topic_count > 0 else "#95a5a6",
                    fg="white",
                    font=self.FONT_SMALL,
                    padx=8,
                    pady=2
                )
                notes_btn.pack(side=tk.RIGHT, padx=2)
                
                # ── % ODEBRANO (tylko dla KOMPLETACJA, gdy są dane) ──
                if stage_code == 'KOMPLETACJA':
                    # Format z bazy: "85% (116)" - nie pokazuj gdy brak danych
                    raw = self.received_percent or "?"
                    print(f"📊 DEBUG TIMELINE KOMPLETACJA: self.received_percent='{self.received_percent}', raw='{raw}', project_id={self.selected_project_id}")
                    
                    if raw and raw != "?":
                        # Zielone tło TYLKO dla badge'a (osobna zmienna!)
                        badge_bg_color = "#d5f4e6"
                        badge_fg_color = "#27ae60"
                        
                        received_lbl = tk.Label(
                            header_row,
                            text=f"📦 {raw}",
                            bg=badge_bg_color,
                            fg=badge_fg_color,
                            font=("Arial", 10, "bold"),
                            padx=10,
                            pady=4,
                            relief=tk.RIDGE,
                            bd=1
                        )
                        received_lbl.pack(side=tk.LEFT, padx=5)
                        
                        # Tooltip wyjaśniający
                        def show_tooltip(event):
                            try:
                                import tkinter.messagebox as mbox
                                percent, count = raw.split()
                                mbox.showinfo(
                                    "Kompletacja BOM",
                                    f"Procent odebranych elementów: {percent}\n"
                                    f"Łączna ilość pozycji w arkuszu: {count}\n\n"
                                    f"(Dane synchronizowane z RM_BAZA)"
                                )
                            except:
                                pass
                        
                        received_lbl.bind("<Button-1>", show_tooltip)
                
                if topic_count > 0 or notes_count > 0:
                    # ── Podgląd 2 pierwszych tematów (inline w header_row) ──
                    try:
                        _db_path = self.get_project_db_path(self.selected_project_id)
                        topics_preview = rmm.get_topics(_db_path, self.selected_project_id, stage_code)[:2]
                        if topics_preview:
                            for ti, tp in enumerate(reversed(topics_preview)):
                                pri_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(tp['priority'], "⚪")
                                title_text = tp['title'][:80]
                                if len(tp['title']) > 80:
                                    title_text += "…"
                                tidx = len(topics_preview) - 1 - ti
                                topic_lbl = tk.Label(
                                    header_row,
                                    text=f" {pri_icon} #{tp['topic_number']} {title_text} ",
                                    bg="#f0f4ff",
                                    fg="#2c3e50",
                                    font=("Arial", 8),
                                    cursor="hand2",
                                    padx=4,
                                    pady=1,
                                    relief=tk.FLAT
                                )
                                topic_lbl.pack(side=tk.RIGHT, padx=2)
                                topic_lbl.bind("<Button-1>", lambda e, sc=stage_code, idx=tidx: self.show_notes_window(sc, idx))
                    except Exception:
                        pass
                    
                    tk.Label(
                        header_row,
                        text=f"({topic_count} tematów, {notes_count} notatek)",
                        bg="white",
                        fg="gray",
                        font=("Arial", 8)
                    ).pack(side=tk.RIGHT, padx=5)
                
                # ── MILESTONE: tylko jedna data (instant) ──────────────────────
                if is_milestone:
                    # DEBUG: Sprawdź dane milestones
                    if stage_code in ['PRZYJETY', 'ZAKONCZONY']:
                        print(f"🏁 DEBUG milestone {stage_code}:")
                        print(f"    template_start: '{fc.get('template_start')}'")
                        print(f"    template_end: '{fc.get('template_end')}'")
                        print(f"    forecast_start: '{fc.get('forecast_start')}'")
                        print(f"    forecast_end: '{fc.get('forecast_end')}'")
                    
                    row1 = tk.Frame(stage_frame, bg="white")
                    row1.pack(fill=tk.X, pady=3)
                    
                    tk.Label(
                        row1, 
                        text="Zdarzenie:", 
                        bg="white", 
                        font=self.FONT_BOLD,
                        width=12,
                        anchor="w"
                    ).pack(side=tk.LEFT, padx=(0, 5))
                    
                    # Milestone ma tylko jedną datę (started_at = ended_at)
                    # POPRAWKA: Sprawdź czy template_start nie jest None/pusty
                    raw_template_start = fc.get('template_start')
                    if raw_template_start and raw_template_start.strip():
                        milestone_date = self.format_date_ddmmyyyy(raw_template_start) or ''
                    else:
                        milestone_date = ''  # Pusta data dla nieskonfigurowanych milestones
                    
                    if stage_code in ['PRZYJETY', 'ZAKONCZONY']:
                        print(f"    raw_template_start: '{raw_template_start}'")
                        print(f"    milestone_date after format: '{milestone_date}'")
                    
                    milestone_entry = tk.Entry(row1, width=25, font=self.FONT_DEFAULT, 
                                             disabledbackground='#f0f0f0', disabledforeground='black',
                                             readonlybackground='#f0f0f0', fg='black')
                    milestone_entry.insert(0, milestone_date)
                    milestone_entry.pack(side=tk.LEFT, padx=2)
                    if not self.have_lock:
                        milestone_entry.config(state='readonly')
                    
                    # Przycisk kalendarza
                    cal_btn = tk.Button(
                        row1,
                        text="📅",
                        command=lambda me=milestone_entry: self.open_calendar_picker(me),
                        bg="#3498db",
                        fg="white",
                        font=self.FONT_SMALL,
                        padx=4,
                        pady=1,
                        state=tk.NORMAL if self.have_lock else tk.DISABLED
                    )
                    cal_btn.pack(side=tk.LEFT, padx=2)
                    
                    # Zapisz referencję (tylko jedna data dla milestone)
                    self.timeline_entries[stage_code] = (milestone_entry, milestone_entry)
                    
                    # Przycisk zapisu
                    save_btn = tk.Button(
                        row1,
                        text="💾 Zapisz",
                        command=lambda sc=stage_code, me=milestone_entry: 
                            self.save_milestone_date(sc, me.get()),
                        bg=self.COLOR_GREEN,
                        fg="white",
                        font=self.FONT_SMALL,
                        padx=8,
                        pady=2,
                        state=tk.NORMAL if self.have_lock else tk.DISABLED
                    )
                    save_btn.pack(side=tk.LEFT, padx=10)
                    
                    # Prognoza (tylko do odczytu)
                    row2 = tk.Frame(stage_frame, bg="white")
                    row2.pack(fill=tk.X, pady=3)
                    
                    tk.Label(
                        row2, 
                        text="Prognoza:", 
                        bg="white", 
                        font=self.FONT_BOLD,
                        width=12,
                        anchor="w"
                    ).pack(side=tk.LEFT, padx=(0, 5))
                    
                    forecast_date_fmt = self.format_date_ddmmyyyy(fc.get('forecast_start')) or 'N/A'
                    
                    tk.Label(
                        row2,
                        text=f"📅 {forecast_date_fmt}",
                        bg="white",
                        font=self.FONT_DEFAULT,
                        fg=self.COLOR_PURPLE
                    ).pack(side=tk.LEFT, padx=2)
                    
                    # Przyciski załączników dla milestone'ów
                    if stage_code in ('PRZYJETY', 'ZAKONCZONY'):
                        att_row = tk.Frame(stage_frame, bg="white")
                        att_row.pack(fill=tk.X, pady=(5, 0))
                        
                        if stage_code == 'PRZYJETY':
                            btn_text = "📋 Karta maszyny"
                            btn_title = 'Karta maszyny'
                        else:  # ZAKONCZONY
                            btn_text = "📋 Protokół odbioru"
                            btn_title = 'Protokół odbioru'
                        
                        # Dodaj licznik załączników
                        att_count = self.get_stage_attachments_count(stage_code)
                        
                        tk.Button(
                            att_row,
                            text=f"{btn_text} ({att_count})",
                            command=lambda sc=stage_code, title=btn_title: self.show_stage_attachments_window(sc, title),
                            bg=self.COLOR_PURPLE,
                            fg="white",
                            font=self.FONT_SMALL,
                            padx=8,
                            pady=2
                        ).pack(side=tk.LEFT, padx=5)
                    
                    continue  # Pomiń normalny rendering dla etapu
                
                # ── Wiersz 1: Szablon (edytowalny) - TYLKO DLA STAGES ──────────
                row1 = tk.Frame(stage_frame, bg=bg_color)
                row1.pack(fill=tk.X, pady=3)
                
                tk.Label(
                    row1, 
                    text="Szablon:", 
                    bg=bg_color, 
                    font=self.FONT_BOLD,
                    width=12,
                    anchor="w"
                ).pack(side=tk.LEFT, padx=(0, 5))
                
                # Entry widgets - ZAWSZE twórz jako normal, wstaw tekst, POTEM zablokuj jeśli trzeba
                # Konwersja dat z ISO (YYYY-MM-DD) do DD-MM-YYYY dla wyświetlania
                template_start_val = self.format_date_ddmmyyyy(fc.get('template_start')) or ''
                template_end_val = self.format_date_ddmmyyyy(fc.get('template_end')) or ''
                
                # DEBUG: Wypisz wartości Entry dla PROJEKT
                if stage_code == 'PROJEKT':
                    print(f"🎯 Entry values PROJEKT:")
                    print(f"    raw template_start: '{fc.get('template_start')}'")
                    print(f"    formatted start: '{template_start_val}'")
                    print(f"    raw template_end: '{fc.get('template_end')}'")
                    print(f"    formatted end: '{template_end_val}'")

                template_start = tk.Entry(row1, width=12, font=self.FONT_DEFAULT, 
                                         disabledbackground='#f0f0f0', disabledforeground='black',
                                         readonlybackground='#f0f0f0', fg='black')
                template_start.insert(0, template_start_val)
                template_start.pack(side=tk.LEFT, padx=2)
                if not self.have_lock:
                    template_start.config(state='readonly')
                
                # Przycisk kalendarza dla daty rozpoczęcia
                cal_start_btn = tk.Button(
                    row1,
                    text="📅",
                    command=lambda ts=template_start: self.open_calendar_picker(ts),
                    bg="#3498db",
                    fg="white",
                    font=self.FONT_SMALL,
                    padx=3,
                    pady=1,
                    state=tk.NORMAL if self.have_lock else tk.DISABLED
                )
                cal_start_btn.pack(side=tk.LEFT, padx=1)
                
                tk.Label(row1, text="→", bg=bg_color).pack(side=tk.LEFT, padx=2)
                
                template_end = tk.Entry(row1, width=12, font=self.FONT_DEFAULT,
                                       disabledbackground='#f0f0f0', disabledforeground='black',
                                       readonlybackground='#f0f0f0', fg='black')
                template_end.insert(0, template_end_val)
                template_end.pack(side=tk.LEFT, padx=2)
                if not self.have_lock:
                    template_end.config(state='readonly')
                
                # Przycisk kalendarza dla daty zakończenia
                cal_end_btn = tk.Button(
                    row1,
                    text="📅",
                    command=lambda te=template_end: self.open_calendar_picker(te),
                    bg="#3498db",
                    fg="white",
                    font=self.FONT_SMALL,
                    padx=3,
                    pady=1,
                    state=tk.NORMAL if self.have_lock else tk.DISABLED
                )
                cal_end_btn.pack(side=tk.LEFT, padx=1)
                
                # Zapisz referencje do Entry widgets
                self.timeline_entries[stage_code] = (template_start, template_end)
                
                # Przycisk zapisu - aktywny tylko gdy jest lock
                save_btn = tk.Button(
                    row1,
                    text="💾 Zapisz szablon",
                    command=lambda sc=stage_code, ts=template_start, te=template_end: 
                        self._debug_and_save_stage_template(sc, ts, te),
                    bg=self.COLOR_GREEN,
                    fg="white",
                    font=self.FONT_SMALL,
                    padx=8,
                    pady=2,
                    state=tk.NORMAL if self.have_lock else tk.DISABLED
                )
                save_btn.pack(side=tk.LEFT, padx=10)
                
                # Przycisk reset - usuwa actual periods i wraca do template  
                reset_btn = tk.Button(
                    row1,
                    text="🗑️ Reset etapu",
                    command=lambda sc=stage_code: self.reset_stage_to_template(sc),
                    bg=self.COLOR_RED,
                    fg="white", 
                    font=self.FONT_SMALL,
                    padx=8,
                    pady=2,
                    state=tk.NORMAL if self.have_lock else tk.DISABLED
                )
                reset_btn.pack(side=tk.LEFT, padx=5)
                
                # Przycisk pracowników - zawsze dostępny (edycja wymaga locka w dialogu)
                # Pobierz liczbę przypisanych pracowników
                try:
                    assigned_staff = rmm.get_stage_assigned_staff(
                        self.get_project_db_path(self.selected_project_id),
                        self.rm_master_db_path,
                        self.selected_project_id,
                        stage_code
                    )
                    staff_count = len(assigned_staff)
                    staff_btn_text = f"👷 Pracownicy ({staff_count})" if staff_count > 0 else "👷 Pracownicy"
                    staff_btn_bg = self.COLOR_GREEN if staff_count > 0 else "#95a5a6"
                except Exception:
                    staff_btn_text = "👷 Pracownicy"
                    staff_btn_bg = "#95a5a6"
                    staff_count = 0
                
                # Przyciski pracowników zawsze aktywne (umożliwiają przeglądanie)
                staff_btn = tk.Button(
                    row1,
                    text=staff_btn_text,
                    command=lambda sc=stage_code: self.assign_staff_dialog(sc),
                    bg=staff_btn_bg,
                    fg="white",
                    font=self.FONT_SMALL,
                    padx=8,
                    pady=2
                )
                staff_btn.pack(side=tk.LEFT, padx=5)
                
                # Wiersz 1b: Lista przypisanych pracowników (jeśli są)
                if staff_count > 0:
                    row1b = tk.Frame(stage_frame, bg=bg_color)
                    row1b.pack(fill=tk.X, pady=(0, 3))
                    
                    tk.Label(
                        row1b, 
                        text="", 
                        bg=bg_color,
                        width=12
                    ).pack(side=tk.LEFT, padx=(0, 5))
                    
                    # Wyświetl pracowników  
                    staff_info = []
                    for s in assigned_staff:
                        name = s['employee_name']
                        category = s['category']
                        # Sprawdź czy kategoria pasuje do etapu
                        preferred = rmm.STAGE_TO_PREFERRED_CATEGORY.get(stage_code, [])
                        if category not in preferred:
                            staff_info.append(f"⚠️ {name} ({category})")
                        else:
                            staff_info.append(f"👤 {name} ({category})")
                    
                    staff_text = ", ".join(staff_info)
                    
                    tk.Label(
                        row1b,
                        text=staff_text,
                        bg=bg_color,
                        font=self.FONT_SMALL,
                        fg="gray",
                        wraplength=600,
                        justify=tk.LEFT
                    ).pack(side=tk.LEFT, padx=2)
                
                # Wiersz 2: Prognoza (tylko do odczytu)
                row2 = tk.Frame(stage_frame, bg=bg_color)
                row2.pack(fill=tk.X, pady=3)
                
                tk.Label(
                    row2, 
                    text="Prognoza:", 
                    bg=bg_color, 
                    font=self.FONT_BOLD,
                    width=12,
                    anchor="w"
                ).pack(side=tk.LEFT, padx=(0, 5))
                
                # Formatuj daty prognozy do DD-MM-YYYY
                forecast_start_fmt = self.format_date_ddmmyyyy(fc.get('forecast_start')) or 'N/A'
                forecast_end_fmt = self.format_date_ddmmyyyy(fc.get('forecast_end')) or 'N/A'
                
                tk.Label(
                    row2,
                    text=f"{forecast_start_fmt} → {forecast_end_fmt}",
                    bg=bg_color,
                    font=self.FONT_DEFAULT,
                    fg=self.COLOR_PURPLE
                ).pack(side=tk.LEFT, padx=2)
                
                # Wiersz 3: Odchylenie
                row3 = tk.Frame(stage_frame, bg=bg_color)
                row3.pack(fill=tk.X, pady=3)
                
                tk.Label(
                    row3, 
                    text="Odchylenie:", 
                    bg=bg_color, 
                    font=self.FONT_BOLD,
                    width=12,
                    anchor="w"
                ).pack(side=tk.LEFT, padx=(0, 5))
                
                tk.Label(
                    row3,
                    text=f"{variance_str} dni {variance_icon}",
                    bg=bg_color,
                    font=self.FONT_DEFAULT,
                    fg=self.COLOR_ORANGE if variance > 0 else self.COLOR_GREEN
                ).pack(side=tk.LEFT, padx=2)
                
                # Wiersz 4: Okresy (jeśli są)
                periods = fc.get('actual_periods', [])
                if periods:
                    row4 = tk.Frame(stage_frame, bg=bg_color)
                    row4.pack(fill=tk.X, pady=3)
                    
                    tk.Label(
                        row4, 
                        text=f"Okresy ({len(periods)}):", 
                        bg=bg_color, 
                        font=self.FONT_BOLD,
                        width=12,
                        anchor="w"
                    ).pack(side=tk.LEFT, padx=(0, 5))
                    
                    periods_text = ""
                    for i, p in enumerate(periods, 1):
                        status = "TRWA" if p['ended_at'] is None else "✓"
                        start_fmt = self.format_datetime(p['started_at'])
                        end_fmt = self.format_datetime(p['ended_at']) if p['ended_at'] else 'TRWA'
                        periods_text += f"#{i}: {start_fmt} → {end_fmt} ({status})  "
                    
                    tk.Label(
                        row4,
                        text=periods_text,
                        bg=bg_color,
                        font=self.FONT_SMALL,
                        fg="gray"
                    ).pack(side=tk.LEFT, padx=2)
                
                # ── SUB-MILESTONES: renderowane wewnątrz ramki etapu-rodzica ──
                if stage_code in SUB_MILESTONES:
                    sep = ttk.Separator(stage_frame, orient='horizontal')
                    sep.pack(fill=tk.X, pady=(8, 4))
                    
                    tk.Label(
                        stage_frame,
                        text="📌 Punkty kontrolne:",
                        bg=bg_color,
                        font=self.FONT_BOLD,
                        fg="#2c3e50",
                        anchor="w"
                    ).pack(fill=tk.X, padx=0, pady=(0, 4))
                    
                    # Pobierz firmy transportowe (do combobox TRANSPORT)
                    transport_companies = []
                    transport_map = {}  # id -> name
                    try:
                        transport_companies = rmm.get_transports(self.rm_master_db_path, active_only=True)
                        transport_map = {t['id']: t['name'] for t in transport_companies}
                        print(f"📦 Załadowano {len(transport_companies)} firm transportowych: {list(transport_map.values())}")
                    except Exception as ex:
                        print(f"⚠️ Błąd ładowania firm transportowych: {ex}")
                        pass
                    
                    for sub_code in SUB_MILESTONES[stage_code]:
                        sub_fc = forecast.get(sub_code)
                        sub_info = stage_data.get(sub_code, {'display_name': sub_code, 'is_milestone': True})
                        sub_display = sub_info['display_name']
                        
                        sub_row = tk.Frame(stage_frame, bg="#f8f9fa")
                        sub_row.pack(fill=tk.X, pady=2, padx=(10, 0))
                        
                        tk.Label(
                            sub_row,
                            text=f"📌 {sub_display}:",
                            bg="#f8f9fa",
                            font=self.FONT_BOLD,
                            width=22,
                            anchor="w"
                        ).pack(side=tk.LEFT, padx=(0, 3))
                        
                        # Data milestone
                        sub_date = ''
                        if sub_fc:
                            sub_date = self.format_date_ddmmyyyy(sub_fc.get('template_start')) or ''
                        
                        sub_entry = tk.Entry(
                            sub_row, width=12, font=self.FONT_DEFAULT,
                            disabledbackground='#f0f0f0', disabledforeground='black',
                            readonlybackground='#f0f0f0', fg='black'
                        )
                        sub_entry.insert(0, sub_date)
                        sub_entry.pack(side=tk.LEFT, padx=2)
                        if not self.have_lock:
                            sub_entry.config(state='readonly')
                        
                        # Przycisk kalendarza
                        sub_cal_btn = tk.Button(
                            sub_row,
                            text="📅",
                            command=lambda se=sub_entry: self.open_calendar_picker(se),
                            bg="#3498db",
                            fg="white",
                            font=self.FONT_SMALL,
                            padx=3,
                            pady=1,
                            state=tk.NORMAL if self.have_lock else tk.DISABLED
                        )
                        sub_cal_btn.pack(side=tk.LEFT, padx=1)
                        
                        self.timeline_entries[sub_code] = (sub_entry, sub_entry)
                        
                        # Przycisk zapisu daty
                        save_btn = tk.Button(
                            sub_row,
                            text="💾",
                            command=lambda sc=sub_code, me=sub_entry: self.save_milestone_date(sc, me.get()),
                            bg=self.COLOR_GREEN,
                            fg="white",
                            font=self.FONT_SMALL,
                            padx=4, pady=1,
                            state=tk.NORMAL if self.have_lock else tk.DISABLED
                        )
                        save_btn.pack(side=tk.LEFT, padx=3)
                        
                        # Checkbox wizualny - pusty kwadrat jeśli brak daty, wypełniony jeśli jest
                        # width=2 aby pusty i zaznaczony miały takie same wymiary (inaczej przesuwają się przyciski)
                        checkbox_icon = "☑" if sub_date else "☐"
                        tk.Label(
                            sub_row, 
                            text=checkbox_icon, 
                            bg="#f8f9fa", 
                            font=self.FONT_SMALL,
                            width=2,
                            anchor="center"
                        ).pack(side=tk.LEFT, padx=1)
                        
                        # Przycisk "Protokół" dla ODBIOR_1, ODBIOR_2, ODBIOR_3, FAT
                        if sub_code in ['ODBIOR_1', 'ODBIOR_2', 'ODBIOR_3', 'FAT']:
                            sub_att_count = self.get_stage_attachments_count(sub_code)
                            tk.Button(
                                sub_row,
                                text=f"📄 Protokół ({sub_att_count})",
                                command=lambda sc=sub_code: self.show_stage_attachments_window(sc, 'Protokół'),
                                bg=self.COLOR_ORANGE,
                                fg="white",
                                font=self.FONT_SMALL,
                                padx=6,
                                pady=1
                            ).pack(side=tk.LEFT, padx=4)
                        
                        # � URUCHOMIENIE_U_KLIENTA: combobox pracownika
                        if sub_code == 'URUCHOMIENIE_U_KLIENTA':
                            try:
                                all_employees = rmm.get_employees(self.rm_master_db_path, active_only=True)
                                employee_map = {e['id']: e['name'] for e in all_employees}
                                
                                current_employee_id = rmm.get_stage_employee_id(
                                    self.get_project_db_path(self.selected_project_id),
                                    self.selected_project_id, 'URUCHOMIENIE_U_KLIENTA'
                                )
                                
                                employee_names = [''] + [e['name'] for e in all_employees]
                                
                                tk.Label(
                                    sub_row, 
                                    text="👷", 
                                    bg="#f8f9fa",
                                    width=2,
                                    anchor="center"
                                ).pack(side=tk.LEFT, padx=(6, 2))
                                
                                employee_combo = ttk.Combobox(
                                    sub_row,
                                    values=employee_names,
                                    width=20,
                                    state='readonly' if self.have_lock else 'disabled'
                                )
                                employee_combo.pack(side=tk.LEFT, padx=2)
                                
                                # Ustaw wartość początkową PRZED bindowaniem
                                if current_employee_id and current_employee_id in employee_map:
                                    employee_combo.set(employee_map[current_employee_id])
                                
                                # Callback
                                def on_employee_selected(event,
                                                        pid=self.selected_project_id,
                                                        pdb=self.get_project_db_path(self.selected_project_id),
                                                        combo=employee_combo,
                                                        employees=all_employees,
                                                        gui_ref=self):
                                    try:
                                        selected_name = combo.get()
                                        eid = None
                                        if selected_name:
                                            for e in employees:
                                                if e['name'] == selected_name:
                                                    eid = e['id']
                                                    break
                                        
                                        rmm.set_stage_employee_id(pdb, pid, 'URUCHOMIENIE_U_KLIENTA', eid)
                                        
                                        gui_ref.status_bar.config(
                                            text=f"✅ Pracownik: {selected_name}" if selected_name else "✅ Pracownik: wyczyszczony",
                                            fg=gui_ref.COLOR_GREEN
                                        )
                                    except Exception as ex:
                                        import traceback
                                        traceback.print_exc()
                                        gui_ref.status_bar.config(
                                            text=f"🔴 Błąd zapisu pracownika: {ex}",
                                            fg=gui_ref.COLOR_RED
                                        )
                                
                                employee_combo.bind("<<ComboboxSelected>>", on_employee_selected)
                            except Exception as ex:
                                print(f"⚠️ Błąd ładowania pracowników: {ex}")
                        
                        # TRANSPORT: combobox firmy transportowej (zawsze widoczny)
                        if sub_code == 'TRANSPORT':
                            print(f"🚛 Renderuję combobox TRANSPORT (have_lock={self.have_lock}) - projekt={self.selected_project_id}, parent={stage_code}")
                            
                            # UWAGA: Sprawdź czy transport został już wyrenderowany dla tego projektu
                            # (zapobiega duplikacji jeśli TRANSPORT jest w kilku SUB_MILESTONES)
                            has_flag = hasattr(self, '_transport_rendered_for_project')
                            flag_value = getattr(self, '_transport_rendered_for_project', None)
                            print(f"🚛 DEBUG: has_flag={has_flag}, flag_value={flag_value}, current_project={self.selected_project_id}")
                            
                            if has_flag and flag_value == self.selected_project_id:
                                print(f"🚛 Transport już wyrenderowany dla projektu {self.selected_project_id} - pomijam")
                                continue
                            
                            # Ustaw flagę NATYCHMIAST aby zapobiec kolejnym renderowaniem
                            print(f"🚛 Ustawiam flagę _transport_rendered_for_project = {self.selected_project_id}")
                            self._transport_rendered_for_project = self.selected_project_id
                            print(f"🚛 Renderuję combobox TRANSPORT (have_lock={self.have_lock})")
                            current_transport_id = rmm.get_stage_transport_id(
                                self.get_project_db_path(self.selected_project_id),
                                self.selected_project_id, 'TRANSPORT'
                            )
                            print(f"🚛 Aktualny transport_id: {current_transport_id}")
                            
                            # Jeśli brak firm transportowych - pokaż komunikat
                            if not transport_companies:
                                transport_names = ['(brak firm - dodaj w menu Listy → Transport)']
                            else:
                                transport_names = [''] + [t['name'] for t in transport_companies]
                            
                            tk.Label(
                                sub_row, 
                                text="🚛", 
                                bg="#f8f9fa",
                                width=2,
                                anchor="center"
                            ).pack(side=tk.LEFT, padx=(6, 2))
                            
                            combobox_state = 'readonly' if (self.have_lock and transport_companies) else 'disabled'
                            print(f"🚛 Combobox state: {combobox_state}")
                            
                            # Stwórz combobox BEZ textvariable (to triggeruje event!)
                            transport_combo = ttk.Combobox(
                                sub_row,
                                values=transport_names,
                                width=20,
                                state=combobox_state
                            )
                            transport_combo.pack(side=tk.LEFT, padx=2)
                            
                            # Ustaw wartość początkową PRZED bindowaniem callbacku
                            if current_transport_id and current_transport_id in transport_map:
                                initial_value = transport_map[current_transport_id]
                                transport_combo.set(initial_value)
                                print(f"🚛 Ustawiam wartość początkową: {initial_value}")
                            
                            # Autozapis po wybraniu
                            def on_transport_selected(event, 
                                                      pid=self.selected_project_id,
                                                      pdb=self.get_project_db_path(self.selected_project_id),
                                                      combo=transport_combo, 
                                                      companies=transport_companies,
                                                      gui_ref=self):
                                print(f"🚛 CALLBACK wywołany! Event: {event}")
                                try:
                                    selected_name = combo.get()
                                    print(f"🚛 Wybrano z combobox: '{selected_name}'")
                                    tid = None
                                    if selected_name:  # Nie puste
                                        for t in companies:
                                            if t['name'] == selected_name:
                                                tid = t['id']
                                                break
                                    
                                    print(f"🚛 Zapisuję transport: '{selected_name}' (ID={tid}) dla projektu {pid}")
                                    rmm.set_stage_transport_id(pdb, pid, 'TRANSPORT', tid)
                                    print(f"✅ Zapis zakończony pomyślnie")
                                    
                                    # NIE odświeżaj timeline - to niszczy combobox i triggeruje callback ponownie!
                                    # Wartość jest już zapisana w bazie i widoczna w comboboxie.
                                    
                                    gui_ref.status_bar.config(
                                        text=f"✅ Transport: {selected_name}" if selected_name else "✅ Transport: wyczyszczony",
                                        fg=gui_ref.COLOR_GREEN
                                    )
                                except Exception as ex:
                                    import traceback
                                    traceback.print_exc()
                                    print(f"❌ Błąd zapisu transportu: {ex}")
                                    gui_ref.status_bar.config(
                                        text=f"🔴 Błąd zapisu transportu: {ex}",
                                        fg=gui_ref.COLOR_RED
                                    )
                            
                            print(f"🚛 Bindowanie callbacku...")
                            transport_combo.bind("<<ComboboxSelected>>", on_transport_selected)
                            print(f"🚛 Combobox TRANSPORT gotowy")
                            
                            # Flaga już ustawiona na początku renderowania
                        
                        # 📝 Przycisk notatek
                        try:
                            sub_notes_stats = rmm.get_topic_stats(
                                self.get_project_db_path(self.selected_project_id),
                                self.selected_project_id,
                                sub_code
                            )
                            sub_topic_count = sub_notes_stats['total_topics']
                            sub_notes_count = sub_notes_stats['total_notes']  # Dodaj liczbę notatek
                            sub_alarms_count = sub_notes_stats['active_alarms']
                        except Exception:
                            sub_topic_count = 0
                            sub_notes_count = 0  # Dodaj domyślną wartość
                            sub_alarms_count = 0
                        
                        # Przycisk notatek - tematy + notatki
                        if sub_topic_count > 0 or sub_notes_count > 0:
                            notes_text = f"📝 {sub_topic_count}T/{sub_notes_count}N"
                        else:
                            notes_text = "📝"
                        if sub_alarms_count > 0:
                            notes_text += f" ⏰{sub_alarms_count}"
                        
                        # Przyciski notatek zawsze aktywne (przeglądanie)
                        notes_btn = tk.Button(
                            sub_row,
                            text=notes_text,
                            command=lambda sc=sub_code: self.show_notes_window(sc),
                            bg=self.COLOR_PURPLE if sub_topic_count > 0 else "#95a5a6",
                            fg="white",
                            font=self.FONT_SMALL,
                            padx=4, pady=1
                        )
                        notes_btn.pack(side=tk.LEFT, padx=3)

            # Przywróć pozycję scrolla po przebudowie widgetów
            self.timeline_frame.update_idletasks()
            self.timeline_canvas.yview_moveto(scroll_pos[0])
            
        except Exception as e:
            error_frame = tk.Frame(self.timeline_frame, bg="white")
            error_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            tk.Label(
                error_frame,
                text=f"Błąd: {e}",
                bg="white",
                fg=self.COLOR_RED,
                font=self.FONT_DEFAULT
            ).pack()
    
    def reset_stage_to_template(self, stage_code: str):
        """Usuń actual periods dla etapu i wróć do używania template"""
        print(f"🗑️ DEBUG reset_stage_to_template: stage={stage_code}, have_lock={self.have_lock}")
        
        if not self.have_lock:
            messagebox.showwarning("Brak uprawnień", "Przejmij lock projektu aby zresetować etap")
            return
            
        # Potwierdzenie
        result = messagebox.askyesno(
            "Potwierdzenie resetu",
            f"Czy na pewno chcesz zresetować etap {stage_code}?\n\n"
            f"Operacja usunie wszystkie faktyczne daty wykonania\n"
            f"i przywróci prognozę na podstawie szablonu.\n\n"
            f"Tej operacji nie można cofnąć!"
        )
        
        if not result:
            return
            
        try:
            # Usuń actual periods
            con = rmm._open_rm_connection(self.get_project_db_path(self.selected_project_id), row_factory=False)
            
            cursor = con.execute("""
                DELETE FROM stage_actual_periods
                WHERE project_stage_id = (
                    SELECT id FROM project_stages
                    WHERE project_id = ? AND stage_code = ?
                )
            """, (self.selected_project_id, stage_code))
            
            rows_deleted = cursor.rowcount
            print(f"🗑️ Usunięto {rows_deleted} actual periods dla {stage_code}")
            
            con.commit()
            con.close()
            
            # Przelicz prognozę (teraz będzie używać template)
            rmm.recalculate_forecast(self.get_project_db_path(self.selected_project_id), self.selected_project_id)
            
            # Odśwież widoki
            self.refresh_all()
            
            self.status_bar.config(text=f"✅ Zresetowano etap {stage_code} do template", fg=self.COLOR_GREEN)
            print(f"🗑️ Reset zakończony pomyślnie")
            
        except Exception as e:
            print(f"🗑️ BŁĄD w reset_stage_to_template: {e}")
            messagebox.showerror("❌ Błąd", f"Nie można zresetować etapu:\n{e}")
            self.status_bar.config(text=f"🔴 Błąd resetu", fg=self.COLOR_RED)

    def _debug_and_save_stage_template(self, stage_code: str, template_start_entry, template_end_entry):
        """Wrapper z debuggiem dla save_stage_template"""
        ts_value = template_start_entry.get()
        te_value = template_end_entry.get()
        print(f"🔧 DEBUG KLIKNIĘCIE ZAPISZ SZABLON:")
        print(f"   - stage_code: '{stage_code}'")
        print(f"   - template_start entry value: '{ts_value}'")
        print(f"   - template_end entry value: '{te_value}'")
        print(f"   - have_lock: {self.have_lock}")
        print(f"   - selected_project_id: {self.selected_project_id}")
        
        self.save_stage_template(stage_code, ts_value, te_value)

    def save_stage_template(self, stage_code: str, template_start: str, template_end: str):
        """Zapisz zmodyfikowane daty szablonu dla etapu"""
        print(f"💾 DEBUG save_stage_template: stage={stage_code}, start='{template_start}', end='{template_end}', have_lock={self.have_lock}")
        
        if not self.have_lock:
            messagebox.showwarning("Brak uprawnień", "Przejmij lock projektu aby edytować daty")
            return
    def save_stage_template(self, stage_code: str, template_start: str, template_end: str):
        """Zapisz zmodyfikowane daty szablonu dla etapu"""
        print(f"💾 DEBUG save_stage_template: stage={stage_code}, start='{template_start}', end='{template_end}', have_lock={self.have_lock}")
        
        if not self.have_lock:
            messagebox.showwarning("Brak uprawnień", "Przejmij lock projektu aby edytować daty")
            return
            
        try:
            # Strip i zamień puste stringi na None
            template_start = template_start.strip() if template_start else ''
            template_end = template_end.strip() if template_end else ''
            print(f"💾 Po strip: start='{template_start}', end='{template_end}'")
            
            # Walidacja i konwersja DD-MM-YYYY → YYYY-MM-DD (ISO)
            valid_start, template_start_iso = self.validate_and_convert_date(template_start)
            print(f"💾 Walidacja start: valid={valid_start}, iso='{template_start_iso}'")
            if not valid_start:
                messagebox.showerror("❌ Błąd walidacji", template_start_iso)
                return
            
            valid_end, template_end_iso = self.validate_and_convert_date(template_end)
            print(f"💾 Walidacja end: valid={valid_end}, iso='{template_end_iso}'")
            if not valid_end:
                messagebox.showerror("❌ Błąd walidacji", template_end_iso)
                return
            
            # Walidacja logiczna: koniec >= początek (tylko jeśli obie daty są podane)
            if template_start_iso and template_end_iso:
                if template_end_iso < template_start_iso:
                    messagebox.showerror(
                        "❌ Błąd logiczny",
                        f"Data końcowa ({template_end}) nie może być wcześniejsza\nniż data początkowa ({template_start})!"
                    )
                    return
            print(f"💾 Walidacja logiczna OK")
            
            # UPDATE stage_schedule (zapisz w formacie ISO YYYY-MM-DD)
            db_path = self.get_project_db_path(self.selected_project_id)
            print(f"💾 Ścieżka DB: {db_path}")
            
            con = rmm._open_rm_connection(db_path, row_factory=False)
            print(f"💾 Połączenie z DB OK")
            
            cursor = con.execute("""
                UPDATE stage_schedule
                SET template_start = ?, template_end = ?
                WHERE project_stage_id = (
                    SELECT id FROM project_stages
                    WHERE project_id = ? AND stage_code = ?
                )
            """, (template_start_iso, template_end_iso, self.selected_project_id, stage_code))
            
            rows_affected = cursor.rowcount
            print(f"💾 UPDATE wykonany, rows_affected: {rows_affected}")
            
            con.commit()
            con.close()
            print(f"💾 Commit i close OK")
            
            # Przelicz prognozę
            print(f"💾 Wywołuję recalculate_forecast...")
            rmm.recalculate_forecast(db_path, self.selected_project_id)
            print(f"💾 Prognoza przeliczona")
            
            # Odśwież widoki
            print(f"💾 Wywołuję refresh_all...")
            self.refresh_all()
            print(f"💾 Refresh zakończony")
            
            # Odśwież wykresy jeśli otwarte
            if self.matplotlib_canvas:
                try:
                    self.create_embedded_gantt_chart(preserve_view=True)
                except Exception:
                    pass
            if self._is_mp_chart_open():
                try:
                    self._create_multi_project_chart_window(
                        self._mp_chart_meta['project_ids'], preserve_view=True)
                except Exception:
                    pass
            
            self.status_bar.config(text=f"✅ Zapisano szablon dla {stage_code}", fg=self.COLOR_GREEN)
            print(f"💾 Status bar ustawiony - KONIEC")
            
        except Exception as e:
            print(f"💾 BŁĄD w save_stage_template: {e}")
            messagebox.showerror("❌ Błąd", f"Nie można zapisać dat:\n{e}")
            self.status_bar.config(text=f"🔴 Błąd zapisu", fg=self.COLOR_RED)
            
        except Exception as e:
            messagebox.showerror("❌ Błąd", f"Nie można zapisać dat:\n{e}")
            self.status_bar.config(text=f"🔴 Błąd zapisu", fg=self.COLOR_RED)

    def save_milestone_date(self, stage_code: str, milestone_date: str):
        """Zapisz datę milestone (template_start = template_end)"""
        try:
            print(f"\n💾 SAVE_MILESTONE_DATE: {stage_code}, data='{milestone_date}', projekt={self.selected_project_id}")
            
            # Strip i walidacja
            milestone_date = milestone_date.strip() if milestone_date else ''
            print(f"   Po strip: '{milestone_date}'")
            
            # Walidacja i konwersja DD-MM-YYYY → YYYY-MM-DD (ISO)
            valid, milestone_date_iso = self.validate_and_convert_date(milestone_date)
            print(f"   Walidacja: valid={valid}, ISO='{milestone_date_iso}'")
            
            if not valid:
                print(f"   ❌ Błąd walidacji daty: {milestone_date_iso}")
                messagebox.showerror("❌ Błąd walidacji", milestone_date_iso)
                return
            
            project_db_path = self.get_project_db_path(self.selected_project_id)
            print(f"   🗂️ Otwieranie bazy: {project_db_path}")
            
            con = rmm._open_rm_connection(project_db_path, row_factory=False)
            
            # Sprawdź czy rekord w stage_schedule istnieje
            print(f"   🔍 Sprawdzam czy rekord w stage_schedule istnieje dla {stage_code}...")
            cursor = con.execute("""
                SELECT ss.id, ss.template_start, ss.template_end 
                FROM stage_schedule ss
                JOIN project_stages ps ON ss.project_stage_id = ps.id
                WHERE ps.project_id = ? AND ps.stage_code = ?
            """, (self.selected_project_id, stage_code))
            
            existing = cursor.fetchone()
            if existing:
                print(f"   📋 Istniejący rekord w stage_schedule:")
                print(f"      ID: {existing[0]}")
                print(f"      template_start: {existing[1]}")
                print(f"      template_end: {existing[2]}")
            else:
                print(f"   📋 Brak rekordu w stage_schedule dla {stage_code}")
                
                # Sprawdź czy w ogóle istnieje projekt_stage
                cursor2 = con.execute("""
                    SELECT id FROM project_stages 
                    WHERE project_id = ? AND stage_code = ?
                """, (self.selected_project_id, stage_code))
                
                stage_row = cursor2.fetchone()
                if stage_row:
                    print(f"   ✅ project_stages.id = {stage_row[0]} istnieje")
                else:
                    print(f"   ❌ Brak rekordu w project_stages dla {stage_code}!")
                    con.close()
                    messagebox.showerror("❌ Błąd", f"Etap {stage_code} nie istnieje w project_stages")
                    return
            
            if existing:
                # UPDATE istniejącego rekordu
                cursor = con.execute("""
                    UPDATE stage_schedule
                    SET template_start = ?, template_end = ?
                    WHERE project_stage_id = (
                        SELECT id FROM project_stages
                        WHERE project_id = ? AND stage_code = ?
                    )
                """, (milestone_date_iso, milestone_date_iso, self.selected_project_id, stage_code))
                
                rows_affected = cursor.rowcount
                print(f"   💾 UPDATE wykonany, rows_affected: {rows_affected}")
            else:
                # INSERT nowego rekordu
                print(f"   💾 Rekord nie istnieje - tworzę nowy")
                
                # Znajdź project_stage_id
                cursor = con.execute("""
                    SELECT id FROM project_stages
                    WHERE project_id = ? AND stage_code = ?
                """, (self.selected_project_id, stage_code))
                
                stage_row = cursor.fetchone()
                if not stage_row:
                    print(f"   ❌ Nie znaleziono project_stage dla {stage_code}!")
                    con.close()
                    messagebox.showerror("❌ Błąd", f"Etap {stage_code} nie istnieje w project_stages")
                    return
                
                project_stage_id = stage_row[0]
                print(f"   📋 project_stage_id: {project_stage_id}")
                
                cursor = con.execute("""
                    INSERT INTO stage_schedule (project_stage_id, template_start, template_end)
                    VALUES (?, ?, ?)
                """, (project_stage_id, milestone_date_iso, milestone_date_iso))
                
                rows_affected = cursor.rowcount
                print(f"   💾 INSERT wykonany, rows_affected: {rows_affected}")
            
            con.commit()
            con.close()
            print(f"   💾 Commit i close OK")
            
            if rows_affected == 0:
                print(f"   ⚠️ UWAGA: Brak wpływu na bazę (rows_affected=0)")
                messagebox.showwarning("⚠️ Uwaga", 
                    f"Nie zaktualizowano żadnych rekordów dla {stage_code}.\n"
                    f"Možliwe że brak rekordu w stage_schedule.\n\n"
                    f"Sprawdź diagnostykę milestone'ów.")
                return
            
            # Przelicz prognozę
            print(f"   🔄 Wywołuję recalculate_forecast...")
            rmm.recalculate_forecast(project_db_path, self.selected_project_id)
            print(f"   🔄 Prognoza przeliczona")
            
            # Odśwież widoki
            print(f"   🔄 Odświeżam widoki...")
            self.refresh_all()
            
            # Odśwież wykresy jeśli otwarte
            if self.matplotlib_canvas:
                try:
                    self.create_embedded_gantt_chart(preserve_view=True)
                except Exception:
                    pass
            if self._is_mp_chart_open():
                try:
                    self._create_multi_project_chart_window(
                        self._mp_chart_meta['project_ids'], preserve_view=True)
                except Exception:
                    pass
            
            print(f"   ✅ Sukces - milestone {stage_code} zapisany z datą {milestone_date_iso}")
            self.status_bar.config(text=f"✅ Zapisano datę milestone {stage_code}", fg=self.COLOR_GREEN)
            
        except Exception as e:
            print(f"   🔥 Exception w save_milestone_date: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("❌ Błąd", f"Nie można zapisać daty milestone:\n{e}")
            self.status_bar.config(text=f"🔴 Błąd zapisu", fg=self.COLOR_RED)

    def assign_staff_dialog(self, stage_code: str):
        """Okno przypisywania pracowników do etapu (przeglądanie + edycja gdy lock).
        
        Prosty wybór z listy wszystkich pracowników + wyświetlanie kategorii.
        Zapisuje employee_id + timestamp w kolumnie assigned_staff (JSON).
        """
        if not self.selected_project_id:
            messagebox.showwarning("Uwaga", "Brak wybranego projektu.")
            return
        
        # Pobierz nazwę etapu
        con = rmm._open_rm_connection(self.get_project_db_path(self.selected_project_id))
        stage_info = con.execute(
            "SELECT display_name FROM stage_definitions WHERE code = ?",
            (stage_code,)
        ).fetchone()
        con.close()
        
        stage_display = stage_info['display_name'] if stage_info else stage_code
        
        # Okno dialogowe
        dlg = tk.Toplevel(self.root)
        dlg.transient(self.root)  # Okno na tym samym ekranie co główna aplikacja
        can_edit = self.have_lock and not self.read_only_mode
        title_suffix = " (READ-ONLY)" if not can_edit else ""
        dlg.title(f"👷 Pracownicy: {stage_display}{title_suffix}")
        dlg.resizable(True, True)
        self._center_window(dlg, 700, 500)
        
        # Nagłówek
        header = tk.Label(dlg, text=f"PRZYPISZ PRACOWNIKÓW\n{stage_display}",
                         bg=self.COLOR_TOPBAR, fg="white", font=self.FONT_BOLD, pady=10)
        header.pack(fill=tk.X)
        
        # Główny frame z listami
        main_frame = tk.Frame(dlg)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Lewa strona: dostępni pracownicy
        left_frame = tk.LabelFrame(main_frame, text="Dostępni pracownicy", font=self.FONT_BOLD)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Listbox z pracownikami (wszystkimi, aktywni + nieaktywni)
        available_list = tk.Listbox(left_frame, font=self.FONT_DEFAULT, selectmode=tk.SINGLE)
        available_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Scrollbar
        scrollbar_avail = ttk.Scrollbar(available_list, orient=tk.VERTICAL, command=available_list.yview)
        scrollbar_avail.pack(side=tk.RIGHT, fill=tk.Y)
        available_list.config(yscrollcommand=scrollbar_avail.set)
        
        # Pobierz wszystkich pracowników
        all_employees = rmm.get_employees(self.rm_master_db_path, active_only=False)
        
        # Sortuj: preferowane kategorie na górze
        preferred_categories = rmm.STAGE_TO_PREFERRED_CATEGORY.get(stage_code, [])
        
        def sort_key(emp):
            # Preferowane kategorie idą na górę
            if emp['category'] in preferred_categories:
                return (0, emp['category'], emp['name'])
            else:
                return (1, emp['category'], emp['name'])
        
        all_employees.sort(key=sort_key)
        
        # Wypełnij listę
        employee_map = {}  # index → employee dict
        for idx, emp in enumerate(all_employees):
            is_preferred = emp['category'] in preferred_categories
            prefix = "⭐ " if is_preferred else "   "
            suffix = " (nieaktywny)" if not emp['is_active'] else ""
            display = f"{prefix}{emp['name']} - {emp['category']}{suffix}"
            available_list.insert(tk.END, display)
            employee_map[idx] = emp
        
        # Prawa strona: przypisani pracownicy
        right_frame = tk.LabelFrame(main_frame, text="Przypisani do tego etapu", font=self.FONT_BOLD)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        assigned_list = tk.Listbox(right_frame, font=self.FONT_DEFAULT, selectmode=tk.SINGLE)
        assigned_list.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        scrollbar_assigned = ttk.Scrollbar(assigned_list, orient=tk.VERTICAL, command=assigned_list.yview)
        scrollbar_assigned.pack(side=tk.RIGHT, fill=tk.Y)
        assigned_list.config(yscrollcommand=scrollbar_assigned.set)
        
        def refresh_assigned():
            """Odśwież listę przypisanych pracowników."""
            assigned_list.delete(0, tk.END)
            try:
                assigned_staff = rmm.get_stage_assigned_staff(
                    self.get_project_db_path(self.selected_project_id),
                    self.rm_master_db_path,
                    self.selected_project_id,
                    stage_code
                )
                
                for s in assigned_staff:
                    name = s['employee_name']
                    category = s['category']
                    assigned_at = s.get('assigned_at', '')
                    
                    # Sprawdź czy kategoria pasuje
                    if category not in preferred_categories:
                        display = f"⚠️ {name} ({category}) - {assigned_at}"
                    else:
                        display = f"👤 {name} ({category}) - {assigned_at}"
                    
                    assigned_list.insert(tk.END, display)
                    # Przechowaj employee_id w hidden attribute (hack przez itemconfig - nie działa w Listbox)
                    # Użyjemy employee_map z indeksem
                    assigned_list.insert(tk.END, "")  # placeholder dla employee_id
                    assigned_list.delete(tk.END)  # usuń placeholder
                    # Zamiast tego przechowamy mapę employee_id
            
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można pobrać listy przypisanych:\n{e}", parent=dlg)
        
        refresh_assigned()
        
        # Przyciski akcji (w środku)
        button_frame = tk.Frame(main_frame)
        button_frame.pack(side=tk.LEFT, padx=10)
        
        def add_selected():
            """Dodaj wybranego pracownika."""
            if not self.have_lock:
                messagebox.showwarning(
                    "Brak uprawnień",
                    "Aby przypisać pracowników, musisz mieć lock projektu.\n\n"
                    "Kliknij 'Weź lock' w menu Projekt.",
                    parent=dlg
                )
                return
            
            sel = available_list.curselection()
            if not sel:
                messagebox.showwarning("Uwaga", "Wybierz pracownika z listy.", parent=dlg)
                return
            
            idx = sel[0]
            emp = employee_map[idx]
            
            try:
                success = rmm.add_staff_to_stage(
                    self.get_project_db_path(self.selected_project_id),
                    self.rm_master_db_path,
                    self.selected_project_id,
                    stage_code,
                    emp['id'],
                    self.current_user
                )
                
                if success:
                    refresh_assigned()
                    self.status_bar.config(
                        text=f"✅ Przypisano {emp['name']} do {stage_display}",
                        fg=self.COLOR_GREEN
                    )
                    # Odśwież timeline aby pokazać badge
                    self.refresh_timeline()
                else:
                    messagebox.showerror(
                        "Błąd",
                        f"Nie można przypisać pracownika - nieoczekiwany błąd.",
                        parent=dlg
                    )
            
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można przypisać pracownika:\n{e}", parent=dlg)
        
        def remove_selected():
            """Usuń wybranego pracownika z przypisanych."""
            if not self.have_lock:
                messagebox.showwarning(
                    "Brak uprawnień",
                    "Aby usunąć pracowników, musisz mieć lock projektu.",
                    parent=dlg
                )
                return
            
            sel = assigned_list.curselection()
            if not sel:
                messagebox.showwarning("Uwaga", "Wybierz pracownika do usunięcia.", parent=dlg)
                return
            
            idx = sel[0]
            # Musimy znaleźć employee_id - pobierzmy ponownie listę
            try:
                assigned_staff = rmm.get_stage_assigned_staff(
                    self.get_project_db_path(self.selected_project_id),
                    self.rm_master_db_path,
                    self.selected_project_id,
                    stage_code
                )
                
                if idx >= len(assigned_staff):
                    return
                
                emp_id = assigned_staff[idx]['employee_id']
                emp_name = assigned_staff[idx]['employee_name']
                
                if not messagebox.askyesno(
                    "Potwierdzenie",
                    f"Usunąć {emp_name} z etapu {stage_display}?",
                    parent=dlg
                ):
                    return
                
                success = rmm.remove_staff_from_stage(
                    self.get_project_db_path(self.selected_project_id),
                    self.selected_project_id,
                    stage_code,
                    emp_id
                )
                
                if success:
                    refresh_assigned()
                    self.status_bar.config(
                        text=f"✅ Usunięto {emp_name} z {stage_display}",
                        fg=self.COLOR_GREEN
                    )
                    # Odśwież timeline
                    self.refresh_timeline()
                
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można usunąć pracownika:\n{e}", parent=dlg)
        
        tk.Button(
            button_frame,
            text="➡️\nDodaj",
            command=add_selected,
            bg=self.COLOR_GREEN,
            fg="white",
            font=self.FONT_DEFAULT,
            width=8,
            height=3
        ).pack(pady=5)
        
        tk.Button(
            button_frame,
            text="⬅️\nUsuń",
            command=remove_selected,
            bg=self.COLOR_RED,
            fg="white",
            font=self.FONT_DEFAULT,
            width=8,
            height=3
        ).pack(pady=5)
        
        # Stopka z informacją
        info_frame = tk.Frame(dlg, bg="#f0f0f0")
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        info_text = (
            "ℹ️ Preferowane kategorie dla tego etapu: " +
            ", ".join(preferred_categories) if preferred_categories else "Brak"
        )
        
        tk.Label(
            info_frame,
            text=info_text,
            bg="#f0f0f0",
            font=self.FONT_SMALL,
            fg="gray",
            wraplength=650,
            justify=tk.LEFT
        ).pack(padx=5, pady=5)
        
        # Przycisk Zamknij
        tk.Button(
            dlg,
            text="Zamknij",
            command=dlg.destroy,
            font=self.FONT_DEFAULT,
            padx=20,
            pady=5
        ).pack(pady=10)

    def save_all_templates(self):
        """Zapisz wszystkie niezapisane zmiany z timeline przed zwolnieniem locka"""
        if not self.selected_project_id or not self.timeline_entries:
            return
        
        try:
            con = rmm._open_rm_connection(self.get_project_db_path(self.selected_project_id), row_factory=False)
            saved_count = 0
            errors = []  # Zbieraj błędy, aby pokazać użytkownikowi
            
            for stage_code, (start_entry, end_entry) in self.timeline_entries.items():
                try:
                    template_start = start_entry.get().strip()
                    template_end = end_entry.get().strip()
                    
                    # Walidacja i konwersja DD-MM-YYYY → YYYY-MM-DD (ISO)
                    valid_start, template_start_iso = self.validate_and_convert_date(template_start)
                    if not valid_start:
                        errors.append(f"{stage_code}: {template_start_iso}")
                        continue
                    
                    valid_end, template_end_iso = self.validate_and_convert_date(template_end)
                    if not valid_end:
                        errors.append(f"{stage_code}: {template_end_iso}")
                        continue
                    
                    # Walidacja logiczna: koniec >= początek (tylko jeśli obie daty są podane)
                    if template_start_iso and template_end_iso:
                        if template_end_iso < template_start_iso:
                            errors.append(f"{stage_code}: Data końcowa nie może być wcześniejsza niż początkowa")
                            continue
                    
                    # UPDATE stage_schedule - zapisz w formacie ISO (YYYY-MM-DD)
                    con.execute("""
                        UPDATE stage_schedule
                        SET template_start = ?, template_end = ?
                        WHERE project_stage_id = (
                            SELECT id FROM project_stages
                            WHERE project_id = ? AND stage_code = ?
                        )
                    """, (template_start_iso, template_end_iso, self.selected_project_id, stage_code))
                    saved_count += 1
                    
                except Exception as e:
                    print(f"⚠️ Błąd zapisu szablonu {stage_code}: {e}")
                    continue
            
            con.commit()
            con.close()
            
            # Pokaż błędy użytkownikowi jeśli były
            if errors:
                messagebox.showwarning(
                    "⚠️ Błędy walidacji dat",
                    f"Nie można zapisać dat dla niektórych etapów:\n\n" + "\n".join(errors) +
                    f"\n\nZapisano poprawne: {saved_count}/{len(self.timeline_entries)}"
                )
            
        except Exception as e:
            messagebox.showerror("❌ Błąd", f"Błąd zapisu szablonów: {e}")
    
    def _scroll_timeline_to_stage(self, stage_code):
        """Przewiń oś czasu do danego etapu"""
        try:
            self.timeline_frame.update_idletasks()
            self.timeline_canvas.configure(scrollregion=self.timeline_canvas.bbox("all"))
            for widget in self.timeline_frame.winfo_children():
                if isinstance(widget, tk.LabelFrame) and getattr(widget, '_stage_code', None) == stage_code:
                    widget_y = widget.winfo_y()
                    scroll_region = self.timeline_canvas.bbox("all")
                    if scroll_region:
                        total_height = scroll_region[3]
                        canvas_height = self.timeline_canvas.winfo_height()
                        if total_height > canvas_height:
                            fraction = max(0.0, min(1.0, widget_y / total_height))
                            self.timeline_canvas.yview_moveto(fraction)
                    return
        except Exception:
            pass

    def refresh_dashboard(self):
        """Odśwież dashboard"""
        if not self.selected_project_id:
            return
        
        try:
            _pdb = self.get_project_db_path(self.selected_project_id)
            summary = rmm.get_project_status_summary(_pdb, self.selected_project_id)
            critical = rmm.calculate_critical_path(_pdb, self.selected_project_id)
            
            # Zapisz pozycję scrolla przed odświeżeniem
            scroll_pos = self.dashboard_text.yview()
            
            # Odblokuj na czas edycji
            self.dashboard_text.config(state='normal')
            self.dashboard_text.delete('1.0', tk.END)
            self.dashboard_text.insert(tk.END, "=" * 100 + "\n")
            project_name = self.project_names.get(self.selected_project_id, f'Projekt {self.selected_project_id}')
            self.dashboard_text.insert(tk.END, f"PODSUMOWANIE - {project_name}\n")
            self.dashboard_text.insert(tk.END, "=" * 100 + "\n\n")
            
            # Status
            status = summary['status']
            if status == 'DELAYED':
                status_icon = "🔴"
                status_pl = "OPÓŹNIONY"
            elif status == 'AT_RISK':
                status_icon = "🟡"
                status_pl = "ZAGROŻONY"
            else:
                status_icon = "🟢"
                status_pl = "ZGODNIE Z PLANEM"
            
            self.dashboard_text.insert(tk.END, f"Status projektu:        {status_icon} {status_pl}\n\n")
            
            # Variance
            var_days = summary['overall_variance_days']
            var_icon = "⚠️" if var_days > 0 else "✅"
            self.dashboard_text.insert(tk.END, f"Odchylenie (całkowite): {var_days:+d} dni {var_icon}\n")
            
            # Completion - format do DD-MM-YYYY
            completion = summary['completion_forecast']
            completion_fmt = self.format_date_ddmmyyyy(completion) if completion else 'N/A'
            self.dashboard_text.insert(tk.END, f"Przewidywane zakończ.:  {completion_fmt}\n\n")
            
            # Active stages
            active = summary['active_stages']
            self.dashboard_text.insert(tk.END, f"Aktywne etapy:          {', '.join(active) if active else 'Brak'}\n")
            
            # Kompletacja - % odebranych i ilość pozycji
            if self.received_percent and self.received_percent != "?":
                self.dashboard_text.insert(tk.END, f"Kompletacja BOM:        📦 {self.received_percent}\n")
            
            # Pause status
            if summary.get('is_paused'):
                self.dashboard_text.insert(tk.END, f"Pauza:                  ⏸️  PROJEKT WSTRZYMANY\n")
            self.dashboard_text.insert(tk.END, "\n")
            
            # Pause history
            pauses = summary.get('pauses', [])
            if pauses:
                self.dashboard_text.insert(tk.END, "=" * 100 + "\n")
                self.dashboard_text.insert(tk.END, "HISTORIA PAUZ:\n")
                self.dashboard_text.insert(tk.END, "=" * 100 + "\n")
                self.dashboard_text.insert(tk.END, f"  {'#':<4} {'Początek':>12}  {'Koniec':>12}  {'Czas trwania':>14}  {'Powód'}\n")
                self.dashboard_text.insert(tk.END, "  " + "-" * 80 + "\n")
                for i, p in enumerate(reversed(pauses), 1):
                    p_start = self.format_date_ddmmyyyy(p.get('start_at')) or '—'
                    p_end = self.format_date_ddmmyyyy(p.get('end_at')) or 'TRWA'
                    reason = p.get('reason') or '—'
                    # Czas trwania
                    if p.get('end_at') and p.get('start_at'):
                        try:
                            dt_start = datetime.fromisoformat(p['start_at'])
                            dt_end = datetime.fromisoformat(p['end_at'])
                            delta = dt_end - dt_start
                            days = delta.days
                            hours = delta.seconds // 3600
                            if days > 0:
                                duration = f"{days}d {hours:02d}h"
                            else:
                                minutes = (delta.seconds % 3600) // 60
                                duration = f"{hours:02d}h {minutes:02d}m"
                        except Exception:
                            duration = "N/A"
                    else:
                        duration = "TRWA"
                    self.dashboard_text.insert(tk.END,
                        f"  {i:<4} {p_start:>12}  {p_end:>12}  {duration:>14}  {reason}\n"
                    )
                self.dashboard_text.insert(tk.END, "\n")
            
            # Progress table
            self.dashboard_text.insert(tk.END, "=" * 100 + "\n")
            self.dashboard_text.insert(tk.END, "POSTĘP ETAPÓW:\n")
            self.dashboard_text.insert(tk.END, "=" * 100 + "\n")
            forecast = rmm.recalculate_forecast(_pdb, self.selected_project_id)
            details = rmm.get_critical_path_details(_pdb, self.selected_project_id)
            n_critical = sum(1 for d in details if d['is_critical'] and d['stage_code'] not in _CHILD_MILESTONE_CODES)
            
            # Pobierz is_milestone dla wszystkich etapów
            con_dash = rmm._open_rm_connection(_pdb)
            cursor_ms = con_dash.execute("SELECT code, is_milestone FROM stage_definitions")
            stage_is_milestone = {row['code']: bool(row['is_milestone']) for row in cursor_ms.fetchall()}
            con_dash.close()
            
            self.dashboard_text.insert(tk.END, f"  {'Etap'.ljust(16)}{'Status'.ljust(18)}{'Plan start'.ljust(14)}{'Plan koniec'.ljust(14)}{'Odchylenie'}\n")
            self.dashboard_text.insert(tk.END, "  " + "-" * 72 + "\n")
            stage_sort = {code: idx for idx, code in enumerate(DEFAULT_STAGE_SEQUENCE)}
            if 'ELEKTROMONTAZ' in stage_sort:
                stage_sort.setdefault('AUTOMATYKA', stage_sort['ELEKTROMONTAZ'])
            details.sort(key=lambda d: stage_sort.get(d['stage_code'], 999))
            for d in details:
                # Pomiń sub-milestones - są wyświetlane jako punkty kontrolne w ramach ODBIORY na osi czasu
                if d['stage_code'] in _CHILD_MILESTONE_CODES:
                    continue
                
                fc = forecast.get(d['stage_code'], {})
                is_ms = stage_is_milestone.get(d['stage_code'], False)
                is_active = fc.get('is_active', False)
                is_actual = fc.get('is_actual', False)
                if is_active:
                    status_str = "● TRWA"
                elif is_actual:
                    status_str = "✓ Ustawiony" if is_ms else "✓ Zakończony"
                else:
                    status_str = "○ Oczekuje"
                variance = fc.get('variance_days', 0)
                if variance > 0 and is_actual:
                    var_str = f"✓ +{variance}d"          # Zakończony z opóźnieniem (nic nie zrobisz)
                elif variance > 0:
                    var_str = f"+{variance}d ⚠"           # Opóźnienie (aktywny/oczekujący)
                elif variance < 0:
                    var_str = f"{variance}d ✅"            # Przed czasem
                else:
                    var_str = "—"                          # W terminie
                
                # Milestone: jedna data (actual lub template), zwykły etap: okres
                if is_ms:
                    # Dla milestone użyj actual jeśli jest, inaczej template
                    if fc.get('actual_periods'):
                        ms_date = fc['actual_periods'][0].get('started_at')
                    else:
                        ms_date = fc.get('template_start')
                    ms_date_fmt = self.format_date_ddmmyyyy(ms_date) if ms_date else '—'
                    t_start = ms_date_fmt
                    t_end = '—'  # Milestone nie ma "końca" (instant)
                else:
                    # Zwykły etap: pokazuj okres
                    t_start = self.format_date_ddmmyyyy(fc.get('template_start')) or '—'
                    t_end = self.format_date_ddmmyyyy(fc.get('template_end')) or '—'
                
                self.dashboard_text.insert(tk.END,
                    f"  {d['stage_code'].ljust(16)}{status_str.ljust(18)}{t_start.ljust(14)}{t_end.ljust(14)}{var_str}\n"
                )
            self.dashboard_text.insert(tk.END, "\n")
            if n_critical == len(details):
                self.dashboard_text.insert(tk.END,
                    "  ℹ Projekt liniowy — każde opóźnienie etapu przesuwa termin projektu.\n"
                    "    Szczegóły CPM (rezerwy): Narzędzia → Ścieżka krytyczna.\n"
                )
            else:
                self.dashboard_text.insert(tk.END,
                    f"  Etapów bez rezerwy: {n_critical} z {len(details)} (opóźnienie → opóźnia projekt).\n"
                    "  Szczegóły CPM: Narzędzia → Ścieżka krytyczna.\n"
                )
            
            # Zablokuj po edycji
            self.dashboard_text.config(state='disabled')
            
            # Przywróć pozycję scrolla
            self.dashboard_text.yview_moveto(scroll_pos[0])
            
        except Exception as e:
            self.dashboard_text.config(state='normal')
            self.dashboard_text.delete('1.0', tk.END)
            self.dashboard_text.insert(tk.END, f"Błąd: {e}")
            self.dashboard_text.config(state='disabled')
    
    def refresh_history(self):
        """Odśwież historię okresów"""
        if not self.selected_project_id:
            return
        
        # Zapisz pozycję scrolla przed odświeżeniem
        scroll_pos = self.history_tree.yview()
        
        # Wyczyść
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        
        try:
            con = rmm._open_rm_connection(self.get_project_db_path(self.selected_project_id))
            
            cursor = con.execute("""
                SELECT ps.stage_code, sap.started_at, sap.ended_at, sap.started_by, sap.ended_by
                FROM stage_actual_periods sap
                JOIN project_stages ps ON sap.project_stage_id = ps.id
                WHERE ps.project_id = ?
                ORDER BY ps.sequence ASC, sap.started_at ASC
            """, (self.selected_project_id,))
            
            for row in cursor.fetchall():
                stage = row['stage_code']
                started = self.format_datetime(row['started_at'])
                ended = self.format_datetime(row['ended_at']) if row['ended_at'] else "TRWA"
                
                # Oblicz czas trwania
                if row['ended_at']:
                    try:
                        start_dt = datetime.fromisoformat(row['started_at'])
                        end_dt = datetime.fromisoformat(row['ended_at'])
                        duration_delta = end_dt - start_dt
                        # Format: X dni, HH:MM
                        days = duration_delta.days
                        hours, remainder = divmod(duration_delta.seconds, 3600)
                        minutes, _ = divmod(remainder, 60)
                        if days > 0:
                            duration = f"{days}d {hours:02d}:{minutes:02d}"
                        else:
                            duration = f"{hours:02d}:{minutes:02d}"
                    except:
                        duration = "N/A"
                else:
                    duration = "TRWA"
                
                status = "Zakończony" if row['ended_at'] else "Aktywny"
                
                self.history_tree.insert('', tk.END, values=(stage, started, ended, duration, status))
            
            con.close()
            
            # Przywróć pozycję scrolla
            self.history_tree.yview_moveto(scroll_pos[0])
        
        except Exception as e:
            print(f"Error loading history: {e}")
    
    def force_reload_projects(self):
        """Wymuś ponowne załadowanie listy projektów z diagnostyką"""
        current_selection = self.selected_project_id
        self.selected_project_id = None
        
        print("📋 Wymuszam odświeżenie listy projektów...")
        print(f"   Master DB: {self.master_db_path}")
        print(f"   RM Projects Dir: {self.rm_projects_dir}")
        
        self.load_projects()
        
        # Przywróć selekcję jeśli możliwe
        if current_selection and current_selection in self.projects:
            try:
                idx = self.projects.index(current_selection)
                self.project_combo.current(idx)
                self.on_project_selected(None)
                print(f"✅ Przywrócono wybór projektu {current_selection}")
            except (ValueError, IndexError):
                print(f"⚠️ Nie można przywrócić projektu {current_selection}")
        
        messagebox.showinfo(
            "🔄 Odświeżono",
            f"Lista projektów została ponownie załadowana.\nZnaleziono: {len(self.projects)} projektów"
        )
    
    def refresh_all(self):
        """Odśwież wszystko"""
        if self.selected_project_id:
            self.load_project_stages()
            self.refresh_timeline()
            self.refresh_dashboard()
            self.refresh_history()
    
    # ========================================================================
    # Menu actions
    # ========================================================================
    
    def auto_sync_to_master(self):
        """Automatyczna synchronizacja z RM_BAZA (bez komunikatów)"""
        if not self.selected_project_id:
            return
        
        if not os.path.exists(self.master_db_path):
            return
        
        try:
            rmm.sync_to_master(self.get_project_db_path(self.selected_project_id), self.master_db_path, self.selected_project_id)
            print(f"🔄 Auto-sync: projekt {self.selected_project_id} → master.sqlite")
        except Exception as e:
            print(f"⚠️ Auto-sync błąd: {e}")
    
    def edit_config(self):
        """Dialog edycji konfiguracji ścieżek"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Konfiguracja ścieżek")
        dialog.transient(self.root)
        dialog.grab_set()
        self._center_window(dialog, 780, 620)

        header = tk.Label(
            dialog,
            text="KONFIGURACJA ŚCIEŻEK",
            bg=self.COLOR_TOPBAR, fg="white",
            font=("Arial", 12, "bold"), pady=8
        )
        header.pack(fill=tk.X)

        form = tk.Frame(dialog, padx=15, pady=10)
        form.pack(fill=tk.BOTH, expand=True)

        def make_row(parent, row, label, hint, default_val, browse_cmd):
            tk.Label(parent, text=label, font=self.FONT_BOLD, anchor="w", width=22).grid(
                row=row * 2, column=0, sticky="w", pady=(8, 0))
            entry = tk.Entry(parent, font=self.FONT_DEFAULT, width=52)
            entry.insert(0, default_val)
            entry.grid(row=row * 2, column=1, padx=5, sticky="ew", pady=(8, 0))
            tk.Button(parent, text="📂", command=lambda e=entry: browse_cmd(e),
                      bg=self.COLOR_PURPLE, fg="white", font=self.FONT_BOLD, padx=6
                      ).grid(row=row * 2, column=2, padx=5, pady=(8, 0))
            tk.Label(parent, text=hint, font=("Arial", 8), fg="#7f8c8d", anchor="w").grid(
                row=row * 2 + 1, column=1, sticky="w", padx=5)
            return entry

        def browse_file(entry):
            path = filedialog.askopenfilename(
                title="Wybierz plik .sqlite",
                filetypes=[("SQLite Database", "*.sqlite"), ("Wszystkie pliki", "*.*")],
                initialdir=os.path.dirname(entry.get()) if os.path.dirname(entry.get()) else "."
            )
            if path:
                entry.delete(0, tk.END)
                entry.insert(0, path)

        def browse_folder(entry):
            path = filedialog.askdirectory(
                title="Wybierz folder",
                initialdir=entry.get() if os.path.isdir(entry.get()) else "."
            )
            if path:
                entry.delete(0, tk.END)
                entry.insert(0, path)

        form.columnconfigure(1, weight=1)
        e_master   = make_row(form, 0, "master.sqlite (RM_BAZA):",
                              "Wspólna baza projektów RM_BAZA  (np. Y:/RM_BAZA/master.sqlite)",
                              self.master_db_path, browse_file)
        e_projects = make_row(form, 1, "Folder projektów RM_BAZA:",
                              "Folder z plikami project_6.sqlite, project_7.sqlite itd.  (np. Y:/RM_BAZA)",
                              self.projects_path, browse_folder)
        e_rm_dir   = make_row(form, 2, "Folder RM_MANAGER:",
                              "Folder główny RM_MANAGER (master baza + LOCKS)  (np. Y:/RM_MANAGER)",
                              self.rm_manager_dir, browse_folder)
        e_rm_db    = make_row(form, 3, "rm_manager.sqlite:",
                              "Główna baza RM_MANAGER z definicjami etapów  (np. Y:/RM_MANAGER/rm_manager.sqlite)",
                              self.rm_master_db_path, browse_file)
        e_rm_proj  = make_row(form, 4, "Folder projektów RM_MANAGER:",
                              "Per-projekt bazy (rm_manager_project_1.sqlite itd.)  (np. Y:/RM_MANAGER_projects)",
                              self.rm_projects_dir, browse_folder)
        e_backup   = make_row(form, 5, "Folder backupów:",
                              "Katalog na backupy (rotacja 30 dni)  (np. Y:/RM_MANAGER/backups)",
                              self.backup_dir, browse_folder)
        e_locks    = make_row(form, 6, "Folder locków:",
                              "Katalog locków projektów  (np. Y:/RM_MANAGER/RM_MANAGER_projects/LOCKS)",
                              self.locks_dir, browse_folder)

        def save_and_close():
            self.master_db_path    = e_master.get().strip()
            self.projects_path     = e_projects.get().strip()
            self.rm_manager_dir    = e_rm_dir.get().strip()
            self.rm_master_db_path = e_rm_db.get().strip() or os.path.join(self.rm_manager_dir, 'rm_manager.sqlite')
            self.rm_projects_dir   = e_rm_proj.get().strip() or os.path.join(os.path.dirname(self.rm_manager_dir), 'RM_MANAGER_projects')
            self.backup_dir        = e_backup.get().strip() or os.path.join(os.path.dirname(self.rm_manager_dir), 'backups')
            self.locks_dir         = e_locks.get().strip() or os.path.join(self.rm_projects_dir, 'LOCKS')
            # Utwórz katalog locków jeśli nie istnieje
            Path(self.locks_dir).mkdir(parents=True, exist_ok=True)
            # Utwórz katalog projektów jeśli nie istnieje
            Path(self.rm_projects_dir).mkdir(parents=True, exist_ok=True)
            # Utwórz katalog backupów jeśli nie istnieje
            Path(self.backup_dir).mkdir(parents=True, exist_ok=True)
            # Zaktualizuj lock_manager na nowy folder LOCKS
            if hasattr(self.lock_manager, 'locks_folder') and self.lock_manager.locks_folder is not None:
                self.lock_manager.locks_folder = Path(self.locks_dir)
                self.lock_manager.locks_folder.mkdir(parents=True, exist_ok=True)
            # Zaktualizuj backup_manager na nowy folder backupów
            if self.backup_manager:
                self.backup_manager.backup_dir = Path(self.backup_dir)
                self.backup_manager.projects_dir = Path(self.rm_projects_dir)
                self.backup_manager.master_backup_dir = Path(self.backup_dir) / "master"
                self.backup_manager.projects_backup_dir = Path(self.backup_dir) / "projects"
                self.backup_manager.master_backup_dir.mkdir(parents=True, exist_ok=True)
                self.backup_manager.projects_backup_dir.mkdir(parents=True, exist_ok=True)
                # Wykryj ponownie wzorzec nazewniczy
                if list(Path(self.rm_projects_dir).glob("rm_manager_project_*.sqlite")):
                    self.backup_manager.project_name_pattern = "rm_manager_project_{id}.sqlite"
                else:
                    self.backup_manager.project_name_pattern = "project_{id}.sqlite"
            self.save_config()
            dialog.destroy()
            self.status_bar.config(text="📂 Konfiguracja zapisana", fg="#27ae60")
            self.load_projects()

        btn_frame = tk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=15, pady=10)
        tk.Button(btn_frame, text="💾 Zapisz", command=save_and_close,
                  bg=self.COLOR_GREEN, fg="white", font=self.FONT_BOLD, padx=20, pady=6
                  ).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="❌ Anuluj", command=dialog.destroy,
                  bg=self.COLOR_RED, fg="white", font=self.FONT_BOLD, padx=20, pady=6
                  ).pack(side=tk.LEFT, padx=5)
    
    # ========================================================================
    # Zarządzanie projektami (mechanizm z RM_BAZA)
    # ========================================================================

    def _reconnect_master_rw(self):
        """Upewnij się, że połączenie do master jest READ-WRITE.
        Zwraca sqlite3.Connection (nowe lub istniejące)."""
        con = rmm._open_rm_connection(self.master_db_path)
        return con

    def add_project_dialog(self, on_created=None):
        """Dialog dodawania nowego projektu (kopiowany z RM_BAZA)"""
        win = tk.Toplevel(self.root)
        win.title("➕ Nowy projekt")
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        self._center_window(win, 600, 270)

        frm = tk.Frame(win, padx=25, pady=20, bg="#f0f0f0")
        frm.pack(fill="both", expand=True)

        # Nazwa projektu
        tk.Label(frm, text="Nazwa projektu:", font=("Arial", 10, "bold"), bg="#f0f0f0").grid(
            row=0, column=0, sticky="e", pady=(0, 12), padx=(0, 10))
        var_name = tk.StringVar()
        ent_name = tk.Entry(frm, textvariable=var_name, width=45, font=("Arial", 10))
        ent_name.grid(row=0, column=1, columnspan=2, sticky="ew", pady=(0, 12))

        # Ścieżka (opcjonalnie)
        tk.Label(frm, text="Ścieżka (opcjonalnie):", font=("Arial", 10), bg="#f0f0f0").grid(
            row=1, column=0, sticky="e", pady=(0, 12), padx=(0, 10))
        var_path = tk.StringVar()
        ent_path = tk.Entry(frm, textvariable=var_path, width=38, font=("Arial", 10))
        ent_path.grid(row=1, column=1, sticky="ew", pady=(0, 12))

        def browse():
            d = filedialog.askdirectory(title="Wybierz katalog projektu")
            if d:
                var_path.set(d)

        tk.Button(frm, text="📁", command=browse, width=3, font=("Arial", 9)).grid(
            row=1, column=2, padx=(5, 0), pady=(0, 12))

        # Konstruktor (opcjonalnie)
        tk.Label(frm, text="Konstruktor:", font=("Arial", 10), bg="#f0f0f0").grid(
            row=2, column=0, sticky="e", pady=(0, 12), padx=(0, 10))
        var_designer = tk.StringVar()
        ent_designer = tk.Entry(frm, textvariable=var_designer, width=45, font=("Arial", 10))
        ent_designer.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(0, 12))

        btn_frame = tk.Frame(frm, bg="#f0f0f0")
        btn_frame.grid(row=3, column=0, columnspan=3, pady=(10, 0))

        def ok():
            name = var_name.get().strip()
            path = var_path.get().strip()
            designer = var_designer.get().strip()

            if not name:
                messagebox.showwarning("Błąd", "Podaj nazwę projektu!", parent=win)
                return

            try:
                con = self._reconnect_master_rw()

                pid_new = create_project(
                    con, name=name, root_path=path or None,
                    project_type="MACHINE",
                    designer=designer or None, status='PROJEKT'
                )

                set_project_statuses(con, pid_new, ["PRZYJETY"],
                                     set_by=self.current_user)
                con.commit()
                con.close()
                print(f"✅ Projekt {pid_new} utworzony w master.sqlite: {name}")

                # 🆕 Utwórz pusty plik bazy projektu (identycznie jak RM_BAZA)
                project_db_path = pm_get_project_db_path(Path(self.projects_path), pid_new, "MACHINE")
                project_db_path.parent.mkdir(parents=True, exist_ok=True)
                print(f"📁 Tworzenie folderu: {project_db_path.parent}")
                
                # Utwórz plik data.sqlite z tabelą items
                temp_con = sqlite3.connect(str(project_db_path), timeout=30.0)
                temp_con.execute("""
                    CREATE TABLE IF NOT EXISTS items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER,
                        source TEXT,
                        src_doc TEXT,
                        src_row INTEGER,
                        src_uid TEXT,
                        src_pos TEXT,
                        src_drawing_no TEXT,
                        src_name TEXT,
                        src_desc TEXT,
                        src_qty INTEGER,
                        src_material_text TEXT,
                        src_supplier_text TEXT,
                        norm_drawing_no TEXT,
                        norm_name_key TEXT,
                        work_drawing_no TEXT,
                        work_name TEXT,
                        work_desc TEXT,
                        work_qty REAL,
                        order_qty REAL,
                        delivered_qty REAL,
                        delivered_updated_at TEXT,
                        supplier_id INTEGER,
                        drawing_over INTEGER,
                        name_over INTEGER,
                        desc_over INTEGER,
                        order_qty_over INTEGER,
                        supplier_over INTEGER,
                        mat_over INTEGER,
                        class_auto TEXT,
                        class_manual TEXT,
                        class_effective TEXT,
                        mat_auto_text TEXT,
                        mat_manual_text TEXT,
                        mat_effective_text TEXT,
                        mat_grade TEXT,
                        thickness_mm REAL,
                        thickness_src TEXT,
                        has_dxf INTEGER,
                        has_dwf INTEGER,
                        has_idw INTEGER,
                        has_stp INTEGER,
                        has_stl INTEGER,
                        alarm_date TEXT,
                        alarm_offset INTEGER,
                        alarm_unit TEXT,
                        deadline_date TEXT,
                        ordered_at TEXT,
                        ordered_flag INTEGER,
                        price_pln REAL,
                        status TEXT,
                        notes TEXT,
                        is_manual INTEGER,
                        dwf_biblioteka INTEGER,
                        is_hidden INTEGER,
                        min_qty REAL,
                        rank INTEGER,
                        created_at TEXT,
                        updated_at TEXT,
                        sync_error TEXT,
                        sync_hash TEXT,
                        sync_last_at TEXT,
                        sync_status TEXT
                    )
                """)
                temp_con.commit()
                temp_con.close()
                print(f"✅ Utworzono plik projektu: {project_db_path}")

                win.destroy()

                # Odśwież listę
                self.load_projects()

                if on_created:
                    try:
                        on_created()
                    except Exception as cb_err:
                        print(f"⚠️  Błąd callback on_created: {cb_err}")

                # Ustaw nowy projekt jako aktywny
                try:
                    idx = self.projects.index(pid_new)
                    self.project_combo.current(idx)
                    self.on_project_selected(None)
                except ValueError:
                    pass

            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się utworzyć projektu:\n{e}", parent=win)

        tk.Button(btn_frame, text="✔ Utwórz", command=ok, width=12,
                  bg="#27ae60", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="✖ Anuluj", command=win.destroy, width=12,
                  bg="#95a5a6", fg="white", font=("Arial", 10)).pack(side=tk.LEFT, padx=8)

        frm.columnconfigure(1, weight=1)
        ent_name.focus_set()
        ent_name.bind("<Return>", lambda e: ent_path.focus())
        ent_path.bind("<Return>", lambda e: ok())
        win.bind("<Escape>", lambda e: win.destroy())

    def projects_list_dialog(self):
        """Lista projektów z możliwością edycji (Treeview – mechanizm z RM_BAZA)"""

        win = tk.Toplevel(self.root)
        win.transient(self.root)  # Okno na tym samym ekranie co główna aplikacja
        win.title("📋 Lista projektów")
        win.resizable(True, True)
        self.restore_window_geometry('projects_list_window', win, 1500, 550)
        
        # Zapisz geometrię przy zamykaniu
        def on_close():
            self.save_window_geometry('projects_list_window', win)
            self.save_column_widths('projects_list_tree', tree)
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)

        var_show_inactive = tk.BooleanVar(value=False)

        # --- Treeview ---
        tree_frame = tk.Frame(win)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=10)

        vsb = tk.Scrollbar(tree_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb = tk.Scrollbar(tree_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        cols = ("id", "active", "name", "designer", "status", "created",
                "montaz", "fat", "completed", "locked", "path")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                            yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tree.heading("id", text="ID")
        tree.heading("active", text="Aktywny")
        tree.heading("name", text="Nazwa")
        tree.heading("designer", text="Konstruktor")
        tree.heading("status", text="Status")
        tree.heading("created", text="Utworzony")
        tree.heading("montaz", text="Montaż")
        tree.heading("fat", text="FAT")
        tree.heading("completed", text="Odbiór")
        tree.heading("locked", text="🔒 Lockuje")
        tree.heading("path", text="Ścieżka")

        tree.column("id",        width=60,  anchor="center")
        tree.column("active",    width=56,  anchor="center")
        tree.column("name",      width=220, anchor="w")
        tree.column("designer",  width=84,  anchor="w")
        tree.column("status",    width=216, anchor="center")
        tree.column("created",   width=95,  anchor="center")
        tree.column("montaz",    width=95,  anchor="center")
        tree.column("fat",       width=95,  anchor="center")
        tree.column("completed", width=95,  anchor="center")
        tree.column("locked",    width=84,  anchor="w")
        tree.column("path",      width=180, anchor="w")

        # Tagi dla kolorowania
        tree.tag_configure("inactive", foreground="#888888")
        tree.tag_configure("finished", foreground="#2c5aa0")  # Ciemnoniebieski
        tree.tag_configure("paused", foreground="#888888")     # Szary
        tree.pack(side=tk.LEFT, fill="both", expand=True)
        vsb.config(command=tree.yview)
        hsb.config(command=tree.xview)
        
        # Przywróć szerokości kolumn
        self.restore_column_widths('projects_list_tree', tree)

        # --- Pomocnicze ---
        def _fmt_date(val):
            """YYYY-MM-DD → DD-MM-YYYY"""
            if not val or len(val) < 10:
                return ""
            try:
                parts = val[:10].split('-')
                if len(parts) == 3 and len(parts[0]) == 4:
                    return f"{parts[2]}-{parts[1]}-{parts[0]}"
            except Exception:
                pass
            return val[:10]

        def _sort_key_projects(row):
            import re
            name = (row[1] or "").lower()
            if name and name[0].isdigit():
                m = re.match(r'^(\d+)', name)
                if m:
                    return (0, -int(m.group(1)), name)
            m = re.match(r'^([a-z]+)(\d+)?', name)
            if m:
                letter = m.group(1)
                num = m.group(2)
                if num:
                    return (1, letter, -int(num), name)
                return (1, letter, 0, name)
            return (1, name, 0, "")

        def reload():
            for iid in tree.get_children():
                tree.delete(iid)

            try:
                con = rmm._open_rm_connection(self.master_db_path)

                mcols = colnames(con, "projects")
                pk = pick_col(mcols, ["id", "project_id"])
                name_col = pick_col(mcols, ["name", "project_name"])
                path_col = pick_col(mcols, ["root_path", "path"])
                active_col = pick_col(mcols, ["is_active", "active", "enabled"])
                type_col = pick_col(mcols, ["project_type", "type"])
                designer_col = pick_col(mcols, ["designer", "designers"])
                created_col = pick_col(mcols, ["created_at"])
                montaz_col = pick_col(mcols, ["montaz", "sat"])
                fat_col = pick_col(mcols, ["fat"])
                completed_col = pick_col(mcols, ["completed_at"])

                select_cols = [pk, name_col, path_col, active_col]
                if type_col: select_cols.append(type_col)
                if designer_col: select_cols.append(designer_col)
                if created_col: select_cols.append(created_col)
                if montaz_col: select_cols.append(montaz_col)
                if fat_col: select_cols.append(fat_col)
                if completed_col: select_cols.append(completed_col)

                where = "WHERE COALESCE(project_type, 'MACHINE') = 'MACHINE'"
                if not var_show_inactive.get() and active_col:
                    where += f" AND COALESCE({active_col}, 1) = 1"

                sql = f"SELECT {', '.join(c for c in select_cols if c)} FROM projects {where}"
                rows = con.execute(sql).fetchall()

                rows_sorted = sorted(rows, key=_sort_key_projects)

                for row in rows_sorted:
                    idx = 0
                    pid = row[idx]; idx += 1
                    rname = row[idx] or ""; idx += 1
                    pth = row[idx] or ""; idx += 1
                    is_act = row[idx] if row[idx] is not None else 1; idx += 1
                    if type_col: idx += 1  # skip project_type
                    designer = ""
                    if designer_col and idx < len(row):
                        designer = row[idx] or ""; idx += 1
                    created = ""
                    if created_col and idx < len(row):
                        created = _fmt_date(row[idx]); idx += 1
                    montaz = ""
                    if montaz_col and idx < len(row):
                        montaz = _fmt_date(row[idx]); idx += 1
                    fat = ""
                    if fat_col and idx < len(row):
                        fat = _fmt_date(row[idx]); idx += 1
                    completed = ""
                    if completed_col and idx < len(row):
                        completed = _fmt_date(row[idx]); idx += 1

                    # Statusy multi-select
                    status_list = get_project_statuses(con, pid)
                    status = ", ".join(status_list) if status_list else "(brak)"

                    # Lock
                    locked_by = ""
                    if not getattr(self.lock_manager, '_STUB', False):
                        lock_info = self.lock_manager.get_project_lock_owner(pid)
                        if lock_info and lock_info.get('user'):
                            locked_by = self._get_user_display_name(lock_info['user'])
                    
                    # Określ tag na podstawie statusu projektu
                    tags = []
                    try:
                        project_db = self.get_project_db_path(pid)
                        if os.path.exists(project_db):
                            # Sprawdź czy zakończony
                            is_finished = rmm.is_milestone_set(project_db, pid, 'ZAKONCZONY')
                            if is_finished:
                                tags.append("finished")  # Ciemnoniebieski
                            else:
                                # Sprawdź czy wstrzymany
                                is_paused = rmm.is_project_paused(project_db, pid)
                                if is_paused:
                                    tags.append("paused")  # Szary
                    except Exception:
                        pass
                    
                    # Dodaj tag dla nieaktywnych (jeśli nie ma innych tagów)
                    if not is_act and not tags:
                        tags.append("inactive")

                    tree.insert("", "end",
                                values=(pid, "TAK" if is_act else "NIE", rname,
                                        designer, status, created, montaz, fat,
                                        completed, locked_by, pth),
                                tags=tuple(tags))

                con.close()
            except Exception as e:
                import traceback; traceback.print_exc()
                messagebox.showerror("Błąd", f"Nie udało się pobrać projektów:\n{e}", parent=win)

        def get_selected():
            sel = tree.selection()
            if not sel:
                return None
            vals = tree.item(sel[0], "values")
            try:
                return {
                    "id": int(vals[0]),
                    "active": vals[1] == "TAK",
                    "name": str(vals[2] or ""),
                    "designer": str(vals[3] or ""),
                    "status": str(vals[4] or ""),
                    "created_at": str(vals[5] or ""),
                    "montaz": str(vals[6] or ""),
                    "fat": str(vals[7] or ""),
                    "completed_at": str(vals[8] or ""),
                    "path": str(vals[10] or ""),
                }
            except Exception:
                return None

        def edit_selected():
            proj = get_selected()
            if not proj:
                messagebox.showwarning("Brak wyboru", "Zaznacz projekt do edycji!", parent=win)
                return
            self._edit_project_dialog(proj, parent_win=win, on_saved=lambda: (reload(), self.load_projects()))

        def toggle_active():
            proj = get_selected()
            if not proj:
                messagebox.showwarning("Brak wyboru", "Zaznacz projekt!", parent=win)
                return
            try:
                con = self._reconnect_master_rw()
                new_state = 0 if proj["active"] else 1
                set_project_active(con, proj["id"], new_state)
                con.commit()
                con.close()
                reload()
                self.load_projects()
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się zmienić statusu:\n{e}", parent=win)

        def delete_selected():
            proj = get_selected()
            if not proj:
                messagebox.showwarning("Brak wyboru", "Zaznacz projekt do usunięcia!", parent=win)
                return

            msg = (f"Czy na pewno usunąć projekt:\n\n'{proj['name']}' (ID: {proj['id']})\n\n"
                   f"UWAGA: Plik bazy projektu NIE zostanie usunięty automatycznie!")
            if not messagebox.askyesno("Potwierdź usunięcie", msg, parent=win):
                return

            try:
                con = self._reconnect_master_rw()
                delete_project(con, proj["id"])
                con.commit()
                con.close()
                print(f"🗑️ Projekt {proj['id']} usunięty")
                reload()
                self.load_projects()
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się usunąć projektu:\n{e}", parent=win)

        # --- Przyciski ---
        btn_bar = tk.Frame(win, bg="#ecf0f1", height=60)
        btn_bar.pack(fill="x")
        btn_bar.pack_propagate(False)

        btn_inner = tk.Frame(btn_bar, bg="#ecf0f1")
        btn_inner.pack(pady=12)

        tk.Checkbutton(btn_inner, text="Pokaż nieaktywne", variable=var_show_inactive,
                       command=reload, bg="#ecf0f1", font=("Arial", 9)).pack(side=tk.LEFT, padx=(10, 20))

        def add_and_reload():
            self.add_project_dialog(on_created=reload)

        tk.Button(btn_inner, text="➕ Dodaj", command=add_and_reload, width=12,
                  bg="#27ae60", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_inner, text="🔄 Odśwież", command=reload, width=12,
                  bg="#16a085", fg="white", font=("Arial", 10)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_inner, text="✏️ Edytuj", command=edit_selected, width=12,
                  bg="#f39c12", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_inner, text="🔄 Aktywny/Nieaktywny", command=toggle_active, width=20,
                  bg="#3498db", fg="white", font=("Arial", 10)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_inner, text="🗑️ Usuń", command=delete_selected, width=12,
                  bg="#e74c3c", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_inner, text="✖ Zamknij", command=on_close, width=12,
                  bg="#95a5a6", fg="white", font=("Arial", 10)).pack(side=tk.LEFT, padx=5)

        tree.bind("<Double-1>", lambda e: edit_selected())
        reload()

    def _edit_project_dialog(self, proj: dict, parent_win=None, on_saved=None):
        """Dialog edycji projektu (kopiowany z RM_BAZA edit_selected)"""
        parent = parent_win or self.root

        # Odczytaj aktualne dane z bazy
        try:
            con = rmm._open_rm_connection(self.master_db_path)
            mcols = colnames(con, "projects")
            pk = pick_col(mcols, ["id", "project_id"])
            designer_col = pick_col(mcols, ["designer", "designers"])
            montaz_col = pick_col(mcols, ["montaz", "sat"])
            fat_col = pick_col(mcols, ["fat"])
            completed_col = pick_col(mcols, ["completed_at"])

            sel = []
            if designer_col: sel.append(designer_col)
            if montaz_col: sel.append(montaz_col)
            if fat_col: sel.append(fat_col)
            if completed_col: sel.append(completed_col)

            if sel:
                row = con.execute(
                    f"SELECT {', '.join(sel)} FROM projects WHERE {pk}=?", (proj['id'],)
                ).fetchone()
                if row:
                    i = 0
                    if designer_col: proj['designer'] = row[i] or ""; i += 1
                    if montaz_col: proj['montaz'] = row[i] or ""; i += 1
                    if fat_col: proj['fat'] = row[i] or ""; i += 1
                    if completed_col: proj['completed_at'] = row[i] or ""; i += 1
            con.close()
        except Exception as e:
            print(f"⚠️  Błąd pobierania danych projektu: {e}")

        dlg = tk.Toplevel(parent)
        dlg.title(f"✏️ Edycja projektu #{proj['id']}")
        dlg.resizable(False, False)
        dlg.transient(parent)
        dlg.grab_set()
        self._center_window(dlg, 600, 550)

        frm = tk.Frame(dlg, padx=25, pady=20, bg="#f0f0f0")
        frm.pack(fill="both", expand=True)

        row_idx = 0

        # Nazwa
        tk.Label(frm, text="Nazwa projektu:", font=("Arial", 10, "bold"), bg="#f0f0f0").grid(
            row=row_idx, column=0, sticky="e", pady=(0, 12), padx=(0, 10))
        var_name = tk.StringVar(value=proj["name"])
        ent_name = tk.Entry(frm, textvariable=var_name, width=45, font=("Arial", 10))
        ent_name.grid(row=row_idx, column=1, columnspan=2, sticky="ew", pady=(0, 12))
        row_idx += 1

        # Ścieżka
        tk.Label(frm, text="Ścieżka:", font=("Arial", 10), bg="#f0f0f0").grid(
            row=row_idx, column=0, sticky="e", pady=(0, 12), padx=(0, 10))
        var_path = tk.StringVar(value=proj.get("path", ""))
        ent_path = tk.Entry(frm, textvariable=var_path, width=38, font=("Arial", 10))
        ent_path.grid(row=row_idx, column=1, sticky="ew", pady=(0, 12))

        def browse():
            d = filedialog.askdirectory(title="Wybierz katalog projektu")
            if d:
                var_path.set(d)

        tk.Button(frm, text="📁", command=browse, width=3, font=("Arial", 9)).grid(
            row=row_idx, column=2, padx=(5, 0), pady=(0, 12))
        row_idx += 1

        # Konstruktor
        tk.Label(frm, text="Konstruktor:", font=("Arial", 10), bg="#f0f0f0").grid(
            row=row_idx, column=0, sticky="e", pady=(0, 12), padx=(0, 10))
        var_designer = tk.StringVar(value=proj.get("designer", ""))
        ent_designer = tk.Entry(frm, textvariable=var_designer, width=45, font=("Arial", 10))
        ent_designer.grid(row=row_idx, column=1, columnspan=2, sticky="ew", pady=(0, 12))
        row_idx += 1

        # --- Statusy (multi-select checkboxy 2×5) ---
        tk.Label(frm, text="Statusy:", font=("Arial", 10, "bold"), bg="#f0f0f0").grid(
            row=row_idx, column=0, sticky="ne", pady=(5, 12), padx=(0, 10))

        try:
            rcon = rmm._open_rm_connection(self.master_db_path)
            current_statuses = get_project_statuses(rcon, proj['id'])
            rcon.close()
        except Exception:
            current_statuses = []

        status_frame = tk.Frame(frm, bg="#f0f0f0")
        status_frame.grid(row=row_idx, column=1, columnspan=2, sticky="w", pady=(0, 12))

        status_vars = {}
        for i, status in enumerate(PROJECT_STATUSES_NEW):
            col = i // 5
            row = i % 5
            var = tk.IntVar(value=1 if status in current_statuses else 0)
            status_vars[status] = var
            tk.Checkbutton(status_frame, text=f"{i+1}. {status}", variable=var,
                           bg="#f0f0f0", font=("Arial", 9), anchor="w"
                           ).grid(row=row, column=col, sticky="w", padx=(0, 20), pady=2)
        row_idx += 1

        # --- Daty ---
        def _to_display(val):
            """YYYY-MM-DD → DD-MM-YYYY"""
            if not val or len(val) < 10:
                return val or ""
            if val[4] == '-' and val[7] == '-':
                try:
                    p = val[:10].split('-')
                    return f"{p[2]}-{p[1]}-{p[0]}"
                except Exception:
                    pass
            return val

        date_fields = [
            ("Data montażu:",    proj.get("montaz", "")),
            ("Data FAT:",        proj.get("fat", "")),
            ("Data odbioru:",    proj.get("completed_at", "")),
        ]
        date_vars = []
        for label_text, raw_val in date_fields:
            tk.Label(frm, text=label_text, font=("Arial", 10), bg="#f0f0f0").grid(
                row=row_idx, column=0, sticky="e", pady=(0, 8), padx=(0, 10))
            v = tk.StringVar(value=_to_display(raw_val))
            date_vars.append(v)
            tk.Entry(frm, textvariable=v, width=45, font=("Arial", 10)).grid(
                row=row_idx, column=1, columnspan=2, sticky="ew", pady=(0, 8))
            tk.Label(frm, text="Przykład: 02-02-2026", font=("Arial", 8, "italic"),
                     fg="#666", bg="#f0f0f0").grid(
                row=row_idx + 1, column=1, columnspan=2, sticky="w", pady=(0, 12))
            row_idx += 2

        def _parse_date(text):
            """DD-MM-YYYY → YYYY-MM-DD (ISO)"""
            text = text.strip()
            if not text:
                return None
            try:
                dt = datetime.strptime(text, "%d-%m-%Y")
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Nieprawidłowy format daty: '{text}'.\nWymagany: DD-MM-YYYY")

        btn_frame = tk.Frame(frm, bg="#f0f0f0")
        btn_frame.grid(row=row_idx, column=0, columnspan=3, pady=(10, 0))

        def save():
            name = var_name.get().strip()
            path = var_path.get().strip()
            designer = var_designer.get().strip()
            selected_statuses = [s for s, v in status_vars.items() if v.get() == 1]

            if not name:
                messagebox.showwarning("Błąd", "Podaj nazwę projektu!", parent=dlg)
                return

            try:
                montaz_iso = _parse_date(date_vars[0].get())
                fat_iso = _parse_date(date_vars[1].get())
                completed_iso = _parse_date(date_vars[2].get())
            except ValueError as ve:
                messagebox.showwarning("Błąd", str(ve), parent=dlg)
                return

            if "ZAKONCZONY" in selected_statuses and not completed_iso:
                completed_iso = datetime.now().strftime("%Y-%m-%d")

            try:
                con = self._reconnect_master_rw()

                update_project(con, proj["id"], name=name,
                               root_path=path or None,
                               designer=designer or None,
                               montaz=montaz_iso, fat=fat_iso,
                               completed_at=completed_iso)

                set_project_statuses(con, proj["id"], selected_statuses,
                                     set_by=self.current_user)
                con.commit()
                con.close()
                print(f"✅ Projekt {proj['id']} zaktualizowany")

                dlg.destroy()
                if on_saved:
                    on_saved()

            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się zapisać:\n{e}", parent=dlg)

        tk.Button(btn_frame, text="✔ Zapisz", command=save, width=12,
                  bg="#27ae60", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="✖ Anuluj", command=dlg.destroy, width=12,
                  bg="#95a5a6", fg="white", font=("Arial", 10)).pack(side=tk.LEFT, padx=8)

        frm.columnconfigure(1, weight=1)
        ent_name.focus_set()
        ent_name.bind("<Return>", lambda e: ent_path.focus())
        ent_path.bind("<Return>", lambda e: save())
        dlg.bind("<Escape>", lambda e: dlg.destroy())

    # ========================================================================
    # Dialog uprawnień kategorii użytkowników
    # ========================================================================

    def edit_permissions_dialog(self):
        """Dialog edycji uprawnień per kategoria (rola) użytkownika.
        Tylko administrator (can_manage_permissions) może zapisywać zmiany.
        Wszyscy mogą przeglądać (read-only).
        """
        PERM_COLS = [
            ('can_start_stage',        'START etapu'),
            ('can_end_stage',          'END etapu'),
            ('can_edit_dates',         'Edycja dat'),
            ('can_sync_master',        'Sync RM_BAZA'),
            ('can_critical_path',      'Ścieżka krytyczna'),
            ('can_manage_permissions', 'Zarządzanie uprawnieniami'),
        ]

        can_save = self._has_permission('can_manage_permissions')

        # Pobierz aktualne uprawnienia
        rows = rmm.get_all_role_permissions(self.rm_master_db_path)
        # Jeśli brak wierszy (np. pusta baza) – użyj domyślnych z DEFAULT_ROLE_PERMISSIONS
        if not rows:
            perm_keys = [k for k, _ in PERM_COLS]
            rows = []
            for role_tuple in rmm.DEFAULT_ROLE_PERMISSIONS:
                row = {'role': role_tuple[0]}
                # role_tuple: (role, start, end, edit_dates, sync, critical_path, manage_permissions)
                for i, key in enumerate(perm_keys):
                    row[key] = bool(role_tuple[i + 1]) if (i + 1) < len(role_tuple) else False
                rows.append(row)

        dlg = tk.Toplevel(self.root)
        dlg.title("Uprawnienia kategorii użytkowników")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(True, True)
        self._center_window(dlg, 760, 420)

        # Nagłówek
        header = tk.Label(
            dlg,
            text="UPRAWNIENIA KATEGORII UŻYTKOWNIKÓW",
            bg=self.COLOR_TOPBAR, fg="white",
            font=("Arial", 12, "bold"), pady=8
        )
        header.pack(fill=tk.X)

        if not can_save:
            info = tk.Label(
                dlg,
                text="⚠ Tryb tylko do odczytu – Twoja rola nie ma prawa do edycji uprawnień",
                bg="#f39c12", fg="white",
                font=("Arial", 9, "bold"), pady=4
            )
            info.pack(fill=tk.X)

        # Tabela checkboxów
        tbl = tk.Frame(dlg, padx=15, pady=10)
        tbl.pack(fill=tk.BOTH, expand=True)

        # Nagłówki kolumn
        tk.Label(tbl, text="Rola / Kategoria", font=self.FONT_BOLD,
                 width=18, anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 6))
        for col_i, (perm_key, perm_lbl) in enumerate(PERM_COLS, start=1):
            tk.Label(tbl, text=perm_lbl, font=("Arial", 9, "bold"),
                     wraplength=90, justify="center").grid(
                row=0, column=col_i, padx=6, pady=(0, 6))

        # Wiersze ról + zmienne BooleanVar
        row_vars: dict[str, dict[str, tk.BooleanVar]] = {}
        for row_i, role_row in enumerate(rows, start=1):
            role = role_row['role']
            row_vars[role] = {}

            tk.Label(tbl, text=role, font=self.FONT_BOLD,
                     width=18, anchor="w").grid(row=row_i, column=0, sticky="w", pady=3)

            for col_i, (perm_key, _) in enumerate(PERM_COLS, start=1):
                var = tk.BooleanVar(value=bool(role_row.get(perm_key, False)))
                row_vars[role][perm_key] = var
                cb_state = tk.NORMAL if can_save else tk.DISABLED
                tk.Checkbutton(
                    tbl, variable=var, state=cb_state,
                    bg="white" if can_save else "#f0f0f0"
                ).grid(row=row_i, column=col_i, padx=6, pady=3)

        # Przyciski
        btn_frame = tk.Frame(dlg)
        btn_frame.pack(fill=tk.X, padx=15, pady=10)

        def save_permissions():
            try:
                # Ochrona przed self-lockout: ADMIN musi mieć can_manage_permissions
                admin_vars = row_vars.get('ADMIN')
                if admin_vars and not admin_vars.get('can_manage_permissions', tk.BooleanVar(value=True)).get():
                    messagebox.showwarning(
                        "⚠ Ochrona ADMIN",
                        "Nie można odebrać uprawnienia 'Zarządzanie uprawnieniami' roli ADMIN.\n"
                        "To spowodowałoby utratę dostępu do edycji uprawnień."
                    )
                    return
                for role, perms_vars in row_vars.items():
                    perms = {k: v.get() for k, v in perms_vars.items()}
                    rmm.set_role_permissions(self.rm_master_db_path, role, perms)
                # Odśwież uprawnienia bieżącego usera
                self.user_permissions = rmm.get_user_permissions(
                    self.rm_master_db_path, self.current_user_role
                )
                self._update_action_buttons_state()
                dlg.destroy()
                self.status_bar.config(text="🔑 Uprawnienia zapisane", fg="#27ae60")
            except Exception as e:
                messagebox.showerror("❌ Błąd", f"Nie można zapisać uprawnień:\n{e}")

        if can_save:
            tk.Button(
                btn_frame, text="💾 Zapisz", command=save_permissions,
                bg=self.COLOR_GREEN, fg="white", font=self.FONT_BOLD, padx=20, pady=6
            ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            btn_frame, text="❌ Zamknij", command=dlg.destroy,
            bg=self.COLOR_RED, fg="white", font=self.FONT_BOLD, padx=20, pady=6
        ).pack(side=tk.LEFT, padx=5)

    # ========================================================================
    # Listy zasobów – Pracownicy
    # ========================================================================

    def employees_dialog(self):
        """Okno listy pracowników z filtrem kategorii i pełną edycją."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Pracownicy")
        dlg.transient(self.root)
        self._center_window(dlg, 1200, 580)

        header = tk.Label(dlg, text="LISTA PRACOWNIKÓW",
                          bg=self.COLOR_TOPBAR, fg="white",
                          font=("Arial", 12, "bold"), pady=8)
        header.pack(fill=tk.X)

        # Toolbar: filtr kategorii + przyciski
        toolbar = tk.Frame(dlg, padx=8, pady=6)
        toolbar.pack(fill=tk.X)

        tk.Label(toolbar, text="Kategoria:", font=self.FONT_BOLD).pack(side=tk.LEFT)
        cat_var = tk.StringVar(value="Wszystkie")
        cat_combo = ttk.Combobox(toolbar, textvariable=cat_var, state='readonly', width=18,
                                 values=["Wszystkie"] + rmm.EMPLOYEE_CATEGORIES, font=self.FONT_DEFAULT)
        cat_combo.pack(side=tk.LEFT, padx=(4, 15))

        show_inactive_var = tk.BooleanVar(value=False)
        tk.Checkbutton(toolbar, text="Pokaż nieaktywnych",
                       variable=show_inactive_var).pack(side=tk.LEFT, padx=(0, 15))

        tk.Button(toolbar, text="➕ Dodaj", command=lambda: self._employee_edit(None, tree, refresh),
                  bg=self.COLOR_GREEN, fg="white", font=self.FONT_BOLD, padx=10).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="✏️ Edytuj", command=lambda: _edit_selected(),
                  bg=self.COLOR_PURPLE, fg="white", font=self.FONT_BOLD, padx=10).pack(side=tk.LEFT, padx=2)
        tk.Button(toolbar, text="🗑 Usuń", command=lambda: _delete_selected(),
                  bg=self.COLOR_RED, fg="white", font=self.FONT_BOLD, padx=10).pack(side=tk.LEFT, padx=2)

        # Treeview
        cols = ('id', 'name', 'category', 'description', 'phone', 'email', 'contact', 'active')
        tree = ttk.Treeview(dlg, columns=cols, show='headings', height=22)
        tree.heading('id',          text='ID');          tree.column('id',          width=40,  stretch=False)
        tree.heading('name',        text='Imię i nazwisko'); tree.column('name',    width=180)
        tree.heading('category',    text='Kategoria');   tree.column('category',    width=110, stretch=False)
        tree.heading('description', text='Opis');        tree.column('description', width=180)
        tree.heading('phone',       text='Nr telefonu'); tree.column('phone',       width=120, stretch=False)
        tree.heading('email',       text='Email');       tree.column('email',       width=180)
        tree.heading('contact',     text='Dane kontaktowe'); tree.column('contact', width=150)
        tree.heading('active',      text='Aktywny');     tree.column('active',      width=65,  stretch=False)

        vsb = ttk.Scrollbar(dlg, orient=tk.VERTICAL,   command=tree.yview)
        hsb = ttk.Scrollbar(dlg, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=4)
        vsb.pack(side=tk.LEFT, fill=tk.Y, pady=4)

        def refresh(*_):
            tree.delete(*tree.get_children())
            cat = cat_var.get()
            rows = rmm.get_employees(
                self.rm_master_db_path,
                category=(None if cat == "Wszystkie" else cat),
                active_only=False
            )
            for r in rows:
                if not show_inactive_var.get() and not r['is_active']:
                    continue
                tree.insert('', tk.END, iid=str(r['id']), values=(
                    r['id'], r['name'], r['category'],
                    r.get('description') or '',
                    r.get('phone') or '',
                    r.get('email') or '',
                    r.get('contact_info') or '',
                    '✓' if r['is_active'] else '—'
                ))

        cat_combo.bind('<<ComboboxSelected>>', refresh)
        show_inactive_var.trace_add('write', refresh)
        tree.bind('<Double-1>', lambda e: _edit_selected())
        refresh()

        def _edit_selected():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Uwaga", "Wybierz pracownika z listy.", parent=dlg)
                return
            self._employee_edit(int(sel[0]), tree, refresh)

        def _delete_selected():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Uwaga", "Wybierz pracownika do usunięcia.", parent=dlg)
                return
            name = tree.item(sel[0])['values'][1]
            if messagebox.askyesno("Potwierdzenie",
                                   f"Usunąć pracownika:\n{name}?", parent=dlg):
                rmm.delete_employee(self.rm_master_db_path, int(sel[0]))
                refresh()

    def _employee_edit(self, employee_id, tree, refresh_cb):
        """Formularz dodawania / edycji pracownika."""
        # Wczytaj istniejące dane
        existing = {}
        if employee_id:
            rows = rmm.get_employees(self.rm_master_db_path)
            for r in rows:
                if r['id'] == employee_id:
                    existing = r
                    break

        frm = tk.Toplevel(self.root)
        frm.title("Dodaj pracownika" if not employee_id else "Edytuj pracownika")
        frm.transient(self.root)
        frm.grab_set()
        frm.resizable(False, False)
        self._center_window(frm, 540, 520)

        header = tk.Label(frm,
                          text="DODAJ PRACOWNIKA" if not employee_id else "EDYTUJ PRACOWNIKA",
                          bg=self.COLOR_TOPBAR, fg="white",
                          font=("Arial", 11, "bold"), pady=7)
        header.pack(fill=tk.X)

        body = tk.Frame(frm, padx=20, pady=12)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)

        def lbl(row, text):
            tk.Label(body, text=text, font=self.FONT_BOLD, anchor='w').grid(
                row=row, column=0, sticky='w', pady=4, padx=(0, 10))

        # Imię i nazwisko
        lbl(0, "Imię i nazwisko *:")
        name_var = tk.StringVar(value=existing.get('name', ''))
        tk.Entry(body, textvariable=name_var, font=self.FONT_DEFAULT).grid(
            row=0, column=1, sticky='ew', pady=4)

        # Kategoria
        lbl(1, "Kategoria *:")
        cat_var = tk.StringVar(value=existing.get('category', rmm.EMPLOYEE_CATEGORIES[0]))
        ttk.Combobox(body, textvariable=cat_var, values=rmm.EMPLOYEE_CATEGORIES,
                     state='readonly', font=self.FONT_DEFAULT).grid(
            row=1, column=1, sticky='ew', pady=4)

        # Opis
        lbl(2, "Opis:")
        desc_text = tk.Text(body, font=self.FONT_DEFAULT, height=3, wrap=tk.WORD)
        desc_text.insert('1.0', existing.get('description') or '')
        desc_text.grid(row=2, column=1, sticky='ew', pady=4)

        # Nr telefonu
        lbl(3, "Nr telefonu:")
        phone_var = tk.StringVar(value=existing.get('phone') or '')
        tk.Entry(body, textvariable=phone_var, font=self.FONT_DEFAULT).grid(
            row=3, column=1, sticky='ew', pady=4)

        # Email
        lbl(4, "Email:")
        email_var = tk.StringVar(value=existing.get('email') or '')
        tk.Entry(body, textvariable=email_var, font=self.FONT_DEFAULT).grid(
            row=4, column=1, sticky='ew', pady=4)

        # Dane kontaktowe (dodatkowe)
        lbl(5, "Dane kontaktowe:")
        contact_text = tk.Text(body, font=self.FONT_DEFAULT, height=3, wrap=tk.WORD)
        contact_text.insert('1.0', existing.get('contact_info') or '')
        contact_text.grid(row=5, column=1, sticky='ew', pady=4)

        # Aktywny
        active_var = tk.BooleanVar(value=bool(existing.get('is_active', True)))
        tk.Checkbutton(body, text="Aktywny", variable=active_var,
                       font=self.FONT_DEFAULT).grid(row=6, column=1, sticky='w', pady=4)

        def save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Uwaga", "Podaj imię i nazwisko.", parent=frm)
                return
            data = {
                'name': name,
                'category': cat_var.get(),
                'description': desc_text.get('1.0', tk.END).strip(),
                'phone': phone_var.get().strip(),
                'email': email_var.get().strip(),
                'contact_info': contact_text.get('1.0', tk.END).strip(),
                'is_active': active_var.get(),
            }
            if employee_id:
                data['id'] = employee_id
            rmm.save_employee(self.rm_master_db_path, data)
            frm.destroy()
            refresh_cb()

        btn_row = tk.Frame(frm)
        btn_row.pack(fill=tk.X, padx=20, pady=10)
        tk.Button(btn_row, text="💾 Zapisz", command=save,
                  bg=self.COLOR_GREEN, fg="white", font=self.FONT_BOLD, padx=16, pady=5
                  ).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_row, text="❌ Anuluj", command=frm.destroy,
                  bg=self.COLOR_RED, fg="white", font=self.FONT_BOLD, padx=16, pady=5
                  ).pack(side=tk.LEFT, padx=4)

    # ========================================================================
    # Listy zasobów – Transport
    # ========================================================================

    def transports_dialog(self):
        """Okno listy transportu z pełną edycją."""
        try:
            print(f"🚚 Otworzenie dialogu transport...")
            
            dlg = tk.Toplevel(self.root)
            dlg.title("Transport")
            dlg.transient(self.root)
            print(f"🚚 Toplevel utworzony")
            
            self._center_window(dlg, 980, 540)
            print(f"🚚 Okno wycentrowane")

            header = tk.Label(dlg, text="LISTA TRANSPORTU",
                              bg=self.COLOR_TOPBAR, fg="white",
                              font=("Arial", 12, "bold"), pady=8)
            header.pack(fill=tk.X)
            print(f"🚚 Header dodany")

            toolbar = tk.Frame(dlg, padx=8, pady=6)
            toolbar.pack(fill=tk.X)
            print(f"🚚 Toolbar utworzony")

            # Definicje funkcji PRZED ich użyciem
            def _edit_selected():
                sel = tree.selection()
                if not sel:
                    messagebox.showwarning("Uwaga", "Wybierz pozycję z listy.", parent=dlg)
                    return
                self._transport_edit(int(sel[0]), tree, refresh)

            def _delete_selected():
                sel = tree.selection()
                if not sel:
                    messagebox.showwarning("Uwaga", "Wybierz pozycję do usunięcia.", parent=dlg)
                    return
                name = tree.item(sel[0])['values'][1]
                if messagebox.askyesno("Potwierdzenie",
                                       f"Usunąć pozycję transportu:\n{name}?", parent=dlg):
                    rmm.delete_transport(self.rm_master_db_path, int(sel[0]))
                    refresh()

            def refresh(*_):
                tree.delete(*tree.get_children())
                for r in rmm.get_transports(self.rm_master_db_path, active_only=False):
                    if not show_inactive_var.get() and not r['is_active']:
                        continue
                    tree.insert('', tk.END, iid=str(r['id']), values=(
                        r['id'], r['name'],
                        r.get('description') or '',
                        r.get('contact_info') or '',
                        '✓' if r['is_active'] else '—'
                    ))

            show_inactive_var = tk.BooleanVar(value=False)
            tk.Checkbutton(toolbar, text="Pokaż nieaktywne",
                           variable=show_inactive_var).pack(side=tk.LEFT, padx=(0, 15))

            tk.Button(toolbar, text="➕ Dodaj", command=lambda: self._transport_edit(None, tree, refresh),
                      bg=self.COLOR_GREEN, fg="white", font=self.FONT_BOLD, padx=10).pack(side=tk.LEFT, padx=2)
            tk.Button(toolbar, text="✏️ Edytuj", command=lambda: _edit_selected(),
                      bg=self.COLOR_PURPLE, fg="white", font=self.FONT_BOLD, padx=10).pack(side=tk.LEFT, padx=2)
            tk.Button(toolbar, text="🗑 Usuń", command=lambda: _delete_selected(),
                      bg=self.COLOR_RED, fg="white", font=self.FONT_BOLD, padx=10).pack(side=tk.LEFT, padx=2)

            cols = ('id', 'name', 'description', 'contact', 'active')
            tree = ttk.Treeview(dlg, columns=cols, show='headings', height=22)
            tree.heading('id',          text='ID');          tree.column('id',          width=40,  stretch=False)
            tree.heading('name',        text='Nazwa');       tree.column('name',        width=220)
            tree.heading('description', text='Opis');        tree.column('description', width=320)
            tree.heading('contact',     text='Dane kontaktowe'); tree.column('contact', width=260)
            tree.heading('active',      text='Aktywny');     tree.column('active',      width=65,  stretch=False)

            vsb = ttk.Scrollbar(dlg, orient=tk.VERTICAL,   command=tree.yview)
            hsb = ttk.Scrollbar(dlg, orient=tk.HORIZONTAL, command=tree.xview)
            tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=4)
            vsb.pack(side=tk.LEFT, fill=tk.Y, pady=4)

            show_inactive_var.trace_add('write', refresh)
            tree.bind('<Double-1>', lambda e: _edit_selected())
            refresh()
            
        except Exception as e:
            print(f"🚚 BŁĄD w transports_dialog: {e}")
            messagebox.showerror("Błąd", f"Błąd okna transportu:\n{e}")

    def _transport_edit(self, transport_id, tree, refresh_cb):
        """Formularz dodawania / edycji pozycji transportu."""
        existing = {}
        if transport_id:
            for r in rmm.get_transports(self.rm_master_db_path):
                if r['id'] == transport_id:
                    existing = r
                    break

        frm = tk.Toplevel(self.root)
        frm.title("Dodaj transport" if not transport_id else "Edytuj transport")
        frm.transient(self.root)
        frm.grab_set()
        frm.resizable(False, False)
        self._center_window(frm, 540, 380)

        header = tk.Label(frm,
                          text="DODAJ TRANSPORT" if not transport_id else "EDYTUJ TRANSPORT",
                          bg=self.COLOR_TOPBAR, fg="white",
                          font=("Arial", 11, "bold"), pady=7)
        header.pack(fill=tk.X)

        body = tk.Frame(frm, padx=20, pady=12)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)

        def lbl(row, text):
            tk.Label(body, text=text, font=self.FONT_BOLD, anchor='w').grid(
                row=row, column=0, sticky='w', pady=4, padx=(0, 10))

        lbl(0, "Nazwa *:")
        name_var = tk.StringVar(value=existing.get('name', ''))
        tk.Entry(body, textvariable=name_var, font=self.FONT_DEFAULT).grid(
            row=0, column=1, sticky='ew', pady=4)

        lbl(1, "Opis:")
        desc_text = tk.Text(body, font=self.FONT_DEFAULT, height=4, wrap=tk.WORD)
        desc_text.insert('1.0', existing.get('description') or '')
        desc_text.grid(row=1, column=1, sticky='ew', pady=4)

        lbl(2, "Dane kontaktowe:")
        contact_text = tk.Text(body, font=self.FONT_DEFAULT, height=4, wrap=tk.WORD)
        contact_text.insert('1.0', existing.get('contact_info') or '')
        contact_text.grid(row=2, column=1, sticky='ew', pady=4)

        active_var = tk.BooleanVar(value=bool(existing.get('is_active', True)))
        tk.Checkbutton(body, text="Aktywny", variable=active_var,
                       font=self.FONT_DEFAULT).grid(row=3, column=1, sticky='w', pady=4)

        def save():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Uwaga", "Podaj nazwę.", parent=frm)
                return
            data = {
                'name': name,
                'description': desc_text.get('1.0', tk.END).strip(),
                'contact_info': contact_text.get('1.0', tk.END).strip(),
                'is_active': active_var.get(),
            }
            if transport_id:
                data['id'] = transport_id
            rmm.save_transport(self.rm_master_db_path, data)
            frm.destroy()
            refresh_cb()

        btn_row = tk.Frame(frm)
        btn_row.pack(fill=tk.X, padx=20, pady=10)
        tk.Button(btn_row, text="💾 Zapisz", command=save,
                  bg=self.COLOR_GREEN, fg="white", font=self.FONT_BOLD, padx=16, pady=5
                  ).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_row, text="❌ Anuluj", command=frm.destroy,
                  bg=self.COLOR_RED, fg="white", font=self.FONT_BOLD, padx=16, pady=5
                  ).pack(side=tk.LEFT, padx=4)

    def sync_to_master(self):
        """Synchronizuj z RM_BAZA master.sqlite"""
        if not self._has_permission('can_sync_master'):
            messagebox.showerror(
                "🚫 Brak uprawnień",
                f"Twoja rola [{self.current_user_role}] nie ma prawa do synchronizacji z RM_BAZA."
            )
            return
        if not self.selected_project_id:
            messagebox.showwarning("⚠️ Uwaga", "Wybierz projekt")
            self.status_bar.config(text="⚠️ Nie wybrano projektu", fg="#f39c12")
            return
        
        if not os.path.exists(self.master_db_path):
            messagebox.showwarning("⚠️ Uwaga", f"Nie znaleziono master.sqlite:\n{self.master_db_path}")
            self.status_bar.config(text="⚠️ Brak master.sqlite", fg="#f39c12")
            return
        
        try:
            self.status_bar.config(text="⏳ Synchronizacja...", fg="#f39c12")
            self.root.update()
            
            rmm.sync_to_master(self.get_project_db_path(self.selected_project_id), self.master_db_path, self.selected_project_id)
            
            self.status_bar.config(text=f"🟢 Zsynchronizowano projekt {self.selected_project_id}", fg="#27ae60")
        except Exception as e:
            self.status_bar.config(text="🔴 Błąd synchronizacji", fg="#e74c3c")
            messagebox.showerror("❌ Błąd", f"Nie można zsynchronizować:\n{e}")
    
    def sync_all_to_master(self):
        """Synchronizuj wszystkie projekty z RM_MANAGER → master.sqlite (manual)"""
        if not self._has_permission('can_sync_master'):
            messagebox.showerror(
                "🚫 Brak uprawnień",
                f"Twoja rola [{self.current_user_role}] nie ma prawa do synchronizacji z RM_BAZA."
            )
            return
        
        if not os.path.exists(self.master_db_path):
            messagebox.showwarning("⚠️ Uwaga", f"Nie znaleziono master.sqlite:\n{self.master_db_path}")
            self.status_bar.config(text="⚠️ Brak master.sqlite", fg="#f39c12")
            return
        
        # Potwierdź operację
        result = messagebox.askyesno(
            "🔄 Synchronizacja wszystkich projektów",
            "Czy zsynchronizować wszystkie projekty z RM_MANAGER → RM_BAZA?\n\n"
            "Operacja może potrwać kilka sekund w zależności od liczby projektów.",
            icon='question'
        )
        if not result:
            return
        
        try:
            self.status_bar.config(text="⏳ Synchronizacja wszystkich projektów...", fg="#f39c12")
            self.root.update()
            
            # Uruchom w osobnym wątku aby nie blokować GUI
            def sync_worker():
                try:
                    synced = rmm.sync_all_projects(
                        self.rm_master_db_path,
                        self.rm_projects_dir,
                        self.master_db_path,
                        user=self.current_user,
                        lock_manager=self.lock_manager
                    )
                    
                    # Zaktualizuj UI w głównym wątku
                    self.root.after(0, lambda: self.status_bar.config(
                        text=f"✅ Zsynchronizowano {synced} projektów",
                        fg="#27ae60"
                    ))
                    self.root.after(0, lambda: messagebox.showinfo(
                        "✅ Sukces",
                        f"Zsynchronizowano {synced} projektów z master.sqlite\n\n"
                        f"Dane w RM_BAZA zostały zaktualizowane."
                    ))
                except Exception as e:
                    self.root.after(0, lambda: self.status_bar.config(
                        text="🔴 Błąd synchronizacji",
                        fg="#e74c3c"
                    ))
                    self.root.after(0, lambda: messagebox.showerror(
                        "❌ Błąd",
                        f"Nie można zsynchronizować projektów:\n{e}"
                    ))
            
            sync_thread = threading.Thread(target=sync_worker, daemon=True)
            sync_thread.start()
            
        except Exception as e:
            self.status_bar.config(text="🔴 Błąd synchronizacji", fg="#e74c3c")
            messagebox.showerror("❌ Błąd", f"Nie można zsynchronizować:\n{e}")
    
    def show_critical_path(self):
        """Pokaż critical path - wizualizacja graficzna + tabela"""
        if not self._has_permission('can_critical_path'):
            messagebox.showerror(
                "🚫 Brak uprawnień",
                f"Twoja rola [{self.current_user_role}] nie ma prawa do analizy ścieżki krytycznej."
            )
            return
        if not self.selected_project_id:
            messagebox.showwarning("⚠️ Uwaga", "Wybierz projekt")
            self.status_bar.config(text="⚠️ Nie wybrano projektu", fg="#f39c12")
            return
        
        try:
            self.status_bar.config(text="⏳ Obliczanie ścieżki krytycznej...", fg="#f39c12")
            self.root.update()
            
            details = rmm.get_critical_path_details(
                self.get_project_db_path(self.selected_project_id), 
                self.selected_project_id
            )
            
            if not details:
                messagebox.showinfo("📊 Ścieżka krytyczna", "Brak danych do analizy CPM")
                return
            
            # Odfiltruj milestones informacyjne (bez zależności w grafie - "wiszące")
            project_db = self.get_project_db_path(self.selected_project_id)
            con_dep = rmm._open_rm_connection(project_db, row_factory=False)
            connected_stages = set()
            for row in con_dep.execute("""
                SELECT predecessor_stage_code, successor_stage_code 
                FROM stage_dependencies WHERE project_id = ?
            """, (self.selected_project_id,)).fetchall():
                connected_stages.add(row[0])
                connected_stages.add(row[1])
            con_dep.close()
            
            # Rozbij na podłączone (CPM) i wiszące (eventy)
            details_connected = [d for d in details if d['stage_code'] in connected_stages]
            details_events = [d for d in details if d['stage_code'] not in connected_stages]
            
            # Używaj tylko podłączonych do metryk
            details = details_connected if details_connected else details
            
            # Sortuj: krytyczne najpierw, potem po rezerwie rosnąco
            details.sort(key=lambda d: (0 if d['is_critical'] else 1, d['total_float']))
            
            critical = [d for d in details if d['is_critical']]
            n_critical = len(critical)
            n_total = len(details)
            pct_critical = (n_critical / n_total * 100) if n_total > 0 else 0
            non_critical = [d for d in details if not d['is_critical']]
            avg_float = sum(d['total_float'] for d in non_critical) / max(1, len(non_critical))
            
            # ═══ OBLICZ OPÓŹNIENIE PROJEKTU vs KONTRAKT ═══
            project_variance_days = None
            expected_delivery = None
            forecast_completion = None
            has_actual_work = False  # Czy projekt już faktycznie wystartował
            
            try:
                # Sprawdź czy projekt ma jakiekolwiek ACTUAL periods (czy rzeczywiście wystartował)
                forecast = rmm.recalculate_forecast(
                    self.get_project_db_path(self.selected_project_id), 
                    self.selected_project_id
                )
                
                if forecast:
                    # Sprawdź czy którykolwiek etap ma actual periods (poza PRZYJĘTY)
                    for stage_code, fc in forecast.items():
                        if stage_code == 'PRZYJETY':  # pomijamy milestone przyjęty
                            continue
                        if fc.get('actual_periods'):
                            has_actual_work = True
                            break
                
                # Pobierz planowaną datę zakończenia z milestonu ZAKOŃCZONY (template)
                con_rm = rmm._open_rm_connection(self.rm_db_path, row_factory=False)
                row = con_rm.execute(
                    """
                    SELECT template_end 
                    FROM stage_schedule 
                    WHERE project_id = ? AND stage_code = 'ZAKONCZONY'
                    """,
                    (self.selected_project_id,)
                ).fetchone()
                con_rm.close()
                
                if row and row[0]:
                    expected_delivery = row[0]  # YYYY-MM-DD z template (planowana data zakończenia)
                
                # Znajdź etap kończący projekt (maksymalny EF)
                if details:
                    max_ef = max(d['EF'] for d in details)
                    # Przelicz EF na datę rzeczywistą (forecast_start pierwszego etapu + EF dni)
                    if forecast:
                        # Znajdź pierwszy etap (earliest start)
                        first_stage = min(forecast.items(), 
                                        key=lambda x: x[1].get('forecast_start', '9999-99-99'))
                        first_start = first_stage[1].get('forecast_start')
                        
                        if first_start:
                            from datetime import datetime, timedelta
                            start_dt = datetime.fromisoformat(str(first_start)[:10])
                            completion_dt = start_dt + timedelta(days=max_ef)
                            forecast_completion = completion_dt.date().isoformat()
                
                # Oblicz variance (opóźnienie projektu)
                if expected_delivery and forecast_completion:
                    from datetime import datetime
                    exp_dt = datetime.fromisoformat(str(expected_delivery)[:10])
                    fc_dt = datetime.fromisoformat(str(forecast_completion)[:10])
                    project_variance_days = (fc_dt - exp_dt).days
                    
            except Exception as e:
                print(f"⚠️ Błąd obliczania opóźnienia projektu: {e}")
            
            # Okno z wykresem
            cp_win = tk.Toplevel(self.root)
            cp_win.transient(self.root)  # Okno na tym samym ekranie co główna aplikacja
            cp_win.title(f"📊 Ścieżka krytyczna (CPM) - Projekt {self.selected_project_id}")
            cp_win.geometry("1200x850")
            
            # Header z metrykami
            header = tk.Frame(cp_win, bg="#2c3e50", pady=12)
            header.pack(fill=tk.X)
            
            metrics_frame = tk.Frame(header, bg="#2c3e50")
            metrics_frame.pack()
            
            # Metryka 1: Etapy krytyczne
            m1 = tk.Frame(metrics_frame, bg="#e74c3c", padx=20, pady=10, relief=tk.RAISED, bd=2)
            m1.pack(side=tk.LEFT, padx=10)
            tk.Label(m1, text=f"{n_critical}", bg="#e74c3c", fg="white", 
                    font=("Arial", 24, "bold")).pack()
            tk.Label(m1, text=f"Bez rezerwy ({pct_critical:.0f}%)", 
                    bg="#e74c3c", fg="white", font=("Arial", 9)).pack()
            
            # Metryka 2: OPÓŹNIENIE PROJEKTU (tylko jeśli projekt już wystartował!)
            if project_variance_days is not None and has_actual_work:
                # Projekt już trwa - pokaż opóźnienie vs oryginalny kontrakt
                if project_variance_days > 0:
                    # OPÓŹNIONY
                    m2_bg = "#c0392b"  # Ciemno czerwony
                    variance_text = f"+{project_variance_days}d"
                    variance_label = "OPÓŹNIENIE"
                elif project_variance_days < 0:
                    # PRZED CZASEM
                    m2_bg = "#27ae60"
                    variance_text = f"{project_variance_days}d"
                    variance_label = "PRZED CZASEM"
                else:
                    # W TERMINIE
                    m2_bg = "#27ae60"
                    variance_text = "0d"
                    variance_label = "W TERMINIE"
                
                m2 = tk.Frame(metrics_frame, bg=m2_bg, padx=20, pady=10, relief=tk.RAISED, bd=2)
                m2.pack(side=tk.LEFT, padx=10)
                tk.Label(m2, text=variance_text, bg=m2_bg, fg="white", 
                        font=("Arial", 24, "bold")).pack()
                tk.Label(m2, text=variance_label, bg=m2_bg, fg="white", 
                        font=("Arial", 9)).pack()
                
                # Daty (tooltips)
                dates_text = f"Kontrakt: {self.format_date_ddmmyyyy(expected_delivery)}\nPrognoza: {self.format_date_ddmmyyyy(forecast_completion)}"
                tk.Label(m2, text=dates_text, bg=m2_bg, fg="white", 
                        font=("Arial", 7)).pack(pady=(3, 0))
            
            elif forecast_completion and expected_delivery and not has_actual_work:
                # Projekt jeszcze nie wystartował - pokaż "Nowy harmonogram"
                m2 = tk.Frame(metrics_frame, bg="#3498db", padx=20, pady=10, relief=tk.RAISED, bd=2)
                m2.pack(side=tk.LEFT, padx=10)
                
                # Oblicz różnicę dat (ale nie nazywaj tego "opóźnieniem")
                from datetime import datetime
                exp_dt = datetime.fromisoformat(str(expected_delivery)[:10])
                fc_dt = datetime.fromisoformat(str(forecast_completion)[:10])
                diff_days = (fc_dt - exp_dt).days
                
                if diff_days > 0:
                    diff_text = f"+{diff_days}d"
                elif diff_days < 0:
                    diff_text = f"{diff_days}d"
                else:
                    diff_text = "0d"
                
                tk.Label(m2, text=diff_text, bg="#3498db", fg="white", 
                        font=("Arial", 24, "bold")).pack()
                tk.Label(m2, text="Przesunięcie harmonogramu", bg="#3498db", fg="white", 
                        font=("Arial", 9)).pack()
                
                # Daty
                dates_text = f"Kontrakt: {self.format_date_ddmmyyyy(expected_delivery)}\nNowy plan: {self.format_date_ddmmyyyy(forecast_completion)}"
                tk.Label(m2, text=dates_text, bg="#3498db", fg="white", 
                        font=("Arial", 7)).pack(pady=(3, 0))
            
            else:
                # Brak danych
                m2 = tk.Frame(metrics_frame, bg="#95a5a6", padx=20, pady=10, relief=tk.RAISED, bd=2)
                m2.pack(side=tk.LEFT, padx=10)
                tk.Label(m2, text="?", bg="#95a5a6", fg="white", 
                        font=("Arial", 24, "bold")).pack()
                tk.Label(m2, text="Brak daty dostawy", bg="#95a5a6", fg="white", 
                        font=("Arial", 9)).pack()
            
            # Metryka 3: Średnia rezerwa
            m3 = tk.Frame(metrics_frame, bg="#3498db", padx=20, pady=10, relief=tk.RAISED, bd=2)
            m3.pack(side=tk.LEFT, padx=10)
            tk.Label(m3, text=f"{avg_float:.1f}d", bg="#3498db", fg="white", 
                    font=("Arial", 24, "bold")).pack()
            tk.Label(m3, text="Średnia rezerwa", bg="#3498db", fg="white", 
                    font=("Arial", 9)).pack()
            
            # Metryka 4: Najdłuższy etap
            longest = max(details, key=lambda d: d['duration'])
            m4 = tk.Frame(metrics_frame, bg="#16a085", padx=20, pady=10, relief=tk.RAISED, bd=2)
            m4.pack(side=tk.LEFT, padx=10)
            tk.Label(m4, text=f"{longest['duration']}d", bg="#16a085", fg="white", 
                    font=("Arial", 24, "bold")).pack()
            tk.Label(m4, text=f"Najdłuższy: {longest['stage_code']}", bg="#16a085", 
                    fg="white", font=("Arial", 9)).pack()
            
            # Container dla wykresu i tabeli (split 60/40)
            container = tk.Frame(cp_win)
            container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # ===== WYKRES GANTT (lewa strona) =====
            if MATPLOTLIB_AVAILABLE:
                chart_frame = tk.Frame(container)
                chart_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
                
                fig = Figure(figsize=(8, 10), dpi=90)
                ax = fig.add_subplot(111)
                
                # Połącz etapy workflow + eventy dla wykresu
                all_chart_items = list(details) + list(details_events)
                
                # Pozycje eventów: oblicz z dat template/forecast (bo ES=0 z CPM jest bezużyteczne)
                # Znajdź datę startu projektu (najwcześniejszy forecast_start)
                project_start_dt = None
                if forecast:
                    for code, fc in forecast.items():
                        fs = fc.get('forecast_start') or fc.get('template_start')
                        if fs:
                            try:
                                dt = datetime.fromisoformat(str(fs)[:10])
                                if project_start_dt is None or dt < project_start_dt:
                                    project_start_dt = dt
                            except Exception:
                                pass
                
                # Oblicz ES dla eventów na podstawie dat
                for d in details_events:
                    if project_start_dt and forecast:
                        fc = forecast.get(d['stage_code'], {})
                        ev_start = fc.get('template_start') or fc.get('forecast_start')
                        if ev_start:
                            try:
                                ev_dt = datetime.fromisoformat(str(ev_start)[:10])
                                d['ES'] = (ev_dt - project_start_dt).days
                                d['EF'] = d['ES'] + d['duration']
                            except Exception:
                                pass
                
                # Sortuj wszystko po ES (pozycji na osi czasu)
                all_chart_items.sort(key=lambda d: d['ES'])
                
                # Sortuj odwrotnie dla wykresu (góra = pierwsza pozycja)
                all_chart_items_reversed = list(reversed(all_chart_items))
                event_codes = {d['stage_code'] for d in details_events}
                
                y_pos = range(len(all_chart_items_reversed))
                stage_names = [d['stage_code'] for d in all_chart_items_reversed]
                
                # Rysuj paski i markery
                for i, d in enumerate(all_chart_items_reversed):
                    is_event = d['stage_code'] in event_codes
                    
                    if is_event:
                        # Event = pasek 1-dniowy (fioletowy)
                        ax.barh(i, 1, left=d['ES'], height=0.6, 
                               color='#8e44ad', alpha=0.8, edgecolor='black', linewidth=1.5)
                        # Etykieta z datą
                        if project_start_dt:
                            ev_date = (project_start_dt + timedelta(days=d['ES'])).strftime('%d-%m')
                            ax.annotate(ev_date, (d['ES'] + 1, i), textcoords="offset points",
                                       xytext=(4, 0), fontsize=7, color='#8e44ad', fontweight='bold')
                    else:
                        color = '#e74c3c' if d['is_critical'] else '#3498db'
                        
                        # Główny pasek (czas trwania)
                        if d['duration'] > 0:
                            ax.barh(i, d['duration'], left=d['ES'], height=0.6, 
                                   color=color, alpha=0.8, edgecolor='black', linewidth=1.5)
                        else:
                            # Milestone (duration=0) - marker
                            ax.plot(d['ES'], i, marker='s', color=color, markersize=10, 
                                   markeredgecolor='black', markeredgewidth=1.2, zorder=5)
                        
                        # Float bar (rezerwa) - cieńszy pasek
                        if d['total_float'] > 0:
                            ax.barh(i, d['total_float'], left=d['EF'], height=0.3,
                                   color='#95a5a6', alpha=0.4, linestyle='--', 
                                   edgecolor='gray', linewidth=0.5)
                
                # Koloruj nazwy eventów
                for i, label in enumerate(ax.get_yticklabels()):
                    item = all_chart_items_reversed[i]
                    if item['stage_code'] in event_codes:
                        label.set_color('#8e44ad')
                        label.set_fontstyle('italic')
                
                # Formatowanie
                ax.set_yticks(y_pos)
                ax.set_yticklabels(stage_names, fontsize=9)
                ax.set_xlabel('Dni od startu projektu', fontsize=10, fontweight='bold')
                ax.set_title('Ścieżka krytyczna (CPM) - wykres Gantt', 
                            fontsize=12, fontweight='bold', pad=15)
                ax.grid(axis='x', alpha=0.3, linestyle='--')
                ax.set_axisbelow(True)
                
                # Legenda
                from matplotlib.patches import Patch
                from matplotlib.lines import Line2D
                legend_elements = [
                    Patch(facecolor='#e74c3c', alpha=0.8, label='Bez rezerwy (opóźnienie → opóźnia projekt)'),
                    Patch(facecolor='#3498db', alpha=0.8, label='Ma rezerwę (może się opóźnić)'),
                    Patch(facecolor='#95a5a6', alpha=0.4, label='Rezerwa czasowa (float)'),
                    Line2D([0], [0], marker='D', color='w', markerfacecolor='#8e44ad', 
                           markersize=8, markeredgecolor='black', label='Event (milestone info)')
                ]
                ax.legend(handles=legend_elements, loc='upper right', fontsize=8)
                
                fig.tight_layout()
                
                canvas = FigureCanvasTkAgg(fig, chart_frame)
                canvas.draw()
                canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            
            # ===== TABELA (prawa strona) =====
            table_frame = tk.Frame(container)
            table_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
            
            tk.Label(table_frame, text="Szczegóły CPM", font=("Arial", 11, "bold"),
                    bg="#ecf0f1", pady=8).pack(fill=tk.X)
            
            # Treeview z danymi
            tree_scroll = tk.Scrollbar(table_frame, orient=tk.VERTICAL)
            tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            columns = ('stage', 'duration', 'float', 'status')
            tree = ttk.Treeview(table_frame, columns=columns, show='headings',
                               yscrollcommand=tree_scroll.set, height=25)
            tree_scroll.config(command=tree.yview)
            
            tree.heading('stage', text='Etap')
            tree.heading('duration', text='Czas [d]')
            tree.heading('float', text='Rezerwa [d]')
            tree.heading('status', text='Status')
            
            tree.column('stage', width=140, anchor='w')
            tree.column('duration', width=70, anchor='center')
            tree.column('float', width=80, anchor='center')
            tree.column('status', width=110, anchor='center')
            
            # Wstaw dane (krytyczne na górze)
            for d in details:
                status = '⚠️ Bez rezerwy' if d['is_critical'] else '✅ Ma rezerwę'
                float_str = '0' if d['is_critical'] else str(d['total_float'])
                
                tree.insert('', tk.END, values=(
                    d['stage_code'],
                    d['duration'],
                    float_str,
                    status
                ), tags=('critical' if d['is_critical'] else 'normal',))
            
            # Wiszące eventy (milestones informacyjne bez zależności)
            if details_events:
                tree.insert('', tk.END, values=('── Eventy ──', '', '', ''), tags=('separator',))
                for d in details_events:
                    tree.insert('', tk.END, values=(
                        d['stage_code'],
                        d['duration'],
                        '—',
                        '📌 Event'
                    ), tags=('event',))
            
            # Kolory wierszy
            tree.tag_configure('critical', background='#fff3e0', foreground='#e65100')
            tree.tag_configure('normal', background='#e8f5e9', foreground='#2e7d32')
            tree.tag_configure('event', background='#f5f5f5', foreground='#9e9e9e')
            tree.tag_configure('separator', background='#e0e0e0', foreground='#757575')
            
            tree.pack(fill=tk.BOTH, expand=True)
            
            # Info box
            info_frame = tk.Frame(table_frame, bg="#ecf0f1", pady=8)
            info_frame.pack(fill=tk.X)
            
            info_text = (
                f"💡 Rezerwa (Float) = ile dni można opóźnić etap bez wpływu na termin projektu\n"
                f"🔴 Etapy z rezerwą 0 = KRYTYCZNE (każde opóźnienie przesuwa cały projekt)\n"
                f"🟢 Etapy z rezerwą > 0 = można elastycznie planować"
            )
            tk.Label(info_frame, text=info_text, bg="#ecf0f1", fg="#34495e",
                    font=("Arial", 8), justify=tk.LEFT, anchor='w').pack(padx=10, fill=tk.X)
            
            # Przyciski
            btn_frame = tk.Frame(cp_win, bg="white", pady=10)
            btn_frame.pack(fill=tk.X)
            
            tk.Button(btn_frame, text="📋 Eksport do CSV", 
                     command=lambda: self._export_cpm_csv(details),
                     bg="#3498db", fg="white", font=("Arial", 10), 
                     padx=15, pady=5).pack(side=tk.LEFT, padx=10)
            
            tk.Button(btn_frame, text="❌ Zamknij", command=cp_win.destroy,
                     bg="#95a5a6", fg="white", font=("Arial", 10),
                     padx=15, pady=5).pack(side=tk.RIGHT, padx=10)
            
            self.status_bar.config(text="🟢 Ścieżka krytyczna obliczona (CPM)", fg="#27ae60")
            
        except Exception as e:
            self.status_bar.config(text="🔴 Błąd ścieżki krytycznej", fg="#e74c3c")
            messagebox.showerror("❌ Błąd", f"Nie można obliczyć ścieżki krytycznej:\n{e}")
            import traceback
            traceback.print_exc()
    
    def _export_cpm_csv(self, details):
        """Eksportuj dane CPM do CSV"""
        try:
            filepath = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialfile=f"cpm_project_{self.selected_project_id}.csv"
            )
            if not filepath:
                return
            
            import csv
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['Etap', 'Czas [dni]', 'ES', 'EF', 'LS', 'LF', 
                                'Rezerwa [dni]', 'Krytyczny'])
                for d in details:
                    writer.writerow([
                        d['stage_code'],
                        d['duration'],
                        d['ES'],
                        d['EF'],
                        d['LS'],
                        d['LF'],
                        d['total_float'],
                        'TAK' if d['is_critical'] else 'NIE'
                    ])
            
            messagebox.showinfo("✅ Eksport", f"Zapisano do:\n{filepath}")
        except Exception as e:
            messagebox.showerror("❌ Błąd eksportu", str(e))
    
    def edit_dates_dialog(self):
        """Dialog edycji dat szablonu i prognozy"""
        if not self._has_permission('can_edit_dates'):
            messagebox.showerror(
                "🚫 Brak uprawnień",
                f"Twoja rola [{self.current_user_role}] nie ma prawa do edycji dat."
            )
            return
        if not self.selected_project_id:
            messagebox.showwarning("⚠️ Uwaga", "Wybierz projekt")
            return
        
        # Zamknij poprzednie okno jeśli istnieje
        if self.edit_window and self.edit_window.winfo_exists():
            self.edit_window.destroy()
        
        # Nowe okno
        self.edit_window = tk.Toplevel(self.root)
        self.edit_window.transient(self.root)  # Okno na tym samym ekranie co główna aplikacja
        self.edit_window.title(f"Edycja dat - Projekt {self.selected_project_id}")
        self.edit_window.resizable(True, True)
        self.restore_window_geometry('edit_dates_window', self.edit_window, 900, 600)
        
        # Zapisz geometrię przy zamykaniu
        def on_close():
            self.save_window_geometry('edit_dates_window', self.edit_window)
            self.edit_window.destroy()
        self.edit_window.protocol("WM_DELETE_WINDOW", on_close)
        
        # Header
        header = tk.Label(
            self.edit_window,
            text=f"EDYCJA DAT SZABLONU I PROGNOZY\nProjekt: {self.selected_project_id}",
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 12, "bold"),
            pady=10
        )
        header.pack(fill=tk.X)
        
        # Frame z tabelą
        table_frame = tk.Frame(self.edit_window)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Scrollbar
        canvas = tk.Canvas(table_frame)
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Pobierz dane
        try:
            forecast = rmm.recalculate_forecast(self.get_project_db_path(self.selected_project_id), self.selected_project_id)
            
            # Słownik do przechowywania Entry widgets
            self.date_entries = {}
            
            # Nagłówki
            headers = ["Etap", "Szablon Start", "Szablon Koniec", "Prognoza Start", "Prognoza Koniec"]
            for col, header in enumerate(headers):
                lbl = tk.Label(
                    scrollable_frame,
                    text=header,
                    font=self.FONT_BOLD,
                    bg="#ecf0f1",
                    relief=tk.RAISED,
                    padx=10,
                    pady=5
                )
                lbl.grid(row=0, column=col, sticky="ew", padx=1, pady=1)
            
            # Wiersze z danymi
            row = 1
            for stage_code, fc in forecast.items():
                # Etap
                tk.Label(
                    scrollable_frame,
                    text=stage_code,
                    font=self.FONT_DEFAULT,
                    anchor="w",
                    padx=5
                ).grid(row=row, column=0, sticky="ew", padx=1, pady=1)
                
                # Szablon Start - konwersja z ISO do DD-MM-YYYY
                col_idx = 1
                cell_frame = tk.Frame(scrollable_frame)
                cell_frame.grid(row=row, column=col_idx, padx=1, pady=1)
                
                template_start = tk.Entry(cell_frame, width=12, font=self.FONT_DEFAULT)
                template_start.insert(0, self.format_date_ddmmyyyy(fc.get('template_start')) or '')
                template_start.pack(side=tk.LEFT, padx=1)
                
                tk.Button(
                    cell_frame,
                    text="📅",
                    command=lambda e=template_start: self.open_calendar_picker(e),
                    bg="#3498db",
                    fg="white",
                    font=("Arial", 7),
                    padx=2,
                    pady=0
                ).pack(side=tk.LEFT)
                
                # Szablon Koniec
                col_idx = 2
                cell_frame = tk.Frame(scrollable_frame)
                cell_frame.grid(row=row, column=col_idx, padx=1, pady=1)
                
                template_end = tk.Entry(cell_frame, width=12, font=self.FONT_DEFAULT)
                template_end.insert(0, self.format_date_ddmmyyyy(fc.get('template_end')) or '')
                template_end.pack(side=tk.LEFT, padx=1)
                
                tk.Button(
                    cell_frame,
                    text="📅",
                    command=lambda e=template_end: self.open_calendar_picker(e),
                    bg="#3498db",
                    fg="white",
                    font=("Arial", 7),
                    padx=2,
                    pady=0
                ).pack(side=tk.LEFT)
                
                # Prognoza Start
                col_idx = 3
                cell_frame = tk.Frame(scrollable_frame)
                cell_frame.grid(row=row, column=col_idx, padx=1, pady=1)
                
                forecast_start = tk.Entry(cell_frame, width=12, font=self.FONT_DEFAULT)
                forecast_start.insert(0, self.format_date_ddmmyyyy(fc.get('forecast_start')) or '')
                forecast_start.pack(side=tk.LEFT, padx=1)
                
                tk.Button(
                    cell_frame,
                    text="📅",
                    command=lambda e=forecast_start: self.open_calendar_picker(e),
                    bg="#3498db",
                    fg="white",
                    font=("Arial", 7),
                    padx=2,
                    pady=0
                ).pack(side=tk.LEFT)
                
                # Prognoza Koniec
                col_idx = 4
                cell_frame = tk.Frame(scrollable_frame)
                cell_frame.grid(row=row, column=col_idx, padx=1, pady=1)
                
                forecast_end = tk.Entry(cell_frame, width=12, font=self.FONT_DEFAULT)
                forecast_end.insert(0, self.format_date_ddmmyyyy(fc.get('forecast_end')) or '')
                forecast_end.pack(side=tk.LEFT, padx=1)
                
                tk.Button(
                    cell_frame,
                    text="📅",
                    command=lambda e=forecast_end: self.open_calendar_picker(e),
                    bg="#3498db",
                    fg="white",
                    font=("Arial", 7),
                    padx=2,
                    pady=0
                ).pack(side=tk.LEFT)
                
                # Zapisz referencje
                self.date_entries[stage_code] = {
                    'template_start': template_start,
                    'template_end': template_end,
                    'forecast_start': forecast_start,
                    'forecast_end': forecast_end
                }
                
                row += 1
            
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
        except Exception as e:
            messagebox.showerror("❌ Błąd", f"Nie można załadować dat:\n{e}")
            self.edit_window.destroy()
            return
        
        # Przyciski
        btn_frame = tk.Frame(self.edit_window)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(
            btn_frame,
            text="💾 Zapisz",
            command=self.save_dates,
            bg=self.COLOR_GREEN,
            fg="white",
            font=self.FONT_BOLD,
            padx=20,
            pady=8
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="❌ Anuluj",
            command=on_close,
            bg=self.COLOR_RED,
            fg="white",
            font=self.FONT_BOLD,
            padx=20,
            pady=8
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Label(
            btn_frame,
            text="Format dat: DD-MM-YYYY (np. 01-04-2026)",
            font=self.FONT_SMALL,
            fg="gray"
        ).pack(side=tk.RIGHT, padx=5)
    
    def save_dates(self):
        """Zapisz zmodyfikowane daty do bazy"""
        try:
            _pdb = self.get_project_db_path(self.selected_project_id)
            con = rmm._open_rm_connection(_pdb, row_factory=False)
            
            for stage_code, entries in self.date_entries.items():
                template_start = entries['template_start'].get().strip()
                template_end = entries['template_end'].get().strip()
                
                # Walidacja i konwersja DD-MM-YYYY → YYYY-MM-DD (ISO)
                valid_start, template_start_iso = self.validate_and_convert_date(template_start)
                if not valid_start:
                    messagebox.showerror("❌ Błąd walidacji", template_start_iso)
                    con.close()
                    return
                
                valid_end, template_end_iso = self.validate_and_convert_date(template_end)
                if not valid_end:
                    messagebox.showerror("❌ Błąd walidacji", template_end_iso)
                    con.close()
                    return
                
                # Walidacja logiczna: koniec >= początek (tylko jeśli obie daty są podane)
                if template_start_iso and template_end_iso:
                    if template_end_iso < template_start_iso:
                        messagebox.showerror(
                            "❌ Błąd logiczny",
                            f"Etap {stage_code}:\nData końcowa ({template_end}) nie może być wcześniejsza\nniż data początkowa ({template_start})!"
                        )
                        con.close()
                        return
                
                # UPDATE stage_schedule (szablon) - zapisz w formacie ISO
                con.execute("""
                    UPDATE stage_schedule
                    SET template_start = ?, template_end = ?
                    WHERE project_stage_id = (
                        SELECT id FROM project_stages
                        WHERE project_id = ? AND stage_code = ?
                    )
                """, (template_start_iso, template_end_iso, self.selected_project_id, stage_code))
            
            con.commit()
            con.close()
            
            # Przelicz prognozę
            rmm.recalculate_forecast(_pdb, self.selected_project_id)
            
            # Zamknij okno (zapisując geometrię)
            self.save_window_geometry('edit_dates_window', self.edit_window)
            self.edit_window.destroy()
            
            # Odśwież widoki
            self.refresh_all()
            
            self.status_bar.config(text="💾 Daty zapisane i prognoza przeliczona", fg="#27ae60")
            
        except Exception as e:
            messagebox.showerror("❌ Błąd", f"Nie można zapisać dat:\n{e}")

    def cleanup_empty_dates_ui(self):
        """Wyczyść puste stringi z stage_schedule (konwertuj na NULL)"""
        try:
            # Pytaj o potwierdzenie
            if not messagebox.askyesno(
                "🧹 Wyczyść puste daty",
                "Ta operacja zastąpi wszystkie puste stringi ('') w kolumnach template_start i template_end wartością NULL.\n\n"
                "Dotyczy WSZYSTKICH projektów w bazie RM_MANAGER.\n\n"
                "Czy kontynuować?"
            ):
                return
            
            # Otwórz każdą bazę projektu i wyczyść
            pattern = os.path.join(self.rm_projects_dir, "rm_manager_project_*.sqlite")
            project_dbs = glob.glob(pattern)
            
            if not project_dbs:
                messagebox.showinfo("ℹ️ Info", "Nie znaleziono żadnych baz projektów RM_MANAGER")
                return
            
            cleaned_count = 0
            project_count = 0
            
            for pdb_path in project_dbs:
                try:
                    con = rmm._open_rm_connection(pdb_path, row_factory=False)
                    cur = con.cursor()
                    
                    # Znajdź puste stringi
                    cur.execute("""
                        SELECT COUNT(*) FROM stage_schedule
                        WHERE template_start = '' OR template_end = ''
                    """)
                    empty_count = cur.fetchone()[0]
                    
                    if empty_count > 0:
                        # Wyczyść
                        cur.execute("""
                            UPDATE stage_schedule
                            SET template_start = NULL
                            WHERE template_start = ''
                        """)
                        cur.execute("""
                            UPDATE stage_schedule
                            SET template_end = NULL
                            WHERE template_end = ''
                        """)
                        con.commit()
                        cleaned_count += empty_count
                        project_count += 1
                    
                    con.close()
                    
                except Exception as e:
                    print(f"Błąd czyszczenia {pdb_path}: {e}")
                    continue
            
            # Pokaż wynik
            messagebox.showinfo(
                "✅ Wyczyszczono",
                f"Wyczyszczono {cleaned_count} pustych dat w {project_count} projektach"
            )
            
            # Odśwież widok jeśli projekt jest wybrany
            if self.selected_project_id:
                self.refresh_all()
                
        except Exception as e:
            messagebox.showerror("❌ Błąd", f"Nie można wyczyścić dat:\n{e}")

    # ========================================================================
    # SYSTEM NOTATEK - Okno notatnika dla etapów
    # ========================================================================

    def show_notes_window(self, stage_code: str = None, topic_index: int = None):
        """Otwórz okno notatnika dla wybranego etapu (read-only gdy brak locka)"""
        if not self.selected_project_id:
            messagebox.showwarning("Brak projektu", "Wybierz projekt")
            return
        
        project_db = self.get_project_db_path(self.selected_project_id)
        
        # Sprawdź czy użytkownik ma lock (określi tryb przeglądania vs edycji)
        can_edit = self.have_lock and not self.read_only_mode
        
        # Okno główne
        notes_win = tk.Toplevel(self.root)
        notes_win.can_edit = can_edit  # Zapisz flagę edycji jako atrybut okna
        notes_win.transient(self.root)  # Okno zawsze na tym samym ekranie co główna aplikacja
        title_suffix = " (READ-ONLY)" if not can_edit else ""
        notes_win.title(f"📝 Notatki - Projekt {self.selected_project_id}{title_suffix}")
        notes_win.resizable(True, True)
        self.restore_window_geometry('notes_window', notes_win, 1200, 700)
        
        # Zapisz geometrię przy zamykaniu (tylko gdy NIE jest zmaksymalizowane)
        def on_close():
            state = notes_win.state()
            if state not in ('zoomed', 'iconic'):
                self.save_window_geometry('notes_window', notes_win)
            notes_win.destroy()
            # Przywróć focus na główne okno aplikacji
            self.root.lift()
            self.root.focus_force()
        notes_win.protocol("WM_DELETE_WINDOW", on_close)
        
        # Top bar - wybór etapu
        top_frame = tk.Frame(notes_win, bg=self.COLOR_TOPBAR, pady=10)
        top_frame.pack(fill=tk.X)
        
        tk.Label(
            top_frame,
            text="Etap:",
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=self.FONT_BOLD
        ).pack(side=tk.LEFT, padx=(10, 5))
        
        # Pobierz listę etapów
        con = rmm._open_rm_connection(project_db)
        stages = con.execute("""
            SELECT code, display_name 
            FROM stage_definitions
        """).fetchall()
        con.close()
        
        # Sortuj wg DEFAULT_STAGE_SEQUENCE
        seq_map = {code: idx for idx, code in enumerate(DEFAULT_STAGE_SEQUENCE)}
        stages = sorted(stages, key=lambda s: seq_map.get(s['code'], 999))
        
        stage_choices = [f"{s['code']} - {s['display_name']}" for s in stages]
        selected_stage = tk.StringVar()
        
        if stage_code:
            for choice in stage_choices:
                if choice.startswith(stage_code):
                    selected_stage.set(choice)
                    break
        
        stage_combo = ttk.Combobox(
            top_frame,
            textvariable=selected_stage,
            values=stage_choices,
            width=30,
            state='readonly'
        )
        stage_combo.pack(side=tk.LEFT, padx=5)
        
        # Main container - split view
        main_container = tk.PanedWindow(notes_win, orient=tk.HORIZONTAL)
        main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # ── LEWY PANEL: Lista tematów ──────────────────────────────
        left_frame = tk.Frame(main_container, bg="white")
        main_container.add(left_frame, width=400)
        
        # Header tematów
        topics_header = tk.Frame(left_frame, bg=self.COLOR_PURPLE, pady=5)
        topics_header.pack(fill=tk.X)
        
        tk.Label(
            topics_header,
            text="📚 TEMATY",
            bg=self.COLOR_PURPLE,
            fg="white",
            font=self.FONT_BOLD
        ).pack(side=tk.LEFT, padx=10)
        
        # Przycisk dodawania tematu
        add_topic_btn = tk.Button(
            topics_header,
            text="➕ Nowy temat",
            command=lambda: self.add_new_topic(project_db, selected_stage, topics_list),
            bg=self.COLOR_GREEN,
            fg="white",
            font=self.FONT_SMALL,
            state=tk.NORMAL if can_edit else tk.DISABLED
        )
        add_topic_btn.pack(side=tk.RIGHT, padx=10)
        
        # Lista tematów
        topics_frame = tk.Frame(left_frame)
        topics_frame.pack(fill=tk.BOTH, expand=True)
        
        topics_scroll = tk.Scrollbar(topics_frame)
        topics_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        topics_list = tk.Listbox(
            topics_frame,
            yscrollcommand=topics_scroll.set,
            font=("Arial", 10),
            selectmode=tk.SINGLE,
            bg="white"
        )
        topics_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        topics_scroll.config(command=topics_list.yview)
        
        # ── Pasek akcji tematów (pod listą) ──────────────────────────────
        topic_btn_bar = tk.Frame(left_frame, bg="#e8e8e8", pady=4)
        topic_btn_bar.pack(fill=tk.X)
        
        def _move_topic(direction):
            sel = topics_list.curselection()
            if not sel:
                return
            idx = sel[0]
            if not hasattr(topics_list, 'topics_data') or idx >= len(topics_list.topics_data):
                return
            topic = topics_list.topics_data[idx]
            stage_text = selected_stage.get()
            if not stage_text:
                return
            stage_code = stage_text.split(" - ")[0].strip()
            rmm.move_topic(project_db, self.selected_project_id, stage_code, topic['id'], direction)
            self.refresh_topics_list(project_db, selected_stage, topics_list)
            # Przywróć zaznaczenie
            new_idx = idx
            if direction == 'up' and idx > 0:
                new_idx = idx - 1
            elif direction == 'down' and idx < topics_list.size() - 1:
                new_idx = idx + 1
            elif direction == 'top':
                new_idx = 0
            elif direction == 'bottom':
                new_idx = topics_list.size() - 1
            if topics_list.size() > 0:
                topics_list.selection_set(new_idx)
                topics_list.see(new_idx)
        
        tk.Button(
            topic_btn_bar, text="⏫", command=lambda: _move_topic('top'),
            font=("Arial", 8), width=3, relief=tk.FLAT,
            state=tk.NORMAL if can_edit else tk.DISABLED
        ).pack(side=tk.LEFT, padx=1)
        
        tk.Button(
            topic_btn_bar, text="⬆️", command=lambda: _move_topic('up'),
            font=("Arial", 8), width=3, relief=tk.FLAT,
            state=tk.NORMAL if can_edit else tk.DISABLED
        ).pack(side=tk.LEFT, padx=1)
        
        tk.Button(
            topic_btn_bar, text="⬇️", command=lambda: _move_topic('down'),
            font=("Arial", 8), width=3, relief=tk.FLAT,
            state=tk.NORMAL if can_edit else tk.DISABLED
        ).pack(side=tk.LEFT, padx=1)
        
        tk.Button(
            topic_btn_bar, text="⏬", command=lambda: _move_topic('bottom'),
            font=("Arial", 8), width=3, relief=tk.FLAT,
            state=tk.NORMAL if can_edit else tk.DISABLED
        ).pack(side=tk.LEFT, padx=1)
        
        tk.Label(topic_btn_bar, text=" ", bg="#e8e8e8").pack(side=tk.LEFT, padx=3)
        
        priority_btn = tk.Button(
            topic_btn_bar, text="🏷️ Priorytet",
            command=lambda: self.change_topic_priority(project_db, selected_stage, topics_list, notes_container, topic_title_label),
            font=("Arial", 8), relief=tk.FLAT,
            state=tk.NORMAL if can_edit else tk.DISABLED
        )
        priority_btn.pack(side=tk.LEFT, padx=1)
        
        topic_alarm_btn = tk.Button(
            topic_btn_bar, text="⏰ Alarm",
            command=lambda: self.add_alarm_to_topic(project_db, topics_list),
            font=("Arial", 8), relief=tk.FLAT,
            state=tk.NORMAL if can_edit else tk.DISABLED
        )
        topic_alarm_btn.pack(side=tk.LEFT, padx=1)
        
        topic_delete_btn = tk.Button(
            topic_btn_bar, text="🗑️ Usuń",
            command=lambda: self.delete_topic(project_db, topics_list, notes_container),
            bg=self.COLOR_RED, fg="white", font=("Arial", 8), relief=tk.FLAT,
            state=tk.NORMAL if can_edit else tk.DISABLED
        )
        topic_delete_btn.pack(side=tk.RIGHT, padx=3)
        
        # ── PRAWY PANEL: Notatki i szczegóły tematu ──────────────────
        right_frame = tk.Frame(main_container, bg="white")
        main_container.add(right_frame)
        
        # Header notatek
        notes_header = tk.Frame(right_frame, bg=self.COLOR_TOPBAR, pady=5)
        notes_header.pack(fill=tk.X)
        
        topic_title_label = tk.Label(
            notes_header,
            text="📝 NOTATKI",
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=self.FONT_BOLD
        )
        topic_title_label.pack(side=tk.LEFT, padx=10)
        
        # Przycisk dodawania notatki
        add_note_btn= tk.Button(
            notes_header,
            text="➕ Nowa notatka",
            command=lambda: self.add_new_note(project_db, topics_list, notes_container, topic_title_label),
            bg=self.COLOR_GREEN,
            fg="white",
            font=self.FONT_SMALL,
            state=tk.DISABLED if not can_edit else tk.DISABLED  # Zawsze disabled na start, włącza się gdy wybrano temat
        )
        add_note_btn.pack(side=tk.RIGHT, padx=10)
        
        # Buttony zarządzania tematem
        topic_actions = tk.Frame(notes_header, bg=self.COLOR_TOPBAR)
        topic_actions.pack(side=tk.RIGHT, padx=(0, 10))
        
        edit_topic_btn = tk.Button(
            topic_actions,
            text="✏️ Edytuj temat",
            command=lambda: self.edit_topic(project_db, topics_list, topic_title_label, selected_stage),
            bg=self.COLOR_ORANGE,
            fg="white",
            font=self.FONT_SMALL,
            state=tk.DISABLED
        )
        edit_topic_btn.pack(side=tk.LEFT, padx=2)
        
        # Scrollable container dla notatek
        notes_outer = tk.Frame(right_frame)
        notes_outer.pack(fill=tk.BOTH, expand=True)
        
        notes_canvas = tk.Canvas(notes_outer, bg="white")
        notes_scroll = tk.Scrollbar(notes_outer, orient=tk.VERTICAL, command=notes_canvas.yview)
        
        notes_container = tk.Frame(notes_canvas, bg="white")
        notes_container_id = notes_canvas.create_window((0, 0), window=notes_container, anchor='nw')
        
        # Śledzenie obecnie edytowanej notatki
        notes_container._currently_editing = None
        
        notes_canvas.configure(yscrollcommand=notes_scroll.set)
        notes_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        notes_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        def on_frame_configure(event):
            notes_canvas.configure(scrollregion=notes_canvas.bbox("all"))
        
        notes_container.bind("<Configure>", on_frame_configure)
        
        # Handler kliknięcia na puste pole w oknie notatek - zamyka edycję
        def close_note_edit_on_empty_click(event):
            """Zamknij edycję notatki gdy kliknięto na puste pole"""
            # Sprawdź czy kliknięcie było bezpośrednio na canvas lub container
            # (nie propagowane z dziecka)
            if event.widget in (notes_canvas, notes_container):
                # Sprawdź czy jest jakaś aktywna edycja
                for note_widget in notes_container.winfo_children():
                    if isinstance(note_widget, tk.LabelFrame):
                        for child in note_widget.winfo_children():
                            if isinstance(child, tk.Text):
                                if str(child.cget('state')) == 'normal':
                                    # Jest aktywna edycja - przenieś focus gdzie indziej
                                    # aby wywołać FocusOut
                                    notes_win.focus_set()
                                    return
        
        notes_canvas.bind("<Button-1>", close_note_edit_on_empty_click, add=True)
        notes_container.bind("<Button-1>", close_note_edit_on_empty_click, add=True)
        
        def on_canvas_configure(event):
            notes_canvas.itemconfig(notes_container_id, width=event.width)
        
        notes_canvas.bind("<Configure>", on_canvas_configure)
        
        # Store references
        notes_win.topics_list = topics_list
        notes_win.notes_container = notes_container
        notes_win.add_note_btn = add_note_btn
        notes_win.edit_topic_btn = edit_topic_btn
        notes_win.topic_title_label = topic_title_label
        notes_win.notes_canvas = notes_canvas
        
        # Inicjalizuj _last_selection i _last_stage_value
        topics_list._last_selection = None
        selected_stage._last_value = selected_stage.get()
        
        # Event handlers
        def check_unsaved_edits():
            """Sprawdź czy są niezapisane zmiany w edycji notatek. Zwraca True jeśli można kontynuować."""
            edited_widgets = []  # Text widgets które są w trybie edycji
            
            for widget in notes_container.winfo_children():
                # Szukaj LabelFrame (note_frame)
                if isinstance(widget, tk.LabelFrame):
                    for child in widget.winfo_children():
                        # Szukaj Text widget
                        if isinstance(child, tk.Text):
                            # Sprawdź czy jest w trybie edycji
                            if str(child.cget('state')) == 'normal':
                                edited_widgets.append(child)
            
            # Jeśli nie ma edytowanych widgetów - OK
            if not edited_widgets:
                return True
            
            # Tymczasowo wyłącz FocusOut dla wszystkich edytowanych widgetów
            # aby uniknąć podwójnego zapytania
            for widget in edited_widgets:
                widget.unbind("<FocusOut>")
            
            try:
                for widget in edited_widgets:
                    # Porównaj zawartość z oryginalną
                    current_content = widget.get(1.0, tk.END).strip()
                    original_content = getattr(widget, '_original_content', '')
                    
                    if current_content != original_content:
                        # Treść zmieniona - zapytaj użytkownika
                        response = messagebox.askyesnocancel(
                            "Niezapisane zmiany",
                            "Notatka została zmieniona.\n\nCzy zapisać zmiany?",
                            icon='question',
                            parent=notes_win
                        )
                        if response is True:  # Tak - zapisz
                            # Wywołaj save_callback jeśli istnieje
                            save_callback = getattr(widget, '_save_callback', None)
                            if save_callback and callable(save_callback):
                                if not save_callback():
                                    # Błąd zapisu - przywroć FocusOut i zatrzymaj
                                    return False
                            # Zapisano - kontynuuj (nie przywracaj FocusOut)
                        elif response is False:  # Nie - odrzuć zmiany
                            # Kontynuuj, zmiany zostaną odrzucone (nie przywracaj FocusOut)
                            pass
                        else:  # Anuluj (None)
                            # Przywroć FocusOut dla wszystkich widgetów
                            for w in edited_widgets:
                                # Znajdź funkcję on_focus_out dla tego widgetu
                                focus_out_handler = getattr(w, '_focus_out_handler', None)
                                if focus_out_handler:
                                    w.bind("<FocusOut>", focus_out_handler)
                            return False  # Zatrzymaj zmianę tematu
                
                return True  # Brak zmian lub wszystko OK
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                # W razie błędu przywroć FocusOut
                for w in edited_widgets:
                    focus_out_handler = getattr(w, '_focus_out_handler', None)
                    if focus_out_handler:
                        w.bind("<FocusOut>", focus_out_handler)
                return False
        
        def on_stage_changed(event=None):
            if not check_unsaved_edits():
                # Przywróć poprzedni etap
                selected_stage.set(selected_stage._last_value)
                return
            
            # Zapisz nowy etap jako ostatni
            selected_stage._last_value = selected_stage.get()
            
            self.refresh_topics_list(project_db, selected_stage, topics_list)
            # Wyczyść notatki
            for widget in notes_container.winfo_children():
                widget.destroy()
            topic_title_label.config(text="📝 NOTATKI")
            add_note_btn.config(state=tk.DISABLED)
            edit_topic_btn.config(state=tk.DISABLED)
        
        def on_topic_selected(event=None):
            # Pobierz nową selekcję
            sel = topics_list.curselection()
            new_selection = sel[0] if sel else None
            
            # Jeśli to ten sam temat - nie rób nic
            if new_selection == topics_list._last_selection:
                return
            
            # Sprawdź czy są niezapisane zmiany przed zmianą tematu
            if not check_unsaved_edits():
                # Anuluj zmianę selekcji - przywróć poprzednią
                topics_list.selection_clear(0, tk.END)
                if topics_list._last_selection is not None:
                    topics_list.selection_set(topics_list._last_selection)
                return
            
            # Zapisz nową selekcję
            topics_list._last_selection = new_selection
            
            self.load_topic_notes(project_db, topics_list, notes_container, topic_title_label, notes_win)
            add_note_btn.config(state=tk.NORMAL)
            edit_topic_btn.config(state=tk.NORMAL)
        
        def on_topic_click(event):
            """Handler kliknięcia na listę tematów - zamyka edycję gdy kliknięto na pustą przestrzeń"""
            # Pobierz index najbliższego elementu pod kursorem
            index = topics_list.nearest(event.y)
            
            # Sprawdź czy kliknięcie było na rzeczywistym elemencie
            if index >= 0 and index < topics_list.size():
                bbox = topics_list.bbox(index)
                if bbox:
                    x, y, width, height = bbox
                    # Jeśli Y kliknięcia jest poza bboxem elementu - kliknięto na pustą przestrzeń
                    if event.y < y or event.y > y + height:
                        # Zamknij edycję jeśli jest aktywna
                        if hasattr(notes_container, '_currently_editing'):
                            currently_editing = notes_container._currently_editing
                            if currently_editing and currently_editing.winfo_exists() and str(currently_editing.cget('state')) == 'normal':
                                # Wyłącz FocusOut aby uniknąć podwójnego zapytania
                                currently_editing.unbind("<FocusOut>")
                                
                                focus_out_handler = getattr(currently_editing, '_focus_out_handler', None)
                                if focus_out_handler and callable(focus_out_handler):
                                    focus_out_handler(None)
                                    # Jeśli użytkownik anulował - przywróć binding
                                    if currently_editing.winfo_exists() and str(currently_editing.cget('state')) == 'normal':
                                        currently_editing.bind("<FocusOut>", focus_out_handler)
                        
                        # NIE zmieniaj selekcji - zatrzymaj propagację
                        return "break"
            
            # Kliknięcie na rzeczywisty element - pozwól normalnie działać
            # Listbox sam zmieni selekcję i wywoła <<ListboxSelect>>
        
        stage_combo.bind('<<ComboboxSelected>>', on_stage_changed)
        topics_list.bind('<<ListboxSelect>>', on_topic_selected)
        topics_list.bind('<Button-1>', on_topic_click)
        
        # Inicjalne załadowanie
        if selected_stage.get():
            on_stage_changed()
            # Autoselekcja tematu jeśli podano topic_index
            if topic_index is not None and topics_list.size() > topic_index:
                topics_list.selection_set(topic_index)
                topics_list.see(topic_index)
                on_topic_selected()
        
        # Drag-and-drop na okno notatek - drop dodaje załącznik do wybranej notatki
        if HAS_DND:
            try:
                def handle_notes_drop(event):
                    # Sprawdź czy jest wybrany temat
                    sel = topics_list.curselection()
                    if not sel or not hasattr(topics_list, 'topics_data'):
                        messagebox.showwarning("Brak tematu", "Wybierz temat z listy aby dodać załącznik")
                        return
                    
                    topic = topics_list.topics_data[sel[0]]
                    topic_id = topic['id']
                    
                    # Pobierz notatki tego tematu
                    notes = rmm.get_notes(project_db, topic_id)
                    if not notes:
                        messagebox.showwarning("Brak notatki", "Dodaj notatke do tematu aby móc dodać załącznik")
                        return
                    
                    # Użyj ostatniej notatki jako domyślnej
                    target_note = notes[-1]
                    
                    # Parsuj pliki
                    files = []
                    try:
                        files = notes_win.tk.splitlist(event.data)
                    except Exception:
                        import re
                        files = re.findall(r'\{([^}]+)\}|(\S+)', event.data)
                        files = [f[0] if f[0] else f[1] for f in files]
                    
                    added = 0
                    for file_path in files:
                        file_path = file_path.strip('{}').strip()
                        if not file_path:
                            continue
                        try:
                            import os
                            if not os.path.exists(file_path):
                                continue
                            file_size = os.path.getsize(file_path)
                            if file_size > 10 * 1024 * 1024:
                                messagebox.showwarning("Plik za duży", f"{os.path.basename(file_path)}: {file_size/1024/1024:.1f} MB\nMax: 10 MB")
                                continue
                            rmm.add_attachment(project_db, target_note['id'], file_path, uploaded_by=self.current_user)
                            added += 1
                            print(f"✅ Załącznik dodany do notatki {target_note['id']}: {os.path.basename(file_path)}")
                        except Exception as e:
                            import traceback
                            traceback.print_exc()
                    
                    if added > 0:
                        # Odśwież widok notatek
                        self.load_topic_notes(project_db, topics_list, notes_container, topic_title_label, notes_win)
                        self.status_bar.config(text=f"✅ Dodano {added} załącznik(ów)", fg=self.COLOR_GREEN)
                
                notes_win.drop_target_register(DND_FILES)
                notes_win.dnd_bind('<<Drop>>', handle_notes_drop)
                print("✅ DnD włączony dla okna notatek")
                
                # Fix: przy pierwszym DnD okno traci focus - przywróć po 100ms
                def restore_focus():
                    try:
                        notes_win.lift()
                        notes_win.focus_force()
                    except:
                        pass
                notes_win.after(100, restore_focus)
            except Exception as ex:
                print(f"⚠️ DnD okno notatek: {ex}")
                on_topic_selected()

    def refresh_topics_list(self, project_db: str, selected_stage: tk.StringVar, topics_list: tk.Listbox):
        """Odśwież listę tematów dla wybranego etapu"""
        stage_text = selected_stage.get()
        if not stage_text:
            return
        
        stage_code = stage_text.split(" - ")[0].strip()
        
        topics_list.delete(0, tk.END)
        topics = rmm.get_topics(project_db, self.selected_project_id, stage_code)
        
        for topic in topics:
            priority_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(topic['priority'], "⚪")
            note_count = topic.get('note_count', 0)
            label = f"{topic['topic_number']} {priority_icon} {topic['title']} ({note_count})"
            topics_list.insert(tk.END, label)
            # Store topic_id in itemconfig (as data)
            topics_list.itemconfig(tk.END, foreground=topic.get('color', 'black') if topic.get('color') else 'black')
        
        # Store topics data
        topics_list.topics_data = topics

    def load_topic_notes(self, project_db: str, topics_list: tk.Listbox, 
                        notes_container: tk.Frame, title_label: tk.Label, notes_win=None):
        """Załaduj notatki dla wybranego tematu"""
        # Sprawdź czy kontener jeszcze istnieje (okno mogło zostać zamknięte)
        if not notes_container.winfo_exists():
            return
        
        selection = topics_list.curselection()
        if not selection:
            return
        
        idx = selection[0]
        if not hasattr(topics_list, 'topics_data') or idx >= len(topics_list.topics_data):
            return
        
        topic = topics_list.topics_data[idx]
        topic_id = topic['id']
        
        # Update title
        priority_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(topic['priority'], "⚪")
        title_label.config(text=f"📝 {priority_icon} {topic['title']}")
        
        # Clear old notes
        for widget in notes_container.winfo_children():
            widget.destroy()
        
        # Load notes
        notes = rmm.get_notes(project_db, topic_id)
        
        if not notes:
            tk.Label(
                notes_container,
                text="Brak notatek w tym temacie",
                font=("Arial", 10, "italic"),
                fg="gray",
                bg="white"
            ).pack(pady=20)
            return
        
        # Display notes
        for note in notes:
            self.create_note_widget(notes_container, project_db, note, topic_id, topics_list, title_label, notes_win)

    def create_note_widget(self, container: tk.Frame, project_db: str, note: dict, 
                          topic_id: int, topics_list: tk.Listbox, title_label: tk.Label, notes_win=None):
        """Utwórz widget pojedynczej notatki z edycją inline"""
        note_frame = tk.LabelFrame(
            container,
            text=f"📌 {note['created_at'][:16]} - {note.get('created_by', 'Nieznany')}",
            font=("Arial", 9),
            bg="white",
            relief=tk.GROOVE,
            bd=2
        )
        note_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Auto-height - oblicz liczbę widocznych linii
        content = note['note_text']
        line_count = max(content.count('\n') + 1, 2)
        for line in content.split('\n'):
            if len(line) > 80:
                line_count += len(line) // 80
        
        # Notatka text - auto-height, readonly domyślnie
        note_text = tk.Text(
            note_frame,
            height=line_count,
            font=("Arial", 10),
            wrap=tk.WORD,
            bg="#f9f9f9",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2"
        )
        note_text.pack(fill=tk.BOTH, padx=5, pady=5)
        note_text.insert(1.0, content)
        note_text.config(state=tk.DISABLED)
        
        # Przyciski normalne (akcje)
        btn_frame = tk.Frame(note_frame, bg="white")
        btn_frame.pack(fill=tk.X, padx=5, pady=3)
        
        # Przyciski edycji (ukryte domyślnie)
        edit_btn_frame = tk.Frame(note_frame, bg="white")
        
        _original = [content]
        # Zapisz oryginalną zawartość jako atrybut widgetu (dostęp z zewnątrz)
        note_text._original_content = content
        note_text._note_id = note['id']
        
        def _recalc_height(txt):
            lc = max(txt.count('\n') + 1, 2)
            for ln in txt.split('\n'):
                if len(ln) > 80:
                    lc += len(ln) // 80
            return lc
        
        def _reload():
            self.load_topic_notes(project_db, topics_list, container, title_label, notes_win)
        
        def _clear_editing_flag():
            """Wyczyść flagę _currently_editing jeśli to ta notatka"""
            parent_container = notes_win.notes_container if notes_win and hasattr(notes_win, 'notes_container') else container
            if parent_container and hasattr(parent_container, '_currently_editing'):
                if parent_container._currently_editing == note_text:
                    parent_container._currently_editing = None
        
        def on_focus_out(event=None):
            """Auto-zamknij tryb edycji lub zapytaj o zapis przy zmianach"""
            # Sprawdź czy widget jeszcze istnieje (może być zniszczony po zamknięciu okna)
            if not note_text.winfo_exists():
                return
            
            if str(note_text.cget('state')) == 'disabled':
                return  # nie jesteśmy w trybie edycji
            
            current_content = note_text.get(1.0, tk.END).strip()
            if current_content == _original[0]:
                # Treść bez zmian - zamknij tryb edycji
                cancel_edit()
            else:
                # Treść zmieniona - zapytaj o zapis
                response = messagebox.askyesnocancel(
                    "Niezapisane zmiany",
                    "Notatka została zmieniona.\n\nCzy zapisać zmiany?",
                    icon='question',
                    parent=notes_win if notes_win else self.root
                )
                if response is True:  # Tak - zapisz
                    save_edit()
                elif response is False:  # Nie - odrzuć
                    cancel_edit()
                else:  # Anuluj (None) - przywróć focus
                    note_text.focus_set()
        
        def start_edit(event=None):
            # Sprawdź czy widget jeszcze istnieje (może być zniszczony po zamknięciu okna)
            if not note_text.winfo_exists():
                return
            
            if str(note_text.cget('state')) != 'disabled':
                return  # już w trybie edycji
            
            # Sprawdź czy inna notatka jest obecnie edytowana
            # Używamy notes_win.notes_container które jest ustawione przy tworzeniu okna
            parent_container = notes_win.notes_container if notes_win and hasattr(notes_win, 'notes_container') else container
            
            if parent_container and hasattr(parent_container, '_currently_editing'):
                currently_editing = parent_container._currently_editing
                if currently_editing and currently_editing != note_text:
                    # Inna notatka jest edytowana
                    if currently_editing.winfo_exists() and str(currently_editing.cget('state')) == 'normal':
                        # KLUCZOWE: Wyłącz FocusOut PRZED wywołaniem handlera aby uniknąć podwójnego zapytania
                        currently_editing.unbind("<FocusOut>")
                        
                        focus_out_handler = getattr(currently_editing, '_focus_out_handler', None)
                        if focus_out_handler and callable(focus_out_handler):
                            focus_out_handler(None)
                            # Jeśli użytkownik anulował (notatka dalej w trybie edycji) - przywróć binding i nie startuj nowej edycji
                            if currently_editing.winfo_exists() and str(currently_editing.cget('state')) == 'normal':
                                currently_editing.bind("<FocusOut>", focus_out_handler)
                                return
            
            # Rozpocznij edycję
            note_text.config(state=tk.NORMAL, bg="white", relief=tk.SUNKEN, bd=1, cursor="xterm")
            note_text.focus_set()
            btn_frame.pack_forget()
            edit_btn_frame.pack(fill=tk.X, padx=5, pady=3)
            # Dodaj handler FocusOut i zapisz go jako atrybut
            note_text._focus_out_handler = on_focus_out
            note_text.bind("<FocusOut>", on_focus_out)
            
            # Oznacz jako obecnie edytowaną
            if parent_container and hasattr(parent_container, '_currently_editing'):
                parent_container._currently_editing = note_text
        
        def save_edit():
            # Sprawdź czy widget jeszcze istnieje
            if not note_text.winfo_exists():
                return False
            
            new_content = note_text.get(1.0, tk.END).strip()
            if not new_content:
                messagebox.showwarning("Brak treści", "Wpisz treść notatki", parent=notes_win if notes_win else self.root)
                return False
            try:
                rmm.update_note(project_db, note['id'], new_content)
                _original[0] = new_content
                note_text._original_content = new_content
                note_text.config(state=tk.DISABLED, bg="#f9f9f9", relief=tk.FLAT, bd=0, cursor="hand2")
                note_text.config(height=_recalc_height(new_content))
                edit_btn_frame.pack_forget()
                btn_frame.pack(fill=tk.X, padx=5, pady=3)
                # Usuń bind FocusOut
                note_text.unbind("<FocusOut>")
                # Wyczyść _currently_editing jeśli to ta notatka
                _clear_editing_flag()
                
                # Odśwież panel główny
                self.load_project_stages()
                self.refresh_timeline()
                
                return True
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można zaktualizować notatki:\n{e}", parent=notes_win if notes_win else self.root)
                return False
        
        # Zapisz callback jako atrybut widgetu
        note_text._save_callback = save_edit
        
        def cancel_edit():
            # Sprawdź czy widget jeszcze istnieje
            if not note_text.winfo_exists():
                return
            
            note_text.config(state=tk.NORMAL)
            note_text.delete(1.0, tk.END)
            note_text.insert(1.0, _original[0])
            note_text.config(state=tk.DISABLED, bg="#f9f9f9", relief=tk.FLAT, bd=0, cursor="hand2")
            note_text.config(height=_recalc_height(_original[0]))
            edit_btn_frame.pack_forget()
            btn_frame.pack(fill=tk.X, padx=5, pady=3)
            # Usuń bind FocusOut
            note_text.unbind("<FocusOut>")
            # Wyczyść _currently_editing jeśli to ta notatka
            _clear_editing_flag()
        
        def do_move(direction):
            rmm.move_note(project_db, topic_id, note['id'], direction)
            _reload()
        
        # Klik na notatkę = edycja (jeśli can_edit)
        if notes_win and hasattr(notes_win, 'can_edit') and notes_win.can_edit:
            note_text.bind("<Button-1>", start_edit)
        
        # --- Przyciski normalne: przesuń + usuń + alarm ---
        button_state = tk.NORMAL if (notes_win and hasattr(notes_win, 'can_edit') and notes_win.can_edit) else tk.DISABLED
        
        tk.Button(
            btn_frame, text="⏫", command=lambda: do_move('top'),
            font=("Arial", 8), width=3, relief=tk.FLAT, state=button_state
        ).pack(side=tk.LEFT, padx=1)
        
        tk.Button(
            btn_frame, text="⬆️", command=lambda: do_move('up'),
            font=("Arial", 8), width=3, relief=tk.FLAT, state=button_state
        ).pack(side=tk.LEFT, padx=1)
        
        tk.Button(
            btn_frame, text="⬇️", command=lambda: do_move('down'),
            font=("Arial", 8), width=3, relief=tk.FLAT, state=button_state
        ).pack(side=tk.LEFT, padx=1)
        
        tk.Button(
            btn_frame, text="⏬", command=lambda: do_move('bottom'),
            font=("Arial", 8), width=3, relief=tk.FLAT, state=button_state
        ).pack(side=tk.LEFT, padx=1)
        
        tk.Button(
            btn_frame, text="🗑️ Usuń",
            command=lambda: self.delete_note(project_db, note['id'], note_frame, topics_list),
            bg=self.COLOR_RED, fg="white", font=self.FONT_SMALL, state=button_state
        ).pack(side=tk.LEFT, padx=(10, 2))
        
        tk.Button(
            btn_frame, text="⏰ Alarm",
            command=lambda: self.add_alarm_to_note(project_db, note['id'], notes_win),
            bg=self.COLOR_PURPLE, fg="white", font=self.FONT_SMALL, state=button_state
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_frame, text="📎 Dodaj załącznik",
            command=lambda: self.add_attachment_to_note(project_db, note['id'], note_frame, notes_win),
            bg=self.COLOR_ORANGE, fg="white", font=self.FONT_SMALL, state=button_state
        ).pack(side=tk.LEFT, padx=2)
        
        # --- Przyciski trybu edycji: zapisz + anuluj ---
        tk.Button(
            edit_btn_frame, text="💾 Zapisz", command=save_edit,
            bg=self.COLOR_GREEN, fg="white", font=self.FONT_SMALL
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            edit_btn_frame, text="❌ Anuluj", command=cancel_edit,
            bg=self.COLOR_RED, fg="white", font=self.FONT_SMALL
        ).pack(side=tk.LEFT, padx=2)
        
        # --- Sekcja załączników ---
        attachments_frame = tk.Frame(note_frame, bg="white")
        attachments_frame.pack(fill=tk.X, padx=5, pady=3)
        
        # Załaduj i wyświetl załączniki
        self.load_attachments_ui(project_db, note['id'], attachments_frame)
        
        # Drag-and-drop na ramkę notatki
        if HAS_DND:
            try:
                def handle_note_drop(event, nid=note['id'], af=attachments_frame, pdb=project_db):
                    print(f"📥 DROP na notatkę {nid}! data='{event.data}'")
                    files = []
                    try:
                        files = note_frame.tk.splitlist(event.data)
                    except Exception:
                        import re
                        files = re.findall(r'\{([^}]+)\}|(\S+)', event.data)
                        files = [f[0] if f[0] else f[1] for f in files]
                    
                    for file_path in files:
                        file_path = file_path.strip('{}').strip()
                        if not file_path:
                            continue
                        try:
                            import os
                            if not os.path.exists(file_path):
                                continue
                            file_size = os.path.getsize(file_path)
                            if file_size > 10 * 1024 * 1024:
                                messagebox.showwarning("Plik za duży", f"{os.path.basename(file_path)}: {file_size/1024/1024:.1f} MB\nMax: 10 MB")
                                continue
                            rmm.add_attachment(pdb, nid, file_path, uploaded_by=self.current_user)
                            print(f"✅ Załącznik dodany do notatki {nid}: {os.path.basename(file_path)}")
                            # Sprawdź czy status_bar nadal istnieje przed konfiguracją
                            if hasattr(self, 'status_bar') and self.status_bar.winfo_exists():
                                self.status_bar.config(text=f"✅ Załącznik dodany: {os.path.basename(file_path)}", fg=self.COLOR_GREEN)
                        except Exception as e:
                            import traceback
                            traceback.print_exc()
                    self.load_attachments_ui(pdb, nid, af)
                
                note_frame.drop_target_register(DND_FILES)
                note_frame.dnd_bind('<<Drop>>', handle_note_drop)
                note_frame.dnd_bind('<<DragEnter>>', lambda e: note_frame.config(bg="#c8e6c9"))
                note_frame.dnd_bind('<<DragLeave>>', lambda e: note_frame.config(bg="white"))
            except Exception as ex:
                print(f"⚠️ DnD notatka {note['id']}: {ex}")

    def add_new_topic(self, project_db: str, selected_stage: tk.StringVar, topics_list: tk.Listbox):
        """Dialog dodawania nowego tematu"""
        stage_text = selected_stage.get()
        if not stage_text:
            messagebox.showwarning("Brak etapu", "Wybierz etap")
            return
        
        stage_code = stage_text.split(" - ")[0].strip()
        
        # Dialog
        notes_win = topics_list.winfo_toplevel()
        dlg = tk.Toplevel(notes_win)
        dlg.title("➕ Nowy temat")
        dlg.transient(notes_win)
        dlg.grab_set()
        self._center_window(dlg, 500, 250)
        
        frm = tk.Frame(dlg, padx=20, pady=20)
        frm.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(frm, text="Tytuł tematu:", font=self.FONT_BOLD).grid(row=0, column=0, sticky='w', pady=5)
        title_entry = tk.Entry(frm, width=50, font=("Arial", 10))
        title_entry.grid(row=0, column=1, pady=5, padx=5)
        title_entry.focus()
        
        tk.Label(frm, text="Priorytet:", font=self.FONT_BOLD).grid(row=1, column=0, sticky='w', pady=5)
        priority_var = tk.StringVar(value="MEDIUM")
        priority_frame = tk.Frame(frm)
        priority_frame.grid(row=1, column=1, sticky='w', padx=5)
        
        tk.Radiobutton(priority_frame, text="🔴 Wysoki", variable=priority_var, value="HIGH").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(priority_frame, text="🟡 Średni", variable=priority_var, value="MEDIUM").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(priority_frame, text="🟢 Niski", variable=priority_var, value="LOW").pack(side=tk.LEFT, padx=5)
        
        def on_save():
            title = title_entry.get().strip()
            if not title:
                messagebox.showwarning("Brak tytułu", "Podaj tytuł tematu", parent=dlg)
                return
            
            try:
                rmm.create_topic(
                    project_db,
                    self.selected_project_id,
                    stage_code,
                    title,
                    priority_var.get(),
                    created_by=self.current_user
                )
                self.refresh_topics_list(project_db, selected_stage, topics_list)
                
                # Odśwież panel główny i oś czasu
                self.load_project_stages()
                self.refresh_timeline()
                
                dlg.destroy()
                notes_win.lift()
                notes_win.focus_set()
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można dodać tematu:\n{e}", parent=dlg)
        
        btn_frame = tk.Frame(frm)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=20)
        
        tk.Button(btn_frame, text="💾 Zapisz", command=on_save, bg=self.COLOR_GREEN, fg="white", width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="❌ Anuluj", command=lambda: [dlg.destroy(), notes_win.lift(), notes_win.focus_set()], bg=self.COLOR_RED, fg="white", width=12).pack(side=tk.LEFT, padx=5)

    def edit_topic(self, project_db: str, topics_list: tk.Listbox, title_label: tk.Label, selected_stage: tk.StringVar = None):
        """Dialog edycji tematu"""
        selection = topics_list.curselection()
        if not selection:
            return
        
        idx = selection[0]
        if not hasattr(topics_list, 'topics_data') or idx >= len(topics_list.topics_data):
            return
        
        topic = topics_list.topics_data[idx]
        
        # Dialog
        notes_win2 = topics_list.winfo_toplevel()
        dlg = tk.Toplevel(notes_win2)
        dlg.title("✏️ Edytuj temat")
        dlg.transient(notes_win2)
        dlg.grab_set()
        self._center_window(dlg, 500, 250)
        
        frm = tk.Frame(dlg, padx=20, pady=20)
        frm.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(frm, text="Tytuł tematu:", font=self.FONT_BOLD).grid(row=0, column=0, sticky='w', pady=5)
        title_entry = tk.Entry(frm, width=50, font=("Arial", 10))
        title_entry.grid(row=0, column=1, pady=5, padx=5)
        title_entry.insert(0, topic['title'])
        title_entry.focus()
        
        tk.Label(frm, text="Priorytet:", font=self.FONT_BOLD).grid(row=1, column=0, sticky='w', pady=5)
        priority_var = tk.StringVar(value=topic['priority'])
        priority_frame = tk.Frame(frm)
        priority_frame.grid(row=1, column=1, sticky='w', padx=5)
        
        tk.Radiobutton(priority_frame, text="🔴 Wysoki", variable=priority_var, value="HIGH").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(priority_frame, text="🟡 Średni", variable=priority_var, value="MEDIUM").pack(side=tk.LEFT, padx=5)
        tk.Radiobutton(priority_frame, text="🟢 Niski", variable=priority_var, value="LOW").pack(side=tk.LEFT, padx=5)
        
        def on_save():
            title = title_entry.get().strip()
            if not title:
                messagebox.showwarning("Brak tytułu", "Podaj tytuł tematu")
                return
            
            try:
                rmm.update_topic(project_db, topic['id'], title=title, priority=priority_var.get())
                # Pełny refresh listy
                if selected_stage:
                    self.refresh_topics_list(project_db, selected_stage, topics_list)
                    # Przywróć zaznaczenie
                    if idx < topics_list.size():
                        topics_list.selection_set(idx)
                
                # Update title label
                priority_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(priority_var.get(), "⚪")
                title_label.config(text=f"📝 {priority_icon} {title}")
                dlg.destroy()
                notes_win2.lift()
                notes_win2.focus_set()
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można zaktualizować tematu:\n{e}")
        
        btn_frame = tk.Frame(frm)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=20)
        
        tk.Button(btn_frame, text="💾 Zapisz", command=on_save, bg=self.COLOR_GREEN, fg="white", width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="❌ Anuluj", command=lambda: [dlg.destroy(), notes_win2.lift(), notes_win2.focus_set()], bg=self.COLOR_RED, fg="white", width=12).pack(side=tk.LEFT, padx=5)

    def delete_topic(self, project_db: str, topics_list: tk.Listbox, notes_container: tk.Frame):
        """Usuń temat (z potwierdzeniem)"""
        # Sprawdź czy widgety jeszcze istnieją
        if not topics_list.winfo_exists() or not notes_container.winfo_exists():
            return
        
        selection = topics_list.curselection()
        if not selection:
            return
        
        idx = selection[0]
        if not hasattr(topics_list, 'topics_data') or idx >= len(topics_list.topics_data):
            return
        
        topic = topics_list.topics_data[idx]
        notes_win = topics_list.winfo_toplevel()
        
        if not messagebox.askyesno("Potwierdzenie", f"Czy na pewno usunąć temat:\n\n{topic['title']}\n\nZostaną usunięte wszystkie notatki i alarmy tego tematu!", parent=notes_win):
            notes_win.lift()
            notes_win.focus_set()
            return
        
        try:
            rmm.delete_topic(project_db, topic['id'])
            topics_list.delete(idx)
            topics_list.topics_data.pop(idx)
            
            # Wyczyść notatki - sprawdź czy kontener nadal istnieje
            if notes_container.winfo_exists():
                for widget in notes_container.winfo_children():
                    widget.destroy()
            
            # Odśwież panel główny i oś czasu
            self.load_project_stages()
            self.refresh_timeline()
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można usunąć tematu:\n{e}", parent=notes_win)
        
        notes_win.lift()
        notes_win.focus_set()

    def change_topic_priority(self, project_db: str, selected_stage: tk.StringVar,
                              topics_list: tk.Listbox, notes_container: tk.Frame,
                              title_label: tk.Label):
        """Zmień priorytet wybranego tematu (menu szybkiego wyboru)"""
        selection = topics_list.curselection()
        if not selection:
            return
        
        idx = selection[0]
        if not hasattr(topics_list, 'topics_data') or idx >= len(topics_list.topics_data):
            return
        
        topic = topics_list.topics_data[idx]
        
        # Popup menu z priorytetami
        menu = tk.Menu(self.root, tearoff=0)
        notes_win = topics_list.winfo_toplevel()
        
        def _set(prio):
            try:
                rmm.update_topic(project_db, topic['id'], priority=prio)
                self.refresh_topics_list(project_db, selected_stage, topics_list)
                if idx < topics_list.size():
                    topics_list.selection_set(idx)
                    topics_list.event_generate('<<ListboxSelect>>')
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można zmienić priorytetu:\n{e}", parent=notes_win)
        
        current = topic['priority']
        menu.add_command(label="🔴 Wysoki" + (" ✓" if current == 'HIGH' else ""),
                        command=lambda: _set('HIGH'))
        menu.add_command(label="🟡 Średni" + (" ✓" if current == 'MEDIUM' else ""),
                        command=lambda: _set('MEDIUM'))
        menu.add_command(label="🟢 Niski" + (" ✓" if current == 'LOW' else ""),
                        command=lambda: _set('LOW'))
        
        # Pokaż menu przy kursorze myszy
        try:
            menu.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            menu.grab_release()

    def _create_user_checklist(self, parent: tk.Frame) -> tuple:
        """Utwórz checklistę użytkowników z ptaszkami (Wszyscy + indywidualni).
        
        Returns:
            tuple: (all_var: BooleanVar, user_vars: dict {username: BooleanVar}, users_inner: Frame)
        """
        users = rmm.get_users_from_baza(self.master_db_path)
        user_names = [u['username'] for u in users]
        
        all_var = tk.BooleanVar(value=True)
        user_vars = {}  # username -> BooleanVar
        
        def on_all_toggle():
            state = all_var.get()
            for uvar in user_vars.values():
                uvar.set(state)
        
        def on_user_toggle():
            # Jeśli wszystkie zaznaczone → zaznacz 'Wszyscy', w przeciwnym razie odznacz
            all_checked = all(v.get() for v in user_vars.values())
            all_var.set(all_checked)
        
        # Checkbox "Wszyscy" (pogrubiony, na górze)
        all_cb = tk.Checkbutton(
            parent, text="✅ Wszyscy", variable=all_var,
            font=("Arial", 9, "bold"), anchor='w',
            command=on_all_toggle
        )
        all_cb.pack(fill=tk.X, padx=2)
        
        # Separator
        sep = tk.Frame(parent, height=1, bg="#cccccc")
        sep.pack(fill=tk.X, padx=5, pady=2)
        
        # Scrollable frame z użytkownikami
        canvas = tk.Canvas(parent, height=min(len(user_names) * 22, 100), bg="white",
                          highlightthickness=0)
        scrollbar = tk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        users_inner = tk.Frame(canvas, bg="white")
        
        users_inner.bind("<Configure>",
                        lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=users_inner, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        
        if len(user_names) > 5:
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        for uname in user_names:
            var = tk.BooleanVar(value=True)
            user_vars[uname] = var
            cb = tk.Checkbutton(
                users_inner, text=f"  {uname}", variable=var,
                font=("Arial", 9), anchor='w', bg="white",
                command=on_user_toggle
            )
            cb.pack(fill=tk.X, padx=4)
        
        return all_var, user_vars, users_inner

    def _get_assigned_to_from_checklist(self, all_var, user_vars: dict) -> str:
        """Zwróć wartość assigned_to na podstawie checklisty."""
        if all_var.get():
            return 'ALL'
        selected = [uname for uname, var in user_vars.items() if var.get()]
        if not selected:
            return ''
        return ','.join(selected)

    def add_alarm_to_topic(self, project_db: str, topics_list: tk.Listbox):
        """Dialog dodawania alarmu do tematu (z checklistą adresatów)"""
        selection = topics_list.curselection()
        if not selection:
            return
        
        idx = selection[0]
        if not hasattr(topics_list, 'topics_data') or idx >= len(topics_list.topics_data):
            return
        
        topic = topics_list.topics_data[idx]
        
        notes_win = topics_list.winfo_toplevel()
        dlg = tk.Toplevel(notes_win)
        dlg.title(f"⏰ Alarm: {topic['title']}")
        dlg.transient(notes_win)
        dlg.grab_set()
        self._center_window(dlg, 600, 520)  # Powiększono szerokość dla listy alarmów
        
        frm = tk.Frame(dlg, padx=20, pady=15)
        frm.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(frm, text="Data i czas alarmu:", font=self.FONT_BOLD).grid(row=0, column=0, sticky='w', pady=5)
        
        date_frame = tk.Frame(frm)
        date_frame.grid(row=0, column=1, sticky='w', padx=5)
        
        date_entry = tk.Entry(date_frame, width=15)
        date_entry.pack(side=tk.LEFT, padx=2)
        date_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))
        
        time_entry = tk.Entry(date_frame, width=10)
        time_entry.pack(side=tk.LEFT, padx=2)
        time_entry.insert(0, "09:00")
        
        # Lista istniejących alarmów dla tego tematu
        tk.Label(frm, text="Istniejące alarmy:", font=self.FONT_BOLD).grid(row=1, column=0, sticky='nw', pady=5)
        
        existing_frame = tk.LabelFrame(frm, text="Już ustawione alarmy dla tego tematu", font=("Arial", 8),
                                      relief=tk.GROOVE, bd=1)
        existing_frame.grid(row=1, column=1, sticky='nsew', padx=5, pady=2)
        
        # Pobierz istniejące alarmy
        try:
            existing_alarms = rmm.get_alarms_for_target(project_db, 'TOPIC', topic['id'])
            if existing_alarms:
                alarms_text = tk.Text(existing_frame, height=4, width=55, font=("Arial", 9),
                                    wrap=tk.WORD, state=tk.DISABLED)
                alarms_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                
                alarms_text.config(state=tk.NORMAL)
                for i, alarm in enumerate(existing_alarms, 1):
                    date_str = alarm['alarm_datetime'][:16]
                    assigned = alarm.get('assigned_to', 'ALL')
                    if assigned == 'ALL':
                        assigned = 'Wszyscy'
                    
                    status = ""
                    if alarm.get('is_snoozed', False):
                        status = " [ODŁOŻONY]"
                    elif alarm.get('acknowledged_at'):
                        status = " [POTWIERDZONY]"
                    
                    message = alarm.get('message', '').replace('\n', ' ')[:50]
                    if len(alarm.get('message', '')) > 50:
                        message += '...'
                    
                    alarms_text.insert(tk.END, f"{i}. {date_str} → {assigned}{status}\n")
                    if message:
                        alarms_text.insert(tk.END, f"   {message}\n")
                    alarms_text.insert(tk.END, "\n")
                
                alarms_text.config(state=tk.DISABLED)
            else:
                tk.Label(existing_frame, text="Brak istniejących alarmów", 
                         font=("Arial", 9, "italic"), fg="gray").pack(pady=10)
        except Exception as e:
            import traceback
            print(f"⚠️ Topic alarm error: {e}")
            print(traceback.format_exc())
            tk.Label(existing_frame, text="Błąd ładowania alarmów - szczegóły w konsoli", 
                     font=("Arial", 9, "italic"), fg="red").pack(pady=10)
        
        # Adresaci alarmu - checklista z ptaszkami
        tk.Label(frm, text="Adresaci:", font=self.FONT_BOLD).grid(row=2, column=0, sticky='nw', pady=5)
        
        users_frame = tk.LabelFrame(frm, text="Kogo powiadomić", font=("Arial", 8),
                                    relief=tk.GROOVE, bd=1)
        users_frame.grid(row=1, column=1, sticky='nsew', padx=5, pady=2)
        
        all_var, user_vars, _ = self._create_user_checklist(users_frame)
        
        tk.Label(frm, text="Wiadomość:", font=self.FONT_BOLD).grid(row=2, column=0, sticky='w', pady=5)
        message_text = scrolledtext.ScrolledText(frm, height=3, width=40, font=("Arial", 10))
        message_text.grid(row=2, column=1, pady=5, padx=5)
        
        frm.grid_rowconfigure(1, weight=1)
        
        def on_save():
            try:
                alarm_dt = f"{date_entry.get()} {time_entry.get()}:00"
                message = message_text.get(1.0, tk.END).strip()
                
                assigned_to = self._get_assigned_to_from_checklist(all_var, user_vars)
                if not assigned_to:
                    messagebox.showwarning("Brak adresatów", "Zaznacz co najmniej jednego adresata", parent=dlg)
                    return
                
                rmm.create_alarm(
                    project_db,
                    self.selected_project_id,
                    'TOPIC',
                    topic['id'],
                    alarm_dt,
                    message or f"Alarm: {topic['title']}",
                    created_by=self.current_user,
                    assigned_to=assigned_to
                )
                
                # Odśwież panel główny i oś czasu
                if hasattr(self, 'load_project_stages'):
                    self.load_project_stages()
                if hasattr(self, 'refresh_timeline'):
                    self.refresh_timeline()
                
                dlg.destroy()
                notes_win.lift()
                notes_win.focus_set()
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można dodać alarmu:\n{e}", parent=dlg)
        
        btn_frame = tk.Frame(frm)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=10)
        
        tk.Button(btn_frame, text="💾 Zapisz", command=on_save, bg=self.COLOR_GREEN, fg="white", width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="❌ Anuluj", command=dlg.destroy, bg=self.COLOR_RED, fg="white", width=12).pack(side=tk.LEFT, padx=5)

    def add_new_note(self, project_db: str, topics_list: tk.Listbox, notes_container: tk.Frame, title_label: tk.Label = None):
        """Dodaj nową notatkę inline (na końcu listy notatek)"""
        selection = topics_list.curselection()
        if not selection:
            return
        
        idx = selection[0]
        if not hasattr(topics_list, 'topics_data') or idx >= len(topics_list.topics_data):
            return
        
        topic = topics_list.topics_data[idx]
        
        # Sprawdź czy jest obecnie edytowana notatka
        if hasattr(notes_container, '_currently_editing'):
            currently_editing = notes_container._currently_editing
            if currently_editing and currently_editing.winfo_exists() and str(currently_editing.cget('state')) == 'normal':
                # Inna notatka jest edytowana - wyłącz FocusOut i wywołaj handler
                currently_editing.unbind("<FocusOut>")
                
                focus_out_handler = getattr(currently_editing, '_focus_out_handler', None)
                if focus_out_handler and callable(focus_out_handler):
                    focus_out_handler(None)
                    # Jeśli użytkownik anulował - przywróć binding i nie dodawaj nowej notatki
                    if currently_editing.winfo_exists() and str(currently_editing.cget('state')) == 'normal':
                        currently_editing.bind("<FocusOut>", focus_out_handler)
                        return
        
        # Usuń placeholder "Brak notatek" jeśli istnieje
        for widget in notes_container.winfo_children():
            if isinstance(widget, tk.Label) and "Brak notatek" in str(widget.cget('text')):
                widget.destroy()
        
        # Twórz ramkę nowej notatki inline
        new_frame = tk.LabelFrame(
            notes_container,
            text="✨ Nowa notatka",
            font=("Arial", 9, "bold"),
            bg="#fffff0",
            relief=tk.GROOVE,
            bd=2
        )
        new_frame.pack(fill=tk.X, padx=10, pady=5)
        
        note_text = tk.Text(
            new_frame,
            height=4,
            font=("Arial", 10),
            wrap=tk.WORD,
            bg="white",
            relief=tk.SUNKEN,
            bd=1
        )
        note_text.pack(fill=tk.BOTH, padx=5, pady=5)
        note_text.focus_set()
        
        # Inicjalizuj _currently_editing jeśli nie istnieje
        if not hasattr(notes_container, '_currently_editing'):
            notes_container._currently_editing = None
        
        # Oznacz jako obecnie edytowaną
        notes_container._currently_editing = note_text
        
        # Dodaj handler FocusOut dla automatycznego zapisu/anulowania
        def on_focus_out_new_note(event=None):
            """Auto-zapisz lub zapytaj o zapis przy utracie focusa"""
            if not note_text.winfo_exists():
                return
                
            current_content = note_text.get(1.0, tk.END).strip()
            if not current_content:
                # Pusta notatka - anuluj bez pytania
                on_cancel()
            else:
                # Treść wprowadzona - zapytaj o zapis
                response = messagebox.askyesnocancel(
                    "Niezapisane zmiany",
                    "Nowa notatka została wprowadzona.\n\nCzy zapisać notatkę?",
                    icon='question',
                    parent=notes_container.winfo_toplevel()
                )
                if response is True:  # Tak - zapisz
                    on_save()
                elif response is False:  # Nie - anuluj bez zapisu
                    on_cancel()
                else:  # Anuluj (None) - przywróć focus
                    note_text.focus_set()
        
        # Zbinduj handler FocusOut i zapisz go jako atrybut
        note_text._focus_out_handler = on_focus_out_new_note
        note_text.bind("<FocusOut>", on_focus_out_new_note)
        
        btn_frame = tk.Frame(new_frame, bg="#fffff0")
        btn_frame.pack(fill=tk.X, padx=5, pady=3)
        
        def on_save():
            content = note_text.get(1.0, tk.END).strip()
            notes_win_widget = notes_container.winfo_toplevel()
            if not content:
                messagebox.showwarning("Brak treści", "Wpisz treść notatki", parent=notes_win_widget)
                return
            try:
                # Odbinduj FocusOut przed zapisem
                note_text.unbind("<FocusOut>")
                
                rmm.add_note(project_db, topic['id'], content, created_by=self.current_user)
                # Wyczyść flagę _currently_editing
                if hasattr(notes_container, '_currently_editing') and notes_container._currently_editing == note_text:
                    notes_container._currently_editing = None
                if title_label:
                    self.load_topic_notes(project_db, topics_list, notes_container, title_label, notes_win_widget)
                
                # Odśwież panel główny
                self.load_project_stages()
                self.refresh_timeline()
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można dodać notatki:\n{e}", parent=notes_win_widget)
        
        def on_cancel():
            # Odbinduj FocusOut przed anulowaniem
            if note_text.winfo_exists():
                note_text.unbind("<FocusOut>")
            # Wyczyść flagę _currently_editing
            if hasattr(notes_container, '_currently_editing') and notes_container._currently_editing == note_text:
                notes_container._currently_editing = None
            new_frame.destroy()
        
        tk.Button(
            btn_frame, text="💾 Zapisz", command=on_save,
            bg=self.COLOR_GREEN, fg="white", font=self.FONT_SMALL
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            btn_frame, text="❌ Anuluj", command=on_cancel,
            bg=self.COLOR_RED, fg="white", font=self.FONT_SMALL
        ).pack(side=tk.LEFT, padx=2)

    def delete_note(self, project_db: str, note_id: int, note_frame: tk.Frame, topics_list: tk.Listbox):
        """Usuń notatkę (z potwierdzeniem)"""
        # Sprawdź czy widget jeszcze istnieje
        if not note_frame.winfo_exists():
            return
        
        notes_win = note_frame.winfo_toplevel()
        if not messagebox.askyesno("Potwierdzenie", "Czy na pewno usunąć tę notatkę?", parent=notes_win):
            return
        
        try:
            rmm.delete_note(project_db, note_id)
            # Sprawdź ponownie czy widget nadal istnieje przed zniszczeniem
            if note_frame.winfo_exists():
                note_frame.destroy()
            
            # Odśwież panel główny
            self.load_project_stages()
            self.refresh_timeline()
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można usunąć notatki:\n{e}", parent=notes_win)

    def add_alarm_to_note(self, project_db: str, note_id: int, notes_win=None):
        """Dialog dodawania alarmu do notatki (z checklistą adresatów)"""
        parent_win = notes_win if notes_win else self.root
        dlg = tk.Toplevel(parent_win)
        dlg.title("⏰ Nowy alarm")
        dlg.transient(parent_win)
        dlg.grab_set()
        self._center_window(dlg, 600, 520)  # Powiększono dla listy alarmów
        
        frm = tk.Frame(dlg, padx=20, pady=15)
        frm.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(frm, text="Data i czas alarmu:", font=self.FONT_BOLD).grid(row=0, column=0, sticky='w', pady=5)
        
        date_frame = tk.Frame(frm)
        date_frame.grid(row=0, column=1, sticky='w', padx=5)
        
        date_entry = tk.Entry(date_frame, width=15)
        date_entry.pack(side=tk.LEFT, padx=2)
        date_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))
        
        time_entry = tk.Entry(date_frame, width=10)
        time_entry.pack(side=tk.LEFT, padx=2)
        time_entry.insert(0, "09:00")
        
        # Lista istniejących alarmów dla tej notatki
        tk.Label(frm, text="Istniejące alarmy:", font=self.FONT_BOLD).grid(row=1, column=0, sticky='nw', pady=5)
        
        existing_frame = tk.LabelFrame(frm, text="Już ustawione alarmy dla tej notatki", font=("Arial", 8),
                                      relief=tk.GROOVE, bd=1)
        existing_frame.grid(row=1, column=1, sticky='nsew', padx=5, pady=2)
        
        # Pobierz istniejące alarmy
        try:
            existing_alarms = rmm.get_alarms_for_target(project_db, 'NOTE', note_id)
            if existing_alarms:
                alarms_text = tk.Text(existing_frame, height=4, width=55, font=("Arial", 9),
                                    wrap=tk.WORD, state=tk.DISABLED)
                alarms_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                
                alarms_text.config(state=tk.NORMAL)
                for i, alarm in enumerate(existing_alarms, 1):
                    date_str = alarm['alarm_datetime'][:16]
                    assigned = alarm.get('assigned_to', 'ALL')
                    if assigned == 'ALL':
                        assigned = 'Wszyscy'
                    
                    status = ""
                    if alarm.get('is_snoozed', False):
                        status = " [ODŁOŻONY]"
                    elif alarm.get('acknowledged_at'):
                        status = " [POTWIERDZONY]"
                    
                    message = alarm.get('message', '').replace('\n', ' ')[:50]
                    if len(alarm.get('message', '')) > 50:
                        message += '...'
                    
                    alarms_text.insert(tk.END, f"{i}. {date_str} → {assigned}{status}\n")
                    if message:
                        alarms_text.insert(tk.END, f"   {message}\n")
                    alarms_text.insert(tk.END, "\n")
                
                alarms_text.config(state=tk.DISABLED)
            else:
                tk.Label(existing_frame, text="Brak istniejących alarmów", 
                         font=("Arial", 9, "italic"), fg="gray").pack(pady=10)
        except Exception as e:
            import traceback
            print(f"⚠️ Note alarm error: {e}")
            print(traceback.format_exc())
            tk.Label(existing_frame, text="Błąd ładowania alarmów - szczegóły w konsoli", 
                     font=("Arial", 9, "italic"), fg="red").pack(pady=10)
        
        # Adresaci alarmu - checklista z ptaszkami
        tk.Label(frm, text="Adresaci:", font=self.FONT_BOLD).grid(row=2, column=0, sticky='nw', pady=5)
        
        users_frame = tk.LabelFrame(frm, text="Kogo powiadomić", font=("Arial", 8),
                                    relief=tk.GROOVE, bd=1)
        users_frame.grid(row=2, column=1, sticky='nsew', padx=5, pady=2)
        
        all_var, user_vars, _ = self._create_user_checklist(users_frame)
        
        tk.Label(frm, text="Wiadomość:", font=self.FONT_BOLD).grid(row=3, column=0, sticky='w', pady=5)
        message_text = scrolledtext.ScrolledText(frm, height=3, width=50, font=("Arial", 10))
        message_text.grid(row=3, column=1, pady=5, padx=5)
        
        frm.grid_rowconfigure(2, weight=1)
        
        def on_save():
            try:
                alarm_dt = f"{date_entry.get()} {time_entry.get()}:00"
                message = message_text.get(1.0, tk.END).strip()
                
                assigned_to = self._get_assigned_to_from_checklist(all_var, user_vars)
                if not assigned_to:
                    messagebox.showwarning("Brak adresatów", "Zaznacz co najmniej jednego adresata", parent=dlg)
                    return
                
                rmm.create_alarm(
                    project_db,
                    self.selected_project_id,
                    'NOTE',
                    note_id,
                    alarm_dt,
                    message,
                    created_by=self.current_user,
                    assigned_to=assigned_to
                )
                
                # Odśwież panel główny i oś czasu
                if hasattr(self, 'load_project_stages'):
                    self.load_project_stages()
                if hasattr(self, 'refresh_timeline'):
                    self.refresh_timeline()
                
                dlg.destroy()
                if notes_win:
                    notes_win.lift()
                    notes_win.focus_set()
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można dodać alarmu:\n{e}", parent=dlg)
        
        btn_frame = tk.Frame(frm)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=10)
        
        tk.Button(btn_frame, text="💾 Zapisz", command=on_save, bg=self.COLOR_GREEN, fg="white", width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="❌ Anuluj", command=dlg.destroy, bg=self.COLOR_RED, fg="white", width=12).pack(side=tk.LEFT, padx=5)

    def add_attachment_to_note(self, project_db: str, note_id: int, note_frame: tk.Frame, notes_win=None):
        """Dialog wyboru pliku i dodania załącznika do notatki"""
        from tkinter import filedialog
        
        # Sprawdź czy frame jeszcze istnieje
        if not note_frame.winfo_exists():
            return
        
        parent_win = notes_win if notes_win else self.root
        file_path = filedialog.askopenfilename(
            parent=parent_win,
            title="Wybierz plik do załączenia",
            filetypes=[
                ("Wszystkie pliki", "*.*"),
                ("Obrazy", "*.jpg *.jpeg *.png *.gif *.bmp"),
                ("PDF", "*.pdf"),
                ("Excel", "*.xlsx *.xls"),
                ("CSV", "*.csv"),
                ("Word", "*.docx *.doc"),
                ("Tekst", "*.txt")
            ]
        )
        
        if not file_path:
            return  # Anulowano
        
        try:
            import os
            file_size = os.path.getsize(file_path)
            
            # Limit 10 MB
            if file_size > 10 * 1024 * 1024:
                messagebox.showwarning(
                    "Plik za duży",
                    f"Plik ma {file_size / 1024 / 1024:.1f} MB.\nMaksymalny rozmiar: 10 MB"
                )
                return
            
            rmm.add_attachment(project_db, note_id, file_path, uploaded_by=self.current_user)
            
            # Odśwież widok załączników
            for widget in note_frame.winfo_children():
                if isinstance(widget, tk.Frame) and widget.winfo_name().startswith('!frame'):
                    # Szukamy attachments_frame (ostatni Frame w note_frame)
                    pass
            
            # Znajdź attachments_frame i odśwież
            children = note_frame.winfo_children()
            for child in reversed(children):
                if isinstance(child, tk.Frame):
                    self.load_attachments_ui(project_db, note_id, child)
                    break
            
            self.status_bar.config(
                text=f"✅ Załącznik dodany: {os.path.basename(file_path)}",
                fg=self.COLOR_GREEN
            )
            
            # Odśwież panel główny
            self.load_project_stages()
            self.refresh_timeline()
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Błąd", f"Nie można dodać załącznika:\n{e}", parent=parent_win)
            if notes_win:
                notes_win.lift()
                notes_win.focus_set()
    
    def load_attachments_ui(self, project_db: str, note_id: int, attachments_frame: tk.Frame):
        """Załaduj i wyświetl załączniki dla notatki"""
        # Sprawdź czy frame jeszcze istnieje
        if not attachments_frame.winfo_exists():
            return
        
        # Wyczyść poprzednią zawartość
        for widget in attachments_frame.winfo_children():
            widget.destroy()
        
        try:
            attachments = rmm.get_attachments(project_db, note_id)
            
            if not attachments:
                return  # Brak załączników - nie pokazuj nic
            
            # Separator
            tk.Frame(attachments_frame, height=1, bg="#ddd").pack(fill=tk.X, pady=(5, 2))
            
            # Header
            tk.Label(
                attachments_frame,
                text=f"📎 Załączniki ({len(attachments)}):",
                font=("Arial", 9, "bold"),
                bg="white",
                fg="#555"
            ).pack(anchor='w', padx=2, pady=2)
            
            # Lista załączników
            for att in attachments:
                self._create_attachment_widget(project_db, note_id, att, attachments_frame)
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            tk.Label(
                attachments_frame,
                text=f"⚠️ Błąd ładowania załączników: {e}",
                font=("Arial", 8),
                fg="red",
                bg="white"
            ).pack(anchor='w', padx=5)
    
    def _create_attachment_widget(self, project_db: str, note_id: int, 
                                   attachment: dict, container: tk.Frame):
        """Utwórz widget pojedynczego załącznika"""
        # Get notes window for proper parent dialogs
        notes_win = container.winfo_toplevel()
        
        att_row = tk.Frame(container, bg="white")
        att_row.pack(fill=tk.X, padx=10, pady=2)
        
        # Ikona wg typu pliku
        filename = attachment['filename']
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        icon_map = {
            'pdf': '📄', 'jpg': '🖼️', 'jpeg': '🖼️', 'png': '🖼️', 'gif': '🖼️',
            'xlsx': '📊', 'xls': '📊', 'csv': '📊',
            'docx': '📝', 'doc': '📝', 'txt': '📝',
            'zip': '📦', 'rar': '📦'
        }
        icon = icon_map.get(ext, '📎')
        
        # Rozmiar
        size_kb = attachment['file_size'] / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
        
        # Nazwa pliku
        tk.Label(
            att_row,
            text=f"{icon} {filename} ({size_str})",
            font=("Arial", 9),
            bg="white",
            fg="#333"
        ).pack(side=tk.LEFT, padx=2)
        
        # Przyciski
        tk.Button(
            att_row,
            text="🔍 Otwórz",
            command=lambda: self.open_attachment(project_db, attachment['id'], notes_win),
            bg="#4CAF50",
            fg="white",
            font=("Arial", 8),
            relief=tk.FLAT,
            padx=8,
            pady=2
        ).pack(side=tk.LEFT, padx=2)
        
        # Sprawdź czy można edytować
        button_state = tk.NORMAL if (notes_win and hasattr(notes_win, 'can_edit') and notes_win.can_edit) else tk.DISABLED
        
        tk.Button(
            att_row,
            text="� Pobierz",
            command=lambda: self.download_attachment(project_db, attachment['id'], attachment['filename'], notes_win),
            bg="#2196F3",
            fg="white",
            font=("Arial", 8),
            relief=tk.FLAT,
            padx=8,
            pady=2
        ).pack(side=tk.LEFT, padx=2)
        
        tk.Button(
            att_row,
            text="�🗑️",
            command=lambda: self.delete_attachment_ui(project_db, note_id, attachment['id'], container, notes_win),
            bg=self.COLOR_RED,
            fg="white",
            font=("Arial", 8),
            relief=tk.FLAT,
            padx=5,
            pady=2,
            state=button_state
        ).pack(side=tk.LEFT, padx=2)
    
    def open_attachment(self, project_db: str, attachment_id: int, notes_win=None):
        """Otwórz załącznik w domyślnej aplikacji"""
        parent_win = notes_win if notes_win else self.root
        try:
            # Zapisz do pliku tymczasowego
            temp_path = rmm.save_attachment_to_temp(project_db, attachment_id)
            
            # Otwórz w systemie
            import platform
            import subprocess
            
            system = platform.system()
            if system == 'Windows':
                import os
                os.startfile(temp_path)
            elif system == 'Darwin':  # macOS
                subprocess.run(['open', temp_path], check=True)
            else:  # Linux
                subprocess.run(['xdg-open', temp_path], check=True)
            
            self.status_bar.config(
                text=f"✅ Otwarto załącznik w aplikacji systemowej",
                fg=self.COLOR_GREEN
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Błąd", f"Nie można otworzyć załącznika:\n{e}", parent=parent_win)
            if notes_win:
                notes_win.lift()
                notes_win.focus_set()
    
    def download_attachment(self, project_db: str, attachment_id: int, 
                           original_filename: str, notes_win=None):
        """Pobierz załącznik i zapisz w wybranej lokalizacji"""
        parent_win = notes_win if notes_win else self.root
        
        try:
            # Dialog wyboru lokalizacji zapisu
            from tkinter import filedialog
            import os
            
            # Zaproponuj oryginalną nazwę pliku
            file_path = filedialog.asksaveasfilename(
                parent=parent_win,
                title="Zapisz załącznik jako",
                initialfile=original_filename,
                defaultextension="",
                filetypes=[
                    ("Wszystkie pliki", "*.*"),
                    ("Dokumenty PDF", "*.pdf"),
                    ("Obrazy", "*.jpg;*.jpeg;*.png;*.gif"),
                    ("Arkusze", "*.xlsx;*.xls;*.csv"),
                    ("Dokumenty", "*.docx;*.doc;*.txt"),
                    ("Archiwa", "*.zip;*.rar")
                ]
            )
            
            if not file_path:  # Użytkownik anulował
                return
                
            # Pobierz dane załącznika z bazy
            attachment_data = rmm.get_attachment_data(project_db, attachment_id)
            
            if not attachment_data:
                messagebox.showerror("Błąd", "Nie można pobrać danych załącznika", parent=parent_win)
                return
            
            # Zapisz do wybranej lokalizacji
            with open(file_path, 'wb') as f:
                f.write(attachment_data['file_content'])
            
            self.status_bar.config(
                text=f"✅ Załącznik zapisany: {os.path.basename(file_path)}",
                fg=self.COLOR_GREEN
            )
            
            # Przywróć focus do okna notatek
            if notes_win:
                notes_win.lift()
                notes_win.focus_set()
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Błąd", f"Nie można pobrać załącznika:\n{e}", parent=parent_win)
            if notes_win:
                notes_win.lift()
                notes_win.focus_set()
    
    def delete_attachment_ui(self, project_db: str, note_id: int, 
                            attachment_id: int, attachments_frame: tk.Frame, notes_win=None):
        """Usuń załącznik po potwierdzeniu"""
        parent_win = notes_win if notes_win else self.root
        if not messagebox.askyesno("Usunąć załącznik?", "Czy na pewno usunąć ten załącznik?", parent=parent_win):
            return
        
        try:
            rmm.delete_attachment(project_db, attachment_id)
            
            # Odśwież widok
            self.load_attachments_ui(project_db, note_id, attachments_frame)
            
            self.status_bar.config(
                text="✅ Załącznik usunięty",
                fg=self.COLOR_GREEN
            )
            
            # Odśwież panel główny
            self.load_project_stages()
            self.refresh_timeline()
            
            # Przywróć focus do okna notatek
            if notes_win:
                notes_win.lift()
                notes_win.focus_set()
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można usunąć załącznika:\n{e}", parent=parent_win)
            if notes_win:
                notes_win.lift()
                notes_win.focus_set()

    def get_stage_attachments_count(self, stage_code: str) -> int:
        """Zlicz załączniki dla danego etapu.
        
        Args:
            stage_code: Kod etapu (np. 'PRZYJETY', 'ZAKONCZONY', 'ODBIOR_1')
            
        Returns:
            int: Liczba załączników
        """
        if not self.selected_project_id:
            return 0
        
        try:
            project_db = self.get_project_db_path(self.selected_project_id)
            attachments = rmm.get_stage_attachments(project_db, self.selected_project_id, stage_code)
            return len(attachments)
        except Exception:
            return 0

    def show_stage_attachments_window(self, stage_code: str, title: str):
        """Okno z załącznikami dla etapu (Karta maszyny, Protokół)"""
        if not self.selected_project_id:
            messagebox.showwarning("Brak projektu", "Wybierz projekt")
            return
        
        # Określ czy można dodawać pliki - wymaga locka
        can_add_files = self.have_lock and not self.read_only_mode
        
        project_db = self.get_project_db_path(self.selected_project_id)
        
        # Okno główne
        win = tk.Toplevel(self.root)
        win.transient(self.root)  # Okno na tym samym ekranie co główna aplikacja
        win.can_edit = can_add_files  # Zapisz flagę edycji jako atrybut okna
        title_suffix = " (READ-ONLY)" if not can_add_files else ""
        win.title(f"📎 {title} - {stage_code} - Projekt {self.selected_project_id}{title_suffix}")
        win.resizable(True, True)
        win_key = f'attachments_window_{stage_code}'
        self.restore_window_geometry(win_key, win, 900, 600)
        
        # Zapisz geometrię przy zamykaniu
        def on_close():
            self.save_window_geometry(win_key, win)
            win.destroy()
            # Przywróć focus na główne okno aplikacji
            self.root.lift()
            self.root.focus_force()
        win.protocol("WM_DELETE_WINDOW", on_close)
        
        # Header
        header = tk.Frame(win, bg=self.COLOR_TOPBAR, pady=10)
        header.pack(fill=tk.X)
        
        tk.Label(
            header,
            text=f"📎 {title}",
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=self.FONT_BOLD
        ).pack(side=tk.LEFT, padx=20)
        
        tk.Label(
            header,
            text=f"Etap: {stage_code}",
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=self.FONT_SMALL
        ).pack(side=tk.LEFT, padx=10)
        
        # Przycisk dodawania (tylko gdy można edytować)
        if can_add_files:
            tk.Button(
                header,
                text="➕ Dodaj plik",
                command=lambda: self.add_stage_attachment(project_db, stage_code, win),
                bg=self.COLOR_GREEN,
                fg="white",
                font=self.FONT_SMALL
            ).pack(side=tk.RIGHT, padx=20)
        else:
            tk.Label(
                header,
                text="🔒 Przejm lock aby dodać pliki",
                bg=self.COLOR_TOPBAR,
                fg="#ffcc00",
                font=self.FONT_SMALL,
                anchor='e'
            ).pack(side=tk.RIGHT, padx=20)
        
        # Drop zone dla drag-and-drop (tylko gdy można edytować)
        if HAS_DND and can_add_files:
            drop_zone = tk.Label(
                win,
                text="📂  Przeciągnij pliki tutaj  📂",
                bg="#e8f4fd",
                fg="#3498db",
                font=("Arial", 12, "italic"),
                relief=tk.GROOVE,
                bd=2,
                pady=20
            )
            drop_zone.pack(fill=tk.X, padx=20, pady=(10, 5))
            
            # Bind drag-and-drop - rejestruj na Label (drop_zone)
            try:
                def handle_drop(event):
                    print(f"📥 DROP EVENT! data='{event.data}'")
                    files_str = event.data
                    
                    files = []
                    try:
                        files = win.tk.splitlist(files_str)
                    except Exception:
                        import re
                        files = re.findall(r'\{([^}]+)\}|(\S+)', files_str)
                        files = [f[0] if f[0] else f[1] for f in files]
                    
                    print(f"📥 Rozparsowano {len(files)} plików: {files}")
                    
                    for file_path in files:
                        file_path = file_path.strip('{}').strip()
                        if not file_path:
                            continue
                        print(f"📎 Dodaję: {file_path}")
                        try:
                            self.add_stage_attachment_from_path(project_db, stage_code, file_path, win)
                        except Exception as e:
                            import traceback
                            traceback.print_exc()
                            messagebox.showerror("Błąd", f"Nie można dodać:\n{file_path}\n\n{e}")
                    
                    drop_zone.config(bg="#e8f4fd")
                
                # Rejestruj drop na WIELU widgetach - Label, okno, canvas
                for widget in [drop_zone, win]:
                    try:
                        widget.drop_target_register(DND_FILES)
                        widget.dnd_bind('<<Drop>>', handle_drop)
                        widget.dnd_bind('<<DragEnter>>', lambda e: drop_zone.config(bg="#c8e6c9", text="📂  Upuść pliki!  📂"))
                        widget.dnd_bind('<<DragLeave>>', lambda e: drop_zone.config(bg="#e8f4fd", text="📂  Przeciągnij pliki tutaj  📂"))
                        print(f"✅ DnD zarejestrowany na: {widget.__class__.__name__}")
                    except Exception as ex:
                        print(f"⚠️ DnD nie udał się na {widget.__class__.__name__}: {ex}")
                
                print(f"✅ Drag-and-drop włączony dla okna {stage_code}")
                
                # Fix: przy pierwszym DnD okno traci focus - przywróć po 100ms
                def restore_focus():
                    try:
                        win.lift()
                        win.focus_force()
                    except:
                        pass
                win.after(100, restore_focus)
            except Exception as ex:
                import traceback
                traceback.print_exc()
                print(f"⚠️ Nie można włączyć drag-and-drop: {ex}")
        
        # Scrollable lista załączników
        list_frame = tk.Frame(win)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        canvas = tk.Canvas(list_frame, bg="white")
        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        
        content_frame = tk.Frame(canvas, bg="white")
        content_frame_id = canvas.create_window((0, 0), window=content_frame, anchor='nw')
        
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        content_frame.bind("<Configure>", on_frame_configure)
        
        def on_canvas_configure(event):
            canvas.itemconfig(content_frame_id, width=event.width)
        
        canvas.bind("<Configure>", on_canvas_configure)
        
        # Załaduj załączniki
        win.content_frame = content_frame
        self.load_stage_attachments_list(project_db, stage_code, content_frame)
    
    def add_stage_attachment(self, project_db: str, stage_code: str, parent_window: tk.Toplevel):
        """Dialog wyboru pliku i dodania załącznika do etapu"""
        from tkinter import filedialog
        
        file_path = filedialog.askopenfilename(
            title="Wybierz plik do załączenia",
            filetypes=[
                ("Wszystkie pliki", "*.*"),
                ("Obrazy", "*.jpg *.jpeg *.png *.gif *.bmp"),
                ("PDF", "*.pdf"),
                ("Excel", "*.xlsx *.xls"),
                ("CSV", "*.csv"),
                ("Word", "*.docx *.doc"),
                ("Tekst", "*.txt")
            ]
        )
        
        if not file_path:
            return
        
        self.add_stage_attachment_from_path(project_db, stage_code, file_path, parent_window)
    
    def add_stage_attachment_from_path(self, project_db: str, stage_code: str, 
                                       file_path: str, parent_window: tk.Toplevel):
        """Dodaj załącznik do etapu z podanej ścieżki (używane przez dialog i drag-and-drop)"""
        try:
            import os
            
            if not os.path.exists(file_path):
                messagebox.showerror("Błąd", f"Plik nie istnieje:\n{file_path}")
                return
            
            file_size = os.path.getsize(file_path)
            
            # Limit 10 MB
            if file_size > 10 * 1024 * 1024:
                messagebox.showwarning(
                    "Plik za duży",
                    f"Plik ma {file_size / 1024 / 1024:.1f} MB.\nMaksymalny rozmiar: 10 MB"
                )
                return
            
            rmm.add_stage_attachment(
                project_db,
                self.selected_project_id,
                stage_code,
                file_path,
                uploaded_by=self.current_user
            )
            
            # Odśwież listę
            self.load_stage_attachments_list(project_db, stage_code, parent_window.content_frame)
            
            self.status_bar.config(
                text=f"✅ Załącznik dodany: {os.path.basename(file_path)}",
                fg=self.COLOR_GREEN
            )
            
            # Odśwież panel główny aby zaktualizować licznik załączników
            self.load_project_stages()
            self.refresh_timeline()
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Błąd", f"Nie można dodać załącznika:\n{e}", parent=parent_win)
            if notes_win:
                notes_win.lift()
                notes_win.focus_set()
    
    def load_stage_attachments_list(self, project_db: str, stage_code: str, container: tk.Frame):
        """Załaduj i wyświetl załączniki dla etapu"""
        # Wyczyść poprzednią zawartość
        for widget in container.winfo_children():
            widget.destroy()
        
        try:
            attachments = rmm.get_stage_attachments(project_db, self.selected_project_id, stage_code)
            
            if not attachments:
                tk.Label(
                    container,
                    text="Brak załączników\n\nKliknij '➕ Dodaj plik' aby dodać pierwszy załącznik",
                    font=("Arial", 11),
                    fg="gray",
                    bg="white",
                    justify=tk.CENTER
                ).pack(pady=50)
                return
            
            # Lista załączników
            for att in attachments:
                self._create_stage_attachment_row(project_db, stage_code, att, container)
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            tk.Label(
                container,
                text=f"⚠️ Błąd ładowania załączników: {e}",
                font=("Arial", 10),
                fg="red",
                bg="white"
            ).pack(anchor='w', padx=20, pady=10)
    
    def _create_stage_attachment_row(self, project_db: str, stage_code: str,
                                     attachment: dict, container: tk.Frame):
        """Utwórz wiersz pojedynczego załącznika"""
        # Pobierz okno nadrzędne aby sprawdzić can_edit
        parent_win = container.winfo_toplevel()
        can_edit = getattr(parent_win, 'can_edit', True)  # Domyślnie True dla kompatybilności
        
        row = tk.Frame(container, bg="white", relief=tk.GROOVE, bd=1)
        row.pack(fill=tk.X, padx=10, pady=5)
        
        # Ikona wg typu pliku
        filename = attachment['filename']
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        icon_map = {
            'pdf': '📄', 'jpg': '🖼️', 'jpeg': '🖼️', 'png': '🖼️', 'gif': '🖼️',
            'xlsx': '📊', 'xls': '📊', 'csv': '📊',
            'docx': '📝', 'doc': '📝', 'txt': '📝',
            'zip': '📦', 'rar': '📦'
        }
        icon = icon_map.get(ext, '📎')
        
        # Rozmiar
        size_kb = attachment['file_size'] / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
        
        # Data i użytkownik
        uploaded_at = attachment['uploaded_at'][:16] if attachment['uploaded_at'] else '?'
        uploaded_by = attachment['uploaded_by'] or '?'
        
        # Info container
        info_frame = tk.Frame(row, bg="white")
        info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=8)
        
        # Nazwa pliku
        tk.Label(
            info_frame,
            text=f"{icon} {filename}",
            font=("Arial", 11, "bold"),
            bg="white",
            fg="#2c3e50",
            anchor="w"
        ).pack(anchor='w')
        
        # Metadane
        tk.Label(
            info_frame,
            text=f"📅 {uploaded_at}  |  👤 {uploaded_by}  |  💾 {size_str}",
            font=("Arial", 9),
            bg="white",
            fg="#7f8c8d",
            anchor="w"
        ).pack(anchor='w', pady=(2, 0))
        
        # Przyciski
        btn_frame = tk.Frame(row, bg="white")
        btn_frame.pack(side=tk.RIGHT, padx=10, pady=8)
        
        tk.Button(
            btn_frame,
            text="🔍 Otwórz",
            command=lambda: self.open_stage_attachment(project_db, attachment['id']),
            bg="#4CAF50",
            fg="white",
            font=("Arial", 9),
            padx=12,
            pady=4
        ).pack(side=tk.LEFT, padx=3)
        
        tk.Button(
            btn_frame,
            text="💾 Pobierz",
            command=lambda: self.download_stage_attachment(project_db, attachment['id'], attachment['filename']),
            bg="#2196F3",
            fg="white",
            font=("Arial", 9),
            padx=12,
            pady=4
        ).pack(side=tk.LEFT, padx=3)
        
        # Przycisk usuń - tylko gdy can_edit
        tk.Button(
            btn_frame,
            text="🗑️ Usuń",
            command=lambda: self.delete_stage_attachment_ui(project_db, stage_code, attachment['id'], container),
            bg=self.COLOR_RED,
            fg="white",
            font=("Arial", 9),
            padx=12,
            pady=4,
            state=tk.NORMAL if can_edit else tk.DISABLED
        ).pack(side=tk.LEFT, padx=3)
    
    def open_stage_attachment(self, project_db: str, attachment_id: int):
        """Otwórz załącznik etapu w domyślnej aplikacji"""
        try:
            temp_path = rmm.save_stage_attachment_to_temp(project_db, attachment_id)
            
            import platform
            import subprocess
            
            system = platform.system()
            if system == 'Windows':
                import os
                os.startfile(temp_path)
            elif system == 'Darwin':  # macOS
                subprocess.run(['open', temp_path], check=True)
            else:  # Linux
                subprocess.run(['xdg-open', temp_path], check=True)
            
            self.status_bar.config(
                text="✅ Otwarto załącznik w aplikacji systemowej",
                fg=self.COLOR_GREEN
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Błąd", f"Nie można otworzyć załącznika:\n{e}")
    
    def download_stage_attachment(self, project_db: str, attachment_id: int, original_filename: str):
        """Pobierz załącznik etapu i zapisz w wybranej lokalizacji"""
        try:
            # Dialog wyboru lokalizacji zapisu
            from tkinter import filedialog
            import os
            
            # Zaproponuj oryginalną nazwę pliku
            file_path = filedialog.asksaveasfilename(
                parent=self.root,
                title="Zapisz załącznik jako",
                initialfile=original_filename,
                defaultextension="",
                filetypes=[
                    ("Wszystkie pliki", "*.*"),
                    ("Dokumenty PDF", "*.pdf"),
                    ("Obrazy", "*.jpg;*.jpeg;*.png;*.gif"),
                    ("Arkusze", "*.xlsx;*.xls;*.csv"),
                    ("Dokumenty", "*.docx;*.doc;*.txt"),
                    ("Archiwa", "*.zip;*.rar")
                ]
            )
            
            if not file_path:  # Użytkownik anulował
                return
                
            # Pobierz dane załącznika z bazy
            attachment_data = rmm.get_stage_attachment_data(project_db, attachment_id)
            
            if not attachment_data:
                messagebox.showerror("Błąd", "Nie można pobrać danych załącznika")
                return
            
            # Zapisz do wybranej lokalizacji
            with open(file_path, 'wb') as f:
                f.write(attachment_data['file_content'])
            
            self.status_bar.config(
                text=f"✅ Załącznik zapisany: {os.path.basename(file_path)}",
                fg=self.COLOR_GREEN
            )
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("Błąd", f"Nie można pobrać załącznika:\n{e}")
    
    def delete_stage_attachment_ui(self, project_db: str, stage_code: str,
                                   attachment_id: int, container: tk.Frame):
        """Usuń załącznik etapu po potwierdzeniu"""
        # Znajdź okno nadrzędne dla przywrócenia focus
        parent_window = container.winfo_toplevel()
        
        if not messagebox.askyesno("Usunąć załącznik?", "Czy na pewno usunąć ten załącznik?", parent=parent_window):
            return
        
        try:
            rmm.delete_stage_attachment(project_db, attachment_id)
            
            # Odśwież listę
            self.load_stage_attachments_list(project_db, stage_code, container)
            
            self.status_bar.config(
                text="✅ Załącznik usunięty",
                fg=self.COLOR_GREEN
            )
            
            # Odśwież panel główny aby zaktualizować licznik załączników
            self.load_project_stages()
            self.refresh_timeline()
            
            # Przywróć focus do okna załączników
            if parent_window and parent_window != self.root:
                parent_window.lift()
                parent_window.focus_set()
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można usunąć załącznika:\n{e}", parent=parent_window)
            # Przywróć focus nawet przy błędzie
            if parent_window and parent_window != self.root:
                parent_window.lift()
                parent_window.focus_set()

    # ============================================================================
    # Plotly Charts
    # ============================================================================

    def _get_project_status_icon(self, project_id: int) -> str:
        """Zwróć ikonę statusu projektu do wyświetlenia na wykresach.
        🏁 = zakończony, 🔄 = w trakcie, ⏸ = wstrzymany, 🆕 = nowy/przyjęty
        """
        try:
            status = rmm.get_project_status(self.master_db_path, project_id)
            if status == ProjectStatus.DONE:
                return '🏁'
            elif status == ProjectStatus.IN_PROGRESS:
                return '🔄'
            elif status == ProjectStatus.PAUSED:
                return '⏸'
            elif status == ProjectStatus.ACCEPTED:
                return '✅'
            else:
                return '🆕'
        except Exception:
            return ''

    def _get_project_status_text(self, project_id: int) -> str:
        """Zwróć tekstowy status projektu (dla matplotlib gdzie emoji nie działają)."""
        try:
            status = rmm.get_project_status(self.master_db_path, project_id)
            if status == ProjectStatus.DONE:
                return '[ZAKOŃCZONY]'
            elif status == ProjectStatus.IN_PROGRESS:
                return '[W TRAKCIE]'
            elif status == ProjectStatus.PAUSED:
                return '[WSTRZYMANY]'
            elif status == ProjectStatus.ACCEPTED:
                return '[PRZYJĘTY]'
            else:
                return '[NOWY]'
        except Exception:
            return ''

    @staticmethod
    def _ensure_min_1day_str(start_str, end_str):
        """Jeśli okres < 24h (stringi dat), rozciągnij do 1 dnia."""
        from datetime import datetime, timedelta
        try:
            s = datetime.fromisoformat(str(start_str)[:10])
            e = datetime.fromisoformat(str(end_str)[:10])
            if (e - s) < timedelta(days=1):
                e = s + timedelta(days=1)
                return start_str[:10], e.strftime('%Y-%m-%d')
        except:
            pass
        return start_str[:10] if start_str else start_str, end_str[:10] if end_str else end_str

    @staticmethod
    def _ensure_min_1day_dt(start_dt, end_dt):
        """Jeśli okres < 24h (datetime), rozciągnij do 1 dnia."""
        from datetime import timedelta
        if (end_dt - start_dt) < timedelta(days=1):
            return start_dt, start_dt + timedelta(days=1)
        return start_dt, end_dt

    def create_gantt_chart(self):
        """Utwórz interaktywny wykres Gantta dla aktualnego projektu"""
        from datetime import datetime, timedelta
        
        if not PLOTLY_AVAILABLE:
            messagebox.showerror("Błąd", "Plotly nie jest zainstalowane.\nZainstaluj: pip install plotly")
            return
            
        if not self.selected_project_id:
            messagebox.showwarning("Brak projektu", "Wybierz projekt najpierw!")
            return

        try:
            self.chart_status.config(text="🔄 Tworzenie wykresu...", fg=self.COLOR_BLUE)
            self.root.update()
            
            # Pobierz dane timeline
            project_db = self.get_project_db_path(self.selected_project_id)
            timeline = rmm.get_stage_timeline(project_db, self.selected_project_id)
            
            if not timeline:
                self.chart_status.config(text="Brak danych do wykresu", fg=self.COLOR_RED)
                return
            
            # Sortuj etapy wg ustalonej kolejności
            timeline.sort(key=lambda s: STAGE_ORDER.get(s['stage_code'], 999))
            
            # DEBUG: Sprawdź zawartość timeline
            print("=== DEBUG TIMELINE ===")
            for i, stage in enumerate(timeline):
                print(f"Etap {i}: {stage['stage_code']}")
                print(f"  - forecast_start: {stage.get('forecast_start')}")
                print(f"  - forecast_end: {stage.get('forecast_end')}")
                print(f"  - actual_periods: {len(stage.get('actual_periods', []))}")
            print("=====================")
            
            # Przygotuj dane dla Gantt chart
            gantt_data = []
            
            # Pobierz nazwy etapów i info o milestone z bazy
            con = rmm._open_rm_connection(project_db)
            stage_names = {}
            stage_milestones = {}
            cursor = con.execute("SELECT code, display_name, is_milestone FROM stage_definitions")
            for row in cursor.fetchall():
                stage_names[row['code']] = row['display_name']
                stage_milestones[row['code']] = bool(row['is_milestone'])
            
            con.close()
            
            for stage in timeline:
                stage_code = stage['stage_code']
                stage_name = stage_names.get(stage_code, stage_code)
                
                # Użyj template z timeline (recalculate_forecast)
                template_start = stage.get('template_start')
                template_end = stage.get('template_end')
                
                # FILTER: Pomiń etapy bez jakichkolwiek danych
                has_template = template_start and template_end
                has_forecast = stage.get('forecast_start') and stage.get('forecast_end')
                has_actual = any(p.get('started_at') for p in stage.get('actual_periods', []))
                
                if not has_template and not has_forecast and not has_actual:
                    print(f"🚫 Pomijam etap {stage_code} - brak danych")
                    continue
                
                # Milestone bez ustawionej daty → pokaż nazwę ale bez pasków
                is_ms = stage_milestones.get(stage_code, False)
                ms_has_date = has_actual or has_template or has_forecast
                if is_ms and not ms_has_date:
                    print(f"⭕ Milestone {stage_code} bez daty - pusty wiersz")
                    gantt_data.append({
                        'Task': f"⭕ {stage_name}",
                        'Start': None,
                        'Finish': None,
                        'Resource': "Milestone (brak daty)",
                        'Complete': 0
                    })
                    continue
                
                print(f"✅ Pokazuję etap {stage_code} (szablon={has_template}, prognoza={has_forecast}, rzeczywiste={has_actual})")
                
                # Dla milestone z datą → użyj actual LUB template (nie rysuj prognozy)
                if is_ms:
                    ms_date_shown = False
                    # 1. Próbuj actual_periods (set_milestone)
                    for i, period in enumerate(stage.get('actual_periods', [])):
                        if period.get('started_at'):
                            start_date = period['started_at']
                            end_date = period.get('ended_at', period['started_at'])
                            start_date, end_date = self._ensure_min_1day_str(start_date, end_date)
                            gantt_data.append({
                                'Task': f"✅ {stage_name}",
                                'Start': start_date,
                                'Finish': end_date,
                                'Resource': "Milestone",
                                'Complete': 100
                            })
                            ms_date_shown = True
                    # 2. Jeśli brak actual → użyj template (ręczna data w GUI)
                    if not ms_date_shown and has_template:
                        tpl_start, tpl_end = self._ensure_min_1day_str(template_start, template_end)
                        gantt_data.append({
                            'Task': f"✅ {stage_name}",
                            'Start': tpl_start,
                            'Finish': tpl_end,
                            'Resource': "Milestone",
                            'Complete': 0
                        })
                    continue
                
                # Szablon/Plan (szary) - rysuj najpierw (pod spodem)
                if has_template:
                    tpl_start, tpl_end = self._ensure_min_1day_str(template_start, template_end)
                    gantt_data.append({
                        'Task': f"{stage_name}",
                        'Start': tpl_start,
                        'Finish': tpl_end,
                        'Resource': "Szablon",
                        'Complete': 0
                    })
                
                # Rzeczywiste okresy (zielone)
                for i, period in enumerate(stage.get('actual_periods', [])):
                    if period.get('started_at'):
                        start_date = period['started_at']
                        end_date = period.get('ended_at', datetime.now().strftime('%Y-%m-%d'))
                        start_date, end_date = self._ensure_min_1day_str(start_date, end_date)
                        
                        gantt_data.append({
                            'Task': f"{stage_name}",
                            'Start': start_date,
                            'Finish': end_date,
                            'Resource': f"Rzeczywiste #{i+1}" if len(stage.get('actual_periods', [])) > 1 else "Rzeczywiste",
                            'Complete': 100 if period.get('ended_at') else 50
                        })
                
                # Plan/forecast (niebieski) - zawsze pokazuj jeśli istnieje
                if stage.get('forecast_start') and stage.get('forecast_end'):
                    forecast_start, forecast_end = self._ensure_min_1day_str(
                        stage['forecast_start'], stage['forecast_end'])
                    
                    gantt_data.append({
                        'Task': f"{stage_name}",
                        'Start': forecast_start,
                        'Finish': forecast_end,
                        'Resource': "Prognoza",
                        'Complete': 0
                    })
            
            if not gantt_data:
                self.chart_status.config(text="Brak okresów do wyświetlenia", fg=self.COLOR_RED)
                return
            
            # DEBUG: Sprawdź dane gantt_data
            print("=== DEBUG GANTT DATA ===")
            for item in gantt_data:
                print(f"Task: {item['Task']}, Resource: {item['Resource']}, Start: {item['Start']}, Finish: {item['Finish']}")
            print("========================")
            
            # Utwórz wykres Gantta
            fig = go.Figure()
            
            # Kolory i style dla różnych typów
            styles = {
                'Szablon':      {'color': '#bdc3c7', 'width': 12, 'opacity': 0.5, 'dash': 'dot'},
                'Prognoza':     {'color': '#3498db', 'width': 16, 'opacity': 0.7, 'dash': 'solid'},
                'Rzeczywiste':  {'color': '#27ae60', 'width': 24, 'opacity': 0.95, 'dash': 'solid'},
                'Milestone':    {'color': '#2ecc71', 'width': 20, 'opacity': 0.9, 'dash': 'solid'},
            }
            
            # Kolejność rysowania: Szablon → Prognoza → Rzeczywiste (na wierzchu)
            draw_order = ['Szablon', 'Milestone', 'Prognoza']
            # Rzeczywiste z numeracją
            draw_order_all = []
            for res_type in draw_order:
                draw_order_all.extend([item for item in gantt_data if item['Resource'] == res_type])
            draw_order_all.extend([item for item in gantt_data if 'Rzeczywiste' in item['Resource']])
            # Placeholder (bez daty) na początku
            draw_order_all = [item for item in gantt_data if item['Start'] is None] + draw_order_all
            
            added_legends = set()
            
            for item in draw_order_all:
                # Placeholder milestone (bez daty)
                if item['Start'] is None:
                    fig.add_trace(go.Scatter(
                        x=[None],
                        y=[item['Task']],
                        mode='markers',
                        marker=dict(size=0, opacity=0),
                        name=item['Resource'],
                        showlegend=False,
                        hoverinfo='skip'
                    ))
                    continue
                
                # Określ styl na podstawie Resource
                res_key = item['Resource']
                if 'Rzeczywiste' in res_key:
                    style = styles['Rzeczywiste']
                    if item['Complete'] < 100:
                        style = {**style, 'color': '#f39c12', 'dash': 'dash'}  # Trwający = pomarańczowy przerywany
                elif 'Milestone' in res_key:
                    style = styles['Milestone']
                elif 'Szablon' in res_key:
                    style = styles['Szablon']
                elif 'Prognoza' in res_key:
                    style = styles['Prognoza']
                else:
                    style = styles['Prognoza']
                
                legend_key = res_key.split('#')[0].strip()  # "Rzeczywiste #1" → "Rzeczywiste"
                show_legend = legend_key not in added_legends
                added_legends.add(legend_key)
                
                fig.add_trace(go.Scatter(
                    x=[item['Start'], item['Finish']],
                    y=[item['Task'], item['Task']],
                    mode='lines+markers' if item.get('Complete', 100) < 100 else 'lines',
                    line=dict(
                        color=style['color'], 
                        width=style['width'],
                        dash=style.get('dash', 'solid')
                    ),
                    marker=dict(
                        size=10,
                        symbol='triangle-right',
                        color=style['color']
                    ) if item.get('Complete', 100) < 100 else None,
                    opacity=style['opacity'],
                    name=legend_key,
                    legendgroup=legend_key,
                    showlegend=show_legend,
                    hovertemplate=f"<b>{item['Task']}</b><br>" +
                                f"Typ: {item['Resource']}<br>" +
                                f"Start: {item['Start']}<br>" +
                                f"Koniec: {item['Finish']}<br>" +
                                f"<extra></extra>"
                ))
            
            # Formatowanie wykresu
            fig.update_layout(
                title=f"📊 Timeline {self.project_names.get(self.selected_project_id, f'Projekt {self.selected_project_id}')} {self._get_project_status_icon(self.selected_project_id)}",
                xaxis_title="📅 Data",
                yaxis_title="🔧 Etapy",
                height=max(400, len(set(item['Task'] for item in gantt_data)) * 60),
                showlegend=True,
                template="plotly_white",
                margin=dict(l=150, r=50, t=80, b=50)
            )
            
            # Siatka czasowa
            fig.update_xaxes(
                showgrid=True,
                gridwidth=1,
                gridcolor='lightgray'
            )
            
            fig.update_yaxes(
                showgrid=True,
                gridwidth=1,
                gridcolor='lightgray'
            )
            
            # Zapisz do tymczasowego pliku HTML i otwórz
            import tempfile
            import webbrowser
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                html_content = fig.to_html(include_plotlyjs=True)
                f.write(html_content)
                self.last_chart_path = f.name
            
            # Otwórz w przeglądarce
            webbrowser.open(f'file://{self.last_chart_path}')
            
            self.chart_status.config(
                text=f"✅ Wykres utworzony ({len(gantt_data)} okresów)", 
                fg=self.COLOR_GREEN
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.chart_status.config(text="❌ Błąd tworzenia wykresu", fg=self.COLOR_RED)
            messagebox.showerror("Błąd wykresu", f"Nie można utworzyć wykresu:\n{e}")

    def export_chart_html(self):
        """Eksportuj ostatni wykres do pliku HTML"""
        if not PLOTLY_AVAILABLE:
            messagebox.showerror("Błąd", "Plotly nie jest dostępne")
            return
            
        if not hasattr(self, 'last_chart_path') or not self.last_chart_path:
            messagebox.showwarning("Brak wykresu", "Najpierw utwórz wykres Gantta")
            return
        
        # Dialog zapisu
        file_path = filedialog.asksaveasfilename(
            title="Zapisz wykres jako HTML",
            defaultextension=".html",
            filetypes=[
                ("Pliki HTML", "*.html"),
                ("Wszystkie pliki", "*.*")
            ],
            initialfile=f"gantt_projekt_{self.selected_project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        )
        
        if not file_path:
            return
        
        try:
            # Skopiuj plik
            import shutil
            shutil.copy2(self.last_chart_path, file_path)
            
            self.status_bar.config(
                text=f"✅ Wykres zapisany: {os.path.basename(file_path)}",
                fg=self.COLOR_GREEN
            )
            
            # Zapytaj czy otworzyć
            if messagebox.askyesno("Sukces", f"Wykres zapisany!\n{file_path}\n\nCzy otworzyć plik?"):
                import webbrowser
                webbrowser.open(f'file://{file_path}')
                
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można zapisać wykresu:\n{e}")

    def select_multiple_projects_dialog(self):
        """Dialog wyboru wielu projektów do porównania"""
        if not self.projects:
            messagebox.showwarning("Brak projektów", "Brak dostępnych projektów do porównania")
            return []
        
        # Okno dialogowe
        dialog = tk.Toplevel(self.root)
        dialog.title("📈 Wybierz projekty do porównania")
        dialog.geometry("400x500")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Centrowanie
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (400 // 2)
        y = (dialog.winfo_screenheight() // 2) - (500 // 2)
        dialog.geometry(f"400x500+{x}+{y}")
        
        selected_projects = []
        
        # Header
        header = tk.Frame(dialog, bg=self.COLOR_TOPBAR, pady=10)
        header.pack(fill=tk.X)
        
        tk.Label(
            header,
            text="📈 Porównanie projektów",
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 14, "bold")
        ).pack()
        
        tk.Label(
            header,
            text="Wybierz projekty do nakładania na wykres Gantt",
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 10)
        ).pack()
        
        # Lista projektów z checkboxami
        main_frame = tk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        tk.Label(main_frame, text="Dostępne projekty:", font=("Arial", 11, "bold")).pack(anchor=tk.W)
        
        # Scrollable frame
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Checkboxy dla projektów
        project_vars = {}
        for project_id in self.projects:
            project_name = self.project_names.get(project_id, f"Projekt {project_id}")
            
            var = tk.BooleanVar()
            project_vars[project_id] = var
            
            cb = tk.Checkbutton(
                scrollable_frame,
                text=f"Projekt {project_id}: {project_name}",
                variable=var,
                font=("Arial", 10)
            )
            cb.pack(anchor=tk.W, pady=2)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Przyciski
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def on_compare():
            selected = [pid for pid, var in project_vars.items() if var.get()]
            if len(selected) < 2:
                messagebox.showwarning("Za mało projektów", "Wybierz przynajmniej 2 projekty do porównania")
                return
            selected_projects.extend(selected)
            dialog.destroy()
        
        def on_cancel():
            dialog.destroy()
        
        tk.Button(
            btn_frame,
            text="📈 Porównaj",
            command=on_compare,
            bg=self.COLOR_PURPLE,
            fg="white",
            font=("Arial", 10, "bold"),
            width=15
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="❌ Anuluj",
            command=on_cancel,
            bg=self.COLOR_RED,
            fg="white",
            font=("Arial", 10),
            width=15
        ).pack(side=tk.RIGHT, padx=5)
        
        dialog.wait_window()
        return selected_projects

    def create_multi_project_gantt(self):
        """Utwórz porównawczy wykres Gantta dla wielu projektów"""
        from datetime import datetime, timedelta
        
        if not PLOTLY_AVAILABLE:
            messagebox.showerror("Błąd", "Plotly nie jest zainstalowane.\nZainstaluj: pip install plotly")
            return
        
        # Dialog wyboru projektów
        selected_projects = self.select_multiple_projects_dialog()
        if not selected_projects:
            return
        
        try:
            self.chart_status.config(text="🔄 Tworzenie porównania...", fg=self.COLOR_BLUE)
            self.root.update()
            
            # Kolory dla projektów
            project_colors = [
                '#27ae60',  # Zielony
                '#3498db',  # Niebieski
                '#e74c3c',  # Czerwony
                '#f39c12',  # Pomarańczowy
                '#9b59b6',  # Fioletowy
                '#1abc9c',  # Turkusowy
                '#34495e',  # Ciemnoszary
                '#e67e22',  # Pomarańczowy ciemny
            ]
            
            gantt_data = []
            
            for proj_idx, project_id in enumerate(selected_projects):
                color = project_colors[proj_idx % len(project_colors)]
                
                # Pobierz dane dla projektu
                project_db = self.get_project_db_path(project_id) 
                timeline = rmm.get_stage_timeline(project_db, project_id)
                
                # Pobierz nazwy etapów
                con = rmm._open_rm_connection(project_db)
                stage_names = {}
                stage_milestones = {}
                cursor = con.execute("SELECT code, display_name, is_milestone FROM stage_definitions")
                for row in cursor.fetchall():
                    stage_names[row['code']] = row['display_name']
                    stage_milestones[row['code']] = bool(row['is_milestone'])
                
                con.close()
                
                project_name = self.project_names.get(project_id, f"Projekt {project_id}")
                status_icon = self._get_project_status_icon(project_id)
                project_label = f"{status_icon} P{project_id}"
                
                for stage in timeline:
                    stage_code = stage['stage_code']
                    stage_name = stage_names.get(stage_code, stage_code)
                    
                    # Użyj template z timeline (recalculate_forecast)
                    template_start = stage.get('template_start')
                    template_end = stage.get('template_end')
                    
                    # FILTER: Pomiń etapy bez jakichkolwiek danych
                    has_template = template_start and template_end
                    has_forecast = stage.get('forecast_start') and stage.get('forecast_end')
                    has_actual = any(p.get('started_at') for p in stage.get('actual_periods', []))
                    
                    if not has_template and not has_forecast and not has_actual:
                        print(f"🚫 [multi] Projekt {project_id}, pomijam etap {stage_code} - brak danych")
                        continue
                    
                    # Milestone bez ustawionej daty → pokaż nazwę ale bez pasków
                    is_ms = stage_milestones.get(stage_code, False)
                    ms_has_date = has_actual or has_template or has_forecast
                    if is_ms and not ms_has_date:
                        print(f"⭕ [multi] Milestone {stage_code} bez daty - pusty wiersz")
                        gantt_data.append({
                            'Task': f"{project_label}: ⭕ {stage_name}",
                            'Start': None,
                            'Finish': None,
                            'Resource': f"{project_name} (Milestone)",
                            'Project': project_id,
                            'Color': '#bdc3c7',
                            'Type': 'Milestone'
                        })
                        continue
                    
                    # Dla milestone z datą → actual LUB template
                    if is_ms:
                        ms_date_shown = False
                        for i, period in enumerate(stage.get('actual_periods', [])):
                            if period.get('started_at'):
                                start_date = period['started_at']
                                end_date = period.get('ended_at', period['started_at'])
                                start_date, end_date = self._ensure_min_1day_str(start_date, end_date)
                                gantt_data.append({
                                    'Task': f"{project_label}: ✅ {stage_name}",
                                    'Start': start_date,
                                    'Finish': end_date,
                                    'Resource': f"{project_name} (Milestone)",
                                    'Project': project_id,
                                    'Color': color,
                                    'Type': 'Milestone'
                                })
                                ms_date_shown = True
                        if not ms_date_shown and has_template:
                            tpl_start, tpl_end = self._ensure_min_1day_str(template_start, template_end)
                            gantt_data.append({
                                'Task': f"{project_label}: ✅ {stage_name}",
                                'Start': tpl_start,
                                'Finish': tpl_end,
                                'Resource': f"{project_name} (Milestone)",
                                'Project': project_id,
                                'Color': color,
                                'Type': 'Milestone'
                            })
                        continue
                    
                    # Szablon/Plan (szary pasek pod spodem)
                    if has_template:
                        tpl_start, tpl_end = self._ensure_min_1day_str(template_start, template_end)
                        gantt_data.append({
                            'Task': f"{project_label}: {stage_name}",
                            'Start': tpl_start,
                            'Finish': tpl_end,
                            'Resource': f"{project_name} (Szablon)",
                            'Project': project_id,
                            'Color': '#95a5a6',
                            'Type': 'Szablon'
                        })
                    
                    # Rzeczywiste okresy
                    for i, period in enumerate(stage.get('actual_periods', [])):
                        if period.get('started_at'):
                            start_date = period['started_at']
                            end_date = period.get('ended_at', datetime.now().strftime('%Y-%m-%d'))
                            start_date, end_date = self._ensure_min_1day_str(start_date, end_date)
                            
                            gantt_data.append({
                                'Task': f"{project_label}: {stage_name}",
                                'Start': start_date,
                                'Finish': end_date,
                                'Resource': f"{project_name}",
                                'Project': project_id,
                                'Color': color,
                                'Type': 'Rzeczywiste'
                            })
                    
                    # Prognozy
                    if stage.get('forecast_start') and stage.get('forecast_end'):
                        forecast_start, forecast_end = self._ensure_min_1day_str(
                            stage['forecast_start'], stage['forecast_end'])
                        
                        gantt_data.append({
                            'Task': f"{project_label}: {stage_name}",
                            'Start': forecast_start,
                            'Finish': forecast_end,
                            'Resource': f"{project_name} (Prognoza)",
                            'Project': project_id,
                            'Color': color,
                            'Type': 'Prognoza'
                        })
            
            if not gantt_data:
                self.chart_status.config(text="Brak danych do porównania", fg=self.COLOR_RED)
                return
            
            # Utwórz wykres
            fig = go.Figure()
            
            for item in gantt_data:
                # Placeholder milestone (bez daty) → dodaj niewidoczny punkt
                if item['Start'] is None:
                    fig.add_trace(go.Scatter(
                        x=[None],
                        y=[item['Task']],
                        mode='markers',
                        marker=dict(size=0, opacity=0),
                        name=item['Resource'],
                        showlegend=False,
                        hoverinfo='skip'
                    ))
                    continue
                
                # Zmień przezroczystość i grubość dla typów
                if item['Type'] == 'Szablon':
                    opacity = 0.3
                    line_width = 20
                elif item['Type'] == 'Milestone':
                    opacity = 0.9
                    line_width = 12
                elif item['Type'] == 'Rzeczywiste':
                    opacity = 0.8
                    line_width = 15
                else:  # Prognoza
                    opacity = 0.4
                    line_width = 10
                
                fig.add_trace(go.Scatter(
                    x=[item['Start'], item['Finish']],
                    y=[item['Task'], item['Task']],
                    mode='lines',
                    line=dict(color=item['Color'], width=line_width),
                    opacity=opacity,
                    name=item['Resource'],
                    showlegend=item['Resource'] not in [trace.name for trace in fig.data],
                    hovertemplate=f"<b>{item['Task']}</b><br>" +
                                f"Projekt: {item['Project']}<br>" +
                                f"Typ: {item['Type']}<br>" +
                                f"Start: {item['Start']}<br>" +
                                f"Koniec: {item['Finish']}<br>" +
                                f"<extra></extra>"
                ))
            
            # Formatowanie
            fig.update_layout(
                title=f"📈 Porównanie projektów: {', '.join(map(str, selected_projects))}",
                xaxis_title="📅 Data",
                yaxis_title="🔧 Etapy projektów",
                height=max(600, len(gantt_data) * 25),
                showlegend=True,
                template="plotly_white",
                margin=dict(l=200, r=50, t=80, b=50)
            )
            
            # Siatka
            fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
            fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
            
            # Zapisz i otwórz
            import tempfile, webbrowser
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                html_content = fig.to_html(include_plotlyjs=True)
                f.write(html_content)
                self.last_chart_path = f.name
            
            webbrowser.open(f'file://{self.last_chart_path}')
            
            self.chart_status.config(
                text=f"✅ Porównanie utworzone ({len(selected_projects)} projektów)",
                fg=self.COLOR_GREEN
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.chart_status.config(text="❌ Błąd porównania", fg=self.COLOR_RED)
            messagebox.showerror("Błąd porównania", f"Nie można utworzyć porównania:\n{e}")

    # ========================================================================
    #  MULTI-PROJECT GANTT CHART (osobne okno)
    # ========================================================================

    def open_multi_project_chart(self):
        """Otwórz wykres Gantta z wieloma projektami w osobnym oknie"""
        if not MATPLOTLIB_AVAILABLE:
            messagebox.showerror("Błąd", "Matplotlib nie jest zainstalowane.")
            return
        if not self.projects:
            messagebox.showwarning("Brak projektów", "Brak załadowanych projektów.")
            return
        
        current_ids = set()
        if self.selected_project_id:
            current_ids.add(self.selected_project_id)
        self._open_project_selector(parent=self.root, current_ids=current_ids)

    def _mp_select_projects_dialog(self):
        """Dialog wyboru projektów — zmiana zestawu projektów w otwartym oknie MP"""
        if not self.projects:
            return
        current_ids = set(self._mp_chart_meta.get('project_ids', [])) if hasattr(self, '_mp_chart_meta') and self._mp_chart_meta else set()
        pinned = getattr(self, '_mp_pinned_projects', set())
        self._open_project_selector(parent=self._mp_chart_window, current_ids=current_ids, pinned_ids=pinned)

    def _open_project_selector(self, parent, current_ids=None, pinned_ids=None):
        """Profesjonalny dialog wyboru projektów z filtrami statusu, czasu i pinowaniem.
        
        Args:
            parent: okno rodzic
            current_ids: set z aktualnie zaznaczonymi project_id
            pinned_ids: set z przypiętymi project_id (nie reagują na filtry)
        """
        from datetime import datetime, timedelta
        import os
        
        if current_ids is None:
            current_ids = set()
        if pinned_ids is None:
            pinned_ids = set()
        
        sel = tk.Toplevel(parent)
        sel.title("📊 Wybór projektów — Multi-projekt Gantt")
        sel.transient(parent)
        sel.grab_set()
        
        w, h = 750, 720
        sel.update_idletasks()
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw // 2) - (w // 2)
            y = py + (ph // 2) - (h // 2)
        except Exception:
            x = (sel.winfo_screenwidth() // 2) - (w // 2)
            y = (sel.winfo_screenheight() // 2) - (h // 2)
        sel.geometry(f"{w}x{h}+{x}+{y}")
        sel.minsize(650, 550)
        
        # ===== Zbierz dane o projektach (jednorazowo) =====
        proj_info = {}  # pid -> {name, status, health, variance, forecast_end, is_paused, is_finished}
        for pid in self.projects:
            pname = self.project_names.get(pid, f"Projekt {pid}")
            info = {'name': pname, 'status': 'UNKNOWN', 'health': 'UNKNOWN',
                    'variance': 0, 'forecast_end': None, 'is_paused': False, 'is_finished': False,
                    'has_db': False}
            try:
                pdb = self.get_project_db_path(pid)
                if os.path.exists(pdb):
                    info['has_db'] = True
                    info['is_finished'] = rmm.is_milestone_set(pdb, pid, 'ZAKONCZONY')
                    info['is_paused'] = rmm.is_project_paused(pdb, pid)
                    ps = rmm.get_project_status(self.master_db_path, pid)
                    info['status'] = ps  # ProjectStatus enum
                    try:
                        summary = rmm.get_project_status_summary(pdb, pid)
                        info['health'] = summary.get('status', 'UNKNOWN')  # DELAYED/AT_RISK/ON_TRACK
                        info['variance'] = summary.get('overall_variance_days', 0)
                        info['forecast_end'] = summary.get('completion_forecast')
                    except Exception:
                        pass
            except Exception:
                pass
            proj_info[pid] = info
        
        # ===== FILTRY — górna sekcja =====
        filter_frame = tk.LabelFrame(sel, text="🔍 Filtry", font=("Arial", 10, "bold"),
                                      padx=8, pady=5)
        filter_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # --- Wiersz 1: Filtry statusu ---
        row1 = tk.Frame(filter_frame)
        row1.pack(fill=tk.X, pady=2)
        tk.Label(row1, text="Status:", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(0, 5))
        
        status_filters = {}
        status_defs = [
            ('active', '🔄 Aktywne', True),
            ('paused', '⏸ Wstrzymane', False),
            ('finished', '🏁 Zakończone', False),
            ('new', '🆕 Nowe', False),
        ]
        for key, label, default in status_defs:
            var = tk.BooleanVar(value=default)
            status_filters[key] = var
            tk.Checkbutton(row1, text=label, variable=var, font=("Arial", 9),
                          command=lambda: apply_filters()).pack(side=tk.LEFT, padx=3)
        
        # --- Wiersz 2: Filtry zdrowia (variance) ---
        row2 = tk.Frame(filter_frame)
        row2.pack(fill=tk.X, pady=2)
        tk.Label(row2, text="Terminowość:", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(0, 5))
        
        health_filters = {}
        health_defs = [
            ('on_track', '✅ W terminie', True),
            ('at_risk', '⚠️ Zagrożone', True),
            ('delayed', '🔴 Opóźnione', True),
        ]
        for key, label, default in health_defs:
            var = tk.BooleanVar(value=default)
            health_filters[key] = var
            tk.Checkbutton(row2, text=label, variable=var, font=("Arial", 9),
                          command=lambda: apply_filters()).pack(side=tk.LEFT, padx=3)
        
        # --- Wiersz 3: Filtry czasowe ---
        row3 = tk.Frame(filter_frame)
        row3.pack(fill=tk.X, pady=2)
        tk.Label(row3, text="Okres:", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(0, 5))
        
        time_filter_var = tk.StringVar(value='all')
        time_options = [
            ('all', 'Wszystkie'),
            ('q_current', 'Bieżący kwartał'),
            ('q_next', 'Następny kwartał'),
            ('h_current', 'Bieżące półrocze'),
            ('year_current', 'Bieżący rok'),
            ('custom', 'Zakres dat...'),
        ]
        time_menu = tk.OptionMenu(row3, time_filter_var, *[k for k, _ in time_options],
                                   command=lambda _: on_time_filter_change())
        time_menu.config(font=("Arial", 9), width=18)
        time_menu.pack(side=tk.LEFT, padx=3)
        # Ustaw etykiety menu
        menu = time_menu['menu']
        menu.delete(0, tk.END)
        for key, label in time_options:
            menu.add_command(label=label, command=lambda k=key: (time_filter_var.set(k), on_time_filter_change()))
        
        # Custom date range
        date_frame = tk.Frame(row3)
        date_frame.pack(side=tk.LEFT, padx=5)
        tk.Label(date_frame, text="Od:", font=("Arial", 8)).pack(side=tk.LEFT)
        date_from_var = tk.StringVar()
        date_from_entry = tk.Entry(date_frame, textvariable=date_from_var, width=10, font=("Arial", 9))
        date_from_entry.pack(side=tk.LEFT, padx=2)
        tk.Label(date_frame, text="Do:", font=("Arial", 8)).pack(side=tk.LEFT)
        date_to_var = tk.StringVar()
        date_to_entry = tk.Entry(date_frame, textvariable=date_to_var, width=10, font=("Arial", 9))
        date_to_entry.pack(side=tk.LEFT, padx=2)
        tk.Button(date_frame, text="🔍", font=("Arial", 8),
                  command=lambda: apply_filters()).pack(side=tk.LEFT, padx=2)
        date_frame.pack_forget()  # Ukryj — pokaż tylko gdy custom
        
        def on_time_filter_change():
            if time_filter_var.get() == 'custom':
                date_frame.pack(side=tk.LEFT, padx=5)
            else:
                date_frame.pack_forget()
            apply_filters()
        
        def get_time_range():
            """Zwróć (date_from, date_to) na podstawie wybranego filtra czasowego"""
            now = datetime.now()
            tf = time_filter_var.get()
            if tf == 'all':
                return None, None
            elif tf == 'q_current':
                q_start_month = ((now.month - 1) // 3) * 3 + 1
                d_from = datetime(now.year, q_start_month, 1)
                q_end_month = q_start_month + 2
                if q_end_month == 12:
                    d_to = datetime(now.year + 1, 1, 1) - timedelta(days=1)
                else:
                    d_to = datetime(now.year, q_end_month + 1, 1) - timedelta(days=1)
                return d_from, d_to
            elif tf == 'q_next':
                q_start_month = ((now.month - 1) // 3) * 3 + 4
                y = now.year
                if q_start_month > 12:
                    q_start_month -= 12
                    y += 1
                d_from = datetime(y, q_start_month, 1)
                q_end_month = q_start_month + 2
                if q_end_month > 12:
                    d_to = datetime(y + 1, q_end_month - 12 + 1, 1) - timedelta(days=1)
                else:
                    d_to = datetime(y, q_end_month + 1, 1) - timedelta(days=1)
                return d_from, d_to
            elif tf == 'h_current':
                if now.month <= 6:
                    return datetime(now.year, 1, 1), datetime(now.year, 6, 30)
                else:
                    return datetime(now.year, 7, 1), datetime(now.year, 12, 31)
            elif tf == 'year_current':
                return datetime(now.year, 1, 1), datetime(now.year, 12, 31)
            elif tf == 'custom':
                try:
                    d_from = datetime.strptime(date_from_var.get().strip(), '%Y-%m-%d') if date_from_var.get().strip() else None
                except ValueError:
                    d_from = None
                try:
                    d_to = datetime.strptime(date_to_var.get().strip(), '%Y-%m-%d') if date_to_var.get().strip() else None
                except ValueError:
                    d_to = None
                return d_from, d_to
            return None, None
        
        def project_in_time_range(pid, d_from, d_to):
            """Sprawdź czy projekt ma aktywność w podanym przedziale czasowym"""
            info = proj_info[pid]
            fe = info.get('forecast_end')
            if not fe:
                return True  # Brak danych — pokaż
            try:
                fe_dt = datetime.strptime(fe[:10], '%Y-%m-%d') if isinstance(fe, str) else fe
            except Exception:
                return True
            # Projekt się kwalifikuje jeśli jego forecast_end wypada po d_from
            # i nie zaczął się po d_to (przybliżenie — nie mamy global start)
            if d_from and fe_dt < d_from:
                return False
            # Forecast_end po d_to → prawdopodobnie aktywny w tym przedziale
            return True
        
        # --- Wiersz 4: Akcje filtrów ---
        row4 = tk.Frame(filter_frame)
        row4.pack(fill=tk.X, pady=(4, 2))
        
        def clear_filters(event=None):
            """Resetuj filtry — pokaż wszystko (wszystkie checkboxy ON)"""
            for var in status_filters.values():
                var.set(True)
            for var in health_filters.values():
                var.set(True)
            time_filter_var.set('all')
            date_frame.pack_forget()
            date_from_var.set('')
            date_to_var.set('')
            apply_filters()
        
        def show_all_projects(event=None):
            """Pokaż wszystkie projekty (widoczne bez zmiany zaznaczenia)"""
            for pid in self.projects:
                row_widgets[pid].pack(fill=tk.X)
            inner.update_idletasks()
            canvas_sel.configure(scrollregion=canvas_sel.bbox("all"))
            update_count()
        
        tk.Button(row4, text="🧹 Wyczyść filtry (Ctrl+Del)", font=("Arial", 9),
                  command=clear_filters).pack(side=tk.LEFT, padx=3)
        tk.Button(row4, text="👁 Pokaż wszystkie (Ctrl+Shift+A)", font=("Arial", 9),
                  command=show_all_projects).pack(side=tk.LEFT, padx=3)
        
        # ===== LISTA PROJEKTÓW =====
        list_frame = tk.Frame(sel)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Header
        hdr = tk.Frame(list_frame, bg="#ecf0f1")
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="☑", width=3, font=("Arial", 8, "bold"), bg="#ecf0f1").pack(side=tk.LEFT)
        tk.Label(hdr, text="📌", width=3, font=("Arial", 8), bg="#ecf0f1").pack(side=tk.LEFT)
        tk.Label(hdr, text="Projekt", width=30, font=("Arial", 9, "bold"), bg="#ecf0f1", anchor="w").pack(side=tk.LEFT, padx=5)
        tk.Label(hdr, text="Status", width=12, font=("Arial", 9, "bold"), bg="#ecf0f1").pack(side=tk.LEFT)
        tk.Label(hdr, text="Terminowość", width=12, font=("Arial", 9, "bold"), bg="#ecf0f1").pack(side=tk.LEFT)
        tk.Label(hdr, text="Odchylenie", width=10, font=("Arial", 9, "bold"), bg="#ecf0f1").pack(side=tk.LEFT)
        tk.Label(hdr, text="Koniec (prognoza)", width=14, font=("Arial", 9, "bold"), bg="#ecf0f1").pack(side=tk.LEFT)
        
        # Scrollable list
        outer = tk.Frame(list_frame)
        outer.pack(fill=tk.BOTH, expand=True)
        canvas_sel = tk.Canvas(outer, highlightthickness=0)
        scrollbar = tk.Scrollbar(outer, orient="vertical", command=canvas_sel.yview)
        inner = tk.Frame(canvas_sel)
        inner.bind("<Configure>", lambda e: canvas_sel.configure(scrollregion=canvas_sel.bbox("all")))
        canvas_sel.create_window((0, 0), window=inner, anchor="nw")
        canvas_sel.configure(yscrollcommand=scrollbar.set)
        canvas_sel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # mousewheel scroll
        canvas_sel.bind_all("<MouseWheel>", lambda e: canvas_sel.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        
        check_vars = {}   # pid -> BooleanVar (zaznaczenie)
        pin_vars = {}      # pid -> BooleanVar (przypięcie)
        row_widgets = {}   # pid -> frame
        
        def status_text(info):
            if info['is_finished']:
                return "🏁 Zakończony"
            if info['is_paused']:
                return "⏸ Wstrzymany"
            ps = info['status']
            if ps == ProjectStatus.NEW:
                return "🆕 Nowy"
            if ps == ProjectStatus.ACCEPTED:
                return "✅ Przyjęty"
            return "🔄 Aktywny"
        
        def health_text(info):
            h = info['health']
            if h == 'DELAYED':
                return "🔴 Opóźniony"
            elif h == 'AT_RISK':
                return "⚠️ Zagrożony"
            elif h == 'ON_TRACK':
                return "✅ W terminie"
            return "—"
        
        def variance_text(info):
            v = info['variance']
            if v > 0:
                return f"+{v}d"
            elif v < 0:
                return f"{v}d"
            return "0d"
        
        def variance_color(info):
            v = info['variance']
            if v > 10:
                return '#e74c3c'
            elif v > 5:
                return '#e67e22'
            elif v < 0:
                return '#27ae60'
            return '#333333'
        
        def forecast_text(info):
            fe = info.get('forecast_end')
            if not fe:
                return "—"
            try:
                dt = datetime.strptime(fe[:10], '%Y-%m-%d') if isinstance(fe, str) else fe
                return dt.strftime('%d-%m-%Y')
            except Exception:
                return str(fe)[:10]
        
        no_db_pids = set()  # projekty bez pliku bazy danych
        
        for pid in self.projects:
            info = proj_info[pid]
            has_db = info.get('has_db', False)
            row = tk.Frame(inner, pady=1)
            row.pack(fill=tk.X)
            
            if has_db:
                cv = tk.BooleanVar(value=(pid in current_ids))
                check_vars[pid] = cv
                tk.Checkbutton(row, variable=cv, width=1).pack(side=tk.LEFT, padx=(2, 0))
                
                pv = tk.BooleanVar(value=(pid in pinned_ids))
                pin_vars[pid] = pv
                tk.Checkbutton(row, variable=pv, text="📌", indicatoron=0,
                              font=("Arial", 8), width=3, selectcolor="#f1c40f",
                              command=lambda: apply_filters()).pack(side=tk.LEFT)
            else:
                # Projekt bez bazy — disabled, nie do zaznaczenia
                no_db_pids.add(pid)
                cv = tk.BooleanVar(value=False)
                check_vars[pid] = cv
                cb = tk.Checkbutton(row, variable=cv, width=1, state='disabled')
                cb.pack(side=tk.LEFT, padx=(2, 0))
                pv = tk.BooleanVar(value=False)
                pin_vars[pid] = pv
                tk.Label(row, text="  ⛔", font=("Arial", 8), width=3, fg="#bdc3c7").pack(side=tk.LEFT)
                row.configure(bg="#f5f5f5")
            
            name_fg = "#333" if has_db else "#aaaaaa"
            name_lbl = info['name'] if has_db else f"{info['name']}  (brak bazy danych)"
            tk.Label(row, text=name_lbl, font=("Arial", 9), anchor="w",
                    width=30, fg=name_fg).pack(side=tk.LEFT, padx=5)
            tk.Label(row, text=status_text(info) if has_db else "⛔ Brak danych",
                    font=("Arial", 8), width=12, fg="#333" if has_db else "#bdc3c7").pack(side=tk.LEFT)
            tk.Label(row, text=health_text(info) if has_db else "—",
                    font=("Arial", 8), width=12, fg="#333" if has_db else "#bdc3c7").pack(side=tk.LEFT)
            tk.Label(row, text=variance_text(info) if has_db else "—",
                    font=("Arial", 8, "bold"),
                    fg=variance_color(info) if has_db else "#bdc3c7", width=10).pack(side=tk.LEFT)
            tk.Label(row, text=forecast_text(info) if has_db else "—",
                    font=("Arial", 8), width=14, fg="#333" if has_db else "#bdc3c7").pack(side=tk.LEFT)
            
            row_widgets[pid] = row
        
        # ===== LOGIKA FILTRÓW =====
        def matches_status_filter(pid):
            info = proj_info[pid]
            if info['is_finished']:
                return status_filters['finished'].get()
            if info['is_paused']:
                return status_filters['paused'].get()
            if info['status'] == ProjectStatus.NEW:
                return status_filters['new'].get()
            return status_filters['active'].get()
        
        def matches_health_filter(pid):
            info = proj_info[pid]
            h = info['health']
            if h == 'DELAYED':
                return health_filters['delayed'].get()
            elif h == 'AT_RISK':
                return health_filters['at_risk'].get()
            elif h == 'ON_TRACK':
                return health_filters['on_track'].get()
            return True  # UNKNOWN → zawsze pokaż
        
        def apply_filters():
            """Zastosuj filtry — pokaz/ukryj projekty, zaznacz/odznacz wg filtrów.
            Przypięte (📌) zawsze widoczne i zaznaczone."""
            d_from, d_to = get_time_range()
            
            for pid in self.projects:
                # Projekty bez bazy — zawsze widoczne, zawsze odznaczone
                if pid in no_db_pids:
                    row_widgets[pid].pack(fill=tk.X)
                    check_vars[pid].set(False)
                    continue
                
                is_pinned = pin_vars[pid].get()
                row = row_widgets[pid]
                
                if is_pinned:
                    row.pack(fill=tk.X)
                    check_vars[pid].set(True)
                    continue
                
                visible = (matches_status_filter(pid) and
                           matches_health_filter(pid) and
                           (d_from is None or project_in_time_range(pid, d_from, d_to)))
                
                if visible:
                    row.pack(fill=tk.X)
                    check_vars[pid].set(True)
                else:
                    row.pack_forget()
                    check_vars[pid].set(False)
            
            # Odśwież scroll region
            inner.update_idletasks()
            canvas_sel.configure(scrollregion=canvas_sel.bbox("all"))
            
            # Pokaż ile zaznaczono
            count = sum(1 for v in check_vars.values() if v.get())
            count_label.config(text=f"Zaznaczono: {count} / {len(self.projects)} projektów")
        
        # ===== DOLNA BELKA — przyciski =====
        bottom = tk.Frame(sel, pady=8)
        bottom.pack(fill=tk.X, padx=10)
        
        # Lewa strona — zaznacz/odznacz + licznik
        left_btns = tk.Frame(bottom)
        left_btns.pack(side=tk.LEFT)
        
        tk.Button(left_btns, text="✅ Zaznacz widoczne", font=("Arial", 9),
                  command=lambda: [v.set(True) for pid, v in check_vars.items() if row_widgets[pid].winfo_ismapped()] or update_count()
        ).pack(side=tk.LEFT, padx=3)
        
        tk.Button(left_btns, text="❌ Odznacz widoczne", font=("Arial", 9),
                  command=lambda: [v.set(False) for pid, v in check_vars.items() if row_widgets[pid].winfo_ismapped() and not pin_vars[pid].get()] or update_count()
        ).pack(side=tk.LEFT, padx=3)
        
        count_label = tk.Label(bottom, text="", font=("Arial", 9, "bold"), fg="#2c3e50")
        count_label.pack(side=tk.LEFT, padx=15)
        
        def update_count():
            count = sum(1 for v in check_vars.values() if v.get())
            count_label.config(text=f"Zaznaczono: {count} / {len(self.projects)} projektów")
        
        # Prawa strona — Generuj
        def on_ok():
            selected = [pid for pid, var in check_vars.items() if var.get()]
            # Zapamiętaj przypięte
            self._mp_pinned_projects = {pid for pid, var in pin_vars.items() if var.get()}
            sel.destroy()
            if selected:
                self._create_multi_project_chart_window(selected)
            else:
                messagebox.showwarning("Brak wyboru", "Nie wybrano żadnych projektów.", parent=parent)
        
        tk.Button(bottom, text="📊 Generuj wykres", command=on_ok,
                  bg=self.COLOR_GREEN, fg="white", font=("Arial", 11, "bold"),
                  padx=20, pady=5).pack(side=tk.RIGHT, padx=5)
        
        # Keyboard shortcuts
        sel.bind('<Control-Delete>', clear_filters)
        sel.bind('<Control-Shift-A>', show_all_projects)
        
        # Inicjalizuj widok
        update_count()
    
    def _create_multi_project_chart_window(self, project_ids, preserve_view=False):
        """Rysuje multi-project Gantt w osobnym oknie.
        
        Args:
            project_ids: lista project_id do wyświetlenia
            preserve_view: zachowaj widok po odświeżeniu
        """
        from datetime import datetime, timedelta
        import matplotlib.dates as mdates
        from matplotlib.lines import Line2D
        
        # ===== Zbierz dane ze wszystkich projektów =====
        # Pobierz kolory etapów z STAGE_DEFINITIONS
        stage_colors = {}
        try:
            sample_db = self.get_project_db_path(project_ids[0])
            con = rmm._open_rm_connection(sample_db)
            cursor = con.execute("SELECT code, display_name, color, is_milestone FROM stage_definitions")
            stage_defs = {}
            for row in cursor.fetchall():
                stage_defs[row['code']] = {
                    'display_name': row['display_name'],
                    'color': row['color'] or '#95a5a6',
                    'is_milestone': bool(row['is_milestone'])
                }
            con.close()
        except Exception:
            stage_defs = {}
        
        # Inicjalizuj filtry etapów (zachowaj istniejące gdy preserve_view)
        if not hasattr(self, '_mp_stage_filters') or not preserve_view:
            self._mp_stage_filters = {}
        # Inicjalizuj filtry typów pasków (globalne)
        if not hasattr(self, '_mp_type_filters') or not preserve_view:
            self._mp_type_filters = {'Szablon': True, 'Rzeczywiste': True, 'Prognoza': True}
        # Inicjalizuj filtry typów per projekt: {pid: {'Szablon': True, ...}}
        if not hasattr(self, '_mp_proj_type_filters') or not preserve_view:
            self._mp_proj_type_filters = {}
        # ON/OFF nadpisania per-projekt (True = filtr projektu niezależny od globalnego)
        if not hasattr(self, '_mp_proj_filter_override') or not preserve_view:
            self._mp_proj_filter_override = {}
        # Filtr konstruktora (employee_id, None = wszyscy)
        if not hasattr(self, '_mp_employee_filter') or not preserve_view:
            self._mp_employee_filter = None
        # Wybrany (zaznaczony/locked) projekt w multi-Gantt
        if not hasattr(self, '_mp_selected_pid') or not preserve_view:
            self._mp_selected_pid = None
        
        # Przeładuj moduł rm_manager jeśli brak nowej funkcji (hotfix dla live session)
        if not hasattr(rmm, 'get_project_staff'):
            import importlib
            importlib.reload(rmm)
        
        # Zbierz wszystkich pracowników (konstruktorów) z wszystkich projektów
        all_employees = {}  # {employee_id: employee_name}
        project_employees = {}  # {pid: set(employee_ids)}
        
        for pid in project_ids:
            try:
                project_db = self.get_project_db_path(pid)
                staff = rmm.get_project_staff(project_db, self.rm_master_db_path, pid)
                emp_ids = set()
                for s in staff:
                    all_employees[s['employee_id']] = s['employee_name']
                    emp_ids.add(s['employee_id'])
                project_employees[pid] = emp_ids
            except Exception as e:
                project_employees[pid] = set()
        
        # Zbierz dane z każdego projektu
        all_gantt_data = []  # lista słowników z danymi pasków
        all_dates = []
        y_labels = []
        y_pos = 0
        project_separators = []  # pozycje Y linii oddzielających projekty
        encountered_stages = set()  # etapy obecne w danych
        
        for pid in project_ids:
            pname = self.project_names.get(pid, f"Projekt {pid}")
            
            # Filtr konstruktora - pomiń projekt jeśli nie ma wybranego konstruktora
            if self._mp_employee_filter is not None:
                if pid not in project_employees or self._mp_employee_filter not in project_employees[pid]:
                    continue
            
            # Domyślne per-projekt filtry typów
            if pid not in self._mp_proj_type_filters:
                self._mp_proj_type_filters[pid] = {'Szablon': True, 'Rzeczywiste': True, 'Prognoza': True}
            
            try:
                project_db = self.get_project_db_path(pid)
                timeline = rmm.get_stage_timeline(project_db, pid)
            except Exception as e:
                print(f"⚠️ Błąd wczytania projektu {pid}: {e}")
                continue
            
            if not timeline:
                continue
            
            # Sortuj etapy wg ustalonej kolejności
            timeline.sort(key=lambda s: STAGE_ORDER.get(s['stage_code'], 999))
            
            # Dodaj nagłówek projektu jako separator
            project_start_y = y_pos
            
            for stage in timeline:
                stage_code = stage['stage_code']
                sd = stage_defs.get(stage_code, {})
                stage_name = sd.get('display_name', stage_code)
                stage_color = sd.get('color', '#95a5a6')
                is_ms = sd.get('is_milestone', False)
                
                template_start = stage.get('template_start')
                template_end = stage.get('template_end')
                
                has_template = template_start and template_end
                has_forecast = stage.get('forecast_start') and stage.get('forecast_end')
                has_actual = any(p.get('started_at') for p in stage.get('actual_periods', []))
                
                if not has_template and not has_forecast and not has_actual:
                    continue
                
                encountered_stages.add(stage_code)
                
                # Domyślnie nowe etapy są włączone
                if stage_code not in self._mp_stage_filters:
                    self._mp_stage_filters[stage_code] = True
                
                # Pomiń odfiltrowane etapy
                if not self._mp_stage_filters.get(stage_code, True):
                    continue
                
                # Label: "nazwa_projektu | etap"
                row_label = f"{pname} | {stage_name}"
                y_labels.append(row_label)
                
                # --- SZABLON ---
                proj_tf = self._mp_proj_type_filters.get(pid, {})
                override = self._mp_proj_filter_override.get(pid, False)
                if has_template:
                    show = proj_tf.get('Szablon', True) if override else (
                        self._mp_type_filters.get('Szablon', True) and proj_tf.get('Szablon', True))
                    if show:
                        tpl_start = datetime.strptime(template_start[:10], '%Y-%m-%d')
                        tpl_end = datetime.strptime(template_end[:10], '%Y-%m-%d')
                        if is_ms:
                            tpl_end = tpl_start + timedelta(days=1)
                        else:
                            tpl_start, tpl_end = self._ensure_min_1day_dt(tpl_start, tpl_end)
                        all_gantt_data.append({
                            'task': row_label,
                            'y_pos': y_pos,
                            'start': tpl_start,
                            'end': tpl_end,
                            'type': 'Szablon',
                            'color': stage_color,
                            'alpha': 0.35,
                            'height': 0.8,
                            'y_offset': -0.1,
                            'project_id': pid,
                            'stage_code': stage_code,
                        })
                        all_dates.extend([tpl_start, tpl_end])
                
                # --- RZECZYWISTE ---
                if override:
                    show_rz = proj_tf.get('Rzeczywiste', True)
                else:
                    show_rz = self._mp_type_filters.get('Rzeczywiste', True) and proj_tf.get('Rzeczywiste', True)
                if show_rz:
                    for period in stage.get('actual_periods', []):
                        if period.get('started_at'):
                            start_date = datetime.strptime(period['started_at'][:10], '%Y-%m-%d')
                            end_date = datetime.strptime(
                                (period.get('ended_at') or datetime.now().strftime('%Y-%m-%d'))[:10],
                                '%Y-%m-%d'
                            )
                            if is_ms:
                                end_date = start_date + timedelta(days=1)
                            else:
                                start_date, end_date = self._ensure_min_1day_dt(start_date, end_date)
                            all_gantt_data.append({
                                'task': row_label,
                                'y_pos': y_pos,
                                'start': start_date,
                                'end': end_date,
                                'type': 'Rzeczywiste',
                                'color': stage_color,
                                'alpha': 0.9,
                                'height': 0.5,
                                'y_offset': 0.05,
                                'project_id': pid,
                                'stage_code': stage_code,
                            })
                            all_dates.extend([start_date, end_date])
                
                # --- PROGNOZA ---
                if has_forecast:
                    show_pr = proj_tf.get('Prognoza', True) if override else (
                        self._mp_type_filters.get('Prognoza', True) and proj_tf.get('Prognoza', True))
                    if show_pr:
                        fc_start = datetime.strptime(stage['forecast_start'][:10], '%Y-%m-%d')
                        fc_end = datetime.strptime(stage['forecast_end'][:10], '%Y-%m-%d')
                        if is_ms:
                            fc_end = fc_start + timedelta(days=1)
                        else:
                            fc_start, fc_end = self._ensure_min_1day_dt(fc_start, fc_end)
                        all_gantt_data.append({
                            'task': row_label,
                            'y_pos': y_pos,
                            'start': fc_start,
                            'end': fc_end,
                            'type': 'Prognoza',
                            'color': stage_color,
                            'alpha': 0.55,
                            'height': 0.25,
                            'y_offset': 0.18,
                            'project_id': pid,
                            'stage_code': stage_code,
                        })
                        all_dates.extend([fc_start, fc_end])
                
                y_pos += 1
            
            # Linia separatora między projektami
            if y_pos > project_start_y:
                project_separators.append({
                    'y': y_pos - 0.5,
                    'label': pname,
                    'y_center': (project_start_y + y_pos - 1) / 2,
                    'pid': pid,
                })
        
        if not all_gantt_data:
            if hasattr(self, '_mp_chart_window') and self._mp_chart_window:
                try:
                    if self._mp_chart_window.winfo_exists():
                        self._mp_status.config(text="⚠️ Brak danych po filtracji", fg=self.COLOR_ORANGE)
                        return
                except Exception:
                    pass
            messagebox.showwarning("Brak danych", "Brak danych do wykresu dla wybranych projektów.")
            return
        
        # ===== Okno wykresu =====
        # Zachowaj widok ze starego okna?
        saved_xlim = None
        saved_ylim = None
        if preserve_view and hasattr(self, '_mp_chart_meta') and self._mp_chart_meta:
            try:
                old_ax = self._mp_chart_meta.get('ax')
                if old_ax:
                    saved_xlim = tuple(old_ax.get_xlim())
                    saved_ylim = tuple(old_ax.get_ylim())
            except Exception:
                pass
        
        # Próba reużycia istniejącego canvas/figure (bez migania)
        reuse_canvas = False
        if preserve_view and hasattr(self, '_mp_chart_meta') and self._mp_chart_meta:
            try:
                _old_canvas = self._mp_chart_meta.get('canvas')
                _old_fig = self._mp_chart_meta.get('fig')
                if _old_canvas and _old_fig and _old_canvas.get_tk_widget().winfo_exists():
                    reuse_canvas = True
            except Exception:
                reuse_canvas = False
        
        # Reuse istniejącego okna jeśli jest otwarte
        reuse = False
        if hasattr(self, '_mp_chart_window') and self._mp_chart_window:
            try:
                if self._mp_chart_window.winfo_exists():
                    if not reuse_canvas:
                        # Zamknij starą figurę matplotlib (memory leak prevention)
                        if hasattr(self, '_mp_chart_meta') and self._mp_chart_meta:
                            try:
                                import matplotlib.pyplot as plt
                                old_fig = self._mp_chart_meta.get('fig')
                                if old_fig:
                                    plt.close(old_fig)
                            except Exception:
                                pass
                        # Wyczyść chart_frame tylko gdy nie reużywamy canvas
                        for child in self._mp_chart_frame.winfo_children():
                            child.destroy()
                    reuse = True
            except Exception:
                pass
        
        if not reuse:
            self._mp_chart_window = tk.Toplevel(self.root)
            self._mp_chart_window.title("📊 Multi-projekt Gantt")
            self._mp_chart_window.geometry("1400x900")
            self._mp_chart_window.minsize(800, 500)
            
            # Toolbar na górze okna
            top_bar = tk.Frame(self._mp_chart_window, bg=self.COLOR_TOPBAR, pady=5)
            top_bar.pack(fill=tk.X)
            
            tk.Button(top_bar, text="🔄 Odśwież", 
                      command=lambda: self._create_multi_project_chart_window(project_ids, preserve_view=True),
                      bg=self.COLOR_BLUE, fg="white", font=("Arial", 10, "bold"),
                      padx=10, pady=3).pack(side=tk.LEFT, padx=5)
            
            tk.Button(top_bar, text="💾 Zapisz PNG",
                      command=lambda: self._save_mp_chart(),
                      bg=self.COLOR_ORANGE, fg="white", font=("Arial", 10),
                      padx=10, pady=3).pack(side=tk.LEFT, padx=5)
            
            tk.Button(top_bar, text="🏠 Reset widoku",
                      command=lambda: self._mp_reset_view(),
                      bg="#7f8c8d", fg="white", font=("Arial", 10),
                      padx=10, pady=3).pack(side=tk.LEFT, padx=5)
            
            tk.Button(top_bar, text="📋 Projekty",
                      command=lambda: self._mp_select_projects_dialog(),
                      bg="#8e44ad", fg="white", font=("Arial", 10, "bold"),
                      padx=10, pady=3).pack(side=tk.LEFT, padx=5)
            
            # Legenda nawigacji
            tk.Label(top_bar,
                     text="🖱 Scroll: góra/dół  |  Shift+Scroll: lewo/prawo  |  Ctrl+Scroll: zoom czasu (X)  |  Ctrl+Shift+Scroll: zoom pionu (Y)  |  Shift+LMB: pan  |  🏠 Home: reset",
                     font=("Arial", 9), fg="black", bg=self.COLOR_TOPBAR
            ).pack(side=tk.RIGHT, padx=10)
            
            # Status bar (na dole)
            self._mp_status = tk.Label(self._mp_chart_window, text="", 
                                        font=("Arial", 9), fg="gray", anchor="w")
            self._mp_status.pack(side=tk.BOTTOM, fill=tk.X, padx=5)
            
            # ===== Panel filtrów =====
            self._mp_filter_frame = tk.Frame(self._mp_chart_window, bg="#f8f8f8", relief=tk.GROOVE, bd=1)
            self._mp_filter_frame.pack(fill=tk.X, padx=5, pady=(2, 0))
            
            self._mp_chart_frame = tk.Frame(self._mp_chart_window)
            self._mp_chart_frame.pack(fill=tk.BOTH, expand=True)
        
        # ===== Odśwież panel filtrów (pomiń gdy reuse_canvas — widgety OK) =====
        if not reuse_canvas:
            for child in self._mp_filter_frame.winfo_children():
                child.destroy()
        
        # Callback odświeżania po zmianie filtra
        def _on_filter_change():
            self._create_multi_project_chart_window(project_ids, preserve_view=True)
        
        if not reuse_canvas:
            # Rząd 1: Typy pasków (Szablon / Rzeczywiste / Prognoza) + przycisk Przerysuj
            type_row = tk.Frame(self._mp_filter_frame, bg="#f8f8f8")
            type_row.pack(fill=tk.X, padx=5, pady=(3, 0))
            
            tk.Button(type_row, text="🔄 Przerysuj", command=_on_filter_change,
                      bg=self.COLOR_GREEN, fg="white", font=("Arial", 9, "bold"),
                      padx=8, pady=1, relief=tk.RAISED, cursor='hand2'
            ).pack(side=tk.LEFT, padx=(0, 10))
            
            tk.Label(type_row, text="Typ:", font=("Arial", 9, "bold"), bg="#f8f8f8"
                    ).pack(side=tk.LEFT, padx=(0, 5))
            
            type_colors = {'Szablon': '#95a5a6', 'Rzeczywiste': '#27ae60', 'Prognoza': '#3498db'}
            self._mp_type_vars = {}
            for ttype, tcolor in type_colors.items():
                var = tk.BooleanVar(value=self._mp_type_filters.get(ttype, True))
                self._mp_type_vars[ttype] = var
                
                def _make_type_cb(tt, v):
                    def cb():
                        self._mp_type_filters[tt] = v.get()
                        _on_filter_change()
                    return cb
                
                cb = tk.Checkbutton(type_row, text=ttype, variable=var,
                                   command=_make_type_cb(ttype, var),
                                   font=("Arial", 9), bg="#f8f8f8",
                                   fg=tcolor, selectcolor="white",
                                   activebackground="#f8f8f8")
                cb.pack(side=tk.LEFT, padx=4)
            
            # Dodaj separator pionowy
            ttk.Separator(type_row, orient='vertical').pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=2)
            
            # Konstruktor w tym samym wierszu
            tk.Label(type_row, text="Konstruktor:", font=("Arial", 9, "bold"), bg="#f8f8f8"
                    ).pack(side=tk.LEFT, padx=(0, 5))
            
            # Lista konstruktorów: "Wszyscy" + lista pracowników
            employee_list = ["Wszyscy"] + [all_employees[eid] for eid in sorted(all_employees.keys(), key=lambda e: all_employees[e])]
            employee_ids_map = {all_employees[eid]: eid for eid in all_employees}  # name -> id
            
            # Znajdź aktualny wybór
            current_selection = "Wszyscy"
            if self._mp_employee_filter is not None and self._mp_employee_filter in all_employees:
                current_selection = all_employees[self._mp_employee_filter]
            
            employee_var = tk.StringVar(value=current_selection)
            employee_combo = ttk.Combobox(type_row, textvariable=employee_var,
                                         values=employee_list, state='readonly',
                                         width=20, font=("Arial", 9))
            employee_combo.pack(side=tk.LEFT, padx=5)
            
            def _on_employee_change(event=None):
                selected = employee_var.get()
                if selected == "Wszyscy":
                    self._mp_employee_filter = None
                else:
                    self._mp_employee_filter = employee_ids_map.get(selected)
                _on_filter_change()
            
            employee_combo.bind("<<ComboboxSelected>>", _on_employee_change)
            
            # Informacja o liczbie projektów po filtrowaniu
            if self._mp_employee_filter is not None:
                filtered_count = sum(1 for pid in project_ids 
                                   if pid in project_employees and self._mp_employee_filter in project_employees[pid])
                tk.Label(type_row, 
                        text=f"({filtered_count}/{len(project_ids)} projektów)",
                        font=("Arial", 9), fg=self.COLOR_BLUE, bg="#f8f8f8"
                ).pack(side=tk.LEFT, padx=5)
            
            # Separator poziomy (przed etapami)
            ttk.Separator(self._mp_filter_frame, orient='horizontal').pack(fill=tk.X, padx=5, pady=2)
            
            # Rząd 2: Etapy (z kolorami)
            stage_row = tk.Frame(self._mp_filter_frame, bg="#f8f8f8")
            stage_row.pack(fill=tk.X, padx=5, pady=(0, 3))
            
            tk.Label(stage_row, text="Etapy:", font=("Arial", 9, "bold"), bg="#f8f8f8"
                    ).pack(side=tk.LEFT, padx=(0, 5))
            
            # Zaznacz / Odznacz wszystko
            def _select_all_stages():
                for sc in self._mp_stage_filters:
                    self._mp_stage_filters[sc] = True
                for v in self._mp_stage_vars.values():
                    v.set(True)
                _on_filter_change()
            
            def _deselect_all_stages():
                for sc in self._mp_stage_filters:
                    self._mp_stage_filters[sc] = False
                for v in self._mp_stage_vars.values():
                    v.set(False)
                _on_filter_change()
            
            tk.Button(stage_row, text="✅", command=_select_all_stages,
                      font=("Arial", 8), padx=2, pady=0, relief=tk.FLAT,
                      bg="#f8f8f8").pack(side=tk.LEFT)
            tk.Button(stage_row, text="❌", command=_deselect_all_stages,
                      font=("Arial", 8), padx=2, pady=0, relief=tk.FLAT,
                      bg="#f8f8f8").pack(side=tk.LEFT, padx=(0, 5))
            
            self._mp_stage_vars = {}
            
            # Posortuj etapy w kolejności z STAGE_DEFINITIONS
            stage_order = list(stage_defs.keys())
            sorted_stages = sorted(encountered_stages, key=lambda sc: stage_order.index(sc) if sc in stage_order else 999)
            
            for sc in sorted_stages:
                sd = stage_defs.get(sc, {})
                sname = sd.get('display_name', sc)
                scolor = sd.get('color', '#95a5a6')
                is_ms = sd.get('is_milestone', False)
                
                var = tk.BooleanVar(value=self._mp_stage_filters.get(sc, True))
                self._mp_stage_vars[sc] = var
                
                def _make_stage_cb(stage_code, v):
                    def cb():
                        self._mp_stage_filters[stage_code] = v.get()
                        _on_filter_change()
                    return cb
                
                # Kontener z kolorowym kwadratem + checkbutton
                frame = tk.Frame(stage_row, bg="#f8f8f8")
                frame.pack(side=tk.LEFT, padx=2)
                
                # Kolorowy kwadrat
                color_lbl = tk.Label(frame, text="  ", bg=scolor, width=2,
                                     relief=tk.SOLID, bd=1)
                color_lbl.pack(side=tk.LEFT, padx=(0, 1))
                
                label_text = f"{'[M] ' if is_ms else ''}{sname}"
                cb = tk.Checkbutton(frame, text=label_text, variable=var,
                                   command=_make_stage_cb(sc, var),
                                   font=("Arial", 8), bg="#f8f8f8",
                                   selectcolor="white", activebackground="#f8f8f8")
                cb.pack(side=tk.LEFT)
        
        # ===== Rysuj wykres =====
        if reuse_canvas:
            fig = self._mp_chart_meta['fig']
            fig.clear()
            ax = fig.add_subplot(111)
            mp_canvas = self._mp_chart_meta['canvas']
        else:
            fig = Figure(figsize=(14, max(6, len(y_labels) * 0.4)), dpi=100)
            ax = fig.add_subplot(111)
        
        # Rysuj paski
        for item in all_gantt_data:
            if item['start'] is None:
                continue
            duration = (item['end'] - item['start']).days
            if duration < 1:
                duration = 1
            
            # Szablon - obramowanie przerywane, Rzeczywiste - pełne, Prognoza - cienkie
            linestyle = '--' if item['type'] == 'Szablon' else '-'
            linewidth = 0.8 if item['type'] == 'Szablon' else (0.5 if item['type'] == 'Prognoza' else 1.0)
            
            rect = patches.Rectangle(
                (mdates.date2num(item['start']), item['y_pos'] + item['y_offset']),
                duration,
                item['height'],
                facecolor=item['color'],
                alpha=item['alpha'],
                edgecolor='black',
                linewidth=linewidth,
                linestyle=linestyle,
            )
            ax.add_patch(rect)
        
        # Dziś - linia pioniowa
        today_num = mdates.date2num(datetime.now())
        ax.axvline(x=today_num, color='red', linewidth=1.5, linestyle='--', alpha=0.7, zorder=5)
        ax.text(today_num, -0.3, ' DZIŚ', color='red', fontsize=8, 
                fontweight='bold', va='bottom', ha='left', zorder=5)
        
        # Separatory między projektami
        for sep in project_separators[:-1]:  # Nie rysuj po ostatnim
            ax.axhline(y=sep['y'], color='#333333', linewidth=1.5, linestyle='-', alpha=0.6, zorder=3)
        
        # Znaki wodne z nazwą projektu na tle każdej sekcji
        for sep in project_separators:
            watermark_text = f"{sep['pid']}  {sep['label']}"
            ax.text(
                0.5, sep['y_center'],
                watermark_text,
                transform=ax.get_yaxis_transform(),
                fontsize=24,
                fontweight='bold',
                color='#000000',
                alpha=0.12,
                ha='center',
                va='center',
                zorder=0,
                rotation=0,
            )
        
        # Mapuj y_pos -> project_id (do identyfikacji kliknięcia)
        y_to_pid = {}
        for item in all_gantt_data:
            y_to_pid[item['y_pos']] = item['project_id']
        
        # Oś Y
        ax.set_ylim(-0.5, len(y_labels) - 0.5)
        ax.set_yticks(range(len(y_labels)))
        # Etykiety Y - pokaż tylko nazwę etapu (bez nazwy projektu)
        short_labels = [lbl.split(' | ')[-1] if ' | ' in lbl else lbl for lbl in y_labels]
        ax.set_yticklabels(short_labels, fontsize=8)
        ax.invert_yaxis()  # Pierwszy etap na górze (przed saved restore)
        
        # Wizualizacja wybranego/locked projektu — czerwone + bold etykiety
        locked_pid = self._mp_selected_pid
        if locked_pid is not None:
            for i, lbl in enumerate(y_labels):
                pid_for_row = y_to_pid.get(i)
                if pid_for_row == locked_pid:
                    ax.get_yticklabels()[i].set_color('#e74c3c')
                    ax.get_yticklabels()[i].set_fontweight('bold')
                    ax.get_yticklabels()[i].set_fontsize(9)
        
        # Oś X
        if all_dates:
            min_date = min(all_dates)
            max_date = max(all_dates)
            ax.set_xlim(mdates.date2num(min_date - timedelta(days=5)),
                        mdates.date2num(max_date + timedelta(days=30)))
        
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('W%W\n%d/%m'))
        ax.xaxis.set_minor_locator(mdates.DayLocator())
        ax.tick_params(axis='x', which='major', labelsize=8, pad=12)
        ax.tick_params(axis='x', which='minor', labelsize=6, labelcolor='#888888')
        fig.autofmt_xdate(rotation=0, ha='center')
        
        # Weekendy
        xlim = ax.get_xlim()
        x_start = mdates.num2date(xlim[0]).replace(tzinfo=None)
        x_end = mdates.num2date(xlim[1]).replace(tzinfo=None)
        current = x_start.replace(hour=0, minute=0, second=0, microsecond=0)
        while current <= x_end:
            if current.weekday() in (5, 6):
                ax.axvspan(mdates.date2num(current), mdates.date2num(current + timedelta(days=1)),
                           facecolor='#e0e0e0', alpha=0.4, zorder=0)
            current += timedelta(days=1)
        
        # Siatka
        ax.grid(True, which='major', alpha=0.4, linewidth=0.8)
        ax.grid(True, which='minor', alpha=0.15, linewidth=0.3)
        ax.set_xlabel('Data', fontweight='bold')
        ax.set_title(f'Multi-projekt Gantt ({len(project_ids)} projektów)', fontweight='bold', pad=15)
        
        # Legenda — typy pasków + kolory etapów
        legend_elements = [
            patches.Patch(facecolor='gray', alpha=0.35, edgecolor='black', 
                         linestyle='--', label='Szablon'),
            patches.Patch(facecolor='gray', alpha=0.9, edgecolor='black', label='Rzeczywiste'),
            patches.Patch(facecolor='gray', alpha=0.55, edgecolor='black', label='Prognoza'),
        ]
        # Kolory etapów
        shown_stages = set()
        for item in all_gantt_data:
            sc = item['stage_code']
            if sc not in shown_stages:
                shown_stages.add(sc)
                sd = stage_defs.get(sc, {})
                legend_elements.append(
                    patches.Patch(facecolor=sd.get('color', '#95a5a6'), alpha=0.8,
                                  edgecolor='black', linewidth=0.5,
                                  label=sd.get('display_name', sc))
                )
        
        ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, -0.06),
                  ncol=min(8, len(legend_elements)), fontsize=7, frameon=True, fancybox=True)
        
        fig.subplots_adjust(left=0.08, right=0.99, top=0.95, bottom=0.12)
        
        if reuse_canvas:
            # Reuse: odśwież figurę i przywróć widok
            if saved_xlim:
                ax.set_xlim(saved_xlim)
            if saved_ylim:
                ax.set_ylim(saved_ylim)
            mp_canvas.draw()
            
            # Zaktualizuj metadane (nowe ax, dane)
            self._mp_chart_meta.update({
                'ax': ax,
                'y_labels': y_labels,
                'gantt_data': all_gantt_data,
                'y_positions': {lbl: idx for idx, lbl in enumerate(y_labels)},
                'stage_defs': stage_defs,
                'all_dates': all_dates,
                'y_to_pid': y_to_pid,
                'project_separators': project_separators,
            })
        else:
            # ===== Canvas i statyczny prawy panel =====
            # Prawy panel — info o wybranym projekcie + lock + filtr per-projekt
            self._mp_right_panel = tk.Frame(self._mp_chart_frame, bg="#f0f0f0", width=170,
                                             relief=tk.GROOVE, bd=1)
            self._mp_right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 2), pady=2)
            self._mp_right_panel.pack_propagate(False)
            self._mp_build_right_panel(project_ids)
            
            mp_canvas = FigureCanvasTkAgg(fig, self._mp_chart_frame)
            mp_canvas.draw()
            mp_canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # Dopasuj marginesy przy resize okna
            def _on_mp_canvas_configure(event):
                try:
                    w = event.width
                    left_frac = max(0.05, min(0.10, 100.0 / max(w, 1)))
                    fig.subplots_adjust(left=left_frac, right=0.99, top=0.95, bottom=0.12)
                    mp_canvas.draw_idle()
                except Exception:
                    pass
            
            # WAŻNE: add='+' żeby NIE nadpisać wewnętrznego handlera matplotlib
            mp_canvas.get_tk_widget().bind('<Configure>', _on_mp_canvas_configure, add='+')
            
            # Toolbar matplotlib usunięty — nawigacja przez custom handlery (scroll/pan/zoom)
            # Home = reset_view, Save = top bar "Zapisz PNG"
            
            # Przywróć zapisany widok
            if saved_xlim:
                ax.set_xlim(saved_xlim)
            if saved_ylim:
                ax.set_ylim(saved_ylim)
            if saved_xlim or saved_ylim:
                mp_canvas.draw_idle()
            
            # ===== Metadane (do edycji pasków) =====
            self._mp_chart_meta = {
                'ax': ax,
                'fig': fig,
                'canvas': mp_canvas,
                'toolbar': None,
                'y_labels': y_labels,
                'gantt_data': all_gantt_data,
                'y_positions': {lbl: idx for idx, lbl in enumerate(y_labels)},
                'stage_defs': stage_defs,
                'project_ids': project_ids,
                'all_dates': all_dates,
                'y_to_pid': y_to_pid,
                'project_separators': project_separators,
            }
            
            self._mp_drag_state = {
                'active': False, 'stage_code': None, 'project_id': None,
                'edge': None, 'original_date': None, 'bar_item': None, 'preview_line': None,
                'drag_anchor_x': None,
            }
            self._mp_pan_state = {'active': False}
            
            # Event handlers
            mp_canvas.mpl_connect('button_press_event', self._mp_on_press)
            mp_canvas.mpl_connect('button_release_event', self._mp_on_release)
            mp_canvas.mpl_connect('motion_notify_event', self._mp_on_motion)
            mp_canvas.mpl_connect('button_press_event', self._mp_on_dblclick)
            
            # Scroll — Windows: <MouseWheel> z modyfikatorami (Button-4/5 to Linux)
            canvas_widget = mp_canvas.get_tk_widget()
            canvas_widget.bind('<Enter>', lambda e: canvas_widget.focus_set())
            canvas_widget.bind('<Control-Shift-MouseWheel>', lambda e: (self._mp_scroll_action('zoom_y', 'up' if e.delta > 0 else 'down', e), 'break')[-1])
            canvas_widget.bind('<Control-MouseWheel>', lambda e: (self._mp_scroll_action('zoom_x', 'up' if e.delta > 0 else 'down', e), 'break')[-1])
            canvas_widget.bind('<Shift-MouseWheel>', lambda e: (self._mp_scroll_action('pan_x', 'up' if e.delta > 0 else 'down'), 'break')[-1])
            canvas_widget.bind('<MouseWheel>', lambda e: (self._mp_scroll_action('pan_y', 'up' if e.delta > 0 else 'down'), 'break')[-1])
        
        self._mp_status.config(text=f"✅ Wykres: {len(project_ids)} projektów, {len(all_gantt_data)} pasków")
    
    # ---- Multi-project: nawigacja ----
    
    def _mp_reset_view(self):
        """Reset widoku multi-project chart"""
        if not hasattr(self, '_mp_chart_meta') or not self._mp_chart_meta:
            return
        try:
            ax = self._mp_chart_meta['ax']
            y_labels = self._mp_chart_meta['y_labels']
            all_dates = self._mp_chart_meta['all_dates']
            import matplotlib.dates as mdates
            if all_dates:
                ax.set_xlim(mdates.date2num(min(all_dates) - timedelta(days=5)),
                            mdates.date2num(max(all_dates) + timedelta(days=30)))
            if y_labels:
                ax.set_ylim(-0.5, len(y_labels) - 0.5)
                ax.invert_yaxis()
            self._mp_chart_meta['canvas'].draw_idle()
        except Exception as e:
            print(f"⚠️ MP reset view: {e}")
    
    def _mp_scroll_action(self, action, direction, tk_event=None):
        """Wykonaj akcję scrolla — wywoływana z dedykowanych Tk bindingów.
        Identyczna logika jak _on_chart_scroll w Wykresie wbudowanym:
        - pan_y: Scroll → pan góra/dół (Y)
        - pan_x: Shift+Scroll → pan lewo/prawo (X)
        - zoom_x: Ctrl+Scroll → zoom czasu (X)
        - zoom_y: Ctrl+Shift+Scroll → zoom pionu (Y)
        """
        if not hasattr(self, '_mp_chart_meta') or not self._mp_chart_meta:
            return
        ax = self._mp_chart_meta['ax']
        canvas = self._mp_chart_meta['canvas']
        
        scale_factor = 0.85 if direction == 'up' else 1.15
        
        if action == 'zoom_y':
            # Ctrl+Shift+scroll: zoom pionu (Y) - centrowany na środku widoku
            ylim = ax.get_ylim()
            y_center = (ylim[0] + ylim[1]) / 2
            # Spróbuj centrować na kursorze
            if tk_event:
                try:
                    widget = canvas.get_tk_widget()
                    y_display = widget.winfo_height() - tk_event.y
                    _, y_center = ax.transData.inverted().transform((0, y_display))
                except Exception:
                    pass
            new_height = (ylim[1] - ylim[0]) * scale_factor
            ax.set_ylim(y_center - new_height * (y_center - ylim[0]) / (ylim[1] - ylim[0]),
                        y_center + new_height * (ylim[1] - y_center) / (ylim[1] - ylim[0]))
        
        elif action == 'zoom_x':
            # Ctrl+scroll: zoom osi czasu (X) - centrowany na kursorze
            xlim = ax.get_xlim()
            x_center = (xlim[0] + xlim[1]) / 2
            if tk_event:
                try:
                    widget = canvas.get_tk_widget()
                    y_display = widget.winfo_height() - tk_event.y
                    x_center, _ = ax.transData.inverted().transform((tk_event.x, y_display))
                except Exception:
                    pass
            new_width = (xlim[1] - xlim[0]) * scale_factor
            ax.set_xlim(x_center - new_width * (x_center - xlim[0]) / (xlim[1] - xlim[0]),
                        x_center + new_width * (xlim[1] - x_center) / (xlim[1] - xlim[0]))
        
        elif action == 'pan_x':
            # Shift+scroll: pan lewo/prawo
            xlim = ax.get_xlim()
            x_range = xlim[1] - xlim[0]
            shift = x_range * 0.1 * (1 if direction == 'down' else -1)
            ax.set_xlim(xlim[0] + shift, xlim[1] + shift)
        
        else:  # pan_y
            # Scroll: pan góra/dół
            ylim = ax.get_ylim()
            y_range = ylim[1] - ylim[0]
            shift = y_range * 0.1 * (1 if direction == 'up' else -1)
            ax.set_ylim(ylim[0] + shift, ylim[1] + shift)
        
        canvas.draw_idle()
    
    # ---- Multi-project: edycja pasków ----
    
    def _mp_find_bar(self, x_data, y_data, tolerance_days=3):
        """Znajdź pasek szablonu pod kursorem w multi-project chart"""
        if not hasattr(self, '_mp_chart_meta'):
            return None, None, None, None
        
        import matplotlib.dates as mdates
        y_idx = round(y_data)
        labels = self._mp_chart_meta['y_labels']
        if y_idx < 0 or y_idx >= len(labels):
            return None, None, None, None
        
        row_label = labels[y_idx]
        x_datetime = mdates.num2date(x_data).replace(tzinfo=None)
        stage_defs = self._mp_chart_meta.get('stage_defs', {})
        
        for item in self._mp_chart_meta['gantt_data']:
            if item['task'] != row_label or item['type'] not in ('Szablon', 'Milestone'):
                continue
            if item['start'] is None:
                continue
            
            # Milestone (type='Milestone' lub is_milestone w stage_defs) → tylko move
            sc = item.get('stage_code', '')
            is_ms = item['type'] == 'Milestone' or stage_defs.get(sc, {}).get('is_milestone', False)
            
            if is_ms:
                if abs(x_datetime - item['start']) <= timedelta(days=tolerance_days):
                    return item['project_id'], item['stage_code'], 'move', item
                continue
            
            if item['start'] <= x_datetime <= item['end']:
                bar_dur = (item['end'] - item['start']).total_seconds() / 86400.0
                edge_tol = max(0.5, min(tolerance_days, bar_dur * 0.25))
                edge_tolerance = timedelta(days=edge_tol)
                if abs(x_datetime - item['start']) <= edge_tolerance:
                    return item['project_id'], item['stage_code'], 'start', item
                elif abs(x_datetime - item['end']) <= edge_tolerance:
                    return item['project_id'], item['stage_code'], 'end', item
                else:
                    return item['project_id'], item['stage_code'], None, item
        
        return None, None, None, None
    
    def _mp_find_any_bar(self, x_data, y_data, tolerance_days=3):
        """Znajdź dowolny pasek (Szablon/Milestone/Rzeczywiste/Prognoza) pod kursorem"""
        if not hasattr(self, '_mp_chart_meta'):
            return None, None, None
        
        import matplotlib.dates as mdates
        y_idx = round(y_data)
        labels = self._mp_chart_meta['y_labels']
        if y_idx < 0 or y_idx >= len(labels):
            return None, None, None
        
        row_label = labels[y_idx]
        x_datetime = mdates.num2date(x_data).replace(tzinfo=None)
        
        # Szukaj trafienia — zbierz wszystkie paski na tym wierszu
        # i zwróć najlepsze trafienie (priorytet: dokładne > tolerancja)
        best_hit = None
        best_dist = None
        
        for item in self._mp_chart_meta['gantt_data']:
            if item['task'] != row_label:
                continue
            if item['start'] is None:
                continue
            
            bar_start = item['start']
            bar_end = item['end']
            # Dodaj 1 dzień do end (pasek rysowany jest do końca dnia end)
            bar_end_ext = bar_end + timedelta(days=1)
            
            # Milestone/1-dniowe - tolerancja
            if item['type'] == 'Milestone' or (bar_end - bar_start).days <= 1:
                dist = abs((x_datetime - bar_start).total_seconds())
                tol = tolerance_days * 86400
                if dist <= tol:
                    if best_dist is None or dist < best_dist:
                        best_hit = (item['project_id'], item['stage_code'], item)
                        best_dist = dist
                continue
            
            # Normalny pasek — sprawdź czy kursor mieści się w zakresie
            if bar_start <= x_datetime <= bar_end_ext:
                # Oblicz odległość od środka (bliżej środka = lepsze trafienie)
                mid = bar_start + (bar_end_ext - bar_start) / 2
                dist = abs((x_datetime - mid).total_seconds())
                if best_dist is None or dist < best_dist:
                    best_hit = (item['project_id'], item['stage_code'], item)
                    best_dist = dist
        
        if best_hit:
            return best_hit
        return None, None, None
    
    def _mp_on_press(self, event):
        """Obsługa kliknięcia - rozpoczęcie drag, pan (Shift+LMB)"""
        if event.dblclick:
            return
        if event.inaxes is None or not hasattr(self, '_mp_chart_meta'):
            return
        
        # Shift + lewy przycisk => PAN (dostępny zawsze, bez locka)
        if event.button == 1 and event.key == 'shift':
            self._mp_pan_state = {
                'active': True,
                'start_px': event.x, 'start_py': event.y,
                'start_xlim': self._mp_chart_meta['ax'].get_xlim(),
                'start_ylim': self._mp_chart_meta['ax'].get_ylim(),
            }
            self._mp_chart_meta['canvas'].get_tk_widget().config(cursor='fleur')
            return
        
        if event.button != 1:
            return
        
        # Sprawdz lock
        if not self.have_lock or self._locked_project_id is None:
            self._mp_status.config(
                text="🔒 Dwuklik = lockuj projekt | Shift+mysz: przesuwanie | Ctrl+scroll: zoom",
                fg=self.COLOR_RED
            )
            return
        
        # Sprawdź uprawnienia
        if not self._has_permission('can_edit_dates'):
            self._mp_status.config(
                text=f"🚫 Brak uprawnień do edycji dat (rola: {self.current_user_role})",
                fg=self.COLOR_RED
            )
            return
        
        pid, stage_code, edge, bar_item = self._mp_find_bar(event.xdata, event.ydata)
        if not stage_code or not bar_item:
            return
        
        # Edycja tylko locked projektu
        if pid != self._locked_project_id:
            self._mp_status.config(text=f"ℹ️ Edycja tylko locked projektu", fg=self.COLOR_ORANGE)
            return
        
        if bar_item['type'] not in ('Szablon', 'Milestone'):
            self._mp_status.config(
                text=f"ℹ️ Można edytować tylko paski szablonu i milestone",
                fg=self.COLOR_BLUE
            )
            return
        
        # Milestone zawsze w trybie move (niezależnie od type)
        stage_defs = self._mp_chart_meta.get('stage_defs', {})
        is_ms = bar_item['type'] == 'Milestone' or stage_defs.get(stage_code, {}).get('is_milestone', False)
        if is_ms:
            edge = 'move'
        
        import matplotlib.dates as mdates
        
        # Zapamiętaj pikselową pozycję startu (do minimalnego progu ruchu)
        self._mp_drag_start_px = event.x
        
        if edge in ('start', 'end'):
            # Kliknięto krawędź - rozpocznij resize
            self._mp_drag_state.update({
                'active': True, 'stage_code': stage_code, 'project_id': pid,
                'edge': edge, 'original_date': bar_item[edge], 'bar_item': bar_item,
                'drag_anchor_x': None,
            })
            self._mp_chart_meta['canvas'].get_tk_widget().config(cursor='sb_h_double_arrow')
            edge_label = "początek" if edge == 'start' else "koniec"
            self._mp_status.config(
                text=f"🖱️ Przeciąganie {edge_label} szablonu: {stage_code}...",
                fg=self.COLOR_BLUE
            )
        else:
            # Kliknięto środek - rozpocznij przesuwanie całego przedziału
            self._mp_drag_state.update({
                'active': True, 'stage_code': stage_code, 'project_id': pid,
                'edge': 'move', 'original_date': bar_item['start'], 'bar_item': bar_item,
                'drag_anchor_x': mdates.num2date(event.xdata).replace(tzinfo=None),
            })
            self._mp_chart_meta['canvas'].get_tk_widget().config(cursor='fleur')
            self._mp_status.config(
                text=f"🖱️ Przesuwanie całego etapu: {stage_code}...",
                fg=self.COLOR_BLUE
            )
    
    def _mp_on_motion(self, event):
        """Obsługa ruchu myszy - zmiana kursora, preview drag, pan wykresu"""
        if not hasattr(self, '_mp_chart_meta'):
            return
        
        canvas = self._mp_chart_meta['canvas']
        ax = self._mp_chart_meta['ax']
        
        # ── PAN: przesuwanie wykresu (Shift+LMB) ──
        if self._mp_pan_state.get('active'):
            if event.x is None or event.y is None:
                return
            old_xlim = self._mp_pan_state['start_xlim']
            old_ylim = self._mp_pan_state['start_ylim']
            bbox = ax.get_window_extent()
            dpx = event.x - self._mp_pan_state['start_px']
            dpy = event.y - self._mp_pan_state['start_py']
            dx_data = dpx * (old_xlim[1] - old_xlim[0]) / bbox.width
            dy_data = dpy * (old_ylim[1] - old_ylim[0]) / bbox.height
            ax.set_xlim(old_xlim[0] - dx_data, old_xlim[1] - dx_data)
            ax.set_ylim(old_ylim[0] - dy_data, old_ylim[1] - dy_data)
            canvas.draw_idle()
            return
        
        if event.inaxes is None:
            self._mp_cancel_hover_timer()
            return
        
        # Bez locka — hover info dostępny, ale nie pokazuj kursora edycji
        if not self.have_lock and not self._mp_drag_state.get('active'):
            # Sprawdź czy najeżdżamy na dowolny pasek (podgląd)
            pid_h, sc_h, bar_h = self._mp_find_any_bar(event.xdata, event.ydata)
            if pid_h and bar_h and sc_h:
                pname = self.project_names.get(pid_h, f"Projekt {pid_h}")
                canvas.get_tk_widget().config(cursor='question_arrow')
                self._mp_status.config(
                    text=f"ℹ️ {pname} | {sc_h} — przytrzymaj aby zobaczyć szczegóły",
                    fg=self.COLOR_BLUE
                )
                hover_key = (pid_h, sc_h)
                if getattr(self, '_mp_hover_key', None) != hover_key:
                    self._mp_cancel_hover_timer()
                    self._mp_hover_key = hover_key
                    self._mp_hover_timer = canvas.get_tk_widget().after(
                        800, lambda p=pid_h, sc=sc_h: self._mp_show_stage_info_popup(p, sc)
                    )
            else:
                self._mp_cancel_hover_timer()
                canvas.get_tk_widget().config(cursor='')
            return
        
        # ── DRAG PREVIEW ──
        if self._mp_drag_state.get('active'):
            import matplotlib.dates as mdates
            new_date = mdates.num2date(event.xdata).replace(tzinfo=None)
            edge = self._mp_drag_state['edge']
            bar_item = self._mp_drag_state['bar_item']
            
            # Usuń stare linie preview
            if self._mp_drag_state.get('preview_line'):
                try:
                    if isinstance(self._mp_drag_state['preview_line'], list):
                        for line in self._mp_drag_state['preview_line']:
                            line.remove()
                    else:
                        self._mp_drag_state['preview_line'].remove()
                except Exception:
                    pass
                self._mp_drag_state['preview_line'] = None
            
            if edge == 'move':
                # Tryb przesuwania - pokaż dwie linie (nowy początek i nowy koniec)
                anchor = self._mp_drag_state.get('drag_anchor_x')
                delta = new_date - anchor
                new_start = bar_item['start'] + delta
                new_end = bar_item['end'] + delta
                
                line1 = ax.axvline(x=mdates.date2num(new_start), color='#e67e22',
                                   linewidth=2, linestyle='--', alpha=0.7, zorder=1000)
                line2 = ax.axvline(x=mdates.date2num(new_end), color='#e67e22',
                                   linewidth=2, linestyle='--', alpha=0.7, zorder=1000)
                self._mp_drag_state['preview_line'] = [line1, line2]
                
                duration = (bar_item['end'] - bar_item['start']).days
                self._mp_status.config(
                    text=f"🖱️ Przesuwanie: {self._mp_drag_state['stage_code']} → "
                         f"{new_start.strftime('%d-%m-%Y')} — {new_end.strftime('%d-%m-%Y')} ({duration}d)",
                    fg=self.COLOR_BLUE
                )
            else:
                # Tryb resize - jedna linia
                self._mp_drag_state['preview_line'] = ax.axvline(
                    x=mdates.date2num(new_date),
                    color='red', linewidth=2, linestyle='--', alpha=0.7, zorder=1000
                )
                edge_label = "Początek" if edge == 'start' else "Koniec"
                self._mp_status.config(
                    text=f"🖱️ Przeciąganie: {self._mp_drag_state['stage_code']} - "
                         f"{edge_label} → {new_date.strftime('%d-%m-%Y')}",
                    fg=self.COLOR_BLUE
                )
            
            canvas.draw_idle()
            return
        
        # ── HOVER — zmiana kursora przy krawędziach ──
        pid, stage_code, edge, bar_item = self._mp_find_bar(event.xdata, event.ydata)
        
        if pid and pid != self._locked_project_id:
            # Pasek innego projektu - pokaż info kursor + hover timer do podglądu
            canvas.get_tk_widget().config(cursor='question_arrow')
            if stage_code:
                pname = self.project_names.get(pid, f"Projekt {pid}")
                self._mp_status.config(
                    text=f"ℹ️ {pname} | {stage_code} — przytrzymaj aby zobaczyć szczegóły",
                    fg=self.COLOR_BLUE
                )
                hover_key = (pid, stage_code)
                if getattr(self, '_mp_hover_key', None) != hover_key:
                    self._mp_cancel_hover_timer()
                    self._mp_hover_key = hover_key
                    self._mp_hover_timer = canvas.get_tk_widget().after(
                        800, lambda p=pid, sc=stage_code: self._mp_show_stage_info_popup(p, sc)
                    )
            else:
                self._mp_cancel_hover_timer()
            return
        
        # Milestone (from stage_defs) → zawsze fleur (move)
        self._mp_cancel_hover_timer()
        stage_defs = self._mp_chart_meta.get('stage_defs', {})
        is_ms = (bar_item and (
            bar_item.get('type') == 'Milestone' or
            stage_defs.get(stage_code or '', {}).get('is_milestone', False)
        ))
        
        if is_ms and bar_item:
            canvas.get_tk_widget().config(cursor='fleur')
            self._mp_status.config(
                text=f"🖱️ Przeciągnij aby przesunąć milestone: {stage_code}",
                fg=self.COLOR_BLUE
            )
        elif edge in ('start', 'end'):
            canvas.get_tk_widget().config(cursor='sb_h_double_arrow')
            edge_label = "początek" if edge == 'start' else "koniec"
            self._mp_status.config(
                text=f"🖱️ Przeciągnij aby zmienić {edge_label} szablonu: {stage_code}",
                fg=self.COLOR_BLUE
            )
        elif bar_item and bar_item['type'] == 'Szablon':
            canvas.get_tk_widget().config(cursor='fleur')
            self._mp_status.config(
                text=f"🖱️ Przeciągnij aby przesunąć cały etap: {stage_code}",
                fg=self.COLOR_BLUE
            )
        elif bar_item and bar_item['type'] == 'Milestone':
            canvas.get_tk_widget().config(cursor='fleur')
            self._mp_status.config(
                text=f"🖱️ Przeciągnij aby przesunąć milestone: {stage_code}",
                fg=self.COLOR_BLUE
            )
        else:
            # Fallback: sprawdź Rzeczywiste/Prognoza dla hover podglądu
            pid_any, sc_any, bar_any = self._mp_find_any_bar(event.xdata, event.ydata)
            if pid_any and sc_any and bar_any:
                pname = self.project_names.get(pid_any, f"Projekt {pid_any}")
                bar_type = bar_any.get('type', '')
                canvas.get_tk_widget().config(cursor='question_arrow')
                self._mp_status.config(
                    text=f"ℹ️ {pname} | {sc_any} ({bar_type}) — przytrzymaj aby zobaczyć szczegóły",
                    fg=self.COLOR_BLUE
                )
                hover_key = (pid_any, sc_any)
                if getattr(self, '_mp_hover_key', None) != hover_key:
                    self._mp_hover_key = hover_key
                    self._mp_hover_timer = canvas.get_tk_widget().after(
                        800, lambda p=pid_any, sc=sc_any: self._mp_show_stage_info_popup(p, sc)
                    )
            else:
                canvas.get_tk_widget().config(cursor='')
                if not self._mp_drag_state.get('active'):
                    self._mp_status.config(
                        text=f"✅ Wykres gotowy | Shift+mysz: przesuwanie | Ctrl+scroll: zoom czasu | Scroll: góra/dół | 🏠 reset widoku",
                        fg=self.COLOR_GREEN
                    )
    
    def _is_mp_chart_open(self):
        """Sprawdź czy okno multi-projekt jest otwarte i widoczne"""
        try:
            return (hasattr(self, '_mp_chart_window') and 
                    self._mp_chart_window and 
                    self._mp_chart_window.winfo_exists() and
                    hasattr(self, '_mp_chart_meta') and 
                    self._mp_chart_meta)
        except Exception:
            return False
    
    def _sync_mp_chart_lock_state(self):
        """Synchronizuj stan locka z głównej aplikacji do Multi-project chart.
        Wywoływane po acquire/release/cancel locka z głównego okna."""
        if not self._is_mp_chart_open():
            return
        try:
            pid = self.selected_project_id
            project_ids = self._mp_chart_meta.get('project_ids', [])
            if pid not in project_ids:
                return
            
            if self.have_lock and self._locked_project_id == pid:
                # Lock przejęty — zaznacz projekt na multi-chart
                self._mp_selected_pid = pid
                pname = self.project_names.get(pid, f"Projekt {pid}")
                self._mp_status.config(
                    text=f"🔒 Locked: {pname} — dwuklik na pasek = edycja etapu",
                    fg=self.COLOR_GREEN
                )
            else:
                # Lock zwolniony — odznacz projekt na multi-chart
                self._mp_selected_pid = None
                self._mp_status.config(
                    text=f"🔓 Dwuklik na projekt = przejmij lock",
                    fg="#7f8c8d"
                )
            
            self._mp_build_right_panel(project_ids)
            self._create_multi_project_chart_window(project_ids, preserve_view=True)
        except Exception as e:
            print(f"⚠️ _sync_mp_chart_lock_state: {e}")
    
    def _mp_cancel_hover_timer(self):
        """Anuluj timer hover podglądu i zamknij popup jeśli otwarty"""
        timer = getattr(self, '_mp_hover_timer', None)
        if timer and hasattr(self, '_mp_chart_meta') and self._mp_chart_meta:
            try:
                self._mp_chart_meta['canvas'].get_tk_widget().after_cancel(timer)
            except Exception:
                pass
        self._mp_hover_timer = None
        self._mp_hover_key = None
        # Zamknij popup jeśli otwarty
        old_popup = getattr(self, '_mp_info_popup', None)
        if old_popup:
            try:
                old_popup.destroy()
            except Exception:
                pass
            self._mp_info_popup = None
    
    def _mp_show_stage_info_popup(self, pid, stage_code):
        """Pokaż okno informacyjne (read-only) o etapie innego projektu"""
        self._mp_hover_timer = None
        self._mp_hover_key = None
        
        # Zamknij poprzedni popup jeśli istnieje
        old_popup = getattr(self, '_mp_info_popup', None)
        if old_popup:
            try:
                old_popup.destroy()
            except Exception:
                pass
            self._mp_info_popup = None
        
        try:
            project_db = self.get_project_db_path(pid)
            forecast = rmm.recalculate_forecast(project_db, pid)
        except Exception:
            return
        
        if stage_code not in forecast:
            return
        
        fc = forecast[stage_code]
        project_name = self.project_names.get(pid, f"Projekt {pid}")
        
        # Status etapu
        if fc.get('is_actual'):
            status_text = "✔️ Zakończony"
            status_color = self.COLOR_GREEN
        elif fc.get('is_active'):
            try:
                fs = fc.get('forecast_start')
                if fs:
                    start_dt = datetime.fromisoformat(fs)
                    days_active = (datetime.now() - start_dt).days
                    status_text = f"● TRWA ({days_active} dni)"
                else:
                    status_text = "● TRWA"
            except Exception:
                status_text = "● TRWA"
            status_color = self.COLOR_BLUE
        else:
            status_text = "○ Nieaktywny"
            status_color = 'gray'
        
        # Odchylenie
        variance = fc.get('variance_days', 0)
        if variance > 0:
            var_text = f"+{variance} dni"
            var_color = self.COLOR_RED
        elif variance < 0:
            var_text = f"{variance} dni"
            var_color = self.COLOR_GREEN
        else:
            var_text = "0 dni"
            var_color = 'gray'
        
        parent = self._mp_chart_window
        popup = tk.Toplevel(parent)
        popup.transient(parent)
        popup.overrideredirect(False)
        popup.title(f"ℹ️ {stage_code} — {project_name} (READ-ONLY)")
        popup.resizable(True, True)
        self._mp_info_popup = popup
        
        # Rozmiar i pozycja — obok kursora
        w, h = 750, 380
        try:
            mx = parent.winfo_pointerx()
            my = parent.winfo_pointery()
            x = mx + 20
            y = my + 10
            # Nie wyjedź poza ekran
            sw = popup.winfo_screenwidth()
            sh = popup.winfo_screenheight()
            if x + w > sw:
                x = mx - w - 20
            if y + h > sh:
                y = my - h - 10
        except Exception:
            x = (popup.winfo_screenwidth() // 2) - (w // 2)
            y = (popup.winfo_screenheight() // 2) - (h // 2)
        popup.geometry(f"{w}x{h}+{x}+{y}")
        
        # ===== HEADER =====
        header_frame = tk.Frame(popup, bg="#7f8c8d", height=40)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        tk.Label(
            header_frame,
            text=f"ℹ️ PODGLĄD ETAPU (READ-ONLY)",
            bg="#7f8c8d", fg="white",
            font=("Arial", 11, "bold"),
            padx=10
        ).pack(side=tk.LEFT, fill=tk.Y)
        
        tk.Button(
            header_frame, text="✕", command=popup.destroy,
            bg="#e74c3c", fg="white", font=("Arial", 10, "bold"),
            padx=8, pady=2, relief=tk.FLAT, cursor='hand2'
        ).pack(side=tk.RIGHT, padx=5, pady=5)
        
        # ===== INFO BAR =====
        info_frame = tk.Frame(popup, bg="#ecf0f1", pady=6)
        info_frame.pack(fill=tk.X)
        
        tk.Label(
            info_frame, text=f"  Projekt: {project_name}",
            bg="#ecf0f1", font=self.FONT_BOLD, fg=self.COLOR_TEXT_DARK, anchor='w'
        ).pack(side=tk.LEFT, padx=10)
        
        tk.Label(
            info_frame, text=f"Etap: {stage_code}",
            bg="#ecf0f1", font=self.FONT_BOLD, fg=self.COLOR_BLUE, anchor='w'
        ).pack(side=tk.LEFT, padx=15)
        
        tk.Label(
            info_frame, text=status_text,
            bg="#ecf0f1", font=self.FONT_BOLD, fg=status_color
        ).pack(side=tk.LEFT, padx=15)
        
        tk.Label(
            info_frame, text=f"Odchylenie: {var_text}",
            bg="#ecf0f1", font=self.FONT_BOLD, fg=var_color
        ).pack(side=tk.LEFT, padx=15)
        
        # ===== TABELA DAT (read-only) =====
        table_frame = tk.Frame(popup, padx=15, pady=10)
        table_frame.pack(fill=tk.X)
        
        for col in range(4):
            table_frame.columnconfigure(col, weight=1)
        
        headers = [
            ("Szablon Start", self.COLOR_TOPBAR),
            ("Szablon Koniec", self.COLOR_TOPBAR),
            ("Prognoza Start", "#7f8c8d"),
            ("Prognoza Koniec", "#7f8c8d"),
        ]
        for col, (header_text, bg_color) in enumerate(headers):
            tk.Label(
                table_frame, text=header_text,
                font=self.FONT_BOLD, bg=bg_color, fg="white",
                relief=tk.RAISED, padx=12, pady=4
            ).grid(row=0, column=col, sticky="ew", padx=2, pady=(0, 3))
        
        dates = [
            self.format_date_ddmmyyyy(fc.get('template_start')) or '—',
            self.format_date_ddmmyyyy(fc.get('template_end')) or '—',
            self.format_date_ddmmyyyy(fc.get('forecast_start')) or '—',
            self.format_date_ddmmyyyy(fc.get('forecast_end')) or '—',
        ]
        for col, dt in enumerate(dates):
            tk.Label(
                table_frame, text=dt,
                font=("Arial", 11), bg="#f0f0f0", fg="#333",
                relief=tk.SUNKEN, padx=8, pady=4
            ).grid(row=1, column=col, padx=2, pady=2, sticky="ew")
        
        # ===== PRACOWNICY =====
        staff_frame = tk.Frame(popup, padx=15, pady=3)
        staff_frame.pack(fill=tk.X)
        
        try:
            assigned_staff = rmm.get_stage_assigned_staff(
                project_db, self.rm_master_db_path, pid, stage_code
            )
            staff_count = len(assigned_staff)
        except Exception:
            assigned_staff = []
            staff_count = 0
        
        staff_label = f"👷 Pracownicy ({staff_count}):" if staff_count > 0 else "👷 Pracownicy: brak"
        tk.Label(
            staff_frame, text=staff_label,
            font=self.FONT_BOLD, fg=self.COLOR_GREEN if staff_count > 0 else "gray"
        ).pack(side=tk.LEFT, padx=(0, 8))
        
        if staff_count > 0:
            staff_info = []
            for s in assigned_staff:
                name = s['employee_name']
                category = s['category']
                preferred = rmm.STAGE_TO_PREFERRED_CATEGORY.get(stage_code, [])
                if category not in preferred:
                    staff_info.append(f"⚠️ {name} ({category})")
                else:
                    staff_info.append(f"👤 {name} ({category})")
            tk.Label(
                staff_frame, text=", ".join(staff_info),
                font=self.FONT_SMALL, fg="gray",
                wraplength=550, justify=tk.LEFT
            ).pack(side=tk.LEFT, padx=3)
        
        # ===== NOTATKI =====
        notes_frame = tk.Frame(popup, padx=15, pady=3)
        notes_frame.pack(fill=tk.X)
        
        try:
            notes_stats = rmm.get_topic_stats(project_db, pid, stage_code)
            topic_count = notes_stats['total_topics']
            notes_count = notes_stats['total_notes']
            alarms_count = notes_stats['active_alarms']
        except Exception:
            topic_count = 0
            notes_count = 0
            alarms_count = 0
        
        notes_text = "📝 Notatki: brak"
        if topic_count > 0 or notes_count > 0:
            notes_text = f"📝 {topic_count} tematów, {notes_count} notatek"
        if alarms_count > 0:
            notes_text += f" ⏰ {alarms_count} alarmów"
        
        tk.Label(
            notes_frame, text=notes_text,
            font=self.FONT_BOLD, fg=self.COLOR_PURPLE if topic_count > 0 else "gray"
        ).pack(side=tk.LEFT, padx=(0, 8))
        
        # Podgląd tematów
        if topic_count > 0:
            try:
                topics_preview = rmm.get_topics(project_db, pid, stage_code)[:3]
                for tp in topics_preview:
                    pri_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(tp['priority'], "⚪")
                    title_text = tp['title'][:50]
                    if len(tp['title']) > 50:
                        title_text += "…"
                    tk.Label(
                        notes_frame,
                        text=f" {pri_icon} #{tp['topic_number']} {title_text} ",
                        bg="#f0f4ff", fg="#2c3e50",
                        font=("Arial", 8), padx=3, pady=1
                    ).pack(side=tk.LEFT, padx=2)
            except Exception:
                pass
        
        # ===== OKRESY =====
        periods = fc.get('actual_periods', [])
        if periods:
            per_frame = tk.Frame(popup, padx=15, pady=3)
            per_frame.pack(fill=tk.X)
            
            tk.Label(
                per_frame, text=f"📊 Okresy ({len(periods)}):",
                font=self.FONT_BOLD, fg=self.COLOR_TEXT_DARK
            ).pack(side=tk.LEFT, padx=(0, 8))
            
            periods_text = ""
            for i, p in enumerate(periods, 1):
                status = "TRWA" if p['ended_at'] is None else "✓"
                start_fmt = self.format_datetime(p['started_at'])
                end_fmt = self.format_datetime(p['ended_at']) if p['ended_at'] else 'TRWA'
                periods_text += f"#{i}: {start_fmt} → {end_fmt} ({status})  "
            
            tk.Label(
                per_frame, text=periods_text,
                font=self.FONT_SMALL, fg="gray",
                wraplength=600, justify=tk.LEFT
            ).pack(side=tk.LEFT, padx=3)
        
        # Zamknij Escape
        popup.bind('<Escape>', lambda e: popup.destroy())
        popup.focus_set()
    
    def _mp_on_release(self, event):
        """Obsługa puszczenia przycisku myszy - zapisz nową datę lub zakończ pan"""
        # Zakończ pan
        if self._mp_pan_state.get('active'):
            self._mp_pan_state['active'] = False
            self._mp_chart_meta['canvas'].get_tk_widget().config(cursor='')
            return
        
        if not self._mp_drag_state.get('active'):
            return
        
        # Minimalny próg ruchu - zapobiegaj przypadkowym przesunięciom przy dwukliku
        start_px = getattr(self, '_mp_drag_start_px', None)
        if start_px is not None and event.x is not None and abs(event.x - start_px) < 5:
            # Mysz się nie ruszyła — anuluj drag (prawdopodobnie dwuklik)
            self._mp_drag_state['active'] = False
            self._mp_drag_state['stage_code'] = None
            self._mp_drag_state['edge'] = None
            self._mp_drag_state['original_date'] = None
            self._mp_drag_state['bar_item'] = None
            self._mp_drag_state['drag_anchor_x'] = None
            self._mp_drag_state['preview_line'] = None
            self._mp_chart_meta['canvas'].get_tk_widget().config(cursor='')
            return
        
        import matplotlib.dates as mdates
        
        try:
            # Usuń linie preview
            if self._mp_drag_state.get('preview_line'):
                try:
                    if isinstance(self._mp_drag_state['preview_line'], list):
                        for line in self._mp_drag_state['preview_line']:
                            line.remove()
                    else:
                        self._mp_drag_state['preview_line'].remove()
                except Exception:
                    pass
                self._mp_drag_state['preview_line'] = None
                # Natychmiastowe odświeżenie żeby linia zniknęła
                self._mp_chart_meta['canvas'].draw_idle()
            
            # Jeśli puszczono poza wykresem, anuluj
            if event.inaxes is None or event.xdata is None:
                self._mp_status.config(
                    text="⚠️ Przeciąganie anulowane (puszczono poza wykresem)",
                    fg=self.COLOR_RED
                )
                self._mp_drag_state['active'] = False
                self._mp_chart_meta['canvas'].draw_idle()
                return
            
            new_date_raw = mdates.num2date(event.xdata).replace(tzinfo=None)
            # Zaokrąglij do najbliższego dnia (nie floor!)
            new_date = (new_date_raw + timedelta(hours=12)).replace(hour=0, minute=0, second=0)
            bar = self._mp_drag_state['bar_item']
            edge = self._mp_drag_state['edge']
            stage_code = self._mp_drag_state['stage_code']
            pid = self._mp_drag_state['project_id']
            
            project_db = self.get_project_db_path(pid)
            
            if edge == 'move':
                # ===== TRYB PRZESUWANIA CAŁEGO PRZEDZIAŁU =====
                anchor = self._mp_drag_state.get('drag_anchor_x')
                # Zaokrąglij anchor do dnia (tak samo jak new_date)
                anchor_day = (anchor + timedelta(hours=12)).replace(hour=0, minute=0, second=0)
                delta = new_date - anchor_day
                new_start = bar['start'] + delta
                new_end = bar['end'] + delta
                # Upewnij się, że wynik jest midnight
                new_start = new_start.replace(hour=0, minute=0, second=0)
                new_end = new_end.replace(hour=0, minute=0, second=0)
                
                # Milestone: obie daty = ta sama (1 dzień)
                stage_defs = self._mp_chart_meta.get('stage_defs', {})
                if stage_defs.get(stage_code, {}).get('is_milestone', False):
                    new_end = new_start
                
                new_start_iso = new_start.strftime('%Y-%m-%d')
                new_end_iso = new_end.strftime('%Y-%m-%d')
                
                con = rmm._open_rm_connection(project_db, row_factory=False)
                con.execute("""
                    UPDATE stage_schedule SET template_start = ?, template_end = ?
                    WHERE project_stage_id = (
                        SELECT id FROM project_stages WHERE project_id = ? AND stage_code = ?
                    )
                """, (new_start_iso, new_end_iso, pid, stage_code))
                con.commit()
                con.close()
                
                rmm.recalculate_forecast(project_db, pid)
                
                duration = (bar['end'] - bar['start']).days
                if bar.get('type') == 'Milestone' or stage_defs.get(stage_code, {}).get('is_milestone', False):
                    self._mp_status.config(
                        text=f"✅ Przesunięto milestone {stage_code}: {new_start.strftime('%d-%m-%Y')}",
                        fg=self.COLOR_GREEN
                    )
                else:
                    self._mp_status.config(
                        text=f"✅ Przesunięto {stage_code}: {new_start.strftime('%d-%m-%Y')} — {new_end.strftime('%d-%m-%Y')} ({duration}d)",
                        fg=self.COLOR_GREEN
                    )
            
            else:
                # ===== TRYB RESIZE KRAWĘDZI =====
                if edge == 'end':
                    if new_date < bar['start']:
                        messagebox.showerror(
                            "❌ Błąd walidacji",
                            f"Data końca ({new_date.strftime('%d-%m-%Y')}) nie może być wcześniejsza\n"
                            f"niż data początku ({bar['start'].strftime('%d-%m-%Y')})!",
                            parent=self._mp_chart_window
                        )
                        self._mp_drag_state['active'] = False
                        self._mp_chart_meta['canvas'].draw_idle()
                        return
                else:  # edge == 'start'
                    if new_date > bar['end']:
                        messagebox.showerror(
                            "❌ Błąd walidacji",
                            f"Data początku ({new_date.strftime('%d-%m-%Y')}) nie może być późniejsza\n"
                            f"niż data końca ({bar['end'].strftime('%d-%m-%Y')})!",
                            parent=self._mp_chart_window
                        )
                        self._mp_drag_state['active'] = False
                        self._mp_chart_meta['canvas'].draw_idle()
                        return
                
                date_iso = new_date.strftime('%Y-%m-%d')
                field_db = 'template_start' if edge == 'start' else 'template_end'
                
                con = rmm._open_rm_connection(project_db, row_factory=False)
                con.execute(f"""
                    UPDATE stage_schedule SET {field_db} = ?
                    WHERE project_stage_id = (
                        SELECT id FROM project_stages WHERE project_id = ? AND stage_code = ?
                    )
                """, (date_iso, pid, stage_code))
                con.commit()
                con.close()
                
                rmm.recalculate_forecast(project_db, pid)
                
                edge_label = "początek" if edge == 'start' else "koniec"
                self._mp_status.config(
                    text=f"✅ Zaktualizowano {edge_label} szablonu: {stage_code} → {new_date.strftime('%d-%m-%Y')}",
                    fg=self.COLOR_GREEN
                )
            
            # Wyłącz drag PRZED odświeżeniem (draw() przetwarza Tk eventy
            # i _mp_on_motion narysowałby nową linię preview)
            self._mp_drag_state['active'] = False
            self._mp_drag_state['preview_line'] = None
            self._mp_chart_meta['canvas'].get_tk_widget().config(cursor='')
            
            # Odśwież wykres (zachowaj widok)
            self._create_multi_project_chart_window(self._mp_chart_meta['project_ids'], preserve_view=True)
            
            # Odśwież wykres wbudowany jeśli otwarty i dotyczy tego samego projektu
            if self.selected_project_id == pid and self.matplotlib_canvas:
                try:
                    self.create_embedded_gantt_chart(preserve_view=True)
                except Exception:
                    pass
            
            # Odśwież timeline w głównym oknie (entry widgety)
            if self.selected_project_id == pid and self.timeline_entries:
                try:
                    self.refresh_timeline()
                except Exception:
                    pass
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._mp_status.config(text=f"❌ Błąd: {e}", fg=self.COLOR_RED)
        
        finally:
            # Reset stanu drag
            self._mp_drag_state['active'] = False
            self._mp_drag_state['stage_code'] = None
            self._mp_drag_state['edge'] = None
            self._mp_drag_state['original_date'] = None
            self._mp_drag_state['bar_item'] = None
            self._mp_drag_state['drag_anchor_x'] = None
            self._mp_drag_state['preview_line'] = None
            self._mp_chart_meta['canvas'].get_tk_widget().config(cursor='')
    
    def _mp_on_dblclick(self, event):
        """Podwójne kliknięcie:
        - Bez locka → lockuj projekt pod kursorem (zaznacz + przejmij lock)
        - Z lockiem na ten projekt → otwórz dialog edycji etapu
        """
        if not event.dblclick or event.inaxes is None:
            return
        if not hasattr(self, '_mp_chart_meta'):
            return
        
        # Ustal projekt pod kursorem
        y_idx = round(event.ydata)
        y_to_pid = self._mp_chart_meta.get('y_to_pid', {})
        clicked_pid = y_to_pid.get(y_idx)
        if clicked_pid is None:
            return
        
        # --- Nie mamy locka → lockuj ten projekt ---
        if not self._mp_selected_pid or self._mp_selected_pid != clicked_pid:
            self._mp_select_and_lock_project(clicked_pid)
            return
        
        # --- Mamy lock na ten projekt → edycja etapu ---
        if self._mp_selected_pid == clicked_pid and self.have_lock and self._locked_project_id == clicked_pid:
            # Anuluj wszelki drag (pierwsze kliknięcie mogło go rozpocząć)
            self._mp_drag_state.update({
                'active': False, 'stage_code': None, 'edge': None,
                'original_date': None, 'bar_item': None, 'drag_anchor_x': None,
                'preview_line': None,
            })
            
            pid, stage_code, edge, bar_item = self._mp_find_bar(event.xdata, event.ydata)
            if not stage_code or not bar_item:
                return
            if bar_item['type'] not in ('Szablon', 'Milestone'):
                self._mp_status.config(text="ℹ️ Edycja tylko pasków szablonu", fg=self.COLOR_ORANGE)
                return
            
            self.selected_project_id = clicked_pid
            self._open_stage_edit_dialog(stage_code, parent=self._mp_chart_window)
            # Po zamknięciu dialogu — odśwież
            self._mp_chart_window.after(500, lambda: self._create_multi_project_chart_window(
                self._mp_chart_meta['project_ids'], preserve_view=True))
    
    def _mp_select_and_lock_project(self, pid):
        """Zaznacz projekt w multi-Gantt i przejmij lock (dwuklik)"""
        pname = self.project_names.get(pid, f"Projekt {pid}")
        
        # Jeśli mamy lock na inny projekt - najpierw zwolnij
        if self.have_lock and self._locked_project_id and self._locked_project_id != pid:
            old_name = self.project_names.get(self._locked_project_id, f"Projekt {self._locked_project_id}")
            if not messagebox.askyesno(
                "Zmiana projektu",
                f"Masz lock na: {old_name}\n\nZwolnić lock i przejąć {pname}?",
                parent=self._mp_chart_window
            ):
                return
            # Odśwież formularz główny przed zwolnieniem (żeby save_all_templates
            # nie nadpisał zmian z multi-Gantt starymi danymi)
            old_lock_pid = self._locked_project_id
            if self.selected_project_id == old_lock_pid and self.timeline_entries:
                try:
                    self.refresh_timeline()
                except Exception:
                    pass
            self._release_current_lock()
        
        # Przejmij lock
        success = self._acquire_project_lock(pid)
        if success:
            self._mp_selected_pid = pid
            self.selected_project_id = pid
            self.read_only_mode = False
            self._snapshot_stage_dates()  # Snapshot dat do cofnięcia przy Anuluj
            self._mp_status.config(
                text=f"🔒 Locked: {pname} — dwuklik na pasek = edycja etapu",
                fg=self.COLOR_GREEN
            )
            # Synchronizuj główną aplikację: combo, lock status, oś czasu
            try:
                idx = self.projects.index(pid)
                self.project_combo.current(idx)
            except (ValueError, AttributeError):
                pass
            self._update_lock_buttons_state()
            self._refresh_combo_lock_info()
            self.load_project_stages()
            self.refresh_timeline()
            try:
                self.refresh_dashboard()
            except Exception:
                pass
            try:
                self.create_embedded_gantt_chart(preserve_view=False)
            except Exception:
                pass
        else:
            # Sprawdź kto ma lock
            owner = self.lock_manager.get_project_lock_owner(pid)
            if owner:
                owner_name = owner.get('user', 'Nieznany')
                owner_comp = owner.get('computer', '')
                self._mp_status.config(
                    text=f"🔒 {pname} — locked przez {owner_name}@{owner_comp}",
                    fg=self.COLOR_RED
                )
            else:
                self._mp_status.config(
                    text=f"❌ Nie udało się przejąć locka: {pname}",
                    fg=self.COLOR_RED
                )
            # Zaznacz wizualnie mimo braku locka (bez edycji)
            self._mp_selected_pid = pid
        
        # Odśwież prawy panel + etykiety
        self._mp_build_right_panel(self._mp_chart_meta['project_ids'])
        self._create_multi_project_chart_window(self._mp_chart_meta['project_ids'], preserve_view=True)
    
    def _mp_unlock_project(self):
        """Zwolnij lock projektu z multi-Gantt"""
        if not self._mp_selected_pid:
            return
        pid = self._mp_selected_pid
        pname = self.project_names.get(pid, f"Projekt {pid}")
        
        if self.have_lock and self._locked_project_id == pid:
            # Multi-Gantt zapisuje zmiany do DB na bieżąco (w _mp_on_release),
            # więc pomijamy save_all_templates() które nadpisałoby DB starymi
            # datami z formularza głównego UI. Wywołujemy logikę _release_current_lock
            # bez save_all_templates().
            
            # Backup projektu przed zwolnieniem locka
            if self._locked_project_id is not None and self.backup_manager:
                try:
                    print(f"📦 Backup projektu {self._locked_project_id} przed zwolnieniem locka...")
                    self.backup_manager.backup_project(self._locked_project_id, skip_checkpoint=True)
                    print(f"✅ Backup projektu {self._locked_project_id} zakończony")
                except Exception as e:
                    print(f"⚠️ Błąd backupu projektu (niegroźne): {e}")
            
            # Zwolnij lock
            self.lock_manager.release_project_lock(self._locked_project_id)
            print(f"🔓 Lock project {self._locked_project_id} zwolniony")
            self._locked_project_id = None
            self.have_lock = False
            self.current_lock_id = None
            
            # Odśwież formularz główny z DB (żeby miał aktualne daty)
            if self.selected_project_id == pid and self.timeline_entries:
                try:
                    self.refresh_timeline()
                except Exception:
                    pass
        
        self._mp_selected_pid = None
        self._update_lock_buttons_state()
        self._refresh_combo_lock_info()
        self._mp_status.config(text=f"🔓 Zwolniono: {pname}", fg="#7f8c8d")
        self._mp_build_right_panel(self._mp_chart_meta['project_ids'])
        self._create_multi_project_chart_window(self._mp_chart_meta['project_ids'], preserve_view=True)
    
    def _mp_cancel_lock(self):
        """Anuluj lock z multi-Gantt (cofnij zmiany + zwolnij)"""
        if not self._mp_selected_pid:
            return
        pid = self._mp_selected_pid
        pname = self.project_names.get(pid, f"Projekt {pid}")
        
        if not messagebox.askyesno(
            "Anuluj zmiany",
            f"Cofnąć wszystkie zmiany w {pname}\ni zwolnić lock?",
            icon='warning',
            parent=self._mp_chart_window
        ):
            return
        
        if self.have_lock and self._locked_project_id == pid:
            # Przywróć daty ze snapshotu
            old_pid = self.selected_project_id
            self.selected_project_id = pid
            if hasattr(self, '_dates_snapshot') and self._dates_snapshot:
                self._restore_stage_dates_from_snapshot()
            self.selected_project_id = old_pid
            
            # Zwalniamy lock BEZ save_all_templates() — snapshot już przywrócił dane,
            # a save_all_templates nadpisałby je starymi z formularza głównego
            if self._locked_project_id is not None and self.backup_manager:
                try:
                    self.backup_manager.backup_project(self._locked_project_id, skip_checkpoint=True)
                except Exception:
                    pass
            self.lock_manager.release_project_lock(self._locked_project_id)
            print(f"🔓 Lock project {self._locked_project_id} zwolniony (anulowano)")
            self._locked_project_id = None
            self.have_lock = False
            self.current_lock_id = None
            
            # Odśwież formularz główny
            if self.selected_project_id == pid and self.timeline_entries:
                try:
                    self.refresh_timeline()
                except Exception:
                    pass
        
        self._mp_selected_pid = None
        self._update_lock_buttons_state()
        self._refresh_combo_lock_info()
        self._mp_status.config(text=f"✖ Anulowano: {pname}", fg=self.COLOR_ORANGE)
        self._mp_build_right_panel(self._mp_chart_meta['project_ids'])
        self._create_multi_project_chart_window(self._mp_chart_meta['project_ids'], preserve_view=True)
    
    def _mp_build_right_panel(self, project_ids):
        """Buduje/odświeża statyczny prawy panel multi-Gantt"""
        panel = self._mp_right_panel
        for child in panel.winfo_children():
            child.destroy()
        
        pid = self._mp_selected_pid
        
        if pid is None:
            # Brak zaznaczenia
            tk.Label(panel, text="PROJEKT", font=("Arial", 10, "bold"),
                     bg="#f0f0f0", fg="#555").pack(pady=(15, 5))
            tk.Label(panel, text="Dwuklik na wykresie\n= wybierz projekt",
                     font=("Arial", 9), bg="#f0f0f0", fg="#888",
                     justify=tk.CENTER).pack(pady=10, padx=5)
            return
        
        pname = self.project_names.get(pid, f"Projekt {pid}")
        is_locked = (self.have_lock and self._locked_project_id == pid)
        
        # === Nazwa projektu ===
        name_color = "#e74c3c" if is_locked else "#2c3e50"
        lock_icon = "🔒" if is_locked else "📋"
        tk.Label(panel, text=f"{lock_icon} {pname}",
                 font=("Arial", 10, "bold"), bg="#f0f0f0", fg=name_color,
                 wraplength=160, justify=tk.CENTER).pack(pady=(10, 5), padx=3)
        
        ttk.Separator(panel, orient='horizontal').pack(fill=tk.X, padx=5, pady=3)
        
        # === Przyciski lock ===
        btn_frame = tk.Frame(panel, bg="#f0f0f0")
        btn_frame.pack(fill=tk.X, padx=5, pady=3)
        
        if is_locked:
            tk.Button(btn_frame, text="🔓 Zwolnij lock",
                      command=self._mp_unlock_project,
                      bg="#27ae60", fg="white", font=("Arial", 9, "bold"),
                      padx=5, pady=2, cursor='hand2').pack(fill=tk.X, pady=1)
            tk.Button(btn_frame, text="✖ Anuluj zmiany",
                      command=self._mp_cancel_lock,
                      bg=self.COLOR_ORANGE, fg="white", font=("Arial", 9),
                      padx=5, pady=2, cursor='hand2').pack(fill=tk.X, pady=1)
        else:
            # Nie mamy locka - pokaż kto go ma (jeśli ktoś)
            owner = self.lock_manager.get_project_lock_owner(pid)
            if owner:
                owner_name = owner.get('user', '?')
                tk.Label(btn_frame, text=f"🔒 Lock: {owner_name}",
                         font=("Arial", 8), bg="#f0f0f0", fg="#e74c3c").pack(fill=tk.X)
                tk.Button(btn_frame, text="⚡ Wymuś lock",
                          command=lambda: self._mp_force_lock(pid),
                          bg="#e74c3c", fg="white", font=("Arial", 9),
                          padx=5, pady=2, cursor='hand2').pack(fill=tk.X, pady=1)
            else:
                tk.Button(btn_frame, text="🔒 Przejmij lock",
                          command=lambda: self._mp_select_and_lock_project(pid),
                          bg=self.COLOR_BLUE, fg="white", font=("Arial", 9, "bold"),
                          padx=5, pady=2, cursor='hand2').pack(fill=tk.X, pady=1)
        
        # Odznacz projekt
        tk.Button(btn_frame, text="↩ Odznacz",
                  command=self._mp_deselect_project,
                  bg="#7f8c8d", fg="white", font=("Arial", 8),
                  padx=5, pady=1, cursor='hand2').pack(fill=tk.X, pady=(3, 0))
        
        # === Filtr per-projekt (S/R/P) z przełącznikiem ON/OFF ===
        ttk.Separator(panel, orient='horizontal').pack(fill=tk.X, padx=5, pady=5)
        
        def _on_proj_filter_change():
            self._create_multi_project_chart_window(
                self._mp_chart_meta['project_ids'], preserve_view=True)
        
        # Przełącznik ON/OFF: niezależność od filtra globalnego
        if pid not in self._mp_proj_filter_override:
            self._mp_proj_filter_override[pid] = False
        
        override_var = tk.BooleanVar(value=self._mp_proj_filter_override.get(pid, False))
        
        def _on_override_change():
            self._mp_proj_filter_override[pid] = override_var.get()
            _on_proj_filter_change()
        
        override_frame = tk.Frame(panel, bg="#f0f0f0")
        override_frame.pack(fill=tk.X, padx=5, pady=(0, 3))
        tk.Checkbutton(override_frame, text="Własny filtr", variable=override_var,
                      command=_on_override_change,
                      font=("Arial", 9, "bold"), bg="#f0f0f0",
                      fg="#e67e22", selectcolor="white",
                      activebackground="#f0f0f0",
                      anchor='w').pack(fill=tk.X)
        
        is_override = self._mp_proj_filter_override.get(pid, False)
        if is_override:
            tk.Label(panel, text="☁ pomija filtr globalny",
                     font=("Arial", 7), bg="#f0f0f0", fg="#e67e22").pack(anchor='w', padx=10)
        
        tk.Label(panel, text="Filtr projektu:", font=("Arial", 9, "bold"),
                 bg="#f0f0f0").pack(anchor='w', padx=5)
        
        if pid not in self._mp_proj_type_filters:
            self._mp_proj_type_filters[pid] = {'Szablon': True, 'Rzeczywiste': True, 'Prognoza': True}
        
        proj_filters = self._mp_proj_type_filters[pid]
        type_info = [
            ('Szablon', '#95a5a6'),
            ('Rzeczywiste', '#27ae60'),
            ('Prognoza', '#3498db'),
        ]
        
        for ttype, tcolor in type_info:
            var = tk.BooleanVar(value=proj_filters.get(ttype, True))
            
            def _make_cb(tt, v):
                def cb():
                    self._mp_proj_type_filters[pid][tt] = v.get()
                    _on_proj_filter_change()
                return cb
            
            tk.Checkbutton(panel, text=ttype, variable=var,
                          command=_make_cb(ttype, var),
                          font=("Arial", 9), bg="#f0f0f0",
                          fg=tcolor, selectcolor="white",
                          activebackground="#f0f0f0",
                          anchor='w').pack(fill=tk.X, padx=10)
    
    def _mp_force_lock(self, pid):
        """Wymuś przejęcie locka w multi-Gantt"""
        pname = self.project_names.get(pid, f"Projekt {pid}")
        if not messagebox.askyesno(
            "Wymuś lock",
            f"Wymusić przejęcie locka na {pname}?\n\n"
            "Inny użytkownik straci kontrolę!",
            icon='warning',
            parent=self._mp_chart_window
        ):
            return
        
        # Zwolnij obecny lock jeśli mamy
        if self.have_lock and self._locked_project_id and self._locked_project_id != pid:
            self._release_current_lock()
        
        success = self._acquire_project_lock(pid, force=True)
        if success:
            self._mp_selected_pid = pid
            self.selected_project_id = pid
            self._mp_status.config(text=f"⚡ Lock wymuszony: {pname}", fg=self.COLOR_GREEN)
        else:
            self._mp_status.config(text=f"❌ Nie udało się wymusić locka", fg=self.COLOR_RED)
        
        self._mp_build_right_panel(self._mp_chart_meta['project_ids'])
        self._create_multi_project_chart_window(self._mp_chart_meta['project_ids'], preserve_view=True)
    
    def _mp_deselect_project(self):
        """Odznacz projekt (bez zwalniania locka — sam lock trzeba zwolnić osobno)"""
        if self.have_lock and self._mp_selected_pid and self._locked_project_id == self._mp_selected_pid:
            if not messagebox.askyesno(
                "Odznacz projekt",
                "Masz aktywny lock.\nZwolnić lock przed odznaczeniem?",
                parent=self._mp_chart_window
            ):
                return
            self._release_current_lock()
            self._update_lock_buttons_state()
        
        self._mp_selected_pid = None
        self._mp_build_right_panel(self._mp_chart_meta['project_ids'])
        self._create_multi_project_chart_window(self._mp_chart_meta['project_ids'], preserve_view=True)
    
    def _save_mp_chart(self):
        """Zapisz multi-project chart do pliku"""
        if not hasattr(self, '_mp_chart_meta') or not self._mp_chart_meta:
            return
        file_path = filedialog.asksaveasfilename(
            title="Zapisz wykres jako",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("PDF", "*.pdf"), ("SVG", "*.svg")]
        )
        if file_path:
            self._mp_chart_meta['fig'].savefig(file_path, dpi=150, bbox_inches='tight')
            self._mp_status.config(text=f"💾 Zapisano: {file_path}", fg=self.COLOR_GREEN)

    def create_embedded_gantt_chart(self, preserve_view=False):
        """Utwórz wbudowany wykres Gantta używając matplotlib
        
        Args:
            preserve_view: Jeśli True, zachowa aktualne ustawienia zoom/pan
        """
        from datetime import datetime, timedelta
        
        if not MATPLOTLIB_AVAILABLE:
            messagebox.showerror("Błąd", "Matplotlib nie jest zainstalowane.\nZainstaluj: pip install matplotlib")
            return
            
        if not self.selected_project_id:
            messagebox.showwarning("Brak projektu", "Wybierz projekt najpierw!")
            return

        # ===== ZAPISZ WIDOK PRZED ODŚWIEŻENIEM =====
        saved_xlim = None
        saved_ylim = None
        if preserve_view and hasattr(self, '_chart_metadata') and self._chart_metadata:
            try:
                ax = self._chart_metadata.get('ax')
                if ax:
                    # Zapisz jako tuple (kopia wartości, nie referencja)
                    saved_xlim = tuple(ax.get_xlim())
                    saved_ylim = tuple(ax.get_ylim())
                    print(f"📊 Zapisano widok: xlim={saved_xlim}, ylim={saved_ylim}")
            except Exception as e:
                print(f"⚠️ Błąd zapisu widoku: {e}")  # Ignoruj błędy - wykres będzie z domyślnym widokiem

        try:
            self.chart_status.config(text="🔄 Tworzenie wbudowanego wykresu...", fg=self.COLOR_BLUE)
            self.root.update()
            
            # Pobierz dane timeline
            project_db = self.get_project_db_path(self.selected_project_id)
            timeline = rmm.get_stage_timeline(project_db, self.selected_project_id)
            
            if not timeline:
                self.chart_status.config(text="Brak danych do wykresu", fg=self.COLOR_RED)
                return
            
            # Sortuj etapy wg ustalonej kolejności
            timeline.sort(key=lambda s: STAGE_ORDER.get(s['stage_code'], 999))
            
            # Pobierz nazwy etapów z bazy
            con = rmm._open_rm_connection(project_db)
            stage_names = {}
            stage_milestones = {}
            cursor = con.execute("SELECT code, display_name, is_milestone FROM stage_definitions")
            for row in cursor.fetchall():
                stage_names[row['code']] = row['display_name']
                stage_milestones[row['code']] = bool(row['is_milestone'])
            
            con.close()
            
            # Przygotuj dane dla wykresu
            gantt_data = []
            all_dates = []
            
            for stage in timeline:
                stage_code = stage['stage_code']
                stage_name = stage_names.get(stage_code, stage_code)
                
                # Użyj template z timeline (recalculate_forecast)
                template_start = stage.get('template_start')
                template_end = stage.get('template_end')
                
                # FILTER: Pomiń etapy bez jakichkolwiek danych
                has_template = template_start and template_end
                has_forecast = stage.get('forecast_start') and stage.get('forecast_end')
                has_actual = any(p.get('started_at') for p in stage.get('actual_periods', []))
                
                if not has_template and not has_forecast and not has_actual:
                    print(f"🚫 [matplotlib] Pomijam etap {stage_code} - brak danych")
                    continue
                
                # Milestone bez ustawionej daty → pokaż nazwę ale bez pasków
                is_ms = stage_milestones.get(stage_code, False)
                ms_has_date = has_actual or has_template or has_forecast
                if is_ms and not ms_has_date:
                    print(f"⭕ [matplotlib] Milestone {stage_code} bez daty - pusty wiersz")
                    gantt_data.append({
                        'task': f"⭕ {stage_name}",
                        'stage_code': stage_code,
                        'start': None,
                        'end': None,
                        'type': 'Milestone',
                        'color': '#bdc3c7'
                    })
                    continue
                
                # Dla milestone z datą → actual LUB template (bez sztucznej prognozy)
                if is_ms:
                    ms_date_shown = False
                    for i, period in enumerate(stage.get('actual_periods', [])):
                        if period.get('started_at'):
                            start_date = datetime.strptime(period['started_at'][:10], '%Y-%m-%d')
                            end_date_str = period.get('ended_at', period['started_at'])
                            end_date = datetime.strptime(end_date_str[:10], '%Y-%m-%d')
                            start_date, end_date = self._ensure_min_1day_dt(start_date, end_date)
                            gantt_data.append({
                                'task': f"[M] {stage_name}",
                                'stage_code': stage_code,
                                'start': start_date,
                                'end': end_date,
                                'type': 'Milestone',
                                'color': '#2ecc71'
                            })
                            all_dates.extend([start_date, end_date])
                            ms_date_shown = True
                    if not ms_date_shown and has_template:
                        tpl_start = datetime.strptime(template_start[:10], '%Y-%m-%d')
                        tpl_end = datetime.strptime(template_end[:10], '%Y-%m-%d')
                        tpl_start, tpl_end = self._ensure_min_1day_dt(tpl_start, tpl_end)
                        gantt_data.append({
                            'task': f"[M] {stage_name}",
                            'stage_code': stage_code,
                            'start': tpl_start,
                            'end': tpl_end,
                            'type': 'Milestone',
                            'color': '#2ecc71'
                        })
                        all_dates.extend([tpl_start, tpl_end])
                    continue
                
                print(f"✅ [matplotlib] Pokazuję etap {stage_code} (szablon={has_template}, prognoza={has_forecast}, rzeczywiste={has_actual})")
                
                # Szablon/Plan (szary) - rysuj pod spodem
                if has_template:
                    tpl_start = datetime.strptime(template_start[:10], '%Y-%m-%d')
                    tpl_end = datetime.strptime(template_end[:10], '%Y-%m-%d')
                    tpl_start, tpl_end = self._ensure_min_1day_dt(tpl_start, tpl_end)
                    gantt_data.append({
                        'task': stage_name,
                        'stage_code': stage_code,
                        'start': tpl_start,
                        'end': tpl_end,
                        'type': 'Szablon',
                        'color': '#95a5a6'  # Szary
                    })
                    all_dates.extend([tpl_start, tpl_end])
                
                # Rzeczywiste okresy
                for i, period in enumerate(stage.get('actual_periods', [])):
                    if period.get('started_at'):
                        start_date = datetime.strptime(period['started_at'][:10], '%Y-%m-%d')
                        if period.get('ended_at'):
                            end_date = datetime.strptime(period['ended_at'][:10], '%Y-%m-%d')
                        else:
                            end_date = datetime.now()
                        start_date, end_date = self._ensure_min_1day_dt(start_date, end_date)
                        
                        gantt_data.append({
                            'task': stage_name,
                            'stage_code': stage_code,
                            'start': start_date,
                            'end': end_date,
                            'type': 'Rzeczywiste',
                            'color': '#27ae60'  # Zielony
                        })
                        
                        all_dates.extend([start_date, end_date])
                
                # Prognozy
                if stage.get('forecast_start') and stage.get('forecast_end'):
                    forecast_start = datetime.strptime(stage['forecast_start'][:10], '%Y-%m-%d')
                    forecast_end = datetime.strptime(stage['forecast_end'][:10], '%Y-%m-%d')
                    forecast_start, forecast_end = self._ensure_min_1day_dt(forecast_start, forecast_end)
                    
                    gantt_data.append({
                        'task': stage_name,
                        'stage_code': stage_code,
                        'start': forecast_start,
                        'end': forecast_end,
                        'type': 'Prognoza',
                        'color': '#3498db'  # Niebieski
                    })
                    
                    all_dates.extend([forecast_start, forecast_end])
            
            if not gantt_data:
                self.chart_status.config(text="Brak okresów do wyświetlenia", fg=self.COLOR_RED)
                return
            
            # Usuń stary canvas jeśli istnieje
            # Przy preserve_view: reużyj istniejący figure+canvas (bez flashu)
            reuse_canvas = False
            if preserve_view and self.matplotlib_canvas and saved_xlim and saved_ylim:
                try:
                    fig = self.matplotlib_canvas.figure
                    fig.clear()
                    ax = fig.add_subplot(111)
                    reuse_canvas = True
                except Exception:
                    reuse_canvas = False
            
            if not reuse_canvas:
                if self.matplotlib_canvas:
                    self.matplotlib_canvas.get_tk_widget().destroy()
                if self.matplotlib_toolbar:
                    self.matplotlib_toolbar.destroy()
                
                # Utwórz nowy wykres
                fig = Figure(figsize=(12, 8), dpi=100)
                ax = fig.add_subplot(111)
            
            # Grupuj dane per task (zachowaj kolejność z timeline)
            from collections import OrderedDict
            tasks = OrderedDict()
            for item in gantt_data:
                key = item['stage_code']
                if key not in tasks:
                    tasks[key] = {'label': item['task'], 'items': []}
                tasks[key]['items'].append(item)
            
            # Rysuj paski Gantt
            y_pos = 0
            y_labels = []
            
            for stage_key, task_group in tasks.items():
                y_labels.append(task_group['label'])
                
                for item in task_group['items']:
                    # Placeholder milestone (bez daty) → tylko nazwa na osi Y, bez paska
                    if item['start'] is None:
                        continue
                    
                    duration = (item['end'] - item['start']).days
                    if duration < 1:
                        duration = 1  # Minimum 1 dzień dla widoczności
                    
                    # Różne wysokości dla różnych typów
                    if item['type'] == 'Milestone':
                        height = 0.4
                        y_offset = 0.1
                    elif item['type'] == 'Rzeczywiste':
                        height = 0.6
                        y_offset = 0
                    elif item['type'] == 'Szablon':
                        height = 0.8
                        y_offset = -0.1
                    else:  # Prognoza
                        height = 0.3
                        y_offset = 0.15
                    
                    # Dodaj pasek
                    rect = patches.Rectangle(
                        (mdates.date2num(item['start']), y_pos + y_offset),
                        duration,
                        height,
                        facecolor=item['color'],
                        alpha=0.8 if item['type'] == 'Rzeczywiste' else 0.5,
                        edgecolor='black',
                        linewidth=0.5
                    )
                    ax.add_patch(rect)
                    
                    # Dodaj tekst z datami
                    if True:
                        dur_days = int((item['end'] - item['start']).days)
                        if item['type'] == 'Milestone':
                            text_date = item['start'].strftime('%d/%m')
                        else:
                            text_date = f"{item['start'].strftime('%d/%m')}-{dur_days}-{item['end'].strftime('%d/%m')}"
                        
                        if item['type'] == 'Prognoza' or item['type'] == 'Milestone':
                            # Prognoza/Milestone: tekst NAD paskiem, kolorem paska
                            text_y = y_pos + y_offset + height + 0.05
                            text_va = 'bottom'
                            text_color = item['color']
                        elif item['type'] == 'Rzeczywiste':
                            # Rzeczywiste: tekst POD paskiem, kolorem paska
                            text_y = y_pos + y_offset - 0.05
                            text_va = 'top'
                            text_color = item['color']
                        else:
                            # Szablon: tekst na środku paska, ciemnoszary
                            text_y = y_pos + y_offset + height/2
                            text_va = 'center'
                            text_color = '#444444'
                        
                        ax.text(
                            mdates.date2num(item['start']) + duration/2, 
                            text_y,
                            text_date,
                            ha='center', va=text_va,
                            fontsize=8, color=text_color, weight='bold',
                            clip_on=False
                        )
                
                y_pos += 1
            
            # Formatowanie osi
            # Nie ustawiaj domyślnych limitów jeśli przywracamy zapisany widok (zapobiega "migotaniu")
            if not (saved_xlim and saved_ylim):
                ax.set_ylim(-0.5, len(y_labels) - 0.5)
                ax.invert_yaxis()  # Pierwszy etap na górze
            else:
                # Przywracanie widoku - ustaw od razu zapisane limity (już odwrócone)
                ax.set_ylim(saved_ylim)
            
            ax.set_yticks(range(len(y_labels)))
            ax.set_yticklabels(y_labels)
            
            # Oś X - daty
            # Nie ustawiaj domyślnych limitów jeśli przywracamy zapisany widok (zapobiega "migotaniu")
            if all_dates and not (saved_xlim and saved_ylim):
                min_date = min(all_dates)
                max_date = max(all_dates)
                ax.set_xlim(mdates.date2num(min_date - timedelta(days=5)), 
                           mdates.date2num(max_date + timedelta(days=5)))
            elif saved_xlim:
                # Przywracanie widoku - ustaw od razu zapisane limity
                ax.set_xlim(saved_xlim)
            
            # Formatowanie dat na osi X
            # Główna oś: tygodnie (poniedziałki)
            ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('W%W\n%d/%m'))
            # Pomocnicza oś: dni
            ax.xaxis.set_minor_locator(mdates.DayLocator())
            ax.xaxis.set_minor_formatter(mdates.DateFormatter('%d'))
            ax.tick_params(axis='x', which='major', labelsize=8, pad=12)
            ax.tick_params(axis='x', which='minor', labelsize=6, labelcolor='#888888')
            fig.autofmt_xdate(rotation=0, ha='center')  # Bez rotacji dla czytelności
            
            # Zaznacz weekendy (sobota/niedziela) szarym tłem
            xlim = ax.get_xlim()
            x_start = mdates.num2date(xlim[0]).replace(tzinfo=None)
            x_end = mdates.num2date(xlim[1]).replace(tzinfo=None)
            current = x_start.replace(hour=0, minute=0, second=0, microsecond=0)
            while current <= x_end:
                if current.weekday() in (5, 6):  # Sobota=5, Niedziela=6
                    ax.axvspan(mdates.date2num(current), mdates.date2num(current + timedelta(days=1)),
                              facecolor='#e0e0e0', alpha=0.4, zorder=0)
                current += timedelta(days=1)
            
            # Siatka i styling
            ax.grid(True, which='major', alpha=0.4, linewidth=0.8)
            ax.grid(True, which='minor', alpha=0.15, linewidth=0.3)
            ax.set_xlabel('Data', fontweight='bold')
            ax.set_ylabel('Etapy', fontweight='bold') 
            ax.set_title(f'Timeline {self.project_names.get(self.selected_project_id, f"Projekt {self.selected_project_id}")} {self._get_project_status_text(self.selected_project_id)}', fontweight='bold', pad=20)
            
            # Legenda
            from matplotlib.lines import Line2D
            legend_elements = [
                Line2D([0], [0], color='#95a5a6', lw=8, label='Szablon'),
                Line2D([0], [0], color='#27ae60', lw=8, label='Rzeczywiste'),
                Line2D([0], [0], color='#3498db', lw=8, label='Prognoza'),
                Line2D([0], [0], color='#2ecc71', lw=8, label='Milestone')
            ]
            ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, -0.08),
                      ncol=4, fontsize=8, frameon=False)
            
            # Dziś - pionowa czerwona linia
            today_num = mdates.date2num(datetime.now())
            ax.axvline(x=today_num, color='red', linewidth=1.5, linestyle='--', alpha=0.7, zorder=5)
            ax.text(today_num, -0.3, ' DZIŚ', color='red', fontsize=8,
                    fontweight='bold', va='bottom', ha='left', zorder=5)
            
            if reuse_canvas:
                # ===== REUSE: Przywróć widok i przerysuj bez tworzenia nowego widgetu =====
                if saved_xlim and saved_ylim:
                    ax.set_xlim(saved_xlim)
                    ax.set_ylim(saved_ylim)
                self.matplotlib_canvas.draw_idle()
                # Zaktualizuj toolbar home
                try:
                    self.matplotlib_toolbar.update()
                    self.matplotlib_toolbar.push_current()
                except Exception:
                    pass
            else:
                # ===== NOWY CANVAS: Utwórz od zera =====
                self.matplotlib_canvas = FigureCanvasTkAgg(fig, self.embedded_chart_frame)
                self.matplotlib_canvas.draw()
                self.matplotlib_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
                
                # Toolbar z narzędziami (zoom, pan, save)
                self.matplotlib_toolbar = NavigationToolbar2Tk(self.matplotlib_canvas, self.embedded_chart_frame)
                self.matplotlib_toolbar.update()
                
                # Nadpisz przycisk Home w toolbarze - reset widoku wykresu
                # Przyciski toolbar są bindowane do metod w momencie tworzenia,
                # więc samo nadpisanie self.home nie działa. Trzeba podmienić command na widgecie.
                home_replaced = False
                # Metoda 1: matplotlib 3.x trzyma przyciski w _buttons dict
                if hasattr(self.matplotlib_toolbar, '_buttons'):
                    for name, btn in self.matplotlib_toolbar._buttons.items():
                        if name.lower() == 'home':
                            btn.config(command=self._reset_chart_view)
                            home_replaced = True
                            break
                # Metoda 2: przeszukaj children toolbara - pierwszy Button to Home
                if not home_replaced:
                    for child in self.matplotlib_toolbar.winfo_children():
                        try:
                            if isinstance(child, tk.Button):
                                child.config(command=self._reset_chart_view)
                                home_replaced = True
                                break
                        except Exception:
                            pass
                
                # Legenda nawigacji pod toolbarem
                if hasattr(self, '_chart_nav_legend') and self._chart_nav_legend:
                    self._chart_nav_legend.destroy()
                self._chart_nav_legend = tk.Label(
                    self.embedded_chart_frame,
                    text="🖱 Scroll: góra/dół  |  Shift+Scroll: lewo/prawo  |  Ctrl+Scroll: zoom czasu (X)  |  Ctrl+Shift+Scroll: zoom pionu (Y)  |  Shift+LMB: pan  |  🏠 Home: reset",
                    font=("Arial", 10), fg="black", bg="#f0f0f0",
                    relief=tk.GROOVE, padx=8, pady=3
                )
                self._chart_nav_legend.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(0, 2))
            
            # ===== INTERAKTYWNA EDYCJA DAT - DRAG & RESIZE =====
            # Zapisz metadane o paskach dla drag & resize
            self._chart_metadata = {
                'y_labels': y_labels,
                'tasks': tasks,
                'gantt_data': gantt_data,
                'y_positions': {task: idx for idx, task in enumerate(y_labels)},
                'stage_names_reverse': {v: k for k, v in stage_names.items()},  # display_name -> code
                'y_to_stage_code': [key for key in tasks.keys()],  # index -> stage_code
                'ax': ax,  # Referencja do axes
                'fig': fig  # Referencja do figure
            }
            
            # Stan drag & resize
            self._drag_state = {
                'active': False,
                'stage_code': None,
                'edge': None,  # 'start' lub 'end'
                'original_date': None,
                'bar_item': None,
                'preview_line': None
            }
            
            # Event handlers dla drag & resize
            self.matplotlib_canvas.mpl_connect('button_press_event', self._on_chart_press)
            self.matplotlib_canvas.mpl_connect('button_release_event', self._on_chart_release)
            self.matplotlib_canvas.mpl_connect('motion_notify_event', self._on_chart_motion)
            
            # Double-click handler dla dialogu edycji dat
            self._dblclick_cid = self.matplotlib_canvas.mpl_connect('button_press_event', self._on_chart_dblclick)
            
            # Pan & Zoom handlers (nawigacja wykresem)
            self.matplotlib_canvas.mpl_connect('scroll_event', self._on_chart_scroll)
            self._pan_state = {'active': False, 'start_x': None, 'start_xlim': None, 'start_y': None, 'start_ylim': None}
            
            self.chart_status.config(
                text=f"✅ Wykres utworzony ({len(gantt_data)} okresów) - przeciągnij krawędzie szablonu aby zmienić daty",
                fg=self.COLOR_GREEN
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.chart_status.config(text="❌ Błąd wbudowanego wykresu", fg=self.COLOR_RED)
            messagebox.showerror("Błąd wykresu", f"Nie można utworzyć wbudowanego wykresu:\n{e}")

    def _reset_chart_view(self):
        """Reset widoku wykresu do domyślnego (dopasowanie do danych)"""
        if not hasattr(self, '_chart_metadata') or not self._chart_metadata:
            return
        try:
            ax = self._chart_metadata['ax']
            gantt_data = self._chart_metadata.get('gantt_data', [])
            y_labels = self._chart_metadata.get('y_labels', [])
            
            # Oblicz zakres dat z danych
            all_dates = []
            for item in gantt_data:
                if item.get('start'):
                    all_dates.append(item['start'])
                if item.get('end'):
                    all_dates.append(item['end'])
            
            if all_dates:
                import matplotlib.dates as mdates
                min_date = min(all_dates)
                max_date = max(all_dates)
                ax.set_xlim(mdates.date2num(min_date - timedelta(days=5)),
                           mdates.date2num(max_date + timedelta(days=5)))
            
            if y_labels:
                ax.set_ylim(-0.5, len(y_labels) - 0.5)
                ax.invert_yaxis()
            
            self.matplotlib_canvas.draw_idle()
            self.status_bar.config(
                text="🏠 Widok wykresu zresetowany",
                fg=self.COLOR_GREEN
            )
        except Exception as e:
            print(f"⚠️ Błąd resetu widoku: {e}")

    def save_embedded_chart(self):
        """Zapisz wbudowany wykres matplotlib do pliku"""
        from datetime import datetime
        
        if not MATPLOTLIB_AVAILABLE:
            messagebox.showerror("Błąd", "Matplotlib nie jest dostępne")
            return
            
        if not self.matplotlib_canvas:
            messagebox.showwarning("Brak wykresu", "Najpierw utwórz wbudowany wykres")
            return
        
        # Dialog zapisu
        file_path = filedialog.asksaveasfilename(
            title="Zapisz wykres jako",
            defaultextension=".png",
            filetypes=[
                ("Pliki PNG", "*.png"),
                ("Pliki PDF", "*.pdf"),
                ("Pliki SVG", "*.svg"),
                ("Wszystkie pliki", "*.*")
            ],
            initialfile=f"gantt_embedded_projekt_{self.selected_project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        )
        
        if not file_path:
            return
        
        try:
            # Zapisz wykres
            figure = self.matplotlib_canvas.figure
            figure.savefig(file_path, dpi=300, bbox_inches='tight', facecolor='white')
            
            self.status_bar.config(
                text=f"✅ Wykres zapisany: {os.path.basename(file_path)}",
                fg=self.COLOR_GREEN
            )
            
            # Zapytaj czy otworzyć
            if messagebox.askyesno("Sukces", f"Wykres zapisany!\n{file_path}\n\nCzy otworzyć plik?"):
                import platform
                import subprocess
                
                system = platform.system()
                if system == 'Windows':
                    import os
                    os.startfile(file_path)
                elif system == 'Darwin':  # macOS
                    subprocess.run(['open', file_path], check=True)
                else:  # Linux
                    subprocess.run(['xdg-open', file_path], check=True)
                
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można zapisać wykresu:\n{e}")

    def _find_bar_at_position(self, x_data, y_data, tolerance_days=3):
        """
        Znajdź pasek szablonu pod kursorem i określ czy kursor jest nad krawędzią
        
        Args:
            x_data: Pozycja X w jednostkach daty (matplotlib date num)
            y_data: Pozycja Y (indeks etapu)
            tolerance_days: Tolerancja w dniach dla detekcji krawędzi
            
        Returns:
            (stage_code, edge, bar_item) gdzie:
            - stage_code: kod etapu lub None
            - edge: 'start', 'end' lub None (None = środek paska)
            - bar_item: słownik z danymi paska
        """
        if not hasattr(self, '_chart_metadata'):
            return None, None, None
        
        # Znajdź etap na podstawie Y
        y_idx = round(y_data)
        if y_idx < 0 or y_idx >= len(self._chart_metadata['y_labels']):
            return None, None, None
        
        task_name = self._chart_metadata['y_labels'][y_idx]
        
        # Pobierz stage_code z mapy y_to_stage_code
        y_to_sc = self._chart_metadata.get('y_to_stage_code', [])
        if y_idx < len(y_to_sc):
            stage_code = y_to_sc[y_idx]
        else:
            display_name = task_name.replace('[M] ', '').replace('⭕ ', '')
            stage_code = self._chart_metadata['stage_names_reverse'].get(display_name)
        
        if not stage_code:
            return None, None, None
        
        # Znajdź paski dla tego etapu
        task_group = self._chart_metadata['tasks'].get(stage_code)
        items = task_group['items'] if task_group else []
        
        # Konwertuj x_data (matplotlib date num) na datetime
        import matplotlib.dates as mdates
        x_datetime = mdates.num2date(x_data).replace(tzinfo=None)
        
        # Szukaj paska szablonu lub milestone
        for item in items:
            if item['type'] not in ('Szablon', 'Milestone') or item['start'] is None:
                continue
            
            # Milestone: tolerancja na kliknięcie w punkt (± tolerance_days)
            if item['type'] == 'Milestone':
                if abs(x_datetime - item['start']) <= timedelta(days=tolerance_days):
                    return stage_code, 'move', item  # Milestone zawsze w trybie move
                continue
            
            # Sprawdź czy kursor jest w zakresie paska
            if item['start'] <= x_datetime <= item['end']:
                # Tolerancja proporcjonalna: max 25% długości paska z każdej strony,
                # ale nie więcej niż tolerance_days i nie mniej niż 0.5 dnia
                bar_duration = (item['end'] - item['start']).total_seconds() / 86400.0
                edge_tol = max(0.5, min(tolerance_days, bar_duration * 0.25))
                edge_tolerance = timedelta(days=edge_tol)
                
                if abs(x_datetime - item['start']) <= edge_tolerance:
                    return stage_code, 'start', item
                elif abs(x_datetime - item['end']) <= edge_tolerance:
                    return stage_code, 'end', item
                else:
                    return stage_code, None, item  # Środek paska
        
        return None, None, None

    def _on_chart_motion(self, event):
        """Obsługa ruchu myszy - zmiana kursora, preview drag, pan wykresu"""
        if not hasattr(self, '_chart_metadata'):
            return
        
        # ── PAN: przesuwanie wykresu (Shift+LMB) ──
        if hasattr(self, '_pan_state') and self._pan_state.get('active'):
            if event.x is None or event.y is None:
                return
            ax = self._chart_metadata['ax']
            
            # Przelicz przesunięcie pikselowe na współrzędne danych
            # (pixel coords są stabilne - nie zmieniają się przy przesuwaniu)
            old_xlim = self._pan_state['start_xlim']
            old_ylim = self._pan_state['start_ylim']
            
            # Rozmiar osi w pikselach
            bbox = ax.get_window_extent()
            
            # Przesunięcie w pikselach
            dpx = event.x - self._pan_state['start_px']
            dpy = event.y - self._pan_state['start_py']
            
            # Zamiana pikseli na jednostki danych
            dx_data = dpx * (old_xlim[1] - old_xlim[0]) / bbox.width
            dy_data = dpy * (old_ylim[1] - old_ylim[0]) / bbox.height
            
            ax.set_xlim(old_xlim[0] - dx_data, old_xlim[1] - dx_data)
            ax.set_ylim(old_ylim[0] - dy_data, old_ylim[1] - dy_data)
            
            self.matplotlib_canvas.draw_idle()
            return
        
        if event.inaxes is None:
            return
        
        # Bez locka nie pokazuj kursora edycji (chyba że drag jest aktywny)
        if not self.have_lock and not self._drag_state.get('active'):
            self.matplotlib_canvas.get_tk_widget().config(cursor='')
            return
        
        # Jeśli trwa drag - aktualizuj preview
        if self._drag_state['active']:
            import matplotlib.dates as mdates
            
            # Nowa data pod kursorem
            new_date = mdates.num2date(event.xdata).replace(tzinfo=None)
            edge = self._drag_state['edge']
            bar_item = self._drag_state['bar_item']
            
            # Aktualizuj linię preview
            ax = self._chart_metadata['ax']
            
            # Usuń stare linie preview
            if self._drag_state['preview_line']:
                try:
                    if isinstance(self._drag_state['preview_line'], list):
                        for line in self._drag_state['preview_line']:
                            line.remove()
                    else:
                        self._drag_state['preview_line'].remove()
                except Exception:
                    pass
            
            if edge == 'move':
                # Tryb przesuwania - pokaż dwie linie (nowy początek i nowy koniec)
                anchor = self._drag_state['drag_anchor_x']
                delta = new_date - anchor
                new_start = bar_item['start'] + delta
                new_end = bar_item['end'] + delta
                
                line1 = ax.axvline(x=mdates.date2num(new_start), color='#e67e22', linewidth=2, linestyle='--', alpha=0.7, zorder=1000)
                line2 = ax.axvline(x=mdates.date2num(new_end), color='#e67e22', linewidth=2, linestyle='--', alpha=0.7, zorder=1000)
                self._drag_state['preview_line'] = [line1, line2]
                
                duration = (bar_item['end'] - bar_item['start']).days
                self.status_bar.config(
                    text=f"🖱️ Przesuwanie: {self._drag_state['stage_code']} → {new_start.strftime('%d-%m-%Y')} — {new_end.strftime('%d-%m-%Y')} ({duration}d)",
                    fg=self.COLOR_BLUE
                )
            else:
                # Tryb resize - jedna linia
                self._drag_state['preview_line'] = ax.axvline(
                    x=mdates.date2num(new_date),
                    color='red',
                    linewidth=2,
                    linestyle='--',
                    alpha=0.7,
                    zorder=1000
                )
                edge_label = "Początek" if edge == 'start' else "Koniec"
                self.status_bar.config(
                    text=f"🖱️ Przeciąganie: {self._drag_state['stage_code']} - {edge_label} → {new_date.strftime('%d-%m-%Y')}",
                    fg=self.COLOR_BLUE
                )
            
            # Odśwież canvas
            self.matplotlib_canvas.draw_idle()
            return
        
        # Normalne hover - zmiana kursora przy krawędziach
        stage_code, edge, bar_item = self._find_bar_at_position(event.xdata, event.ydata)
        
        if edge in ['start', 'end']:
            # Kursor nad krawędzią - resize cursor
            self.matplotlib_canvas.get_tk_widget().config(cursor='sb_h_double_arrow')
            edge_label = "początek" if edge == 'start' else "koniec"
            self.status_bar.config(
                text=f"🖱️ Przeciągnij aby zmienić {edge_label} szablonu: {stage_code}",
                fg=self.COLOR_BLUE
            )
        elif bar_item and bar_item['type'] == 'Szablon':
            # Kursor nad środkiem paska - move cursor
            self.matplotlib_canvas.get_tk_widget().config(cursor='fleur')
            self.status_bar.config(
                text=f"🖱️ Przeciągnij aby przesunąć cały etap: {stage_code}",
                fg=self.COLOR_BLUE
            )
        elif bar_item and bar_item['type'] == 'Milestone':
            # Milestone - move cursor
            self.matplotlib_canvas.get_tk_widget().config(cursor='fleur')
            self.status_bar.config(
                text=f"🖱️ Przeciągnij aby przesunąć milestone: {stage_code}",
                fg=self.COLOR_BLUE
            )
        else:
            # Kursor poza paskami
            self.matplotlib_canvas.get_tk_widget().config(cursor='')
            if not self._drag_state['active']:
                self.status_bar.config(
                    text=f"✅ Wykres gotowy | Shift+mysz: przesuwanie | Ctrl+scroll: zoom czasu | Scroll: zoom pion | 🏠 reset widoku",
                    fg=self.COLOR_GREEN
                )

    def _on_chart_scroll(self, event):
        """Obsługa scrolla na wykresie:
        - Scroll: pan góra/dół (Y)
        - Shift+scroll: pan lewo/prawo (X)
        - Ctrl+scroll: zoom osi czasu (X)
        - Ctrl+Shift+scroll: zoom pionu (Y)
        """
        if event.inaxes is None or not hasattr(self, '_chart_metadata'):
            return
        
        ax = self._chart_metadata['ax']
        
        # Kierunek: scroll up = zoom in, scroll down = zoom out
        if event.button == 'up':
            scale_factor = 0.85  # zoom in
        elif event.button == 'down':
            scale_factor = 1.15  # zoom out
        else:
            return
        
        has_ctrl = event.key == 'control' or (event.key and 'ctrl' in event.key)
        has_shift = event.key == 'shift' or (event.key and 'shift' in event.key)
        
        if has_ctrl and has_shift:
            # Ctrl+Shift+scroll: zoom pionu (Y) - centrowany na pozycji kursora
            ylim = ax.get_ylim()
            y_center = event.ydata
            new_height = (ylim[1] - ylim[0]) * scale_factor
            ax.set_ylim(y_center - new_height * (y_center - ylim[0]) / (ylim[1] - ylim[0]),
                        y_center + new_height * (ylim[1] - y_center) / (ylim[1] - ylim[0]))
            self.matplotlib_canvas.draw_idle()
        elif has_ctrl:
            # Ctrl+scroll: zoom osi czasu (X) - centrowany na pozycji kursora
            xlim = ax.get_xlim()
            x_center = event.xdata
            new_width = (xlim[1] - xlim[0]) * scale_factor
            ax.set_xlim(x_center - new_width * (x_center - xlim[0]) / (xlim[1] - xlim[0]),
                        x_center + new_width * (xlim[1] - x_center) / (xlim[1] - xlim[0]))
            self.matplotlib_canvas.draw_idle()
        elif has_shift:
            # Shift+scroll: pan osi czasu (przesuwanie w lewo/prawo)
            xlim = ax.get_xlim()
            x_range = xlim[1] - xlim[0]
            shift = x_range * 0.1 * (1 if event.button == 'down' else -1)
            ax.set_xlim(xlim[0] + shift, xlim[1] + shift)
            self.matplotlib_canvas.draw_idle()
        else:
            # Scroll bez modyfikatora: pan góra/dół (Y)
            ylim = ax.get_ylim()
            y_range = ylim[1] - ylim[0]
            shift = y_range * 0.1 * (1 if event.button == 'up' else -1)
            ax.set_ylim(ylim[0] + shift, ylim[1] + shift)
            self.matplotlib_canvas.draw_idle()

    def _on_chart_dblclick(self, event):
        """Obsługa podwójnego kliknięcia - otwórz dialog edycji dat"""
        if event.dblclick != True or event.inaxes is None or not hasattr(self, '_chart_metadata'):
            return
        
        # Sprawdź lock
        if not self.have_lock:
            self.status_bar.config(
                text=f"🔒 Edycja wykresu wymaga przejęcia locka",
                fg=self.COLOR_RED
            )
            return
        
        # Sprawdź uprawnienia
        if not self._has_permission('can_edit_dates'):
            self.status_bar.config(
                text=f"🚫 Brak uprawnień do edycji dat (rola: {self.current_user_role})",
                fg=self.COLOR_RED
            )
            return
        
        stage_code, edge, bar_item = self._find_bar_at_position(event.xdata, event.ydata)
        
        if not stage_code or not bar_item:
            return
        
        if bar_item['type'] not in ('Szablon', 'Milestone'):
            return
        
        # Zablokuj drag z tego kliknięcia
        self._drag_state['active'] = False
        
        self._open_stage_edit_dialog(stage_code)

    def _open_stage_edit_dialog(self, stage_code, parent=None):
        """Dialog edycji dat szablonu i prognozy dla pojedynczego etapu"""
        if parent is None:
            parent = self.root
        try:
            forecast = rmm.recalculate_forecast(
                self.get_project_db_path(self.selected_project_id), self.selected_project_id
            )
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można załadować dat:\n{e}")
            return
        
        if stage_code not in forecast:
            messagebox.showerror("Błąd", f"Nie znaleziono etapu {stage_code} w prognozie")
            return
        
        fc = forecast[stage_code]
        project_name = self.project_names.get(self.selected_project_id, f"Projekt {self.selected_project_id}")
        
        # Status etapu
        if fc.get('is_actual'):
            status_text = "✔️ Zakończony"
            status_color = self.COLOR_GREEN
        elif fc.get('is_active'):
            # Oblicz ile dni trwa
            try:
                from datetime import datetime as _dt
                fs = fc.get('forecast_start')
                if fs:
                    start_dt = _dt.fromisoformat(fs)
                    days_active = (_dt.now() - start_dt).days
                    status_text = f"● TRWA ({days_active} dni)"
                else:
                    status_text = "● TRWA"
            except Exception:
                status_text = "● TRWA"
            status_color = self.COLOR_BLUE
        else:
            status_text = "○ Nieaktywny"
            status_color = 'gray'
        
        # Odchylenie
        variance = fc.get('variance_days', 0)
        if variance > 0:
            var_text = f"+{variance} dni"
            var_color = self.COLOR_RED
        elif variance < 0:
            var_text = f"{variance} dni"
            var_color = self.COLOR_GREEN
        else:
            var_text = "0 dni"
            var_color = 'gray'
        
        dialog = tk.Toplevel(parent)
        dialog.transient(parent)
        dialog.focus_set()
        dialog.title(f"Edycja dat etapu - {stage_code} - {project_name}")
        dialog.resizable(True, True)
        
        # Rozmiar i pozycja - centruj na rodzicu (wykresie)
        w, h = 900, 420
        dialog.update_idletasks()
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw // 2) - (w // 2)
            y = py + (ph // 2) - (h // 2)
        except Exception:
            x = (dialog.winfo_screenwidth() // 2) - (w // 2)
            y = (dialog.winfo_screenheight() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        
        # ===== HEADER (jak główne okno) =====
        header_frame = tk.Frame(dialog, bg=self.COLOR_TOPBAR, height=50)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        tk.Label(
            header_frame,
            text=f"📅 EDYCJA DAT SZABLONU I PROGNOZY",
            bg=self.COLOR_TOPBAR, fg="white",
            font=("Arial", 13, "bold"),
            padx=15
        ).pack(side=tk.LEFT, fill=tk.Y)
        
        # ===== INFO BAR =====
        info_frame = tk.Frame(dialog, bg="#ecf0f1", pady=6)
        info_frame.pack(fill=tk.X)
        
        tk.Label(
            info_frame, text=f"  Projekt: {project_name}",
            bg="#ecf0f1", font=self.FONT_BOLD, fg=self.COLOR_TEXT_DARK, anchor='w'
        ).pack(side=tk.LEFT, padx=10)
        
        tk.Label(
            info_frame, text=f"Etap: {stage_code}",
            bg="#ecf0f1", font=self.FONT_BOLD, fg=self.COLOR_BLUE, anchor='w'
        ).pack(side=tk.LEFT, padx=15)
        
        tk.Label(
            info_frame, text=status_text,
            bg="#ecf0f1", font=self.FONT_BOLD, fg=status_color
        ).pack(side=tk.LEFT, padx=15)
        
        tk.Label(
            info_frame, text=f"Odchylenie: {var_text}",
            bg="#ecf0f1", font=self.FONT_BOLD, fg=var_color
        ).pack(side=tk.LEFT, padx=15)
        
        # ===== TABELA DAT =====
        table_frame = tk.Frame(dialog, padx=15, pady=15)
        table_frame.pack(fill=tk.BOTH, expand=True)
        
        # Konfiguracja kolumn - równomierne rozłożenie
        for col in range(4):
            table_frame.columnconfigure(col, weight=1)
        
        # Nagłówki
        headers = [
            ("Szablon Start", self.COLOR_TOPBAR),
            ("Szablon Koniec", self.COLOR_TOPBAR),
            ("Prognoza Start", "#7f8c8d"),
            ("Prognoza Koniec", "#7f8c8d"),
        ]
        for col, (header_text, bg_color) in enumerate(headers):
            tk.Label(
                table_frame, text=header_text,
                font=self.FONT_BOLD, bg=bg_color, fg="white",
                relief=tk.RAISED, padx=12, pady=6
            ).grid(row=0, column=col, sticky="ew", padx=2, pady=(0, 5))
        
        # Szablon Start - edytowalny
        template_start_entry = tk.Entry(
            table_frame, width=16, font=("Arial", 12),
            justify='center', relief=tk.SOLID, bd=1
        )
        template_start_entry.insert(0, self.format_date_ddmmyyyy(fc.get('template_start')) or '')
        template_start_entry.grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        
        # Szablon Koniec - edytowalny
        template_end_entry = tk.Entry(
            table_frame, width=16, font=("Arial", 12),
            justify='center', relief=tk.SOLID, bd=1
        )
        template_end_entry.insert(0, self.format_date_ddmmyyyy(fc.get('template_end')) or '')
        template_end_entry.grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        
        # Prognoza Start - nieedytowalna
        fs_text = self.format_date_ddmmyyyy(fc.get('forecast_start')) or '—'
        tk.Label(
            table_frame, text=fs_text,
            font=("Arial", 12), bg="#f0f0f0", fg="#555555",
            relief=tk.SUNKEN, padx=8, pady=4
        ).grid(row=1, column=2, padx=2, pady=2, sticky="ew")
        
        # Prognoza Koniec - nieedytowalna
        fe_text = self.format_date_ddmmyyyy(fc.get('forecast_end')) or '—'
        tk.Label(
            table_frame, text=fe_text,
            font=("Arial", 12), bg="#f0f0f0", fg="#555555",
            relief=tk.SUNKEN, padx=8, pady=4
        ).grid(row=1, column=3, padx=2, pady=2, sticky="ew")
        
        template_start_entry.focus()
        template_start_entry.select_range(0, tk.END)
        
        # ===== SEKCJA PRACOWNIKÓW =====
        staff_frame = tk.Frame(dialog, padx=15, pady=5)
        staff_frame.pack(fill=tk.X)
        
        # Pobierz przypisanych pracowników
        try:
            assigned_staff = rmm.get_stage_assigned_staff(
                self.get_project_db_path(self.selected_project_id),
                self.rm_master_db_path,
                self.selected_project_id,
                stage_code
            )
            staff_count = len(assigned_staff)
        except Exception:
            assigned_staff = []
            staff_count = 0
        
        staff_btn_text = f"👷 Pracownicy ({staff_count})" if staff_count > 0 else "👷 Pracownicy"
        staff_btn_bg = self.COLOR_GREEN if staff_count > 0 else "#95a5a6"
        
        def open_staff():
            self.assign_staff_dialog(stage_code)
        
        tk.Button(
            staff_frame,
            text=staff_btn_text,
            command=open_staff,
            bg=staff_btn_bg,
            fg="white",
            font=self.FONT_BOLD,
            padx=10,
            pady=3,
            cursor='hand2'
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        # Wyświetl listę przypisanych pracowników
        if staff_count > 0:
            staff_info = []
            for s in assigned_staff:
                name = s['employee_name']
                category = s['category']
                preferred = rmm.STAGE_TO_PREFERRED_CATEGORY.get(stage_code, [])
                if category not in preferred:
                    staff_info.append(f"⚠️ {name} ({category})")
                else:
                    staff_info.append(f"👤 {name} ({category})")
            
            tk.Label(
                staff_frame,
                text=", ".join(staff_info),
                font=self.FONT_SMALL,
                fg="gray",
                wraplength=600,
                justify=tk.LEFT
            ).pack(side=tk.LEFT, padx=5)
        
        # ===== SEKCJA NOTATEK =====
        notes_frame = tk.Frame(dialog, padx=15, pady=5)
        notes_frame.pack(fill=tk.X)
        
        # Pobierz statystyki notatek
        try:
            notes_stats = rmm.get_topic_stats(
                self.get_project_db_path(self.selected_project_id),
                self.selected_project_id,
                stage_code
            )
            topic_count = notes_stats['total_topics']
            notes_count = notes_stats['total_notes']
            alarms_count = notes_stats['active_alarms']
        except Exception:
            topic_count = 0
            notes_count = 0
            alarms_count = 0
        
        notes_btn_text = "📝"
        if topic_count > 0 or notes_count > 0:
            notes_btn_text = f"📝 {topic_count}T/{notes_count}N"
        if alarms_count > 0:
            notes_btn_text += f" ⏰{alarms_count}"
        
        def open_notes():
            self.show_notes_window(stage_code)
        
        tk.Button(
            notes_frame,
            text=notes_btn_text,
            command=open_notes,
            bg=self.COLOR_PURPLE if topic_count > 0 else "#95a5a6",
            fg="white",
            font=self.FONT_BOLD,
            padx=10,
            pady=3,
            cursor='hand2'
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        # Podgląd 2 pierwszych tematów
        if topic_count > 0:
            try:
                _db_path = self.get_project_db_path(self.selected_project_id)
                topics_preview = rmm.get_topics(_db_path, self.selected_project_id, stage_code)[:2]
                for tp in topics_preview:
                    pri_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(tp['priority'], "⚪")
                    title_text = tp['title'][:60]
                    if len(tp['title']) > 60:
                        title_text += "…"
                    topic_lbl = tk.Label(
                        notes_frame,
                        text=f" {pri_icon} #{tp['topic_number']} {title_text} ",
                        bg="#f0f4ff",
                        fg="#2c3e50",
                        font=("Arial", 8),
                        cursor="hand2",
                        padx=4,
                        pady=1,
                        relief=tk.FLAT
                    )
                    topic_lbl.pack(side=tk.LEFT, padx=2)
                    topic_lbl.bind("<Button-1>", lambda e, sc=stage_code: open_notes())
            except Exception:
                pass
            
            if topic_count > 0 or notes_count > 0:
                tk.Label(
                    notes_frame,
                    text=f"({topic_count} tematów, {notes_count} notatek)",
                    font=("Arial", 8),
                    fg="gray"
                ).pack(side=tk.LEFT, padx=5)
        
        # ===== PRZYCISKI (jak główne okno) =====
        btn_frame = tk.Frame(dialog, bg="#ecf0f1", pady=8)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        def save():
            ts = template_start_entry.get().strip()
            te = template_end_entry.get().strip()
            
            valid_s, ts_iso = self.validate_and_convert_date(ts)
            if not valid_s:
                messagebox.showerror("Błąd walidacji", ts_iso, parent=dialog)
                return
            valid_e, te_iso = self.validate_and_convert_date(te)
            if not valid_e:
                messagebox.showerror("Błąd walidacji", te_iso, parent=dialog)
                return
            
            if ts_iso and te_iso and te_iso < ts_iso:
                messagebox.showerror("Błąd logiczny",
                    f"Data końcowa ({te}) nie może być wcześniejsza\nniż data początkowa ({ts})!",
                    parent=dialog)
                return
            
            try:
                _pdb = self.get_project_db_path(self.selected_project_id)
                con = rmm._open_rm_connection(_pdb, row_factory=False)
                con.execute("""
                    UPDATE stage_schedule
                    SET template_start = ?, template_end = ?
                    WHERE project_stage_id = (
                        SELECT id FROM project_stages
                        WHERE project_id = ? AND stage_code = ?
                    )
                """, (ts_iso, te_iso, self.selected_project_id, stage_code))
                con.commit()
                con.close()
                
                rmm.recalculate_forecast(_pdb, self.selected_project_id)
                dialog.destroy()
                self.create_embedded_gantt_chart(preserve_view=True)
                
                # Odśwież multi-Gantt jeśli jest otwarty
                if self._is_mp_chart_open():
                    try:
                        self._create_multi_project_chart_window(
                            self._mp_chart_meta['project_ids'], preserve_view=True)
                    except Exception:
                        pass
                
                self.status_bar.config(
                    text=f"✅ Zaktualizowano {stage_code}: {ts} — {te}",
                    fg=self.COLOR_GREEN
                )
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można zapisać dat:\n{e}", parent=dialog)
        
        tk.Button(
            btn_frame, text="💾 OK", command=save,
            bg=self.COLOR_GREEN, fg="white",
            font=self.FONT_BOLD, padx=25, pady=6,
            relief=tk.RAISED, cursor='hand2'
        ).pack(side=tk.LEFT, padx=(15, 5))
        
        tk.Button(
            btn_frame, text="❌ Anuluj", command=dialog.destroy,
            bg=self.COLOR_RED, fg="white",
            font=self.FONT_BOLD, padx=25, pady=6,
            relief=tk.RAISED, cursor='hand2'
        ).pack(side=tk.LEFT, padx=5)
        
        def go_to_timeline():
            dialog.destroy()
            # Przełącz na zakładkę Oś czasu
            try:
                self.tab_control.select(self.timeline_tab)
            except Exception:
                pass
            # Odśwież oś czasu i przewiń do etapu
            self.refresh_timeline()
            self.root.after(200, lambda: self._scroll_timeline_to_stage(stage_code))
        
        tk.Button(
            btn_frame, text="📅 Oś czasu", command=go_to_timeline,
            bg=self.COLOR_BLUE, fg="white",
            font=self.FONT_BOLD, padx=25, pady=6,
            relief=tk.RAISED, cursor='hand2'
        ).pack(side=tk.LEFT, padx=15)
        
        tk.Label(
            btn_frame, text="Format dat: DD-MM-YYYY (np. 01-04-2026)",
            font=self.FONT_SMALL, fg="gray", bg="#ecf0f1"
        ).pack(side=tk.RIGHT, padx=15)
        
        dialog.bind('<Return>', lambda e: save())
        dialog.bind('<Escape>', lambda e: dialog.destroy())

    def _on_chart_press(self, event):
        """Obsługa kliknięcia - rozpoczęcie drag, pan (Shift+LMB) lub otwarcie dialogu"""
        # Ignoruj podwójne kliknięcia - obsługuje je _on_chart_dblclick
        if event.dblclick:
            return
        if event.inaxes is None or not hasattr(self, '_chart_metadata'):
            return
        
        # Shift + lewy przycisk => PAN (dostępny zawsze, bez locka)
        if event.button == 1 and event.key == 'shift':
            if not hasattr(self, '_pan_state'):
                self._pan_state = {}
            self._pan_state['active'] = True
            self._pan_state['start_px'] = event.x   # pixel coords - stabilne
            self._pan_state['start_py'] = event.y
            ax = self._chart_metadata['ax']
            self._pan_state['start_xlim'] = ax.get_xlim()
            self._pan_state['start_ylim'] = ax.get_ylim()
            self.matplotlib_canvas.get_tk_widget().config(cursor='fleur')
            return
        
        # Sprawdź lock (tylko lewy przycisk bez Shift = edycja pasków)
        if not self.have_lock:
            self.status_bar.config(
                text=f"🔒 Edycja wymaga locka | Shift+mysz: przesuwanie | Ctrl+scroll: zoom",
                fg=self.COLOR_RED
            )
            return
        
        # Sprawdź uprawnienia
        if not self._has_permission('can_edit_dates'):
            self.status_bar.config(
                text=f"🚫 Brak uprawnień do edycji dat (rola: {self.current_user_role})",
                fg=self.COLOR_RED
            )
            return
        
        stage_code, edge, bar_item = self._find_bar_at_position(event.xdata, event.ydata)
        
        if not stage_code or not bar_item:
            return
        
        if bar_item['type'] not in ('Szablon', 'Milestone'):
            self.status_bar.config(
                text=f"ℹ️ Można edytować tylko paski szablonu i milestone",
                fg=self.COLOR_BLUE
            )
            return
        
        # Milestone zawsze w trybie move
        if bar_item['type'] == 'Milestone':
            edge = 'move'
        
        if edge in ['start', 'end']:
            # Kliknięto krawędź - rozpocznij resize
            self._drag_state['active'] = True
            self._drag_state['stage_code'] = stage_code
            self._drag_state['edge'] = edge
            self._drag_state['original_date'] = bar_item[edge]
            self._drag_state['bar_item'] = bar_item
            self._drag_state['drag_anchor_x'] = None
            
            edge_label = "początek" if edge == 'start' else "koniec"
            self.status_bar.config(
                text=f"🖱️ Przeciąganie {edge_label} szablonu: {stage_code}...",
                fg=self.COLOR_BLUE
            )
        else:
            # Kliknięto środek - rozpocznij przesuwanie całego przedziału
            import matplotlib.dates as mdates
            self._drag_state['active'] = True
            self._drag_state['stage_code'] = stage_code
            self._drag_state['edge'] = 'move'  # Tryb przesuwania
            self._drag_state['bar_item'] = bar_item
            self._drag_state['original_date'] = bar_item['start']
            # Zapamiętaj punkt chwytu (offset od początku paska)
            self._drag_state['drag_anchor_x'] = mdates.num2date(event.xdata).replace(tzinfo=None)
            
            self.status_bar.config(
                text=f"🖱️ Przesuwanie całego etapu: {stage_code}...",
                fg=self.COLOR_BLUE
            )

    def _on_chart_release(self, event):
        """Obsługa puszczenia przycisku myszy - zapisz nową datę lub zakończ pan"""
        # Zakończ pan
        if hasattr(self, '_pan_state') and self._pan_state.get('active'):
            self._pan_state['active'] = False
            self.matplotlib_canvas.get_tk_widget().config(cursor='')
            return
        
        if not self._drag_state['active']:
            return
        
        try:
            # Usuń linie preview
            if self._drag_state['preview_line']:
                try:
                    if isinstance(self._drag_state['preview_line'], list):
                        for line in self._drag_state['preview_line']:
                            line.remove()
                    else:
                        self._drag_state['preview_line'].remove()
                except Exception:
                    pass
                self._drag_state['preview_line'] = None
            
            # Jeśli puszczono poza wykresem, anuluj
            if event.inaxes is None or event.xdata is None:
                self.status_bar.config(
                    text="⚠️ Przeciąganie anulowane (puszczono poza wykresem)",
                    fg=self.COLOR_RED
                )
                self._drag_state['active'] = False
                self.matplotlib_canvas.draw_idle()
                return
            
            # Pobierz nową datę
            import matplotlib.dates as mdates
            new_date_raw = mdates.num2date(event.xdata).replace(tzinfo=None)
            # Zaokrąglij do najbliższego dnia (nie floor!)
            new_date = (new_date_raw + timedelta(hours=12)).replace(hour=0, minute=0, second=0)
            
            stage_code = self._drag_state['stage_code']
            edge = self._drag_state['edge']
            bar_item = self._drag_state['bar_item']
            
            _pdb = self.get_project_db_path(self.selected_project_id)
            
            if edge == 'move':
                # ===== TRYB PRZESUWANIA CAŁEGO PRZEDZIAŁU =====
                anchor = self._drag_state['drag_anchor_x']
                # Zaokrąglij anchor do dnia (tak samo jak new_date)
                anchor_day = (anchor + timedelta(hours=12)).replace(hour=0, minute=0, second=0)
                delta = new_date - anchor_day
                new_start = bar_item['start'] + delta
                new_end = bar_item['end'] + delta
                # Upewnij się, że wynik jest midnight
                new_start = new_start.replace(hour=0, minute=0, second=0)
                new_end = new_end.replace(hour=0, minute=0, second=0)
                
                new_start_iso = new_start.strftime('%Y-%m-%d')
                new_end_iso = new_end.strftime('%Y-%m-%d')
                
                con = rmm._open_rm_connection(_pdb, row_factory=False)
                con.execute("""
                    UPDATE stage_schedule
                    SET template_start = ?, template_end = ?
                    WHERE project_stage_id = (
                        SELECT id FROM project_stages
                        WHERE project_id = ? AND stage_code = ?
                    )
                """, (new_start_iso, new_end_iso, self.selected_project_id, stage_code))
                con.commit()
                con.close()
                
                rmm.recalculate_forecast(_pdb, self.selected_project_id)
                self.create_embedded_gantt_chart(preserve_view=True)
                
                # Odśwież multi-Gantt jeśli otwarty
                if self._is_mp_chart_open():
                    try:
                        self._create_multi_project_chart_window(
                            self._mp_chart_meta['project_ids'], preserve_view=True)
                    except Exception:
                        pass
                
                duration = (bar_item['end'] - bar_item['start']).days
                if bar_item['type'] == 'Milestone':
                    self.status_bar.config(
                        text=f"✅ Przesunięto milestone {stage_code}: {new_start.strftime('%d-%m-%Y')}",
                        fg=self.COLOR_GREEN
                    )
                else:
                    self.status_bar.config(
                        text=f"✅ Przesunięto {stage_code}: {new_start.strftime('%d-%m-%Y')} — {new_end.strftime('%d-%m-%Y')} ({duration}d)",
                        fg=self.COLOR_GREEN
                    )
            
            else:
                # ===== TRYB RESIZE KRAWĘDZI =====
                if edge == 'end':
                    if new_date < bar_item['start']:
                        messagebox.showerror(
                            "❌ Błąd walidacji",
                            f"Data końca ({new_date.strftime('%d-%m-%Y')}) nie może być wcześniejsza\n"
                            f"niż data początku ({bar_item['start'].strftime('%d-%m-%Y')})!"
                        )
                        self._drag_state['active'] = False
                        self.matplotlib_canvas.draw_idle()
                        return
                else:  # edge == 'start'
                    if new_date > bar_item['end']:
                        messagebox.showerror(
                            "❌ Błąd walidacji",
                            f"Data początku ({new_date.strftime('%d-%m-%Y')}) nie może być późniejsza\n"
                            f"niż data końca ({bar_item['end'].strftime('%d-%m-%Y')})!"
                        )
                        self._drag_state['active'] = False
                        self.matplotlib_canvas.draw_idle()
                        return
                
                date_iso = new_date.strftime('%Y-%m-%d')
                field_db = 'template_start' if edge == 'start' else 'template_end'
                
                con = rmm._open_rm_connection(_pdb, row_factory=False)
                con.execute(f"""
                    UPDATE stage_schedule
                    SET {field_db} = ?
                    WHERE project_stage_id = (
                        SELECT id FROM project_stages
                        WHERE project_id = ? AND stage_code = ?
                    )
                """, (date_iso, self.selected_project_id, stage_code))
                con.commit()
                con.close()
                
                rmm.recalculate_forecast(_pdb, self.selected_project_id)
                self.create_embedded_gantt_chart(preserve_view=True)
                
                # Odśwież multi-Gantt jeśli otwarty
                if self._is_mp_chart_open():
                    try:
                        self._create_multi_project_chart_window(
                            self._mp_chart_meta['project_ids'], preserve_view=True)
                    except Exception:
                        pass
                
                edge_label = "początek" if edge == 'start' else "koniec"
                self.status_bar.config(
                    text=f"✅ Zaktualizowano {edge_label} szablonu: {stage_code} → {new_date.strftime('%d-%m-%Y')}",
                    fg=self.COLOR_GREEN
                )
            
        except Exception as e:
            messagebox.showerror("❌ Błąd", f"Nie można zapisać daty:\n{e}")
        
        finally:
            # Reset stanu drag
            self._drag_state['active'] = False
            self._drag_state['stage_code'] = None
            self._drag_state['edge'] = None
            self._drag_state['original_date'] = None
            self._drag_state['bar_item'] = None
            self._drag_state['drag_anchor_x'] = None
            self.matplotlib_canvas.draw_idle()

    def edit_single_date_dialog(self, stage_code: str, field: str, current_bar_data: dict):
        """
        Dialog edycji pojedynczej daty szablonu po kliknięciu na wykresie
        
        Args:
            stage_code: Kod etapu (np. 'PROJEKT')
            field: 'start' lub 'end'
            current_bar_data: Słownik z danymi paska (start, end, type, color)
        """
        # Pobierz aktualną wartość
        current_value = current_bar_data[field]
        field_label = "Początek" if field == 'start' else "Koniec"
        
        # Okno dialogowe
        dialog = tk.Toplevel(self.root)
        dialog.transient(self.root)
        dialog.title(f"Edytuj datę szablonu - {stage_code}")
        dialog.geometry("400x200")
        dialog.resizable(False, False)
        
        # Wyśrodkuj okno
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Header
        tk.Label(
            dialog,
            text=f"📅 EDYCJA DATY SZABLONU",
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 11, "bold"),
            pady=10
        ).pack(fill=tk.X)
        
        # Frame główny
        main_frame = tk.Frame(dialog, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Info
        tk.Label(
            main_frame,
            text=f"Etap: {stage_code}",
            font=self.FONT_BOLD,
            anchor='w'
        ).pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(
            main_frame,
            text=f"Pole: {field_label} szablonu",
            font=self.FONT_DEFAULT,
            anchor='w',
            fg='gray'
        ).pack(fill=tk.X, pady=(0, 10))
        
        # Entry z datą
        tk.Label(
            main_frame,
            text="Nowa data (DD-MM-YYYY):",
            font=self.FONT_DEFAULT,
            anchor='w'
        ).pack(fill=tk.X)
        
        # Frame dla Entry + przycisk kalendarza
        date_input_frame = tk.Frame(main_frame)
        date_input_frame.pack(fill=tk.X, pady=(5, 15))
        
        date_entry = tk.Entry(date_input_frame, font=("Arial", 12), width=20)
        date_entry.insert(0, current_value.strftime('%d-%m-%Y'))
        date_entry.pack(side=tk.LEFT, padx=(0, 5))
        date_entry.focus()
        date_entry.select_range(0, tk.END)
        
        # Przycisk kalendarza
        tk.Button(
            date_input_frame,
            text="📅 Kalendarz",
            command=lambda: self.open_calendar_picker(date_entry),
            bg="#3498db",
            fg="white",
            font=self.FONT_SMALL,
            padx=8,
            pady=5
        ).pack(side=tk.LEFT)
        
        # Przyciski
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)
        
        def save_single_date():
            """Zapisz zmienioną datę"""
            new_date_str = date_entry.get().strip()
            
            # Walidacja i konwersja DD-MM-YYYY → YYYY-MM-DD (ISO)
            valid, date_iso = self.validate_and_convert_date(new_date_str)
            if not valid:
                messagebox.showerror("❌ Błąd walidacji", date_iso, parent=dialog)
                return
            
            try:
                _pdb = self.get_project_db_path(self.selected_project_id)
                con = rmm._open_rm_connection(_pdb, row_factory=False)
                
                # UPDATE tylko jednego pola (template_start lub template_end)
                field_db = 'template_start' if field == 'start' else 'template_end'
                
                con.execute(f"""
                    UPDATE stage_schedule
                    SET {field_db} = ?
                    WHERE project_stage_id = (
                        SELECT id FROM project_stages
                        WHERE project_id = ? AND stage_code = ?
                    )
                """, (date_iso, self.selected_project_id, stage_code))
                
                con.commit()
                con.close()
                
                # Przelicz prognozę
                rmm.recalculate_forecast(_pdb, self.selected_project_id)
                
                # Zamknij dialog
                dialog.destroy()
                
                # Odśwież wykres (zachowaj widok zoom/pan)
                self.create_embedded_gantt_chart(preserve_view=True)
                
                # Odśwież multi-Gantt jeśli otwarty
                if self._is_mp_chart_open():
                    try:
                        self._create_multi_project_chart_window(
                            self._mp_chart_meta['project_ids'], preserve_view=True)
                    except Exception:
                        pass
                
                self.status_bar.config(
                    text=f"✅ Zaktualizowano {field_label.lower()} szablonu dla {stage_code}: {new_date_str}",
                    fg=self.COLOR_GREEN
                )
                
            except Exception as e:
                messagebox.showerror("❌ Błąd", f"Nie można zapisać daty:\n{e}", parent=dialog)
        
        def cancel_dialog():
            dialog.destroy()
        
        # Enter = zapisz, Escape = anuluj
        dialog.bind('<Return>', lambda e: save_single_date())
        dialog.bind('<Escape>', lambda e: cancel_dialog())
        
        tk.Button(
            btn_frame,
            text="💾 Zapisz",
            command=save_single_date,
            bg=self.COLOR_GREEN,
            fg="white",
            font=self.FONT_BOLD,
            padx=15,
            pady=5,
            width=10
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="❌ Anuluj",
            command=cancel_dialog,
            bg=self.COLOR_RED,
            fg="white",
            font=self.FONT_BOLD,
            padx=15,
            pady=5,
            width=10
        ).pack(side=tk.LEFT, padx=5)

    def test_transport_components(self):
        """Test komponentów transport - sprawdź czy nie ma duplikacji"""
        if not self.selected_project_id:
            messagebox.showwarning("Test", "Wybierz projekt do testu transport")
            return
            
        try:
            print(f"\n🚛 TEST KOMPONENTÓW TRANSPORT - projekt {self.selected_project_id}")
            
            # Reset flagi
            self._transport_rendered_for_project = None
            
            # Sprawdź ile razy TRANSPORT występuje w definicjach
            project_db = self.get_project_db_path(self.selected_project_id)
            con = rmm._open_rm_connection(project_db, row_factory=False)
            
            cursor = con.execute("""
                SELECT COUNT(*) FROM project_stages 
                WHERE project_id = ? AND stage_code = 'TRANSPORT'
            """, (self.selected_project_id,))
            transport_count = cursor.fetchone()[0]
            
            print(f"   Etapów TRANSPORT w project_stages: {transport_count}")
            
            # Sprawdź w SUB_MILESTONES 
            transport_in_subs = 0
            for parent, subs in SUB_MILESTONES.items():
                if 'TRANSPORT' in subs:
                    transport_in_subs += 1
                    print(f"   TRANSPORT znaleziony jako sub-milestone w: {parent}")
            
            print(f"   TRANSPORT w SUB_MILESTONES: {transport_in_subs} wystąpień")
            
            # Test aktualnego transport_id
            current_transport = rmm.get_stage_transport_id(project_db, self.selected_project_id, 'TRANSPORT')
            print(f"   Aktualny transport_id: {current_transport}")
            
            # Test dostępnych firm
            try:
                companies = rmm.get_transports(self.rm_master_db_path, active_only=True)
                print(f"   Dostępnych firm: {len(companies)}")
            except Exception as ex:
                print(f"   ❌ Błąd ładowania firm: {ex}")
                companies = []
            
            con.close()
            
            # Informacja dla użytkownika
            message = (
                f"Test komponentów transport zakończony:\n\n"
                f"• Etapów TRANSPORT: {transport_count}\n"
                f"• Wystąpień w SUB_MILESTONES: {transport_in_subs}\n"
                f"• Aktualny transport: {current_transport}\n"
                f"• Dostępnych firm: {len(companies)}\n\n"
                f"Sprawdź konsolę dla szczegółowych logów."
            )
            
            if transport_in_subs > 1:
                message += f"\n⚠️ UWAGA: TRANSPORT renderuje się {transport_in_subs} razy!\nTo może powodować problemy z callbackami."
            
            messagebox.showinfo("🚛 Test transport", message)
            
            # Test re-renderowania - odśwież etapy
            print(f"   🔄 Test re-renderowania - wywołuję load_project_stages...")
            self.load_project_stages()
            print(f"   ✅ Re-renderowanie zakończone")
            
        except Exception as e:
            print(f"   🔥 Błąd testu transport: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("❌ Błąd testu", f"Nie można wykonać testu transport:\n{e}")

    def fix_milestone_schedule_records(self):
        """Napraw brakujące rekordy stage_schedule dla milestone'ów"""
        if not self.selected_project_id:
            messagebox.showwarning("Uwaga", "Wybierz projekt do naprawy milestone'ów")
            return
            
        try:
            print(f"\n🔧 NAPRAWA MILESTONE'ÓW - projekt {self.selected_project_id}")
            
            project_db = self.get_project_db_path(self.selected_project_id)
            con = rmm._open_rm_connection(project_db)
            
            # Znajdź milestone'y które nie mają rekordów w stage_schedule
            cursor = con.execute("""
                SELECT ps.id as project_stage_id, ps.stage_code, sd.display_name
                FROM project_stages ps
                JOIN stage_definitions sd ON ps.stage_code = sd.code
                WHERE ps.project_id = ? AND sd.is_milestone = 1
                  AND ps.id NOT IN (
                      SELECT project_stage_id FROM stage_schedule
                  )
            """, (self.selected_project_id,))
            
            missing_milestones = cursor.fetchall()
            
            if not missing_milestones:
                print(f"   ✅ Wszystkie milestone'y mają rekordy w stage_schedule")
                messagebox.showinfo("✅ OK", "Wszystkie milestone'y mają poprawne rekordy w stage_schedule")
                con.close()
                return
            
            print(f"   📋 Znaleziono {len(missing_milestones)} milestone'ów bez rekordów:")
            for row in missing_milestones:
                print(f"      • {row['stage_code']} ({row['display_name']})")
            
            # Pytaj użytkownika czy naprawić
            result = messagebox.askyesno(
                "🔧 Naprawić milestone'y?",
                f"Znaleziono {len(missing_milestones)} milestone'ów bez rekordów stage_schedule:\n\n" + 
                "\n".join([f"• {row['stage_code']} ({row['display_name']})" for row in missing_milestones]) +
                f"\n\nCzy chcesz utworzyć brakujące rekordy?\n"
                f"(Będą miały puste daty template_start/template_end)"
            )
            
            if not result:
                print(f"   ❌ Użytkownik anulował naprawę")
                con.close()
                return
            
            # Utwórz brakujące rekordy
            created_count = 0
            for row in missing_milestones:
                try:
                    con.execute("""
                        INSERT INTO stage_schedule (project_stage_id, template_start, template_end)
                        VALUES (?, NULL, NULL)
                    """, (row['project_stage_id'],))
                    created_count += 1
                    print(f"   ✅ Utworzono rekord dla {row['stage_code']}")
                except Exception as ex:
                    print(f"   ❌ Błąd tworzenia rekordu dla {row['stage_code']}: {ex}")
            
            con.commit()
            con.close()
            
            message = (
                f"Naprawa zakończona:\n\n"
                f"• Znalezionych milestone'ów: {len(missing_milestones)}\n"
                f"• Utworzonych rekordów: {created_count}\n\n"
                f"Teraz zapisy milestone'ów powinny działać poprawnie.\n"
                f"Sprawdź konsolę dla szczegółowych logów."
            )
            
            print(f"   ✅ Naprawa zakończona: {created_count}/{len(missing_milestones)} rekordów utworzonych")
            messagebox.showinfo("🔧 Naprawa zakończona", message)
            
        except Exception as e:
            print(f"   🔥 Błąd naprawy milestone'ów: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("❌ Błąd naprawy", f"Nie można naprawić milestone'ów:\n{e}")

    def create_segmented_bar_chart(self):
        """Utwórz wykres segmented bar - pipeline projektów.
        1 wiersz = 1 projekt, pasek podzielony na kolorowe segmenty etapów.
        """
        from datetime import datetime, timedelta
        
        if not PLOTLY_AVAILABLE:
            messagebox.showerror("Błąd", "Plotly nie jest zainstalowane.\nZainstaluj: pip install plotly")
            return
        
        selected_projects = self.select_multiple_projects_dialog()
        if not selected_projects:
            return
        
        try:
            self.chart_status.config(text="🔄 Tworzenie segmented bar...", fg=self.COLOR_BLUE)
            self.root.update()
            
            # Stałe kolory per etap
            stage_colors = {
                'PRZYJETY': '#27ae60', 'PROJEKT': '#3498db',
                'KOMPLETACJA': '#e74c3c', 'MONTAZ': '#f39c12',
                'ELEKTROMONTAZ': '#9b59b6', 'URUCHOMIENIE': '#1abc9c',
                'ODBIORY': '#34495e', 'POPRAWKI': '#e67e22',
                'ZAKONCZONY': '#16a085', 'WSTRZYMANY': '#95a5a6',
                'TRANSPORT': '#d35400', 'FAT': '#8e44ad',
                'ELEKTROPROJEKT': '#2980b9',
                'ODBIOR_1': '#2c3e50', 'ODBIOR_2': '#7f8c8d',
                'ODBIOR_3': '#c0392b', 'URUCHOMIENIE_U_KLIENTA': '#0e6655'
            }
            
            # ── Zbierz dane ──────────────────────────────────────────
            all_projects = []  # [{label, segments: [{code, name, start, end, color, level}]}]
            
            for project_id in selected_projects:
                project_db = self.get_project_db_path(project_id)
                timeline = rmm.get_stage_timeline(project_db, project_id)
                timeline.sort(key=lambda s: STAGE_ORDER.get(s['stage_code'], 999))
                
                con = rmm._open_rm_connection(project_db)
                stage_info = {}
                for row in con.execute("SELECT code, display_name FROM stage_definitions"):
                    stage_info[row['code']] = row['display_name']
                con.close()
                
                project_name = self.project_names.get(project_id, f"Projekt {project_id}")
                status_icon = self._get_project_status_icon(project_id)
                label = f"{status_icon} P{project_id}: {project_name}"
                
                segments = []
                for stage in timeline:
                    code = stage['stage_code']
                    name = stage_info.get(code, code)
                    color = stage_colors.get(code, '#7f8c8d')
                    
                    # Etap bez szablonu i bez rzeczywistych dat → pomiń
                    # (forecast generuje sztuczne daty typu now()+5d dla takich etapów)
                    has_tpl = stage.get('template_start') and stage.get('template_end')
                    has_act = any(p.get('started_at') for p in stage.get('actual_periods', []))
                    if not has_tpl and not has_act:
                        continue
                    
                    # Źródło dat: actual > forecast > template
                    added = False
                    for period in stage.get('actual_periods', []):
                        if period.get('started_at'):
                            s = period['started_at'][:10]
                            e = (period.get('ended_at') or datetime.now().strftime('%Y-%m-%d'))[:10]
                            s_dt = datetime.strptime(s, '%Y-%m-%d')
                            e_dt = datetime.strptime(e, '%Y-%m-%d')
                            if e_dt <= s_dt:
                                e_dt = s_dt + timedelta(days=1)
                            segments.append({
                                'code': code, 'name': name,
                                'start': s_dt, 'end': e_dt,
                                'color': color, 'source': 'actual', 'level': 0
                            })
                            added = True
                    
                    if not added:
                        # Próbuj forecast
                        fs = stage.get('forecast_start')
                        fe = stage.get('forecast_end')
                        if not fs or not fe:
                            fs = stage.get('template_start')
                            fe = stage.get('template_end')
                        if fs and fe:
                            s_dt = datetime.strptime(fs[:10], '%Y-%m-%d')
                            e_dt = datetime.strptime(fe[:10], '%Y-%m-%d')
                            if e_dt <= s_dt:
                                e_dt = s_dt + timedelta(days=1)
                            segments.append({
                                'code': code, 'name': name,
                                'start': s_dt, 'end': e_dt,
                                'color': color, 'source': 'plan', 'level': 0
                            })
                
                segments.sort(key=lambda x: x['start'])
                
                # Smart packing: przypisz level (micro-lane) dla nakładających się
                for i, seg in enumerate(segments):
                    lvl = 0
                    while True:
                        collision = False
                        for prev in segments[:i]:
                            if prev['level'] == lvl:
                                if not (seg['start'] >= prev['end'] or seg['end'] <= prev['start']):
                                    collision = True
                                    break
                        if not collision:
                            seg['level'] = lvl
                            break
                        lvl += 1
                
                max_level = max((s['level'] for s in segments), default=0)
                all_projects.append({
                    'label': label,
                    'segments': segments,
                    'max_level': max_level
                })
            
            if not all_projects:
                self.chart_status.config(text="Brak danych", fg=self.COLOR_RED)
                return
            
            # ── Rysuj wykres ─────────────────────────────────────────
            fig = go.Figure()
            
            # Oblicz pozycje Y (od dołu do góry) z dynamiczną wysokością swimlane
            SUBLANE_GAP = 0.08       # przerwa między micro-lanes

            y_positions = []  # środek etykiety
            y_labels = []
            current_y = 0.0
            
            for proj in reversed(all_projects):
                n_lanes = proj['max_level'] + 1
                # Grubość paska: pełna gdy 1 lane, cieńsza gdy więcej
                if n_lanes == 1:
                    bar_h = 0.40
                elif n_lanes == 2:
                    bar_h = 0.28
                else:
                    bar_h = 0.22
                sublane_step = bar_h + SUBLANE_GAP
                lane_height = n_lanes * sublane_step
                proj['_y_base'] = current_y
                proj['_lane_h'] = lane_height
                proj['_bar_h'] = bar_h
                proj['_sublane_step'] = sublane_step
                y_positions.append(current_y + lane_height / 2)
                y_labels.append(proj['label'])
                current_y += lane_height + 0.35  # gap między projektami
            
            y_positions.reverse()
            y_labels.reverse()
            
            # Śledź które stage_code już mają legendę
            legend_added = set()
            
            for proj in all_projects:
                base_y = proj['_y_base']
                bar_h = proj['_bar_h']
                sublane_step = proj['_sublane_step']
                
                for seg in proj['segments']:
                    # Pozycja Y: dolna krawędź prostokąta
                    y_bottom = base_y + seg['level'] * sublane_step
                    y_top = y_bottom + bar_h
                    y_center = (y_bottom + y_top) / 2
                    
                    duration_days = (seg['end'] - seg['start']).days
                    
                    # Przezroczystość: plan = przeźroczysty, actual = pełny
                    opacity = 0.45 if seg['source'] == 'plan' else 1.0
                    
                    show_legend = seg['code'] not in legend_added
                    if show_legend:
                        legend_added.add(seg['code'])
                    
                    # Prostokąt w współrzędnych danych (NIE w pikselach)
                    fig.add_shape(
                        type='rect',
                        x0=seg['start'], x1=seg['end'],
                        y0=y_bottom, y1=y_top,
                        fillcolor=seg['color'],
                        opacity=opacity,
                        line=dict(width=1, color='white'),
                        layer='above'
                    )
                    
                    # Niewidoczny trace dla hover + legenda
                    mid_date = seg['start'] + (seg['end'] - seg['start']) / 2
                    fig.add_trace(go.Scatter(
                        x=[mid_date],
                        y=[y_center],
                        mode='markers',
                        marker=dict(size=1, opacity=0),
                        name=seg['name'],
                        legendgroup=seg['code'],
                        showlegend=show_legend,
                        hovertemplate=(
                            f"<b>{seg['name']}</b>"
                            f"{'  (plan)' if seg['source'] == 'plan' else ''}<br>"
                            f"Start: {seg['start'].strftime('%d-%m-%Y')}<br>"
                            f"Koniec: {seg['end'].strftime('%d-%m-%Y')}<br>"
                            f"Czas: {duration_days}d"
                            f"<extra></extra>"
                        )
                    ))
                    
                    # Tekst na pasku (jeśli wystarczająco szeroki)
                    if duration_days >= 5:
                        fig.add_annotation(
                            x=mid_date,
                            y=y_center,
                            text=f"<b>{seg['name']}</b>",
                            showarrow=False,
                            font=dict(color='white', size=9),
                            xanchor='center',
                            yanchor='middle'
                        )
            
            # Separatory między projektami (poziome linie)
            for i in range(len(all_projects) - 1):
                p1 = all_projects[i]
                p2 = all_projects[i + 1]
                separator_y = (p1['_y_base'] + p1['_lane_h'] + p2['_y_base']) / 2
                fig.add_hline(
                    y=separator_y,
                    line_dash='dot',
                    line_color='#bdc3c7',
                    line_width=1
                )
            
            total_height = current_y
            fig.update_layout(
                title={
                    'text': f"📊 Pipeline projektów – {len(all_projects)} maszyn",
                    'x': 0.5, 'xanchor': 'center',
                    'font': {'size': 18, 'color': '#2c3e50'}
                },
                xaxis=dict(
                    title="Oś czasu",
                    type='date',
                    showgrid=True,
                    gridcolor='#ecf0f1',
                    dtick='M1',
                    tickformat='%b %Y'
                ),
                yaxis=dict(
                    tickmode='array',
                    tickvals=y_positions,
                    ticktext=y_labels,
                    showgrid=False,
                    type='linear'
                ),
                height=max(400, int(total_height * 90) + 120),
                hovermode='closest',
                plot_bgcolor='white',
                paper_bgcolor='white',
                legend=dict(
                    title="Etapy",
                    orientation='h',
                    yanchor='bottom',
                    y=1.02,
                    xanchor='center',
                    x=0.5
                )
            )
            
            # Otwórz w przeglądarce
            import tempfile, os, webbrowser
            fd, temp_path = tempfile.mkstemp(suffix='.html', prefix='rm_segmented_bar_')
            os.close(fd)
            fig.write_html(temp_path)
            webbrowser.open('file://' + temp_path)
            
            self.chart_status.config(
                text=f"✅ Segmented bar ({len(all_projects)} projektów) → przeglądarka",
                fg=self.COLOR_GREEN
            )
            
        except Exception as e:
            print(f"🔥 Błąd tworzenia segmented bar: {e}")
            import traceback
            traceback.print_exc()
            self.chart_status.config(text=f"❌ Błąd: {e}", fg=self.COLOR_RED)
            messagebox.showerror("Błąd wykresu", f"Nie można utworzyć wykresu:\n{e}")

    # ========================================================================
    # MODUŁ BACKUPÓW
    # ========================================================================

    def menu_view_backups(self):
        """Menu: Podgląd backupów"""
        if not self.backup_manager:
            messagebox.showwarning("Backupy niedostępne", "BackupManager nie jest zainicjalizowany!")
            return
        self.backups_view_dialog()
    
    def menu_run_backup_now(self):
        """Menu: Wykonaj backup teraz"""
        if not self.backup_manager:
            messagebox.showwarning("Backupy niedostępne", "BackupManager nie jest zainicjalizowany!")
            return
        
        if not messagebox.askyesno("Potwierdź backup", "Wykonać backup master DB i wszystkich projektów?"):
            return
        
        try:
            self.backup_manager.run_daily_backup()
            messagebox.showinfo("Sukces", "Backup zakończony pomyślnie!")
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się wykonać backupu:\n{e}")
    
    def backups_view_dialog(self):
        """Dialog podglądu backupów"""
        win = tk.Toplevel(self.root)
        win.title("📋 Podgląd backupów")
        win.geometry("1000x650")
        win.transient(self.root)
        
        # Wycentruj
        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (win.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (win.winfo_height() // 2)
        win.geometry(f"+{x}+{y}")
        
        # Główny frame
        main_frame = tk.Frame(win, bg="#f0f0f0", padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Wybór typu backupu
        top_frame = tk.Frame(main_frame, bg="#f0f0f0")
        top_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(top_frame, text="Typ backupu:", bg="#f0f0f0", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(0, 10))
        
        backup_type_var = tk.StringVar(value="master")
        tk.Radiobutton(top_frame, text="🗄️ Baza master RM_MANAGER", variable=backup_type_var, value="master",
                      bg="#f0f0f0", font=("Arial", 10), command=lambda: load_backups()).pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(top_frame, text="📁 Projekty", variable=backup_type_var, value="projects",
                      bg="#f0f0f0", font=("Arial", 10), command=lambda: load_backups()).pack(side=tk.LEFT, padx=10)
        
        # Wybór projektu (jeśli typ=projects) - ZAWSZE widoczny na górze, ale disabled gdy master
        project_frame = tk.Frame(main_frame, bg="#f0f0f0")
        project_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(project_frame, text="Projekt:", bg="#f0f0f0", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(0, 10))
        
        project_combo = ttk.Combobox(project_frame, state="disabled", width=60, font=("Arial", 10))  # Disabled na początku
        project_combo.pack(side=tk.LEFT, padx=5)
        
        # Lista backupów
        list_frame = tk.Frame(main_frame, bg="white", relief=tk.SUNKEN, bd=1)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Treeview
        columns = ("Data", "Rozmiar", "Typ")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
        tree.heading("Data", text="Data backupu")
        tree.heading("Rozmiar", text="Rozmiar (MB)")
        tree.heading("Typ", text="Typ")
        
        tree.column("Data", width=200)
        tree.column("Rozmiar", width=120)
        tree.column("Typ", width=150)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Panel podglądu
        preview_frame = tk.LabelFrame(main_frame, text="Podgląd zawartości", bg="#f0f0f0", font=("Arial", 10, "bold"))
        preview_frame.pack(fill=tk.BOTH, pady=(0, 10))
        
        preview_text = tk.Text(preview_frame, height=8, bg="white", font=("Courier", 9), wrap=tk.WORD)
        preview_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Cache backupów
        backups_cache = {}
        
        def load_projects_list():
            """Załaduj listę projektów do combobox"""
            try:
                # Pobierz projekty z master DB
                print(f"🔍 load_projects_list: master_db_path = {self.master_db_path}")
                from pathlib import Path
                master_path = Path(self.master_db_path)
                print(f"   Plik istnieje: {master_path.exists()}")
                if master_path.exists():
                    print(f"   Rozmiar: {master_path.stat().st_size / 1024:.1f} KB")
                
                con = sqlite3.connect(self.master_db_path, timeout=10.0)
                con.row_factory = sqlite3.Row
                
                # Sprawdź czy tabela projects istnieje
                cursor = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='projects'")
                if not cursor.fetchone():
                    print(f"   ⚠️  Tabela 'projects' NIE ISTNIEJE w {self.master_db_path}")
                    con.close()
                    return
                
                # Wykryj nazwy kolumn dynamicznie
                cursor = con.execute("PRAGMA table_info(projects)")
                cols_info = cursor.fetchall()
                col_names = [col[1] for col in cols_info]
                
                print(f"   Kolumny w tabeli projects: {col_names}")
                
                # Znajdź kolumnę ID
                id_col = 'id'
                if 'project_id' in col_names:
                    id_col = 'project_id'
                
                # Znajdź kolumnę name
                name_col = 'name'
                if 'project_name' in col_names:
                    name_col = 'project_name'
                
                # Znajdź kolumnę active
                active_col = None
                for candidate in ['is_active', 'active', 'enabled']:
                    if candidate in col_names:
                        active_col = candidate
                        break
                
                # Buduj SQL - tylko aktywne projekty MACHINE
                where_clause = []
                if active_col:
                    where_clause.append(f"COALESCE({active_col}, 1) = 1")
                if 'project_type' in col_names:
                    where_clause.append("COALESCE(project_type, 'MACHINE') = 'MACHINE'")
                
                where_sql = f"WHERE {' AND '.join(where_clause)}" if where_clause else ""
                
                sql = f"SELECT {id_col} as pid, {name_col} as name FROM projects {where_sql}"
                cursor = con.execute(sql)
                projects = cursor.fetchall()
                con.close()
                
                print(f"   Znaleziono {len(projects)} projektów")
                
                # Sortowanie identyczne jak w głównym oknie (cyfry malejąco → litery A-Z + numery malejąco)
                def sort_key(row):
                    name_lower = (row['name'] or '').lower()
                    import re
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
                
                projects_sorted = sorted(projects, key=sort_key)
                
                project_combo['values'] = [f"{p['pid']}: {p['name']}" for p in projects_sorted]
                if projects_sorted:
                    project_combo.current(0)
            except Exception as e:
                print(f"⚠️  Błąd ładowania projektów: {e}")
                import traceback
                traceback.print_exc()
        
        def load_backups():
            """Załaduj listę backupów"""
            tree.delete(*tree.get_children())
            preview_text.delete("1.0", tk.END)
            backups_cache.clear()
            
            backup_type = backup_type_var.get()
            
            try:
                if backup_type == "master":
                    # Wyłącz combobox projektu
                    project_combo.config(state="disabled")
                    backups = self.backup_manager.list_master_backups()
                    
                    for b in backups:
                        tree.insert("", tk.END, values=(
                            b['date'],
                            f"{b['size_mb']:.2f}",
                            "RM_MANAGER Master"
                        ))
                        backups_cache[b['date']] = b
                
                else:  # projects
                    # Włącz combobox projektu
                    project_combo.config(state="readonly")
                    
                    # Pobierz wybrane ID projektu
                    sel = project_combo.get()
                    if not sel:
                        return
                    
                    project_id = int(sel.split(':')[0])
                    backups = self.backup_manager.list_project_backups(project_id)
                    
                    for b in backups:
                        tree.insert("", tk.END, values=(
                            b['date'],
                            f"{b['size_mb']:.2f}",
                            f"Projekt {project_id}"
                        ))
                        backups_cache[b['date']] = b
            
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się załadować backupów:\n{e}")
        
        def on_backup_selected(event):
            """Podgląd backupu"""
            sel = tree.selection()
            if not sel:
                return
            
            item = tree.item(sel[0])
            date = item['values'][0]
            
            if date not in backups_cache:
                return
            
            backup_info = backups_cache[date]
            
            try:
                preview_data = self.backup_manager.get_backup_preview_data(
                    backup_info['path'],
                    backup_info['type']
                )
                
                # Wyświetl podgląd
                preview_text.delete("1.0", tk.END)
                preview_text.insert("1.0", f"📁 Plik: {preview_data['file']}\n")
                preview_text.insert(tk.END, f"📏 Rozmiar: {preview_data['size_mb']:.2f} MB\n")
                preview_text.insert(tk.END, f"🕐 Zmodyfikowano: {preview_data['modified'][:19]}\n\n")
                
                if backup_info['type'] == 'master':
                    preview_text.insert(tk.END, f"📊 Statystyki RM_MANAGER:\n")
                    preview_text.insert(tk.END, f"  • Definicje etapów: {preview_data.get('stage_definitions_count', 'N/A')}\n")
                    preview_text.insert(tk.END, f"  • Śledzenie plików: {preview_data.get('file_tracking_count', 'N/A')}\n")
                
                elif backup_info['type'] == 'project':
                    preview_text.insert(tk.END, f"📊 Statystyki projektu:\n")
                    preview_text.insert(tk.END, f"  • Etapy: {preview_data.get('stages_count', 'N/A')}\n")
                    preview_text.insert(tk.END, f"  • Okresy: {preview_data.get('periods_count', 'N/A')}\n")
                    preview_text.insert(tk.END, f"  • Zależności: {preview_data.get('dependencies_count', 'N/A')}\n")
            
            except Exception as e:
                preview_text.delete("1.0", tk.END)
                preview_text.insert("1.0", f"❌ Błąd podglądu: {e}")
                import traceback
                traceback.print_exc()
        
        tree.bind("<<TreeviewSelect>>", on_backup_selected)
        project_combo.bind("<<ComboboxSelected>>", lambda e: load_backups())
        
        # Przyciski
        btn_frame = tk.Frame(main_frame, bg="#ecf0f1", height=50)
        btn_frame.pack(fill=tk.X)
        btn_frame.pack_propagate(False)
        
        btn_inner = tk.Frame(btn_frame, bg="#ecf0f1")
        btn_inner.pack(pady=10)
        
        tk.Button(btn_inner, text="🔄 Odśwież", command=load_backups, width=15,
                 bg="#16a085", fg="white", font=("Arial", 10)).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_inner, text="✖ Zamknij", command=win.destroy, width=15,
                 bg="#95a5a6", fg="white", font=("Arial", 10)).pack(side=tk.LEFT, padx=5)
        
        # Początkowe załadowanie
        load_projects_list()
        load_backups()


    
    def hide_notifications_banner(self):
        """Ukryj banner powiadomień."""
        self.notifications_banner.pack_forget()
    
    def show_notifications_banner(self, count: int):
        """Pokaż banner z liczbą nowych powiadomień."""
        if count > 0:
            msg = f"🔔 Masz {count} {'nowe powiadomienie' if count == 1 else 'nowe powiadomienia'} o płatnościach!"
            self.notifications_label.config(text=msg)
            self.notifications_banner.pack(fill=tk.X, after=self.top_frame, pady=(0, 5))
        else:
            self.hide_notifications_banner()
    
    def check_unread_notifications(self):
        """Sprawdź nieprzeczytane powiadomienia i pokaż banner."""
        try:
            notifications = rmm.get_unread_notifications(self.rm_master_db_path)
            self.show_notifications_banner(len(notifications))
        except Exception as e:
            print(f"❌ Błąd sprawdzania powiadomień: {e}")
    
    def show_all_notifications(self):
        """Pokaż okno ze wszystkimi powiadomieniami."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Powiadomienia o płatnościach")
        dialog.transient(self.root)
        
        self._center_window(dialog, 900, 600)
        
        # Treeview
        tree = ttk.Treeview(
            dialog,
            columns=('project', 'message', 'created_at', 'created_by', 'status'),
            show='headings',
            height=20
        )
        
        tree.heading('project', text='Projekt')
        tree.heading('message', text='Wiadomość')
        tree.heading('created_at', text='Data')
        tree.heading('created_by', text='Utworzył')
        tree.heading('status', text='Status')
        
        tree.column('project', width=150)
        tree.column('message', width=350)
        tree.column('created_at', width=150)
        tree.column('created_by', width=100)
        tree.column('status', width=100, anchor='center')
        
        scroll = ttk.Scrollbar(dialog, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        
        # Załaduj powiadomienia (wszystkie, nie tylko nieprzeczytane)
        try:
            con = rmm._open_rm_connection(self.rm_master_db_path)
            rows = con.execute("""
                SELECT id, project_name, message, created_at, created_by, is_read
                FROM in_app_notifications
                ORDER BY created_at DESC
                LIMIT 100
            """).fetchall()
            con.close()
            
            notification_ids = []
            for row in rows:
                nid = row['id']
                project = row['project_name'] or f"ID {row.get('project_id', '?')}"
                message = row['message']
                created_at = row['created_at']
                created_by = row['created_by'] or "---"
                status = "✅ Przeczytane" if row['is_read'] else "🔔 Nowe"
                
                tree.insert('', tk.END, values=(project, message, created_at, created_by, status), tags=(nid,))
                
                if not row['is_read']:
                    notification_ids.append(nid)
            
            # Oznacz wszystkie jako przeczytane
            if notification_ids:
                con = rmm._open_rm_connection(self.rm_master_db_path)
                for nid in notification_ids:
                    con.execute("""
                        UPDATE in_app_notifications
                        SET is_read = 1, read_at = CURRENT_TIMESTAMP, read_by = ?
                        WHERE id = ?
                    """, (self.current_user, nid))
                con.commit()
                con.close()
                
                # Odśwież banner
                self.check_unread_notifications()
            
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można załadować powiadomień:\n{e}")
        
        # Przycisk zamknij
        tk.Button(
            dialog,
            text="❌ Zamknij",
            command=dialog.destroy,
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 10),
            padx=20,
            pady=5
        ).pack(pady=10)
    
    # ========================================================================
    # PAYMENT SYSTEM - Płatności (2026-04-13)
    # ========================================================================
    
    def payment_notifications_config(self):
        """Dialog konfiguracji powiadomień email o płatnościach."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Konfiguracja powiadomień płatności")
        dialog.transient(self.root)
        
        self._center_window(dialog, 600, 540)
        
        # Pobierz aktualną konfigurację
        try:
            config = rmm.get_payment_notification_config(self.rm_master_db_path)
            if not config:
                config = {
                    'trigger_percentage': 100,
                    'email_recipients': [],
                    'smtp_server': '',
                    'smtp_port': 587,
                    'smtp_user': '',
                    'smtp_password': '',
                    'enabled': True
                }
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można załadować konfiguracji:\n{e}")
            return
        
        # Frame dla opcji
        main_frame = tk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Trigger percentage
        tk.Label(main_frame, text="Trigger (%): ", font=self.FONT_DEFAULT).grid(row=0, column=0, sticky='e', pady=5)
        trigger_var = tk.IntVar(value=config['trigger_percentage'])
        tk.Spinbox(
            main_frame,
            from_=1,
            to=100,
            textvariable=trigger_var,
            width=10,
            font=self.FONT_DEFAULT
        ).grid(row=0, column=1, sticky='w', pady=5)
        tk.Label(main_frame, text="(wysyłaj powiadomienie przy tym procencie)", font=self.FONT_SMALL, fg="gray").grid(row=0, column=2, sticky='w', padx=10)
        
        # Enabled
        enabled_var = tk.BooleanVar(value=config['enabled'])
        tk.Checkbutton(
            main_frame,
            text="Powiadomienia włączone",
            variable=enabled_var,
            font=self.FONT_DEFAULT
        ).grid(row=1, column=0, columnspan=3, sticky='w', pady=10)
        
        # Lista email
        tk.Label(main_frame, text="Odbiorcy email:", font=("Arial", 11, "bold")).grid(row=2, column=0, columnspan=3, sticky='w', pady=(20, 5))
        
        recipients_frame = tk.Frame(main_frame)
        recipients_frame.grid(row=3, column=0, columnspan=3, sticky='ew', pady=5)
        
        recipients_listbox = tk.Listbox(recipients_frame, height=6, font=self.FONT_DEFAULT)
        recipients_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        recipients_scroll = ttk.Scrollbar(recipients_frame, orient=tk.VERTICAL, command=recipients_listbox.yview)
        recipients_listbox.configure(yscrollcommand=recipients_scroll.set)
        recipients_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Załaduj odbiorców
        for email in config['email_recipients']:
            recipients_listbox.insert(tk.END, email)
        
        # Przyciski zarządzania listą
        list_controls = tk.Frame(main_frame)
        list_controls.grid(row=4, column=0, columnspan=3, pady=10)
        
        def add_recipient():
            email = simpledialog.askstring("Dodaj odbiorcę", "Podaj adres email:", parent=dialog)
            if email and '@' in email:
                recipients_listbox.insert(tk.END, email)
            elif email:
                messagebox.showwarning("Błąd", "Nieprawidłowy adres email.")
        
        def remove_recipient():
            selected = recipients_listbox.curselection()
            if selected:
                recipients_listbox.delete(selected[0])
        
        tk.Button(
            list_controls,
            text="➕ Dodaj",
            command=add_recipient,
            bg=self.COLOR_GREEN,
            fg="white",
            font=self.FONT_DEFAULT,
            padx=15,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            list_controls,
            text="🗑️ Usuń",
            command=remove_recipient,
            bg=self.COLOR_RED,
            fg="white",
            font=self.FONT_DEFAULT,
            padx=15,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        # SMTP konfiguracja
        tk.Label(main_frame, text="Konfiguracja SMTP:", font=("Arial", 11, "bold")).grid(row=5, column=0, columnspan=3, sticky='w', pady=(20, 5))
        
        tk.Label(main_frame, text="Serwer:", font=self.FONT_DEFAULT).grid(row=6, column=0, sticky='e', pady=5)
        smtp_server_var = tk.StringVar(value=config['smtp_server'] or '')
        tk.Entry(main_frame, textvariable=smtp_server_var, width=30, font=self.FONT_DEFAULT).grid(row=6, column=1, columnspan=2, sticky='w', pady=5)
        
        tk.Label(main_frame, text="Port:", font=self.FONT_DEFAULT).grid(row=7, column=0, sticky='e', pady=5)
        smtp_port_var = tk.IntVar(value=config['smtp_port'] or 587)
        tk.Entry(main_frame, textvariable=smtp_port_var, width=10, font=self.FONT_DEFAULT).grid(row=7, column=1, sticky='w', pady=5)
        
        tk.Label(main_frame, text="Użytkownik:", font=self.FONT_DEFAULT).grid(row=8, column=0, sticky='e', pady=5)
        smtp_user_var = tk.StringVar(value=config['smtp_user'] or '')
        tk.Entry(main_frame, textvariable=smtp_user_var, width=30, font=self.FONT_DEFAULT).grid(row=8, column=1, columnspan=2, sticky='w', pady=5)
        
        tk.Label(main_frame, text="Hasło:", font=self.FONT_DEFAULT).grid(row=9, column=0, sticky='e', pady=5)
        smtp_password_var = tk.StringVar(value=config['smtp_password'] or '')
        tk.Entry(main_frame, textvariable=smtp_password_var, width=30, font=self.FONT_DEFAULT, show='*').grid(row=9, column=1, columnspan=2, sticky='w', pady=5)
        
        def save():
            # Pobierz listę odbiorców
            recipients = list(recipients_listbox.get(0, tk.END))
            
            try:
                rmm.update_payment_notification_config(
                    self.rm_master_db_path,
                    recipients=recipients,
                    smtp_server=smtp_server_var.get().strip() or None,
                    smtp_port=smtp_port_var.get() or None,
                    smtp_user=smtp_user_var.get().strip() or None,
                    smtp_password=smtp_password_var.get() or None,
                    enabled=enabled_var.get(),
                    trigger_percentage=trigger_var.get()
                )
                
                messagebox.showinfo("Sukces", "Konfiguracja zapisana.")
                dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można zapisać konfiguracji:\n{e}")

        def send_test_email():
            """Wyślij testowy email aby zweryfikować konfigurację SMTP."""
            server = smtp_server_var.get().strip()
            user = smtp_user_var.get().strip()
            password = smtp_password_var.get()
            recipients = list(recipients_listbox.get(0, tk.END))

            print("\n📧 ========== TEST EMAIL DEBUG ==========")
            print(f"📧 Server: {server}")
            print(f"📧 User: {user}")
            print(f"📧 Password: {'*' * len(password) if password else '(empty)'}")
            print(f"📧 Recipients: {recipients}")

            if not server or not user or not password:
                print("❌ Walidacja nie powiodła się: brak server/user/password")
                messagebox.showwarning("Brak danych", "Wypełnij serwer SMTP, użytkownika i hasło.", parent=dialog)
                return
            if not recipients:
                print("❌ Walidacja nie powiodła się: brak odbiorców")
                messagebox.showwarning("Brak odbiorców", "Dodaj co najmniej jednego odbiorcę email.", parent=dialog)
                return

            try:
                port = smtp_port_var.get() or 587
            except (tk.TclError, ValueError):
                port = 587
            
            print(f"📧 Port: {port}")

            def _worker():
                import smtplib
                from email.mime.text import MIMEText
                try:
                    print("📧 [1/6] Tworzenie wiadomości...")
                    msg = MIMEText("TEST", 'plain', 'utf-8')
                    msg['From'] = user
                    msg['To'] = ', '.join(recipients)
                    msg['Subject'] = "TEST"
                    print("✅ Wiadomość utworzona")

                    # Port 465 = SMTP_SSL (SSL od razu), Port 587 = SMTP + STARTTLS
                    if port == 465:
                        print(f"📧 [2/6] Łączenie SSL z {server}:{port} (timeout=15s)...")
                        srv = smtplib.SMTP_SSL(server, port, timeout=15)
                        print("✅ Połączono (SSL)")
                        print("📧 [3/6] SSL już aktywne, pomijam STARTTLS")
                    else:
                        print(f"📧 [2/6] Łączenie z {server}:{port} (timeout=15s)...")
                        srv = smtplib.SMTP(server, port, timeout=15)
                        print("✅ Połączono")
                        
                        print("📧 [3/6] STARTTLS...")
                        srv.starttls()
                        print("✅ TLS aktywowane")
                    
                    print(f"📧 [4/6] Logowanie jako '{user}'...")
                    srv.login(user, password)
                    print("✅ Zalogowano")
                    
                    print(f"📧 [5/6] Wysyłanie do {recipients}...")
                    srv.send_message(msg)
                    print("✅ Wysłano")
                    
                    print("📧 [6/6] Zamykanie połączenia...")
                    srv.quit()
                    print("✅ Zamknięto")
                    print("📧 ========== TEST ZAKOŃCZONY SUKCESEM ==========")

                    dialog.after(0, lambda: messagebox.showinfo(
                        "Sukces", f"✅ Testowy email wysłany do:\n{', '.join(recipients)}", parent=dialog))
                except Exception as e:
                    print(f"\n❌ ========== BŁĄD SMTP ==========")
                    print(f"❌ Typ błędu: {type(e).__name__}")
                    print(f"❌ Args: {e.args}")
                    
                    # Parsuj błąd SMTP (często tuple z kodem i komunikatem)
                    if isinstance(e, smtplib.SMTPException) and hasattr(e, 'smtp_code'):
                        err_msg = f"[{e.smtp_code}] {e.smtp_error.decode('utf-8', errors='replace') if isinstance(e.smtp_error, bytes) else e.smtp_error}"
                    elif isinstance(e.args, tuple) and len(e.args) >= 2:
                        code, msg = e.args[0], e.args[1]
                        if isinstance(msg, bytes):
                            msg = msg.decode('utf-8', errors='replace')
                        err_msg = f"[{code}] {msg}"
                    else:
                        err_msg = str(e)
                    
                    print(f"❌ Parsed error: {err_msg}")
                    print(f"❌ =============================\n")
                    
                    dialog.after(0, lambda m=err_msg: messagebox.showerror(
                        "Błąd SMTP", 
                        f"❌ Nie udało się wysłać testowego emaila:\n\n{m}\n\n"
                        f"💡 Porty SMTP:\n"
                        f"• 587 = STARTTLS (zalecane dla WP.pl)\n"
                        f"• 465 = SSL (starsze, może nie działać wszędzie)\n\n"
                        f"💡 Wskazówki dla WP.pl:\n"
                        f"• Login: PEŁNY adres (np. user@wp.pl, nie samo 'user')\n"
                        f"• Hasło: aktualne hasło do poczty WP.pl\n"
                        f"• Port: 587 (STARTTLS)\n"
                        f"• Jeśli błąd 535: sprawdź hasło lub zaloguj się na https://poczta.wp.pl\n\n"
                        f"💡 Wskazówki dla Gmail:\n"
                        f"• Wymagane 'Hasło aplikacji' zamiast głównego hasła\n"
                        f"• Gmail → Konto Google → Bezpieczeństwo → Hasła aplikacji",
                        parent=dialog))

            threading.Thread(target=_worker, daemon=True).start()
        
        # Przyciski akcji
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=20)
        
        tk.Button(
            btn_frame,
            text="💾 Zapisz",
            command=save,
            bg=self.COLOR_GREEN,
            fg="white",
            font=("Arial", 11, "bold"),
            padx=30,
            pady=8
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            btn_frame,
            text="📧 Test",
            command=send_test_email,
            bg=self.COLOR_PURPLE,
            fg="white",
            font=("Arial", 11, "bold"),
            padx=30,
            pady=8
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="❌ Anuluj",
            command=dialog.destroy,
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 11),
            padx=30,
            pady=8
        ).pack(side=tk.LEFT, padx=5)
    
    def sms_config_dialog(self):
        """Dialog konfiguracji SMS (SMSAPI.pl)."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Konfiguracja SMS - SMSAPI.pl")
        dialog.transient(self.root)
        dialog.geometry("650x550")
        
        # Centrowanie okna
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (650 // 2)
        y = (dialog.winfo_screenheight() // 2) - (550 // 2)
        dialog.geometry(f"650x550+{x}+{y}")
        
        # Frame główny
        main_frame = tk.Frame(dialog, bg="white")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Konfiguruj grid weights aby widgety były widoczne
        main_frame.columnconfigure(0, weight=0)
        main_frame.columnconfigure(1, weight=1)
        main_frame.columnconfigure(2, weight=0)
        for i in range(11):
            main_frame.rowconfigure(i, weight=0)
        
        # Info header
        tk.Label(
            main_frame,
            text="📱 Konfiguracja SMS (SMSAPI.pl)",
            font=("Arial", 12, "bold"),
            fg=self.COLOR_BLUE
        ).grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 10))
        
        tk.Label(
            main_frame,
            text="Powiadomienia SMS o zmianach statusu projektów",
            font=self.FONT_SMALL,
            fg="gray"
        ).grid(row=1, column=0, columnspan=3, sticky='w', pady=(0, 20))
        
        # SMS enabled
        sms_enabled = tk.BooleanVar(value=self.config.get('sms_enabled', False))
        tk.Checkbutton(
            main_frame,
            text="SMS włączony",
            variable=sms_enabled,
            font=("Arial", 11, "bold")
        ).grid(row=2, column=0, columnspan=3, sticky='w', pady=10)
        
        # Token SMSAPI
        tk.Label(main_frame, text="Token OAuth:", font=self.FONT_DEFAULT).grid(row=3, column=0, sticky='e', pady=5, padx=5)
        token_var = tk.StringVar(value=self.config.get('sms_api_token', ''))
        token_entry = tk.Entry(main_frame, textvariable=token_var, width=40, font=self.FONT_DEFAULT, show='*')
        token_entry.grid(row=3, column=1, columnspan=2, sticky='w', pady=5)
        
        tk.Label(
            main_frame,
            text="(z https://www.smsapi.pl → Ustawienia → OAuth)",
            font=self.FONT_SMALL,
            fg="gray"
        ).grid(row=4, column=1, columnspan=2, sticky='w')
        
        # Nazwa nadawcy (opcjonalne)
        tk.Label(main_frame, text="Nazwa nadawcy:", font=self.FONT_DEFAULT).grid(row=5, column=0, sticky='e', pady=5, padx=5)
        sender_var = tk.StringVar(value=self.config.get('sms_sender_name', 'RM_MANAGER'))
        tk.Entry(main_frame, textvariable=sender_var, width=15, font=self.FONT_DEFAULT).grid(row=5, column=1, sticky='w', pady=5)
        
        tk.Label(
            main_frame,
            text="(opcjonalne, wymaga rejestracji w SMSAPI, 10 PLN/msc)",
            font=self.FONT_SMALL,
            fg="gray"
        ).grid(row=6, column=1, columnspan=2, sticky='w')
        
        # Kod kraju (domyślny)
        tk.Label(main_frame, text="Kod kraju:", font=self.FONT_DEFAULT).grid(row=7, column=0, sticky='e', pady=5, padx=5)
        country_var = tk.StringVar(value=self.config.get('sms_default_country_code', '48'))
        tk.Entry(main_frame, textvariable=country_var, width=5, font=self.FONT_DEFAULT).grid(row=7, column=1, sticky='w', pady=5)
        
        tk.Label(
            main_frame,
            text="(np. 48 dla Polski, dodawany automatycznie jeśli brak w numerze)",
            font=self.FONT_SMALL,
            fg="gray"
        ).grid(row=8, column=1, columnspan=2, sticky='w')
        
        # Info o kosztach
        info_frame = tk.Frame(main_frame, bg="#e8f4fd", relief=tk.SOLID, bd=1)
        info_frame.grid(row=9, column=0, columnspan=3, sticky='ew', pady=(20, 10))
        
        tk.Label(
            info_frame,
            text="ℹ️ Koszt SMS:",
            font=("Arial", 10, "bold"),
            bg="#e8f4fd"
        ).pack(anchor='w', padx=10, pady=(10, 5))
        
        tk.Label(
            info_frame,
            text="• 1 SMS (do 160 znaków): ~0.06-0.10 PLN\n"
                 "• Wymagana biblioteka: pip install smsapi-client\n"
                 "• Konto: https://www.smsapi.pl (min. 10 PLN startowe)",
            font=self.FONT_SMALL,
            bg="#e8f4fd",
            justify=tk.LEFT
        ).pack(anchor='w', padx=10, pady=(0, 10))
        
        # Przyciski
        btn_frame = tk.Frame(main_frame)
        btn_frame.grid(row=10, column=0, columnspan=3, pady=(20, 0))
        
        def save():
            try:
                # Zapisz do config
                self.config['sms_enabled'] = sms_enabled.get()
                self.config['sms_api_token'] = token_var.get().strip()
                self.config['sms_sender_name'] = sender_var.get().strip() or 'RM_MANAGER'
                self.config['sms_default_country_code'] = country_var.get().strip() or '48'
                
                # Zapisz do pliku JSON
                import json
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
                
                messagebox.showinfo("Sukces", "Konfiguracja SMS zapisana.", parent=dialog)
                dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można zapisać konfiguracji:\n{e}", parent=dialog)
        
        tk.Button(
            btn_frame,
            text="💾 Zapisz",
            command=save,
            bg=self.COLOR_GREEN,
            fg="white",
            font=("Arial", 11, "bold"),
            padx=30,
            pady=8
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="❌ Anuluj",
            command=dialog.destroy,
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 11),
            padx=30,
            pady=8
        ).pack(side=tk.LEFT, padx=5)
    
    def send_test_sms_dialog(self):
        """Dialog wysyłki testowego SMS."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Wyślij SMS testowy")
        dialog.transient(self.root)
        dialog.geometry("550x400")
        
        # Centrowanie okna
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (550 // 2)
        y = (dialog.winfo_screenheight() // 2) - (400 // 2)
        dialog.geometry(f"550x400+{x}+{y}")
        
        # Frame główny
        main_frame = tk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Konfiguruj grid
        main_frame.columnconfigure(1, weight=1)
        
        tk.Label(
            main_frame,
            text="📱 Test SMS - SMSAPI.pl",
            font=("Arial", 12, "bold"),
            fg=self.COLOR_BLUE
        ).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 20))
        
        # Numer telefonu
        tk.Label(main_frame, text="Numer telefonu:", font=self.FONT_DEFAULT).grid(row=1, column=0, sticky='e', pady=5, padx=5)
        phone_var = tk.StringVar()
        tk.Entry(main_frame, textvariable=phone_var, width=20, font=self.FONT_DEFAULT).grid(row=1, column=1, sticky='w', pady=5)
        
        tk.Label(
            main_frame,
            text="(np. 48123456789 lub 123456789)",
            font=self.FONT_SMALL,
            fg="gray"
        ).grid(row=2, column=1, sticky='w')
        
        # Treść SMS
        tk.Label(main_frame, text="Treść SMS:", font=self.FONT_DEFAULT).grid(row=3, column=0, sticky='ne', pady=5, padx=5)
        message_text = tk.Text(main_frame, width=40, height=4, font=self.FONT_DEFAULT)
        message_text.grid(row=3, column=1, sticky='w', pady=5)
        message_text.insert('1.0', 'Test SMS z RM_MANAGER')
        
        # Licznik znaków
        char_label = tk.Label(main_frame, text="0/160 znaków (1 SMS)", font=self.FONT_SMALL, fg="gray")
        char_label.grid(row=4, column=1, sticky='w')
        
        def update_char_count(event=None):
            text = message_text.get('1.0', 'end-1c')
            length = len(text)
            sms_count = (length // 160) + 1 if length > 0 else 0
            char_label.config(text=f"{length}/160 znaków ({sms_count} SMS)")
        
        message_text.bind('<KeyRelease>', update_char_count)
        update_char_count()
        
        # Przyciski
        btn_frame = tk.Frame(main_frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(20, 0))
        
        def send():
            phone = phone_var.get().strip()
            message = message_text.get('1.0', 'end-1c').strip()
            
            if not phone:
                messagebox.showwarning("Błąd", "Podaj numer telefonu.", parent=dialog)
                return
            if not message:
                messagebox.showwarning("Błąd", "Wpisz treść SMS.", parent=dialog)
                return
            
            # Sprawdź konfigurację
            if not self.config.get('sms_enabled', False):
                messagebox.showwarning(
                    "SMS wyłączony",
                    "SMS jest wyłączony w konfiguracji.\n\nWłącz w: Narzędzia → Konfiguracja SMS",
                    parent=dialog
                )
                return
            
            if not self.config.get('sms_api_token', '').strip():
                messagebox.showwarning(
                    "Brak tokenu",
                    "Brak tokenu SMSAPI w konfiguracji.\n\nDodaj w: Narzędzia → Konfiguracja SMS",
                    parent=dialog
                )
                return
            
            # Wyślij SMS
            try:
                if not self.selected_project_id:
                    messagebox.showwarning("Błąd", "Wybierz projekt.", parent=dialog)
                    return
                
                result = rmm.send_custom_sms(
                    rm_db_path=self.rm_master_db_path,
                    project_id=self.selected_project_id,
                    message=message,
                    config=self.config,
                    phone_number=phone
                )
                
                if result['success'] > 0:
                    messagebox.showinfo(
                        "Sukces",
                        f"✅ SMS wysłany!\n\n{result['message']}",
                        parent=dialog
                    )
                    dialog.destroy()
                else:
                    error_msg = result.get('message', 'Nieznany błąd')
                    errors = result.get('errors', [])
                    if errors:
                        error_msg += '\n\nSzczegóły:\n' + '\n'.join(errors)
                    
                    messagebox.showerror(
                        "Błąd wysyłki",
                        f"❌ Nie udało się wysłać SMS:\n\n{error_msg}",
                        parent=dialog
                    )
            
            except Exception as e:
                messagebox.showerror("Błąd", f"Wyjątek podczas wysyłki:\n{e}", parent=dialog)
        
        tk.Button(
            btn_frame,
            text="📱 Wyślij",
            command=send,
            bg=self.COLOR_GREEN,
            fg="white",
            font=("Arial", 11, "bold"),
            padx=30,
            pady=8
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="❌ Anuluj",
            command=dialog.destroy,
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 11),
            padx=30,
            pady=8
        ).pack(side=tk.LEFT, padx=5)
    
    def manage_plc_senders_dialog(self):
        """Dialog zarządzania uprawnieniami do wysyłki kodów PLC."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Zarządzaj uprawnieniami wysyłki kodów PLC")
        dialog.transient(self.root)
        dialog.geometry("700x500")
        
        # Centrowanie okna
        self._center_window(dialog, 700, 500)
        
        # Frame główny
        main_frame = tk.Frame(dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Nagłówek
        tk.Label(
            main_frame,
            text="🔐 Uprawnienia do wysyłki kodów PLC",
            font=("Arial", 12, "bold"),
            fg=self.COLOR_BLUE
        ).pack(anchor='w', pady=(0, 20))
        
        # Toolbar
        toolbar = tk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=(0, 10))
        
        tk.Button(
            toolbar,
            text="➕ Dodaj użytkownika",
            command=lambda: self._add_plc_sender(sender_tree, dialog),
            bg=self.COLOR_GREEN,
            fg="white",
            font=("Arial", 10, "bold"),
            padx=15,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            toolbar,
            text="🗑️ Usuń",
            command=lambda: self._remove_plc_sender(sender_tree),
            bg=self.COLOR_RED,
            fg="white",
            font=("Arial", 10),
            padx=15,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        # Treeview - lista uprawnionych
        tree_frame = tk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        sender_tree = ttk.Treeview(
            tree_frame,
            columns=('username', 'added_by', 'added_at', 'notes'),
            show='headings',
            height=15
        )
        sender_tree.heading('username', text='Użytkownik')
        sender_tree.heading('added_by', text='Dodał')
        sender_tree.heading('added_at', text='Data dodania')
        sender_tree.heading('notes', text='Notatki')
        
        sender_tree.column('username', width=150)
        sender_tree.column('added_by', width=120)
        sender_tree.column('added_at', width=150)
        sender_tree.column('notes', width=200)
        
        scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=sender_tree.yview)
        sender_tree.configure(yscrollcommand=scroll.set)
        
        sender_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Załaduj dane
        def load_senders():
            for item in sender_tree.get_children():
                sender_tree.delete(item)
            
            try:
                senders = rmm.get_plc_authorized_senders(self.rm_master_db_path)
                for s in senders:
                    sender_tree.insert('', tk.END, values=(
                        s['username'],
                        s['added_by'] or '---',
                        s['added_at'] or '---',
                        s['notes'] or '---'
                    ))
            except Exception as e:
                print(f"❌ Błąd ładowania listy: {e}")
        
        load_senders()
        
        # Przyciski dolne
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(pady=(20, 0))
        
        tk.Button(
            btn_frame,
            text="🔄 Odśwież",
            command=load_senders,
            bg=self.COLOR_BLUE,
            fg="white",
            font=("Arial", 10),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="❌ Zamknij",
            command=dialog.destroy,
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 10),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        # Funkcje pomocnicze nie mogą być zagnieżdżone - użyjemy self._add_plc_sender
        # Zapisz referencję do load_senders
        self._plc_senders_load_callback = load_senders
    
    def _add_plc_sender(self, tree, parent_dialog):
        """Dodaj użytkownika do listy uprawnionych."""
        dialog = tk.Toplevel(parent_dialog)
        dialog.title("Dodaj użytkownika")
        dialog.transient(parent_dialog)
        dialog.grab_set()
        
        self._center_window(dialog, 400, 250)
        
        tk.Label(dialog, text="Nazwa użytkownika:", font=self.FONT_DEFAULT).grid(row=0, column=0, sticky='e', padx=10, pady=10)
        username_entry = tk.Entry(dialog, width=25, font=self.FONT_DEFAULT)
        username_entry.grid(row=0, column=1, sticky='w', padx=10, pady=10)
        
        tk.Label(dialog, text="Notatki (opcjonalnie):", font=self.FONT_DEFAULT).grid(row=1, column=0, sticky='e', padx=10, pady=10)
        notes_entry = tk.Entry(dialog, width=25, font=self.FONT_DEFAULT)
        notes_entry.grid(row=1, column=1, sticky='w', padx=10, pady=10)
        
        def save():
            username = username_entry.get().strip()
            notes = notes_entry.get().strip()
            
            if not username:
                messagebox.showwarning("Błąd", "Podaj nazwę użytkownika.", parent=dialog)
                return
            
            try:
                rmm.add_plc_authorized_sender(
                    self.rm_master_db_path,
                    username=username,
                    added_by=self.current_user,
                    notes=notes if notes else None
                )
                
                self.status_bar.config(text=f"✅ Dodano użytkownika {username}", fg="#27ae60")
                self._plc_senders_load_callback()  # Odśwież listę
                dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można dodać użytkownika:\n{e}", parent=dialog)
        
        # Przyciski
        button_frame = tk.Frame(dialog)
        button_frame.grid(row=2, column=0, columnspan=2, pady=20)
        
        tk.Button(
            button_frame,
            text="✅ Dodaj",
            command=save,
            bg=self.COLOR_GREEN,
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            button_frame,
            text="❌ Anuluj",
            command=dialog.destroy,
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 10),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
    
    def _remove_plc_sender(self, tree):
        """Usuń użytkownika z listy uprawnionych."""
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Brak wyboru", "Wybierz użytkownika z listy.")
            return
        
        item = selection[0]
        values = tree.item(item, 'values')
        username = values[0]
        
        confirm = messagebox.askyesno(
            "Potwierdzenie",
            f"Czy na pewno usunąć użytkownika '{username}' z listy uprawnionych?"
        )
        
        if not confirm:
            return
        
        try:
            rmm.remove_plc_authorized_sender(self.rm_master_db_path, username)
            self.status_bar.config(text=f"✅ Usunięto użytkownika {username}", fg="#27ae60")
            self._plc_senders_load_callback()  # Odśwież listę
            
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można usunąć użytkownika:\n{e}")
    
    def _clear_payment_selection_if_empty(self, event):
        """Usuń selekcję w payment_tree jeśli kliknięto w tło (nie na wierszu)."""
        # Sprawdź czy kliknięto na konkretnym elemencie
        item = self.payment_tree.identify_row(event.y)
        if not item:
            # Kliknięto w tło - usuń selekcję
            self.payment_tree.selection_remove(self.payment_tree.selection())
    
    def _clear_plc_codes_selection_if_empty(self, event):
        """Usuń selekcję w plc_codes_tree jeśli kliknięto w tło (nie na wierszu)."""
        # Sprawdź czy kliknięto na konkretnym elemencie
        item = self.plc_codes_tree.identify_row(event.y)
        if not item:
            # Kliknięto w tło - usuń selekcję
            self.plc_codes_tree.selection_remove(self.plc_codes_tree.selection())
    
    def _clear_history_selection_if_empty(self, event):
        """Usuń selekcję w history_tree jeśli kliknięto w tło (nie na wierszu)."""
        # Sprawdź czy kliknięto na konkretnym elemencie
        item = self.history_tree.identify_row(event.y)
        if not item:
            # Kliknięto w tło - usuń selekcję
            self.history_tree.selection_remove(self.history_tree.selection())
    
    def load_payment_milestones(self):
        """Załaduj transze płatności do treeview."""
        # Wyczyść treeview
        for item in self.payment_tree.get_children():
            self.payment_tree.delete(item)
        
        if not self.selected_project_id:
            return
        
        try:
            milestones = rmm.get_payment_milestones(self.rm_master_db_path, self.selected_project_id)
            
            for m in milestones:
                percentage = f"{m['percentage']}%"
                payment_date = m['payment_date'] or "---"
                created_by = m['created_by'] or "---"
                modified_at = m['modified_at'] or "---"
                
                self.payment_tree.insert('', tk.END, values=(percentage, payment_date, created_by, modified_at))
            
        except Exception as e:
            print(f"❌ Błąd ładowania płatności: {e}")
    
    def add_payment_milestone(self):
        """Dialog dodawania nowej transzy płatności."""
        if not self.selected_project_id:
            messagebox.showwarning("Brak projektu", "Wybierz projekt z listy.")
            return
        
        # Sprawdź istniejące transze i oblicz ile zostało
        try:
            existing = rmm.get_payment_milestones(self.rm_master_db_path, self.selected_project_id)
            current_sum = sum(m['percentage'] for m in existing)
        except Exception:
            existing = []
            current_sum = 0
        
        remaining = 100 - current_sum
        
        if remaining <= 0:
            messagebox.showinfo(
                "Płatność kompletna",
                f"Suma transz wynosi już {current_sum}%.\n"
                f"Nie można dodać więcej."
            )
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Dodaj transzę płatności")
        dialog.transient(self.root)
        dialog.grab_set()
        
        self._center_window(dialog, 400, 280)
        
        # Info o aktualnym stanie
        info_text = f"Zapłacono: {current_sum}%  |  Pozostało: {remaining}%"
        tk.Label(dialog, text=info_text, font=("Arial", 10, "bold"), fg="#2980b9").grid(
            row=0, column=0, columnspan=2, pady=(10, 5))
        
        # Procent
        tk.Label(dialog, text="Procent (%):", font=self.FONT_DEFAULT).grid(row=1, column=0, sticky='e', padx=10, pady=10)
        percentage_var = tk.IntVar(value=remaining)
        tk.Spinbox(
            dialog,
            from_=1,
            to=remaining,
            textvariable=percentage_var,
            width=10,
            font=self.FONT_DEFAULT
        ).grid(row=1, column=1, sticky='w', padx=10, pady=10)
        
        # Data płatności
        tk.Label(dialog, text="Data płatności:", font=self.FONT_DEFAULT).grid(row=2, column=0, sticky='e', padx=10, pady=10)
        
        # Frame dla daty + przycisk kalendarza
        date_frame = tk.Frame(dialog)
        date_frame.grid(row=2, column=1, sticky='w', padx=10, pady=10)
        
        date_entry = tk.Entry(date_frame, width=20, font=self.FONT_DEFAULT)
        date_entry.pack(side=tk.LEFT, padx=(0, 5))
        date_entry.insert(0, datetime.now().strftime('%Y-%m-%d'))
        
        # Przycisk kalendarza
        tk.Button(
            date_frame,
            text="📅",
            command=lambda: self.open_calendar_picker(date_entry),
            bg="#3498db",
            fg="white",
            font=("Arial", 8),
            padx=4,
            pady=2
        ).pack(side=tk.LEFT)
        
        tk.Label(dialog, text="(YYYY-MM-DD)", font=self.FONT_SMALL, fg="gray").grid(row=3, column=1, sticky='w', padx=10)
        
        def save():
            percentage = percentage_var.get()
            payment_date = date_entry.get().strip()
            
            if not payment_date:
                messagebox.showerror("Błąd", "Podaj datę płatności.")
                return
            
            # Walidacja: suma nie może przekroczyć 100%
            if percentage + current_sum > 100:
                messagebox.showerror(
                    "Błąd",
                    f"Suma transz nie może przekroczyć 100%.\n\n"
                    f"Aktualnie: {current_sum}%\n"
                    f"Dodajesz: {percentage}%\n"
                    f"Suma: {percentage + current_sum}%\n\n"
                    f"Maksymalnie możesz dodać: {remaining}%"
                )
                return
            
            # Walidacja daty
            is_valid, iso_date_or_error = self.validate_and_convert_date(payment_date)
            if not is_valid:
                messagebox.showerror("Błąd", iso_date_or_error)
                return
            
            payment_date = iso_date_or_error
            
            try:
                rmm.add_payment_milestone(
                    self.rm_master_db_path,
                    self.selected_project_id,
                    percentage,
                    payment_date,
                    user=self.current_user,
                    check_trigger=False,  # Wyłącz auto-email (zawiesza GUI)
                    master_db_path=self.master_db_path
                )
                
                self.load_payment_milestones()
                dialog.destroy()
                
                # Jeśli SUMA transz = 100% - automatycznie otwórz dialog wysyłki kodu PERMANENT
                if percentage + current_sum == 100:
                    self._auto_open_permanent_code_dialog()
                
            except sqlite3.IntegrityError:
                messagebox.showerror("Błąd", f"Transza {percentage}% już istnieje dla tego projektu.")
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można dodać transzy:\n{e}")
        
        # Przyciski
        btn_frame = tk.Frame(dialog)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=20)
        
        tk.Button(
            btn_frame,
            text="💾 Zapisz",
            command=save,
            bg=self.COLOR_GREEN,
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="❌ Anuluj",
            command=dialog.destroy,
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 10),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
    
    def _auto_open_permanent_code_dialog(self):
        """Automatyczne utworzenie kodu PERMANENT i otwarcie dialogu wysyłki po dodaniu 100%."""
        if not self.selected_project_id:
            return
        
        try:
            # Sprawdź czy już istnieje kod PERMANENT dla tego projektu
            existing_codes = rmm.get_plc_codes(self.rm_master_db_path, self.selected_project_id)
            permanent_code = next((c for c in existing_codes if c['code_type'] == 'PERMANENT'), None)
            
            if permanent_code:
                # Kod już istnieje - otwórz dialog wysyłki
                print(f"✅ Znaleziono istniejący kod PERMANENT: {permanent_code['unlock_code']}")
                self.root.after(500, lambda: self.send_plc_code(permanent_code['id']))
            else:
                # Utwórz nowy kod PERMANENT
                import random
                import string
                unlock_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                
                code_id = rmm.add_plc_code(
                    rm_db_path=self.rm_master_db_path,
                    project_id=self.selected_project_id,
                    code_type='PERMANENT',
                    unlock_code=unlock_code,
                    description='Kod permanentny - płatność 100%',
                    user=self.current_user
                )
                
                print(f"✅ Utworzono nowy kod PERMANENT: {unlock_code}")
                
                # Odbiorcy są teraz GLOBALNI - nie trzeba kopiować z innych kodów
                
                self.load_plc_codes()
                
                # Otwórz dialog wysyłki po krótkiej chwili
                self.root.after(500, lambda: self.send_plc_code(code_id))
                
        except Exception as e:
            print(f"❌ Błąd przy auto-tworzeniu kodu PERMANENT: {e}")
            import traceback
            traceback.print_exc()
    
    def edit_payment_milestone(self):
        """Dialog edycji daty istniejącej transzy."""
        if not self.selected_project_id:
            messagebox.showwarning("Brak projektu", "Wybierz projekt z listy.")
            return
        
        selected = self.payment_tree.selection()
        if not selected:
            messagebox.showwarning("Brak wyboru", "Zaznacz transzę do edycji.")
            return
        
        values = self.payment_tree.item(selected[0])['values']
        percentage_str = values[0]  # "100%"
        percentage = int(percentage_str.replace('%', ''))
        current_date = values[1]
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edytuj transzę {percentage}%")
        dialog.transient(self.root)
        dialog.grab_set()
        
        self._center_window(dialog, 400, 200)
        
        tk.Label(dialog, text=f"Transza: {percentage}%", font=("Arial", 12, "bold")).grid(row=0, column=0, columnspan=2, pady=10)
        
        # Frame dla daty + przycisk kalendarza
        date_frame = tk.Frame(dialog)
        date_frame.grid(row=1, column=1, sticky='w', padx=10, pady=10)
        
        tk.Label(dialog, text="Nowa data płatności:", font=self.FONT_DEFAULT).grid(row=1, column=0, sticky='e', padx=10, pady=10)
        
        date_entry = tk.Entry(date_frame, width=20, font=self.FONT_DEFAULT)
        date_entry.pack(side=tk.LEFT, padx=(0, 5))
        date_entry.insert(0, current_date if current_date != "---" else datetime.now().strftime('%Y-%m-%d'))
        
        # Przycisk kalendarza
        tk.Button(
            date_frame,
            text="📅",
            command=lambda: self.open_calendar_picker(date_entry),
            bg="#3498db",
            fg="white",
            font=("Arial", 8),
            padx=4,
            pady=2
        ).pack(side=tk.LEFT)
        
        tk.Label(dialog, text="(YYYY-MM-DD)", font=self.FONT_SMALL, fg="gray").grid(row=2, column=1, sticky='w', padx=10)
        
        def save():
            new_date = date_entry.get().strip()
            
            if not new_date:
                messagebox.showerror("Błąd", "Podaj datę płatności.")
                return
            
            is_valid, iso_date_or_error = self.validate_and_convert_date(new_date)
            if not is_valid:
                messagebox.showerror("Błąd", iso_date_or_error)
                return
            
            new_date = iso_date_or_error
            
            try:
                rmm.update_payment_milestone(
                    self.rm_master_db_path,
                    self.selected_project_id,
                    percentage,
                    new_date,
                    user=self.current_user,
                    check_trigger=True,
                    master_db_path=self.master_db_path
                )
                
                self.load_payment_milestones()
                dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można zaktualizować:\n{e}")
        
        # Przyciski
        btn_frame = tk.Frame(dialog)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=20)
        
        tk.Button(
            btn_frame,
            text="💾 Zapisz",
            command=save,
            bg=self.COLOR_GREEN,
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="❌ Anuluj",
            command=dialog.destroy,
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 10),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
    
    def delete_payment_milestone(self):
        """Usuń wybraną transzę płatności."""
        if not self.selected_project_id:
            messagebox.showwarning("Brak projektu", "Wybierz projekt z listy.")
            return
        
        selected = self.payment_tree.selection()
        if not selected:
            messagebox.showwarning("Brak wyboru", "Zaznacz transzę do usunięcia.")
            return
        
        values = self.payment_tree.item(selected[0])['values']
        percentage_str = values[0]
        percentage = int(percentage_str.replace('%', ''))
        
        if not messagebox.askyesno("Potwierdzenie", f"Usunąć transzę {percentage}%?"):
            return
        
        try:
            rmm.delete_payment_milestone(
                self.rm_master_db_path,
                self.selected_project_id,
                percentage,
                user=self.current_user
            )
            
            messagebox.showinfo("Sukces", f"Usunięto transzę {percentage}%")
            self.load_payment_milestones()
            
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można usunąć transzy:\n{e}")
    
    def show_payment_history(self):
        """Pokaż historię zmian płatności."""
        if not self.selected_project_id:
            messagebox.showwarning("Brak projektu", "Wybierz projekt z listy.")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Historia zmian płatności")
        dialog.transient(self.root)
        
        self._center_window(dialog, 800, 500)
        
        # Treeview
        tree = ttk.Treeview(
            dialog,
            columns=('percentage', 'payment_date', 'action', 'changed_by', 'changed_at', 'old_date'),
            show='headings',
            height=20
        )
        
        tree.heading('percentage', text='Procent')
        tree.heading('payment_date', text='Nowa data')
        tree.heading('action', text='Akcja')
        tree.heading('changed_by', text='Kto')
        tree.heading('changed_at', text='Kiedy')
        tree.heading('old_date', text='Stara data')
        
        tree.column('percentage', width=80, anchor='center')
        tree.column('payment_date', width=100)
        tree.column('action', width=100)
        tree.column('changed_by', width=100)
        tree.column('changed_at', width=150)
        tree.column('old_date', width=100)
        
        scroll = ttk.Scrollbar(dialog, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        
        # Załaduj historię
        try:
            history = rmm.get_payment_history(self.rm_master_db_path, self.selected_project_id)
            
            for h in history:
                percentage = f"{h['percentage']}%"
                payment_date = h['payment_date'] or "---"
                action = h['action']
                changed_by = h['changed_by'] or "---"
                changed_at = h['changed_at'] or "---"
                old_date = h['old_date'] or "---"
                
                tree.insert('', tk.END, values=(percentage, payment_date, action, changed_by, changed_at, old_date))
            
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można załadować historii:\n{e}")
        
        # Przycisk zamknij
        tk.Button(
            dialog,
            text="❌ Zamknij",
            command=dialog.destroy,
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 10),
            padx=20,
            pady=5
        ).pack(pady=10)
    
    # ========================================================================
    # PLC Unlock Codes (2026-04-14)
    # ========================================================================
    
    def load_plc_codes(self):
        """Załaduj kody PLC do treeview."""
        # Wyczyść treeview
        for item in self.plc_codes_tree.get_children():
            self.plc_codes_tree.delete(item)
        
        if not self.selected_project_id:
            return
        
        try:
            codes = rmm.get_plc_codes(self.rm_master_db_path, self.selected_project_id)
            
            for code in codes:
                code_type = code['code_type']
                unlock_code = code['unlock_code']
                description = code['description'] or "---"
                is_used_str = "✅ TAK" if code['is_used'] else "❌ NIE"
                used_at = code['used_at'] or "---"
                created_by = code['created_by'] or "---"
                
                # Pobierz datę wygaśnięcia z bazy (już obliczoną przy dodawaniu)
                expiry_date = "---"
                if code['expiry_date']:
                    # Wyświetl tylko datę bez czasu
                    expiry_date = code['expiry_date'].split(' ')[0]
                
                # Przechowaj ID w tagu
                item_id = self.plc_codes_tree.insert('', tk.END, values=(
                    code_type, unlock_code, description, is_used_str, used_at, expiry_date, created_by
                ))
                self.plc_codes_tree.set(item_id, '#1', code_type)  # Nadpisanie aby zachować ID
                # Przechowaj code_id jako tag
                self.plc_codes_tree.item(item_id, tags=(str(code['id']),))
            
        except Exception as e:
            print(f"❌ Błąd ładowania kodów PLC: {e}")
    
    
    def add_plc_code(self):
        """Dialog dodawania nowego kodu PLC."""
        if not self.selected_project_id:
            messagebox.showwarning("Brak projektu", "Wybierz projekt z listy.")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Dodaj kod PLC")
        dialog.transient(self.root)
        dialog.grab_set()
        
        self._center_window(dialog, 450, 300)
        
        # Typ kodu
        tk.Label(dialog, text="Typ kodu:", font=self.FONT_DEFAULT).grid(row=0, column=0, sticky='e', padx=10, pady=10)
        code_type_var = tk.StringVar(value="PERMANENT")
        code_type_combo = ttk.Combobox(
            dialog,
            textvariable=code_type_var,
            values=['PERMANENT', 'TEMPORARY'],
            state='readonly',
            width=15,
            font=self.FONT_DEFAULT
        )
        code_type_combo.grid(row=0, column=1, sticky='w', padx=10, pady=10)
        
        # Kod odblokowujący
        tk.Label(dialog, text="Kod:", font=self.FONT_DEFAULT).grid(row=1, column=0, sticky='e', padx=10, pady=10)
        code_entry = tk.Entry(dialog, width=30, font=self.FONT_DEFAULT)
        code_entry.grid(row=1, column=1, sticky='w', padx=10, pady=10)
        
        # Opis
        tk.Label(dialog, text="Opis:", font=self.FONT_DEFAULT).grid(row=2, column=0, sticky='e', padx=10, pady=10)
        desc_entry = tk.Entry(dialog, width=30, font=self.FONT_DEFAULT)
        desc_entry.grid(row=2, column=1, sticky='w', padx=10, pady=10)
        
        def save_code():
            code_type = code_type_var.get()
            unlock_code = code_entry.get().strip()
            description = desc_entry.get().strip()
            
            if not unlock_code:
                messagebox.showwarning("Brak kodu", "Wprowadź kod odblokowujący.")
                return
            
            try:
                rmm.add_plc_code(
                    self.rm_master_db_path,
                    self.selected_project_id,
                    code_type=code_type,
                    unlock_code=unlock_code,
                    description=description if description else None,
                    user=self.current_user
                )
                
                self.status_bar.config(text=f"✅ Dodano kod {code_type}", fg="#27ae60")
                self.load_plc_codes()
                dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można dodać kodu:\n{e}")
        
        # Przyciski
        button_frame = tk.Frame(dialog)
        button_frame.grid(row=3, column=0, columnspan=2, pady=20)
        
        tk.Button(
            button_frame,
            text="✅ Zapisz",
            command=save_code,
            bg=self.COLOR_GREEN,
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            button_frame,
            text="❌ Anuluj",
            command=dialog.destroy,
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 10),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
    
    def edit_plc_code(self):
        """Dialog edycji kodu PLC."""
        selection = self.plc_codes_tree.selection()
        if not selection:
            messagebox.showwarning("Brak wyboru", "Wybierz kod z listy.")
            return
        
        item = selection[0]
        tags = self.plc_codes_tree.item(item, 'tags')
        if not tags:
            messagebox.showerror("Błąd", "Nie można odczytać ID kodu.")
            return
        
        code_id = int(tags[0])
        values = self.plc_codes_tree.item(item, 'values')
        old_code = values[1]
        old_desc = values[2] if values[2] != "---" else ""
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Edytuj kod PLC")
        dialog.transient(self.root)
        dialog.grab_set()
        
        self._center_window(dialog, 450, 250)
        
        # Kod odblokowujący
        tk.Label(dialog, text="Kod:", font=self.FONT_DEFAULT).grid(row=0, column=0, sticky='e', padx=10, pady=10)
        code_entry = tk.Entry(dialog, width=30, font=self.FONT_DEFAULT)
        code_entry.insert(0, old_code)
        code_entry.grid(row=0, column=1, sticky='w', padx=10, pady=10)
        
        # Opis
        tk.Label(dialog, text="Opis:", font=self.FONT_DEFAULT).grid(row=1, column=0, sticky='e', padx=10, pady=10)
        desc_entry = tk.Entry(dialog, width=30, font=self.FONT_DEFAULT)
        desc_entry.insert(0, old_desc)
        desc_entry.grid(row=1, column=1, sticky='w', padx=10, pady=10)
        
        def save_changes():
            new_code = code_entry.get().strip()
            new_desc = desc_entry.get().strip()
            
            if not new_code:
                messagebox.showwarning("Brak kodu", "Wprowadź kod odblokowujący.")
                return
            
            try:
                rmm.update_plc_code(
                    self.rm_master_db_path,
                    code_id=code_id,
                    unlock_code=new_code,
                    description=new_desc if new_desc else None,
                    user=self.current_user
                )
                
                self.status_bar.config(text=f"✅ Zaktualizowano kod", fg="#27ae60")
                self.load_plc_codes()
                dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można zaktualizować kodu:\n{e}")
        
        # Przyciski
        button_frame = tk.Frame(dialog)
        button_frame.grid(row=2, column=0, columnspan=2, pady=20)
        
        tk.Button(
            button_frame,
            text="✅ Zapisz",
            command=save_changes,
            bg=self.COLOR_GREEN,
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            button_frame,
            text="❌ Anuluj",
            command=dialog.destroy,
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 10),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
    
    def delete_plc_code(self):
        """Usuń kod PLC."""
        selection = self.plc_codes_tree.selection()
        if not selection:
            messagebox.showwarning("Brak wyboru", "Wybierz kod z listy.")
            return
        
        item = selection[0]
        tags = self.plc_codes_tree.item(item, 'tags')
        if not tags:
            messagebox.showerror("Błąd", "Nie można odczytać ID kodu.")
            return
        
        code_id = int(tags[0])
        values = self.plc_codes_tree.item(item, 'values')
        code_type = values[0]
        unlock_code = values[1]
        
        confirm = messagebox.askyesno(
            "Potwierdzenie",
            f"Czy na pewno usunąć kod?\n\nTyp: {code_type}\nKod: {unlock_code}"
        )
        
        if not confirm:
            return
        
        try:
            rmm.delete_plc_code(self.rm_master_db_path, code_id)
            self.status_bar.config(text=f"✅ Usunięto kod {code_type}", fg="#27ae60")
            self.load_plc_codes()
            
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie można usunąć kodu:\n{e}")
    
    def mark_plc_code_as_used(self):
        """Oznacz kod PLC jako użyty (przekazany klientowi)."""
        selection = self.plc_codes_tree.selection()
        if not selection:
            messagebox.showwarning("Brak wyboru", "Wybierz kod z listy.")
            return
        
        item = selection[0]
        tags = self.plc_codes_tree.item(item, 'tags')
        if not tags:
            messagebox.showerror("Błąd", "Nie można odczytać ID kodu.")
            return
        
        code_id = int(tags[0])
        values = self.plc_codes_tree.item(item, 'values')
        is_used = values[3]
        
        if is_used == "✅ TAK":
            messagebox.showinfo("Info", "Ten kod jest już oznaczony jako użyty.")
            return
        
        # Dialog z notką
        dialog = tk.Toplevel(self.root)
        dialog.title("Oznacz kod jako użyty")
        dialog.transient(self.root)
        dialog.grab_set()
        
        self._center_window(dialog, 400, 200)
        
        tk.Label(dialog, text="Notatka (opcjonalnie):", font=self.FONT_DEFAULT).pack(pady=10)
        notes_entry = tk.Entry(dialog, width=40, font=self.FONT_DEFAULT)
        notes_entry.pack(pady=5)
        
        def mark_used():
            notes = notes_entry.get().strip()
            
            try:
                rmm.mark_plc_code_as_used(
                    self.rm_master_db_path,
                    code_id=code_id,
                    user=self.current_user,
                    notes=notes if notes else None
                )
                
                self.status_bar.config(text=f"✅ Oznaczono kod jako użyty", fg="#27ae60")
                self.load_plc_codes()
                dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można oznaczyć kodu:\n{e}")
        
        # Przyciski
        button_frame = tk.Frame(dialog)
        button_frame.pack(pady=20)
        
        tk.Button(
            button_frame,
            text="✅ Oznacz",
            command=mark_used,
            bg=self.COLOR_GREEN,
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            button_frame,
            text="❌ Anuluj",
            command=dialog.destroy,
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 10),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
    
    def send_plc_code(self, code_id=None):
        """Dialog wysyłki kodu PLC (email/SMS).
        
        Args:
            code_id: ID kodu do wysłania (opcjonalny, jeśli None - pobiera z selekcji treeview)
        """
        # Jeśli nie podano code_id, pobierz z selekcji
        if code_id is None:
            selection = self.plc_codes_tree.selection()
            if not selection:
                messagebox.showwarning("Brak wyboru", "Wybierz kod z listy.")
                return
            
            item = selection[0]
            tags = self.plc_codes_tree.item(item, 'tags')
            if not tags:
                messagebox.showerror("Błąd", "Nie można odczytać ID kodu.")
                return
            
            code_id = int(tags[0])
            values = self.plc_codes_tree.item(item, 'values')
            code_type = values[0]
            unlock_code = values[1]
            is_used_display = values[3]  # "✅ TAK" lub "❌ NIE"
            
            # SPRAWDŹ CZY KOD JUŻ ZOSTAŁ UŻYTY
            if is_used_display == "✅ TAK":
                messagebox.showwarning(
                    "Kod już wysłany", 
                    f"⚠️ Ten kod został już wcześniej wysłany!\n\n"
                    f"Typ: {code_type}\n"
                    f"Kod: {unlock_code}\n\n"
                    f"Ponowne wysłanie tego samego kodu jest zablokowane."
                )
                return
        else:
            # Pobierz dane kodu z bazy
            try:
                codes = rmm.get_plc_codes(self.rm_master_db_path, self.selected_project_id)
                code_data = next((c for c in codes if c['id'] == code_id), None)
                if not code_data:
                    messagebox.showerror("Błąd", f"Nie znaleziono kodu o ID {code_id}")
                    return
                    
                # SPRAWDŹ CZY KOD JUŻ ZOSTAŁ UŻYTY
                if code_data['is_used']:
                    messagebox.showwarning(
                        "Kod już wysłany", 
                        f"⚠️ Ten kod został już wcześniej wysłany!\n\n"
                        f"Typ: {code_data['code_type']}\n"
                        f"Kod: {code_data['unlock_code']}\n"
                        f"Data wysłania: {code_data['used_at'] or 'nieznana'}\n\n"
                        f"Ponowne wysłanie tego samego kodu jest zablokowane."
                    )
                    return
                    
                code_type = code_data['code_type']
                unlock_code = code_data['unlock_code']
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie można pobrać danych kodu:\n{e}")
                return
        
        # Pobierz nazwę projektu i numer
        project_name = "???"
        project_number = "???"
        try:
            con = rmm._open_rm_connection(self.master_db_path)
            # Tabela projects w RM_BAZA - sprawdź czy kolumna to 'id' czy 'project_id'
            cursor = con.execute("PRAGMA table_info(projects)")
            columns = [row[1] for row in cursor.fetchall()]
            
            id_column = 'project_id' if 'project_id' in columns else 'id'
            
            row = con.execute(f"SELECT * FROM projects WHERE {id_column} = ?", (self.selected_project_id,)).fetchone()
            if row:
                # Tabela projects w RM_BAZA: name, project_id (sqlite3.Row używa [key] nie .get())
                project_name = row['name'] if 'name' in row.keys() else "???"
                project_number = str(self.selected_project_id)  # Używamy project_id jako numeru
                print(f"✅ Pobrano projekt: {project_number} - {project_name}")
            else:
                print(f"⚠️ Nie znaleziono projektu {self.selected_project_id} w bazie")
            con.close()
        except Exception as e:
            print(f"⚠️ Nie można pobrać nazwy projektu {self.selected_project_id}: {e}")
            import traceback
            traceback.print_exc()
        
        # Pobierz pracownika serwisu z etapu ODBIORY (pierwszy z assigned_staff)
        service_employee = "---"
        try:
            project_db = self.get_project_db_path(self.selected_project_id)
            if project_db and os.path.exists(project_db):
                print(f"🔍 Szukam pracownika Serwis w etapie ODBIORY...")
                staff_list = rmm.get_stage_assigned_staff(
                    project_db,
                    self.rm_master_db_path,
                    self.selected_project_id,
                    'ODBIORY'
                )
                print(f"   Znaleziono pracowników ODBIORY: {len(staff_list) if staff_list else 0}")
                if staff_list:
                    for emp in staff_list:
                        print(f"   - {emp.get('employee_name')} ({emp.get('category')})")
                
                if staff_list and len(staff_list) > 0:
                    # Znajdź pierwszego z kategorii Serwis
                    for emp in staff_list:
                        if emp.get('category') == 'Serwis':
                            service_employee = emp.get('employee_name', '???')
                            print(f"✅ Wybrany pracownik Serwis: {service_employee}")
                            break
                    # Jeśli nie ma z Serwisu - weź pierwszego
                    if service_employee == "---" and len(staff_list) > 0:
                        service_employee = staff_list[0].get('employee_name', '???')
                        print(f"⚠️ Brak pracownika Serwis, wybrany pierwszy: {service_employee}")
            else:
                print(f"⚠️ Brak pliku bazy projektu: {project_db}")
        except Exception as e:
            print(f"⚠️ Błąd pobierania pracownika Serwis: {e}")
            import traceback
            traceback.print_exc()
        
        # Dialog wysyłki
        dialog = tk.Toplevel(self.root)
        dialog.title("Wyślij kod PLC")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("700x800")
        
        # Informacje o kodzie
        info_frame = tk.LabelFrame(dialog, text="Kod do wysłania", font=("Arial", 10, "bold"), padx=10, pady=10)
        info_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(info_frame, text=f"Typ: {code_type}", font=self.FONT_DEFAULT, anchor='w').pack(fill=tk.X)
        tk.Label(info_frame, text=f"Kod: {unlock_code}", font=("Arial", 10, "bold"), anchor='w').pack(fill=tk.X)
        
        # Checkboxy: SMS i Email
        method_frame = tk.LabelFrame(dialog, text="Metoda wysyłki", font=("Arial", 10, "bold"), padx=10, pady=10)
        method_frame.pack(fill=tk.X, padx=10, pady=5)
        
        send_email_var = tk.BooleanVar(value=True)
        send_sms_var = tk.BooleanVar(value=True)
        
        tk.Checkbutton(
            method_frame,
            text="📧 Email",
            variable=send_email_var,
            font=self.FONT_DEFAULT
        ).pack(anchor='w', pady=2)
        
        tk.Checkbutton(
            method_frame,
            text="📱 SMS",
            variable=send_sms_var,
            font=self.FONT_DEFAULT
        ).pack(anchor='w', pady=2)
        
        # Nazwa nadawcy
        sender_frame = tk.Frame(dialog, padx=10)
        sender_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(sender_frame, text="Nazwa nadawcy:", font=self.FONT_DEFAULT).grid(row=0, column=0, sticky='w', pady=5)
        sender_entry = tk.Entry(sender_frame, width=40, font=self.FONT_DEFAULT)
        sender_entry.insert(0, "RM Manager - Kody PLC")
        sender_entry.grid(row=0, column=1, sticky='ew', pady=5, padx=(10, 0))
        sender_frame.columnconfigure(1, weight=1)
        
        # Tytuł email
        email_title_frame = tk.Frame(dialog, padx=10)
        email_title_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(email_title_frame, text="Tytuł email:", font=self.FONT_DEFAULT).grid(row=0, column=0, sticky='w', pady=5)
        email_title_entry = tk.Entry(email_title_frame, width=40, font=self.FONT_DEFAULT)
        email_title_entry.insert(0, f"KOD - {project_name}")
        email_title_entry.grid(row=0, column=1, sticky='ew', pady=5, padx=(10, 0))
        email_title_frame.columnconfigure(1, weight=1)
        
        # Lista odbiorców
        recipients_frame = tk.LabelFrame(dialog, text="Odbiorcy (globalni dla wszystkich projektów)", font=("Arial", 10, "bold"), padx=10, pady=10)
        recipients_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Wczytaj GLOBALNE odbiorcy (wspólne dla wszystkich projektów RM_MANAGER)
        selected_recipients = []
        try:
            print(f"\n🔍 LOAD RECIPIENTS: rm_master_db={self.rm_master_db_path}, code_id={code_id}")
            saved_recipient_ids = rmm.get_plc_code_recipients(self.rm_master_db_path, code_id)
            print(f"   saved_recipient_ids={saved_recipient_ids}")
            
            if saved_recipient_ids:
                # Pobierz szczegóły pracowników
                all_employees = rmm.get_employees(self.rm_master_db_path, active_only=False)
                print(f"   all_employees count={len(all_employees)}")
                for emp in all_employees:
                    if emp['id'] in saved_recipient_ids:
                        selected_recipients.append({
                            'id': emp['id'],
                            'name': emp['name'],
                            'category': emp.get('category', ''),
                            'email': emp.get('email', '') or emp.get('contact_info', ''),
                            'phone': emp.get('phone', '')
                        })
                print(f"✅ Wczytano {len(selected_recipients)} globalnych odbiorców")
            else:
                print(f"⚠️ Brak zapisanych globalnych odbiorców")
        except Exception as e:
            print(f"❌ Nie można wczytać zapisanych odbiorców: {e}")
            import traceback
            traceback.print_exc()
        
        recipients_text = tk.Text(recipients_frame, height=3, width=50, font=self.FONT_DEFAULT, state='disabled', bg='#f0f0f0')
        recipients_text.pack(fill=tk.X, pady=5)
        
        def update_recipients_display():
            recipients_text.config(state='normal')
            recipients_text.delete('1.0', tk.END)
            if selected_recipients:
                names = [r['name'] for r in selected_recipients]
                recipients_text.insert('1.0', ', '.join(names))
            else:
                recipients_text.insert('1.0', "(brak wybranych odbiorców)")
            recipients_text.config(state='disabled')
        
        def select_recipients():
            nonlocal selected_recipients
            
            # Dialog wyboru pracowników
            select_dialog = tk.Toplevel(dialog)
            select_dialog.title("Wybierz odbiorców (globalni dla wszystkich projektów)")
            select_dialog.transient(dialog)
            select_dialog.grab_set()
            
            self._center_window(select_dialog, 500, 600)
            
            # Frame z listą
            list_frame = tk.Frame(select_dialog)
            list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Scrollbar
            scrollbar = tk.Scrollbar(list_frame)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Canvas dla checkboxów
            canvas = tk.Canvas(list_frame, yscrollcommand=scrollbar.set)
            canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.config(command=canvas.yview)
            
            # Frame wewnętrzny
            inner_frame = tk.Frame(canvas)
            canvas.create_window((0, 0), window=inner_frame, anchor='nw')
            
            # Pobierz wszystkich pracowników
            try:
                employees = rmm.get_employees(self.rm_master_db_path, active_only=True)
                if not employees:
                    print(f"⚠️ Brak pracowników w bazie: {self.rm_master_db_path}")
            except Exception as e:
                print(f"⚠️ Błąd pobierania pracowników: {e}")
                import traceback
                traceback.print_exc()
                employees = []
            
            # Zmienne checkboxów
            checkbox_vars = {}
            
            for emp in employees:
                emp_id = emp['id']
                emp_name = emp['name']
                emp_category = emp.get('category', '')
                
                var = tk.BooleanVar(value=False)
                # Sprawdź czy już wybrany
                if any(r['id'] == emp_id for r in selected_recipients):
                    var.set(True)
                
                checkbox_vars[emp_id] = (var, emp_name, emp_category, emp)
                
                cb = tk.Checkbutton(
                    inner_frame,
                    text=f"{emp_name} ({emp_category})",
                    variable=var,
                    font=self.FONT_DEFAULT
                )
                cb.pack(anchor='w', pady=2, padx=5)
            
            inner_frame.update_idletasks()
            canvas.config(scrollregion=canvas.bbox('all'))
            
            def confirm_selection():
                selected_recipients.clear()
                for emp_id, (var, name, category, emp) in checkbox_vars.items():
                    if var.get():
                        selected_recipients.append({
                            'id': emp_id,
                            'name': name,
                            'category': category,
                            'email': emp.get('email', '') or emp.get('contact_info', ''),
                            'phone': emp.get('phone', '')
                        })
                
                # Zapisz odbiorców do bazy (persistence) - dla WSZYSTKICH kodów tego projektu
                try:
                    recipient_ids = [r['id'] for r in selected_recipients]
                    # Zapisz GLOBALNIE (dla wszystkich projektów RM_MANAGER)
                    rmm.save_plc_code_recipients(self.rm_master_db_path, code_id, recipient_ids)
                    print(f"✅ Zapisano {len(recipient_ids)} globalnych odbiorców")
                except Exception as e:
                    print(f"⚠️ Nie można zapisać globalnych odbiorców: {e}")
                
                update_recipients_display()
                select_dialog.destroy()
            
            # Przyciski
            btn_frame = tk.Frame(select_dialog)
            btn_frame.pack(fill=tk.X, padx=10, pady=10)
            
            tk.Button(
                btn_frame,
                text="✔️ Zatwierdź",
                command=confirm_selection,
                bg=self.COLOR_GREEN,
                fg="white",
                font=("Arial", 10, "bold"),
                padx=20
            ).pack(side=tk.LEFT, padx=5)
            
            tk.Button(
                btn_frame,
                text="❌ Anuluj",
                command=select_dialog.destroy,
                bg=self.COLOR_TOPBAR,
                fg="white",
                font=("Arial", 10),
                padx=20
            ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            recipients_frame,
            text="👥 Wybierz odbiorców",
            command=select_recipients,
            bg="#3498db",
            fg="white",
            font=self.FONT_DEFAULT,
            padx=10
        ).pack(pady=5)
        
        update_recipients_display()
        
        # Treść wiadomości
        message_frame = tk.LabelFrame(dialog, text="Treść wiadomości", font=("Arial", 10, "bold"), padx=10, pady=10)
        message_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Auto-generowana część
        auto_text = f"""{project_name}
Kod: {unlock_code}
{service_employee}
{code_type}"""
        
        tk.Label(message_frame, text=auto_text, font=self.FONT_DEFAULT, anchor='w', justify='left').pack(fill=tk.X, pady=5)
        
        # Opis (edytowalne pole)
        tk.Label(message_frame, text="Dodatkowy opis:", font=self.FONT_DEFAULT).pack(anchor='w', pady=(10, 5))
        desc_text = tk.Text(message_frame, height=3, width=50, font=self.FONT_DEFAULT)
        desc_text.pack(fill=tk.X, pady=5)
        
        def send_code():
            send_email = send_email_var.get()
            send_sms = send_sms_var.get()
            sender_name = sender_entry.get().strip()
            email_title = email_title_entry.get().strip()
            description = desc_text.get('1.0', tk.END).strip()
            
            # Walidacja
            if not send_email and not send_sms:
                messagebox.showwarning("Brak metody", "Wybierz przynajmniej Email lub SMS.")
                return
            
            if not selected_recipients:
                messagebox.showwarning("Brak odbiorców", "Wybierz odbiorców wiadomości.")
                return
            
            if not sender_name:
                messagebox.showwarning("Brak nadawcy", "Podaj nazwę nadawcy.")
                return
            
            # Buduj pełną treść
            full_message = f"""{project_name}
Kod: {unlock_code}
{service_employee}
{code_type}
{description}"""
            
            # Email subject (z edytowalnego pola)
            email_subject = email_title if email_title else f"KOD - {project_name}"
            
            # Przygotuj listy odbiorców
            recipient_emails = [r['email'] for r in selected_recipients if r.get('email')]
            recipient_phones = [r['phone'] for r in selected_recipients if r.get('phone')]
            
            print(f"\n📤 WYSYŁKA KODU PLC:")
            print(f"   Odbiorcy: {[r['name'] for r in selected_recipients]}")
            print(f"   Emails: {recipient_emails}")
            print(f"   Phones: {recipient_phones}")
            print(f"   Send email: {send_email}, Send SMS: {send_sms}")
            
            # Walidacja odbiorców dla wybranych metod
            if send_email and not recipient_emails:
                messagebox.showwarning("Brak emaili", "Wybrani odbiorcy nie mają adresów email.")
                return
            
            if send_sms and not recipient_phones:
                messagebox.showwarning("Brak telefonów", "Wybrani odbiorcy nie mają numerów telefonów.")
                return
            
            # PRAWDZIWA WYSYŁKA
            # Sprawdź uprawnienia w GUI (ADMIN ma zawsze dostęp)
            auth_user = None if self.current_user_role == 'ADMIN' else self.current_user
            
            # Zamknij dialog OD RAZU po kliknięciu Wyślij
            dialog.destroy()
            
            # Wysyłka w osobnym wątku (żeby GUI się nie zawieszało)
            import threading
            
            self.status_bar.config(text="⏳ Wysyłanie kodu PLC...", fg="#f39c12")
            
            def _do_send():
                success = True
                errors = []
                
                print("🔄 Wątek wysyłki START")
                try:
                    # Wyślij EMAIL
                    if send_email:
                        try:
                            print(f"📧 Wysyłam email do: {recipient_emails}")
                            rmm.send_plc_code_email(
                                rm_db_path=self.rm_master_db_path,
                                code_id=code_id,
                                recipient_emails=recipient_emails,
                                subject=email_subject,
                                message=full_message,
                                user=auth_user
                            )
                            print(f"✅ Email wysłany do {len(recipient_emails)} odbiorców")
                        except Exception as e:
                            import traceback
                            traceback.print_exc()
                            errors.append(f"Email: {str(e)}")
                            success = False
                    
                    # Wyślij SMS
                    if send_sms:
                        try:
                            print(f"📱 Wysyłam SMS do: {recipient_phones}")
                            rmm.send_plc_code_sms(
                                rm_db_path=self.rm_master_db_path,
                                code_id=code_id,
                                phone_numbers=recipient_phones,
                                message=full_message,
                                user=auth_user,
                                sms_config=self.config
                            )
                            print(f"✅ SMS wysłany do {len(recipient_phones)} odbiorców")
                        except Exception as e:
                            import traceback
                            traceback.print_exc()
                            errors.append(f"SMS: {str(e)}")
                            success = False
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    errors.append(f"Błąd ogólny: {str(e)}")
                    success = False
                
                print(f"🏁 Wątek wysyłki KONIEC: success={success}, errors={errors}")
                
                # Wyniki - z powrotem w głównym wątku Tkinter
                def _show_result():
                    if success:
                        methods = []
                        if send_email:
                            methods.append(f"Email ({len(recipient_emails)})")
                        if send_sms:
                            methods.append(f"SMS ({len(recipient_phones)})")
                        
                        self.status_bar.config(text=f"✅ Wysłano kod PLC do {len(selected_recipients)} odbiorców", fg="#27ae60")
                        self.load_plc_codes()
                        
                        recipients_names = ', '.join([r['name'] for r in selected_recipients])
                        messagebox.showinfo(
                            "Wysłano kod PLC",
                            f"✅ Kod został wysłany!\n\n"
                            f"Metoda: {' + '.join(methods)}\n"
                            f"Odbiorcy: {recipients_names}\n"
                            f"Nadawca: {sender_name}"
                        )
                    else:
                        error_msg = '\n'.join(errors)
                        messagebox.showerror(
                            "Błąd wysyłki",
                            f"❌ Wystąpiły błędy podczas wysyłki:\n\n{error_msg}"
                        )
                        self.status_bar.config(text="❌ Błąd wysyłki kodu PLC", fg="#e74c3c")
                
                self.root.after(0, _show_result)
            
            threading.Thread(target=_do_send, daemon=True).start()
        
        # Przyciski
        button_frame = tk.Frame(dialog, pady=10)
        button_frame.pack(fill=tk.X)
        
        tk.Button(
            button_frame,
            text="📤 Wyślij",
            command=send_code,
            bg=self.COLOR_GREEN,
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=10)
        
        tk.Button(
            button_frame,
            text="❌ Anuluj",
            command=dialog.destroy,
            bg=self.COLOR_TOPBAR,
            fg="white",
            font=("Arial", 10),
            padx=20,
            pady=5
        ).pack(side=tk.LEFT, padx=5)
        
        # Wymuś odświeżenie okna
        dialog.update_idletasks()


# ============================================================================
# Main
# ============================================================================

def main():
    import signal
    import atexit

    # Użyj TkinterDnD.Tk() jeśli drag-and-drop dostępny
    if HAS_DND:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    
    app = RMManagerGUI(root)

    # Zabezpieczenie: cleanup locków przy jakimkolwiek wyjściu (crash, Ctrl+C, kill)
    # Wzór z RM_BAZA - działa nawet przy awaryjnym zamknięciu
    def cleanup_on_exit():
        """Zwolnij wszystkie locki przy zamykaniu (nawet awaryjnym)"""
        try:
            if hasattr(app, 'lock_manager') and app.lock_manager:
                print("\n🧹 ATEXIT: Czyszczenie locków...")
                app.lock_manager.cleanup_all_my_locks()
        except Exception as e:
            print(f"⚠️ ATEXIT cleanup error: {e}")

    def signal_handler(sig, frame):
        """Obsługa Ctrl+C i innych sygnałów"""
        print(f"\n⚠️  Otrzymano sygnał {sig} - czyszczenie i zamykanie...")
        cleanup_on_exit()
        import sys
        sys.exit(0)

    atexit.register(cleanup_on_exit)
    signal.signal(signal.SIGINT, signal_handler)    # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)   # kill

    root.mainloop()


if __name__ == "__main__":
    main()
