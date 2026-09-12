r"""
============================================================================
DATABASE MANAGER - Zarządzanie bazami master + project
============================================================================
Obsługuje:
- Master DB (Y:\RM_BAZA\master.sqlite) - READ ONLY
- Project DB (lokalnie C:\ lub zdalnie Y:\projects\)
- Sync lokalny ↔ serwer
============================================================================
"""

import sqlite3
import shutil
import threading
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from datetime import datetime


class DatabaseManager:
    """Zarządza połączeniami do master i project baz"""
    
    def __init__(self, master_path: str, projects_dir: str, local_dir: str, projects_mag_dir: str = None):
        r"""
        Args:
            master_path: Ścieżka do master.sqlite (Y:\RM_BAZA\master.sqlite)
            projects_dir: Folder z projektami maszynowymi (Y:\RM_BAZA)
            local_dir: Folder lokalny (C:\RMPAK_CLIENT)
            projects_mag_dir: Folder z projektami magazynowymi (Y:\RM_BAZA\PROJECTS_MAG)
        """
        self.master_path = Path(master_path)
        self.projects_dir = Path(projects_dir)
        self.projects_mag_dir = Path(projects_mag_dir) if projects_mag_dir else Path(projects_dir) / "PROJECTS_MAG"
        self.local_dir = Path(local_dir)
        
        # Połączenia
        self.master_con: Optional[sqlite3.Connection] = None
        # Serializuje reconnecty mastera (watchdog z kilku wątków naraz).
        self._master_reconnect_lock = threading.Lock()
        self.project_con: Optional[sqlite3.Connection] = None
        
        # Stan
        self.current_project_id: Optional[int] = None
        self.current_project_type: str = "MACHINE"  # Typ aktualnie otwartego projektu
        self.is_local: bool = False  # Czy pracujemy na lokalnej kopii?
        
        # Callback dla aktualizacji statusu (opcjonalny)
        self.status_callback = None  # Funkcja(msg: str) -> None
        
        # Flaga: czy połączenie sieciowe jest dostępne (aktualizowana przez pre-check)
        self._network_available = True
        
        # Lock na reconnect (zapobiega podwójnemu reconnect z wielu wątków)
        self._reconnect_lock = threading.Lock()
        
        # Utwórz folder lokalny jeśli nie istnieje
        self.local_dir.mkdir(parents=True, exist_ok=True)
    
    def _retire_master_con(self) -> None:
        """NIC NIE ROBI — nie ma połączenia do odłączenia."""
        self.master_con = None

    def master_commit(self) -> None:
        """NIC NIE ROBI — commit należy do serwera, nie do klienta."""
        return None

    def master_rollback_stuck(self, powod: str = "") -> bool:
        """NIC NIE ROBI — nie ma lokalnej transakcji, która mogłaby zawisnąć.

        Wisząca transakcja na współdzielonym `master_con` była przyczyną
        rodziny błędów „master locked". Serwer prowadzi własną transakcję
        na każde polecenie i sam ją zamyka.
        """
        return False

    def ustaw_klienta_mastera(self, host, port=None, sekret=None):
        """Konfiguruje dostęp do serwera. Wołane raz, przy starcie aplikacji.

        Adres przychodzi z `sync_config.json` na `Y:` — ten sam plik dla
        wszystkich stanowisk. Zwraca opis do logu.
        """
        import rm_klient
        rm_klient.ustaw_serwer(host, port=port, sekret=sekret)
        return rm_klient.opis()

    def master_read(self, operation, params=None):
        """Odczyt przez nazwaną operację. Zwraca listę słowników.

        Nazwa musi istnieć w `rm_serwer_operacje.ODCZYT` — SQL żyje tylko tam.
        Prefiks `map-` kieruje do bazy mapowań, resztę obsługuje master.
        """
        import rm_klient
        return rm_klient.master_read(operation, params)

    def master_exec(self, operation, params=None, request_id=None):
        """Pojedynczy zapis. Zwraca {'rowcount', 'lastrowid'}."""
        import rm_klient
        return rm_klient.master_exec(operation, params, request_id=request_id)

    def master_batch(self, operacje, request_id=None):
        """Kilka zapisów jako JEDNA transakcja — wszystko albo nic."""
        import rm_klient
        return rm_klient.master_batch(operacje, request_id=request_id)

    def _retire_project_con(self) -> None:
        """To samo co _retire_master_con, dla project_con.

        Tylko dla reconnectu z watchdoga (ensure_project_alive, wołany
        z wątku z timeoutem przez _safe_ensure_project_alive). Świadome
        zamknięcie projektu (_close_project, checkpoint WAL w GUI) nadal
        robi commit + close(): tam plik MUSI być zwolniony od razu — locki,
        kopiowanie lokalnej kopii na serwer.
        """
        self.project_con = None

    def connect_master(self) -> bool:
        """NIC NIE OTWIERA — master leży na RM_SERWER, nie na dysku klienta.

        Zostaje jako zgoda na dalszą pracę (True), bo wołają ją 26 miejsc
        w RM_BAZA. Wcześniej otwierała `paths.master` z konfigu; gdy plik
        przeniósł się na serwer, start kończył się `ConnectionError`, mimo
        że żadne zapytanie już z tego połączenia nie korzystało.
        """
        self.master_wants_rw = False
        return True

    def _warm_up_remote_file(self, db_path: Path, label: str, cold_start: bool = False) -> None:
        """Wymuś szybki odczyt pliku, żeby obudzić SMB/połączenie sieciowe.
        
        Args:
            db_path: Ścieżka do pliku bazy
            label: Etykieta do logów
            cold_start: Czy to zimny start (pierwsze połączenie) - więcej prześle retry
        """
        import time

        print(f"🧊 WARM-UP {label} START: {time.strftime('%H:%M:%S')} (cold_start={cold_start})")
        warm_start = time.time()

        # Retry loop dla zimnego startu (dysk sieciowy może być uśpiony)
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
                    # Zimny start: odczytaj 16KB (obudzi cache dysku sieciowego)
                    # Normalny: 1KB wystarczy
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
    
    def reconnect_master_rw(self) -> bool:
        """NIC NIE ROBI — zapisy idą przez `master_exec`, nie przez plik.

        Przełączanie połączenia na read-write miało sens, gdy dziesięć stacji
        pisało do jednego pliku na dysku sieciowym. Serwer kolejkuje zapisy
        u siebie i jest jedynym właścicielem bazy.
        """
        self.master_wants_rw = True
        return True

    def _reconnect_master_after_locked(self) -> bool:
        """NIC NIE ROBI — „database is locked" było chorobą pliku na SMB."""
        return True

    def ensure_stats_columns_exist(self) -> bool:
        """NIC NIE ROBI — schematu pilnuje RM_SERWER przy starcie.

        Klient dokładał sobie kolumny sam (ALTER TABLE przy pierwszym
        zapisie); teraz robią to migracje serwera, wykonywane raz.
        """
        return True

    def get_projects(self) -> List[Tuple[int, str, int, str]]:
        """
        Pobierz listę projektów z master
        Returns: [(project_id, name, active, project_type), ...]
        """
        if not self.master_con:
            self.connect_master()
        
        # Sprawdź żywotność przed operacją
        self.ensure_master_alive()
        
        # Retry loop: po uśpieniu/obudzeniu połączenie może być "locked"
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                return self._get_projects_inner()
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries:
                    print(f"⚠️  get_projects: database locked (próba {attempt+1}/{max_retries+1}), reconnect...")
                    if not self._reconnect_master_after_locked():
                        raise
                    continue
                raise
    
    def _get_projects_inner(self) -> List[Tuple[int, str, int, str]]:
        """Wewnętrzna implementacja get_projects (bez retry).

        Schematu nie sprawdzamy: `project_type` pilnuje migracja serwera,
        a `COALESCE` i tak podstawia 'MACHINE' tam, gdzie wartości brak.
        Wcześniejsze `PRAGMA table_info` było z czasów, gdy każdy klient
        dokładał sobie kolumny sam.
        """
        return [(w["project_id"], w["name"], w["active"], w["project_type"])
                for w in self.master_read("projekty-do-selektora")]
    
    def get_project_statuses(self) -> Dict[int, str]:
        """Pobierz status (kolumna projects.status) dla wszystkich projektow.

        Osobna metoda zamiast rozszerzania get_projects() - ta druga zwraca
        4-elementowe krotki rozpakowywane pozycyjnie w kilku miejscach kodu
        (RM_BAZA_v15_MAG_STATS_ORG.py:2681, 8199, 19311); dolozenie kolumny
        wywalilo by te miejsca (ValueError: too many values to unpack).

        Returns: {project_id: status_text lub '' gdy NULL}
        """
        try:
            return {w["project_id"]: w["status"]
                    for w in self.master_read("projekty-statusy-tekstowe")}
        except Exception as e:
            print(f"⚠️  get_project_statuses: {e}")
            return {}

    def get_suppliers(self) -> List[Tuple[int, str]]:
        """
        Pobierz listę dostawców z master
        Returns: [(supplier_id, name), ...]

        Bez pętli ponowień: „database is locked" było chorobą pliku na dysku
        sieciowym, do którego pisało dziesięć stacji naraz. Serwer wykonuje
        polecenia pojedynczo i kolejkuje je u siebie, więc nie ma tu czego
        ponawiać — a błąd połączenia i tak wymaga innej reakcji niż retry.
        """
        return [(w["supplier_id"], w["name"])
                for w in self.master_read("suppliers-aktywni-id-nazwa")]
    
    def is_file_accessible(self, path: Path, timeout_s: float = 2.0) -> bool:
        """Szybki test dostępności pliku (w osobnym wątku z timeoutem).
        
        Zamiast czekać 30s na timeout SQLite, sprawdzamy dostępność pliku w <2s.
        
        Returns:
            True jeśli plik jest dostępny, False jeśli nie (timeout lub błąd)
        """
        result = [False]
        
        def _check():
            try:
                if path.exists():
                    # Spróbuj odczytać 1 bajt
                    with path.open('rb') as f:
                        f.read(1)
                    result[0] = True
            except Exception:
                result[0] = False
        
        t = threading.Thread(target=_check, daemon=True)
        t.start()
        t.join(timeout=timeout_s)
        
        if t.is_alive():
            # Timeout - plik niedostępny (dysk sieciowy nie odpowiada)
            print(f"⚠️  is_file_accessible: TIMEOUT ({timeout_s}s) dla {path}")
            self._network_available = False
            return False
        
        self._network_available = result[0]
        return result[0]
    
    def ensure_master_alive(self) -> bool:
        """NIC NIE SPRAWDZA — nie ma połączenia, które mogłoby obumrzeć.

        Watchdog pilnował uchwytu do pliku na dysku sieciowym (zrywanego
        przez uśpienie stacji albo chwilową utratę SMB). Dziś każde zapytanie
        to osobne, krótkie połączenie TCP do serwera: albo się uda, albo
        rzuci wyjątek w miejscu wywołania.
        """
        return True

    def _reconnect_master_same_mode(self) -> bool:
        """NIC NIE ROBI — nie ma połączenia z plikiem do odtworzenia.

        Zostaje, bo była częścią watchdoga mastera; nikt jej dziś nie woła.
        """
        return True

    def ensure_project_alive(self) -> bool:
        """Sprawdź czy połączenie z projektem jest żywe. Reconnect jeśli nie.
        
        Returns:
            True jeśli połączenie OK, False jeśli nie udało się przywrócić
        """
        # Jeśli nie ma projektu, nie ma co sprawdzać
        if not self.project_con:
            return False
        
        # Dla zdalnego projektu: szybki pre-check pliku
        if not self.is_local and self.current_project_id:
            from project_manager import get_project_db_path
            base_dir = self.projects_mag_dir if self.current_project_type == "WAREHOUSE" else self.projects_dir
            remote_db = get_project_db_path(base_dir, self.current_project_id, self.current_project_type)
            if not self.is_file_accessible(remote_db, timeout_s=2.0):
                print(f"⚠️  Project: plik zdalny niedostępny - nie próbuję reconnect")
                return False
        
        # Test żywotności
        try:
            self.project_con.execute("SELECT 1").fetchone()
            return True
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
            print(f"⚠️  Project: połączenie martwe ({e}), reconnect...")
            
            # Odłącz martwe połączenie bez close() — inny wątek może być
            # w execute() na tym samym obiekcie (patrz _retire_master_con).
            self._retire_project_con()
            self.project_con = None
            
            # Próba ponownego otwarcia projektu
            if self.current_project_id:
                try:
                    import time
                    time.sleep(0.05)
                    
                    from project_manager import get_project_db_path
                    
                    # Re-otwórz projekt w tym samym trybie co był
                    if self.is_local:
                        # Lokalny projekt
                        if self.current_project_type == "WAREHOUSE":
                            local_db = self.local_dir / f"project_MAG_{self.current_project_id}.sqlite"
                        else:
                            local_db = self.local_dir / f"project_{self.current_project_id}.sqlite"
                        
                        if local_db.exists():
                            self.project_con = sqlite3.connect(
                                str(local_db), timeout=5.0,
                                check_same_thread=False
                            )
                            self.project_con.row_factory = sqlite3.Row
                            self._configure_project_db()
                            print(f"✅ Project reconnect OK (local)")
                            return True
                    else:
                        # Zdalny projekt (read-only)
                        base_dir = self.projects_mag_dir if self.current_project_type == "WAREHOUSE" else self.projects_dir
                        remote_db = get_project_db_path(
                            base_dir, 
                            self.current_project_id, 
                            self.current_project_type
                        )
                        if remote_db.exists():
                            self.project_con = sqlite3.connect(
                                f"file:{remote_db}?mode=ro",
                                uri=True,
                                timeout=5.0,
                                check_same_thread=False
                            )
                            self.project_con.row_factory = sqlite3.Row
                            self._configure_project_db()
                            print(f"✅ Project reconnect OK (remote RO)")
                            return True
                    
                except Exception as reconnect_err:
                    print(f"❌ Project reconnect failed: {reconnect_err}")
                    return False
            
            return False
    
    def open_project_remote(self, project_id: int, project_type: str = "MACHINE"):
        """
        Otwórz projekt ZDALNIE (READ ONLY)
        Używane gdy NIE mamy locka
        """
        # 🔥 WAŻNE: Sprawdź czy projekt jest już otwarty jako REMOTE
        if (self.project_con is not None and 
            self.current_project_id == project_id and 
            self.current_project_type == project_type and
            not self.is_local):
            print(f"✅ Projekt {project_id} ({project_type}) już otwarty REMOTE - pomijam ponowne otwieranie")
            return
        
        self._close_project()
        
        # Użyj get_project_db_path dla backward compatibility
        from project_manager import get_project_db_path
        base_dir = self.projects_mag_dir if project_type == "WAREHOUSE" else self.projects_dir
        remote_db = get_project_db_path(base_dir, project_id, project_type)
        
        # 🔥 PRE-TOUCH: Obudź dysk sieciowy PRZED sqlite.connect()
        import time
        print(f"🔍 PRE-TOUCH {remote_db.name} (REMOTE) START: {time.strftime('%H:%M:%S')}")
        pre_start = time.time()
        
        if not remote_db.exists():
            raise FileNotFoundError(f"Brak projektu: {remote_db}")
        
        # Wymuszenie dostępu do pliku (obudź SMB cache)
        try:
            file_stat = remote_db.stat()
            print(f"  📊 File size: {file_stat.st_size / 1024:.1f} KB")
        except Exception as e:
            print(f"  ⚠️  stat() failed: {e}")

        # Dodatkowy WARM-UP: szybki odczyt 1 bajtu (pomaga na świeżym Windowsie)
        self._warm_up_remote_file(remote_db, remote_db.name)
        
        pre_time = time.time() - pre_start
        print(f"🔍 PRE-TOUCH {remote_db.name} (REMOTE) END: {pre_time:.3f}s")
        
        # Read-only connection
        print(f"🔌 SQLITE CONNECT {remote_db.name} (REMOTE) START: {time.strftime('%H:%M:%S')}")
        connect_start = time.time()
        
        self.project_con = sqlite3.connect(
            f"file:{remote_db}?mode=ro&immutable=1",
            uri=True,
            timeout=5.0,
            check_same_thread=False
        )
        self.project_con.row_factory = sqlite3.Row
        
        # Optymalizacje wydajności dla READ-ONLY
        self.project_con.execute("PRAGMA cache_size=-32000")  # 32MB cache
        self.project_con.execute("PRAGMA temp_store=MEMORY")
        
        connect_time = time.time() - connect_start
        print(f"🔌 SQLITE CONNECT {remote_db.name} (REMOTE) END: {connect_time:.3f}s")
        
        self.current_project_id = project_id
        self.current_project_type = project_type
        self.is_local = False
        
        print(f"✅ Projekt {project_id} ({project_type}, REMOTE READ-ONLY): {remote_db} - TOTAL: {pre_time + connect_time:.3f}s")
    
    def open_project_local(self, project_id: int, project_type: str = "MACHINE"):
        r"""
        Otwórz projekt LOKALNIE (READ/WRITE)
        Używane gdy MAMY lock
        
        Workflow:
        1. Kopiuj Y:\projects\project_X.sqlite → C:\RMPAK_CLIENT\ (140KB = instant!)
        2. Otwórz C:\RMPAK_CLIENT\project_X.sqlite BEZ WAL (zbędny przy locku)
        """
        # 🔥 WAŻNE: Sprawdź czy projekt jest już otwarty jako LOCAL
        if (self.project_con is not None and 
            self.current_project_id == project_id and 
            self.current_project_type == project_type and
            self.is_local):
            print(f"✅ Projekt {project_id} ({project_type}) już otwarty LOCAL - pomijam ponowne otwieranie")
            return
        
        self._close_project()
        
        # Użyj get_project_db_path dla backward compatibility
        from project_manager import get_project_db_path
        base_dir = self.projects_mag_dir if project_type == "WAREHOUSE" else self.projects_dir
        remote_db = get_project_db_path(base_dir, project_id, project_type)
        
        # Lokalna kopia - nazwa zależy od typu
        if project_type == "WAREHOUSE":
            local_db = self.local_dir / f"project_MAG_{project_id}.sqlite"
        else:  # MACHINE
            local_db = self.local_dir / f"project_{project_id}.sqlite"
        
        # 🔥 PRE-TOUCH: Obudź dysk sieciowy PRZED copy
        import time
        print(f"🔍 PRE-TOUCH {remote_db.name} (LOCAL) START: {time.strftime('%H:%M:%S')}")
        pre_start = time.time()
        
        if not remote_db.exists():
            raise FileNotFoundError(f"Brak projektu: {remote_db}")
        
        pre_time = time.time() - pre_start
        print(f"🔍 PRE-TOUCH {remote_db.name} (LOCAL) END: {pre_time:.3f}s")
        
        # Kopiuj remote → local (140KB przez LAN = milisekundy)
        print(f"📥 COPY {remote_db.name} → {self.local_dir}/ START: {time.strftime('%H:%M:%S')}")
        copy_start = time.time()
        shutil.copy2(remote_db, local_db)
        copy_time = time.time() - copy_start
        print(f"📥 COPY END: {copy_time:.3f}s")
        
        # Otwórz lokalną kopię (READ/WRITE) BEZ WAL
        print(f"🔌 SQLITE CONNECT {local_db.name} (LOCAL) START: {time.strftime('%H:%M:%S')}")
        connect_start = time.time()
        self.project_con = sqlite3.connect(
            str(local_db),
            timeout=5.0,
            check_same_thread=False
        )
        self.project_con.row_factory = sqlite3.Row
        
        # DELETE mode (najprostszy, wystarczy przy locku)
        self.project_con.execute("PRAGMA journal_mode=DELETE")
        self.project_con.execute("PRAGMA busy_timeout=5000")
        self.project_con.execute("PRAGMA locking_mode=NORMAL")
        self.project_con.execute("PRAGMA synchronous=NORMAL")
        self.project_con.execute("PRAGMA temp_store=MEMORY")
        self.project_con.execute("PRAGMA cache_size=-32000")  # 32MB cache
        self.project_con.execute("PRAGMA foreign_keys=ON")
        
        connect_time = time.time() - connect_start
        print(f"🔌 SQLITE CONNECT {local_db.name} (LOCAL) END: {connect_time:.3f}s")
        
        self.current_project_id = project_id
        self.current_project_type = project_type
        self.is_local = True
        
        total_time = pre_time + copy_time + connect_time
        print(f"✅ Projekt {project_id} ({project_type}, LOCAL READ/WRITE): {local_db} - TOTAL: {total_time:.3f}s")
    
    def sync_project_to_server(self, project_id: int):
        r"""
        Upload lokalnej kopii na serwer
        
        Workflow:
        1. Commit wszystko
        2. Kopiuj C:\project_X.sqlite → Y:\projects\ (140KB = instant)
        """
        if not self.is_local:
            raise ValueError("Nie pracujesz na lokalnej kopii!")
        
        if self.current_project_id != project_id:
            raise ValueError(f"Otwarty projekt {self.current_project_id}, próba sync {project_id}")
        
        # Commit wszystko
        if self.project_con:
            self.project_con.commit()
            print("  ✅ Commit")
        
        # ⚠️ ZAMYKAMY połączenie przed nadpisaniem pliku na serwerze.
        #
        # Sam `commit()` wyżej nie wystarcza: uchwyt do bazy ZOSTAJE OTWARTY,
        # a Windows nie pozwala nadpisać pliku trzymanego przez proces. Na `Y:`
        # przechodziło, na W2019S kończy się „[Errno 13] Permission denied"
        # przy zwalnianiu locka — plik widać wtedy w `Get-SmbOpenFile` jako
        # otwarty przez nas samych (12.09.2026). Wołający zamyka projekt zaraz
        # potem (`close_project_and_cleanup`), więc nic nie tracimy.
        if self.project_con:
            try:
                self.project_con.close()
            except Exception:
                pass
            self.project_con = None

        # Użyj get_project_db_path dla backward compatibility - zapisz tam skąd był pobrany
        project_type = self.current_project_type  # Użyj aktualnego typu
        from project_manager import get_project_db_path
        base_dir = self.projects_mag_dir if project_type == "WAREHOUSE" else self.projects_dir
        remote_db = get_project_db_path(base_dir, project_id, project_type)
        
        # Lokalna kopia
        if project_type == "WAREHOUSE":
            local_db = self.local_dir / f"project_MAG_{project_id}.sqlite"
        else:  # MACHINE
            local_db = self.local_dir / f"project_{project_id}.sqlite"
        
        # Kopiuj local → remote (140KB przez LAN = milisekundy)
        import time
        print(f"📤 Upload {local_db.name} → {remote_db.parent}/")
        upload_start = time.time()
        
        # Utwórz katalog jeśli nie istnieje
        remote_db.parent.mkdir(parents=True, exist_ok=True)
        
        shutil.copy2(local_db, remote_db)
        upload_time = time.time() - upload_start
        print(f"  ⏱️  Wgrano w {upload_time:.3f}s")
        
        print(f"✅ Projekt {project_id} ({project_type}) zsynchronizowany")
    
    
    def close_project_and_cleanup(self, project_id: int, project_type: str = "MACHINE"):
        """
        Zamknij projekt i usuń lokalną kopię
        """
        self._close_project()
        
        # Określ nazwę pliku w zależności od typu
        if project_type == "WAREHOUSE":
            filename_base = f"project_MAG_{project_id}.sqlite"
        else:  # MACHINE
            filename_base = f"project_{project_id}.sqlite"
        
        # Usuń lokalną kopię
        local_db = self.local_dir / filename_base
        if local_db.exists():
            local_db.unlink()
            print(f"🗑️  Usunięto lokalną kopię: {local_db.name}")
        
        # Usuń pliki pomocnicze (journal itp)
        for suffix in ['-wal', '-shm', '-journal']:
            helper_file = self.local_dir / f"{filename_base}{suffix}"
            if helper_file.exists():
                helper_file.unlink()
    
    def _configure_project_db(self):
        """Ustaw PRAGMA optymalizacyjne dla połączenia z projektem.
        
        Wywoływane po otwarciu lub reconnect połączenia projektowego.
        """
        if not self.project_con:
            return
        try:
            self.project_con.execute("PRAGMA cache_size=-32000")  # 32MB cache
            self.project_con.execute("PRAGMA temp_store=MEMORY")
            if self.is_local:
                # Lokalny projekt - pełne optymalizacje RW
                self.project_con.execute("PRAGMA journal_mode=DELETE")
                self.project_con.execute("PRAGMA busy_timeout=5000")
                self.project_con.execute("PRAGMA locking_mode=NORMAL")
                self.project_con.execute("PRAGMA synchronous=NORMAL")
                self.project_con.execute("PRAGMA foreign_keys=ON")
        except Exception as e:
            print(f"⚠️  _configure_project_db: {e}")
    
    def _close_project(self):
        """Zamknij aktualne połączenie do projektu"""
        if self.project_con:
            try:
                self.project_con.commit()
                self.project_con.close()
            except:
                pass
            self.project_con = None
        
        self.current_project_id = None
        self.current_project_type = "MACHINE"
        self.is_local = False
    
    def get_project_items(self, project_id: int, show_hidden: bool = False) -> List[sqlite3.Row]:
        """
        Pobierz wszystkie items z projektu
        
        Args:
            project_id: ID projektu
            show_hidden: Czy pokazywać ukryte pozycje (is_hidden=1)
        """
        if not self.project_con:
            raise ValueError("Projekt nie jest otwarty!")
        
        if self.current_project_id != project_id:
            raise ValueError(f"Otwarty projekt {self.current_project_id}, zapytanie o {project_id}")
        
        # 🔄 Sprawdź żywotność połączenia przed odczytem
        if not self.ensure_project_alive():
            raise ConnectionError("Połączenie z bazą projektu zostało przerwane. Spróbuj ponownie otworzyć projekt.")
        
        # Warunek filtrowania ukrytych
        # False (domyślnie): pokazuj tylko widoczne (is_hidden = 0)
        # True: pokazuj tylko ukryte (is_hidden = 1)
        
        print(f"\n🗄️  DATABASE_MANAGER.get_project_items:")
        print(f"   Otrzymano parametr show_hidden={show_hidden} (type: {type(show_hidden)})")
        print(f"   Is local: {self.is_local}")
        print(f"   Connection: {self.project_con}")
        
        # Sprawdź plik bazy z której czytamy
        try:
            db_path_query = self.project_con.execute("PRAGMA database_list").fetchone()
            if db_path_query:
                print(f"   📂 Baza: {db_path_query[2]}")
        except:
            pass
        
        # Zbuduj SQL dynamicznie bez f-string (może być problem z cachowaniem)
        if show_hidden:
            target_is_hidden = 1
            print(f"   FILTR: pokazuj TYLKO UKRYTE (is_hidden = 1)")
        else:
            target_is_hidden = 0
            print(f"   FILTR: pokazuj TYLKO WIDOCZNE (is_hidden = 0)")
        
        # Sprawdź czy baza ma kolumny src_modul i work_modul (backward compatibility)
        has_modul_cols = False
        has_symbol_col = False
        try:
            cursor_check = self.project_con.execute("PRAGMA table_info(items)")
            columns = [row[1] for row in cursor_check.fetchall()]
            has_modul_cols = 'src_modul' in columns and 'work_modul' in columns
            has_symbol_col = 'subiekt_symbol' in columns
            print(f"   Kolumny Moduł w bazie: {has_modul_cols}")
        except Exception as e:
            print(f"   ⚠️  Nie udało się sprawdzić kolumn: {e}")
        
        # Zbuduj SELECT z warunkowymi kolumnami modul
        modul_select = ""
        if has_modul_cols:
            modul_select = """
                -- MODUŁ - src, work i COALESCE
                i.src_modul,
                i.work_modul,
                COALESCE(i.work_modul, i.src_modul) AS modul_disp,
                """
        
        # Symbol, pod którym pozycja poszła do Subiekta — arkusz pokazuje go
        # w „Nr rysunku", gdy numeru brak (znormalia). Bazy sprzed migracji
        # kolumny nie mają, stąd warunkowo.
        symbol_select = "                i.subiekt_symbol,\n" if has_symbol_col else ""
        # Zbuduj pełne SQL query
        query = f"""
            SELECT 
                i.id,
                i.is_manual,
                i.is_hidden,
                
                -- Kolumny wyświetlane (COALESCE work → src)
                COALESCE(NULLIF(i.work_drawing_no,''), i.src_drawing_no) AS drawing_no,
                COALESCE(NULLIF(i.work_name,''), i.src_name) AS name,
                COALESCE(NULLIF(i.work_desc,''), i.src_desc) AS descr,
                COALESCE(i.work_qty, i.src_qty) AS qty_bom,
                
                -- Oryginalne kolumny src_* (do porównania BOM)
                i.src_drawing_no,
                i.src_name,
                i.src_desc,
                i.src_qty,
                i.src_material_text,
                
                -- Kolumny work_* (do porównania override)
                i.work_drawing_no,
                i.work_name,
                i.work_desc,
                i.work_qty,
                
                -- Reszta kolumn
                i.order_qty,
                i.delivered_qty,
                i.delivered_updated_at,
                
                -- KLASYFIKACJA - wszystkie 3 kolumny!
                i.class_auto,
                i.class_manual,
                COALESCE(i.class_manual, i.class_auto) AS class_effective,
                
                -- MATERIAŁ - wszystkie 3 kolumny!
                i.mat_auto_text,
                i.mat_manual_text,
                COALESCE(i.mat_manual_text, i.mat_auto_text, i.src_material_text) AS mat_effective_text,
                
                -- GRUBOŚĆ + źródło
                i.thickness_mm,
                i.thickness_src,
                
                {symbol_select}
                {modul_select}
                i.supplier_id,
                i.price_pln,
                i.ordered_flag,
                i.ordered_at,
                i.deadline_date,
                i.alarm_offset,
                i.alarm_unit,
                i.alarm_date,
                COALESCE(i.dwf_biblioteka,0) AS dwf_biblioteka,
                i.notes,
                i.created_at,
                i.updated_at
            FROM items i
            WHERE i.project_id = ? AND COALESCE(i.is_hidden, 0) = ?
            ORDER BY drawing_no COLLATE NOCASE, name COLLATE NOCASE, i.id
        """
        
        print(f"   SQL parametry: project_id={project_id}, is_hidden={target_is_hidden}")
        
        # Wykonaj query z dwoma parametrami
        cursor = self.project_con.execute(query, (project_id, target_is_hidden))
        
        results = cursor.fetchall()
        print(f"   Znaleziono {len(results)} pozycji")
        if results:
            # Pokaż wartości is_hidden z pierwszych 3 pozycji
            sample = results[:3]
            print(f"   Próbka is_hidden: {[r['is_hidden'] for r in sample]}")
        
        return results
    
    def update_item(self, item_id: int, field: str, value):
        """
        Aktualizuj pojedyncze pole w item
        
        Args:
            item_id: ID pozycji
            field: Nazwa kolumny (work_drawing_no, work_name, ...)
            value: Nowa wartość
        """
        if not self.project_con:
            raise ValueError("Projekt nie jest otwarty!")
        
        if not self.is_local:
            raise ValueError("Nie możesz edytować - pracujesz w trybie READ-ONLY!")
        
        # 🔄 Sprawdź żywotność połączenia przed zapisem
        if not self.ensure_project_alive():
            raise ConnectionError("Połączenie z bazą projektu zostało przerwane. Spróbuj ponownie otworzyć projekt.")
        
        # Whitelist dozwolonych pól (bezpieczeństwo)
        allowed_fields = [
            # Kolumny BOM (nadpisywalne)
            'work_drawing_no', 'work_name', 'work_desc', 'work_qty', 'work_modul',
            
            # Ilości
            'order_qty', 'delivered_qty',
            
            # Klasyfikacja/Materiał
            'class_effective', 'mat_effective_text', 'thickness_mm',
            
            # Dostawca
            'supplier_id',
            
            # Zamówienie
            'ordered_flag', 'ordered_at', 'deadline_date',
            
            # Alarm
            'alarm_offset', 'alarm_unit', 'alarm_date',
            
            # Cena
            'price_pln',
            
            # Inne
            'notes', 'dwf_biblioteka'
        ]
        
        if field not in allowed_fields:
            raise ValueError(f"Pole {field} nie jest dozwolone do edycji")
        
        # Specjalna obsługa dla delivered_qty - aktualizuj również delivered_updated_at
        if field == 'delivered_qty':
            now_iso = datetime.now().isoformat()
            self.project_con.execute("""
                UPDATE items 
                SET delivered_qty = ?, 
                    delivered_updated_at = ?,
                    updated_at = ?
                WHERE id = ?
            """, (value, now_iso, now_iso, item_id))
        else:
            # Update standardowy
            self.project_con.execute(f"""
                UPDATE items 
                SET {field} = ?, updated_at = ?
                WHERE id = ?
            """, (value, datetime.now().isoformat(), item_id))
        
        self.project_con.commit()
    
    def close_all(self):
        """Zamknij wszystkie połączenia"""
        self._close_project()
        
        if self.master_con:
            try:
                self.master_con.close()
            except:
                pass
            self.master_con = None
        
        print("✅ Wszystkie połączenia zamknięte")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


# Bazy, dla których journal_mode=DELETE zweryfikowano już w tym procesie.
# journal_mode persystuje w nagłówku bazy, więc kosztowny round-trip fetchone()
# przez SMB wystarczy raz na plik. Klucz to znormalizowana ścieżka (bez części
# ?mode=ro URI), żeby ro/rw wariant tej samej bazy dzielił wpis.
_BAZA_JOURNAL_VERIFIED: set = set()


def _open_baza_connection(db_path, row_factory=True, uri=False, timeout=30.0):
    """Otwórz połączenie SQLite z PRAGMA bezpiecznymi dla NAS/SMB.

    Analogiczna funkcja do ``_open_rm_connection`` w rm_manager.py.
    Ustawia: journal_mode=DELETE, busy_timeout=5000, locking_mode=NORMAL,
    synchronous=NORMAL, cache_size=-2000, temp_store=MEMORY.

    Args:
        db_path: ścieżka do bazy (str/Path) lub URI (gdy uri=True).
        row_factory: czy ustawić sqlite3.Row (domyślnie True).
        uri: czy db_path to URI (np. ``file:...?mode=ro``).
        timeout: timeout połączenia w sekundach.
    Returns:
        sqlite3.Connection z ustawionymi PRAGMA.

    Wydajność (SMB/NAS): PRAGMA ustawiane jednym executescript() (jeden round-trip
    zamiast sześciu), weryfikacja journal_mode tylko raz na plik na proces. Istotne
    dla ścieżek skanujących wiele plików projektów, gdzie ta funkcja jest wołana
    w pętli per plik na dysku sieciowym o wysokiej latencji.
    """
    con = sqlite3.connect(
        str(db_path) if not uri else db_path,
        uri=uri,
        timeout=timeout,
        check_same_thread=False,
    )
    if row_factory:
        con.row_factory = sqlite3.Row
    # SMB-safe PRAGMAs — jeden round-trip.
    con.executescript(
        "PRAGMA journal_mode=DELETE;"
        "PRAGMA busy_timeout=5000;"
        "PRAGMA locking_mode=NORMAL;"
        "PRAGMA synchronous=NORMAL;"
        "PRAGMA cache_size=-2000;"
        "PRAGMA temp_store=MEMORY;"
    )
    # Weryfikuj journal_mode raz na plik - WAL na SMB powoduje korupcję.
    # Klucz: sama ścieżka pliku (dla URI odetnij ?query), by ro/rw dzieliły wpis.
    _key = str(db_path)
    if uri and "?" in _key:
        _key = _key.split("?", 1)[0]
    if _key not in _BAZA_JOURNAL_VERIFIED:
        actual_mode = con.execute("PRAGMA journal_mode").fetchone()[0]
        if actual_mode.upper() != "DELETE":
            print(f"🔴 OSTRZEŻENIE: journal_mode={actual_mode} zamiast DELETE dla {db_path}!")
            print(f"   WAL mode NIE DZIAŁA przez SMB - ryzyko korupcji danych!")
        else:
            _BAZA_JOURNAL_VERIFIED.add(_key)
    return con


def get_supplier_name(db_manager: DatabaseManager, supplier_id: Optional[int]) -> str:
    """Pobierz nazwę dostawcy po ID"""
    if not supplier_id:
        return ""
    
    suppliers = db_manager.get_suppliers()
    for sid, name in suppliers:
        if sid == supplier_id:
            return name
    
    return ""
