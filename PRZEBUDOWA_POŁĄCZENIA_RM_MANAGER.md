# Przebudowa systemu zapisu danych — RM_MANAGER

Data analizy: 2026-04-22

---

## Obecny stan — mapa problemów

### Dwa równoległe systemy locków (duplikat)

| Plik | Klasa | Użycie |
|---|---|---|
| `lock_manager_v2.py` | `ProjectLockManager` | GUI (`rm_manager_gui.py`) — aktywny |
| `rm_lock_manager.py` | `RMLockManager` | 98% identyczny kod, nieużywany |

### Trzy osobne funkcje do otwierania połączeń SQLite

```
rm_manager.py         → _open_rm_connection()
database_manager.py   → _open_baza_connection()
rm_database_manager.py → inline w RMDatabaseManager
```
Każda ustawia te same PRAGMy — skopiowane 3x. Problem estetyczny, nie funkcjonalny.

### Gdzie jest lock — a gdzie go nie ma

**Z lockiem (poprawnie chronione):**
- `release_lock()` → woła `save_all_templates()` przed zwolnieniem
- GUI blokuje pola edycji gdy `not self.have_lock`

**BEZ sprawdzenia locka — zapis mimo wszystko:**

| Funkcja | Plik | Co zapisuje bez locka |
|---|---|---|
| `_restore_dates_from_snapshot()` | `rm_manager_gui.py:1580` | UPDATE `stage_schedule` |
| `save_stage_date()` | `rm_manager_gui.py:7237` | UPDATE `stage_schedule` (inline) |
| `save_milestone_date()` | `rm_manager_gui.py:7340` | UPDATE/INSERT `stage_schedule` |
| Multi-project drag | `rm_manager_gui.py:16313` | UPDATE `stage_schedule` (inline) |
| `apply_optimization()` | `rm_manager_gui.py:21893` | wiele projektów, zero locka |
| `undo_optimization()` | `rm_manager_gui.py:~21930` | wiele projektów, zero locka |
| `update_stage_definitions()` | `rm_manager.py:735` | INSERT/UPDATE master |
| `migrate_*`, `fix_*`, `ensure_*` | `rm_manager.py:3818` | migracje bez locka |
| `toggle_active()`, `delete_selected()` | `rm_manager_gui.py:8620` | master.sqlite bez locka |

### Fundamentalny problem — optymalizator

```
UŻYTKOWNIK A         UŻYTKOWNIK B         OPTYMALIZATOR
przejmuje             przejmuje
project_3.lock        project_5.lock

                                           apply_optimization()
                                           → pisze do project_3, 5, 7, 9
                                           → BEZ sprawdzania locków!
                                           → race condition z A i B
```

Master DB (`rm_manager.sqlite`) nie ma żadnego locka — każdy pisze kiedy chce.

---

## Proponowana architektura

### Koncepcja: dwie warstwy locków

```
LOCKS/
├── project_3.lock      ← per-projekt, 1 użytkownik, heartbeat (istniejące)
├── project_5.lock
└── scheduler.lock      ← NOWY: optymalizator, blokuje cały folder
```

**Reguły wzajemnego wykluczania:**

```
acquire_project_lock(X)  →  sprawdź czy scheduler.lock istnieje → DENY jeśli tak
acquire_scheduler_lock() →  sprawdź czy istnieje JAKIKOLWIEK project_X.lock → DENY jeśli tak
```

---

## Plan wdrożenia

### Krok 1 — Konsolidacja lock managera (~1-2h)

- Usuń `rm_lock_manager.py` (nieużywany duplikat)
- Dodaj 3 nowe metody do `lock_manager_v2.py`:

```python
def acquire_scheduler_lock(self, user: str, reason: str = "optimizer") -> tuple[bool, list]:
    """Optymalizator przejmuje globalną blokadę.
    
    Returns:
        (True, [])        — lock przejęty
        (False, [holders]) — lista użytkowników blokujących
    """
    scheduler_lock = self.locks_folder / "scheduler.lock"

    # Sprawdź czy ktoś ma project lock
    active = list(self.locks_folder.glob("project_*.lock"))
    if active:
        holders = []
        for f in active:
            try:
                holders.append(json.loads(f.read_text(encoding='utf-8')))
            except Exception:
                pass
        return False, holders

    data = {
        "user": user,
        "computer": self.my_computer,
        "reason": reason,
        "locked_at": datetime.now().isoformat()
    }
    scheduler_lock.write_text(json.dumps(data, indent=2), encoding='utf-8')
    return True, []

def release_scheduler_lock(self):
    """Zwolnij globalną blokadę optymalizatora."""
    scheduler_lock = self.locks_folder / "scheduler.lock"
    try:
        scheduler_lock.unlink(missing_ok=True)
    except Exception as e:
        print(f"⚠️ release_scheduler_lock: {e}")

def get_scheduler_lock_owner(self) -> dict | None:
    """Pobierz właściciela globalnej blokady (None = wolne)."""
    scheduler_lock = self.locks_folder / "scheduler.lock"
    if not scheduler_lock.exists():
        return None
    try:
        return json.loads(scheduler_lock.read_text(encoding='utf-8'))
    except Exception:
        return None
```

- Patch `acquire_project_lock()` — dodaj sprawdzenie `scheduler.lock` na początku:

```python
def acquire_project_lock(self, project_id: int, force: bool = False):
    # NOWE: blokuj jeśli optymalizator pracuje
    if not force:
        scheduler_owner = self.get_scheduler_lock_owner()
        if scheduler_owner:
            return False, None
    # ... reszta bez zmian ...
```

---

### Krok 2 — Guard + centralna funkcja zapisu (~2-3h)

Dodać do `RMManagerApp` w `rm_manager_gui.py`:

```python
def _require_lock(self, project_id: int) -> bool:
    """Guard: True tylko jeśli aktualnie mamy ważny lock na project_id.
    
    Weryfikuje plik lock na dysku (nie tylko flagę GUI).
    """
    if not self.have_lock:
        return False
    if self._locked_project_id != project_id:
        return False
    if not getattr(self.lock_manager, '_STUB', False):
        owner = self.lock_manager.get_project_lock_owner(project_id)
        if not owner or owner.get('lock_id') != self.current_lock_id:
            self._on_lock_lost("Lock wymuszony przez innego użytkownika")
            return False
    return True

def _save_stage_schedule(self, project_id: int, stage_code: str,
                          start_iso: str | None, end_iso: str | None) -> bool:
    """Jedyne legalne miejsce zapisu dat etapów do stage_schedule.
    
    Sprawdza lock przed zapisem. Zwraca False jeśli brak locka.
    """
    if not self._require_lock(project_id):
        print(f"🔴 BLOCKED: próba zapisu {stage_code} dla projektu {project_id} bez locka!")
        return False
    try:
        con = rmm._open_rm_connection(
            self.get_project_db_path(project_id), row_factory=False
        )
        con.execute("""
            UPDATE stage_schedule SET template_start = ?, template_end = ?
            WHERE project_stage_id = (
                SELECT id FROM project_stages WHERE project_id = ? AND stage_code = ?
            )
        """, (start_iso, end_iso, project_id, stage_code))
        con.commit()
        con.close()
        return True
    except Exception as e:
        print(f"🔥 _save_stage_schedule({stage_code}): {e}")
        return False
```

Przepiąć następujące funkcje na `_save_stage_schedule()`:
- `save_all_templates()` (`rm_manager_gui.py:7716`)
- `save_stage_date()` (`rm_manager_gui.py:7237`)
- `save_milestone_date()` — część (`rm_manager_gui.py:7340`)
- `_restore_stage_dates_from_snapshot()` (`rm_manager_gui.py:1580`) — guard: skip jeśli lock utracony

---

### Krok 3 — Multi-project drag (~1h)

Plik: `rm_manager_gui.py:16313`

Przed każdym zapisem z drag/drop na wykresie Gantta dodać:

```python
# Przed inline SQL w drag handler:
if not self._require_lock(pid):
    messagebox.showwarning(
        "Brak locka",
        f"Nie masz locka projektu {pid}.\nPrzejmij lock przed edycją wykresu.",
        parent=self._mp_chart_window
    )
    return
```

Docelowo przepiąć inline SQL na `_save_stage_schedule(pid, stage_code, ...)`.

---

### Krok 4 — Optymalizator ze scheduler.lock (~1h)

Plik: `rm_manager_gui.py` — funkcje `_apply_result()` i `_undo_result()` w `_optimizer_build_run_tab()`

```python
def _apply_result():
    result = getattr(btn_apply, '_opt_result', None)
    if not result or not result.get('changes'):
        return

    # 1. Spróbuj przejąć scheduler lock
    ok, blockers = self.lock_manager.acquire_scheduler_lock(
        user=self.current_user, reason="optimizer"
    )
    if not ok:
        names = [b.get('user', '?') for b in blockers if b]
        messagebox.showwarning(
            "Blokada optymalizatora",
            f"Nie można uruchomić optymalizatora.\n\n"
            f"Aktywne locki projektów:\n" + "\n".join(f"  • {n}" for n in names) +
            f"\n\nPoproś użytkowników o zwolnienie locków.",
            parent=dlg
        )
        return

    if not messagebox.askyesno("Potwierdzenie",
            f"Zastosować zmiany optymalizacji?\n\n"
            f"Zmienione zostaną daty template w {len(result['changes'])} projektach.\n"
            f"Operację można cofnąć przyciskiem ↩ Cofnij.",
            parent=dlg):
        self.lock_manager.release_scheduler_lock()
        return

    try:
        apply_result = rm_optimizer.apply_optimization(
            rm_manager_dir=self.rm_projects_dir,
            rm_master_db_path=self.rm_master_db_path,
            changes=result['changes'],
            user=getattr(self, 'current_user', None),
        )
        msg = (f"✅ Zastosowano: {apply_result['applied_projects']} projektów, "
               f"{apply_result['applied_stages']} etapów.")
        if apply_result.get('errors'):
            msg += f"\n\n⚠️ Błędy:\n" + "\n".join(apply_result['errors'])
        messagebox.showinfo("Zastosowano", msg, parent=dlg)
        btn_apply.configure(state=tk.DISABLED)
        if apply_result.get('snapshots'):
            btn_undo._snapshots = apply_result['snapshots']
            btn_undo.configure(state=tk.NORMAL)
    except Exception as e:
        messagebox.showerror("Błąd", f"Nie udało się zastosować:\n{e}", parent=dlg)
    finally:
        # 3. Zawsze zwolnij scheduler lock
        self.lock_manager.release_scheduler_lock()


def _undo_result():
    snapshots = getattr(btn_undo, '_snapshots', None)
    if not snapshots:
        return

    # Scheduler lock przy cofaniu
    ok, blockers = self.lock_manager.acquire_scheduler_lock(
        user=self.current_user, reason="optimizer_undo"
    )
    if not ok:
        names = [b.get('user', '?') for b in blockers if b]
        messagebox.showwarning(
            "Blokada cofania",
            f"Nie można cofnąć optymalizacji.\n\n"
            f"Aktywne locki projektów:\n" + "\n".join(f"  • {n}" for n in names),
            parent=dlg
        )
        return

    if not messagebox.askyesno("Cofnij optymalizację",
            f"Przywrócić daty sprzed optymalizacji w {len(snapshots)} projektach?",
            parent=dlg):
        self.lock_manager.release_scheduler_lock()
        return

    try:
        undo_res = rm_optimizer.undo_optimization(
            rm_manager_dir=self.rm_projects_dir,
            snapshots=snapshots,
        )
        msg = f"↩ Cofnięto: {undo_res['restored_projects']} projektów."
        if undo_res.get('errors'):
            msg += f"\n\n⚠️ Błędy:\n" + "\n".join(undo_res['errors'])
        messagebox.showinfo("Cofnięto", msg, parent=dlg)
        btn_undo.configure(state=tk.DISABLED)
        btn_undo._snapshots = None
    except Exception as e:
        messagebox.showerror("Błąd", f"Nie udało się cofnąć:\n{e}", parent=dlg)
    finally:
        self.lock_manager.release_scheduler_lock()
```

---

## Czego NIE przebudowywać

- **Heartbeat, `stale_lock_seconds`, force** — działają poprawnie, zostawić
- **SQLite PRAGMA** (`journal_mode=DELETE`, `busy_timeout`) — zostawić
- **`_open_rm_connection`** — wystarczy, duplikacja w 3 plikach to problem estetyczny, nie funkcjonalny
- **Master DB** (`rm_manager.sqlite`) — krótkie transakcje + `busy_timeout=5000` wystarczą; dodanie zewnętrznego locka zwielokrotniłoby ryzyko deadlocka
- **Snapshot/undo w optymalizatorze** — `undo_optimization()` już istnieje, wystarczy

---

## Priorytety

| Krok | Czas | Ryzyko pominięcia |
|---|---|---|
| **Krok 4** (scheduler.lock) | ~1h | **WYSOKIE** — optymalizator może nadpisać dane innym użytkownikom |
| **Krok 1** (konsolidacja) | ~1-2h | NISKIE — tylko estetyka/porządek |
| **Krok 2** (guard + centralna fn) | ~2-3h | ŚREDNIE — dziury w edge-casach |
| **Krok 3** (multi-project drag) | ~1h | ŚREDNIE — tylko gdy użytkownik edytuje cudzy projekt |

**Najszybszy zysk: zacząć od Kroku 4.**
