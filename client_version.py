"""
client_version.py — kontrola wersji klienta RM_BAZA i heartbeat sesji.

Dwa mechanizmy, wspólny cel: żeby nikt nie pracował na starej binarce.

1. BRAMKA STARTU (check_outdated)
   Przy starcie porównuje własny .exe z wzorcowym na serwerze
   (Y:/RMPAK_CLIENT/RM_BAZA_v15_MAG.exe — to samo miejsce, z którego
   aktualizuje RM_Tray_Organizer). Jeśli serwerowy jest NOWSZY i INNY —
   klient jest przestarzały i nie powinien dotykać mastera.

   "Wzorzec" to rozmiar + mtime. Nie hash: 127 MB przez SMB przy każdym
   starcie to kilka sekund, a copy2/Explorer zachowują mtime, więc para
   (rozmiar, mtime) jednoznacznie identyfikuje build. Lokalny NOWSZY niż
   serwerowy to nie błąd — to deweloper ze świeżym buildem.

2. HEARTBEAT SESJI (heartbeat / close_session)
   Co tick istniejącego heartbeatu locków (2 min) wpisuje do tabeli
   `client_sessions` w masterze: host, użytkownik, build .exe, PID,
   ostatni sygnał. Dzięki temu jedno zapytanie mówi, KTO jest zalogowany
   i NA CZYM. Okno "Sesje klientów" (menu Narzędzia) pokazuje to na czerwono
   dla przestarzałych.

Zasady:
- Heartbeat NIGDY nie używa master_con aplikacji: tick leci w wątku
  roboczym, a połączenia sqlite3 nie są współdzielone między wątkami.
  Otwiera własne, krótkie połączenie z busy_timeout 2 s i po zapisie zamyka.
- Master jest w journal_mode=delete (celowo, WAL po SMB się rozpada), więc
  każdy zapis blokuje plik dla wszystkich — heartbeat jest jednym małym
  UPSERT-em i przy "database is locked" po prostu odpuszcza do następnego
  ticku. Nigdy nie rzuca do GUI.
- Praca ze źródeł (nie-frozen) omija bramkę: nie ma własnego .exe do
  porównania. Heartbeat wtedy raportuje build "src".
"""

import os
import socket
import sqlite3
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

DEFAULT_SERVER_EXE = "Y:/RMPAK_CLIENT/RM_BAZA_v15_MAG.exe"

# Tolerancja mtime: kopiowanie przez SMB potrafi zaokrąglić do 2 s (FAT-owe
# dziedzictwo w timestampach), a mtime identycznego pliku nie może różnić
# się bardziej.
_MTIME_TOL_S = 2.0

_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS client_sessions (
    host        TEXT PRIMARY KEY,
    username    TEXT,
    role        TEXT,
    exe_path    TEXT,
    exe_size    INTEGER,
    exe_mtime   TEXT,
    build_id    TEXT,
    pid         INTEGER,
    started_at  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    ended_at    TEXT
)
"""

_PROCESS_STARTED_AT = datetime.now().isoformat(timespec="seconds")
_hb_error_reported = False   # loguj pierwszą awarię heartbeatu, nie każdą


# ─────────────────────────────────────────────────────────────────────────────
# Identyfikacja własnej binarki
# ─────────────────────────────────────────────────────────────────────────────

def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def own_exe_path() -> Optional[Path]:
    """Ścieżka własnego .exe (onefile: sys.executable to bootloader = ten sam
    plik, który skopiował TRAY). Ze źródeł → None."""
    if not is_frozen():
        return None
    return Path(sys.executable)


def hostname() -> str:
    return socket.gethostname().upper()


def _stat_with_timeout(path: Path, timeout_s: float):
    """os.stat w wątku z limitem — stat na zamapowanym, ale martwym udziale
    SMB potrafi wisieć 30–60 s. Zwraca os.stat_result albo None."""
    box = [None]

    def _run():
        try:
            box[0] = path.stat()
        except Exception:
            box[0] = None

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    return box[0]


def build_info(path: Optional[Path], timeout_s: float = 3.0) -> Optional[dict]:
    """(rozmiar, mtime, build_id) pliku albo None gdy niedostępny."""
    if path is None:
        return None
    st = _stat_with_timeout(path, timeout_s)
    if st is None:
        return None
    mtime = datetime.fromtimestamp(st.st_mtime)
    return {
        "path": str(path),
        "size": st.st_size,
        "mtime": st.st_mtime,
        "mtime_str": mtime.strftime("%Y-%m-%d %H:%M:%S"),
        "build_id": f"{st.st_size}-{int(st.st_mtime)}",
    }


def own_build_info() -> dict:
    """Build własnego procesu: ze źródeł → 'src' + ścieżka skryptu."""
    p = own_exe_path()
    if p is None:
        main = Path(sys.argv[0]).resolve() if sys.argv and sys.argv[0] else None
        return {
            "path": str(main) if main else "<src>",
            "size": None, "mtime": None, "mtime_str": None,
            "build_id": "src",
        }
    return build_info(p) or {
        "path": str(p), "size": None, "mtime": None, "mtime_str": None,
        "build_id": "unknown",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Bramka startu
# ─────────────────────────────────────────────────────────────────────────────

def server_exe_path(config: Optional[dict] = None) -> Path:
    """Wzorcowy .exe na serwerze; nadpisywalny w sync_config.json →
    paths.server_exe."""
    paths = (config or {}).get("paths", {}) if isinstance(config, dict) else {}
    return Path(paths.get("server_exe") or DEFAULT_SERVER_EXE)


def is_outdated(local: Optional[dict], server: Optional[dict]) -> bool:
    """Lokalny build jest przestarzały, gdy serwerowy jest NOWSZY i INNY.

    - identyczny rozmiar → ten sam build (mtime może się różnić o zaokrąglenie)
    - lokalny nowszy niż serwerowy → build deweloperski, nie blokuj
    - brak któregokolwiek → nie da się orzec, nie blokuj
    """
    if not local or not server:
        return False
    if local.get("size") is None or server.get("size") is None:
        return False
    if local["size"] == server["size"]:
        return False
    return (server["mtime"] - local["mtime"]) > _MTIME_TOL_S


def check_outdated(config: Optional[dict] = None) -> dict:
    """Porównaj własny .exe z serwerowym.

    Zwraca dict: {outdated, local, server, reason}. Nigdy nie rzuca —
    problem z dostępem do serwera oznacza "nie wiem", a nie "blokuj":
    bramka ma zatrzymać starą wersję, nie odciąć wszystkich, gdy ktoś
    przeniesie katalog na serwerze.
    """
    ui = (config or {}).get("ui", {}) if isinstance(config, dict) else {}
    if ui.get("version_gate", True) is False:
        return {"outdated": False, "local": None, "server": None,
                "reason": "version_gate=false w sync_config.json"}

    local_path = own_exe_path()
    if local_path is None:
        return {"outdated": False, "local": own_build_info(), "server": None,
                "reason": "praca ze źródeł — bramka pominięta"}

    local = build_info(local_path)
    srv_path = server_exe_path(config)
    server = build_info(srv_path)

    if server is None:
        return {"outdated": False, "local": local, "server": None,
                "reason": f"wzorzec niedostępny: {srv_path}"}

    outdated = is_outdated(local, server)
    return {
        "outdated": outdated,
        "local": local,
        "server": server,
        "reason": "serwerowy build jest nowszy" if outdated else "aktualny",
    }


def self_update(server: Path, local: Path) -> str:
    """Podmień własny .exe na serwerowy.

    Windows nie pozwala nadpisać uruchomionego .exe, ale pozwala go
    PRZEMIANOWAĆ — więc: bieżący → .old, serwerowy → na miejsce. Przy
    nieudanej kopii .old wraca na swoje miejsce. Zwraca opis do pokazania
    użytkownikowi; rzuca przy niepowodzeniu (wołający pokazuje komunikat
    z instrukcją ręczną).
    """
    import shutil

    old = local.with_suffix(local.suffix + ".old")
    if old.exists():
        old.unlink()
    local.rename(old)
    try:
        shutil.copy2(str(server), str(local))
    except Exception:
        try:
            if local.exists():
                local.unlink()
        finally:
            old.rename(local)
        raise
    return (f"Pobrano nową wersję:\n{server}\n→ {local}\n\n"
            f"Poprzednia zachowana jako:\n{old}")


# ─────────────────────────────────────────────────────────────────────────────
# Heartbeat sesji
# ─────────────────────────────────────────────────────────────────────────────

def _open_master_rw(master_path, timeout_s: float = 2.0) -> sqlite3.Connection:
    con = sqlite3.connect(str(master_path), timeout=timeout_s)
    con.execute(f"PRAGMA busy_timeout={int(timeout_s * 1000)}")
    return con


def heartbeat(master_path, username: Optional[str], role: Optional[str],
              build: Optional[dict] = None) -> bool:
    """Jeden UPSERT do client_sessions. True gdy zapisano.

    Nie rzuca. Pierwszą awarię loguje, kolejne milczą (locked na masterze
    w journal=delete to zdarzenie zwykłe, nie warte spamu w konsoli).
    """
    global _hb_error_reported
    if not master_path:
        return False
    build = build or own_build_info()
    now = datetime.now().isoformat(timespec="seconds")
    try:
        con = _open_master_rw(master_path)
        try:
            con.execute(_SESSIONS_DDL)
            con.execute(
                """
                INSERT INTO client_sessions
                    (host, username, role, exe_path, exe_size, exe_mtime,
                     build_id, pid, started_at, last_seen, ended_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(host) DO UPDATE SET
                    username  = excluded.username,
                    role      = excluded.role,
                    exe_path  = excluded.exe_path,
                    exe_size  = excluded.exe_size,
                    exe_mtime = excluded.exe_mtime,
                    build_id  = excluded.build_id,
                    pid       = excluded.pid,
                    started_at = CASE WHEN client_sessions.pid = excluded.pid
                                      THEN client_sessions.started_at
                                      ELSE excluded.started_at END,
                    last_seen = excluded.last_seen,
                    ended_at  = NULL
                """,
                (hostname(), username, role, build.get("path"),
                 build.get("size"), build.get("mtime_str"),
                 build.get("build_id"), os.getpid(),
                 _PROCESS_STARTED_AT, now),
            )
            con.commit()
        finally:
            con.close()
        _hb_error_reported = False
        return True
    except Exception as e:
        if not _hb_error_reported:
            print(f"⚠️  client_sessions heartbeat: {e}")
            _hb_error_reported = True
        return False


def close_session(master_path) -> None:
    """Oznacz własną sesję jako zakończoną (wołane przy zamykaniu)."""
    if not master_path:
        return
    try:
        con = _open_master_rw(master_path, timeout_s=1.0)
        try:
            con.execute(
                "UPDATE client_sessions SET ended_at=?, last_seen=? "
                "WHERE host=? AND pid=?",
                (datetime.now().isoformat(timespec="seconds"),
                 datetime.now().isoformat(timespec="seconds"),
                 hostname(), os.getpid()),
            )
            con.commit()
        finally:
            con.close()
    except Exception:
        pass


def list_sessions(master_path, stale_after_s: int = 300) -> list:
    """Wiersze client_sessions + pola pochodne: `alive` (świeży sygnał,
    bez ended_at) i `age_s`. Tylko odczyt."""
    rows = []
    try:
        con = sqlite3.connect(f"file:{master_path}?mode=ro", uri=True, timeout=2.0)
        con.row_factory = sqlite3.Row
        try:
            cur = con.execute(
                "SELECT * FROM client_sessions ORDER BY ended_at IS NOT NULL, last_seen DESC"
            )
            now = time.time()
            for r in cur.fetchall():
                d = dict(r)
                try:
                    seen = datetime.fromisoformat(d["last_seen"]).timestamp()
                    d["age_s"] = int(now - seen)
                except Exception:
                    d["age_s"] = None
                d["alive"] = (d.get("ended_at") is None
                              and d["age_s"] is not None
                              and d["age_s"] <= stale_after_s)
                rows.append(d)
        finally:
            con.close()
    except sqlite3.OperationalError as e:
        if "no such table" not in str(e).lower():
            print(f"⚠️  list_sessions: {e}")
    except Exception as e:
        print(f"⚠️  list_sessions: {e}")
    return rows
