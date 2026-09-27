# -*- coding: utf-8 -*-
"""indeks_modeli_3d.py — indeks „numer rysunku -> model 3D" dla makra MAG.

    python indeks_modeli_3d.py                     # suchy przebieg — NIC nie zapisuje
    python indeks_modeli_3d.py --zapisz            # zapis do serwera
    python indeks_modeli_3d.py --zapisz --pelny    # przebudowa od zera
    python indeks_modeli_3d.py --root "B:\\Czujniki RM" --raport r.txt

Etap 1 planu `PLAN_MAG.md`. Uruchamiany na STACJI z Inventorem
(W2019S go nie ma), wynik trafia do `subiekt_mapowania.sqlite` na serwerze,
tabela `modele_3d`, operacjami `map-model3d-*`.

SKĄD WIEMY, KTÓRY MODEL NALEŻY DO RYSUNKU
    `Inventor.ApprenticeServer` czyta referencje wprost z IDW. Osobny, lekki
    proces — nie dotyka sesji Inventora użytkownika. ⛔ NIE po nazwie pliku:
    „016-100.03 Uchwyt lusterka.idw" rysuje „blaszka lusterka, 304 gr1,5mm.ipt".

    Numer rysunku = pierwszy wyraz NAZWY IDW („016-100.03 Uchwyt….idw"),
    tak jak `import_bom.find_dwf_in_library`. Kontrolą jest `Part Number`
    modelu — dla detali RMPAK równy numerowi rysunku. Rozjazd trafia do
    raportu, nie blokuje zapisu (to może być model współdzielony).

CO POMIJAMY
    • katalogi `OldVersions`, `Nieaktualne`, `Templates`;
    • IDW bez numeru („Zespół trójkąta R1 lewy.idw") i ze starym numerem
      z apostrofem („2020-300.10' Ucho….idw" — to wersje wycofane);
    • rysunki, które mają wpis RĘCZNY — decyzja człowieka wygrywa;
    • bez `--pelny`: IDW niezmienione od poprzedniego skanu (ta sama ścieżka
      i data modyfikacji).

TEN SAM NUMER W KILKU MIEJSCACH (203 numery na B:, 27.09.2026)
    Np. `EWTR-820.01X` w `!BIBLIOTEKA\\Elewator` i w `WaterFall EWTR`.
    Wygrywa NOWSZY plik IDW. Gdy kopie wskazują RÓŻNE modele (po nazwie
    pliku, nie po ścieżce — kopia folderu to wciąż ten sam model), raport
    pokazuje to jako konflikt do sprawdzenia.

RYSUNEK BEZ MODELU (19% biblioteki) dostaje wiersz z pustą ścieżką —
to informacja dla makra („ten rysunek nie ma modelu 3D"), nie brak danych.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")       # polska konsola, cp1250

import rm_klient

#: Katalogi, których nie skanujemy — nazwy porównywane bez wielkości liter.
POMIJANE_KATALOGI = ("oldversions", "nieaktualne", "templates")

#: Rozszerzenia modeli. IDW potrafi wskazywać też inne rysunki czy obrazki.
MODELE = (".ipt", ".iam")

#: Biblioteka = katalog, z którego skanujemy rysunki I z którego wolno
#: wstawiać modele. W firmie (Mongo i każda inna stacja) to `B:`; na M-OLD
#: (dom) `C:\Projekty` — tam nie ma firmowej biblioteki, a projekty są
#: lokalnie (decyzja użytkownika 27.09.2026). Klucz = COMPUTERNAME.
BIBLIOTEKA_WG_KOMPUTERA = {"M-OLD": "C:\\Projekty\\"}
BIBLIOTEKA_DOMYSLNA = "B:\\"


def biblioteka() -> str:
    """Katalog biblioteki tej stacji, zakończony `\\`."""
    komputer = (os.environ.get("COMPUTERNAME") or "").upper()
    return BIBLIOTEKA_WG_KOMPUTERA.get(komputer, BIBLIOTEKA_DOMYSLNA)


#: Modele wstawiamy TYLKO z biblioteki (ustalenie 27.09.2026). Referencja do
#: `C:\Biblioteka\…` rozwiązuje się wyłącznie na stacji, która ma taką
#: lokalną kopię — na innej makro wstawiłoby nieistniejący plik. Tak było
#: z `016-100.05`: na M-OLD Apprentice znalazł model w `C:\Biblioteka`,
#: a naprawdę rysunek modelu nie ma (potwierdzone przez usera).
DOZWOLONE_DYSKI = (biblioteka().upper(),)

#: Ten sam katalog pod inną nazwą. `B:` to udział `BibliotekaRM`, a IDW
#: pamiętają ścieżkę AUTORA — `C:\BibliotekaRM\…` — którą Apprentice
#: rozwiązuje dosłownie, gdy stacja ma taki katalog lokalnie (M-OLD:
#: `B:` = `\\M-OLD\BibliotekaRM` =`C:\BibliotekaRM`). To NIE jest
#: zgadywanie po nazwie: ta sama ścieżka względna, ten sam plik. Przepisujemy
#: tylko wtedy, gdy plik na `B:` istnieje.
#: ⚠️ `C:\Biblioteka` (bez „RM") to INNY katalog — `016-100.05` wskazuje tam
#: model, którego na `B:` nie ma, i słusznie zostaje „bez modelu".
TEN_SAM_KATALOG = {"C:\\BIBLIOTEKARM\\": "B:\\"}


def na_dysk_b(sciezka: str) -> str:
    """Ścieżka przepisana na `B:` wg `TEN_SAM_KATALOG`, gdy plik tam jest."""
    gora = sciezka.upper()
    for stary, nowy in TEN_SAM_KATALOG.items():
        if gora.startswith(stary):
            kandydat = nowy + sciezka[len(stary):]
            if os.path.isfile(kandydat):
                return kandydat
    return sciezka

#: Ile operacji w jednym `master-batch`. Grupy jednego rysunku nie są
#: dzielone między paczki — „usuń stare + zapisz nowe" idzie jedną transakcją.
PACZKA = 400


# ── numer rysunku ──────────────────────────────────────────────────────────

def numer_z_nazwy(nazwa: str) -> str:
    """„016-100.03 Uchwyt lusterka.idw" -> „016-100.03"; pusty, gdy to nie numer.

    Numer musi mieć cyfrę. Apostrof odrzucamy — tak oznaczane są wersje
    wycofane („2020-300.10'"). Kropkę na końcu obcinamy („FC8U-100.02.").
    """
    trzon = os.path.splitext(nazwa)[0].strip()
    if not trzon:
        return ""
    nr = trzon.split(" ", 1)[0].strip().rstrip(".")
    if "'" in nr or "’" in nr or not any(c.isdigit() for c in nr):
        return ""
    return nr.upper()


def zbierz_idw(root: str) -> dict:
    """{NUMER: [(ścieżka, mtime), …] od najnowszego} — jeden przelot po dysku."""
    rysunki = {}
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs
                   if not any(p in d.lower() for p in POMIJANE_KATALOGI)]
        for f in files:
            if not f.lower().endswith(".idw"):
                continue
            nr = numer_z_nazwy(f)
            if not nr:
                continue
            sciezka = os.path.join(dirpath, f)
            try:
                mtime = os.path.getmtime(sciezka)
            except OSError:
                continue
            rysunki.setdefault(nr, []).append((sciezka, mtime))
    for lista in rysunki.values():
        lista.sort(key=lambda x: -x[1])
    return rysunki


# ── Apprentice ─────────────────────────────────────────────────────────────

def czytaj_idw(app, sciezka: str) -> dict:
    """{"modele": [(ścieżka, part_number)], "zepsute": [ścieżka]} albo {"blad": …}.

    `zepsute` = referencja do pliku, którego nie ma na dysku ALBO który leży
    poza `DOZWOLONE_DYSKI`. Takiego modelu nie da się wstawić na każdej
    stacji, więc nie trafia do `modele`.
    """
    try:
        dok = app.Open(sciezka)
    except Exception as e:
        return {"blad": str(e)[:120]}
    try:
        pn = {}
        try:
            rd = dok.ReferencedDocuments
            for i in range(1, rd.Count + 1):
                d = rd.Item(i)
                try:
                    wartosc = d.PropertySets.Item("Design Tracking Properties") \
                               .Item("Part Number").Value
                except Exception:
                    wartosc = ""
                pn[d.FullFileName.lower()] = (wartosc or "").strip()
        except Exception:
            pass                       # PN to tylko kontrola — brak nie szkodzi
        modele, zepsute = [], []
        pliki = dok.File.ReferencedFiles
        for i in range(1, pliki.Count + 1):
            oryginal = pliki.Item(i).FullFileName
            if not oryginal.lower().endswith(MODELE):
                continue
            s = na_dysk_b(oryginal)
            if s.upper().startswith(DOZWOLONE_DYSKI) and os.path.isfile(s):
                if s not in (m[0] for m in modele):
                    modele.append((s, pn.get(oryginal.lower(), "")))
            else:
                zepsute.append(s)
        return {"modele": modele, "zepsute": zepsute}
    except Exception as e:
        return {"blad": str(e)[:120]}
    finally:
        try:
            app.Close()
        except Exception:
            pass


# ── serwer ─────────────────────────────────────────────────────────────────

def skonfiguruj_serwer(adres=None):
    """Adres z `--serwer host:port` albo z `sync_config.json` (jak RM_BAZA).

    Brak pliku nie jest błędem: `rm_klient` ma adres firmowy na sztywno.
    """
    if adres:
        host, _, port = adres.partition(":")
        rm_klient.ustaw_serwer(host, int(port) if port else None)
        rm_klient.ustaw_uzytkownika("INDEKS_MODELI_3D")
        return
    try:
        cfg = json.loads(Path(r"C:\RMPAK_CLIENT\sync_config.json")
                         .read_text(encoding="utf-8-sig"))
        s = cfg.get("rm_serwer") or {}
        if s.get("host"):
            rm_klient.ustaw_serwer(s["host"], s.get("port"), s.get("sekret"))
    except Exception:
        pass
    rm_klient.ustaw_uzytkownika("INDEKS_MODELI_3D")


def indeks_z_serwera() -> dict:
    """{NUMER: [wiersz, …]} — to, co już leży w `modele_3d`."""
    out = {}
    for w in rm_klient.master_read("map-model3d-wszystkie", timeout=120):
        out.setdefault(w["numer_rysunku"], []).append(w)
    return out


def operacje_dla(numer, idw, mtime, modele, kto, kiedy) -> list:
    """„usuń stare automatyczne + zapisz nowe" dla jednego rysunku."""
    ops = [{"operation": "map-model3d-usun-auto",
            "params": {"numer_rysunku": numer}}]
    wiersze = modele or [("", "")]              # pusta ścieżka = brak modelu
    for i, (sciezka, pn) in enumerate(wiersze):
        ops.append({"operation": "map-model3d-zapisz", "params": {
            "numer_rysunku": numer, "sciezka": sciezka, "kolejnosc": i,
            "part_number": pn or None, "idw": idw, "idw_mtime": mtime,
            "zrodlo": "idw", "kto": kto, "kiedy": kiedy}})
    return ops


def zapisz(grupy: list, pelny: bool) -> int:
    """Wysyła grupy operacji paczkami. Zwraca liczbę zapisanych wierszy."""
    if pelny:
        rm_klient.master_exec("map-model3d-czysc", {})
    zapisane, paczka = 0, []

    def wyslij(p):
        n = 0
        for o, w in zip(p, rm_klient.master_batch(p, timeout=120)):
            if o["operation"] == "map-model3d-zapisz" and (w or {}).get("rowcount"):
                n += 1
        return n

    for g in grupy:
        if paczka and len(paczka) + len(g) > PACZKA:
            zapisane += wyslij(paczka)
            paczka = []
        paczka.extend(g)
    if paczka:
        zapisane += wyslij(paczka)
    return zapisane


# ── raport ─────────────────────────────────────────────────────────────────

def _nazwy(modele) -> set:
    return {os.path.basename(s).lower() for s, _pn in modele}


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=biblioteka(),
                    help="katalog do przeskanowania (domyślnie biblioteka tej stacji)")
    ap.add_argument("--zapisz", action="store_true",
                    help="zapis do serwera (bez tego suchy przebieg)")
    ap.add_argument("--pelny", action="store_true",
                    help="skanuj wszystko od nowa, także niezmienione IDW")
    ap.add_argument("--limit", type=int, default=0,
                    help="najwyżej N rysunków (do próby)")
    ap.add_argument("--raport", help="pełny raport do pliku tekstowego")
    ap.add_argument("--serwer", help="host:port RM_SERWER (domyślnie z sync_config.json)")
    a = ap.parse_args()

    print("=" * 72)
    print("INDEKS MODELI 3D  (numer rysunku -> .ipt/.iam)" +
          ("" if a.zapisz else "   [SUCHY PRZEBIEG — nic nie zapisuję]"))
    print(f"biblioteka tej stacji ({os.environ.get('COMPUTERNAME', '?')}): {biblioteka()}")
    print("=" * 72)

    # 1. Dysk
    t0 = time.time()
    rysunki = zbierz_idw(a.root)
    plikow = sum(len(v) for v in rysunki.values())
    print(f"\n1. {a.root}: {plikow} IDW z numerem, {len(rysunki)} unikalnych numerów"
          f"  ({time.time() - t0:.0f}s)")
    if not rysunki:
        print("   Nic do zrobienia.")
        return 0

    # 2. Serwer — co już wiemy
    skonfiguruj_serwer(a.serwer)
    print(f"\n2. {rm_klient.opis()}")
    try:
        znane = indeks_z_serwera()
        print(f"   w indeksie: {len(znane)} rysunków")
    except rm_klient.BladSerwera as e:
        if a.zapisz:
            print(f"   ⛔ serwer: {e}")
            return 1
        # Suchy przebieg ma sens i bez serwera — pokaże, co jest na dysku.
        # Tabela może też jeszcze nie istnieć (serwer bez nowych migracji).
        print(f"   ⚠️  serwer: {e}\n   liczę tak, jakby indeks był pusty")
        znane = {}

    # 3. Co skanować
    reczne, bez_zmian, do_skanu = [], 0, []
    for nr in sorted(rysunki):
        wiersze = znane.get(nr, [])
        if any(w["zrodlo"] == "reczny" for w in wiersze):
            reczne.append(nr)
            continue
        idw, mtime = rysunki[nr][0]
        if (not a.pelny and wiersze
                and all(w["idw"] == idw and w["idw_mtime"] == mtime for w in wiersze)):
            bez_zmian += 1
            continue
        do_skanu.append(nr)
    if a.limit:
        do_skanu = do_skanu[:a.limit]
    print(f"\n3. do skanu: {len(do_skanu)}   bez zmian: {bez_zmian}"
          f"   ręczne (nie ruszam): {len(reczne)}")

    # 4. Apprentice
    import win32com.client
    app = win32com.client.Dispatch("Inventor.ApprenticeServer")
    t0 = time.time()
    kto, kiedy = os.environ.get("USERNAME") or "?", datetime.now().isoformat(timespec="seconds")
    grupy = []
    wynik = {"jeden": 0, "kilka": 0, "brak": 0}
    nowe, zmienione, identyczne = [], [], 0
    bledy, zepsute, konflikty, pn_rozny = [], [], [], []

    for i, nr in enumerate(do_skanu, 1):
        kopie = rysunki[nr]
        odczyty = [(s, m, czytaj_idw(app, s)) for s, m in kopie]
        dobre = [(s, m, o) for s, m, o in odczyty if "blad" not in o]
        for s, _m, o in odczyty:
            if "blad" in o:
                bledy.append((nr, s, o["blad"]))
        if not dobre:
            continue
        idw, mtime, o = dobre[0]                # najnowszy czytelny
        modele = o["modele"]
        if o["zepsute"]:
            # Model poza `B:` albo nieistniejący — makro i tak nie ma czego
            # wstawić, więc dla indeksu to „bez modelu" (zapisujemy, żeby
            # nie skanować go przy każdym przebiegu). Raport pokazuje, co
            # IDW naprawdę wskazywał — do poprawienia w rysunku.
            zepsute.append((nr, idw, o["zepsute"]))
        for s2, _m2, o2 in dobre[1:]:
            if _nazwy(o2["modele"]) != _nazwy(modele):
                konflikty.append((nr, idw, modele, s2, o2["modele"]))
                break
        for s, pn in modele:
            if pn and pn.upper() != nr:
                pn_rozny.append((nr, s, pn))

        wynik["brak" if not modele else "jeden" if len(modele) == 1 else "kilka"] += 1
        stare = sorted(w["sciezka"] for w in znane.get(nr, []))
        nowe_sc = sorted(s for s, _ in modele) or [""]
        if not stare:
            nowe.append(nr)
        elif stare != nowe_sc:
            zmienione.append((nr, stare, nowe_sc))
        else:
            identyczne += 1
        grupy.append(operacje_dla(nr, idw, mtime, modele, kto, kiedy))

        if i % 200 == 0:
            print(f"   … {i}/{len(do_skanu)}  ({time.time() - t0:.0f}s)")

    # Masowe błędy otwarcia to prawie zawsze za stary Inventor: Apprentice
    # 2013 (M-OLD) nie otwiera IDW zapisanych przez 2015 w firmie. Pomiar
    # z planu (0 błędów) był robiony na stacji firmowej.
    if bledy and len(bledy) * 5 > len(do_skanu):
        try:
            wersja = app.SoftwareVersion.DisplayVersion
        except Exception:
            wersja = "?"
        print(f"\n   ⚠️  {len(bledy)} IDW się nie otworzyło — Apprentice tej stacji to"
              f" Inventor {wersja}. Pliki zapisane nowszym Inventorem są dla niego"
              f" nieczytelne; pełny skan uruchom na stacji z Inventorem firmowym.")

    razem = sum(wynik.values())
    print(f"\n4. Apprentice: {len(do_skanu)} rysunków w {time.time() - t0:.0f}s")
    print("=" * 72)
    if razem:
        print(f"   jeden model       {wynik['jeden']:>5}  ({wynik['jeden'] / razem * 100:.0f}%)")
        print(f"   kilka modeli      {wynik['kilka']:>5}  ({wynik['kilka'] / razem * 100:.0f}%)")
        print(f"   BEZ MODELU        {wynik['brak']:>5}  ({wynik['brak'] / razem * 100:.0f}%)")
    print(f"   model poza bibl.  {len(zepsute):>5}   (zapisuję jako bez modelu)")
    print(f"   błąd odczytu      {len(bledy):>5}")
    print(f"   konflikt kopii    {len(konflikty):>5}   (wygrał nowszy IDW)")
    print(f"   Part Number ≠ nr  {len(pn_rozny):>5}   (zapisuję, do sprawdzenia)")
    print("-" * 72)
    print(f"   ZMIANY W INDEKSIE: nowe {len(nowe)}, zmienione {len(zmienione)},"
          f" bez zmian {identyczne}")
    print("=" * 72)

    # Raport szczegółowy — na ekran po kilka przykładów, do pliku całość.
    # Każda pozycja to jeden blok (bywa wielowierszowy).
    sekcje = [
        ("ZMIENIONE", [f"   {nr}\n      było: {st}\n      jest: {no}"
                       for nr, st, no in zmienione]),
        ("KONFLIKT KOPII", [f"   {nr}\n      {s1} -> {sorted(_nazwy(m1))}"
                            f"\n      {s2} -> {sorted(_nazwy(m2))}"
                            for nr, s1, m1, s2, m2 in konflikty]),
        ("PART NUMBER RÓŻNY OD NUMERU", [f"   {nr:20} PN={pn:20} {s}"
                                         for nr, s, pn in pn_rozny]),
        ("ZEPSUTE REFERENCJE / MODEL POZA BIBLIOTEKĄ", [f"   {nr:20} {s}\n      brak: {z}"
                                for nr, s, z in zepsute]),
        ("BŁĄD ODCZYTU", [f"   {nr:20} {s}  ({b})" for nr, s, b in bledy]),
    ]
    if a.raport:
        with open(a.raport, "w", encoding="utf-8") as f:
            for tytul, bloki in sekcje:
                f.write(f"\n--- {tytul} ({len(bloki)}) ---\n")
                f.write("".join(b + "\n" for b in bloki))
        print(f"\nPełny raport: {a.raport}")
    else:
        for tytul, bloki in sekcje:
            if bloki:
                print(f"\n--- {tytul} ({len(bloki)}) ---")
                print("\n".join(bloki[:8]))
                if len(bloki) > 8:
                    print(f"   … i {len(bloki) - 8} więcej (--raport plik.txt)")

    # 5. Zapis
    if not a.zapisz:
        print(f"\nSUCHY PRZEBIEG — do zapisu byłoby {len(grupy)} rysunków."
              f" Uruchom z --zapisz.")
        return 0
    if not grupy and not a.pelny:
        print("\nNic do zapisania.")
        return 0
    n = zapisz(grupy, a.pelny)
    print(f"\n5. ZAPISANO: {n} wierszy dla {len(grupy)} rysunków"
          f" -> subiekt_mapowania.sqlite / modele_3d")
    return 0


if __name__ == "__main__":
    sys.exit(main())
