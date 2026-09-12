# -*- coding: utf-8 -*-
"""Blokady projektów pilnowane przez RM_SERWER.

Zastępuje `lock_manager_v2` (plik = blokada w katalogu LOCKS na dysku
sieciowym). Interfejs jest ten sam, więc `rm_manager_gui` używa obu tak samo
— różni się tylko to, gdzie leży prawda o zajętości:

    dawniej   project_<id>.lock na Y:  — kto pierwszy utworzył plik
    teraz     tabela project_locks     — kto pierwszy zapisał wiersz

Czemu to lepsze: katalog na dysku sieciowym nie potrafi powiedzieć „ten wpis
już istnieje". Dwa komputery mogły utworzyć plik niemal równocześnie i oba
uznać, że mają blokadę. Tutaj pilnuje tego klucz główny tabeli, a serwer
wykonuje polecenia pojedynczo, więc dwóch zwycięzców być nie może.

Reguły zachowane z wersji plikowej:
- jeden użytkownik trzyma jeden projekt (`acquire_project_lock` zwalnia
  pozostałe swoje blokady); wyjątkiem jest tryb zbiorczy dla linii
  produkcyjnej,
- blokada bez bicia serca od `stale_seconds` jest przeterminowana i można ją
  przejąć,
- `force` przejmuje bez patrzenia na wiek.
"""
from __future__ import annotations

import socket
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

DOMYSLNY_LIMIT_S = 300          # 5 minut bez bicia serca = blokada porzucona


def _teraz() -> str:
    return datetime.now().isoformat()


class ProjectLockManager:
    """Blokady projektów w bazie RM_MANAGER na serwerze."""

    def __init__(self, config: dict):
        self.my_name = (config.get("client", {}) or {}).get("name") or "?"
        self.my_computer = socket.gethostname()
        locks = config.get("locks", {}) or {}
        self.stale_lock_seconds = int(locks.get("stale_seconds", DOMYSLNY_LIMIT_S))
        self._my_locks: Set[int] = set()
        print("🔧 LockManager: blokady na RM_SERWER (tabela project_locks)")
        print("💻 Mój komputer: %s" % self.my_computer)
        print("⏱️  Limit bez bicia serca: %ss" % self.stale_lock_seconds)

    # ── dostęp do serwera ────────────────────────────────────────────────
    def _rmm(self):
        import rm_manager
        return rm_manager

    def _czytaj(self, operacja: str, params: dict = None) -> list:
        try:
            return self._rmm().rmm_read(operacja, params or {})
        except Exception as e:
            print("⚠️  Blokady — odczyt %s: %s" % (operacja, e))
            return []

    def _pisz(self, operacja: str, params: dict) -> Optional[dict]:
        """Zwraca odpowiedź serwera (z `rowcount`) albo None przy błędzie.
        Liczba zmienionych wierszy rozstrzyga, czy przejęcie się udało."""
        try:
            return self._rmm().rmm_exec(operacja, params) or {}
        except Exception as e:
            print("⚠️  Blokady — zapis %s: %s" % (operacja, e))
            return None

    # ── pomocnicze ───────────────────────────────────────────────────────
    def _wiek_s(self, owner: Optional[Dict]) -> Optional[float]:
        """Wiek bicia serca w sekundach; None gdy brak daty lub zła."""
        if not owner:
            return None
        hb = owner.get("last_heartbeat") or owner.get("locked_at")
        if not hb:
            return None
        try:
            return (datetime.now() - datetime.fromisoformat(str(hb))).total_seconds()
        except Exception:
            return None

    def _moj(self, owner: Optional[Dict]) -> bool:
        """Czy blokada jest moja. Przyjmuje oba zestawy nazw: surowy wiersz
        z serwera (uzytkownik/komputer) i przemianowany dla GUI
        (user/computer) — inaczej właściciel nie rozpoznaje własnej blokady."""
        if not owner:
            return False
        kto = owner.get("uzytkownik", owner.get("user"))
        gdzie = owner.get("komputer", owner.get("computer"))
        return kto == self.my_name and gdzie == self.my_computer

    def _na_slownik(self, w: dict) -> dict:
        """Nazwy pól jak w wersji plikowej — GUI czyta `user` i `computer`."""
        return {"lock_id": w.get("lock_id"),
                "user": w.get("uzytkownik"),
                "computer": w.get("komputer"),
                "locked_at": w.get("locked_at"),
                "last_heartbeat": w.get("last_heartbeat")}

    def _zapisz_blokade(self, project_id: int, force: bool = False) -> Tuple[bool, Optional[str]]:
        """Przejmij projekt jednym poleceniem. Serwer nadpisze wiersz tylko
        gdy blokada jest moja albo porzucona, więc przy równoczesnej próbie
        z kilku stacji wygrywa dokładnie jedna — reszta dostaje `rowcount = 0`.
        Sprawdzanie „czy wolny", a potem osobny zapis, dawało kilku
        zwycięzców naraz."""
        project_id = int(project_id)
        lock_id = str(uuid.uuid4())
        teraz = _teraz()
        dane = {"project_id": project_id, "lock_id": lock_id,
                "uzytkownik": self.my_name, "komputer": self.my_computer,
                "locked_at": teraz, "last_heartbeat": teraz}
        if force:
            odp = self._pisz("rmm-lock-przejmij-sila", dane)
        else:
            dane["granica"] = self._granica()
            odp = self._pisz("rmm-lock-przejmij", dane)
        if odp is None:
            print("❌ Nie udało się przejąć projektu %s" % project_id)
            return (False, None)
        if not odp.get("rowcount"):
            wl = self.get_project_lock_owner(project_id)
            print("🔴 Projekt %s zajął ktoś inny: %s@%s"
                  % (project_id, (wl or {}).get("user"), (wl or {}).get("computer")))
            self._my_locks.discard(project_id)
            return (False, None)
        self._my_locks.add(project_id)
        print("✅ Projekt %s przejęty: %s@%s (%s…)"
              % (project_id, self.my_name, self.my_computer, lock_id[:8]))
        return (True, lock_id)

    def _granica(self) -> str:
        """Bicie serca starsze niż to = blokada porzucona."""
        return (datetime.now() - timedelta(seconds=self.stale_lock_seconds)).isoformat()

    # ── odczyt stanu ─────────────────────────────────────────────────────
    def get_project_lock_owner(self, project_id: int) -> Optional[Dict]:
        w = self._czytaj("rmm-lock-po-projekcie", {"project_id": int(project_id)})
        return self._na_slownik(w[0]) if w else None

    def get_all_lock_owners(self) -> Dict[int, Dict]:
        """Właściciele WSZYSTKICH blokad, jednym zapytaniem: {project_id: dane}.

        Do odświeżania listy projektów, gdzie interesuje nas stan wielu naraz.
        Pytanie po jednym (`get_project_lock_owner` w pętli) to przy 87
        projektach 883 ms i osiemdziesiąt kilka pakietów — zbiorczo 16 ms
        i jeden, bo tabela blokad ma zwykle kilka wierszy, nie tyle co
        projektów. Serwer i tak wykonuje polecenia po kolei, jednym wątkiem.
        """
        wynik = {}
        for w in self._czytaj("rmm-locki-wszystkie"):
            try:
                wynik[int(w["project_id"])] = self._na_slownik(w)
            except (KeyError, TypeError, ValueError):
                continue
        return wynik

    def have_project_lock(self, project_id: int) -> bool:
        return int(project_id) in self._my_locks

    def get_my_locked_projects(self) -> Set[int]:
        return set(self._my_locks)

    # ── przejmowanie ─────────────────────────────────────────────────────
    def acquire_project_lock(self, project_id: int, force: bool = False) -> Tuple[bool, Optional[str]]:
        """Przejmij projekt. Zwraca (udało się, identyfikator blokady)."""
        project_id = int(project_id)
        self._release_my_other_locks(project_id)
        owner = self.get_project_lock_owner(project_id)

        if owner is None:
            print("🔓 Projekt %s wolny — przejmuję" % project_id)
            return self._zapisz_blokade(project_id)

        if self._moj(owner):
            print("✅ Projekt %s: już mój" % project_id)
            self._my_locks.add(project_id)
            return (True, owner.get("lock_id") or str(uuid.uuid4()))

        if force:
            print("⚡ Projekt %s: wymuszam przejęcie" % project_id)
            return self._zapisz_blokade(project_id, force=True)

        wiek = self._wiek_s(owner)
        if wiek is None:
            print("🔓 Projekt %s: brak bicia serca — przejmuję" % project_id)
            return self._zapisz_blokade(project_id)
        if wiek < self.stale_lock_seconds:
            print("🔴 Projekt %s zajęty przez %s@%s (bicie serca %ds temu)"
                  % (project_id, owner.get("user"), owner.get("computer"), int(wiek)))
            return (False, None)
        print("🔓 Projekt %s: bicie serca przeterminowane (%ds, limit %ds) — przejmuję"
              % (project_id, int(wiek), self.stale_lock_seconds))
        return self._zapisz_blokade(project_id)

    def acquire_project_locks_bulk(self, project_ids: List[int],
                                   force: bool = False) -> Dict[int, Tuple[bool, Optional[str]]]:
        """Przejmij wiele projektów naraz (linia produkcyjna). Bez reguły
        „jeden projekt na osobę"; zwalnia własne blokady spoza zestawu."""
        idy = [int(p) for p in project_ids]
        self._zwolnij_moje_poza(idy)
        wyniki: Dict[int, Tuple[bool, Optional[str]]] = {}
        for pid in idy:
            owner = self.get_project_lock_owner(pid)
            if owner is None:
                wyniki[pid] = self._zapisz_blokade(pid)
            elif self._moj(owner):
                self._my_locks.add(pid)
                wyniki[pid] = (True, owner.get("lock_id") or str(uuid.uuid4()))
            elif force:
                wyniki[pid] = self._zapisz_blokade(pid, force=True)
            else:
                wiek = self._wiek_s(owner)
                wyniki[pid] = (self._zapisz_blokade(pid)
                               if wiek is None or wiek >= self.stale_lock_seconds
                               else (False, None))
        return wyniki

    # ── zwalnianie ───────────────────────────────────────────────────────
    def _zwolnij_moje_poza(self, zostaw: List[int]):
        import json
        self._pisz("rmm-lock-zwolnij-moje-poza", {
            "uzytkownik": self.my_name, "komputer": self.my_computer,
            "idy_json": json.dumps([int(p) for p in zostaw])})
        self._my_locks = {p for p in self._my_locks if p in set(int(x) for x in zostaw)}

    def _release_my_other_locks(self, except_project_id: int):
        """Reguła „jeden projekt na osobę": zwolnij wszystkie poza tym."""
        self._zwolnij_moje_poza([int(except_project_id)])

    def release_project_lock(self, project_id: int):
        project_id = int(project_id)
        if self._pisz("rmm-lock-zwolnij-moj", {
                "project_id": project_id, "uzytkownik": self.my_name,
                "komputer": self.my_computer}):
            print("🔓 Projekt %s zwolniony" % project_id)
        self._my_locks.discard(project_id)

    def cleanup_all_my_locks(self):
        """Zwolnij wszystko, co trzymam (zamykanie programu)."""
        self._zwolnij_moje_poza([])
        self._my_locks.clear()

    def cleanup_my_computer_locks(self) -> int:
        """Posprzątaj blokady tego komputera (np. po awarii programu)."""
        ile = len(self._czytaj("rmm-locki-wszystkie"))
        przed = [w for w in self._czytaj("rmm-locki-wszystkie")
                 if w.get("komputer") == self.my_computer]
        self._pisz("rmm-lock-zwolnij-komputer", {"komputer": self.my_computer})
        self._my_locks.clear()
        if przed:
            print("🧹 Usunięto %d blokad tego komputera" % len(przed))
        return len(przed)

    def cleanup_stale_locks(self) -> int:
        """Usuń blokady bez bicia serca ponad limit."""
        granica = self._granica()
        stare = [w for w in self._czytaj("rmm-locki-wszystkie")
                 if not w.get("last_heartbeat") or str(w["last_heartbeat"]) < granica]
        if stare:
            self._pisz("rmm-locki-usun-przeterminowane", {"granica": granica})
            for w in stare:
                print("🧹 Usunięto porzuconą blokadę projektu %s (%s@%s)"
                      % (w.get("project_id"), w.get("uzytkownik"), w.get("komputer")))
            for w in stare:
                self._my_locks.discard(int(w.get("project_id") or 0))
        return len(stare)

    def force_delete_lock(self, project_id: int) -> bool:
        project_id = int(project_id)
        ok = self._pisz("rmm-lock-zwolnij", {"project_id": project_id})
        self._my_locks.discard(project_id)
        if ok:
            print("⚡ Blokada projektu %s usunięta siłowo" % project_id)
        return ok

    # ── bicie serca ──────────────────────────────────────────────────────
    def refresh_heartbeat(self, project_id: int) -> bool:
        project_id = int(project_id)
        if project_id not in self._my_locks:
            return False
        owner = self.get_project_lock_owner(project_id)
        if owner is None:
            print("⚠️  Bicie serca: projekt %s nie ma już blokady" % project_id)
            self._my_locks.discard(project_id)
            return False
        if not self._moj(owner):
            print("⚠️  Bicie serca: projekt %s przejął %s@%s"
                  % (project_id, owner.get("user"), owner.get("computer")))
            self._my_locks.discard(project_id)
            return False
        return self._pisz("rmm-lock-bicie-serca", {
            "last_heartbeat": _teraz(), "project_id": project_id,
            "uzytkownik": self.my_name, "komputer": self.my_computer})

    def refresh_all_my_locks(self):
        for pid in list(self._my_locks):
            self.refresh_heartbeat(pid)

    # ── zmiana użytkownika po zalogowaniu ────────────────────────────────
    def update_user_name(self, new_name: str):
        """Po zalogowaniu: przepisz na nową nazwę blokady tego komputera
        należące do starej. Przeterminowane po prostu znikają."""
        stary, self.my_name = self.my_name, new_name
        print("🔄 Blokady: %s -> %s" % (stary, new_name))
        self.cleanup_stale_locks()
        self._pisz("rmm-lock-przepisz-uzytkownika", {
            "nowy": new_name, "last_heartbeat": _teraz(),
            "komputer": self.my_computer, "stary": stary})
        self._my_locks = {int(w["project_id"]) for w in self._czytaj("rmm-locki-wszystkie")
                          if w.get("komputer") == self.my_computer
                          and w.get("uzytkownik") == new_name}
