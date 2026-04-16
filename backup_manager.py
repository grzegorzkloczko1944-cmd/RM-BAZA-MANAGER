"""
Moduł zarządzania backupami bazy głównej i projektów
- Automatyczne backupy codzienne
- Rotacja 30 dni
- Podgląd i przywracanie (tylko ADMIN)
"""

import sqlite3
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import json


class BackupManager:
    """Zarządza backupami master DB i projektów"""
    
    def __init__(self, master_path: Path, projects_dir: Path, backup_dir: Path, db_manager=None, project_name_pattern: str = None):
        """
        Args:
            master_path: Ścieżka do master.sqlite
            projects_dir: Katalog z bazami projektów
            backup_dir: Katalog na backupy (np. Y:/RM_BAZA/backups)
            db_manager: Opcjonalny DatabaseManager (do rozwiązywania ścieżek magazynowych)
            project_name_pattern: Wzorzec nazwy pliku projektu (np. "project_{id}.sqlite" lub "rm_manager_project_{id}.sqlite")
                                 Jeśli None, wykrywa automatycznie
        """
        self.master_path = Path(master_path)
        self.projects_dir = Path(projects_dir)
        self.backup_dir = Path(backup_dir)
        self.db_manager = db_manager
        
        # Wykryj lub ustaw wzorzec nazw projektów
        if project_name_pattern:
            self.project_name_pattern = project_name_pattern
        else:
            # Auto-detect: jeśli znajduje pliki rm_manager_project_*.sqlite, użyj tego wzorca
            if list(self.projects_dir.glob("rm_manager_project_*.sqlite")):
                self.project_name_pattern = "rm_manager_project_{id}.sqlite"
                print(f"  🔍 Wykryto wzorzec RM_MANAGER: rm_manager_project_{{id}}.sqlite")
            else:
                self.project_name_pattern = "project_{id}.sqlite"
                print(f"  🔍 Wykryto wzorzec RM_BAZA: project_{{id}}.sqlite")
        
        # Utwórz strukturę katalogów
        self.master_backup_dir = self.backup_dir / "master"
        self.projects_backup_dir = self.backup_dir / "projects"
        
        self.master_backup_dir.mkdir(parents=True, exist_ok=True)
        self.projects_backup_dir.mkdir(parents=True, exist_ok=True)
        
        self.retention_days = 30
        
        # Cache backupów projektu (aby uniknąć wielokrotnego skanowania przez sieć)
        # Format: {project_id: {'timestamp': float, 'backups': list}}
        self._backup_cache = {}
        self._cache_ttl = 60.0  # 60 sekund ważności cache
    
    def create_backup(self, db_path: Path, backup_subdir: Path, name_prefix: str, skip_if_exists: bool = False) -> Path:
        """
        Tworzy backup pojedynczej bazy
        
        Args:
            db_path: Ścieżka do bazy do backupu
            backup_subdir: Podkatalog w backup_dir
            name_prefix: Prefix nazwy pliku (np. "master" lub "project_5")
            skip_if_exists: Jeśli True i backup z dzisiejszą datą istnieje - POMIŃ (nie nadpisuj)
        
        Returns:
            Path do utworzonego backupu (lub None jeśli pominięto)
        """
        if not db_path.exists():
            raise FileNotFoundError(f"Baza nie istnieje: {db_path}")
        
        # Format nazwy: master_2026-01-23.sqlite lub project_9_2026-01-24.sqlite
        # Tylko data - jeden backup dziennie, nadpisywany przy kolejnych zapisach
        today = datetime.now().strftime("%Y-%m-%d")
        backup_name = f"{name_prefix}_{today}.sqlite"
        backup_path = backup_subdir / backup_name
        
        print(f"🎯 create_backup: db_path={db_path}, backup_path={backup_path}")
        print(f"   skip_if_exists={skip_if_exists}, backup_path.exists()={backup_path.exists()}")
        
        # Jeśli istnieje i skip_if_exists=True - POMIŃ
        if backup_path.exists() and skip_if_exists:
            print(f"⏭️  Backup z dzisiejszą datą już istnieje, pomijam: {backup_name}")
            return None
        
        # Jeśli istnieje - USUŃ i stwórz od nowa (zamiast nadpisywać)
        if backup_path.exists():
            print(f"⚠️  Usuwam stary dzienny backup: {backup_path}")
            print(f"   Stary plik - rozmiar: {backup_path.stat().st_size / 1024:.1f} KB, modyfikacja: {datetime.fromtimestamp(backup_path.stat().st_mtime)}")
            try:
                backup_path.unlink()
                # Usuń też metadane
                meta_path = backup_path.with_suffix('.json')
                if meta_path.exists():
                    meta_path.unlink()
                print(f"   ✅ Stary backup usunięty")
            except Exception as e:
                print(f"⚠️  Nie udało się usunąć starego backupu: {e}")
                import traceback
                traceback.print_exc()
                raise
        
        # Skopiuj bazę
        print(f"📦 Tworzę backup: {backup_name}")
        print(f"   Źródło: {db_path} ({db_path.stat().st_size / 1024:.1f} KB)")
        print(f"   Cel: {backup_path}")
        
        shutil.copy2(db_path, backup_path)
        
        print(f"   ✅ Skopiowano ({backup_path.stat().st_size / 1024:.1f} KB)")
        print(f"   Modyfikacja po copy: {datetime.fromtimestamp(backup_path.stat().st_mtime)}")
        
        # WAŻNE: Wymuś checkpoint WAL i weryfikację integralności
        try:
            import time
            time.sleep(0.1)  # Poczekaj na flush
            
            verify_con = sqlite3.connect(backup_path, timeout=30.0)
            verify_con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            verify_con.execute("PRAGMA integrity_check")
            verify_con.close()
            print(f"  ✅ Backup zweryfikowany i zamknięty")
        except Exception as e:
            print(f"  ⚠️  Weryfikacja backupu: {e}")
            import traceback
            traceback.print_exc()
        
        # Zapisz metadata
        meta = {
            'source': str(db_path),
            'created_at': datetime.now().isoformat(),
            'size_bytes': backup_path.stat().st_size
        }
        meta_path = backup_path.with_suffix('.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Backup utworzony: {backup_path}")
        return backup_path
    
    def cleanup_old_backups(self, backup_subdir: Path, name_prefix: str):
        """
        Usuwa backupy starsze niż retention_days
        
        Args:
            backup_subdir: Podkatalog z backupami
            name_prefix: Prefix nazwy pliku
        """
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        # Znajdź wszystkie backupy z danym prefixem
        pattern = f"{name_prefix}_*.sqlite"
        
        for backup_file in backup_subdir.glob(pattern):
            try:
                # Wyciągnij datę z nazwy: 
                # master_2026-01-23.sqlite -> 2026-01-23
                # project_9_2026-01-24_153045.sqlite -> 2026-01-24
                filename = backup_file.stem  # Bez .sqlite
                
                # Znajdź datę (YYYY-MM-DD) w nazwie pliku
                import re
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
                if not date_match:
                    continue
                
                date_str = date_match.group(1)
                backup_date = datetime.strptime(date_str, "%Y-%m-%d")
                
                if backup_date < cutoff_date:
                    print(f"🗑️  Usuwam stary backup: {backup_file.name}")
                    backup_file.unlink()
                    
                    # Usuń też metadata
                    meta_file = backup_file.with_suffix('.json')
                    if meta_file.exists():
                        meta_file.unlink()
            
            except Exception as e:
                print(f"⚠️  Błąd usuwania {backup_file.name}: {e}")
    
    def backup_master(self) -> Path:
        """Backup bazy głównej"""
        backup_path = self.create_backup(
            self.master_path,
            self.master_backup_dir,
            "master"
        )
        self.cleanup_old_backups(self.master_backup_dir, "master")
        return backup_path
    
    def backup_project(self, project_id: int, skip_checkpoint: bool = False) -> Path:
        """
        Backup pojedynczego projektu
        
        Args:
            project_id: ID projektu
            skip_checkpoint: Jeśli True, pomija checkpoint (zakładamy że plik jest już zamknięty)
        
        Returns:
            Path do backupu
        """
        # Ścieżka z użyciem wzorca (RM_BAZA: project_5.sqlite, RM_MANAGER: rm_manager_project_5.sqlite)
        project_filename = self.project_name_pattern.format(id=project_id)
        project_db = self.projects_dir / project_filename
        
        if not project_db.exists():
            raise FileNotFoundError(f"Baza projektu {project_id} nie istnieje: {project_db}")
        
        print(f"🔧 Rozpoczynam backup projektu {project_id} z {project_db}")
        print(f"   Plik istnieje: {project_db.exists()}")
        if project_db.exists():
            print(f"   Rozmiar: {project_db.stat().st_size / 1024:.1f} KB")
            print(f"   Modyfikacja: {datetime.fromtimestamp(project_db.stat().st_mtime)}")
        
        # Checkpoint TYLKO jeśli nie został już wykonany
        if not skip_checkpoint:
            try:
                conn = sqlite3.connect(project_db, timeout=30.0)
                # Wymuś checkpoint z TRUNCATE (usuwa WAL po zapisie)
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.commit()
                conn.close()
                
                # Otwórz ponownie żeby wymusić flush systemu plików
                conn = sqlite3.connect(project_db, timeout=30.0)
                conn.execute("PRAGMA integrity_check")
                conn.close()
                
                print(f"  ✅ WAL checkpoint + flush przed backupem projektu {project_id}")
            except Exception as e:
                print(f"  ⚠️  WAL checkpoint nieudany: {e}")
                import traceback
                traceback.print_exc()
            
            # Poczekaj chwilę żeby system plików zapisał wszystko
            import time
            time.sleep(0.1)
        else:
            print(f"  ⏭️  Pomijam checkpoint (skip_checkpoint=True)")
        
        # Katalog dla backupów tego projektu
        project_backup_subdir = self.projects_backup_dir / f"project_{project_id}"
        project_backup_subdir.mkdir(exist_ok=True)
        print(f"📁 Katalog backupów: {project_backup_subdir}")
        
        backup_path = self.create_backup(
            project_db,
            project_backup_subdir,
            f"project_{project_id}"
        )
        
        print(f"🎯 create_backup() zwróciło: {backup_path}")
        
        self.cleanup_old_backups(project_backup_subdir, f"project_{project_id}")
        return backup_path
    
    def backup_all_projects(self, skip_existing_today: bool = False) -> list:
        """
        Backup wszystkich projektów
        
        Args:
            skip_existing_today: Jeśli True, pomija projekty które mają już backup z dzisiejszą datą
        
        Returns:
            Lista tuple (project_id, backup_path) dla wykonanych backupów
        """
        backups = []
        
        # Wykryj pattern do wyszukiwania (RM_BAZA: project_*.sqlite, RM_MANAGER: rm_manager_project_*.sqlite)
        if "rm_manager_project" in self.project_name_pattern:
            search_pattern = "rm_manager_project_*.sqlite"
        else:
            search_pattern = "project_*.sqlite"
        
        # Znajdź wszystkie pliki projektów
        for project_db in sorted(self.projects_dir.glob(search_pattern)):
            try:
                # Wyciągnij ID z nazwy pliku
                # RM_BAZA: project_5.sqlite → ['project', '5'] → 5
                # RM_MANAGER: rm_manager_project_5.sqlite → ['rm', 'manager', 'project', '5'] → 5
                parts = project_db.stem.split('_')
                project_id = int(parts[-1])  # Ostatnia część to zawsze ID
                
                # Sprawdź czy backup z dzisiejszą datą już istnieje (jeśli skip_existing_today=True)
                if skip_existing_today:
                    today = datetime.now().strftime("%Y-%m-%d")
                    project_backup_subdir = self.projects_backup_dir / f"project_{project_id}"
                    backup_file = project_backup_subdir / f"project_{project_id}_{today}.sqlite"
                    
                    if backup_file.exists():
                        print(f"⏭️  Projekt {project_id}: backup z dzisiejszą datą już istnieje, pomijam")
                        continue
                
                backup_path = self.backup_project(project_id)
                if backup_path:  # może być None jeśli pominięto
                    backups.append((project_id, backup_path))
            
            except Exception as e:
                print(f"⚠️  Błąd backupu {project_db.name}: {e}")
        
        return backups
    
    def run_daily_backup(self, skip_existing_projects: bool = True):
        """
        Wykonaj codzienny backup wszystkiego
        
        Args:
            skip_existing_projects: Jeśli True, pomija projekty które mają już backup z dzisiejszą datą
                                   (np. zrobione przy release_lock)
        """
        print(f"\n{'='*60}")
        print(f"🕐 CODZIENNY BACKUP - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
        
        try:
            # Master
            print("📦 Backup bazy głównej...")
            self.backup_master()
            
            # Projekty
            print("\n📦 Backup projektów...")
            backups = self.backup_all_projects(skip_existing_today=skip_existing_projects)
            print(f"\n✅ Backup zakończony: master + {len(backups)} projektów")
        
        except Exception as e:
            print(f"\n❌ Błąd backupu: {e}")
            import traceback
            traceback.print_exc()
    
    def list_master_backups(self) -> list:
        """
        Lista backupów master DB
        
        Returns:
            Lista dict: [{'date': '2026-01-23', 'path': Path, 'size_mb': 1.2}, ...]
        """
        backups = []
        
        for backup_file in sorted(self.master_backup_dir.glob("master_*.sqlite"), reverse=True):
            try:
                date_str = backup_file.stem.split('_', 1)[1]
                size_mb = backup_file.stat().st_size / (1024 * 1024)
                
                backups.append({
                    'date': date_str,
                    'path': backup_file,
                    'size_mb': size_mb,
                    'type': 'master'
                })
            except Exception as e:
                print(f"⚠️  Błąd odczytu {backup_file.name}: {e}")
        
        return backups
    
    def list_project_backups(self, project_id: int) -> list:
        """
        Lista backupów projektu
        
        Args:
            project_id: ID projektu
        
        Returns:
            Lista dict backupów
        """
        import time
        
        # Sprawdź cache
        now = time.time()
        if project_id in self._backup_cache:
            cached = self._backup_cache[project_id]
            age = now - cached['timestamp']
            if age < self._cache_ttl:
                # Cache aktualny
                return cached['backups']
        
        # Cache nieaktualny lub brak - skanuj katalog
        backups = []
        project_backup_subdir = self.projects_backup_dir / f"project_{project_id}"
        
        if not project_backup_subdir.exists():
            # Zapisz pusty wynik do cache
            self._backup_cache[project_id] = {'timestamp': now, 'backups': []}
            return []
        
        pattern = f"project_{project_id}_*.sqlite"
        
        for backup_file in sorted(project_backup_subdir.glob(pattern), reverse=True):
            try:
                date_str = backup_file.stem.split('_', 2)[2]  # project_5_2026-01-23
                size_mb = backup_file.stat().st_size / (1024 * 1024)
                
                backups.append({
                    'date': date_str,
                    'path': backup_file,
                    'size_mb': size_mb,
                    'type': 'project',
                    'project_id': project_id
                })
            except Exception as e:
                print(f"⚠️  Błąd odczytu {backup_file.name}: {e}")
        
        # Zapisz do cache
        self._backup_cache[project_id] = {'timestamp': now, 'backups': backups}
        
        return backups
    
    def list_all_project_backups(self) -> dict:
        """
        Lista backupów WSZYSTKICH projektów
        
        Returns:
            Dict: {project_id: [backups], ...}
        """
        all_backups = {}
        
        for project_subdir in sorted(self.projects_backup_dir.glob("project_*")):
            if not project_subdir.is_dir():
                continue
            
            try:
                project_id = int(project_subdir.name.split('_')[1])
                backups = self.list_project_backups(project_id)
                if backups:
                    all_backups[project_id] = backups
            except Exception as e:
                print(f"⚠️  Błąd listowania {project_subdir.name}: {e}")
        
        return all_backups
    
    def restore_master(self, backup_date: str) -> bool:
        """
        Przywróć master DB z backupu
        
        Args:
            backup_date: Data w formacie YYYY-MM-DD
        
        Returns:
            True jeśli sukces
        """
        backup_file = self.master_backup_dir / f"master_{backup_date}.sqlite"
        
        if not backup_file.exists():
            raise FileNotFoundError(f"Backup nie istnieje: {backup_file}")
        
        # Backup bieżącej bazy przed nadpisaniem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        current_backup = self.master_path.with_name(f"master_before_restore_{timestamp}.sqlite")
        shutil.copy2(self.master_path, current_backup)
        print(f"💾 Backup bieżącej bazy: {current_backup.name}")
        
        # Przywróć
        print(f"🔄 Przywracam master DB z {backup_date}...")
        shutil.copy2(backup_file, self.master_path)
        
        print(f"✅ Master DB przywrócona z {backup_date}")
        return True
    
    def restore_project(self, project_id: int, backup_date: str) -> bool:
        """
        Przywróć projekt z backupu
        
        Args:
            project_id: ID projektu
            backup_date: Data YYYY-MM-DD
        
        Returns:
            True jeśli sukces
        """
        # Ścieżka z użyciem wzorca
        project_filename = self.project_name_pattern.format(id=project_id)
        project_db = self.projects_dir / project_filename
        project_backup_subdir = self.projects_backup_dir / f"project_{project_id}"
        backup_file = project_backup_subdir / f"project_{project_id}_{backup_date}.sqlite"
        
        if not backup_file.exists():
            raise FileNotFoundError(f"Backup nie istnieje: {backup_file}")
        
        # Backup bieżącej bazy
        if project_db.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            current_backup = project_db.with_name(f"project_{project_id}_before_restore_{timestamp}.sqlite")
            shutil.copy2(project_db, current_backup)
            print(f"💾 Backup bieżącej bazy: {current_backup.name}")
        
        # Przywróć
        print(f"🔄 Przywracam projekt {project_id} z {backup_date}...")
        shutil.copy2(backup_file, project_db)
        
        print(f"✅ Projekt {project_id} przywrócony z {backup_date}")
        return True
    
    def get_backup_preview_data(self, backup_path: Path, backup_type: str) -> dict:
        """
        Pobierz dane podglądu z backupu (bez przywracania)
        
        Args:
            backup_path: Ścieżka do pliku backupu
            backup_type: 'master' lub 'project'
        
        Returns:
            Dict z danymi do podglądu
        """
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup nie istnieje: {backup_path}")
        
        # Poczekaj dłużej żeby być pewnym że plik jest zapisany
        import time
        time.sleep(0.2)
        
        preview = {
            'file': backup_path.name,
            'size_mb': backup_path.stat().st_size / (1024 * 1024),
            'modified': datetime.fromtimestamp(backup_path.stat().st_mtime).isoformat()
        }
        
        # OPCJONALNIE: Wymuś checkpoint WAL przed odczytem (tylko jeśli nie jest locked)
        # Używamy krótkiego timeoutu żeby nie zawiesić aplikacji
        try:
            temp_con = sqlite3.connect(backup_path, timeout=1.0)  # timeout 1s
            try:
                temp_con.execute("PRAGMA wal_checkpoint(PASSIVE)")  # PASSIVE = nie czeka na lock
                temp_con.execute("PRAGMA query_only = ON")
            finally:
                temp_con.close()
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            # Jeśli locked - OK, czytamy i tak
            print(f"  ⚠️  WAL checkpoint pominięty (plik może być locked): {e}")
        except Exception as e:
            print(f"  ⚠️  Błąd checkpointu (niegroźne): {e}")
        
        # Poczekaj po checkpoint
        time.sleep(0.1)
        
        # Połącz ponownie (świeże dane bez cache)
        # Użyj immutable=1 żeby SQLite nie tworzył WAL/SHM + timeout
        try:
            con = sqlite3.connect(f"file:{backup_path}?mode=ro&immutable=1", uri=True, timeout=5.0)
        except Exception as e:
            # Jeśli immutable nie działa, spróbuj bez immutable
            print(f"  ⚠️  Immutable mode nieudany, próbuję readonly: {e}")
            con = sqlite3.connect(backup_path, timeout=5.0)
            con.execute("PRAGMA query_only = ON")
        
        con.row_factory = sqlite3.Row
        
        try:
            if backup_type == 'master':
                # Sprawdź czy to RM_BAZA (ma projects/users/suppliers) czy RM_MANAGER (ma stage_definitions)
                cursor = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                
                if 'stage_definitions' in tables:
                    # RM_MANAGER master DB
                    cursor = con.execute("SELECT COUNT(*) as cnt FROM stage_definitions")
                    preview['stage_definitions_count'] = cursor.fetchone()[0]
                    
                    # Śledzenie plików
                    if 'project_file_tracking' in tables:
                        cursor = con.execute("SELECT COUNT(*) as cnt FROM project_file_tracking")
                        preview['file_tracking_count'] = cursor.fetchone()[0]
                    else:
                        preview['file_tracking_count'] = 0
                    
                    # Uprawnienia
                    if 'rm_user_permissions' in tables:
                        cursor = con.execute("SELECT COUNT(*) as cnt FROM rm_user_permissions")
                        preview['user_permissions_count'] = cursor.fetchone()[0]
                    else:
                        preview['user_permissions_count'] = 0
                    
                elif 'projects' in tables:
                    # RM_BAZA master DB (oryginalny kod)
                    # Pobierz liczbę projektów, użytkowników, dostawców
                    cursor = con.execute("SELECT COUNT(*) as cnt FROM projects")
                    preview['projects_count'] = cursor.fetchone()[0]
                    
                    cursor = con.execute("SELECT COUNT(*) as cnt FROM users")
                    preview['users_count'] = cursor.fetchone()[0]
                    
                    cursor = con.execute("SELECT COUNT(*) as cnt FROM suppliers")
                    preview['suppliers_count'] = cursor.fetchone()[0]
                    
                    # Lista projektów - wykryj nazwy kolumn dynamicznie
                    cursor = con.execute("PRAGMA table_info(projects)")
                    cols_info = cursor.fetchall()
                    col_names = [col[1] for col in cols_info]
                    
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
                    
                    # Buduj SELECT
                    if active_col:
                        sql = f"SELECT {id_col}, {name_col}, {active_col} FROM projects ORDER BY {id_col}"
                    else:
                        sql = f"SELECT {id_col}, {name_col} FROM projects ORDER BY {id_col}"
                    
                    cursor = con.execute(sql)
                    projects_list = []
                    for row in cursor.fetchall():
                        if active_col:
                            projects_list.append({'id': row[0], 'name': row[1], 'active': row[2]})
                        else:
                            projects_list.append({'id': row[0], 'name': row[1], 'active': 1})
                    
                    preview['projects'] = projects_list
            
            elif backup_type == 'project':
                # Sprawdź czy to RM_BAZA (ma items) czy RM_MANAGER (ma project_stages)
                cursor = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                
                if 'project_stages' in tables:
                    # RM_MANAGER per-projekt DB
                    cursor = con.execute("SELECT COUNT(*) as cnt FROM project_stages")
                    preview['stages_count'] = cursor.fetchone()[0]
                    
                    if 'stage_actual_periods' in tables:
                        cursor = con.execute("SELECT COUNT(*) as cnt FROM stage_actual_periods")
                        preview['periods_count'] = cursor.fetchone()[0]
                    else:
                        preview['periods_count'] = 0
                    
                    if 'stage_dependencies' in tables:
                        cursor = con.execute("SELECT COUNT(*) as cnt FROM stage_dependencies")
                        preview['dependencies_count'] = cursor.fetchone()[0]
                    else:
                        preview['dependencies_count'] = 0
                    
                elif 'items' in tables:
                    # RM_BAZA per-projekt DB (oryginalny kod)
                    # Pobierz liczbę items
                    cursor = con.execute("SELECT COUNT(*) as cnt FROM items")
                    preview['items_count'] = cursor.fetchone()[0]
                    
                    # Wykryj dostępne kolumny w tabeli items
                    cursor = con.execute("PRAGMA table_info(items)")
                    cols_info = cursor.fetchall()
                    col_names = [col[1] for col in cols_info]
                    
                    # Buduj listę kolumn dynamicznie - wszystkie ważne pola
                    select_cols = []
                    
                    # Podstawowe kolumny (preferuj work_* nad src_*)
                    if 'work_drawing_no' in col_names:
                        select_cols.append('COALESCE(work_drawing_no, src_drawing_no) as drawing_no')
                    else:
                        select_cols.append('src_drawing_no as drawing_no')
                    
                    if 'work_name' in col_names:
                        select_cols.append('COALESCE(work_name, src_name) as name')
                    else:
                        select_cols.append('src_name as name')
                    
                    if 'work_qty' in col_names:
                        select_cols.append('COALESCE(work_qty, src_qty) as qty')
                    else:
                        select_cols.append('src_qty as qty')
                    
                    # Dodaj materiał
                    if 'mat_manual_text' in col_names:
                        select_cols.append('mat_manual_text')
                    if 'mat_auto_text' in col_names:
                        select_cols.append('mat_auto_text')
                    if 'mat_effective_text' in col_names:
                        select_cols.append('mat_effective_text')
                    
                    # Dodaj grubość
                    if 'thickness_mm' in col_names:
                        select_cols.append('thickness_mm')
                    
                    # Dodaj typ
                    if 'class_manual' in col_names:
                        select_cols.append('class_manual')
                    if 'class_auto' in col_names:
                        select_cols.append('class_auto')
                    if 'class_effective' in col_names:
                        select_cols.append('class_effective')
                    
                    # Dodaj dostawcę
                    if 'supplier_id' in col_names:
                        select_cols.append('supplier_id')
                    
                    # Dodaj zamówienie
                    if 'order_qty' in col_names:
                        select_cols.append('order_qty')
                    if 'delivered_qty' in col_names:
                        select_cols.append('delivered_qty')
                    
                    sql = f"SELECT id, {', '.join(select_cols)} FROM items LIMIT 10"
                    
                    cursor = con.execute(sql)
                    preview['items_sample'] = [dict(row) for row in cursor.fetchall()]
        
        finally:
            con.close()
        
        return preview


def schedule_daily_backups(backup_manager: BackupManager):
    """
    Harmonogram codziennych backupów (do uruchomienia w tle)
    
    Uwaga: Wymaga zainstalowania biblioteki schedule:
    pip install schedule
    """
    try:
        import schedule
        import time
        import threading
        
        def job():
            backup_manager.run_daily_backup()
        
        # Backup codziennie o 2:00 w nocy
        schedule.every().day.at("02:00").do(job)
        
        def run_scheduler():
            while True:
                schedule.run_pending()
                time.sleep(60)  # Sprawdzaj co minutę
        
        # Uruchom w osobnym wątku
        thread = threading.Thread(target=run_scheduler, daemon=True)
        thread.start()
        
        print("✅ Harmonogram backupów uruchomiony (codziennie 02:00)")
    
    except ImportError:
        print("⚠️  Biblioteka 'schedule' nie jest zainstalowana")
        print("   Aby włączyć automatyczne backupy: pip install schedule")


if __name__ == "__main__":
    # Test
    from pathlib import Path
    
    master_path = Path("Y:/RM_BAZA/master.sqlite")
    projects_dir = Path("Y:/RM_BAZA/projects")
    backup_dir = Path("Y:/RM_BAZA/backups")
    
    bm = BackupManager(master_path, projects_dir, backup_dir)
    
    # Wykonaj backup
    bm.run_daily_backup()
    
    # Lista backupów
    print("\n📋 Backupy master:")
    for b in bm.list_master_backups():
        print(f"  {b['date']} - {b['size_mb']:.2f} MB")
    
    print("\n📋 Backupy projektów:")
    for proj_id, backups in bm.list_all_project_backups().items():
        print(f"  Projekt {proj_id}: {len(backups)} backupów")
