"""scan_czesci_znormalizowanych.py — szybki skan katalogu projektów pod kątem
części znormalizowanych (łożyska, siłowniki Festo, pneumatyka, IGUS, itd.).

Jeden przebieg drzewa katalogów w Pythonie zamiast wielu wywołań find/grep
przez agenta LLM — to samo zadanie w sekundy zamiast w ~1h.

Użycie:
    python scan_czesci_znormalizowanych.py
    python scan_czesci_znormalizowanych.py --root D:\\inny_katalog --out wynik.csv
    python scan_czesci_znormalizowanych.py --min-project 2020 --max-project 2325

Wynik: plik CSV (UTF-8 BOM, separator ';' — otwiera się poprawnie w Excelu)
z kolumnami: kategoria, kod, plik, sciezka, projekt. Traktuj jako surowe dane
wejściowe do ręcznego przeglądu i wklejenia do
slownik_czesci_znormalizowanych_SZABLON.xlsx — nie wklejaj bez sprawdzenia
(patrz uwagi o szumie w kategorii "Łożysko kulkowe" niżej).

Dopisywanie nowej kategorii: dodaj wpis do słownika CATEGORIES niżej
(kategoria -> lista wzorców regex) i uruchom ponownie.
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

# Wzorce wykluczające — śruby/złączki, nigdy nie klasyfikowane (nawet jeśli
# przypadkiem pasują do innego wzorca poniżej)
EXCLUDE_PATTERNS = [
    re.compile(r'\bDIN\s?9\d{2}\b', re.IGNORECASE),
    re.compile(r'\bISO\s?4\d{3}\b', re.IGNORECASE),
    re.compile(r'\bM\d{1,2}\s?x\s?\d+\b', re.IGNORECASE),
    re.compile(r'sruba|śruba|wkret|wkręt', re.IGNORECASE),
]

# kategoria -> lista wzorców regex (pierwsze trafienie w liście wygrywa kod)
CATEGORIES: dict[str, list[re.Pattern]] = {
    'Siłownik pneumatyczny (Festo)': [
        re.compile(r'\b(DFM|DSNU|ADVUL|DNC|DGP|ESBF)[-_]\S+', re.IGNORECASE),
        re.compile(r'\bADN[-_]\S+', re.IGNORECASE),
    ],
    'Pneumatyka (Festo — zawory/złączki)': [
        re.compile(r'\bVUVG[-_]\S+', re.IGNORECASE),
        re.compile(r'\bQS[-_][A-Z0-9/]+', re.IGNORECASE),
        re.compile(r'\bGRL[AZ][-_]?\S*', re.IGNORECASE),
    ],
    'Łożysko w oprawie (UC../ASAHI)': [
        re.compile(r'\bUCFL\d{2,3}\S*', re.IGNORECASE),
        re.compile(r'\bUCF\d{2,3}\S*', re.IGNORECASE),
        re.compile(r'\bUCP\d{2,3}\S*', re.IGNORECASE),
        re.compile(r'\bK(P|FL)\d{3}\S*', re.IGNORECASE),
    ],
    'Łożysko kulkowe': [
        # UWAGA: najbardziej podatna na szum kategoria — sam 4-cyfrowy numer
        # bez kontekstu bywa numerem rysunku, nie kodem łożyska. Przeglądaj
        # ręcznie zanim przepiszesz do arkusza.
        re.compile(r'\b6[0-3]\d{2}(?:[-\s]?(?:ZZ|2RS1?|RS1?|Z))?\b', re.IGNORECASE),
        re.compile(r'\b3\d{3}\s?A\b', re.IGNORECASE),
    ],
    'IGUS (tuleje/prowadnice ślizgowe)': [
        re.compile(r'\bLBN[-_]\d+[-_]\d+', re.IGNORECASE),
        re.compile(r'\bigus\b', re.IGNORECASE),
    ],
}

CATEGORY_ORDER = list(CATEGORIES.keys())
MODEL_EXTENSIONS = {'.ipt', '.iam'}
PROJECT_PREFIX_RE = re.compile(r'^(\d{4})')

# Sufiksy dopisywane przez Inventora do kopii/duplikatów tego samego pliku —
# usuwane przed porównaniem kodów, żeby "ADN-10-P.0001" i "ADN-10-P_MIR" nie
# wypadały jako dwa różne elementy
ARTIFACT_SUFFIXES = [
    re.compile(r'\.\d{3,4}$'),
    re.compile(r'_MIR$', re.IGNORECASE),
    re.compile(r'_kopia\d*$', re.IGNORECASE),
    re.compile(r'-copy\d*$', re.IGNORECASE),
]


def normalize_code(code: str) -> str:
    changed = True
    while changed:
        changed = False
        for pat in ARTIFACT_SUFFIXES:
            new = pat.sub('', code)
            if new != code:
                code = new
                changed = True
    return code


def project_name(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
        return rel.parts[0] if rel.parts else ''
    except ValueError:
        return ''


def project_number(name: str) -> int | None:
    m = PROJECT_PREFIX_RE.match(name)
    return int(m.group(1)) if m else None


def classify(stem: str) -> tuple[str, str] | None:
    if any(p.search(stem) for p in EXCLUDE_PATTERNS):
        return None
    for cat in CATEGORY_ORDER:
        for pattern in CATEGORIES[cat]:
            m = pattern.search(stem)
            if m:
                return cat, normalize_code(m.group(0).upper().strip('-_ '))
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', default=r'C:\projekty')
    ap.add_argument('--out', default='wynik_skanu_czesci.csv')
    ap.add_argument('--min-project', type=int, default=None)
    ap.add_argument('--max-project', type=int, default=None)
    args = ap.parse_args()

    root = Path(args.root)
    seen: dict[tuple[str, str], dict] = {}
    counts: dict[str, int] = {}
    total_files = 0

    for path in root.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in MODEL_EXTENSIONS:
            continue

        proj = project_name(path, root)
        if args.min_project is not None or args.max_project is not None:
            num = project_number(proj)
            if num is None:
                continue
            if args.min_project is not None and num < args.min_project:
                continue
            if args.max_project is not None and num > args.max_project:
                continue

        total_files += 1
        result = classify(path.stem)
        if not result:
            continue
        cat, code = result
        key = (cat, code)
        if key not in seen:
            seen[key] = {
                'kategoria': cat,
                'kod': code,
                'plik': path.name,
                'sciezka': str(path),
                'projekt': proj,
            }
            counts[cat] = counts.get(cat, 0) + 1

    with open(args.out, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(
            f, fieldnames=['kategoria', 'kod', 'plik', 'sciezka', 'projekt'], delimiter=';'
        )
        writer.writeheader()
        for row in sorted(seen.values(), key=lambda r: (r['kategoria'], r['kod'])):
            writer.writerow(row)

    print(f'Przeskanowano plikow .ipt/.iam: {total_files}')
    print(f'Znaleziono unikalnych kodow: {len(seen)}')
    for cat in CATEGORY_ORDER:
        print(f'  {cat}: {counts.get(cat, 0)}')
    print(f'Wynik zapisany do: {args.out}')


if __name__ == '__main__':
    main()
