# -*- coding: utf-8 -*-
"""
Powiązanie dostawców RM_BAZA z kontrahentami Subiekta — po NIP-ie.

Problem (zmierzony 04.09.2026): RM_BAZA ma 113 dostawców, Subiekt 629
kontrahentów, a wspólnym kluczem są tylko nazwy — i te pokrywają się w 55 %.
Reszta to warianty zapisu („AMBProdukt lasery" ↔ „AMB PRODUKT Piotr Bobrowski"),
dopiski („Alufrost domówione") i wpisy, które wcale nie są firmami
(„GIĘCIE", „spawanie", „?").

Rozwiązanie: **NIP jako klucz twardy.** Kolumna `nip` w `suppliers` istnieje,
ale jest wypełniona w 1 rekordzie na 113. Ten moduł ją uzupełnia — biorąc NIP
z Subiekta dla dostawców dopasowanych po nazwie. Od tego momentu dopasowanie
idzie po NIP-ie (pewne), a nazwa jest tylko podpowiedzią przy pierwszym wiązaniu.

    python subiekt_dostawcy.py            # suchy przebieg — pokazuje co by zapisał
    python subiekt_dostawcy.py --zapisz   # dopisuje NIP-y do RM_BAZA

⚠️ Zapisuje do master.sqlite (RM_BAZA), NIE do Subiekta. Uzupełnia wyłącznie
puste NIP-y — istniejących nie nadpisuje.
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile

from subiekt_stany import _find_exe, blad_mostu, CONFIG_PATH, PROJECTS_DIR

TIMEOUT_S = 300


def _master_path():
    return os.path.join(os.path.dirname(PROJECTS_DIR.rstrip("\\/")), "master.sqlite")


# ── Kontrahenci z Subiekta ──────────────────────────────────────────────────
def pobierz_kontrahentow(timeout=TIMEOUT_S):
    """[{id, nazwa, nip}] — firmy z Subiekta."""
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")
    if not os.path.isfile(CONFIG_PATH):
        raise RuntimeError(f"Brak konfiguracji połączenia:\n{CONFIG_PATH}")

    tmpdir = tempfile.mkdtemp(prefix="subiekt_kontr_")
    out = os.path.join(tmpdir, "kontr.json")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.run([exe, "kontrahenci", f"--out={out}"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=flags)
    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(blad_mostu(exe, "kontrahenci", proc, out))

    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    return [{"id": k.get("Id"),
             "nazwa": (k.get("NazwaSkrocona") or "").strip(),
             "nip": (k.get("NIP") or "").strip()}
            for k in data.get("kontrahenci", [])]


# ── Dostawcy RM_BAZA ────────────────────────────────────────────────────────
def pobierz_dostawcow():
    """[{supplier_id, name, nip}] z master.sqlite."""
    p = _master_path()
    if not os.path.isfile(p):
        raise RuntimeError(f"Brak bazy głównej: {p}")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        return [{"supplier_id": r[0], "name": (r[1] or "").strip(),
                 "nip": (r[2] or "").strip() if r[2] else ""}
                for r in con.execute(
                    "SELECT supplier_id, name, nip FROM suppliers "
                    "WHERE COALESCE(name,'') <> ''")]
    finally:
        con.close()


def _uprosc(s):
    """Nazwa bez znaków, które w jednym systemie są ozdobnikiem, a w drugim nie."""
    return "".join(c for c in (s or "").lower() if c.isalnum())


# Wpisy, które nie są firmami — operacje technologiczne, statusy, magazyn.
# Nie zakładamy dla nich kontrahentów i nie szukamy im NIP-u.
NIE_FIRMY = {
    # statusy i miejsca
    "?", "magazyn", "anulowane", "oferta", "klient", "casting", "kabelki",
    # operacje technologiczne wpisywane w pole Dostawca
    "spawanie", "giecie", "giecie2", "gięcie", "gięcie2", "tokarnia",
    "malowanie", "gwintowanie", "lakiernia", "montaż", "montaz",
    "laser", "laser1", "laser2", "materiał", "material",
}


def czy_nie_firma(nazwa):
    n = (nazwa or "").strip().lower()
    return n in NIE_FIRMY or _uprosc(n) in {_uprosc(x) for x in NIE_FIRMY}


def dopasuj(dostawcy, kontrahenci):
    """[(dostawca, kontrahent|None, powód)] — dopasowanie po nazwie.

    Kolejność prób: NIP (jeśli już jest) → nazwa dokładnie → nazwa uproszczona
    → pierwszy człon, gdy jednoznaczny. Ta sama logika co w oknie zamówień.
    Decyzje „nie firma" podjęte w oknie są trwałe (subiekt_mapowania).
    """
    try:
        import subiekt_mapowania
        reczne_nie_firmy = subiekt_mapowania.dostawcy_nie_firmy()
    except Exception:
        reczne_nie_firmy = set()

    po_nip = {k["nip"]: k for k in kontrahenci if k["nip"]}
    po_nazwie = {k["nazwa"].lower(): k for k in kontrahenci}
    po_uproszczonej = {}
    for k in kontrahenci:
        po_uproszczonej.setdefault(_uprosc(k["nazwa"]), k)

    wynik = []
    for d in dostawcy:
        if czy_nie_firma(d["name"]) or d["supplier_id"] in reczne_nie_firmy:
            wynik.append((d, None, "nie-firma"))
            continue
        if d["nip"] and d["nip"] in po_nip:
            wynik.append((d, po_nip[d["nip"]], "nip"))
            continue

        k = po_nazwie.get(d["name"].lower())
        if k:
            wynik.append((d, k, "nazwa"))
            continue

        k = po_uproszczonej.get(_uprosc(d["name"]))
        if k:
            wynik.append((d, k, "nazwa-uproszczona"))
            continue

        pierwszy = d["name"].split()[0] if d["name"].split() else ""
        if len(pierwszy) >= 3:
            pu = _uprosc(pierwszy)
            traf = [k for k in kontrahenci if _uprosc(k["nazwa"]).startswith(pu)]
            if len(traf) == 1:
                wynik.append((d, traf[0], "pierwszy-człon"))
                continue

        wynik.append((d, None, "brak"))
    return wynik


def dopisz_nipy(pary, zapisz=False):
    """Uzupełnia puste NIP-y w RM_BAZA. Zwraca listę (nazwa, nip, status)."""
    zmiany = []
    for d, k, powod in pary:
        if not k or not k["nip"]:
            continue
        if d["nip"]:
            # Nie nadpisujemy — jeśli NIP już jest, to ktoś go wpisał świadomie.
            status = "ma-nip" if d["nip"] == k["nip"] else "ROZBIEŻNY"
            zmiany.append((d["name"], d["nip"], status))
            continue
        zmiany.append((d["name"], k["nip"], "do-dopisania"))

    if not zapisz:
        return zmiany

    p = _master_path()
    con = sqlite3.connect(p, timeout=15.0)
    try:
        con.execute("PRAGMA journal_mode=DELETE")   # WAL nie działa przez SMB
        con.execute("PRAGMA busy_timeout=5000")
        for d, k, powod in pary:
            if k and k["nip"] and not d["nip"]:
                con.execute("UPDATE suppliers SET nip = ? WHERE supplier_id = ?",
                            (k["nip"], d["supplier_id"]))
        con.commit()
    finally:
        con.close()
    return [(n, nip, "zapisany" if s == "do-dopisania" else s) for n, nip, s in zmiany]


def dane_kontaktowe(nazwy):
    """{nazwa: {email, telefon}} — z suppliers, do założenia kontrahenta."""
    p = _master_path()
    if not os.path.isfile(p) or not nazwy:
        return {}
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info('suppliers')")}
        mail = [c for c in ("email_default", "email") if c in cols]
        tel = [c for c in ("phone_default", "phone") if c in cols]
        sel = ["name"] + mail + tel
        q = (f"SELECT {', '.join(sel)} FROM suppliers "
             f"WHERE name IN ({','.join('?' * len(nazwy))})")
        out = {}
        for r in con.execute(q, list(nazwy)):
            wart = list(r[1:])
            e = next((v for v in wart[:len(mail)] if v and str(v).strip()), "")
            t = next((v for v in wart[len(mail):] if v and str(v).strip()), "")
            out[r[0]] = {"email": str(e).strip(), "telefon": str(t).strip()}
        return out
    except sqlite3.Error:
        return {}
    finally:
        con.close()


def zaloz_w_subiekcie(dostawcy_do_zalozenia, zapisz=False, timeout=TIMEOUT_S):
    """Zakłada kontrahentów w Subiekcie. dostawcy_do_zalozenia: [{name, nip}].

    NIP trafia w pole NIP kartoteki — dzięki temu w Subiekcie wystarczy
    zaznaczyć nowego kontrahenta i kliknąć „Pobierz z GUS", bez przepisywania.
    Sfera sama z GUS nie pobiera (to funkcja interfejsu, nie API).
    """
    exe = _find_exe()
    if not exe:
        raise RuntimeError("Nie znaleziono NexoRecon.exe.")

    kontakty = dane_kontaktowe([d["name"] for d in dostawcy_do_zalozenia])
    plan = {"dostawcy": [{
        "nazwa": d["name"],
        "nip": d.get("nip", ""),
        "email": kontakty.get(d["name"], {}).get("email", ""),
        "telefon": kontakty.get(d["name"], {}).get("telefon", ""),
    } for d in dostawcy_do_zalozenia]}

    tmpdir = tempfile.mkdtemp(prefix="subiekt_dost_")
    plan_path = os.path.join(tmpdir, "plan.json")
    out = os.path.join(tmpdir, "wynik.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)

    cmd = [exe, "dostawcy", f"--plan={plan_path}", f"--out={out}"]
    if zapisz:
        cmd.append("--zapisz")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=flags)
    if proc.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(blad_mostu(exe, "dostawcy", proc, out))
    with open(out, encoding="utf-8") as f:
        return json.load(f)


def raport(zapisz=False):
    kontrahenci = pobierz_kontrahentow()
    dostawcy = pobierz_dostawcow()
    pary = dopasuj(dostawcy, kontrahenci)

    ile = lambda p: sum(1 for _, _, x in pary if x == p)          # noqa: E731
    print(f"RM_BAZA: {len(dostawcy)} dostawców   |   Subiekt: {len(kontrahenci)} "
          f"kontrahentów ({sum(1 for k in kontrahenci if k['nip'])} z NIP)")
    print(f"  po NIP:            {ile('nip')}")
    print(f"  po nazwie:         {ile('nazwa') + ile('nazwa-uproszczona') + ile('pierwszy-człon')}")
    print(f"  nie-firmy:         {ile('nie-firma')}  (GIĘCIE, spawanie, ? …)")
    print(f"  bez dopasowania:   {ile('brak')}  ← kandydaci do założenia w Subiekcie")

    zmiany = dopisz_nipy(pary, zapisz)
    do_zapisu = [z for z in zmiany if z[2] in ("do-dopisania", "zapisany")]
    rozbiezne = [z for z in zmiany if z[2] == "ROZBIEŻNY"]

    print()
    print(f"NIP-y {'ZAPISANE' if zapisz else 'do dopisania'}: {len(do_zapisu)}")
    for n, nip, _ in do_zapisu[:15]:
        print(f"    {n[:34]:34} → {nip}")
    if len(do_zapisu) > 15:
        print(f"    … i {len(do_zapisu) - 15} więcej")
    if rozbiezne:
        print(f"\n⚠ ROZBIEŻNE NIP-y ({len(rozbiezne)}) — RM_BAZA ma inny niż Subiekt:")
        for n, nip, _ in rozbiezne:
            print(f"    {n}: RM_BAZA={nip}")

    brak = [d["name"] for d, k, p in pary if p == "brak"]
    if brak:
        print(f"\nBEZ DOPASOWANIA ({len(brak)}) — do założenia w Subiekcie albo do sprawdzenia:")
        for n in brak[:20]:
            print(f"    {n}")
        if len(brak) > 20:
            print(f"    … i {len(brak) - 20} więcej")
    if not zapisz:
        print("\n(suchy przebieg — nic nie zapisano; uruchom z --zapisz)")
    return [d for d, k, p in pary if p == "brak"]


def zakladaj(zapisz=False):
    """Zakłada w Subiekcie kontrahentów dla niedopasowanych dostawców RM_BAZA."""
    kontrahenci = pobierz_kontrahentow()
    dostawcy = pobierz_dostawcow()
    brak = [d for d, k, p in dopasuj(dostawcy, kontrahenci) if p == "brak"]
    if not brak:
        print("Wszyscy dostawcy mają odpowiednik w Subiekcie — nie ma czego zakładać.")
        return

    print(f"Do założenia w Subiekcie: {len(brak)} kontrahentów")
    wynik = zaloz_w_subiekcie(brak, zapisz=zapisz)
    for k in wynik.get("kroki", []):
        print(f"    {k['Nazwa'][:34]:34} {k['Status']:14} {k.get('Szczegoly') or ''}")
    if not zapisz:
        print("\n(suchy przebieg — w Subiekcie nic nie powstało; dodaj --zapisz)")
    else:
        print("\nW Subiekcie: zaznacz nowych kontrahentów i użyj „Pobierz z GUS” —\n"
              "NIP jest już w kartotece, więc nie trzeba go przepisywać.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--zakladaj" in sys.argv:
        zakladaj(zapisz="--zapisz" in sys.argv)
    else:
        raport(zapisz="--zapisz" in sys.argv)
