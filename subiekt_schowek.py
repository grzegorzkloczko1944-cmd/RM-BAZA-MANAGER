# -*- coding: utf-8 -*-
"""Schowek montażowy — bufor między monterem a dokumentem RW.

PO CO TO JEST
─────────────
Zgłoszenie magazyniera: monterzy biorą element, zaraz oddają bo nie pasuje,
biorą inny, dobierają, zwracają. Robienie RW na każdy taki ruch jest bez
sensu księgowo (element wraca tego samego dnia), zniechęca do jakiejkolwiek
ewidencji i tak nie odda prawdy — nikt nie zdąży klikać między próbami.

Schowek zbiera w ciągu dnia same ZDARZENIA (pobrano / oddano), a Subiekt
widzi jeden dokument dopiero przy rozliczeniu — i to NETTO, nie sumę prób:

    bierze:  A×1, B×2, C×1        →   RW: A×1, B×1, D×3
    oddaje:  B×1, C×1                 (zamiany znikają z papierologii)
    dobiera: D×3

⚠️ KLUCZOWA WŁASNOŚĆ: zwrot tego samego dnia = ZERO ŚLADU na dokumencie.
`+1 pobrano, −1 oddano → 0 → nie trafia na RW`. To jedyny powód, dla którego
to w ogóle rozwiązuje problem magazyniera — nie wolno tego „uprościć" do
zwykłego koszyka pozycji.

GDZIE TO ŻYJE — PLIK ROBOCZY, NIE BAZA
──────────────────────────────────────
Schowek NIE trafia do bazy projektu ani na serwer. Leży w zwykłym pliku JSON
na stanowisku magazyniera. Decyzja użytkownika (13.09.2026): „dlaczego to
idzie do bazy? to ma iść tylko do Subiekta".

* **Bufor to stan przejściowy.** Do Subiekta idzie WYNIK (jedno RW), a nie
  droga, którą do niego doszliśmy.
* **Zero locka.** Zapis do bazy projektu wymagałby locka, czyli skanowanie
  blokowałoby projekt wszystkim innym.
* **Przeżywa zamknięcie okna.** Monter wziął rano, oddaje po południu.
* **Schowek ogólny** (serwis, eksploatacja) nie ma projektu, więc nie miałby
  gdzie zamieszkać w bazie projektowej.

Konsekwencja: schowek jest LOKALNY dla stanowiska. Drugi magazynier na innym
komputerze go nie zobaczy. Przy jednym stanowisku wydawania to bez znaczenia;
gdyby kiedyś było ich kilka, plik przenosi się na udział sieciowy albo do
RM_SERWER — reszta modułu zostaje bez zmian.

Rozliczenie do RW opisuje SCHOWEK_RW_ALGORYTM.md. Ten moduł kończy się na
`do_rozliczenia()` — dalej jest już sprawa okna i mostu.
"""

import json
import os
import tempfile
from datetime import datetime


#: Plik roboczy stanowiska. Obok innych plików RM_BAZA (sync_config.json,
#: subiekt_kolumny.json), bo to ta sama kategoria: stan tego komputera.
SCIEZKA = r"C:\RMPAK_CLIENT\schowki_montazowe.json"

#: Statusy. ROZLICZONY jest końcowy — po nim ruchy są zamrożone, bo RW
#: istnieje już w Subiekcie i cofnięcie rozjechałoby stan magazynu.
OTWARTY = "OTWARTY"
ROZLICZONY = "ROZLICZONY"

#: Etykieta schowka bez projektu.
OGOLNY = "OGÓLNY"


class BladSchowka(Exception):
    """Operacja niemożliwa — z powodem czytelnym dla magazyniera."""


# ── plik ────────────────────────────────────────────────────────────────────
def _pusty():
    return {"wersja": 1, "nastepny_id": 1, "schowki": []}


def wczytaj(sciezka=None):
    """Zawartość pliku roboczego. Brak pliku = pusty schowek, nie błąd."""
    p = sciezka or SCIEZKA
    if not os.path.isfile(p):
        return _pusty()
    try:
        with open(p, encoding="utf-8") as f:
            dane = json.load(f) or {}
    except (OSError, ValueError):
        # Uszkodzony plik nie może zablokować wydawania — magazynier ma
        # pracować dalej, a stary plik zostaje obok do obejrzenia.
        _odloz_uszkodzony(p)
        return _pusty()
    dane.setdefault("schowki", [])
    dane.setdefault("nastepny_id",
                    max([s.get("id", 0) for s in dane["schowki"]] or [0]) + 1)
    return dane


def _odloz_uszkodzony(p):
    try:
        os.replace(p, p + ".uszkodzony-%s"
                   % datetime.now().strftime("%Y%m%d-%H%M%S"))
    except OSError:
        pass


def zapisz(dane, sciezka=None):
    """Zapis ATOMOWY — przez plik tymczasowy i podmianę.

    Magazynier skanuje seriami; zapis „w miejscu" przerwany zamknięciem
    programu zostawiłby obcięty JSON i cała dzisiejsza praca byłaby nie do
    odczytania.
    """
    p = sciezka or SCIEZKA
    katalog = os.path.dirname(p) or "."
    try:
        os.makedirs(katalog, exist_ok=True)
        uchwyt, tmp = tempfile.mkstemp(dir=katalog, suffix=".tmp")
        with os.fdopen(uchwyt, "w", encoding="utf-8") as f:
            json.dump(dane, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    except OSError as e:
        raise BladSchowka("Nie udało się zapisać schowka:\n%s" % e)


# ── schowki ─────────────────────────────────────────────────────────────────
def utworz(monter, projekt=None, nazwa=None, sciezka=None):
    """Nowy otwarty schowek. `projekt=None` → schowek ogólny."""
    monter = (monter or "").strip()
    if not monter:
        raise BladSchowka("Podaj montera, dla którego zakładasz schowek.")
    dane = wczytaj(sciezka)
    nowy = {
        "id": dane["nastepny_id"],
        "projekt": (projekt or "").strip() or None,
        "monter": monter,
        "nazwa": (nazwa or "").strip() or None,
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": OTWARTY,
        "rw_numer": None,
        "rozliczony": None,
        "ruchy": [],
    }
    dane["schowki"].append(nowy)
    dane["nastepny_id"] += 1
    zapisz(dane, sciezka)
    return nowy["id"]


def lista(tylko_otwarte=False, projekt=None, sciezka=None):
    """Schowki od najnowszego, z licznikiem pozycji i sztuk.

    `projekt` zawęża do schowków tego projektu ORAZ ogólnych — magazynier
    pracujący na projekcie ma widzieć swoje schowki i te bez przypisania,
    ale nie cudze projekty.

    Liczniki obejmują TYLKO pozycje o dodatnim bilansie — pozycja wzięta
    i oddana nie ma czego pokazywać, a „0 szt." sugerowałoby, że coś jest
    do zrobienia.
    """
    dane = wczytaj(sciezka)
    cel = (projekt or "").strip() or None
    wynik = []
    for s in sorted(dane["schowki"], key=lambda x: x["id"], reverse=True):
        if tylko_otwarte and s.get("status") != OTWARTY:
            continue
        if cel and s.get("projekt") and s["projekt"] != cel:
            continue
        stan = _bilans(s)
        w = {k: v for k, v in s.items() if k != "ruchy"}
        w["pozycji"] = len(stan)
        w["sztuk"] = sum(p["ilosc"] for p in stan)
        wynik.append(w)
    return wynik


def _znajdz(dane, schowek_id):
    for s in dane["schowki"]:
        if s["id"] == schowek_id:
            return s
    raise BladSchowka("Nie ma schowka o numerze %s." % schowek_id)


def pobierz(schowek_id, sciezka=None):
    s = _znajdz(wczytaj(sciezka), schowek_id)
    return {k: v for k, v in s.items() if k != "ruchy"}


def usun(schowek_id, sciezka=None):
    """Kasuje schowek z pliku — sprzątanie po rozliczonych albo pomyłkach."""
    dane = wczytaj(sciezka)
    dane["schowki"].remove(_znajdz(dane, schowek_id))
    zapisz(dane, sciezka)


def opis(s):
    """Etykieta na listę: „2627 — Kowalski" albo „OGÓLNY — Nowak"."""
    czolo = s.get("projekt") or s.get("nazwa") or OGOLNY
    return "%s — %s" % (czolo, s.get("monter") or "?")


# ── ruchy ───────────────────────────────────────────────────────────────────
def _klucz(symbol):
    """Symbol do porównań: TRIM + wielkie litery.

    ⚠️ NIE tniemy na spacji — symbole w Subiekcie ją zawierają („6212 2RS",
    „DIN 933 M8x30"). Ta sama zasada co w skanerze okna wydania.
    """
    return (symbol or "").strip().upper()


def _bilans(s):
    """Bilans NETTO po symbolach — tylko pozycje z dodatnią ilością.

    Jedyne miejsce, w którym powstaje „co jest w schowku". Liczymy z ruchów
    zamiast trzymać osobne pole, żeby historia i stan nie mogły się rozjechać.
    """
    razem, nazwy, oryginal = {}, {}, {}
    for r in s.get("ruchy", []):
        k = _klucz(r["symbol"])
        razem[k] = razem.get(k, 0.0) + float(r["ilosc"])
        oryginal.setdefault(k, r["symbol"])
        if r.get("nazwa"):
            nazwy[k] = r["nazwa"]
    return [{"symbol": oryginal[k], "nazwa": nazwy.get(k, ""), "ilosc": v}
            for k, v in sorted(razem.items()) if v > 0]


def stan_schowka(schowek_id, sciezka=None):
    return _bilans(_znajdz(wczytaj(sciezka), schowek_id))


def ile_w_schowku(schowek_id, symbol, sciezka=None):
    """Bilans jednego symbolu (może być 0)."""
    s = _znajdz(wczytaj(sciezka), schowek_id)
    k = _klucz(symbol)
    return sum(float(r["ilosc"]) for r in s.get("ruchy", [])
               if _klucz(r["symbol"]) == k)


def historia(schowek_id, sciezka=None):
    """Wszystkie ruchy od najnowszego — do okna „Historia"."""
    return list(reversed(_znajdz(wczytaj(sciezka), schowek_id).get("ruchy", [])))


def _wymagaj_otwartego(s):
    if s.get("status") != OTWARTY:
        raise BladSchowka(
            "Schowek jest już rozliczony (RW %s).\n\n"
            "Zwrot wymaga ponownego przyjęcia na magazyn — otwórz PW zwrotu."
            % (s.get("rw_numer") or "?"))


def _ruch(schowek_id, symbol, ilosc, nazwa, operator, monter, sciezka):
    dane = wczytaj(sciezka)
    s = _znajdz(dane, schowek_id)
    _wymagaj_otwartego(s)
    s.setdefault("ruchy", []).append({
        "symbol": (symbol or "").strip(), "nazwa": nazwa or "",
        "ilosc": float(ilosc),
        "czas": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "operator": (operator or "").strip(),
        "monter": (monter or s.get("monter") or "").strip(),
    })
    zapisz(dane, sciezka)
    k = _klucz(symbol)
    return sum(float(r["ilosc"]) for r in s["ruchy"] if _klucz(r["symbol"]) == k)


def pobrano(schowek_id, symbol, ilosc, nazwa=None, operator=None,
            monter=None, sciezka=None):
    """Monter WZIĄŁ element — ruch dodatni."""
    if not (symbol or "").strip():
        raise BladSchowka("Brak symbolu.")
    if ilosc <= 0:
        raise BladSchowka("Ilość musi być większa od zera.")
    return _ruch(schowek_id, symbol, ilosc, nazwa, operator, monter, sciezka)


def oddano(schowek_id, symbol, ilosc, nazwa=None, operator=None,
           monter=None, sciezka=None):
    """Monter ODDAŁ element — ruch ujemny.

    ⛔ Nie wolno oddać więcej, niż monter faktycznie ma w schowku: ujemny
    bilans zaniżyłby RW przy rozliczeniu i rozjechał stan magazynu. Twardy
    błąd, zero zapisu („nic po cichu").
    """
    if not (symbol or "").strip():
        raise BladSchowka("Brak symbolu.")
    if ilosc <= 0:
        raise BladSchowka("Ilość musi być większa od zera.")
    ma = ile_w_schowku(schowek_id, symbol, sciezka)
    if ilosc > ma:
        raise BladSchowka(
            "W schowku jest %s szt. „%s” — nie można oddać %s.\n"
            "Żaden ruch nie został zapisany."
            % (_ilo(ma), (symbol or "").strip(), _ilo(ilosc)))
    return _ruch(schowek_id, symbol, -ilosc, nazwa, operator, monter, sciezka)


def usun_pozycje(schowek_id, symbol, sciezka=None):
    """Kasuje CAŁĄ historię jednego symbolu — cofnięcie pomyłki skanowania.

    To NIE jest zwrot od montera: zwrot zostawia ślad (`oddano`), a to
    czyści tak, jakby skanu nigdy nie było. Do użycia, gdy magazynier
    dopisał pozycję do złego schowka.
    """
    dane = wczytaj(sciezka)
    s = _znajdz(dane, schowek_id)
    _wymagaj_otwartego(s)
    k = _klucz(symbol)
    s["ruchy"] = [r for r in s.get("ruchy", []) if _klucz(r["symbol"]) != k]
    zapisz(dane, sciezka)


def wyczysc(schowek_id, sciezka=None):
    """Kasuje wszystkie ruchy schowka. Schowek zostaje, pusty."""
    dane = wczytaj(sciezka)
    s = _znajdz(dane, schowek_id)
    _wymagaj_otwartego(s)
    s["ruchy"] = []
    zapisz(dane, sciezka)


# ── rozliczenie ─────────────────────────────────────────────────────────────
def do_rozliczenia(schowek_id, sciezka=None):
    """Pozycje, które pójdą na RW — bilans netto. Pusty = nie ma czego wydawać."""
    return stan_schowka(schowek_id, sciezka)


def oznacz_rozliczony(schowek_id, rw_numer, sciezka=None):
    """Zamyka schowek po UDANYM zapisie RW (dopiero po read-backie).

    Wołać wyłącznie wtedy, gdy dokument faktycznie stoi w Subiekcie —
    inaczej ruchy zostaną zamrożone bez pokrycia w dokumencie.
    """
    dane = wczytaj(sciezka)
    s = _znajdz(dane, schowek_id)
    s["status"] = ROZLICZONY
    s["rw_numer"] = (rw_numer or "").strip() or None
    s["rozliczony"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    zapisz(dane, sciezka)


def zajete_w_schowkach(tylko_otwarte=True, sciezka=None):
    """{SYMBOL: ilość} — co fizycznie chodzi po hali w rękach monterów.

    Subiekt o schowkach nie wie, więc jego stan jest ZAWYŻONY o te sztuki.
    Dostępność fizyczna = stan z Subiekta − to. Bez tego magazynier wyda
    drugi raz coś, co już ktoś trzyma (§4 BUFOR_SCHOWEK_MONTAZOWY.md).
    """
    razem = {}
    for s in wczytaj(sciezka)["schowki"]:
        if tylko_otwarte and s.get("status") != OTWARTY:
            continue
        for p in _bilans(s):
            razem[p["symbol"]] = razem.get(p["symbol"], 0.0) + p["ilosc"]
    return {k: v for k, v in razem.items() if v > 0}


def _ilo(x):
    """Liczba bez zbędnego ogona: 3 zamiast 3.0, ale 2.5 zostaje."""
    x = float(x)
    return str(int(x)) if abs(x - int(x)) < 1e-9 else ("%.3f" % x).rstrip("0")
