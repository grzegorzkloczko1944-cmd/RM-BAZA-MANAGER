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

### Koncepcja: optymalizator jako superużytkownik z per-project lockami

Optymalizator używa **istniejącego** mechanizmu `acquire_project_lock` — zakłada locki
na wszystkie wybrane projekty jednocześnie, pracuje na lokalnych kopiach, uploaduje, zwalnia.

```
LOCKS/
├── project_3.lock      ← per-projekt, zakładany również przez optymalizator
├── project_5.lock
└── project_7.lock
```

**Flow optymalizatora:**
```
1. Użytkownik klika "Zastosuj wynik"
2. Pętla: acquire_project_lock(pid) dla każdego wybranego projektu
   → któryś zajęty → abort + informacja "projekt X zajęty przez Kowalskiego"
   → wszystkie wolne → kontynuuj
3. Skopiuj lokalne kopie (snapshot do undo)
4. apply_optimization() pisze do lokalnych kopii
5. Upload plików na serwer (shutil.copy2)
6. finally: release_project_lock() dla każdego przejętego projektu
```

**Zalety nad scheduler.lock:**
- Zero nowego kodu w `lock_manager_v2.py` — `acquire_project_lock` już istnieje
- Użytkownik widzi konflikty identycznie jak przy normalnej pracy
- Heartbeat automatycznie odświeża locki podczas liczenia solvera
- Undo używa tych samych lokalnych kopii (snapshotów)
- Brak nowego typu pliku lock — prostsze

**Jedyne nowe w GUI:**
Pętla `acquire` po liście projektów + zbiorcze `release` w bloku `finally`.

---

## Plan wdrożenia

### Krok 1 — Konsolidacja lock managera (~1h)

- Usuń `rm_lock_manager.py` (nieużywany duplikat — 98% identyczny z `lock_manager_v2.py`)

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

### Krok 4 — Optymalizator z per-project lockami (~1h)

Plik: `rm_manager_gui.py` — funkcje `_apply_result()` i `_undo_result()` w `_optimizer_build_run_tab()`

```python
def _apply_result():
    result = getattr(btn_apply, '_opt_result', None)
    if not result or not result.get('changes'):
        return

    target_pids = [int(pid) for pid in result['changes'].keys()]

    # 1. Przejąć locki na wszystkie projekty objęte zmianami
    acquired = []
    conflicts = []
    for pid in target_pids:
        success, lock_id = self.lock_manager.acquire_project_lock(pid, force=False)
        if success:
            acquired.append((pid, lock_id))
        else:
            owner = self.lock_manager.get_project_lock_owner(pid)
            who = self._get_user_display_name(owner.get('user', '?')) if owner else '?'
            conflicts.append(f"  • Projekt {pid}: zajęty przez {who}")

    if conflicts:
        # Sprawdź czy wszystkie konflikty są przeterminowane (stale)
        stale_pids = []
        fresh_pids = []
        for pid in [int(c.split()[2].rstrip(':')) for c in conflicts]:
            owner = self.lock_manager.get_project_lock_owner(pid)
            age = self.lock_manager._lock_age_seconds(owner) if owner else None
            if age is None or age >= self.lock_manager.stale_lock_seconds:
                stale_pids.append(pid)
            else:
                fresh_pids.append(pid)

        # Dialog z trzema opcjami
        conflict_win = tk.Toplevel(dlg)
        conflict_win.title("⚠️ Konflikty locków")
        conflict_win.transient(dlg)
        conflict_win.grab_set()

        tk.Label(conflict_win,
                 text="Nie można zastosować optymalizacji — zajęte projekty:",
                 font=("Arial", 10, "bold"), pady=8).pack(padx=15)
        tk.Label(conflict_win,
                 text="\n".join(conflicts),
                 font=("Consolas", 9), justify="left").pack(padx=15)

        force_choice = tk.StringVar(value='cancel')

        btn_frame = tk.Frame(conflict_win, pady=10)
        btn_frame.pack()

        def _choose(val):
            force_choice.set(val)
            conflict_win.destroy()

        tk.Button(btn_frame, text="Anuluj", width=14,
                  command=lambda: _choose('cancel')).pack(side=tk.LEFT, padx=5)

        btn_stale = tk.Button(btn_frame, text="⚡ Wymuś przeterminowane", width=22,
                              fg="white", bg="#e67e22",
                              command=lambda: _choose('force_stale'),
                              state=tk.NORMAL if stale_pids else tk.DISABLED)
        btn_stale.pack(side=tk.LEFT, padx=5)

        tk.Button(btn_frame, text="💀 Wymuś WSZYSTKIE", width=18,
                  fg="white", bg="#c0392b",
                  command=lambda: _choose('force_all')).pack(side=tk.LEFT, padx=5)

        conflict_win.wait_window()
        choice = force_choice.get()

        if choice == 'cancel':
            # Zwolnij już przejęte locki i abort
            for pid, _ in acquired:
                self.lock_manager.release_project_lock(pid)
            return

        # Wymuś — przejmij siłowo konfliktowe locki
        pids_to_force = stale_pids if choice == 'force_stale' else \
                        [int(c.split()[2].rstrip(':')) for c in conflicts]
        for pid in pids_to_force:
            success, lock_id = self.lock_manager.acquire_project_lock(pid, force=True)
            if success:
                acquired.append((pid, lock_id))
            else:
                # Nie udało się nawet wymusić — abort wszystkiego
                for apid, _ in acquired:
                    self.lock_manager.release_project_lock(apid)
                messagebox.showerror("Błąd", f"Nie udało się wymusić locka projektu {pid}.", parent=dlg)
                return

    if not messagebox.askyesno("Potwierdzenie",
            f"Zastosować zmiany optymalizacji?\n\n"
            f"Zmienione zostaną daty template w {len(result['changes'])} projektach.\n"
            f"Operację można cofnąć przyciskiem ↩ Cofnij.",
            parent=dlg):
        for pid, _ in acquired:
            self.lock_manager.release_project_lock(pid)
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
        # 3. Zawsze zwolnij wszystkie przejęte locki
        for pid, _ in acquired:
            self.lock_manager.release_project_lock(pid)
        # Odśwież GUI jeśli aktualnie otwarty projekt był w puli
        if self.selected_project_id in target_pids:
            self._refresh_combo_lock_info()
            self._update_lock_buttons_state()


def _undo_result():
    snapshots = getattr(btn_undo, '_snapshots', None)
    if not snapshots:
        return

    target_pids = list(snapshots.keys()) if isinstance(snapshots, dict) else []

    # Przejąć locki na projekty do cofnięcia
    acquired = []
    conflicts = []
    for pid in target_pids:
        success, lock_id = self.lock_manager.acquire_project_lock(int(pid), force=False)
        if success:
            acquired.append((int(pid), lock_id))
        else:
            owner = self.lock_manager.get_project_lock_owner(int(pid))
            who = self._get_user_display_name(owner.get('user', '?')) if owner else '?'
            conflicts.append(f"  • Projekt {pid}: zajęty przez {who}")

    if conflicts:
        # Identyczny dialog jak w _apply_result — Anuluj / Wymuś przeterminowane / Wymuś WSZYSTKIE
        # (ten sam kod co powyżej — w implementacji wydzielić do helper _optimizer_force_lock_dialog)
        pass  # → patrz _apply_result po szczegóły
        return  # jeśli cancel lub błąd wymuszenia

    if not messagebox.askyesno("Cofnij optymalizację",
            f"Przywrócić daty sprzed optymalizacji w {len(snapshots)} projektach?",
            parent=dlg):
        for pid, _ in acquired:
            self.lock_manager.release_project_lock(pid)
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
        for pid, _ in acquired:
            self.lock_manager.release_project_lock(pid)
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
| **Krok 4** (optimizer per-project locks) | ~1h | **WYSOKIE** — optymalizator może nadpisać dane innym użytkownikom |
| **Krok 1** (usuń rm_lock_manager.py) | ~15min | NISKIE — tylko porządek |
| **Krok 2** (guard + centralna fn) | ~2-3h | ŚREDNIE — dziury w edge-casach |
| **Krok 3** (multi-project drag) | ~1h | ŚREDNIE — tylko gdy użytkownik edytuje cudzy projekt |

**Najszybszy zysk: zacząć od Kroku 4.**
