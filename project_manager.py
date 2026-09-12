"""
============================================================================
PROJECT MANAGER - Zarządzanie projektami dla RM_BAZA v10 DISTRIBUTED
============================================================================
Funkcje do zarządzania projektami w masterze — WYŁĄCZNIE przez RM_SERWER.

⚠️ Parametr `con` został w sygnaturach (wołają je dziesiątki miejsc), ale
jest IGNOROWANY: master leży na dysku serwera i klient nie ma połączenia
do pliku. Nowy kod może go po prostu pomijać.

Funkcje:
- Tworzenie nowych projektów
- Edycja projektów (nazwa, ścieżka)
- Aktywacja/dezaktywacja projektów
- Usuwanie projektów
============================================================================
"""

from pathlib import Path
from typing import Optional, Tuple, List
import re
import sqlite3


def _klient():
    """RM_SERWER — jedyna droga do mastera.

    Import w środku funkcji, bo `project_manager` bywa importowany przez
    narzędzia, które serwera nie potrzebują (np. `get_project_db_path`
    liczy samą ścieżkę).
    """
    import rm_klient
    return rm_klient


def norm(s) -> str:
    """Normalizacja tekstu: usuń nadmiarowe spacje"""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).replace("\u00A0", " ")).strip()




def colnames(con=None, table: str = "projects") -> set:
    """Nazwy kolumn tabeli w masterze.

    `con` ignorowane (patrz nagłówek modułu). Schemat czytamy z pierwszego
    wiersza zwróconego przez serwer — to wystarcza, bo wołający pytają
    wyłącznie „czy jest kolumna X".

    Obsługiwane są tabele, dla których serwer ma operację `SELECT *`.
    Dla nieznanej tabeli zwracamy pusty zbiór — wołający i tak sprawdzają
    obecność kolumn, więc zachowają się jak przy starszym schemacie.
    """
    OPERACJE = {"projects": "projects-list", "suppliers": "suppliers-list",
                "users": "users-list"}
    operacja = OPERACJE.get(table)
    if not operacja:
        return set()
    try:
        wiersze = _klient().master_read(operacja)
    except Exception:
        return set()
    return set(wiersze[0].keys()) if wiersze else set()


def pick_col(cols: set, candidates: list) -> Optional[str]:
    """Wybiera pierwszą pasującą kolumnę z listy kandydatów."""
    for c in candidates:
        if c.lower() in cols:
            return c
    return None


# ============================================================================
# PROJEKTY - Podstawowe operacje
# ============================================================================









def fetch_projects(
    con=None,
    only_active: bool = False,
    include_active: bool = False,
    project_type: Optional[str] = None
) -> List[Tuple]:
    """Lista projektów z mastera (przez RM_SERWER).

    `con` jest ignorowane — zostaje w sygnaturze, bo wołają tę funkcję
    dziesiątki miejsc. Master leży na serwerze i klient nie ma połączenia
    do pliku.

    Zwraca krotki: (id, nazwa, ścieżka, typ) albo — przy `include_active` —
    (id, nazwa, ścieżka, aktywny, typ). Kolejność pól zachowana, bo
    wołający rozpakowują je pozycyjnie.
    """
    wiersze = _klient().master_read("projects-list")

    out = []
    for w in wiersze:
        akt = 1 if (w.get("active") is None or w.get("active")) else 0
        if only_active and not akt:
            continue
        typ = w.get("project_type") or "MACHINE"
        if project_type and typ != project_type:
            continue

        pid = int(w.get("project_id"))
        nazwa = str(w.get("name") or "")
        sciezka = str(w.get("path") or "")
        out.append((pid, nazwa, sciezka, akt, typ) if include_active
                   else (pid, nazwa, sciezka, typ))

    # Sortowanie po stronie klienta: SQLite sortowałby po COLLATE NOCASE,
    # ale polskie znaki i tak wymagają `lower()` w Pythonie.
    out.sort(key=lambda r: ((r[1] or "").lower(), r[0]))
    return out


def create_project(
    con=None,
    name: str = "",
    root_path: str = "",
    project_type: str = "MACHINE",
    designer: str = "",
    status: str = "PROJEKT"
) -> int:
    """Zakłada projekt w masterze. Zwraca nadany `project_id`.

    Wpis początkowy w historii statusów leci TYM SAMYM batchem — projekt
    bez historii wyglądałby jak utworzony poza systemem.
    """
    nazwa = norm(name)
    if not nazwa:
        raise ValueError("Nazwa projektu jest wymagana")

    wynik = _klient().master_exec("project-add", {
        "project_id": None,                 # NULL → SQLite nada kolejny numer
        "name": nazwa,
        "path": norm(root_path) if root_path else None,
        "project_type": (project_type
                         if project_type in ("MACHINE", "WAREHOUSE") else "MACHINE"),
        "designer": norm(designer) if designer else None,
        "status": status or "PROJEKT",
    })
    project_id = int((wynik or {}).get("lastrowid") or 0)
    if not project_id:
        raise RuntimeError("Serwer nie zwrócił identyfikatora nowego projektu")

    from datetime import datetime
    try:
        _klient().master_exec("status-historia-zapisz", {
            "project_id": project_id,
            "old_status": None,
            "new_status": status or "PROJEKT",
            "changed_at": datetime.now().isoformat(),
            "changed_by": None,
            "notes": "Utworzenie projektu",
        })
    except Exception:
        pass        # historia jest dziennikiem — jej brak nie unieważnia projektu

    return project_id


def update_project(
    con=None,
    project_id: int = 0,
    name: Optional[str] = None,
    root_path: Optional[str] = None,
    designer: Optional[str] = None,
    montaz: Optional[str] = None,
    fat: Optional[str] = None,
    completed_at: Optional[str] = None,
    expected_delivery: Optional[str] = None,
    received_percent: Optional[str] = None,
    status: Optional[str] = None
) -> None:
    """Edycja projektu. `None` = pole bez zmian (operacja używa COALESCE).

    Status idzie OSOBNO, przez `change_project_status` — ta funkcja
    dopisuje wpis do historii, czego zwykły UPDATE by nie zrobił.
    """
    _klient().master_exec("project-edit", {
        "project_id": int(project_id),
        "name": norm(name) if name is not None else None,
        "path": (norm(root_path) or None) if root_path is not None else None,
        "designer": (norm(designer) or None) if designer is not None else None,
        # `montaz` i `sat` to w tej bazie to samo pole pod dwiema nazwami —
        # zapisujemy obie, żeby okna czytające którąkolwiek widziały zmianę.
        "montaz": montaz,
        "sat": montaz,
        "fat": fat,
        "completed_at": completed_at,
        "expected_delivery": expected_delivery,
        "received_percent": received_percent,
    })

    if status is not None:
        wiersze = _klient().master_read("project-get", {"project_id": int(project_id)})
        stary = (wiersze[0].get("status") if wiersze else None)
        if stary != status:
            change_project_status(None, int(project_id), status,
                                  notes="Zmiana przez GUI")


def set_project_active(con=None, project_id: int = 0, is_active: int = 1) -> None:
    """Włącza/wyłącza projekt. Wyłączony znika z list, ale zostaje w bazie."""
    _klient().master_exec("project-set-active", {
        "project_id": int(project_id),
        "active": 1 if is_active else 0,
    })


def delete_project(con=None, project_id: int = 0) -> None:
    """Usuwa projekt z mastera.

    Statusy, historia i dziennik zmian znikają same — mają
    `ON DELETE CASCADE` na `projects(project_id)`.
    """
    _klient().master_exec("project-delete", {"project_id": int(project_id)})


# ============================================================================
# UTILITY - Dodatkowe pomocnicze funkcje
# ============================================================================

def get_project_info(con=None, project_id: int = 0) -> Optional[Tuple[int, str, str, str]]:
    """(id, nazwa, ścieżka, typ) albo None, gdy projektu nie ma."""
    wiersze = _klient().master_read("project-get", {"project_id": int(project_id)})
    if not wiersze:
        return None
    w = wiersze[0]
    return (int(w.get("project_id")), str(w.get("name") or ""),
            str(w.get("path") or ""), str(w.get("project_type") or "MACHINE"))


def project_exists(con=None, project_id: int = 0) -> bool:
    return get_project_info(None, project_id) is not None


def get_project_db_path(projects_dir: Path, project_id: int, project_type: str = "MACHINE") -> Path:
    """
    Zwraca ścieżkę do pliku bazy danych projektu.
    
    Używa katalogów DOKŁADNIE jak podane w config (projects_dir / projects_mag_dir).
    NIE dodaje żadnych podkatalogów — ścieżka z configu wskazuje bezpośrednio
    na katalog z plikami .sqlite.
    
    Args:
        projects_dir: Katalog z bazami projektów (dokładnie jak w config):
                      - Dla MACHINE: np. Y:/RM_BAZA/projects
                      - Dla WAREHOUSE: np. Y:/RM_BAZA/projects_MAG
        project_id: ID projektu
        project_type: Typ projektu ('MACHINE' lub 'WAREHOUSE')
    
    Returns:
        Ścieżka do pliku: projects_dir/project_X.sqlite lub projects_dir/project_MAG_X.sqlite
    """
    if project_type == "WAREHOUSE":
        filename = f"project_MAG_{project_id}.sqlite"
    else:
        filename = f"project_{project_id}.sqlite"
    
    return projects_dir / filename


# ============================================================================
# ZARZĄDZANIE STATUSAMI I HISTORIĄ
# ============================================================================

# ============================================================================
# MULTI-STATUS SYSTEM - Wiele statusów równocześnie
# ============================================================================

# NOWA LISTA STATUSÓW (multi-select)
PROJECT_STATUSES_NEW = [
    "PRZYJETY",       # Przyjęty do realizacji
    "PROJEKT",        # Faza projektowania
    "KOMPLETACJA",    # Kompletacja materiałów
    "MONTAZ",         # Montaż
    "AUTOMATYKA",     # Prace nad automatyką
    "URUCHOMIENIE",   # Uruchomienie
    "ODBIORY",        # Odbiory
    "POPRAWKI",       # Poprawki
    "WSTRZYMANY",     # Wstrzymany
    "ZAKONCZONY"      # Zakończony
]

# STARA LISTA (backward compatibility - nie używana w nowym systemie)
PROJECT_STATUSES = [
    "PROJEKT",        # Faza projektowania urządzenia
    "W_REALIZACJI",   # Projekt w trakcie realizacji
    "WSTRZYMANY",     # Projekt tymczasowo wstrzymany
    "ZAKOŃCZONY"      # Projekt zakończony
]








def change_project_status(
    con=None,
    project_id: int = 0,
    new_status: str = "",
    changed_by: Optional[str] = None,
    notes: Optional[str] = None
) -> bool:
    """Zmienia status projektu i zapisuje wpis w historii.

    Wszystko jednym batchem (jedna transakcja): historia, samo pole
    `status` i ewentualna data zakończenia. Rozjazd między tymi trzema
    zapisami dałby projekt w stanie, którego historia nie tłumaczy.
    """
    from datetime import datetime

    if new_status not in PROJECT_STATUSES:
        print(f"❌ Nieznany status: {new_status}")
        print(f"   Dozwolone: {', '.join(PROJECT_STATUSES)}")
        return False

    try:
        wiersze = _klient().master_read("project-get", {"project_id": int(project_id)})
        if not wiersze:
            print(f"❌ Projekt {project_id} nie istnieje")
            return False
        stary = wiersze[0].get("status")
        if stary == new_status:
            return True          # nic się nie zmienia — bez pustego wpisu

        teraz = datetime.now().isoformat()
        operacje = [
            {"operation": "status-historia-zapisz",
             "params": {"project_id": int(project_id), "old_status": stary,
                        "new_status": new_status, "changed_at": teraz,
                        "changed_by": changed_by, "notes": notes}},
            {"operation": "project-status-zmien",
             "params": {"project_id": int(project_id), "status": new_status,
                        "status_changed_at": teraz}},
        ]
        if new_status == "ZAKOŃCZONY":
            operacje.append({"operation": "project-zakonczony",
                             "params": {"project_id": int(project_id),
                                        "completed_at": teraz}})
        _klient().master_batch(operacje)
        return True

    except Exception as e:
        print(f"❌ Błąd zmiany statusu: {e}")
        return False


def get_project_status_history(con=None, project_id: int = 0) -> List[Tuple]:
    """Historia zmian statusu: (id, stary, nowy, kiedy, kto, uwagi)."""
    return [(w["id"], w["old_status"], w["new_status"], w["changed_at"],
             w["changed_by"], w["notes"])
            for w in _klient().master_read("status-historia",
                                           {"project_id": int(project_id)})]


def get_project_time_in_status(
    con=None,
    project_id: int = 0,
    status: str = ""
) -> float:
    """Łączny czas (w dniach) spędzony w danym statusie.

    Liczony z historii przejść: od wpisu, który ten status nadał, do
    następnej zmiany. Ostatni odcinek trwa do teraz.
    """
    from datetime import datetime

    try:
        wiersze = _klient().master_read("status-historia-rosnaco",
                                        {"project_id": int(project_id)})
        if not wiersze:
            return 0.0

        razem = 0.0
        for i, w in enumerate(wiersze):
            if w.get("new_status") != status:
                continue
            try:
                od = datetime.fromisoformat(w["changed_at"])
            except Exception:
                continue
            if i + 1 < len(wiersze):
                try:
                    do = datetime.fromisoformat(wiersze[i + 1]["changed_at"])
                except Exception:
                    continue
            else:
                do = datetime.now()      # wciąż w tym statusie
            razem += (do - od).total_seconds() / 86400.0

        return razem
    except Exception as e:
        print(f"⚠️  get_project_time_in_status: {e}")
        return 0.0


def get_all_project_times(
    con=None,
    project_id: int = 0
) -> dict:
    """
    Oblicza czas spędzony w każdym statusie.
    
    Returns:
        Dict: {status: days}
    """
    times = {}
    for status in PROJECT_STATUSES:
        times[status] = get_project_time_in_status(con, project_id, status)
    return times


# ============================================================================
# MULTI-STATUS SYSTEM - Funkcje zarządzania wieloma statusami
# ============================================================================

def get_project_statuses(con=None, project_id: int = 0) -> list:
    """Wszystkie statusy projektu (może mieć kilka naraz), od najstarszego."""
    try:
        return [w["status"] for w in
                _klient().master_read("statusy-projektu",
                                      {"project_id": int(project_id)})]
    except Exception as e:
        print(f"⚠️  get_project_statuses: {e}")
        return []


def set_project_statuses(
    con=None,
    project_id: int = 0,
    statuses: list = None,
    set_by: Optional[str] = None
) -> bool:
    """Ustawia KOMPLET statusów projektu (podmiana, nie dokładanie).

    Wszystko leci jednym batchem — dziennik zmian, podmiana zbioru,
    wpis w historii i znaczniki w `projects`. Rozjazd między nimi dałby
    projekt, którego dzienniki nie tłumaczą.
    """
    from datetime import datetime

    statuses = statuses or []
    for status in statuses:
        if status not in PROJECT_STATUSES_NEW:
            print(f"❌ Nieznany status: {status}")
            print(f"   Dozwolone: {', '.join(PROJECT_STATUSES_NEW)}")
            return False

    try:
        teraz = datetime.now().isoformat()
        stare = set(get_project_statuses(None, project_id))
        nowe = set(statuses)
        dodane, zdjete = nowe - stare, stare - nowe

        operacje = []
        for status in sorted(dodane):
            operacje.append({"operation": "status-zmiana-zapisz",
                             "params": {"project_id": project_id, "status": status,
                                        "action": "ADDED", "changed_at": teraz,
                                        "changed_by": set_by, "notes": None}})
        for status in sorted(zdjete):
            operacje.append({"operation": "status-zmiana-zapisz",
                             "params": {"project_id": project_id, "status": status,
                                        "action": "REMOVED", "changed_at": teraz,
                                        "changed_by": set_by, "notes": None}})

        # Podmiana zbioru: czyścimy i wstawiamy od nowa.
        operacje.append({"operation": "statusy-wyczysc",
                         "params": {"project_id": project_id}})
        for status in statuses:
            operacje.append({"operation": "status-dodaj",
                             "params": {"project_id": project_id, "status": status,
                                        "set_at": teraz, "set_by": set_by}})

        stary_opis = ", ".join(sorted(stare)) if stare else None
        nowy_opis = ", ".join(sorted(nowe)) if nowe else None
        if stary_opis != nowy_opis:
            operacje.append({"operation": "status-historia-zapisz",
                             "params": {"project_id": project_id,
                                        "old_status": stary_opis,
                                        "new_status": nowy_opis,
                                        "changed_at": teraz, "changed_by": set_by,
                                        "notes": "Multi-status update"}})

        operacje.append({"operation": "project-status-znacznik",
                         "params": {"project_id": project_id,
                                    "status_changed_at": teraz}})
        if "ZAKONCZONY" in statuses:
            operacje.append({"operation": "project-zakonczony",
                             "params": {"project_id": project_id,
                                        "completed_at": teraz}})

        _klient().master_batch(operacje)
        return True

    except Exception as e:
        print(f"❌ Błąd zapisu statusów: {e}")
        return False


def add_project_status(
    con=None,
    project_id: int = 0,
    status: str = "",
    set_by: Optional[str] = None
) -> bool:
    """
    Dodaje pojedynczy status do projektu (nie usuwając innych).
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
        status: Status do dodania
        set_by: Kto dodał
    
    Returns:
        True jeśli sukces
    """
    statuses = get_project_statuses(con, project_id)
    if status not in statuses:
        statuses.append(status)
        return set_project_statuses(con, project_id, statuses, set_by)
    return True


def remove_project_status(
    con=None,
    project_id: int = 0,
    status: str = "",
    set_by: Optional[str] = None
) -> bool:
    """
    Usuwa pojedynczy status z projektu.
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
        status: Status do usunięcia
        set_by: Kto usunął
    
    Returns:
        True jeśli sukces
    """
    statuses = get_project_statuses(con, project_id)
    if status in statuses:
        statuses.remove(status)
        return set_project_statuses(con, project_id, statuses, set_by)
    return True


def get_project_statuses_display(con: sqlite3.Connection, project_id: int) -> str:
    """
    Pobiera statusy projektu jako string do wyświetlenia.
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
    
    Returns:
        String: "PROJEKT, MONTAZ, AUTOMATYKA" lub "(brak)"
    """
    statuses = get_project_statuses(con, project_id)
    if not statuses:
        return "(brak)"
    return ", ".join(statuses)


# ============================================================================
# SZCZEGÓŁOWA HISTORIA STATUSÓW - Tracking każdej zmiany osobno
# ============================================================================

def get_status_detailed_history(con=None, project_id: int = 0,
                                status: Optional[str] = None) -> List[Tuple]:
    """Dziennik ADDED/REMOVED: (id, status, akcja, kiedy, kto, uwagi).

    Bez `status` — całość dla projektu; z `status` — tylko ten jeden.
    """
    try:
        if status:
            wiersze = _klient().master_read(
                "status-zmiany-jednego",
                {"project_id": int(project_id), "status": status})
        else:
            wiersze = _klient().master_read(
                "status-zmiany", {"project_id": int(project_id)})
        return [(w["id"], w["status"], w["action"], w["changed_at"],
                 w["changed_by"], w["notes"]) for w in wiersze]
    except Exception as e:
        print(f"⚠️  get_status_detailed_history: {e}")
        return []


def get_status_timeline(
    con=None,
    project_id: int = 0
) -> dict:
    """
    Pobiera pełną linię czasu statusów dla projektu.
    
    Zwraca słownik gdzie klucz to status, wartość to lista zmian:
    {
        "MONTAZ": [
            {"action": "ADDED", "changed_at": "2026-03-26 10:00", "changed_by": "admin"},
            {"action": "REMOVED", "changed_at": "2026-03-27 14:00", "changed_by": "admin"}
        ],
        "ODBIORY": [...]
    }
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
    
    Returns:
        Dict z historią każdego statusu
    """
    history = get_status_detailed_history(con, project_id)
    
    timeline = {}
    for row in history:
        _, status, action, changed_at, changed_by, notes = row
        
        if status not in timeline:
            timeline[status] = []
        
        timeline[status].append({
            "action": action,
            "changed_at": changed_at,
            "changed_by": changed_by,
            "notes": notes
        })
    
    return timeline


def get_status_duration(
    con=None,
    project_id: int = 0,
    status: str = ""
) -> float:
    """
    Oblicza łączny czas (w dniach) spędzony w danym statusie.
    
    Analizuje pary ADDED/REMOVED aby obliczyć rzeczywisty czas.
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
        status: Nazwa statusu
    
    Returns:
        Liczba dni (float)
    """
    from datetime import datetime
    
    history = get_status_detailed_history(con, project_id, status)
    
    if not history:
        return 0.0
    
    total_seconds = 0.0
    added_at = None
    
    # Iteruj od najstarszych do najnowszych (odwróć listę)
    for row in reversed(history):
        _, _, action, changed_at, _, _ = row
        
        try:
            timestamp = datetime.fromisoformat(changed_at)
        except:
            continue
        
        if action == "ADDED":
            added_at = timestamp
        elif action == "REMOVED" and added_at is not None:
            delta = (timestamp - added_at).total_seconds()
            total_seconds += delta
            added_at = None
    
    # Jeśli status jest nadal aktywny (ADDED bez REMOVED)
    if added_at is not None:
        now = datetime.now()
        delta = (now - added_at).total_seconds()
        total_seconds += delta
    
    return total_seconds / 86400.0  # Konwertuj na dni


def get_all_statuses_duration(con=None, project_id: int = 0) -> dict:
    """Czas spędzony w każdym statusie: {status: liczba_dni}."""
    try:
        uzyte = [w["status"] for w in _klient().master_read(
            "status-lista-uzytych", {"project_id": int(project_id)})]
        return {s: get_status_duration(None, project_id, s) for s in uzyte}
    except Exception as e:
        print(f"⚠️  get_all_statuses_duration: {e}")
        return {}


def is_status_currently_active(
    con=None,
    project_id: int = 0,
    status: str = ""
) -> bool:
    """
    Sprawdza czy dany status jest obecnie aktywny dla projektu.
    
    Args:
        con: Połączenie z master.sqlite
        project_id: ID projektu
        status: Nazwa statusu
    
    Returns:
        True jeśli status jest aktywny
    """
    current_statuses = get_project_statuses(con, project_id)
    return status in current_statuses


