# -*- coding: utf-8 -*-
"""Blokady projektów RM_BAZA pilnowane przez RM_SERWER.

Zastępuje `lock_manager_v2` (plik `project_<id>.lock` w katalogu LOCKS na
dysku sieciowym) — tak samo jak `lock_manager_serwer` zrobił to dla
RM_MANAGER. Interfejs jest ten sam, więc RM_BAZA używa obu tak samo; różni
się tylko to, gdzie leży prawda o zajętości:

    dawniej   project_<id>.lock na Y:  — kto pierwszy utworzył plik
    teraz     tabela project_locks     — kto pierwszy zapisał wiersz

Czemu to lepsze: katalog na dysku sieciowym nie potrafi powiedzieć „ten wpis
już istnieje". Dwa komputery mogły utworzyć plik niemal równocześnie i oba
uznać, że mają blokadę. Tutaj pilnuje tego klucz główny tabeli, a serwer
wykonuje polecenia pojedynczo, więc dwóch zwycięzców być nie może.

═══════════════════════════════════════════════════════════════════════════
⚠️ DWA OSOBNE SYSTEMY BLOKAD — to jest cały sens tego pliku
═══════════════════════════════════════════════════════════════════════════

RM_BAZA i RM_MANAGER mają blokady w DWÓCH RÓŻNYCH BAZACH i nic ich nie łączy:

    RM_BAZA     operacje `lock-*`      -> master RM_BAZA
    RM_MANAGER  operacje `rmm-lock-*`  -> rm_manager.sqlite

Rozdziela je routing serwera (`rm_serwer._polaczenie`) po prefiksie nazwy
operacji. Tabela nazywa się w obu bazach tak samo, ale to inne pliki.

Tak MUSI być, bo numery projektów obu programów pokrywają się w 81 na 85
przypadków (RM_BAZA 1..2611, RM_MANAGER 1..90). Jedna wspólna tabela
kazałaby userowi RM_BAZA czekać na „zajęty" projekt 22 dlatego, że ktoś
zupełnie gdzie indziej otworzył projekt 22 w RM_MANAGER.

Cała logika (wyścig, przejmowanie, bicie serca, przeterminowanie) jest
wspólna i mieszka w `lock_manager_serwer` — tutaj podmieniamy WYŁĄCZNIE
transport i prefiks nazw. Dzięki temu poprawka reguł w jednym miejscu
działa dla obu programów, zamiast rozjeżdżać się po dwóch kopiach.
"""
from __future__ import annotations

from typing import Optional

from lock_manager_serwer import ProjectLockManager as _ProjectLockManagerRMM


class ProjectLockManager(_ProjectLockManagerRMM):
    """Blokady projektów RM_BAZA w masterze na serwerze.

    Konstruktor bierze ten sam `config` co wersja plikowa. `locks.folder`
    jest przyjmowany i ignorowany: katalog LOCKS przestał mieć znaczenie,
    ale konfiguracje na stanowiskach wciąż go zawierają i nie ma powodu
    wywracać się na jego obecność.
    """

    #: Prefiks nazw operacji. Pusty = master RM_BAZA (patrz nagłówek).
    PREFIKS = ""

    def __init__(self, config: dict):
        super().__init__(config)
        print("🔧 LockManager: blokady RM_BAZA na RM_SERWER (master, tabela project_locks)")

    # ── transport: master RM_BAZA zamiast bazy RM_MANAGER ────────────────
    #
    # `lock_manager_serwer` woła `rm_manager.rmm_read/rmm_exec`, co trafia do
    # rm_manager.sqlite. RM_BAZA rozmawia z masterem przez `rm_klient`.
    def _czytaj(self, operacja: str, params: dict = None) -> list:
        import rm_klient
        try:
            return rm_klient.master_read(self._nazwa(operacja), params or {})
        except Exception as e:
            print("⚠️  Blokady — odczyt %s: %s" % (operacja, e))
            return []

    def _pisz(self, operacja: str, params: dict) -> Optional[dict]:
        """Zwraca odpowiedź serwera (z `rowcount`) albo None przy błędzie.
        Liczba zmienionych wierszy rozstrzyga, czy przejęcie się udało."""
        import rm_klient
        try:
            return rm_klient.master_exec(self._nazwa(operacja), params) or {}
        except Exception as e:
            print("⚠️  Blokady — zapis %s: %s" % (operacja, e))
            return None

    # ── nazwy operacji ───────────────────────────────────────────────────
    def _nazwa(self, operacja: str) -> str:
        """`rmm-lock-przejmij` -> `lock-przejmij`.

        Klasa bazowa ma nazwy zaszyte w kodzie metod; zdejmujemy prefiks
        tutaj, zamiast przepisywać wszystkie jej metody tylko po to, żeby
        zmienić jeden człon napisu.
        """
        return operacja[4:] if operacja.startswith("rmm-") else operacja
