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
from pathlib import Path
from typing import Dict, Optional
from PyQt5.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QAction, 
    QMessageBox, QDialog, QVBoxLayout, QCheckBox,
    QPushButton, QLabel, QHBoxLayout, QFileDialog,
    QLineEdit, QGridLayout, QGroupBox, QInputDialog
)
from PyQt5.QtCore import Qt, QTimer
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
    return {"autostart_apps": [], "app_paths": {}, "custom_apps": {}, "visible_apps": []}


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
        self.setMinimumWidth(700)
        self.setMinimumHeight(700)
        
        layout = QVBoxLayout()
        
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
            
            # Zachowaj custom_apps z bieżącej konfiguracji
            current_config = load_config()
            
            # Zapisz konfigurację
            config = {
                "autostart_apps": autostart_apps,
                "app_paths": app_paths,
                "custom_apps": current_config.get("custom_apps", {}),
                "visible_apps": visible_apps
            }
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
# GŁÓWNA APLIKACJA TRAY
# ============================================================================

class RMTrayOrganizer(QSystemTrayIcon):
    """System Tray organizer dla aplikacji RM."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Procesy uruchomionych aplikacji
        self.processes: Dict[str, subprocess.Popen] = {}
        
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
