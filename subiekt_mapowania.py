# -*- coding: utf-8 -*-
"""
Globalna tabela mapowań numer rysunku → kartoteka Subiekta.

Warstwa pośrednicząca między RM_BAZA a Subiektem (SUBIEKT_INTEGRACJA_PLAN.md,
sekcja „Zapamiętanie skojarzenia"). Trzy rzeczy, dla których istnieje:

1. **Globalna, nie per projekt.** Jeśli `013-100.22X` raz został skojarzony
   z kartoteką Subiekta, każdy następny projekt zna to skojarzenie od razu.
   Dlatego mieszka obok master.sqlite, a nie w bazie projektu.

2. **Warstwa filtrująca przed siecią.** Krok „sprawdź w Subiekcie" pyta
   najpierw tutaj (jedno żądanie do RM_SERWER, ~20 ms) i dopiero przy braku
   trafienia leci przez Sferę (15–30 s dla 300 pozycji). To nie zamiennik
   zapytania do Subiekta, tylko filtr przed nim.

3. **Ślad, skąd wzięło się dopasowanie.** `sposob` rozróżnia trafienie
   automatyczne po symbolu od ręcznego wyboru użytkownika (fuzzy) — plan
   wymaga, żeby dało się to pokazać w arkuszu jako różne stany, bo ręczne
   dopasowanie mogło być pomyłką.

Nazwy/opisów detali NIE zapisujemy z Subiekta — źródłem prawdy dla danych
konstrukcyjnych zostaje RM_BAZA (plan, sekcja 1/12.1).

GDZIE LEŻĄ DANE (od 14.09.2026)

    RM_BAZA ──TCP──► RM_SERWER ──► C:\\Apps\\RM_SERWER\\dane\\subiekt_mapowania.sqlite

Ten moduł NIE otwiera żadnego pliku. Wszystko idzie przez `rm_klient`
operacjami `map-*` (routing po prefiksie robi serwer — `rm_serwer._polaczenie`),
a schemat pilnują migracje serwera (`rm_serwer_operacje.MIGRACJE_MAPOWANIA`).

⚠️ Dlaczego nie plik. Do 12.09.2026 moduł otwierał `subiekt_mapowania.sqlite`
obok `master.sqlite`, po ścieżce z `sync_config.json` stacji. Po przenosinach
mastera na serwer ta ścieżka wskazywała katalog na `Y:`, którego już nie było:
odczyty zwracały `{}` („brak pliku = brak mapowań"), a pierwszy zapis
założyłby świeży, pusty plik na udziale — cichy rozjazd między stacjami
a serwerem, bez jednego komunikatu. Sprawdzone na produkcji 14.09.2026.

BŁĘDY. Funkcje rzucają `rm_klient.BladSerwera` jak każdy inny odczyt i zapis
mastera — bez cichego `{}` przy awarii. To właśnie cisza ukryła martwe
mapowania na dwa dni.

Parametr `path=` w sygnaturach został dla zgodności z wołającymi
(`subiekt_dopasowanie.zapisz_decyzje` go przekazuje) — jest IGNOROWANY.
"""

import json
import os
from datetime import datetime

import rm_klient

SPOSOB_AUTO = "auto"        # trafienie 1:1 po symbolu = numer rysunku
SPOSOB_LUZNY = "luzny"      # TRIM + wielkość liter (spacje/a-A w bazie Subiekta)
SPOSOB_RECZNY = "reczny"    # użytkownik wskazał kartotekę (fuzzy match)
SPOSOB_ZALOZONA = "zalozona"  # kartoteka założona przez RM_BAZA
SPOSOB_SCALONA = "scalona"    # stary symbol → kartoteka docelowa po scaleniu (alias)

#: Ile wpisów w jednym `master-batch`. Batch to jedna transakcja i jeden wpis
#: w dzienniku idempotencji serwera; 354 pozycje projektu to ~70 KB ramki,
#: daleko od limitu (8 MB) — paczkujemy z zapasu, nie z konieczności.
_PACZKA = 500


def _key(numer):
    return (numer or "").strip().upper()


def _kto():
    return os.environ.get("USERNAME") or "?"


def _teraz():
    return datetime.now().isoformat(timespec="seconds")


def _zapisano(wynik):
    """Czy pojedynczy zapis coś zmienił (0 = odrzucony regułą w SQL)."""
    return bool((wynik or {}).get("rowcount"))


def _op_put(numer, symbol, sposob, id_subiekt=None, nazwa=None, uwagi=None,
            kto=None, kiedy=None):
    """Jedna operacja `map-put` do `master_exec`/`master_batch`."""
    return {"operation": "map-put", "params": {
        "numer_rysunku": _key(numer), "symbol_subiekt": symbol.strip(),
        "id_subiekt": id_subiekt, "nazwa_subiekt": nazwa, "sposob": sposob,
        "kto": kto or _kto(), "kiedy": kiedy or _teraz(), "uwagi": uwagi}}


# ── mapowania ────────────────────────────────────────────────────────────────

def get(numer, path=None):
    """Jedno mapowanie albo None."""
    k = _key(numer)
    if not k:
        return None
    wiersze = rm_klient.master_read("map-get", {"numer_rysunku": k})
    return wiersze[0] if wiersze else None


def get_many(numery, path=None):
    """{NUMER: mapowanie} dla listy numerów — jedno zapytanie zamiast N.

    To jest ta „warstwa filtrująca": wołane raz na całą listę BOM zanim
    cokolwiek poleci do Subiekta przez sieć. Lista idzie jako JSON, serwer
    rozwija ją `json_each` — bez limitu 999 zmiennych SQLite i bez sklejania
    `IN (?,?,?…)` po stronie klienta.
    """
    klucze = sorted({_key(n) for n in (numery or []) if _key(n)})
    if not klucze:
        return {}
    out = {}
    for i in range(0, len(klucze), _PACZKA):
        paczka = klucze[i:i + _PACZKA]
        for w in rm_klient.master_read("map-get-many",
                                       {"numery_json": json.dumps(paczka)}):
            out[w["numer_rysunku"]] = w
    return out


def put(numer, symbol_subiekt, sposob, id_subiekt=None, nazwa_subiekt=None,
        kto=None, uwagi=None, path=None):
    """Zapisuje/aktualizuje mapowanie. True, gdy zapisano.

    Ręczny wybór użytkownika nie jest nadpisywany automatem — decyzja
    człowieka ma pierwszeństwo, bo automat mógłby ją cofnąć przy następnym
    przebiegu. Regułę egzekwuje SQL operacji `map-put` na serwerze
    (`… DO UPDATE … WHERE sposob != 'reczny' OR excluded.sposob = 'reczny'`),
    więc obowiązuje tak samo dla `put`, `put_many` i scalania — i nie ma
    wyścigu „odczytaj czy ręczne → zapisz" między stacjami. Odrzucony wpis
    to rowcount 0, stąd False.
    """
    k = _key(numer)
    if not k or not (symbol_subiekt or "").strip():
        return False
    op = _op_put(k, symbol_subiekt, sposob, id_subiekt, nazwa_subiekt, uwagi, kto)
    return _zapisano(rm_klient.master_exec(op["operation"], op["params"]))


def put_many(wpisy, path=None):
    """[(numer, symbol, sposob[, id[, nazwa]])] → liczba zapisanych.

    Wołane po suchym przebiegu/zapisie, żeby zapamiętać, co Subiekt potwierdził.
    Paczka = jeden `master-batch` = JEDNA transakcja na serwerze.

    Historia: przez plik na Y: leciało `put()` w pętli — connect + PRAGMA +
    SELECT + INSERT + commit na KAŻDY wpis, 37 s na 354 pozycje (profil py-spy
    09.09.2026). Przez serwer cała paczka to jedno żądanie.

    Wpisy odrzucone regułą „ręczne ma pierwszeństwo" nie są liczone.
    """
    kto, kiedy = _kto(), _teraz()
    operacje = []
    for w in (wpisy or []):
        numer, symbol, sposob = w[0], w[1], w[2]
        if not _key(numer) or not (symbol or "").strip():
            continue
        operacje.append(_op_put(numer, symbol, sposob,
                                w[3] if len(w) > 3 else None,
                                w[4] if len(w) > 4 else None,
                                None, kto, kiedy))
    n = 0
    for i in range(0, len(operacje), _PACZKA):
        for wynik in rm_klient.master_batch(operacje[i:i + _PACZKA]):
            n += 1 if _zapisano(wynik) else 0
    return n


def delete(numer, path=None):
    """Usuwa mapowanie — gdy okaże się błędne (np. zły ręczny wybór)."""
    k = _key(numer)
    if not k:
        return False
    return _zapisano(rm_klient.master_exec("map-delete", {"numer_rysunku": k}))


def stats(path=None):
    """{sposob: liczba, 'razem': n} — do podglądu i diagnostyki."""
    out = {w["sposob"]: w["n"] for w in rm_klient.master_read("map-statystyki")}
    out["razem"] = sum(out.values())
    return out


# ── SCALANIE KARTOTEK: aliasy starych symboli ────────────────────────────────
# Tabela `aliasy_scalen` (schemat: migracje serwera) jest kluczowana STARYM
# SYMBOLEM SUBIEKTA, nie numerem z BOM-u — żeby po pół roku dało się
# odpowiedzieć „skąd wzięło się to mapowanie" i cofnąć decyzję. To dziennik:
# ten sam symbol może dostać kolejny wpis, `map-alias` czyta najnowszy.

def zapisz_scalenie(cel, cel_id, zrodla, path=None):
    """Po udanym scaleniu w Subiekcie: aliasy + przepięcie mapowań.

    `zrodla` = {stary_symbol: stary_id}. Trzy rzeczy na każde źródło, a całość
    w JEDNEJ transakcji (`master-batch` — wszystko albo nic):
      1. alias stary → nowy (`map-alias-dodaj`),
      2. każde mapowanie BOM-u, które wskazywało stary symbol, wskazuje
         teraz cel (`map-przepnij-symbol`) — inaczej arkusz dalej „widziałby"
         wycofaną kartotekę,
      3. mapowanie numer=stary_symbol → cel (sposob=scalona): gdy stary BOM
         przyniesie dosłownie stary symbol, etap 3 rozpozna go od razu jako
         zapamiętany i wskaże kartotekę docelową — bez zmian w dopasowaniu.
         Ręcznego mapowania pod tym numerem nie nadpisze (reguła `map-put`).
    Zwraca liczbę przepiętych mapowań (krok 2).
    """
    cel = (cel or "").strip()
    if not cel or not zrodla:
        return 0
    kto, kiedy = _kto(), _teraz()
    operacje = []
    for stary, stary_id in zrodla.items():
        stary = (stary or "").strip()
        if not stary:
            continue
        operacje.append({"operation": "map-alias-dodaj", "params": {
            "stary_symbol": stary, "stary_id": stary_id,
            "nowy_symbol": cel, "nowy_id": cel_id, "kto": kto, "kiedy": kiedy}})
        operacje.append({"operation": "map-przepnij-symbol", "params": {
            "nowy_symbol": cel, "nowy_id": cel_id, "stary_symbol": stary}})
        operacje.append(_op_put(stary, cel, SPOSOB_SCALONA, cel_id, None,
                                f"alias po scaleniu kartotek: {stary} → {cel}",
                                kto, kiedy))
        # Relacje polproduktow wskazujace wycofana kartoteke — ta sama
        # transakcja, bez osobnego ostrzezenia dla uzytkownika
        # (POLPRODUKTY_PLAN.md, „Kartoteka polproduktu nie znika").
        # Bez `stary_id` nie ma czego przepinac: relacja trzyma ID, nie symbol.
        if stary_id not in (None, ""):
            operacje.append({"operation": "map-polprodukt-przepnij", "params": {
                "nowy_id": cel_id, "nowy_symbol": cel,
                "stary_id": int(stary_id)}})
            # Resztki po `UPDATE OR IGNORE`: rysunki, ktore mialy JUZ relacje
            # do kartoteki docelowej — inaczej zostalby wiersz na martwym ID.
            operacje.append({
                "operation": "map-polprodukt-usun-po-scaleniu",
                "params": {"stary_id": int(stary_id)}})
    if not operacje:
        return 0
    wyniki = rm_klient.master_batch(operacje)
    # ⚠️ Liczymy po NAZWIE operacji, nie po pozycji w liscie: od 14.09.2026
    # zrodlo z `stary_id` dokłada dwie operacje polproduktow, wiec dawne
    # „co trzeci wynik" (`wyniki[1::3]`) wskazywaloby na cudze wiersze.
    return sum((w or {}).get("rowcount") or 0
               for op, w in zip(operacje, wyniki)
               if op["operation"] == "map-przepnij-symbol")


def alias_dla(symbol, path=None):
    """Kartoteka docelowa dla wycofanego symbolu albo None."""
    s = (symbol or "").strip()
    if not s:
        return None
    w = rm_klient.master_read("map-alias", {"stary_symbol": s})
    return {"symbol": w[0]["nowy_symbol"], "id": w[0]["nowy_id"]} if w else None


# ── Polprodukty zakupowe ─────────────────────────────────────────────────────
# Detal czesto powstaje z KUPIONEGO polfabrykatu: rysunek „Kolo 5M_40 fi38"
# to gotowe kolo zebate + obrobka otworu. Relacja mowi, CO trzeba kupic pod
# ten rysunek i ILE sztuk na jeden detal (POLPRODUKTY_PLAN.md).
#
# ⚠️ `symbol` i `nazwa` w zwracanych wierszach to CACHE do wyswietlania.
# Prawda o kartotece zyje w Subiekcie i ma tam `id_subiekt` — przy rozbieznosci
# wygrywa Subiekt, a cache odswiezamy kolejnym `zapisz_polprodukt`. Ceny,
# stanu i ilosci dostepnej NIE trzymamy wcale: kopia po dniu klamie.

def polprodukty(numer, path=None):
    """[wiersz, …] — polprodukty jednego rysunku. Pusta lista, gdy brak."""
    k = _key(numer)
    if not k:
        return []
    return rm_klient.master_read("map-polprodukt", {"numer_rysunku": k})


def polprodukty_many(numery, path=None):
    """{NUMER: [wiersz, …]} dla listy numerow — JEDNO zapytanie.

    Wolane raz na caly arkusz (znacznik 🛒 w kolumnie Δ), nie per wiersz.
    """
    klucze = sorted({_key(n) for n in (numery or []) if _key(n)})
    if not klucze:
        return {}
    out = {}
    for i in range(0, len(klucze), _PACZKA):
        for w in rm_klient.master_read(
                "map-polprodukty-many",
                {"numery_json": json.dumps(klucze[i:i + _PACZKA])}):
            out.setdefault(w["numer_rysunku"], []).append(w)
    return out


def polprodukt_gdzie(id_subiekt, path=None):
    """[wiersz, …] — w ktorych rysunkach uzywana jest ta kartoteka."""
    if id_subiekt in (None, ""):
        return []
    return rm_klient.master_read("map-polprodukt-gdzie",
                                 {"id_subiekt": int(id_subiekt)})


def zapisz_polprodukt(numer, id_subiekt, ilosc_na_szt=1, symbol=None,
                      nazwa=None, uwagi=None, path=None):
    """Powiaz rysunek z kartoteka polfabrykatu. True = zapisano.

    ⚠️ `ilosc_na_szt` jest CALKOWITA — „sztuka to sztuka, nic nie dzielimy".
    Kupujemy N sztuk polproduktu na 1 detal, zwykle 1. Docinany walek to
    zakup CALEGO walka, nie 0,3 sztuki (decyzja 14.09.2026).

    Ponowne wywolanie dla tej samej pary (rysunek, kartoteka) zmienia ILOSC
    i odswieza cache symbolu/nazwy — nie zaklada drugiego wiersza.
    """
    k = _key(numer)
    if not k or id_subiekt in (None, ""):
        return False
    # ⚠️ NIE `int(x or 1)`: zero jest falszywe, wiec „0 sztuk" po cichu stalo
    # sie „1 sztuka" zamiast bledem (zlapane testem 14.09.2026).
    ile = 1 if ilosc_na_szt is None else int(ilosc_na_szt)
    if ile < 1:
        raise ValueError("ilosc na sztuke musi byc >= 1 (sztuki calkowite)")
    return _zapisano(rm_klient.master_exec("map-polprodukt-zapisz", {
        "numer_rysunku": k, "id_subiekt": int(id_subiekt),
        "symbol": (symbol or "").strip() or None,
        "nazwa": (nazwa or "").strip() or None,
        "ilosc_na_szt": ile, "kto": _kto(), "kiedy": _teraz(),
        "uwagi": uwagi}))


def usun_polprodukt(numer, id_subiekt, path=None):
    """Rozwiaz powiazanie. True = cos usunieto."""
    k = _key(numer)
    if not k or id_subiekt in (None, ""):
        return False
    return _zapisano(rm_klient.master_exec("map-polprodukt-usun", {
        "numer_rysunku": k, "id_subiekt": int(id_subiekt)}))


# ── Decyzje o dostawcach ─────────────────────────────────────────────────────
# Osobna tabela: które wpisy z kolumny Dostawca RM_BAZA NIE są firmami
# („GIĘCIE", „spawanie", „?") i nie mają dostawać kontrahenta w Subiekcie.
# Powiązania „to jest ta firma" nie wymagają tabeli — zapisują się jako NIP
# w suppliers i następne dopasowanie idzie po NIP-ie. Ale „to nie firma" nie
# ma gdzie żyć w RM_BAZA, a bez utrwalenia wracało po każdym odświeżeniu.

def dostawcy_nie_firmy(path=None):
    """{supplier_id} oznaczonych jako „nie firma"."""
    return {w["supplier_id"] for w in rm_klient.master_read("map-dostawcy-nie-firmy")}


def dostawca_decyzja(supplier_id, nazwa, decyzja, path=None):
    """Zapisuje decyzję; decyzja=None cofa ją."""
    if decyzja is None:
        rm_klient.master_exec("map-dostawca-decyzja-usun", {"supplier_id": supplier_id})
    else:
        rm_klient.master_exec("map-dostawca-decyzja", {
            "supplier_id": supplier_id, "nazwa": nazwa, "decyzja": decyzja,
            "kto": _kto(), "kiedy": _teraz()})


if __name__ == "__main__":
    print("RM_SERWER:", rm_klient.opis())
    print("Statystyki:", stats())
