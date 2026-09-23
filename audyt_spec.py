# -*- coding: utf-8 -*-
"""Audyt plików `.spec`: czy PyInstaller na pewno spakuje moduły ładowane LENIWIE.

    python audyt_spec.py

Po co: PyInstaller analizuje importy STATYCZNIE. Moduł importowany wewnątrz
funkcji (`def open_okno(): import subiekt_panel`) jest dla niego niewidoczny
i nie trafia do `.exe`. Build kończy się sukcesem, `.exe` startuje, a dopiero
kliknięcie kafla daje `ModuleNotFoundError` — i to U USERA, nie u budującego,
bo ten ma obok pliki `.py`. Taki moduł trzeba wpisać do `hiddenimports`
w `.spec`.

⚠️ Ta pułapka wracała już TRZY razy (07.09, 23.09 ×2 — patrz
`pamiec/project_build_leniwe_importy.md`). Uruchamiać **po dołożeniu każdego
nowego okna** i przed zbudowaniem `.exe` do rozesłania.

Metoda:
1. w każdym `.spec` znajdź moduł wejściowy z `Analysis([...])` (`.py` i `.pyw`);
2. przez AST rozdziel importy na te z poziomu modułu (PyInstaller je widzi)
   i te wewnątrz funkcji/klas (nie widzi);
3. domknij rekurencyjnie — moduł leniwy wciąga też swoje własne importy,
   bo PyInstaller w ogóle do niego nie dotarł;
4. porównaj z treścią `.spec`.

⚠️ CZYTANIE WYNIKU — skrypt zgłasza też FAŁSZYWE ALARMY, każdy sprawdzić
ręcznie (`grep -n "import X" plik.py`):

* **moduł wejściowy `.spec`** — PyInstaller pakuje go zawsze;
* **importy top-level** — skrypt widzi je jako leniwe, gdy inny moduł
  importuje je w funkcji, ale wpis jest zbędny, jeśli główny plik ma je
  na górze (np. `backup_manager` w RM_BAZA, `rm_manager` w RM_MANAGER);
* **pakiety niezainstalowane** — np. `schedule` siedzi w `try/except` jako
  zależność opcjonalna; wpisanie go do `.spec` WYWALI build.

Z 9 kandydatów przy audycie 23.09.2026 realnych braków było 5.
"""
import ast
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
REPO = os.path.dirname(os.path.abspath(__file__))

LOKALNE = {f.rsplit(".", 1)[0] for f in os.listdir(REPO)
           if f.endswith((".py", ".pyw"))}

#: Zewnętrzne, które PyInstaller gubi przy imporcie dynamicznym. Lista celowo
#: wąska — chodzi o te realnie używane w projekcie, nie o cały PyPI.
WAZNE_ZEWN = {"tksheet", "requests", "win32com", "pythoncom", "pywintypes",
              "PIL", "openpyxl", "matplotlib", "numpy", "pandas", "reportlab",
              "fitz", "pyodbc", "serial", "schedule", "psutil"}


def sciezka_modulu(nazwa):
    """Plik modułu — `.py` albo `.pyw` (RM_Tray_Organizer)."""
    for suf in (".py", ".pyw"):
        p = os.path.join(REPO, nazwa + suf)
        if os.path.exists(p):
            return p
    return None


def importy(sciezka):
    """(top_level, leniwe) — nazwy modułów importowanych na obu poziomach."""
    try:
        drzewo = ast.parse(io.open(sciezka, encoding="utf-8",
                                   errors="replace").read())
    except (SyntaxError, OSError):
        return set(), set()
    top, lazy = set(), set()

    def nazwy(w):
        if isinstance(w, ast.Import):
            return {a.name.split(".")[0] for a in w.names}
        if isinstance(w, ast.ImportFrom) and w.module and w.level == 0:
            return {w.module.split(".")[0]}
        return set()

    for w in drzewo.body:
        top |= nazwy(w)
    for w in ast.walk(drzewo):
        if isinstance(w, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for p in ast.walk(w):
                if isinstance(p, (ast.Import, ast.ImportFrom)):
                    lazy |= nazwy(p)
    # to, co jest i tam, i tam, PyInstaller widzi z poziomu modułu
    return top, lazy - top


def domkniecie(start):
    """Moduły lokalne wciągnięte leniwie + wszystko, co one importują."""
    kolejka, widziane, zewn = list(start), set(), set()
    while kolejka:
        m = kolejka.pop()
        if m in widziane or m not in LOKALNE:
            continue
        widziane.add(m)
        p = sciezka_modulu(m)
        if not p:
            continue
        t, l = importy(p)
        for x in t | l:
            if x in LOKALNE:
                kolejka.append(x)
            elif x in WAZNE_ZEWN:
                zewn.add(x)
    return widziane, zewn


def modul_wejsciowy(spec_txt):
    m = re.search(r"Analysis\(\s*\[\s*r?['\"]([^'\"]+\.pyw?)['\"]", spec_txt)
    return m.group(1) if m else None


def main():
    bledow = 0
    for spec in sorted(f for f in os.listdir(REPO) if f.endswith(".spec")):
        txt = io.open(os.path.join(REPO, spec), encoding="utf-8",
                      errors="replace").read()
        wejscie = modul_wejsciowy(txt)
        print(f"\n### {spec}   (wejście: {wejscie})")
        if not wejscie or not os.path.exists(os.path.join(REPO, wejscie)):
            print("   pomijam — nie znalazłem pliku wejściowego")
            continue

        _, lazy = importy(os.path.join(REPO, wejscie))
        wszystkie, zewn = domkniecie({m for m in lazy if m in LOKALNE})

        # `.spec` to zwykły Python — wystarczy sprawdzić wystąpienie nazwy
        # w cudzysłowach, bo moduły trafiają tam i do hiddenimports, i do datas
        brak_lok = sorted(m for m in wszystkie
                          if f"'{m}'" not in txt and f'"{m}"' not in txt)
        brak_zewn = sorted(m for m in zewn
                           if f"'{m}'" not in txt and f'"{m}"' not in txt)

        print(f"   leniwych lokalnych (z domknięciem): {len(wszystkie)}")
        if not brak_lok and not brak_zewn:
            print("   BRAKÓW NIE MA")
            continue

        bledow += len(brak_lok) + len(brak_zewn)
        print(f"   DO SPRAWDZENIA: {len(brak_lok)} lokalnych, "
              f"{len(brak_zewn)} zewnętrznych")
        for m in brak_lok:
            zrodla = []
            for w in sorted(wszystkie | {wejscie.rsplit('.', 1)[0]}):
                p = sciezka_modulu(w)
                if p and m in set().union(*importy(p)):
                    zrodla.append(w)
            print(f"      {m:38} ← {', '.join(zrodla[:3]) or '?'}")
        for m in brak_zewn:
            print(f"      [zewn] {m}")

    if bledow:
        print(f"\n⚠️  {bledow} zgłoszeń — KAŻDE zweryfikuj ręcznie "
              f"(patrz nagłówek: fałszywe alarmy).")
    else:
        print("\nWszystkie .spec domknięte.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
