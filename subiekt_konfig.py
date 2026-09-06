# -*- coding: utf-8 -*-
"""Konfiguracja połączenia z Subiektem — jedno miejsce na odczyt i zapis.

Plik `C:\\RMPAK_CLIENT\\.nexo_sfera.json` trzyma dane logowania do dwóch
NIEZALEŻNYCH systemów (patrz `NexoSession.Connect`):

  1. SQL Server         — `sqlUser` / `sqlHaslo` albo autoryzacja Windows
  2. operator nexo      — `nexoLogin` / `nexoHaslo`, to samo, czym człowiek
                          loguje się do Subiekta

Oba muszą przejść, żeby most wstał.

⚠️ MOST CZYTA TEN PLIK RAZ, PRZY STARCIE PROCESU (`NexoSession` dostaje
`Konfig` w konstruktorze). Samo nadpisanie pliku nic nie zmienia w działającym
moście — trzeba go zatrzymać i podnieść. Robi to `zapisz_i_zaloguj()`.

Ścieżka była wcześniej powtórzona jako stała w `subiekt_stany.py`,
`subiekt_podobne.py` i w kodzie C#. Przy dokładaniu ZAPISU (okno logowania,
06.09.2026) trzy kopie zaczęły grozić rozjazdem, stąd ten moduł.
"""

import json
import os
import subprocess
import tempfile

#: Poza repo — plik zawiera hasła i NIGDY nie może trafić do gita.
CONFIG_PATH = r"C:\RMPAK_CLIENT\.nexo_sfera.json"

#: Pola, które są hasłami. Wydzielone, bo traktujemy je inaczej w kilku
#: miejscach: czyści je „Wyloguj", nie pokazujemy ich w logach ani w opisie
#: połączenia, a okno wyświetla je gwiazdkami.
POLA_HASEL = ("sqlHaslo", "nexoHaslo")

#: Domyślne wartości dla nowego stanowiska. Bez adresu serwera i nazwy bazy —
#: te wpisuje administrator, a wpisanie ich tutaj rozsiewałoby dane firmowego
#: serwera po repozytorium.
DOMYSLNE = {
    "serwer": "",
    "baza": "",
    "sqlWindowsAuth": False,
    "sqlUser": "sa",
    "sqlHaslo": "",
    "nexoLogin": "",
    "nexoHaslo": "",
    "sdkBin": r"C:\iLogic\Subiekt\Bin\ ".strip(),
}


def istnieje():
    """Czy stanowisko ma w ogóle skonfigurowane połączenie."""
    return os.path.isfile(CONFIG_PATH)


def wczytaj():
    """Zwraca konfigurację jako słownik. Braki uzupełnia domyślnymi.

    Nie rzuca, gdy pliku nie ma — okno logowania musi się otworzyć na
    świeżym stanowisku, żeby dało się cokolwiek wpisać.
    """
    dane = dict(DOMYSLNE)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            wczytane = json.load(f)
        if isinstance(wczytane, dict):
            for k, v in wczytane.items():
                if not k.startswith("_"):       # _komentarz z wzorca
                    dane[k] = v
    except (OSError, ValueError):
        pass                                    # brak pliku albo uszkodzony
    return dane


def zapisz(dane, sciezka=None, zawez=True):
    """Zapisuje konfigurację; opcjonalnie zawęża uprawnienia do właściciela.

    `sciezka` — do testu przed zapisem (plik tymczasowy). Bez niej pisze
    do konfiguracji stanowiska.

    `zawez=False` dla plików tymczasowych. ⚠️ Zawężenie zdejmuje prawa
    dziedziczone, a most to OSOBNY PROCES — przy pliku testowym kończyło
    się to `UnauthorizedAccessException` w `NexoSession.Wczytaj` i „Testuj
    połączenie" nie działało w ogóle (06.09.2026). Trwała konfiguracja leży
    w profilu maszyny i tam zawężenie ma sens; kopia w %TEMP% żyje kilka
    sekund i musi być czytelna dla mostu.
    """
    sciezka = sciezka or CONFIG_PATH
    czyste = {k: v for k, v in dane.items() if not k.startswith("_")}
    katalog = os.path.dirname(sciezka)
    if katalog:
        os.makedirs(katalog, exist_ok=True)
    with open(sciezka, "w", encoding="utf-8") as f:
        json.dump(czyste, f, indent=2, ensure_ascii=False)
        f.write("\n")
    if zawez:
        _zawez_uprawnienia(sciezka)
    return sciezka


def _zawez_uprawnienia(sciezka):
    """Dostęp tylko dla właściciela pliku. Cichy no-op, gdy cokolwiek nie gra.

    ŚWIADOMIE BEZ SZYFROWANIA haseł: klucz i tak musiałby leżeć obok, więc
    dawałoby to złudzenie bezpieczeństwa kosztem diagnostyki. Realna ochrona
    to uprawnienia systemu plików — plik siedzi w profilu maszyny, poza repo.

    ⚠️ TA FUNKCJA POTRAFI ZAMKNĄĆ PLIK PRZED WŁASNYM WŁAŚCICIELEM. Pierwsza
    wersja budowała regułę z `os.environ['USERNAME']`, a ta zmienna bywa
    pusta — powstawało `MONGO\\:(F)`, czyli nadanie praw NIKOMU, przy
    jednocześnie zdjętym dziedziczeniu. Efekt: `PermissionError` przy
    odczycie i most nie wstawał (06.09.2026). Stąd trzy zabezpieczenia:
    nazwa konta z API systemu zamiast zmiennej, sprawdzenie że nie jest
    pusta, i WERYFIKACJA ODCZYTU po zmianie — gdy plik przestał być
    czytelny, uprawnienia wracają do dziedziczonych.
    """
    if os.name != "nt":
        try:
            os.chmod(sciezka, 0o600)
        except OSError:
            pass
        return

    konto = _konto_windows()
    if not konto:
        return              # bez pewnej nazwy konta NIE RUSZAMY uprawnień

    try:
        # /inheritance:r zdejmuje dziedziczone prawa (np. Users z korzenia
        # dysku), inaczej zawężenie nic nie daje.
        subprocess.run(
            ["icacls", sciezka, "/inheritance:r",
             "/grant:r", konto + ":F",
             "/grant:r", "*S-1-5-18:F"],       # SYSTEM po SID — niezależne od języka Windows
            capture_output=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return              # brak uprawnień nie może zablokować zapisu

    # Sprawdzian: czy plik nadal daje się odczytać. Zawężenie, które odcina
    # własny proces, jest gorsze niż jego brak — cofamy je.
    try:
        with open(sciezka, "r", encoding="utf-8") as f:
            f.read(1)
    except OSError:
        try:
            subprocess.run(["icacls", sciezka, "/reset"],
                           capture_output=True, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        except (OSError, subprocess.SubprocessError):
            pass


def _konto_windows():
    """Pełna nazwa konta (DOMENA\\user) albo None, gdy nie da się ustalić.

    `os.environ['USERNAME']` bywa pusta (usługi, procesy potomne bez pełnego
    środowiska), a pusta nazwa w `icacls` tworzy regułę dla nikogo.
    """
    try:
        import getpass
        nazwa = (getpass.getuser() or "").strip()
    except Exception:
        nazwa = ""
    if not nazwa:
        nazwa = (os.environ.get("USERNAME") or "").strip()
    if not nazwa:
        return None
    domena = (os.environ.get("USERDOMAIN") or "").strip()
    return domena + chr(92) + nazwa if domena else nazwa


def zapisz_tymczasowo(dane):
    """Konfiguracja w pliku tymczasowym — do testu PRZED nadpisaniem.

    Test musi iść na kopii, bo inaczej literówka w haśle nadpisuje działające
    połączenie i stanowisko zostaje bez niczego.
    """
    katalog = tempfile.mkdtemp(prefix="subiekt_cfg_")
    return zapisz(dane, os.path.join(katalog, "test.nexo_sfera.json"),
                  zawez=False)


def wyczysc_hasla():
    """Kasuje SAME hasła, zostawiając serwer, bazę i loginy.

    To jest „wyloguj": przy powrocie administrator dopisuje tylko hasło,
    zamiast konfigurować stanowisko od zera. Samo skasowanie pliku byłoby
    wygodniejsze w kodzie i gorsze w użyciu.
    """
    if not istnieje():
        return False
    dane = wczytaj()
    for pole in POLA_HASEL:
        dane[pole] = ""
    zapisz(dane)
    return True


def braki(dane):
    """Lista pól wymaganych, których brakuje. Pusta = można próbować logować."""
    brak = []
    if not (dane.get("serwer") or "").strip():
        brak.append("Serwer SQL")
    if not (dane.get("baza") or "").strip():
        brak.append("Baza")
    if not dane.get("sqlWindowsAuth"):
        if not (dane.get("sqlUser") or "").strip():
            brak.append("Użytkownik SQL")
        if not (dane.get("sqlHaslo") or "").strip():
            brak.append("Hasło SQL")
    if not (dane.get("nexoLogin") or "").strip():
        brak.append("Login operatora nexo")
    if not (dane.get("nexoHaslo") or "").strip():
        brak.append("Hasło operatora nexo")
    return brak


def opis_bez_hasel(dane):
    """Jednolinijkowy opis połączenia do paska stanu i logów — BEZ haseł."""
    auth = "Windows" if dane.get("sqlWindowsAuth") else f"SQL:{dane.get('sqlUser') or '?'}"
    return (f"serwer={dane.get('serwer') or '?'}  baza={dane.get('baza') or '?'}  "
            f"auth={auth}  operator={dane.get('nexoLogin') or '?'}")
