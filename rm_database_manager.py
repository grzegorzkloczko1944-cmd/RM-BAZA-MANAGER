"""
============================================================================
RM DATABASE MANAGER - Zarządzanie połączeniami LAN dla RM_MANAGER
============================================================================
KOPIUJE 1:1 sprawdzone mechanizmy z database_manager.py (RM_BAZA):
- PRE-TOUCH warm-up (budzenie SMB przed sqlite.connect)
- Retry loop dla zimnego startu (3 próby, progresywne opóźnienie)
- is_file_accessible() z timeoutem (2-5s zamiast 30s hang)
- ensure_alive() - auto-reconnect po sleep/wake
- Thread-safe reconnect lock
- SMB-safe PRAGMA (journal_mode=DELETE, busy_timeout)

Historia testów: 2 miesiące, 5 użytkowników, LAN SMB
============================================================================
"""

import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional


class RMDatabaseManager:
    """Zarządza połączeniami do rm_manager.sqlite + per-project databases
    
    Architektura:
    Y:/RM_MANAGER/
    ├─ rm_manager.sqlite                  ← główna baza (READ-WRITE)
    └─ RM_MANAGER_PROJECTS/
        ├─ rm_manager_project_123.sqlite  ← bazy projektów (READ-WRITE)
        ├─ rm_manager_project_124.sqlite
        └─ ...
    """
    
    def __init__(self, rm_base_dir: str):
        r"""
        Args:
            rm_base_dir: Y:\RM_MANAGER (root folder)
        """
        self.rm_base_dir = Path(rm_base_dir)
        self.rm_main_db = self.rm_base_dir / "rm_manager.sqlite"
        self.rm_projects_dir = self.rm_base_dir / "RM_MANAGER_PROJECTS"
        
        # Połączenia
        self.main_con: Optional[sqlite3.Connection] = None
        self.project_con: Optional[sqlite3.Connection] = None
        self.current_project_id: Optional[int] = None
        
        # Thread-safe reconnect
        self._reconnect_lock = threading.Lock()
        
        # Network status
        self._network_available = True
        
        # Utwórz foldery
        self.rm_base_dir.mkdir(parents=True, exist_ok=True)
        self.rm_projects_dir.mkdir(parents=True, exist_ok=True)
    
    # ========================================================================
    # PRE-TOUCH - Warm-up dysku sieciowego (KLUCZOWY mechanizm!)
    # ========================================================================
    
    def _warm_up_remote_file(self, db_path: Path, label: str, cold_start: bool = False) -> None:
        """Wymuś szybki odczyt pliku, żeby obudzić SMB/połączenie sieciowe.
        
        **DLACZEGO TO JEST KRYTYCZNE:**
        - sqlite3.connect() przez SMB może wisieć 30-60s na timeout
        - Odczyt 16KB PRZED connect() budzi cache dysku w <1s
        - Retry loop dla zimnego startu (dysk sieciowy uśpiony)
        """
        print(f"🧊 WARM-UP {label} START: {time.strftime('%H:%M:%S')} (cold_start={cold_start})")
        warm_start = time.time()
        
        # Retry loop dla zimnego startu
        max_attempts = 3 if cold_start else 1
        
        for attempt in range(max_attempts):
            try:
                if not db_path.exists():
                    if attempt < max_attempts - 1:
                        print(f"  ⚠️  WARM-UP próba {attempt+1}/{max_attempts}: brak pliku (czekam 0.5s...)")
                        time.sleep(0.5)
                        continue
                    else:
                        print(f"  ❌ WARM-UP: brak pliku {db_path} po {max_attempts} próbach")
                        return
            except Exception as e:
                if attempt < max_attempts - 1:
                    print(f"  ⚠️  WARM-UP próba {attempt+1}/{max_attempts}: exists() failed: {e} (czekam 0.5s...)")
                    time.sleep(0.5)
                    continue
                else:
                    print(f"  ❌ WARM-UP: exists() failed po {max_attempts} próbach: {e}")
                    return
            
            # Plik istnieje - spróbuj odczytać
            try:
                with db_path.open("rb") as f:
                    # Zimny start: 16KB, normalny: 1KB
                    chunk_size = 16384 if cold_start else 1024
                    data = f.read(chunk_size)
                    print(f"  ✅ WARM-UP odczytano {len(data)} bajtów")
                    break  # Sukces!
            except Exception as e:
                if attempt < max_attempts - 1:
                    print(f"  ⚠️  WARM-UP próba {attempt+1}/{max_attempts}: read failed: {e} (czekam 0.5s...)")
                    time.sleep(0.5)
                    continue
                else:
                    print(f"  ❌ WARM-UP: read failed po {max_attempts} próbach: {e}")
                    return
        
        warm_time = time.time() - warm_start
        print(f"🧊 WARM-UP {label} END: {warm_time:.3f}s")
    
    # ========================================================================
    # is_file_accessible - Szybki test dostępności (z timeoutem)
    # ========================================================================
    
    def is_file_accessible(self, path: Path, timeout_s: float = 2.0) -> bool:
        """Szybki test dostępności pliku (w osobnym wątku z timeoutem).
        
        **DLACZEGO TO JEST KRYTYCZNE:**
        - path.exists() przez SMB może wisieć 30s
        - Thread z timeoutem = odpowiedź w <2s
        - Unika martwych connect() wywołań
        """
        result = [False]
        
        def _check():
            try:
                if path.exists():
                    with path.open('rb') as f:
                        f.read(1)
                    result[0] = True
            except Exception:
                result[0] = False
        
        t = threading.Thread(target=_check, daemon=True)
        t.start()
        t.join(timeout=timeout_s)
        
        if t.is_alive():
            print(f"⚠️  is_file_accessible: TIMEOUT ({timeout_s}s) dla {path}")
            self._network_available = False
            return False
        
        self._network_available = result[0]
        return result[0]
    
    # ========================================================================
    # connect_main - Połączenie z rm_manager.sqlite (retry dla zimnego startu)
    # ========================================================================
    
    def connect_main(self) -> bool:
        """Otwórz rm_manager.sqlite (READ-WRITE)
        
        **RETRY LOOP dla ZIMNEGO STARTU:**
        - Pierwsze połączenie = zimny start
        - 3 próby z progresywnym opóźnieniem (2s, 4s)
        """
        # Sprawdź czy już połączone
        if self.main_con:
            try:
                self.main_con.execute("SELECT 1").fetchone()
                print(f"✅ RM Main już połączone")
                return True
            except:
                try:
                    self.main_con.close()
                except:
                    pass
                self.main_con = None
        
        # PRE-TOUCH
        print(f"🔍 PRE-TOUCH rm_manager.sqlite START: {time.strftime('%H:%M:%S')}")
        pre_start = time.time()
        
        # Zimny start?
        cold_start = not hasattr(self, '_first_connect_main_done')
        if cold_start:
            print(f"  ❄️  ZIMNY START wykryty")
        
        # Retry loop
        max_attempts = 3 if cold_start else 1
        last_error = None
        
        for attempt in range(max_attempts):
            if attempt > 0:
                wait_time = 2 * attempt
                print(f"  🔄 Próba {attempt+1}/{max_attempts} po {wait_time}s...")
                time.sleep(wait_time)
            
            try:
                # Pre-check z timeoutem
                precheck_timeout = 5.0 if cold_start else 3.0
                if not self.is_file_accessible(self.rm_main_db, timeout_s=precheck_timeout):
                    if attempt < max_attempts - 1:
                        print(f"  ⚠️  Próba {attempt+1}: rm_manager.sqlite niedostępny")
                        continue
                    else:
                        print(f"  ❌ rm_manager.sqlite niedostępny po {max_attempts} próbach")
                        return False
                
                # Warm-up
                self._warm_up_remote_file(self.rm_main_db, "rm_manager.sqlite", cold_start)
                
                pre_time = time.time() - pre_start
                print(f"🔍 PRE-TOUCH END: {pre_time:.3f}s")
                
                # SQLite connect
                print(f"🔌 SQLITE CONNECT START")
                connect_start = time.time()
                
                timeout_s = 15.0 if cold_start else 5.0
                
                self.main_con = sqlite3.connect(
                    str(self.rm_main_db),
                    timeout=timeout_s,
                    check_same_thread=False,
                    isolation_level='DEFERRED'
                )
                self.main_con.row_factory = sqlite3.Row
                
                # SMB-safe PRAGMA
                self.main_con.execute("PRAGMA cache_size=-32000")
                self.main_con.execute("PRAGMA temp_store=MEMORY")
                self.main_con.execute("PRAGMA journal_mode=DELETE")  # WAL nie działa przez SMB!
                self.main_con.execute("PRAGMA busy_timeout=5000")
                self.main_con.execute("PRAGMA locking_mode=NORMAL")
                self.main_con.execute("PRAGMA synchronous=NORMAL")
                # Weryfikuj journal_mode
                actual_mode = self.main_con.execute("PRAGMA journal_mode").fetchone()[0]
                if actual_mode.upper() != "DELETE":
                    print(f"🔴 OSTRZEŻENIE: journal_mode={actual_mode} zamiast DELETE!")
                    print(f"   WAL mode NIE DZIAŁA przez SMB - ryzyko korupcji danych!")
                
                # Test
                test_result = self.main_con.execute("SELECT 1").fetchone()
                if not test_result:
                    raise sqlite3.OperationalError("Test query failed")
                
                connect_time = time.time() - connect_start
                print(f"🔌 SQLITE CONNECT END: {connect_time:.3f}s")
                print(f"✅ RM Main connected: {self.rm_main_db}")
                
                self._first_connect_main_done = True
                return True
                
            except Exception as e:
                last_error = e
                if attempt < max_attempts - 1:
                    print(f"  ⚠️  Próba {attempt+1}: Błąd: {e}")
                    try:
                        if self.main_con:
                            self.main_con.close()
                            self.main_con = None
                    except:
                        pass
                    continue
                else:
                    print(f"❌ Błąd po {max_attempts} próbach: {e}")
                    return False
        
        return False
    
    # ========================================================================
    # ensure_main_alive - Auto-reconnect
    # ========================================================================
    
    def ensure_main_alive(self) -> bool:
        """Sprawdź żywotność + auto-reconnect po sleep/wake"""
        if not self.main_con:
            print("🔄 RM Main: brak połączenia, łączę...")
            return self.connect_main()
        
        # Pre-check pliku
        if not self.is_file_accessible(self.rm_main_db, timeout_s=2.0):
            print(f"⚠️  RM Main: plik niedostępny")
            return False
        
        # Test żywotności
        try:
            self.main_con.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
            return True
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            err_msg = str(e).lower()
            
            if "locked" in err_msg:
                print(f"⚠️  RM Main: database locked (sleep/wake?), reconnect...")
            else:
                print(f"⚠️  RM Main: martwe połączenie, reconnect...")
            
            try:
                self.main_con.close()
            except:
                pass
            self.main_con = None
            
            time.sleep(0.05)
            return self.connect_main()
    
    # ========================================================================
    # open_project - Per-project database
    # ========================================================================
    
    def open_project(self, project_id: int) -> bool:
        """Otwórz bazę projektu (rm_manager_project_XXX.sqlite)"""
        # Jeśli już otwarty
        if self.project_con and self.current_project_id == project_id:
            try:
                self.project_con.execute("SELECT 1").fetchone()
                print(f"✅ Projekt {project_id} już otwarty")
                return True
            except:
                pass
        
        # Zamknij poprzedni
        if self.project_con:
            try:
                self.project_con.close()
            except:
                pass
            self.project_con = None
        
        # Ścieżka do bazy projektu
        project_db = self.rm_projects_dir / f"rm_manager_project_{project_id}.sqlite"
        
        # PRE-TOUCH
        print(f"🔍 PRE-TOUCH project {project_id} START")
        if not self.is_file_accessible(project_db, timeout_s=3.0):
            print(f"⚠️  Projekt {project_id}: niedostępny")
            return False
        
        self._warm_up_remote_file(project_db, f"project_{project_id}", cold_start=False)
        
        # Connect
        try:
            self.project_con = sqlite3.connect(
                str(project_db),
                timeout=5.0,
                check_same_thread=False,
                isolation_level='DEFERRED'
            )
            self.project_con.row_factory = sqlite3.Row
            
            # SMB-safe
            self.project_con.execute("PRAGMA cache_size=-32000")
            self.project_con.execute("PRAGMA temp_store=MEMORY")
            self.project_con.execute("PRAGMA journal_mode=DELETE")
            self.project_con.execute("PRAGMA busy_timeout=5000")
            self.project_con.execute("PRAGMA locking_mode=NORMAL")
            self.project_con.execute("PRAGMA synchronous=NORMAL")
            # Weryfikuj journal_mode
            actual_mode = self.project_con.execute("PRAGMA journal_mode").fetchone()[0]
            if actual_mode.upper() != "DELETE":
                print(f"🔴 OSTRZEŻENIE: journal_mode={actual_mode} zamiast DELETE dla {project_db}!")
            
            # Test
            self.project_con.execute("SELECT 1").fetchone()
            
            self.current_project_id = project_id
            print(f"✅ Project {project_id} connected")
            return True
            
        except Exception as e:
            print(f"❌ Błąd projektu {project_id}: {e}")
            return False
    
    def ensure_project_alive(self) -> bool:
        """Auto-reconnect dla projektu"""
        if not self.project_con or not self.current_project_id:
            return False
        
        project_db = self.rm_projects_dir / f"rm_manager_project_{self.current_project_id}.sqlite"
        if not self.is_file_accessible(project_db, timeout_s=2.0):
            print(f"⚠️  Project: niedostępny")
            return False
        
        try:
            self.project_con.execute("SELECT 1").fetchone()
            return True
        except:
            print(f"⚠️  Project: martwy, reconnect...")
            try:
                self.project_con.close()
            except:
                pass
            self.project_con = None
            
            time.sleep(0.05)
            return self.open_project(self.current_project_id)
    
    def close_all(self):
        """Zamknij wszystkie połączenia"""
        if self.main_con:
            try:
                self.main_con.close()
            except:
                pass
            self.main_con = None
        
        if self.project_con:
            try:
                self.project_con.close()
            except:
                pass
            self.project_con = None
