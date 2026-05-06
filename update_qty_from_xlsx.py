#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
update_qty_from_xlsx.py
=======================

Aktualizuje TYLKO ilości pozycji w bazie projektu RM-BAZA-MANAGER
(`rm_manager_project_<ID>.sqlite`) na podstawie nowego pliku XLSX:

    XLSX  "Ilość całkowita"  ->  items.work_qty   (wyświetlane jako "Ilość BOM")
    XLSX  "Ilość (zam.)"     ->  items.order_qty  (wyświetlane jako "Ilość (zam.)")

Pozostałe pola (nazwy, opisy, materiały, moduły, dostawcy, klasyfikacja,
delivered_qty, statusy, uwagi, eventy, milestones, locki itd.) NIE są ruszane.

Dopasowanie:
    1) po znormalizowanym numerze rysunku  (`work_drawing_no` || `src_drawing_no`)
    2) jeśli pozycja w XLSX nie ma numeru, po znormalizowanej nazwie
       (`work_name` || `src_name`)
    Dopasowanie jest case-insensitive z normalizacją białych znaków.

Bezpieczeństwo:
    * domyślnie DRY-RUN — pokazuje co by się zmieniło, NIC nie zapisuje
    * przy `--apply` najpierw robi kopię bazy (`*.sqlite.bak_qty_<TS>`)
    * całość jako jedna transakcja
    * raport CSV (`update_qty_report_<TS>.csv`) ze szczegółami każdej pozycji

Użycie (Windows, w PowerShell / cmd):

    python update_qty_from_xlsx.py ^
        --db   "C:\\sciezka\\rm_manager_project_12.sqlite" ^
        --xlsx "C:\\sciezka\\LOGISTYKA_OUT.xlsx"

    # po przejrzeniu raportu — uruchom drugi raz z --apply:
    python update_qty_from_xlsx.py ^
        --db   "C:\\sciezka\\rm_manager_project_12.sqlite" ^
        --xlsx "C:\\sciezka\\LOGISTYKA_OUT.xlsx" ^
        --apply

Opcjonalnie:
    --sheet ZBIORCZY            (domyślnie; spróbuje też pierwszego arkusza)
    --no-backup                 (przy --apply pomija kopię — NIE ZALECANE)
    --tolerance 0.001           (różnica poniżej której traktujemy jako "bez zmian")
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("BŁĄD: brak pandas — zainstaluj: pip install pandas openpyxl")


# ---------- helpers ---------------------------------------------------------

_WS_RE = re.compile(r"\s+")


def norm(s) -> str:
    """Normalizuje whitespace i case dla dopasowania (zgodnie z app)."""
    if s is None:
        return ""
    try:
        if isinstance(s, float) and pd.isna(s):
            return ""
    except Exception:
        pass
    return _WS_RE.sub(" ", str(s).strip()).upper()


def to_float(v):
    """Zamienia wartość z XLSX na float; '', None, 'nan' -> None."""
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    s = str(v).strip().replace(",", ".")
    if s == "" or s.lower() == "nan":
        return None
    # symbol '●' w WAREHOUSE multi-module = nieznane → traktuj jak brak
    if s == "●":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def almost_equal(a, b, tol: float) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


# ---------- XLSX ------------------------------------------------------------

XLSX_DRAWING_COLS = ["Nr rysunku", "Nr Rysunku", "Nr_rysunku", "Numer rysunku"]
XLSX_NAME_COLS = ["Nazwa"]
XLSX_QTY_BOM_COLS = ["Ilość całkowita", "Ilosc calkowita", "Ilość BOM", "Ilosc BOM"]
XLSX_QTY_ORDER_COLS = ["Ilość (zam.)", "Ilosc (zam.)", "Ilość zam.", "Ilosc zam."]


def pick_col(df: "pd.DataFrame", candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    # luźne dopasowanie po normalizacji
    norm_map = {norm(c): c for c in df.columns}
    for c in candidates:
        if norm(c) in norm_map:
            return norm_map[norm(c)]
    return None


def load_xlsx(xlsx_path: Path, sheet: str | None) -> "pd.DataFrame":
    xls = pd.ExcelFile(xlsx_path, engine="openpyxl")
    if sheet and sheet in xls.sheet_names:
        df = xls.parse(sheet, dtype=object)
    elif "ZBIORCZY" in xls.sheet_names:
        df = xls.parse("ZBIORCZY", dtype=object)
    else:
        df = xls.parse(xls.sheet_names[0], dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    return df


# ---------- DB --------------------------------------------------------------

def load_items(con: sqlite3.Connection):
    cur = con.execute(
        """
        SELECT
            id,
            COALESCE(NULLIF(work_drawing_no, ''), src_drawing_no) AS drawing_no,
            COALESCE(NULLIF(work_name, ''),         src_name)     AS name,
            COALESCE(work_qty, src_qty)                            AS qty_bom,
            order_qty
        FROM items
        """
    )
    rows = []
    for r in cur.fetchall():
        rows.append(
            {
                "id": r[0],
                "drawing_no": r[1] or "",
                "name": r[2] or "",
                "qty_bom": r[3],
                "order_qty": r[4],
            }
        )
    return rows


# ---------- main ------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Aktualizuje TYLKO Ilość BOM (work_qty) i Ilość (zam.) (order_qty) "
                    "w bazie projektu z nowego XLSX."
    )
    ap.add_argument("--db", required=True, help="Ścieżka do rm_manager_project_<ID>.sqlite")
    ap.add_argument("--xlsx", required=True, help="Ścieżka do nowego pliku XLSX (arkusz ZBIORCZY)")
    ap.add_argument("--sheet", default=None, help="Nazwa arkusza (domyślnie ZBIORCZY)")
    ap.add_argument("--apply", action="store_true", help="Wykonaj zapis (bez tej flagi: dry-run)")
    ap.add_argument("--no-backup", action="store_true", help="Pomija kopię bazy przy --apply (NIE ZALECANE)")
    ap.add_argument("--tolerance", type=float, default=1e-6,
                    help="Różnica liczbowa traktowana jako 'bez zmian' (domyślnie 1e-6)")
    args = ap.parse_args()

    db_path = Path(args.db)
    xlsx_path = Path(args.xlsx)
    if not db_path.exists():
        sys.exit(f"BŁĄD: nie znaleziono bazy: {db_path}")
    if not xlsx_path.exists():
        sys.exit(f"BŁĄD: nie znaleziono XLSX: {xlsx_path}")

    print(f"📂 DB:   {db_path}")
    print(f"📂 XLSX: {xlsx_path}")
    print(f"🔧 Tryb: {'APPLY (zapis)' if args.apply else 'DRY-RUN (tylko podgląd)'}")

    df = load_xlsx(xlsx_path, args.sheet)
    col_dn = pick_col(df, XLSX_DRAWING_COLS)
    col_name = pick_col(df, XLSX_NAME_COLS)
    col_bom = pick_col(df, XLSX_QTY_BOM_COLS)
    col_ord = pick_col(df, XLSX_QTY_ORDER_COLS)
    if col_name is None or (col_bom is None and col_ord is None):
        sys.exit(f"BŁĄD: brak wymaganych kolumn w XLSX. "
                 f"Wykryte: dn={col_dn}, name={col_name}, qty_bom={col_bom}, qty_ord={col_ord}")
    print(f"🧭 Kolumny XLSX: dn='{col_dn}'  name='{col_name}'  "
          f"qty_bom='{col_bom}'  qty_ord='{col_ord}'")

    con = sqlite3.connect(str(db_path))
    items = load_items(con)
    print(f"📊 Pozycji w bazie: {len(items)}")

    # indeksy
    by_dn: dict[str, list[dict]] = {}
    by_name: dict[str, list[dict]] = {}
    for it in items:
        k = norm(it["drawing_no"])
        if k:
            by_dn.setdefault(k, []).append(it)
        else:
            by_name.setdefault(norm(it["name"]), []).append(it)

    # raport
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = db_path.with_name(f"update_qty_report_{ts}.csv")

    stats = {
        "xlsx_rows": 0,
        "matched_dn": 0,
        "matched_name": 0,
        "ambiguous": 0,
        "not_found": 0,
        "no_change": 0,
        "to_update": 0,
    }
    updates: list[tuple] = []  # (id, new_bom, new_ord)
    rows_for_report = []

    for _, r in df.iterrows():
        # pomijamy puste wiersze
        dn = r[col_dn] if col_dn else None
        nm = r[col_name] if col_name else None
        if (dn is None or norm(dn) == "") and (nm is None or norm(nm) == ""):
            continue
        stats["xlsx_rows"] += 1

        dn_n = norm(dn)
        nm_n = norm(nm)
        new_bom = to_float(r[col_bom]) if col_bom else None
        new_ord = to_float(r[col_ord]) if col_ord else None

        # zasada z importu: '●' w BOM => użyj qty_zam jako BOM
        raw_bom = r[col_bom] if col_bom else None
        if raw_bom is not None and str(raw_bom).strip() == "●":
            new_bom = new_ord

        # dopasowanie
        candidates: list[dict] = []
        match_kind = ""
        if dn_n and dn_n in by_dn:
            candidates = by_dn[dn_n]
            match_kind = "DRAWING_NO"
        elif nm_n and nm_n in by_name:
            candidates = by_name[nm_n]
            match_kind = "NAME"

        if not candidates:
            stats["not_found"] += 1
            rows_for_report.append([dn or "", nm or "", "", "NOT_FOUND", "", "", "", "",
                                    new_bom if new_bom is not None else "",
                                    new_ord if new_ord is not None else ""])
            continue

        if len(candidates) > 1:
            stats["ambiguous"] += 1

        if match_kind == "DRAWING_NO":
            stats["matched_dn"] += 1
        else:
            stats["matched_name"] += 1

        for it in candidates:
            cur_bom = it["qty_bom"]
            cur_ord = it["order_qty"]
            change_bom = (new_bom is not None) and (not almost_equal(cur_bom, new_bom, args.tolerance))
            change_ord = (new_ord is not None) and (not almost_equal(cur_ord, new_ord, args.tolerance))
            status = "MULTI_MATCH" if len(candidates) > 1 else match_kind
            if not change_bom and not change_ord:
                stats["no_change"] += 1
                rows_for_report.append([
                    dn or "", nm or "", it["id"], status,
                    cur_bom if cur_bom is not None else "",
                    new_bom if new_bom is not None else "",
                    cur_ord if cur_ord is not None else "",
                    new_ord if new_ord is not None else "",
                    "NO_CHANGE", ""
                ])
                continue

            stats["to_update"] += 1
            # zachowujemy starą wartość gdy w XLSX brak (None)
            final_bom = new_bom if new_bom is not None else cur_bom
            final_ord = new_ord if new_ord is not None else cur_ord
            updates.append((it["id"], final_bom, final_ord, change_bom, change_ord))
            change_desc = []
            if change_bom:
                change_desc.append(f"BOM {cur_bom}→{new_bom}")
            if change_ord:
                change_desc.append(f"ZAM {cur_ord}→{new_ord}")
            rows_for_report.append([
                dn or "", nm or "", it["id"], status,
                cur_bom if cur_bom is not None else "",
                new_bom if new_bom is not None else "",
                cur_ord if cur_ord is not None else "",
                new_ord if new_ord is not None else "",
                "WILL_UPDATE" if not args.apply else "UPDATED",
                "; ".join(change_desc),
            ])

    # zapis raportu
    with report_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["xlsx_drawing_no", "xlsx_name", "item_id", "match",
                    "current_qty_bom", "new_qty_bom",
                    "current_order_qty", "new_order_qty",
                    "result", "changes"])
        w.writerows(rows_for_report)
    print(f"📝 Raport: {report_path}")

    print("\n--- PODSUMOWANIE ---")
    for k, v in stats.items():
        print(f"  {k:>14s}: {v}")

    if not updates:
        print("\nBrak zmian do zapisania.")
        con.close()
        return

    if not args.apply:
        print(f"\nDRY-RUN: NIC nie zapisano. Po przejrzeniu raportu uruchom z --apply.")
        con.close()
        return

    # backup
    if not args.no_backup:
        bak = db_path.with_suffix(db_path.suffix + f".bak_qty_{ts}")
        shutil.copy2(db_path, bak)
        print(f"💾 Backup bazy: {bak}")

    # apply: TYLKO work_qty / order_qty + updated_at; NIC innego
    cur = con.cursor()
    try:
        cur.execute("BEGIN")
        for item_id, final_bom, final_ord, change_bom, change_ord in updates:
            sets = []
            params = []
            if change_bom:
                sets.append("work_qty = ?")
                params.append(final_bom)
            if change_ord:
                sets.append("order_qty = ?")
                params.append(final_ord)
            if not sets:
                continue
            sets.append("updated_at = datetime('now')")
            params.append(item_id)
            cur.execute(f"UPDATE items SET {', '.join(sets)} WHERE id = ?", params)
        con.commit()
        print(f"✅ Zapisano {len(updates)} aktualizacji.")
    except Exception as e:
        con.rollback()
        sys.exit(f"BŁĄD zapisu (rollback): {e}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
