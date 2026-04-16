"""
============================================================================
RM LOCK MANAGER - System locków dla RM_MANAGER
============================================================================
KOPIUJE 1:1 lock_manager_v2.py z RM_BAZA (sprawdzony przez 2 miesiące, 5 użytkowników)

LOCK = PLIK JSON w katalogu LOCKS/
- project_X.lock
- {"user", "computer", "locked_at", "last_heartbeat"}

HEARTBEAT:
✅ Odświeżaj co 2 minuty
✅ Locki > 5 minut = przeterminowane
✅ Automatyczne przejmowanie
============================================================================
"""

import json
import socket
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Set, Tuple


class RMLockManager:
    """System locków dla RM_MANAGER - heartbeat-based"""
    
    def __init__(self, locks_folder: Path, stale_seconds: int = 300):
        """
        Args:
            locks_folder: Path do folderu LOCKS/
            stale_seconds: Po ilu sekundach lock przeterminowany (default: 300 = 5 min)
        """
        self.my_name = socket.gethostname()  # Zmień przez update_user_name()
        self.my_computer = socket.gethostname()
        self.locks_folder = locks_folder
        self.stale_lock_seconds = stale_seconds
        
        self.locks_folder.mkdir(parents=True, exist_ok=True)
        
        # Aktywne locki
        self._my_locks: Dict[int, str] = {}  # project_id -> lock_id
        
        print(f"🔧 RMLockManager: {self.locks_folder}")
        print(f"💻 Komputer: {self.my_computer}")
        print(f"⏱️  Timeout: {self.stale_lock_seconds}s")
    
    def update_user_name(self, new_name: str):
        """Zaktualizuj nazwę użytkownika (po zalogowaniu)"""
        old_name = self.my_name
        self.my_name = new_name
        print(f"🔄 Zmiana: {old_name} -> {new_name}")
        
        # Skanuj CAŁY folder LOCKS — napraw stare locki tego komputera
        try:
            for lock_file in self.locks_folder.glob("project_*.lock"):
                try:
                    with open(lock_file, 'r', encoding='utf-8') as f:
                        lock_data = json.load(f)
                    if lock_data.get('computer') == self.my_computer and lock_data.get('user') == old_name:
                        lock_data['user'] = new_name
                        lock_data['last_heartbeat'] = datetime.now().isoformat()
                        with open(lock_file, 'w', encoding='utf-8') as f:
                            json.dump(lock_data, f, indent=2)
                        try:
                            pid = int(lock_file.stem.replace('project_', ''))
                            self._my_locks[pid] = lock_data.get('lock_id', '')
                        except ValueError:
                            pass
                        print(f"   ✅ Zaktualizowano {lock_file.name}: {old_name} -> {new_name}")
                except Exception as e:
                    print(f"   ⚠️ Błąd aktualizacji {lock_file.name}: {e}")
        except Exception as e:
            print(f"   ⚠️ Błąd skanowania folderu LOCKS: {e}")
    
    def _lock_age_seconds(self, owner: Optional[Dict]) -> Optional[float]:
        """Wiek heartbeat w sekundach"""
        if not owner:
            return None
        heartbeat = owner.get('last_heartbeat') or owner.get('locked_at')
        if not heartbeat:
            return None
        try:
            lock_dt = datetime.fromisoformat(str(heartbeat))
            return (datetime.now() - lock_dt).total_seconds()
        except Exception:
            return None
    
    def acquire_project_lock(self, project_id: int, force: bool = False) -> Tuple[bool, Optional[str]]:
        """Przejmij lock projektu
        
        Returns:
            (success, lock_id)
        """
        lock_file = self.locks_folder / f"project_{project_id}.lock"
        
        # Brak locka - przejmij
        if not lock_file.exists():
            print(f"🔓 Lock {project_id}: wolny")
            return self._create_lock_file(project_id, lock_file)
        
        # Lock istnieje - sprawdź czy mój
        owner = self.get_project_lock_owner(project_id)
        if owner:
            owner_user = owner.get('user', 'Unknown')
            owner_comp = owner.get('computer', 'Unknown')
            if owner_comp == self.my_computer and owner_user == self.my_name:
                print(f"✅ Lock {project_id}: już mój")
                lock_id = owner.get('lock_id', str(uuid.uuid4()))
                self._my_locks[project_id] = lock_id
                return (True, lock_id)
        
        # Zajęty przez innego
        owner_user = owner.get('user', 'Unknown') if owner else 'Unknown'
        owner_comp = owner.get('computer', 'Unknown') if owner else 'Unknown'
        
        if not force:
            # Sprawdź heartbeat
            lock_age = self._lock_age_seconds(owner)
            
            if lock_age is None:
                print(f"🔓 Lock {project_id}: brak heartbeat")
                return self._create_lock_file(project_id, lock_file)
            
            if lock_age < self.stale_lock_seconds:
                # Świeży - aktywny
                print(f"🔴 Lock {project_id}: zajęty przez {owner_user}@{owner_comp} (heartbeat {int(lock_age)}s)")
                return (False, None)
            
            # Przeterminowany
            print(f"🔓 Lock {project_id}: przeterminowany ({int(lock_age)}s / {self.stale_lock_seconds}s)")
            return self._create_lock_file(project_id, lock_file)
        else:
            # Force
            print(f"⚡ Lock {project_id}: force")
            return self._create_lock_file(project_id, lock_file)
    
    def _create_lock_file(self, project_id: int, lock_file: Path) -> Tuple[bool, Optional[str]]:
        """Utwórz plik lock"""
        lock_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        lock_data = {
            "lock_id": lock_id,
            "user": self.my_name,
            "computer": self.my_computer,
            "locked_at": now,
            "last_heartbeat": now
        }
        
        try:
            with open(lock_file, 'w', encoding='utf-8') as f:
                json.dump(lock_data, f, indent=2)
            
            self._my_locks[project_id] = lock_id
            print(f"✅ Lock {project_id} przejęty: {self.my_name}@{self.my_computer} ({lock_id[:8]}...)")
            return (True, lock_id)
        except Exception as e:
            print(f"❌ Błąd locka {project_id}: {e}")
            return (False, None)
    
    def release_project_lock(self, project_id: int):
        """Zwolnij lock"""
        lock_file = self.locks_folder / f"project_{project_id}.lock"
        
        try:
            if lock_file.exists():
                lock_file.unlink()
            
            if project_id in self._my_locks:
                del self._my_locks[project_id]
            
            print(f"🔓 Lock {project_id} zwolniony")
        except Exception as e:
            print(f"⚠️  Błąd zwalniania {project_id}: {e}")
    
    def refresh_heartbeat(self, project_id: int) -> bool:
        """Odśwież heartbeat (wywołuj co ~2 min)"""
        lock_file = self.locks_folder / f"project_{project_id}.lock"
        
        if not lock_file.exists():
            print(f"⚠️  Lock {project_id}: brak pliku")
            return False
        
        try:
            # Odczytaj
            with open(lock_file, 'r', encoding='utf-8') as f:
                lock_data = json.load(f)
            
            # Sprawdź czy mój
            if lock_data.get('computer') != self.my_computer or lock_data.get('user') != self.my_name:
                print(f"⚠️  Lock {project_id}: nie mój")
                return False
            
            # Odśwież
            lock_data['last_heartbeat'] = datetime.now().isoformat()
            
            # Zapisz
            with open(lock_file, 'w', encoding='utf-8') as f:
                json.dump(lock_data, f, indent=2)
            
            print(f"💓 Lock {project_id}: heartbeat")
            return True
        except Exception as e:
            print(f"❌ Błąd heartbeat {project_id}: {e}")
            return False
    
    def have_project_lock(self, project_id: int) -> bool:
        """Czy mam lock?"""
        return project_id in self._my_locks
    
    def get_my_locked_projects(self) -> Set[int]:
        """Zwróć set zablokowanych projektów"""
        return set(self._my_locks.keys())
    
    def get_project_lock_owner(self, project_id: int) -> Optional[Dict]:
        """Info o właścicielu locka"""
        lock_file = self.locks_folder / f"project_{project_id}.lock"
        
        if not lock_file.exists():
            return None
        
        try:
            with open(lock_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Błąd odczytu: {e}")
            return None
    
    def release_all_my_locks(self):
        """Zwolnij wszystkie (przy zamykaniu)"""
        project_ids = list(self._my_locks.keys())
        for project_id in project_ids:
            self.release_project_lock(project_id)
