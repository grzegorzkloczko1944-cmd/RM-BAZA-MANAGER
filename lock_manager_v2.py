#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lock Manager SIMPLE - Prosty system locków na plikach
======================================================

LOCK = PLIK JSON w katalogu locks/
- Nazwa: project_X.lock
- Zawartość: {"user": "M-old", "computer": "DESKTOP-ABC", "locked_at": "...", "last_heartbeat": "..."}

HEARTBEAT system:
✅ Lock odświeżany co 2 minuty (last_heartbeat)
✅ Locki starsze niż 5 minut automatycznie przejmowane
✅ Proste i niezawodne
"""

import json
import socket
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Set, Tuple


class ProjectLockManager:
    """Prosty system locków - plik = lock"""
    
    def __init__(self, config: dict):
        self.my_name = config['client']['name']
        self.my_computer = socket.gethostname()
        self.locks_folder = Path(config['locks']['folder'])
        self.stale_lock_seconds = int(config.get('locks', {}).get('stale_seconds', 300))  # 5 minut domyślnie
        print(f"🔧 LockManager: folder locks = {self.locks_folder}")
        self.locks_folder.mkdir(parents=True, exist_ok=True)
        print(f"✅ LockManager: folder locks utworzony/zweryfikowany")
        print(f"💻 Mój komputer: {self.my_computer}")
        print(f"⏱️  Heartbeat timeout: {self.stale_lock_seconds}s")
        
        # Aktywne locki (project_id -> True)
        self._my_locks: Set[int] = set()
    
    def update_user_name(self, new_name: str):
        """Zaktualizuj nazwę użytkownika (po zalogowaniu)
        
        Args:
            new_name: Nowa nazwa użytkownika (username)
        """
        old_name = self.my_name
        self.my_name = new_name
        print(f"🔄 LockManager: zmieniono nazwę użytkownika {old_name} -> {new_name}")
        
        # Skanuj CAŁY folder LOCKS — napraw/usuń stare locki tego komputera
        try:
            for lock_file in self.locks_folder.glob("project_*.lock"):
                try:
                    with open(lock_file, 'r', encoding='utf-8') as f:
                        lock_data = json.load(f)
                    if lock_data.get('computer') == self.my_computer and lock_data.get('user') == old_name:
                        # Sprawdź wiek heartbeat — jeśli stale, USUŃ (osierocony z crashu)
                        lock_age = self._lock_age_seconds(lock_data)
                        if lock_age is not None and lock_age >= self.stale_lock_seconds:
                            lock_file.unlink()
                            print(f"   🧹 Usunięto osieroconego locka {lock_file.name}: {old_name} (wiek: {int(lock_age)}s)")
                            continue
                        # Lock świeży — adoptuj i zaktualizuj nazwę
                        lock_data['user'] = new_name
                        lock_data['last_heartbeat'] = datetime.now().isoformat()
                        with open(lock_file, 'w', encoding='utf-8') as f:
                            json.dump(lock_data, f, indent=2)
                        # Dodaj do _my_locks (ten lock należy do nas)
                        try:
                            pid = int(lock_file.stem.replace('project_', ''))
                            self._my_locks.add(pid)
                        except ValueError:
                            pass
                        print(f"   ✅ Zaktualizowano {lock_file.name}: {old_name} -> {new_name}")
                except Exception as e:
                    print(f"   ⚠️ Błąd aktualizacji {lock_file.name}: {e}")
        except Exception as e:
            print(f"   ⚠️ Błąd skanowania folderu LOCKS: {e}")

    def _lock_age_seconds(self, owner: Optional[Dict]) -> Optional[float]:
        """Zwróć wiek HEARTBEAT w sekundach (None jeśli brak daty lub błąd)."""
        if not owner:
            return None
        # Sprawdź last_heartbeat (priorytet) lub locked_at (fallback)
        heartbeat = owner.get('last_heartbeat') or owner.get('locked_at')
        if not heartbeat:
            return None
        try:
            lock_dt = datetime.fromisoformat(str(heartbeat))
            return (datetime.now() - lock_dt).total_seconds()
        except Exception:
            return None
    
    def _release_my_other_locks(self, except_project_id: int):
        """Zwolnij wszystkie moje locki OPRÓCZ podanego projektu (single-lock-per-user)."""
        try:
            for lock_file in self.locks_folder.glob("project_*.lock"):
                try:
                    pid = int(lock_file.stem.replace('project_', ''))
                    if pid == except_project_id:
                        continue
                    with open(lock_file, 'r', encoding='utf-8') as f:
                        lock_data = json.load(f)
                    if lock_data.get('computer') == self.my_computer and lock_data.get('user') == self.my_name:
                        lock_file.unlink()
                        self._my_locks.discard(pid)
                        print(f"🧹 Auto-release: zwolniono lock project {pid} (polityka single-lock)")
                except Exception as e:
                    print(f"⚠️ Błąd auto-release lock: {e}")
        except Exception as e:
            print(f"⚠️ Błąd skanowania LOCKS w _release_my_other_locks: {e}")

    def acquire_project_lock(self, project_id: int, force: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Przejmij lock projektu
        
        Args:
            project_id: ID projektu
            force: Czy wymusić przejęcie (ignoruj czy owner online)
        
        Returns:
            Tuple[bool, Optional[str]]: (success, lock_id)
            - success: True jeśli lock przejęty, False jeśli zajęty
            - lock_id: Unikalny ID locka (lub None jeśli niepowodzenie)
        """
        # Single-lock-per-user: zwolnij inne moje locki przed przejęciem nowego
        self._release_my_other_locks(project_id)

        lock_file = self.locks_folder / f"project_{project_id}.lock"
        
        # Jeśli lock NIE istnieje - od razu przejmij
        if not lock_file.exists():
            print(f"🔓 Lock project {project_id}: wolny - przejmuję")
            return self._create_lock_file(project_id, lock_file)
        
        # Lock istnieje - sprawdź czy to mój
        owner = self.get_project_lock_owner(project_id)
        if owner:
            owner_user = owner.get('user', 'Unknown')
            owner_comp = owner.get('computer', 'Unknown')
            if owner_comp == self.my_computer and owner_user == self.my_name:
                print(f"✅ Lock project {project_id}: już mój")
                self._my_locks.add(project_id)
                lock_id = owner.get('lock_id', str(uuid.uuid4()))
                return (True, lock_id)
        
        # Lock zajęty przez kogoś innego - sprawdź HEARTBEAT
        owner_user = owner.get('user', 'Unknown') if owner else 'Unknown'
        owner_comp = owner.get('computer', 'Unknown') if owner else 'Unknown'
        
        if not force:
            # Sprawdź wiek heartbeat
            lock_age = self._lock_age_seconds(owner)
            
            if lock_age is None:
                # Brak timestampa - przejmij lock
                print(f"🔓 Lock project {project_id}: brak heartbeat - przejmuję")
                return self._create_lock_file(project_id, lock_file)
            
            if lock_age < self.stale_lock_seconds:
                # Heartbeat świeży - lock aktywny
                print(
                    f"🔴 Lock project {project_id}: zajęty przez {owner_user}@{owner_comp} "
                    f"(heartbeat {int(lock_age)}s temu)"
                )
                return (False, None)
            
            # Heartbeat przeterminowany - przejmij lock
            print(
                f"🔓 Lock project {project_id}: heartbeat przeterminowany "
                f"({int(lock_age)}s, limit {self.stale_lock_seconds}s) - przejmuję"
            )
            return self._create_lock_file(project_id, lock_file)
        else:
            # Force = przejmij bez sprawdzania heartbeat
            print(f"⚡ Lock project {project_id}: wymuszam przejęcie (force=True)")
            return self._create_lock_file(project_id, lock_file)
    
    def _create_lock_file(self, project_id: int, lock_file: Path) -> Tuple[bool, Optional[str]]:
        """Utwórz plik lock
        
        Returns:
            Tuple[bool, Optional[str]]: (success, lock_id)
        """
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
            
            self._my_locks.add(project_id)
            print(f"✅ Lock project {project_id} przejęty: {self.my_name}@{self.my_computer} (lock_id: {lock_id[:8]}...)")
            return (True, lock_id)
        
        except Exception as e:
            print(f"❌ Błąd przejmowania locka project {project_id}: {e}")
            return (False, None)
    
    def release_project_lock(self, project_id: int):
        """Zwolnij lock projektu"""
        lock_file = self.locks_folder / f"project_{project_id}.lock"
        
        try:
            if lock_file.exists():
                lock_file.unlink()
            
            if project_id in self._my_locks:
                self._my_locks.remove(project_id)
            
            print(f"🔓 Lock project {project_id} zwolniony")
        
        except Exception as e:
            print(f"⚠️ Błąd zwalniania locka project {project_id}: {e}")
    
    def have_project_lock(self, project_id: int) -> bool:
        """Sprawdź czy mam lock dla projektu"""
        return project_id in self._my_locks
    
    def get_my_locked_projects(self) -> Set[int]:
        """Zwróć set ID projektów które mam zablokowane"""
        return set(self._my_locks)
    
    def get_project_lock_owner(self, project_id: int) -> Optional[Dict]:
        """
        Pobierz info o właścicielu locka projektu
        
        Returns:
            Dict z {"user", "computer", "locked_at"} lub None jeśli brak locka
        """
        lock_file = self.locks_folder / f"project_{project_id}.lock"
        
        if not lock_file.exists():
            return None
        
        try:
            with open(lock_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Błąd odczytu locka: {e}")
            return None
    
    def refresh_heartbeat(self, project_id: int) -> bool:
        """Odśwież heartbeat dla locka projektu
        
        Args:
            project_id: ID projektu
            
        Returns:
            True jeśli heartbeat odświeżony, False jeśli błąd
        """
        if project_id not in self._my_locks:
            print(f"⚠️  refresh_heartbeat: projekt {project_id} nie ma mojego locka")
            return False
        
        lock_file = self.locks_folder / f"project_{project_id}.lock"
        
        try:
            # Sprawdź czy lock istnieje
            if not lock_file.exists():
                print(f"⚠️  refresh_heartbeat: lock project {project_id} nie istnieje!")
                self._my_locks.discard(project_id)
                return False
            
            # Wczytaj lock
            with open(lock_file, 'r', encoding='utf-8') as f:
                lock_data = json.load(f)
            
            # Sprawdź czy to mój lock
            if lock_data.get('computer') != self.my_computer or lock_data.get('user') != self.my_name:
                print(f"⚠️  refresh_heartbeat: lock project {project_id} należy do kogoś innego!")
                self._my_locks.discard(project_id)
                return False
            
            # Odśwież heartbeat
            lock_data['last_heartbeat'] = datetime.now().isoformat()
            
            with open(lock_file, 'w', encoding='utf-8') as f:
                json.dump(lock_data, f, indent=2)
            
            return True
        
        except Exception as e:
            print(f"❌ Błąd odświeżania heartbeat project {project_id}: {e}")
            return False
    
    def refresh_all_my_locks(self):
        """Odśwież heartbeat dla wszystkich moich locków"""
        if not self._my_locks:
            return
        
        print(f"💓 Odświeżam heartbeat dla {len(self._my_locks)} locków...")
        for project_id in list(self._my_locks):
            self.refresh_heartbeat(project_id)
    
    def cleanup_stale_locks(self) -> int:
        """
        Usuń wszystkie stare locki (heartbeat > stale_lock_seconds)
        
        Returns:
            Liczba usuniętych locków
        """
        removed_count = 0
        
        try:
            # Znajdź wszystkie pliki lock
            lock_files = list(self.locks_folder.glob("project_*.lock"))
            print(f"🔍 Sprawdzam {len(lock_files)} locków pod kątem wygaśnięcia...")
            
            for lock_file in lock_files:
                try:
                    # Wczytaj lock
                    with open(lock_file, 'r', encoding='utf-8') as f:
                        lock_data = json.load(f)
                    
                    # Sprawdź wiek heartbeat
                    lock_age = self._lock_age_seconds(lock_data)
                    
                    if lock_age is not None:
                        if lock_age >= self.stale_lock_seconds:
                            # Lock przeterminowany - usuń
                            owner_user = lock_data.get('user', 'Unknown')
                            owner_comp = lock_data.get('computer', 'Unknown')
                            
                            lock_file.unlink()
                            removed_count += 1
                            
                            print(f"🧹 Usunięto stary lock {lock_file.name}: {owner_user}@{owner_comp} (wiek: {int(lock_age)}s)")
                        else:
                            # Lock aktywny - info
                            owner_user = lock_data.get('user', 'Unknown')
                            print(f"   ✅ {lock_file.name}: aktywny ({int(lock_age)}s, limit: {self.stale_lock_seconds}s) - {owner_user}")
                
                except Exception as e:
                    print(f"⚠️  Błąd sprawdzania {lock_file.name}: {e}")
                    continue
            
            if removed_count > 0:
                print(f"✅ Usunięto {removed_count} starych locków")
            else:
                print(f"   Brak starych locków do usunięcia")
        
        except Exception as e:
            print(f"❌ Błąd cleanup_stale_locks: {e}")
        
        return removed_count
    
    def cleanup_all_my_locks(self):
        """Zwolnij wszystkie moje locki (przy zamykaniu aplikacji)"""
        for project_id in list(self._my_locks):
            self.release_project_lock(project_id)

    def cleanup_my_computer_locks(self) -> int:
        """Usuń WSZYSTKIE locki należące do tego komputera (skan plików).
        
        Wywoływane na STARCIE aplikacji — po crashu _my_locks jest pusty,
        ale pliki .lock z poprzedniej instancji wciąż istnieją na dysku.
        cleanup_all_my_locks() ich nie widzi bo operuje na _my_locks (pamięć).
        Ta funkcja skanuje pliki i kasuje po computer name.
        
        Returns:
            Liczba usuniętych locków
        """
        removed = 0
        try:
            for lock_file in self.locks_folder.glob("project_*.lock"):
                try:
                    with open(lock_file, 'r', encoding='utf-8') as f:
                        lock_data = json.load(f)
                    if lock_data.get('computer') == self.my_computer:
                        owner = lock_data.get('user', '?')
                        lock_file.unlink()
                        removed += 1
                        print(f"🧹 Startup cleanup: usunięto {lock_file.name} ({owner}@{self.my_computer})")
                except Exception as e:
                    print(f"⚠️ Błąd cleanup {lock_file.name}: {e}")
        except Exception as e:
            print(f"⚠️ Błąd skanowania LOCKS: {e}")
        if removed:
            print(f"🧹 Startup: usunięto {removed} osieroconych locków z tego komputera")
        else:
            print(f"✅ Startup: brak osieroconych locków z tego komputera")
        return removed
    
    def force_delete_lock(self, project_id: int) -> bool:
        """
        WYMUSZENIE USUNIĘCIA LOCKA - użyj tylko gdy wiesz co robisz!
        Usuwa lock nawet jeśli nie należy do ciebie.
        
        Args:
            project_id: ID projektu którego lock chcesz usunąć
            
        Returns:
            True jeśli lock został usunięty, False jeśli nie istniał
        """
        lock_file = self.locks_folder / f"project_{project_id}.lock"
        
        try:
            if lock_file.exists():
                # Przeczytaj dane przed usunięciem
                with open(lock_file, 'r', encoding='utf-8') as f:
                    lock_data = json.load(f)
                
                print(f"⚠️  WYMUSZAM USUNIĘCIE LOCKA project_{project_id}.lock:")
                print(f"   Właściciel: {lock_data.get('user', 'UNKNOWN')}")
                print(f"   Komputer: {lock_data.get('computer', 'UNKNOWN')}")
                print(f"   Założony: {lock_data.get('locked_at', 'UNKNOWN')}")
                
                # Usuń plik
                lock_file.unlink()
                
                # Usuń z lokalnej listy jeśli był tam
                if project_id in self._my_locks:
                    self._my_locks.remove(project_id)
                
                print(f"✅ Lock project_{project_id} USUNIĘTY")
                return True
            else:
                print(f"⚠️  Lock project_{project_id}.lock nie istnieje")
                return False
                
        except Exception as e:
            print(f"❌ Błąd usuwania locka project_{project_id}: {e}")
            return False

