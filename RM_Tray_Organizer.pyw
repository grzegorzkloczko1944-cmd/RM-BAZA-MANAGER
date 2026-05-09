#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RM Tray Organizer
System Tray aplikacja do zarządzania wszystkimi aplikacjami RM_*.

Funkcje:
- Ikona w zasobniku systemowym
- Menu do uruchamiania/zatrzymywania aplikacji
- Autostart przy starcie Windows
- Monitoring działających procesów
"""

import sys
import os
import subprocess
import json
import winreg
import sqlite3
import hashlib
import re
import time
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List
from PyQt5.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QAction,
    QMessageBox, QDialog, QVBoxLayout, QCheckBox,
    QPushButton, QLabel, QHBoxLayout, QFileDialog,
    QLineEdit, QGridLayout, QGroupBox, QInputDialog,
    QComboBox, QScrollArea, QWidget, QFrame, QSizePolicy,
    QTextEdit, QSplitter
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QCursor

try:
    # Windows API do wymuszania widoczności ikony w tray
    import ctypes
    from ctypes import wintypes
    _has_win32 = True
except ImportError:
    _has_win32 = False

# ============================================================================
# KONFIGURACJA APLIKACJI
# ============================================================================

APPLICATIONS = {
    "RM_BAZA": {
        "name": "RM BAZA",
        "description": "Baza danych",
        "file": "RM_BAZA.py",
        "exe": "RM_BAZA.exe",
    },
    "RM_MANAGER": {
        "name": "RM MANAGER",
        "description": "Menedżer systemu",
        "file": "RM_MANAGER.py",
        "exe": "RM_MANAGER.exe",
    },
    "RM_ALARM": {
        "name": "RM ALARM",
        "description": "System alarmów",
        "file": "RM_ALARM.py",
        "exe": "RM_ALARM.exe",
    },
    "RM_COPY": {
        "name": "RM COPY",
        "description": "Kopiowanie plików",
        "file": "RM_COPY.py",
        "exe": "RM_COPY.exe",
    },
    "RM_IMPORT": {
        "name": "RM IMPORT",
        "description": "Import danych",
        "file": "RM_IMPORT.py",
        "exe": "RM_IMPORT.exe",
    },
    "RM_MONITOR": {
        "name": "RM MONITOR",
        "description": "Monitoring systemu",
        "file": "RM_MONITOR.py",
        "exe": "RM_MONITOR.exe",
    },
    "RM_Transfer_Project_AUTO": {
        "name": "RM Transfer AUTO",
        "description": "Transfer projektów (AUTO)",
        "file": "RM_Transfer_Project_AUTO.py",
        "exe": "RM_Transfer_Project_AUTO.exe",
    },
    "RM_Transfer_Project_FULL": {
        "name": "RM Transfer FULL",
        "description": "Transfer projektów (FULL)",
        "file": "RM_Transfer_Project _FULL.py",
        "exe": "RM_Transfer_Project_FULL.exe",
    },
    "RM_BIB_TRZEP": {
        "name": "RM BIB TRZEP",
        "description": "Trzepanie biblioteki",
        "file": "RM_BIB_TRZEP.py",
        "exe": "RM_BIB_TRZEP.exe",
    },
}

# Określ lokalizację pliku konfiguracyjnego
# Dla skompilowanej aplikacji (PyInstaller) - katalog obok .exe
# Dla normalnego skryptu - katalog obok .py/.pyw
if getattr(sys, 'frozen', False):
    # Aplikacja skompilowana - użyj katalogu gdzie jest .exe
    CONFIG_FILE = Path(sys.executable).parent / "rm_tray_config.json"
else:
    # Normalny skrypt - użyj katalogu gdzie jest .py/.pyw
    CONFIG_FILE = Path(__file__).parent / "rm_tray_config.json"

AUTOSTART_NAME = "RM_Tray_Organizer"

# ============================================================================
# FUNKCJE POMOCNICZE
# ============================================================================

def get_app_directory() -> Path:
    """Zwróć katalog gdzie znajduje się aplikacja (.exe lub .py/.pyw)."""
    if getattr(sys, 'frozen', False):
        # Aplikacja skompilowana (PyInstaller) - katalog gdzie jest .exe
        return Path(sys.executable).parent
    else:
        # Normalny skrypt Python - katalog gdzie jest .py/.pyw
        return Path(__file__).parent


def get_all_applications() -> Dict:
    """Zwróć wszystkie aplikacje (podstawowe + niestandardowe)."""
    config = load_config()
    custom_apps = config.get("custom_apps", {})
    
    # Połącz podstawowe aplikacje z niestandardowymi
    all_apps = APPLICATIONS.copy()
    all_apps.update(custom_apps)
    
    return all_apps


def get_app_path(app_id: str) -> Optional[Path]:
    """Znajdź ścieżkę do aplikacji (.exe lub .py)."""
    # Najpierw sprawdź zapisaną ścieżkę w konfiguracji
    config = load_config()
    app_paths = config.get("app_paths", {})
    
    if app_id in app_paths:
        saved_path = Path(app_paths[app_id])
        if saved_path.exists():
            return saved_path
    
    # Jeśli nie ma zapisanej ścieżki, szukaj w katalogu organizera
    app_dir = get_app_directory()
    all_apps = get_all_applications()
    app_info = all_apps.get(app_id, {})
    
    # Najpierw szukaj .exe
    exe_name = app_info.get("exe")
    if exe_name:
        exe_path = app_dir / exe_name
        if exe_path.exists():
            return exe_path
    
    # Potem .py
    py_name = app_info.get("file")
    if py_name:
        py_path = app_dir / py_name
        if py_path.exists():
            return py_path
    
    return None


def is_autostart_enabled() -> bool:
    """Sprawdź czy autostart jest włączony w rejestrze Windows."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ
        )
        try:
            winreg.QueryValueEx(key, AUTOSTART_NAME)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception:
        return False


def set_autostart(enabled: bool) -> bool:
    """Włącz/wyłącz autostart w rejestrze Windows."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE
        )
        
        if enabled:
            # Dodaj do autostartu
            exe_path = sys.executable
            script_path = Path(__file__).resolve()
            
            # Jeśli uruchomione jako .exe (PyInstaller)
            if getattr(sys, 'frozen', False):
                cmd = f'"{exe_path}"'
            else:
                # Uruchomione jako .pyw przez pythonw.exe
                cmd = f'"{exe_path}" "{script_path}"'
            
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, cmd)
        else:
            # Usuń z autostartu
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass
        
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"Błąd ustawiania autostartu: {e}")
        return False


def load_config() -> Dict:
    """Wczytaj konfigurację z pliku JSON."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {"autostart_apps": [], "app_paths": {}, "custom_apps": {}, "visible_apps": [],
            "master_sqlite_path": "", "server_apps_path": ""}


def get_master_sqlite_path() -> Optional[Path]:
    """Zwróć ścieżkę do master.sqlite z konfiguracji (lub None)."""
    p = load_config().get("master_sqlite_path", "").strip()
    if p:
        path = Path(p)
        if path.exists():
            return path
    return None


def get_chat_dir() -> Optional[Path]:
    """Zwróć katalog z plikami JSON chatu (podfolder 'chat' obok master.sqlite)."""
    mp = get_master_sqlite_path()
    if mp:
        return mp.parent / "chat"
    return None


def get_users_from_master() -> List[Dict]:
    """Wczytaj aktywnych użytkowników z master.sqlite."""
    mp = get_master_sqlite_path()
    if not mp:
        return []
    try:
        con = sqlite3.connect(str(mp), timeout=5)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, username, display_name, role, password_hash "
            "FROM users WHERE is_active = 1 ORDER BY username"
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"⚠️  get_users_from_master: {e}")
        return []


def verify_password(password: str, stored_hash: str) -> bool:
    """Sprawdź hasło (SHA-256)."""
    if not stored_hash:
        return True  # Brak hasła → wolny dostęp
    return hashlib.sha256(password.encode()).hexdigest() == stored_hash


def save_config(config: Dict):
    """Zapisz konfigurację do pliku JSON."""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Błąd zapisu konfiguracji: {e}")


def create_icon() -> QIcon:
    """Stwórz domyślną ikonę dla tray (niebieskie 'RM')."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    
    # Tło - niebieski okrąg
    painter.setBrush(QColor(30, 144, 255))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, 60, 60)
    
    # Tekst "RM"
    painter.setPen(QColor(255, 255, 255))
    font = QFont("Arial", 24, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "RM")
    
    painter.end()
    
    return QIcon(pixmap)


# ============================================================================
# DIALOG DODAWANIA NOWEJ APLIKACJI
# ===========================================================================

class AddAppDialog(QDialog):
    """Dialog dodawania nowej aplikacji."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dodaj nową aplikację")
        self.setModal(True)
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout()
        
        # Nazwa aplikacji
        layout.addWidget(QLabel("<b>Nazwa aplikacji:</b>"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("np. RM NOWA APP")
        layout.addWidget(self.name_input)
        
        layout.addSpacing(10)
        
        # Opis aplikacji
        layout.addWidget(QLabel("<b>Opis:</b>"))
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("np. Nowa funkcjonalność")
        layout.addWidget(self.desc_input)
        
        layout.addSpacing(10)
        
        # Ścieżka do pliku
        layout.addWidget(QLabel("<b>Plik aplikacji:</b>"))
        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Wybierz plik .exe lub .py")
        self.path_input.setReadOnly(True)
        path_layout.addWidget(self.path_input)
        
        browse_btn = QPushButton("Przeglądaj...")
        browse_btn.clicked.connect(self.browse_file)
        path_layout.addWidget(browse_btn)
        
        layout.addLayout(path_layout)
        
        layout.addSpacing(20)
        
        # Przyciski
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Dodaj")
        add_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def browse_file(self):
        """Wybierz plik aplikacji."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz plik aplikacji",
            str(get_app_directory()),
            "Pliki wykonywalne (*.exe *.py *.pyw);;Wszystkie pliki (*.*)"
        )
        
        if file_path:
            self.path_input.setText(file_path)
    
    def get_app_data(self):
        """Zwróć dane wprowadzone przez użytkownika."""
        name = self.name_input.text().strip()
        desc = self.desc_input.text().strip()
        path = self.path_input.text().strip()
        
        if not name or not path:
            return None
        
        # Wygeneruj app_id z nazwy
        app_id = "CUSTOM_" + name.upper().replace(" ", "_")
        
        # Wyciągnij nazwę pliku z pełnej ścieżki
        file_name = Path(path).name
        
        return {
            "app_id": app_id,
            "name": name,
            "description": desc or "Aplikacja niestandardowa",
            "file": file_name,
            "exe": file_name if file_name.endswith('.exe') else "",
        }


# ============================================================================
# DIALOG USTAWIEŃ
# ============================================================================

class SettingsDialog(QDialog):
    """Dialog ustawień autostartu aplikacji."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ustawienia RM Tray Organizer")
        self.setModal(True)
        self.setMinimumWidth(1400)
        self.setMinimumHeight(700)
        
        layout = QVBoxLayout()

        # RM_BAZA – master.sqlite
        layout.addWidget(QLabel("<b>Połączenie z RM_BAZA (chat / logowanie):</b>"))
        mb_group = QGroupBox("Plik master.sqlite")
        mb_layout = QHBoxLayout()
        cfg = load_config()

        self.master_sqlite_input = QLineEdit()
        self.master_sqlite_input.setPlaceholderText("Ścieżka do master.sqlite (np. Y:/RM_BAZA/master.sqlite)")
        self.master_sqlite_input.setReadOnly(True)
        mb_path = cfg.get("master_sqlite_path", "")
        if mb_path:
            self.master_sqlite_input.setText(mb_path)
        mb_layout.addWidget(self.master_sqlite_input)

        mb_browse = QPushButton("Wybierz...")
        mb_browse.clicked.connect(self._browse_master_sqlite)
        mb_layout.addWidget(mb_browse)

        mb_clear = QPushButton("Wyczyść")
        mb_clear.clicked.connect(lambda: self.master_sqlite_input.clear())
        mb_layout.addWidget(mb_clear)

        mb_group.setLayout(mb_layout)
        layout.addWidget(mb_group)

        layout.addSpacing(10)

        # Serwer – katalog z plikami aplikacji
        layout.addWidget(QLabel("<b>Katalog aktualizacji aplikacji (serwer):</b>"))
        sa_group = QGroupBox("Katalog z plikami aplikacji na serwerze")
        sa_layout = QHBoxLayout()

        self.server_apps_input = QLineEdit()
        self.server_apps_input.setPlaceholderText("Ścieżka do katalogu z aplikacjami (np. Y:/RM_APPS/)")
        self.server_apps_input.setReadOnly(True)
        sa_path = cfg.get("server_apps_path", "")
        if sa_path:
            self.server_apps_input.setText(sa_path)
        sa_layout.addWidget(self.server_apps_input)

        sa_browse = QPushButton("Wybierz...")
        sa_browse.clicked.connect(self._browse_server_apps)
        sa_layout.addWidget(sa_browse)

        sa_clear = QPushButton("Wyczyść")
        sa_clear.clicked.connect(lambda: self.server_apps_input.clear())
        sa_layout.addWidget(sa_clear)

        sa_group.setLayout(sa_layout)
        layout.addWidget(sa_group)

        layout.addSpacing(10)

        # Autostart organizera
        layout.addWidget(QLabel("<b>Autostart systemu:</b>"))
        self.autostart_checkbox = QCheckBox("Uruchom RM Tray Organizer przy starcie Windows")
        self.autostart_checkbox.setChecked(is_autostart_enabled())
        layout.addWidget(self.autostart_checkbox)
        
        layout.addSpacing(20)
        
        # Zarządzanie aplikacjami
        layout.addWidget(QLabel("<b>Zarządzanie aplikacjami:</b>"))
        
        manage_layout = QHBoxLayout()
        add_app_btn = QPushButton("➕ Dodaj nową aplikację")
        add_app_btn.clicked.connect(self.add_new_app)
        manage_layout.addWidget(add_app_btn)
        
        remove_app_btn = QPushButton("➖ Usuń aplikację niestandardową")
        remove_app_btn.clicked.connect(self.remove_custom_app)
        manage_layout.addWidget(remove_app_btn)
        manage_layout.addStretch()
        
        layout.addLayout(manage_layout)
        
        layout.addSpacing(10)
        
        # Ścieżki do aplikacji
        layout.addWidget(QLabel("<b>Ścieżki do aplikacji:</b>"))
        layout.addWidget(QLabel("<i>Wybierz pliki .exe lub .py dla każdej aplikacji:</i>"))
        
        layout.addSpacing(10)
        
        config = load_config()
        app_paths = config.get("app_paths", {})
        all_apps = get_all_applications()
        
        # Grupa ze ścieżkami
        paths_group = QGroupBox("Pliki aplikacji")
        paths_layout = QGridLayout()
        
        self.path_inputs = {}
        row = 0
        
        for app_id, app_info in all_apps.items():
            # Nazwa aplikacji
            name_label = QLabel(f"{app_info['name']}:")
            paths_layout.addWidget(name_label, row, 0)
            
            # Pole tekstowe ze ścieżką
            path_input = QLineEdit()
            current_path = get_app_path(app_id)
            if current_path:
                path_input.setText(str(current_path))
            elif app_id in app_paths:
                path_input.setText(app_paths[app_id])
            path_input.setPlaceholderText("Nie wybrano pliku")
            path_input.setReadOnly(True)
            paths_layout.addWidget(path_input, row, 1)
            
            # Przycisk wyboru pliku
            browse_btn = QPushButton("Wybierz...")
            browse_btn.clicked.connect(lambda checked, aid=app_id, inp=path_input: self.browse_file(aid, inp))
            paths_layout.addWidget(browse_btn, row, 2)
            
            # Przycisk wyczyść
            clear_btn = QPushButton("Wyczyść")
            clear_btn.clicked.connect(lambda checked, inp=path_input: inp.clear())
            paths_layout.addWidget(clear_btn, row, 3)

            # Przycisk aktualizuj
            update_btn = QPushButton("Aktualizuj")
            update_btn.setToolTip("Skopiuj plik z katalogu serwera do lokalnej ścieżki")
            update_btn.clicked.connect(lambda checked, aid=app_id, inp=path_input: self._update_app(aid, inp))
            paths_layout.addWidget(update_btn, row, 4)

            self.path_inputs[app_id] = path_input
            row += 1
        
        paths_group.setLayout(paths_layout)
        layout.addWidget(paths_group)
        
        layout.addSpacing(20)
        
        # Autostart aplikacji i widoczność
        layout.addWidget(QLabel("<b>Automatyczne uruchamianie aplikacji:</b>"))
        layout.addWidget(QLabel("<i>Zaznacz aplikacje, które mają być uruchamiane automatycznie<br/>po starcie RM Tray Organizer oraz które mają być widoczne w menu:</i>"))
        
        layout.addSpacing(10)
        
        autostart_apps = config.get("autostart_apps", [])
        visible_apps = config.get("visible_apps", [])
        
        # Jeśli visible_apps jest puste (pierwszy raz), domyślnie wszystkie widoczne
        if not visible_apps:
            visible_apps = list(all_apps.keys())
        
        # Grupa aplikacji
        apps_group = QGroupBox("Aplikacje")
        apps_grid = QGridLayout()
        apps_grid.addWidget(QLabel("<b>Aplikacja</b>"), 0, 0)
        apps_grid.addWidget(QLabel("<b>Autostart</b>"), 0, 1)
        apps_grid.addWidget(QLabel("<b>Widoczna</b>"), 0, 2)
        
        self.app_autostart_checkboxes = {}
        self.app_visible_checkboxes = {}
        
        row = 1
        for app_id, app_info in all_apps.items():
            # Nazwa aplikacji
            name_label = QLabel(f"{app_info['name']} - {app_info['description']}")
            apps_grid.addWidget(name_label, row, 0)
            
            # Checkbox autostart
            autostart_cb = QCheckBox()
            autostart_cb.setChecked(app_id in autostart_apps)
            self.app_autostart_checkboxes[app_id] = autostart_cb
            apps_grid.addWidget(autostart_cb, row, 1)
            
            # Checkbox widoczność
            visible_cb = QCheckBox()
            visible_cb.setChecked(app_id in visible_apps)
            self.app_visible_checkboxes[app_id] = visible_cb
            apps_grid.addWidget(visible_cb, row, 2)
            
            row += 1
        
        apps_group.setLayout(apps_grid)
        layout.addWidget(apps_group)
        
        layout.addSpacing(20)
        
        # Przyciski
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Zapisz")
        save_btn.clicked.connect(self.save_settings)
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def _browse_master_sqlite(self):
        """Wybierz plik master.sqlite."""
        current = self.master_sqlite_input.text()
        start_dir = str(Path(current).parent) if current and Path(current).exists() else str(get_app_directory())
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Wskaż plik master.sqlite",
            start_dir,
            "SQLite (*.sqlite *.db);;Wszystkie pliki (*.*)"
        )
        if file_path:
            self.master_sqlite_input.setText(file_path)

    def _browse_server_apps(self):
        """Wybierz katalog z aplikacjami na serwerze."""
        current = self.server_apps_input.text()
        start_dir = current if current and Path(current).exists() else str(get_app_directory())
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Wskaż katalog z aplikacjami na serwerze",
            start_dir,
        )
        if dir_path:
            self.server_apps_input.setText(dir_path)

    def _update_app(self, app_id: str, path_input: QLineEdit):
        """Skopiuj plik aplikacji z serwera do lokalnej ścieżki."""
        local_path_str = path_input.text().strip()
        if not local_path_str:
            QMessageBox.warning(
                self, "Brak ścieżki lokalnej",
                "Nie podano lokalnej ścieżki docelowej.\nNajpierw wybierz plik przez 'Wybierz...'"
            )
            return

        server_dir_str = self.server_apps_input.text().strip()
        if not server_dir_str:
            QMessageBox.warning(
                self, "Brak ścieżki serwera",
                "Nie ustawiono katalogu z aplikacjami na serwerze.\n"
                "Ustaw ścieżkę w sekcji 'Katalog aktualizacji aplikacji (serwer)'."
            )
            return

        server_dir = Path(server_dir_str)
        if not server_dir.exists():
            QMessageBox.warning(self, "Błąd", f"Katalog serwera nie istnieje:\n{server_dir}")
            return

        local_path = Path(local_path_str)
        filename = local_path.name
        server_file = server_dir / filename

        if not server_file.exists():
            QMessageBox.warning(
                self, "Brak pliku na serwerze",
                f"Nie znaleziono pliku na serwerze:\n{server_file}"
            )
            return

        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(server_file), str(local_path))
            all_apps = get_all_applications()
            app_name = all_apps.get(app_id, {}).get('name', app_id)
            QMessageBox.information(
                self, "Zaktualizowano",
                f"Plik '{app_name}' został zaktualizowany.\n\n"
                f"Źródło:  {server_file}\n"
                f"Cel:     {local_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Błąd kopiowania", f"Nie udało się skopiować pliku:\n{e}")

    def browse_file(self, app_id: str, path_input: QLineEdit):
        """Otwórz dialog wyboru pliku dla aplikacji."""
        all_apps = get_all_applications()
        app_info = all_apps[app_id]
        
        # Filtr plików
        file_filter = "Pliki wykonywalne (*.exe *.py *.pyw);;Wszystkie pliki (*.*)"
        
        # Domyślny katalog
        current_path = path_input.text()
        if current_path and Path(current_path).exists():
            start_dir = str(Path(current_path).parent)
        else:
            start_dir = str(get_app_directory())
        
        # Otwórz dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Wybierz plik dla {app_info['name']}",
            start_dir,
            file_filter
        )
        
        if file_path:
            path_input.setText(file_path)
    
    def add_new_app(self):
        """Dodaj nową aplikację niestandardową."""
        dialog = AddAppDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            app_data = dialog.get_app_data()
            if app_data:
                # Wczytaj konfigurację
                config = load_config()
                custom_apps = config.get("custom_apps", {})
                app_paths = config.get("app_paths", {})
                
                # Dodaj nową aplikację
                app_id = app_data.pop("app_id")
                custom_apps[app_id] = app_data
                
                # Dodaj ścieżkę z dialogu
                app_paths[app_id] = dialog.path_input.text()
                
                # Zapisz i odświeź
                config["custom_apps"] = custom_apps
                config["app_paths"] = app_paths
                save_config(config)
                
                # Zamknij i otwórz ponownie dialog ustawień
                self.accept()
                
                # Informacja dla użytkownika
                QMessageBox.information(
                    self,
                    "Aplikacja dodana",
                    f"Aplikacja '{app_data['name']}' została dodana.\nOtwórz Ustawienia ponownie aby zobaczyć zmiany."
                )
    
    def remove_custom_app(self):
        """Usuń aplikację niestandardową."""
        config = load_config()
        custom_apps = config.get("custom_apps", {})
        
        if not custom_apps:
            QMessageBox.information(
                self,
                "Brak aplikacji",
                "Brak niestandardowych aplikacji do usunięcia."
            )
            return
        
        # Lista aplikacji do wyboru
        app_names =  [f"{app_id}: {info['name']}" for app_id, info in custom_apps.items()]
        
        choice, ok = QInputDialog.getItem(
            self,
            "Usuń aplikację",
            "Wybierz aplikację do usunięcia:",
            app_names,
            0,
            False
        )
        
        if ok and choice:
            app_id = choice.split(":")[0]
            
            # Potwierdź usunięcie
            reply = QMessageBox.question(
                self,
                "Potwierdzenie",
                f"Czy na pewno chcesz usunąć aplikację:\n{custom_apps[app_id]['name']}?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                # Usuń aplikację
                del custom_apps[app_id]
                
                # Usuń ścieżkę jeśli istnieje
                app_paths = config.get("app_paths", {})
                if app_id in app_paths:
                    del app_paths[app_id]
                
                # Usuń z autostart jeśli tam jest
                autostart_apps = config.get("autostart_apps", [])
                if app_id in autostart_apps:
                    autostart_apps.remove(app_id)
                
                # Usuń z visible_apps jeśli tam jest
                visible_apps = config.get("visible_apps", [])
                if app_id in visible_apps:
                    visible_apps.remove(app_id)
                
                # Zapisz i odśwież
                config["custom_apps"] = custom_apps
                config["app_paths"] = app_paths
                config["autostart_apps"] = autostart_apps
                config["visible_apps"] = visible_apps
                save_config(config)
                
                # Zamknij i informuj
                self.accept()
                
                QMessageBox.information(
                    self,
                    "Aplikacja usunięta",
                    "Aplikacja została usunięta.\nOtwórz Ustawienia ponownie aby zobaczyć zmiany."
                )
    
    def save_settings(self):
        """Zapisz ustawienia."""
        try:
            # Autostart organizera
            enabled = self.autostart_checkbox.isChecked()
            set_autostart(enabled)
            
            # Ścieżki do aplikacji - zapisz wszystkie podane ścieżki
            app_paths = {}
            for app_id, path_input in self.path_inputs.items():
                path_text = path_input.text().strip()
                if path_text:  # Zapisz jeśli cokolwiek wpisano (bez sprawdzania exists)
                    app_paths[app_id] = path_text
            
            # Autostart aplikacji
            autostart_apps = [
                app_id for app_id, cb in self.app_autostart_checkboxes.items()
                if cb.isChecked()
            ]
            
            # Widoczne aplikacje
            visible_apps = [
                app_id for app_id, cb in self.app_visible_checkboxes.items()
                if cb.isChecked()
            ]
            
            # master.sqlite
            master_sqlite_path = self.master_sqlite_input.text().strip()

            # Serwer – katalog z plikami aplikacji
            server_apps_path = self.server_apps_input.text().strip()

            # Zachowaj custom_apps i last_user_id z bieżącej konfiguracji
            current_config = load_config()

            # Zapisz konfigurację
            config = {
                "autostart_apps": autostart_apps,
                "app_paths": app_paths,
                "custom_apps": current_config.get("custom_apps", {}),
                "visible_apps": visible_apps,
                "master_sqlite_path": master_sqlite_path,
                "server_apps_path": server_apps_path,
            }
            if "last_user_id" in current_config:
                config["last_user_id"] = current_config["last_user_id"]
            save_config(config)
            
            # Informacja o zapisie (opcjonalnie)
            QMessageBox.information(
                self,
                "Zapisano ustawienia",
                f"Ustawienia zostały zapisane pomyślnie.\n\n"
                f"Plik konfiguracyjny: {CONFIG_FILE}\n"
                f"Zapisano ścieżek: {len(app_paths)}\n"
                f"Aplikacji autostart: {len(autostart_apps)}\n"
                f"Aplikacji widocznych: {len(visible_apps)}"
            )
            
            self.accept()
            
        except Exception as e:
            # Wyświetl błąd użytkownikowi
            QMessageBox.critical(
                self,
                "Błąd zapisu",
                f"Nie udało się zapisać ustawień!\n\n"
                f"Błąd: {str(e)}\n\n"
                f"Plik konfiguracyjny: {CONFIG_FILE}"
            )
            # Nie zamykaj dialogu przy błędzie


# ============================================================================
# DIALOG LOGOWANIA
# ============================================================================

class LoginDialog(QDialog):
    """Dialog logowania do RM_BAZA (weryfikacja przez master.sqlite)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Logowanie do RM_BAZA")
        self.setModal(True)
        self.setMinimumWidth(380)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.result_user = None  # Dict: id, username, display_name, role

        layout = QVBoxLayout()
        layout.setSpacing(10)

        # Ścieżka
        mp = get_master_sqlite_path()
        if not mp:
            layout.addWidget(QLabel(
                "<b style='color:red'>Nie ustawiono ścieżki do master.sqlite!</b><br/>"
                "Otwórz Ustawienia i wskaż plik."
            ))
            btn = QPushButton("Zamknij")
            btn.clicked.connect(self.reject)
            layout.addWidget(btn)
            self.setLayout(layout)
            return

        layout.addWidget(QLabel(f"<b>Baza:</b> {mp}"))
        layout.addWidget(QLabel("<b>Użytkownik:</b>"))

        self.user_combo = QComboBox()
        self._users = get_users_from_master()
        if not self._users:
            layout.addWidget(QLabel("<b style='color:red'>Brak użytkowników w bazie!</b>"))
            btn = QPushButton("Zamknij")
            btn.clicked.connect(self.reject)
            layout.addWidget(btn)
            self.setLayout(layout)
            return

        for u in self._users:
            dn = u.get('display_name') or u['username']
            self.user_combo.addItem(f"{dn} [{u['role']}]", userData=u)
        layout.addWidget(self.user_combo)

        layout.addWidget(QLabel("<b>Hasło:</b>"))
        self.pwd_edit = QLineEdit()
        self.pwd_edit.setEchoMode(QLineEdit.Password)
        self.pwd_edit.setPlaceholderText("(puste = brak hasła)")
        layout.addWidget(self.pwd_edit)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: red;")
        layout.addWidget(self.status_label)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("Zaloguj")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_login)
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

        self.pwd_edit.returnPressed.connect(self._on_login)

    def _on_login(self):
        idx = self.user_combo.currentIndex()
        if idx < 0:
            return
        user = self.user_combo.itemData(idx)
        password = self.pwd_edit.text()
        stored = user.get('password_hash') or ""
        if not verify_password(password, stored):
            self.status_label.setText("Nieprawidłowe hasło!")
            self.pwd_edit.clear()
            self.pwd_edit.setFocus()
            return
        self.result_user = user
        self.accept()


# ============================================================================
# OKNO CHATU TRAY
# ============================================================================

class _ChatInputEdit(QTextEdit):
    """QTextEdit: Enter=wyślij, Shift+Enter=nowa linia, Ctrl+A=zaznacz."""

    send_requested = pyqtSignal()

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key_A and (mods & Qt.ControlModifier):
            self.selectAll()
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if mods & Qt.ShiftModifier:
                super().keyPressEvent(event)   # Shift+Enter = nowa linia
                return
            self.send_requested.emit()         # Enter = wyślij
            return
        super().keyPressEvent(event)


class TrayChatWindow(QDialog):
    """Okno chatu – identyczne wizualnie i algorytmicznie z ChatWindow z RM_BAZA."""

    # Kolory identyczne jak w RM_BAZA
    _BG_COLORS = ["#fff3cd", "#ffcccc"]
    _HEADER_BG = "#34495e"
    _BODY_BG   = "#2c3e50"
    _MSG_BG    = "#ecf0f1"

    def __init__(self, username: str, display_name: str, chat_dir: Path, parent=None):
        super().__init__(parent)
        self.username     = username
        self.display_name = display_name or username
        self.chat_dir     = chat_dir

        self._last_timestamp  = None
        self._displayed_count = 0   # Liczba wyświetlonych wiadomości (kolory naprzemienne)
        self._always_on_top   = False

        self.setWindowTitle("💬 Chat - RM_BAZA")
        self.setMinimumSize(500, 400)
        self.setWindowFlags(self.windowFlags() | Qt.Window)

        self._build_ui()

        # Ustaw rozmiar po pierwszym pokazaniu okna (omija ograniczenia layoutu)
        QTimer.singleShot(0, lambda: self.resize(1000, 720))

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh_messages)
        self._timer.start(5000)   # Auto-refresh co 5 s

        QTimer.singleShot(50, self._deferred_init)

    # ------------------------------------------------------------------
    # BUDOWA UI (identyczny układ jak RM_BAZA)
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── HEADER (ciemny pasek) ──────────────────────────────────────
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet(f"background: {self._HEADER_BG};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(10, 5, 10, 5)
        hl.setSpacing(10)

        title = QLabel("💬 Chat")
        title.setStyleSheet("color: white; font-size: 14pt; font-weight: bold; background: transparent;")
        hl.addWidget(title)

        self.topmost_cb = QCheckBox("📌 Zawsze na wierzchu")
        self.topmost_cb.setStyleSheet(
            "QCheckBox { color: white; font-size: 9pt; background: transparent; }"
            "QCheckBox::indicator { background: #2c3e50; border: 1px solid #aaa; width: 13px; height: 13px; }"
            "QCheckBox::indicator:checked { background: #3498db; }"
        )
        self.topmost_cb.toggled.connect(self._toggle_always_on_top)
        hl.addWidget(self.topmost_cb)
        hl.addStretch()

        user_lbl = QLabel(f"Zalogowany: {self.display_name}")
        user_lbl.setStyleSheet("color: #ecf0f1; font-size: 10pt; background: transparent;")
        hl.addWidget(user_lbl)

        root.addWidget(header)

        # ── OBSZAR WIADOMOŚCI ──────────────────────────────────────────
        msg_outer = QFrame()
        msg_outer.setStyleSheet(f"background: {self._BODY_BG};")
        mol = QVBoxLayout(msg_outer)
        mol.setContentsMargins(10, 10, 10, 10)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(
            f"QScrollArea {{ background: {self._MSG_BG}; border: none; }}"
        )

        self.msg_container = QWidget()
        self.msg_container.setStyleSheet(f"background: {self._MSG_BG};")
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setAlignment(Qt.AlignTop)
        self.msg_layout.setSpacing(0)
        self.msg_layout.setContentsMargins(0, 0, 0, 0)

        # Padding na dole (jak w RM_BAZA)
        self._padding = QFrame()
        self._padding.setObjectName("chat_padding")
        self._padding.setFixedHeight(20)
        self._padding.setStyleSheet(f"background: {self._MSG_BG}; border: none;")
        self.msg_layout.addWidget(self._padding)

        self.scroll.setWidget(self.msg_container)
        mol.addWidget(self.scroll)
        root.addWidget(msg_outer, stretch=1)

        # ── INPUT (ciemny pasek) ───────────────────────────────────────
        input_frame = QFrame()
        input_frame.setStyleSheet(f"background: {self._HEADER_BG};")
        il = QHBoxLayout(input_frame)
        il.setContentsMargins(10, 5, 5, 10)
        il.setSpacing(5)

        self.input_edit = _ChatInputEdit()
        self.input_edit.setStyleSheet(
            "background: white; color: #2c3e50; font-size: 10pt;"
            "border: 1px solid #ccc; border-radius: 0;"
        )
        self.input_edit.setPlaceholderText(
            "Napisz wiadomość… (Enter = wyślij, Shift+Enter = nowa linia)"
        )
        self.input_edit.send_requested.connect(self.send_message)
        self.input_edit.document().contentsChanged.connect(self._adjust_input_height)
        self._adjust_input_height()
        il.addWidget(self.input_edit)

        send_btn = QPushButton("📤\nWyślij")
        send_btn.setFixedSize(70, 60)
        send_btn.setStyleSheet(
            "QPushButton { background: #3498db; color: white; font-size: 9pt;"
            " font-weight: bold; border: none; }"
            "QPushButton:hover { background: #2980b9; }"
        )
        send_btn.clicked.connect(self.send_message)
        il.addWidget(send_btn)

        root.addWidget(input_frame)

    # ------------------------------------------------------------------
    # POMOCNICZE
    # ------------------------------------------------------------------

    def _adjust_input_height(self):
        """Dynamiczna wysokość pola input: 1–8 linii (jak w RM_BAZA)."""
        fm = self.input_edit.fontMetrics()
        line_h = fm.lineSpacing()
        n = max(2, min(self.input_edit.document().blockCount(), 8))
        m = self.input_edit.contentsMargins()
        self.input_edit.setFixedHeight(n * line_h + m.top() + m.bottom() + 10)

    def _toggle_always_on_top(self, checked: bool):
        """Przełącz 'Zawsze na wierzchu' (jak RM_BAZA: toggle_always_on_top)."""
        flags = self.windowFlags()
        if checked:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()  # Wymagane po setWindowFlags

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, lambda:
            self.scroll.verticalScrollBar().setValue(
                self.scroll.verticalScrollBar().maximum()
            )
        )

    def _remove_padding(self):
        """Tymczasowo odepnij padding od layoutu (jak RM_BAZA usuwa padding_frame)."""
        self._padding.setParent(None)

    def _restore_padding(self):
        """Przywróć padding na koniec layoutu."""
        self.msg_layout.addWidget(self._padding)

    # ------------------------------------------------------------------
    # ALGORYTM WIADOMOŚCI – identyczny z RM_BAZA
    # ------------------------------------------------------------------

    def _deferred_init(self):
        """Jak RM_BAZA._deferred_init: cleanup → load → focus."""
        self._cleanup_old_messages()
        self._load_messages()
        self.input_edit.setFocus()

    def _cleanup_old_messages(self):
        """Usuń najstarsze pliki, zachowaj tylko 200 (identycznie jak RM_BAZA)."""
        try:
            json_files = list(self.chat_dir.glob("*.json"))
            if len(json_files) <= 200:
                return
            json_files.sort(key=lambda f: f.stat().st_mtime)
            to_delete = len(json_files) - 200
            deleted = 0
            for fp in json_files[:to_delete]:
                try:
                    fp.unlink()
                    deleted += 1
                except Exception:
                    continue
            if deleted:
                print(f"🗑️  Usunięto {deleted} najstarszych wiadomości (limit: 200)")
        except Exception as e:
            print(f"⚠️  cleanup_old_messages: {e}")

    def _load_messages(self):
        """Załaduj wszystkie wiadomości przy pierwszym otwarciu (jak RM_BAZA.load_messages)."""
        try:
            if not self.chat_dir.exists():
                self.chat_dir.mkdir(parents=True, exist_ok=True)

            json_files = list(self.chat_dir.glob("*.json"))
            messages = []
            for fp in json_files:
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        messages.append(json.load(f))
                except Exception:
                    continue

            messages.sort(key=lambda x: x.get('timestamp', ''))
            messages = messages[-200:]

            self._remove_padding()

            for msg in messages:
                self._display_message(
                    msg.get('username', '?'),
                    msg.get('display_name'),
                    msg.get('message', ''),
                    msg.get('timestamp', ''),
                    msg_index=self._displayed_count,
                )
                self._displayed_count += 1
                if msg.get('timestamp'):
                    self._last_timestamp = msg['timestamp']

            self._restore_padding()
            self._scroll_to_bottom()

        except Exception as e:
            print(f"⚠️  _load_messages: {e}")
            import traceback
            traceback.print_exc()

    def refresh_messages(self):
        """Dodaj tylko NOWE wiadomości (delta, identycznie jak RM_BAZA.refresh_messages)."""
        try:
            json_files = list(self.chat_dir.glob("*.json"))
            new_messages = []
            for fp in json_files:
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        msg = json.load(f)
                        if not self._last_timestamp or msg.get('timestamp', '') > self._last_timestamp:
                            new_messages.append(msg)
                except Exception:
                    continue

            if not new_messages:
                return

            new_messages.sort(key=lambda x: x.get('timestamp', ''))

            # Usuń padding (jak RM_BAZA usuwa padding_frame przed dodaniem nowych)
            self._remove_padding()

            for msg in new_messages:
                self._display_message(
                    msg.get('username', '?'),
                    msg.get('display_name'),
                    msg.get('message', ''),
                    msg.get('timestamp', ''),
                    msg_index=self._displayed_count,
                )
                self._displayed_count += 1
                if msg.get('timestamp'):
                    self._last_timestamp = msg['timestamp']

            # Przywróć padding (jak RM_BAZA dodaje padding_frame z powrotem)
            self._restore_padding()
            self._scroll_to_bottom()

        except Exception:
            pass

    def _display_message(self, username, display_name, message, timestamp, msg_index=0):
        """Wyświetl pojedynczą wiadomość – identyczny układ 2-kolumnowy jak RM_BAZA.display_message."""
        # Parsuj timestamp
        try:
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.strftime("%H:%M:%S")
        except Exception:
            time_str = timestamp[:8] if len(timestamp) >= 8 else timestamp

        name_to_display = display_name or username

        # Naprzemienne kolory (#fff3cd / #ffcccc) – identycznie jak RM_BAZA
        bg = self._BG_COLORS[msg_index % 2]

        # ── Ramka wiadomości (fill=X jak w RM_BAZA) ──
        msg_frame = QFrame()
        msg_frame.setStyleSheet(f"background: {bg}; border: none;")
        msg_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        fl = QHBoxLayout(msg_frame)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(0)

        # ── Lewa kolumna: stała szerokość 160px – [czas] nazwa ──
        left = QWidget()
        left.setFixedWidth(160)
        left.setStyleSheet(f"background: {bg};")
        ll = QHBoxLayout(left)
        ll.setContentsMargins(5, 5, 5, 5)
        ll.setSpacing(2)

        ts_lbl = QLabel(f"[{time_str}]")
        ts_lbl.setStyleSheet(f"color: #000000; font-size: 10pt; background: {bg};")
        ll.addWidget(ts_lbl)

        # Spacja
        sp = QLabel(" ")
        sp.setStyleSheet(f"background: {bg};")
        ll.addWidget(sp)

        user_lbl = QLabel(name_to_display)
        user_lbl.setStyleSheet(
            f"color: #003366; font-size: 10pt; font-weight: bold; background: {bg};"
        )
        ll.addWidget(user_lbl)
        ll.addStretch()

        fl.addWidget(left)

        # ── Pionowy separator 2px czarny ──
        vsep = QFrame()
        vsep.setFixedWidth(2)
        vsep.setStyleSheet("background: #000000; border: none;")
        fl.addWidget(vsep)

        # ── Prawa kolumna: treść wiadomości (selectable, readonly) ──
        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        msg_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        msg_lbl.setStyleSheet(
            f"color: #000000; font-size: 10pt; background: {bg}; padding: 5px;"
        )
        msg_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        fl.addWidget(msg_lbl, stretch=1)

        self.msg_layout.addWidget(msg_frame)

        # ── Separator poziomy 1px szary ──
        hsep = QFrame()
        hsep.setFixedHeight(1)
        hsep.setStyleSheet("background: #cccccc; border: none;")
        self.msg_layout.addWidget(hsep)

    # ------------------------------------------------------------------
    # WYSYŁANIE
    # ------------------------------------------------------------------

    def send_message(self):
        """Wyślij wiadomość – identycznie jak RM_BAZA.send_message."""
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        if len(text) > 2000:
            QMessageBox.warning(self, "Za długa", "Wiadomość max 2000 znaków.")
            return
        try:
            self.chat_dir.mkdir(parents=True, exist_ok=True)
            now = datetime.now()
            unix_us = int(time.time() * 1_000_000)
            msg_data = {
                'timestamp': now.isoformat(),
                'username':  self.username,
                'display_name': self.display_name,
                'message': text,
            }
            safe_u = re.sub(r'[^a-zA-Z0-9_-]', '_', self.username)
            fname = f"{now.strftime('%Y-%m-%d_%H-%M-%S')}_{safe_u}_{unix_us}.json"
            with open(self.chat_dir / fname, 'w', encoding='utf-8') as f:
                json.dump(msg_data, f, ensure_ascii=False, indent=2)
            self.input_edit.clear()
            self._adjust_input_height()
            print(f"💬 Wysłano: {fname}")
            self.refresh_messages()
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się wysłać:\n{e}")

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)


# ============================================================================
# OKNO POWIADOMIENIA CHAT
# ============================================================================

class ChatNotificationWindow(QDialog):
    """Popup o nowej wiadomości – port show_custom_notification z RM_BAZA."""

    mute_requested = pyqtSignal(int)   # minuty wyciszenia

    def __init__(self, username: str, message: str, on_open_chat, parent=None):
        super().__init__(parent)
        self._on_open_chat_cb = on_open_chat
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # Nie kradnij focusa
        self._build_ui(username, message)
        self.adjustSize()
        self._position_bottom_right()

    def _build_ui(self, username: str, message: str):
        _BG = "#2c3e50"
        self.setStyleSheet(f"background: {_BG};")

        root = QVBoxLayout(self)
        root.setContentsMargins(15, 10, 15, 8)
        root.setSpacing(6)

        # ── Wiersz 1: [Od: username] [stretch] [Zamknij] [✕] ─────────
        header = QHBoxLayout()
        header.setSpacing(6)

        from_lbl = QLabel(f"Od: {username}")
        from_lbl.setStyleSheet(
            f"color: #ecf0f1; font-size: 10pt; font-weight: bold; background: {_BG};"
        )
        header.addWidget(from_lbl)
        header.addStretch()

        close_red = QPushButton("Zamknij")
        close_red.setFixedHeight(22)
        close_red.setStyleSheet(
            "QPushButton { background: #e74c3c; color: white; font-size: 8pt;"
            " font-weight: bold; border: none; padding: 0 10px; }"
            "QPushButton:hover { background: #c0392b; }"
        )
        close_red.clicked.connect(self.close)
        header.addWidget(close_red)

        x_btn = QPushButton("✕")
        x_btn.setFixedSize(22, 22)
        x_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #95a5a6; font-size: 12pt;"
            " border: none; padding: 0; }"
            "QPushButton:hover { color: white; }"
        )
        x_btn.clicked.connect(self.close)
        header.addWidget(x_btn)

        root.addLayout(header)

        # ── Wiersz 2: treść wiadomości ─────────────────────────────
        if len(message) > 150:
            message = message[:147] + "..."

        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setFixedWidth(310)
        msg_lbl.setStyleSheet(
            "color: white; font-size: 9pt; background: #34495e; padding: 4px 6px;"
        )
        root.addWidget(msg_lbl)

        # ── Wiersz 3: wyciszanie ────────────────────────────────────
        mute_row = QHBoxLayout()
        mute_row.setSpacing(4)

        mute_lbl = QLabel("🔕 Nie powiadamiaj przez:")
        mute_lbl.setStyleSheet(f"color: #95a5a6; font-size: 8pt; background: {_BG};")
        mute_row.addWidget(mute_lbl)
        mute_row.addStretch()

        for minutes, label in [(30, "30min"), (60, "1h"), (120, "2h")]:
            btn = QPushButton(label)
            btn.setFixedHeight(20)
            btn.setStyleSheet(
                "QPushButton { background: #34495e; color: white; font-size: 8pt;"
                " border: none; padding: 0 8px; }"
                "QPushButton:hover { background: #4a6278; }"
            )
            btn.clicked.connect(lambda checked, m=minutes: self._on_mute(m))
            mute_row.addWidget(btn)

        root.addLayout(mute_row)

        self.setFixedWidth(350)

    def _position_bottom_right(self):
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry()
        x = avail.right() - self.width() - 10
        y = avail.bottom() - self.height() - 10
        self.move(x, y)

    def _on_mute(self, minutes: int):
        self.mute_requested.emit(minutes)
        self.close()

    def mousePressEvent(self, event):
        """Kliknięcie w obszar (poza przyciskami) → otwórz chat."""
        if event.button() == Qt.LeftButton:
            self.close()
            self._on_open_chat_cb()
        super().mousePressEvent(event)


# ============================================================================
# GŁÓWNA APLIKACJA TRAY
# ============================================================================

class RMTrayOrganizer(QSystemTrayIcon):
    """System Tray organizer dla aplikacji RM."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Procesy uruchomionych aplikacji
        self.processes: Dict[str, subprocess.Popen] = {}

        # Aktualny użytkownik (po zalogowaniu)
        self.current_user: Optional[str] = None
        self.current_display_name: Optional[str] = None
        self.current_user_id: Optional[int] = None
        self.current_user_role: Optional[str] = None

        # Okno chatu
        self._chat_window: Optional[TrayChatWindow] = None

        # Powiadomienia chat (background polling)
        self._last_chat_timestamp: Optional[str] = None
        self._chat_notifications_muted_until = None
        self._notification_window: Optional[ChatNotificationWindow] = None

        # Ustaw ikonę
        self.setIcon(create_icon())
        self.setToolTip("RM Tray Organizer")
        
        # Wymuś widoczność ikony w systemie - agresywnie
        self.setVisible(True)
        
        # Stwórz menu
        self.create_menu()
        
        # Podłącz sygnał kliknięcia ikony (lewy przycisk myszy)
        self.activated.connect(self.on_tray_icon_activated)
        
        # Timer do sprawdzania statusu procesów i wymuszania widoczności
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_menu_status)
        self.timer.start(2000)  # Co 2 sekundy
        
        # Dodatkowy timer do częstszego wymuszania widoczności ikony
        self.visibility_timer = QTimer()
        self.visibility_timer.timeout.connect(self.ensure_icon_visible)
        self.visibility_timer.start(500)  # Co 0.5 sekundy
        
        # Pokaż ikonę
        self.show()
        
        # Autostart aplikacji
        self.autostart_apps()
        # Auto-logowanie na ostatnim użytkowniku
        self._try_autologin()

        # Timer sprawdzania nowych wiadomości chat (powiadomienia w tle)
        self._chat_monitor_timer = QTimer()
        self._chat_monitor_timer.timeout.connect(self._check_for_new_chat_messages)
        self._chat_monitor_timer.start(10_000)  # Co 10 sekund

    def ensure_icon_visible(self):
        """Wymuś widoczność ikony w tray."""
        if not self.isVisible():
            self.setVisible(True)
            self.show()
        
        # Windows-specific: Odśwież ikonę w tray
        if _has_win32:
            try:
                # Odśwież ikonę przez ponowne ustawienie
                current_icon = self.icon()
                self.setIcon(QIcon())  # Usuń tymczasowo
                self.setIcon(current_icon)  # Przywróć
            except:
                pass
    
    def on_tray_icon_activated(self, reason):
        """Obsłuż kliknięcie ikony w tray."""
        if reason == QSystemTrayIcon.Trigger:  # Lewy przycisk myszy (single click)
            # Pokaż menu przy kursorze
            menu = self.contextMenu()
            if menu:
                menu.popup(QCursor.pos())
    
    def refresh_menu(self):
        """Odśwież menu kontekstowe (przebuduj po zmianie konfiguracji)."""
        self.create_menu()
    
    def create_menu(self):
        """Stwórz menu kontekstowe."""
        menu = QMenu()
        
        all_apps = get_all_applications()
        config = load_config()
        visible_apps = config.get("visible_apps", [])
        
        # Jeśli visible_apps jest puste (pierwszy raz), domyślnie wszystkie widoczne
        if not visible_apps:
            visible_apps = list(all_apps.keys())
        
        # Sekcja aplikacji - proste akcje bez podmenu (tylko widoczne)
        for app_id, app_info in all_apps.items():
            # Pomiń aplikacje oznaczone jako niewidoczne
            if app_id not in visible_apps:
                continue
            
            app_path = get_app_path(app_id)
            
            # Prosta akcja - kliknięcie uruchamia/zatrzymuje aplikację
            action = QAction(app_info["name"], menu)
            action.setData(app_id)  # Przechowaj app_id w akcji
            action.triggered.connect(lambda checked, aid=app_id: self.toggle_app(aid))
            
            # Włącz/wyłącz w zależności czy aplikacja istnieje
            if app_path is None:
                action.setEnabled(False)
                action.setToolTip("Aplikacja nie znaleziona - ustaw ścieżkę w Ustawieniach")
            else:
                action.setEnabled(True)
            
            menu.addAction(action)
        
        menu.addSeparator()

        # Chat / logowanie
        if self.current_user:
            login_action = QAction(f"👤 {self.current_display_name or self.current_user}  [wyloguj]", menu)
            login_action.triggered.connect(self.logout_user)
        else:
            login_action = QAction("👤 Zaloguj do RM_BAZA...", menu)
            login_action.triggered.connect(self.show_login)
            if not get_master_sqlite_path():
                login_action.setEnabled(False)
                login_action.setToolTip("Ustaw ścieżkę do master.sqlite w Ustawieniach")
        menu.addAction(login_action)

        chat_action = QAction("💬 Chat", menu)
        chat_action.triggered.connect(self.open_chat)
        chat_action.setEnabled(bool(self.current_user and get_chat_dir()))
        menu.addAction(chat_action)

        menu.addSeparator()

        # Ustawienia
        settings_action = QAction("⚙ Ustawienia...", menu)
        settings_action.triggered.connect(self.show_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        # Wyjście
        exit_action = QAction("✕ Zakończ", menu)
        exit_action.triggered.connect(self.exit_app)
        menu.addAction(exit_action)

        self.setContextMenu(menu)
    
    def update_menu_status(self):
        """Aktualizuj status aplikacji w menu."""
        menu = self.contextMenu()
        
        running_count = 0
        running_names = []
        
        # Pobierz akcje aplikacji (pierwsze N akcji przed separatorem)
        app_actions = []
        for action in menu.actions():
            if action.isSeparator():
                break
            app_actions.append(action)
        
        all_apps = get_all_applications()
        config = load_config()
        visible_apps = config.get("visible_apps", [])
        
        # Jeśli visible_apps jest puste (pierwszy raz), domyślnie wszystkie widoczne
        if not visible_apps:
            visible_apps = list(all_apps.keys())
        
        # Filtruj tylko widoczne aplikacje
        visible_apps_list = [(app_id, app_info) for app_id, app_info in all_apps.items() if app_id in visible_apps]
        
        # Aktualizuj każdą akcję aplikacji
        for i, (app_id, app_info) in enumerate(visible_apps_list):
            if i >= len(app_actions):
                break
            
            action = app_actions[i]
            
            # Sprawdź czy proces działa
            is_running = False
            if app_id in self.processes:
                proc = self.processes[app_id]
                if proc.poll() is None:  # Proces wciąż działa
                    is_running = True
                    running_count += 1
                    running_names.append(app_info['name'])
                else:
                    # Proces zakończony - usuń z listy
                    del self.processes[app_id]
            
            # Aktualizuj nazwę z oznaczniem statusu
            if is_running:
                action.setText(f"● {app_info['name']}")
            else:
                action.setText(f"○ {app_info['name']}")
            
            # Sprawdź czy aplikacja istnieje
            app_path = get_app_path(app_id)
            if app_path is None:
                action.setEnabled(False)
                action.setToolTip("Aplikacja nie znaleziona - ustaw ścieżkę w Ustawieniach")
            else:
                action.setEnabled(True)
                if is_running:
                    action.setToolTip("Kliknij aby zatrzymać")
                else:
                    action.setToolTip("Kliknij aby uruchomić")
        
        # Aktualizuj tooltip z informacją o działających aplikacjach
        if running_count > 0:
            tooltip = f"RM Tray Organizer\nDziała: {running_count} aplikacji\n" + "\n".join(running_names)
        else:
            tooltip = "RM Tray Organizer\nBrak działających aplikacji"
        self.setToolTip(tooltip)
        
        # Wymuś widoczność ikony
        if not self.isVisible():
            self.setVisible(True)
            self.show()
    
    def start_app(self, app_id: str):
        """Uruchom aplikację."""
        if app_id in self.processes and self.processes[app_id].poll() is None:
            # Aplikacja już działa - nie rób nic
            return
        
        app_path = get_app_path(app_id)
        if app_path is None:
            # Nie znaleziono pliku aplikacji
            return
        
        try:
            # Uruchom jako proces w tle
            if app_path.suffix.lower() in ['.exe']:
                # Plik .exe
                proc = subprocess.Popen(
                    [str(app_path)],
                    cwd=str(app_path.parent),
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                # Plik .py/.pyw - uruchom przez pythonw.exe (bez konsoli)
                pythonw = Path(sys.executable).parent / "pythonw.exe"
                if not pythonw.exists():
                    pythonw = Path(sys.executable).parent / "python.exe"
                
                proc = subprocess.Popen(
                    [str(pythonw), str(app_path)],
                    cwd=str(app_path.parent),
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            
            self.processes[app_id] = proc
        except Exception as e:
            # Błąd uruchomienia - loguj do konsoli
            all_apps = get_all_applications()
            app_name = all_apps.get(app_id, {}).get('name', app_id)
            print(f"Błąd uruchomienia {app_name}: {e}")
    
    def stop_app(self, app_id: str):
        """Zatrzymaj aplikację."""
        if app_id not in self.processes:
            return
        
        proc = self.processes[app_id]
        if proc.poll() is None:  # Proces wciąż działa
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        
        del self.processes[app_id]
    
    def stop_all_apps(self):
        """Zatrzymaj wszystkie działające aplikacje."""
        app_ids = list(self.processes.keys())
        if not app_ids:
            return
        
        for app_id in app_ids:
            self.stop_app(app_id)
    
    def toggle_app(self, app_id: str):
        """Uruchom lub zatrzymaj aplikację (toggle)."""
        # Sprawdź czy aplikacja już działa
        if app_id in self.processes and self.processes[app_id].poll() is None:
            # Aplikacja działa - zatrzymaj ją
            self.stop_app(app_id)
        else:
            # Aplikacja nie działa - uruchom ją
            self.start_app(app_id)
    
    def autostart_apps(self):
        """Automatycznie uruchom aplikacje z konfiguracji."""
        config = load_config()
        autostart_apps = config.get("autostart_apps", [])
        
        if not autostart_apps:
            return
        
        all_apps = get_all_applications()
        
        for app_id in autostart_apps:
            if app_id in all_apps and get_app_path(app_id):
                self.start_app(app_id)
    
    def show_login(self):
        """Dialog logowania do RM_BAZA."""
        dlg = LoginDialog()
        if dlg.exec_() == QDialog.Accepted and dlg.result_user:
            u = dlg.result_user
            self.current_user = u['username']
            self.current_display_name = u.get('display_name') or u['username']
            self.current_user_id = u['id']
            self.current_user_role = u.get('role', 'USER')
            print(f"✅ Zalogowano: {self.current_user} ({self.current_user_role})")
            # Zapisz ostatniego użytkownika do config (auto-login przy następnym starcie)
            cfg = load_config()
            cfg['last_user_id'] = u['id']
            save_config(cfg)
            self.refresh_menu()

    def logout_user(self):
        """Wyloguj bieżącego użytkownika."""
        if self._chat_window and self._chat_window.isVisible():
            self._chat_window.close()
            self._chat_window = None
        self.current_user = None
        self.current_display_name = None
        self.current_user_id = None
        self.current_user_role = None
        # Usuń zapisanego użytkownika z config
        cfg = load_config()
        cfg.pop('last_user_id', None)
        save_config(cfg)
        self.refresh_menu()

    def _try_autologin(self):
        """Automatyczne logowanie na ostatnim użytkowniku (z config)."""
        cfg = load_config()
        last_id = cfg.get('last_user_id')
        if not last_id:
            return
        users = get_users_from_master()
        if not users:
            return
        matched = next((u for u in users if u['id'] == last_id), None)
        if not matched:
            return
        self.current_user = matched['username']
        self.current_display_name = matched.get('display_name') or matched['username']
        self.current_user_id = matched['id']
        self.current_user_role = matched.get('role', 'USER')
        print(f"🔄 Auto-logowanie: {self.current_user}")
        self.refresh_menu()

    def _check_for_new_chat_messages(self):
        """Sprawdź nowe wiadomości i pokaż popup (gdy okno chat nie jest otwarte)."""
        if not self.current_user:
            return

        chat_dir = get_chat_dir()
        if not chat_dir or not chat_dir.exists():
            return

        try:
            latest_timestamp = None
            newest_foreign = None

            for fp in chat_dir.glob("*.json"):
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        msg = json.load(f)
                    ts = msg.get('timestamp')
                    if ts and (not latest_timestamp or ts > latest_timestamp):
                        latest_timestamp = ts
                    # Nowe wiadomości od innych użytkowników
                    if ts and msg.get('username') != self.current_user:
                        if not self._last_chat_timestamp or ts > self._last_chat_timestamp:
                            if not newest_foreign or ts > newest_foreign.get('timestamp', ''):
                                newest_foreign = msg
                except Exception:
                    continue

            if newest_foreign:
                if self._is_rm_baza_running():
                    # RM_BAZA jest otwarta – zamknij okno TRAY chatu, nie pokazuj popupu
                    if self._chat_window and self._chat_window.isVisible():
                        self._chat_window.close()
                        self._chat_window = None
                elif not (self._chat_window and self._chat_window.isVisible()):
                    # RM_BAZA nie jest otwarta, okno TRAY chatu nie jest widoczne → popup
                    u = newest_foreign.get('display_name') or newest_foreign.get('username', '?')
                    m = newest_foreign.get('message', '')
                    self._show_chat_notification(u, m)

            # Synchronizuj timestamp (też z okna chatu jeśli otwarte)
            if self._chat_window and self._chat_window.isVisible():
                if self._chat_window._last_timestamp:
                    latest_timestamp = max(
                        latest_timestamp or '',
                        self._chat_window._last_timestamp
                    ) or latest_timestamp
            if latest_timestamp:
                self._last_chat_timestamp = latest_timestamp

        except Exception as e:
            print(f"⚠️  _check_for_new_chat_messages: {e}")

    def _is_rm_baza_running(self) -> bool:
        """Sprawdź czy RM_BAZA jest aktualnie uruchomiona."""
        # 1. Procesy zarządzane przez Tray
        if "RM_BAZA" in self.processes and self.processes["RM_BAZA"].poll() is None:
            return True
        # 2. Szukaj okna z tytułem zaczynającym się od "RM_BAZA" (EnumWindows – wildcard)
        try:
            import ctypes
            found = []

            @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong, ctypes.c_long)
            def _enum_cb(hwnd, _lp):
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length >= 6:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                    if buf.value.startswith("RM_BAZA"):
                        found.append(True)
                        return False  # Przerwij – wystarczy jeden hit
                return True

            ctypes.windll.user32.EnumWindows(_enum_cb, 0)
            if found:
                return True
        except Exception:
            pass
        # 3. Fallback: tasklist
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq RM_BAZA.exe", "/NH"],
                capture_output=True, text=True, timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if "RM_BAZA.exe" in result.stdout:
                return True
        except Exception:
            pass
        return False

    def _show_chat_notification(self, username: str, message: str):
        """Pokaż popup o nowej wiadomości (identyczny z RM_BAZA show_custom_notification)."""
        # Sprawdź wyciszenie
        if self._chat_notifications_muted_until:
            if datetime.now() < self._chat_notifications_muted_until:
                return
            self._chat_notifications_muted_until = None

        # Zamknij poprzednie okno powiadomienia
        if self._notification_window:
            try:
                self._notification_window.close()
            except Exception:
                pass
            self._notification_window = None

        notif = ChatNotificationWindow(username, message, self.open_chat)
        notif.mute_requested.connect(self._on_mute_chat_notifications)
        notif.show()
        self._notification_window = notif

    def _on_mute_chat_notifications(self, minutes: int):
        """Wycisz powiadomienia chat na N minut."""
        from datetime import timedelta  # noqa: PLC0415
        self._chat_notifications_muted_until = datetime.now() + timedelta(minutes=minutes)
        print(f"🔕 Wyciszono powiadomienia chat na {minutes} min")

    def open_chat(self):
        """Otwórz okno chatu."""
        chat_dir = get_chat_dir()
        if not chat_dir:
            QMessageBox.warning(None, "Błąd", "Nie ustawiono ścieżki do master.sqlite w Ustawieniach.")
            return
        if not self.current_user:
            QMessageBox.warning(None, "Błąd", "Najpierw zaloguj się do RM_BAZA.")
            return
        if self._chat_window and self._chat_window.isVisible():
            self._chat_window.raise_()
            self._chat_window.activateWindow()
            return
        self._chat_window = TrayChatWindow(
            username=self.current_user,
            display_name=self.current_display_name,
            chat_dir=chat_dir,
        )
        self._chat_window.show()

    def show_settings(self):
        """Pokaż dialog ustawień."""
        dialog = SettingsDialog()
        result = dialog.exec_()

        # Po zapisaniu ustawień, odśwież menu
        if result == QDialog.Accepted:
            self.refresh_menu()
    
    def show_about(self):
        """Pokaż informacje o programie."""
        QMessageBox.about(
            None,
            "O programie RM Tray Organizer",
            "<h2>RM Tray Organizer</h2>"
            "<p>Wersja 1.0</p>"
            "<p>System Tray organizer do zarządzania aplikacjami RM.</p>"
            "<p><b>Funkcje:</b></p>"
            "<ul>"
            "<li>Uruchamianie/zatrzymywanie aplikacji (jedno kliknięcie)</li>"
            "<li>Monitoring działających procesów</li>"
            "<li>Autostart przy starcie Windows</li>"
            "<li>Automatyczne uruchamianie wybranych aplikacji</li>"
            "<li>Własne ścieżki do plików aplikacji</li>"
            "</ul>"
            "<p><b>🖱️ Użytkowanie:</b><br/>"
            "Prawy przycisk na ikonę RM → Kliknij nazwę aplikacji<br/>"
            "● = działa (kliknij aby zatrzymać)<br/>"
            "○ = nieaktywna (kliknij aby uruchomić)</p>"
            "<p><b>💡 Wskazówka:</b> Aby ikona była zawsze widoczna w Tray:<br/>"
            "Kliknij strzałkę ^ → Prawy przycisk na ikonę RM → Przypnij do paska zadań</p>"
        )
    
    def exit_app(self):
        """Zakończ aplikację."""
        reply = QMessageBox.question(
            None,
            "Potwierdzenie",
            "Czy na pewno chcesz zakończyć RM Tray Organizer?\n\n"
            "Wszystkie działające aplikacje zostaną zatrzymane.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Zatrzymaj wszystkie procesy
            self.stop_all_apps()
            QApplication.quit()


# ============================================================================
# GŁÓWNA FUNKCJA
# ============================================================================

def main():
    """Główna funkcja aplikacji."""
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    # Sprawdź czy już działa inna instancja
    app.setApplicationName("RM_Tray_Organizer")
    
    # Stwórz organizer w tray
    tray = RMTrayOrganizer()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
