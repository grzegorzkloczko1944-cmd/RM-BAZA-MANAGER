# -*- coding: utf-8 -*-
"""Dostęp do udziału z bazami projektów — logowanie kontem technicznym.

PROBLEM
-------
Bazy projektów (`project_N.sqlite`, `rm_manager_project_N.sqlite`) są
OTWIERANE JAKO PLIKI z `\\\\W2019S\\RM_SERWER$`. Przez protokół idzie tylko
master, blokady i sesje — projekty zostały plikami świadomie, bo przepisanie
302 zapytań na protokół dawało 20× wolniejszą pracę (decyzja 12.09.2026).

Część pracowników ma konta bez prawa do zasobów sieciowych: Windows pokazuje
im wtedy okno „Wprowadzanie poświadczeń sieciowych", a program nie ma jak
otworzyć żadnego projektu.

ROZWIĄZANIE
-----------
Program loguje się do udziału SAM, kontem technicznym, przy starcie. Użytkownik
niczego nie wpisuje i nadal nie widzi otoczenia sieciowego — uprawnienia jego
konta się nie zmieniają. Połączenie jest nietrwałe (`/persistent:no`): żyje do
wylogowania i nie zostawia śladu w profilu.

⚠️ To zabezpieczenie PRZED PRZYPADKIEM, nie przed upartym: hasło jest w pliku
`.exe`, który leży na udziale. Realną granicę dostępu wyznaczają uprawnienia
NTFS na katalogu, nie ten mechanizm.
"""
from __future__ import annotations

import os
import subprocess

#: Udział z bazami projektów, backupami, chatem i historią Subiekta.
UDZIAL = r"\\W2019S\RM_SERWER$"

#: Konto techniczne na serwerze — lokalne konto W2019S (firma jest
#: w WORKGROUP, nie w domenie, więc konto żyje tylko na serwerze i nie ma
#: go na stacjach).
#:
#: ⚠️ Serwer pozwala na udział `Everyone: Full`, ale „Everyone" w Windows NIE
#: obejmuje niezalogowanych: każdy klient musi przedstawić się kontem
#: istniejącym NA SERWERZE. Userzy takiego nie mają — stąd okno
#: „Wprowadzanie poświadczeń sieciowych". Tym kontem przedstawia się program.
#: ⚠️ Hasło NIE MOŻE zawierać fragmentu nazwy konta (Windows odrzuca takie
#: przy zakładaniu, myląco raportując „nie spełnia wymagań złożoności").
KONTO = r"W2019S\RM_KLIENT"
HASLO = "Zx7#mVq2$Torpeda94"

_zalogowano = False


def dostepny() -> bool:
    """Czy widzimy zawartość udziału (bez próby logowania)."""
    try:
        return os.path.isdir(UDZIAL)
    except OSError:
        return False


def zaloguj(cichy: bool = True) -> bool:
    """Nawiąż sesję SMB do udziału. True, gdy udział jest osiągalny.

    Bezpieczne do wielokrotnego wywołania — przy istniejącej sesji `net use`
    zwraca błąd 1219 („konflikt poświadczeń"), co dla nas znaczy „już jest".
    """
    global _zalogowano
    if _zalogowano or dostepny():
        _zalogowano = True
        return True
    try:
        # CREATE_NO_WINDOW — inaczej przy starcie .exe mignęłoby czarne okno.
        wynik = subprocess.run(
            ["net", "use", UDZIAL, HASLO, "/user:" + KONTO, "/persistent:no"],
            capture_output=True, text=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if wynik.returncode == 0:
            _zalogowano = True
            if not cichy:
                print("  ✅ Udział serwera: zalogowano jako %s" % KONTO)
            return True
        # 1219: sesja do tego serwera już istnieje na innym koncie — sprawdzamy,
        # czy mimo to widzimy dane (zwykle tak: liczy się istniejąca sesja).
        if dostepny():
            _zalogowano = True
            return True
        if not cichy:
            print("  ⚠️  Udział serwera niedostępny: %s"
                  % (wynik.stderr or wynik.stdout or "").strip()[:120])
        return False
    except Exception as e:
        if not cichy:
            print("  ⚠️  Udział serwera — błąd logowania: %s" % e)
        return False
