"""
Moduł importu BOM z Excel (LOGISTYKA_OUT.xlsx) lub CSV
Funkcje pomocnicze + konwerter CSV -> XLSX
"""
import csv
import re
import tempfile
from pathlib import Path
from typing import Generator, Dict, Optional, Tuple
import openpyxl


def csv_to_xlsx(csv_path: Path, encoding: str = "auto") -> Path:
    """
    Konwertuje plik CSV na XLSX z arkuszem ZBIORCZY.
    
    Plik tymczasowy XLSX jest tworzony obok oryginału (ten sam katalog).
    
    Args:
        csv_path: Ścieżka do pliku CSV
        encoding: Kodowanie CSV ('auto' = próbuj utf-8-sig, cp1250, latin-1)
    
    Returns:
        Path do utworzonego pliku XLSX
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Plik CSV nie istnieje: {csv_path}")
    
    # Wykryj kodowanie
    encodings = ["utf-8-sig", "utf-8", "cp1250", "latin-1"]
    if encoding != "auto":
        encodings = [encoding]
    
    rows = None
    used_encoding = None
    for enc in encodings:
        try:
            with open(csv_path, "r", encoding=enc, newline="") as f:
                # Wykryj separator (;  ,  \t)
                sample = f.read(4096)
                f.seek(0)
                sniffer = csv.Sniffer()
                try:
                    dialect = sniffer.sniff(sample, delimiters=";,\t")
                except csv.Error:
                    dialect = csv.excel
                    dialect.delimiter = ";"  # domyślnie średnik (PL)
                
                reader = csv.reader(f, dialect)
                rows = list(reader)
                used_encoding = enc
                break
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    if rows is None:
        raise ValueError(f"Nie udało się odczytać CSV żadnym kodowaniem: {csv_path.name}")
    
    if not rows:
        raise ValueError(f"Plik CSV jest pusty: {csv_path.name}")
    
    print(f"📄 CSV: {csv_path.name} ({len(rows)} wierszy, encoding={used_encoding})")
    
    # Utwórz XLSX
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ZBIORCZY"
    
    for row in rows:
        ws.append(row)
    
    # Zapisz obok oryginału
    xlsx_path = csv_path.with_suffix(".xlsx")
    # Jeśli plik już istnieje, dodaj _csv suffix
    if xlsx_path.exists():
        xlsx_path = csv_path.with_name(csv_path.stem + "_csv.xlsx")
    
    wb.save(xlsx_path)
    wb.close()
    
    print(f"✅ CSV → XLSX: {xlsx_path.name} ({len(rows)} wierszy)")
    return xlsx_path


def norm(s) -> str:
    """Normalizacja tekstu: usuń nadmiarowe spacje, non-breaking spaces"""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s).replace("\u00A0", " ")).strip()


def parse_thickness_mm(material_text: str) -> Optional[float]:
    """
    Wyciąga grubość z zapisu 'gr1,5mm' → 1.5
    
    Przykłady:
        "Blacha gr1,5mm"     → 1.5
        "STAL gr 2mm"        → 2.0
        "AL gr0,8 mm"        → 0.8
        "Blacha 3mm"         → None (brak "gr")
    
    Returns:
        float lub None jeśli nie znaleziono
    """
    if not material_text:
        return None
    
    # Regex: \bgr\s*([0-9]+(?:[\.,][0-9]+)?)\s*mm\b
    m = re.search(
        r"\bgr\s*([0-9]+(?:[\.,][0-9]+)?)\s*mm\b",
        str(material_text),
        flags=re.IGNORECASE
    )
    
    if not m:
        return None
    
    try:
        return float(m.group(1).replace(",", "."))
    except Exception:
        return None


def normalize_type_label(t: str) -> str:
    """
    Normalizuje opisy typu z Excela/DB do kanonicznych wartości w bazie:
    X, XX, Z, ZZ, STANDARD, ZNORMALIZOWANE, UNKNOWN.
    
    W LOGISTYKA_OUT.xlsx w kolumnie 'Typ' bywają etykiety opisowe (np. 'CIĘCIE (X)', 
    'CIĘCIE+GIĘCIE (XX)', 'ZŁOŻENIE (Z)', 'MODUŁ (ZZ)').
    
    UWAGA: NIE wolno wykrywać samej litery 'Z' regexem, bo psuje 'ZNORMALIZOWANE'.
    """
    tt = norm(t).upper()
    if not tt:
        return "UNKNOWN"
    
    # Najpierw pełne słowa (żeby nie psuć ZNORMALIZOWANE)
    if "ZNORMALIZOWANE" in tt:
        return "ZNORMALIZOWANE"
    
    if tt in ("STANDARD", "STAND."):
        return "STANDARD"
    
    if tt in ("UNKNOWN", "NIEZNANE"):
        return "UNKNOWN"
    
    # Kolejność ma znaczenie (XX przed X)
    if tt == "ZZ" or "(ZZ" in tt or "(ZZ)" in tt or "MODUŁ" in tt:
        return "ZZ"
    
    if tt == "Z" or "(Z" in tt or "(Z)" in tt or "ZŁOŻENIE" in tt:
        return "Z"
    
    if tt == "XX" or "(XX" in tt or "(XX)" in tt or ("GIĘCIE" in tt and "X" in tt):
        return "XX"
    
    if tt == "X" or "(X)" in tt or ("CIĘCIE" in tt and "GIĘCIE" not in tt and "XX" not in tt):
        return "X"
    
    return "UNKNOWN"


def infer_type_from_drawing_no(dn: str) -> str:
    """
    Inferencja typu z Nr rysunku.
    
    - XX: końcówka numeru → 'XX'
    - X:  końcówka numeru → 'X'
    - ZZ: końcówka numeru → 'ZZ'
    - Z:  końcówka numeru → 'Z'
    - pusty numer: 'ZNORMALIZOWANE'
    - reszta: 'STANDARD'
    """
    s = norm(dn).upper()
    if not s:
        return "ZNORMALIZOWANE"
    
    # Kolejność ma znaczenie: dłuższe sufiksy przed krótszymi
    if s.endswith("ZZ"):
        return "ZZ"
    if s.endswith("Z"):
        return "Z"
    if s.endswith("XX"):
        return "XX"
    if s.endswith("X"):
        return "X"
    
    return "STANDARD"


def iter_zbiorczy_data_rows(excel_path: Path) -> Generator[Dict[str, str], None, None]:
    """
    Czyta LOGISTYKA_OUT.xlsx → arkusz ZBIORCZY.
    
    Zwraca rekordy tylko dla wierszy danych, pomija:
      - nagłówki sekcji (ELEMENTY ...)
      - puste wiersze
      - powtórzone wiersze nagłówków kolumn
    
    Uwaga: elementy ZNORMALIZOWANE mogą mieć pusty 'Nr rysunku' – wtedy rekord nadal jest zwracany.
    
    Yields:
        Dict z kluczami: Nr rysunku, Nazwa, Opis, Ilość całkowita, Typ, Materiał, Dostawca, ...
    """
    # Szybsze podejście: czytaj wszystko do listy i natychmiast zamknij plik
    # To eliminuje problem z wolnym dostępem do komórek przy uszkodzonym formatowaniu
    
    results = []
    wb = None
    load_method = None
    
    try:
        # Próba załadowania workbooka - WIELOKROTNY FALLBACK
        print(f"📊 [iter_zbiorczy] Ładowanie {excel_path.name}...")
        
        # Próba 1: data_only=True (SZYBKIE - pełny random access do komórek)
        # UWAGA: NIE używać read_only=True! W trybie read_only ws[r] jest O(n²)!
        try:
            wb = openpyxl.load_workbook(excel_path, data_only=True)
            load_method = "data_only=True"
            print(f"✅ [iter_zbiorczy] Załadowano: {load_method}")
        except Exception as e1:
            print(f"⚠️  [iter_zbiorczy] Próba 1 nieudana: {type(e1).__name__}")
            
            # Próba 2: domyślne parametry (ostatnia deska ratunku)
            try:
                wb = openpyxl.load_workbook(excel_path)
                load_method = "domyślne parametry"
                print(f"✅ [iter_zbiorczy] Załadowano: {load_method}")
            except Exception as e2:
                print(f"❌ [iter_zbiorczy] Wszystkie próby nieudane")
                print(f"   Błąd końcowy: {type(e2).__name__}: {str(e2)[:200]}")
                raise Exception(
                    f"Nie udało się otworzyć pliku Excel żadną metodą.\n"
                    f"Ostatni błąd: {type(e2).__name__}: {str(e2)[:200]}\n\n"
                    f"MOŻLIWE ROZWIĄZANIE:\n"
                    f"Plik może być uszkodzony lub zawierać niezgodne formatowanie.\n"
                    f"Spróbuj otworzyć plik w Microsoft Excel i zapisać ponownie."
                ) from e2
        
        if wb is None:
            raise Exception("Nie udało się otworzyć pliku Excel")
        
        # Znajdź arkusz ZBIORCZY
        if "ZBIORCZY" in wb.sheetnames:
            ws = wb["ZBIORCZY"]
        else:
            # Fallback - pierwszy arkusz
            ws = wb[wb.sheetnames[0]]
        
        print(f"📄 [iter_zbiorczy] Arkusz: {ws.title}, wierszy: {ws.max_row}")
        
        header_row = None
        colmap = {}
        
        def looks_like_header(row_vals):
            """Wykryj czy wiersz to nagłówek kolumn"""
            return (
                "Nr rysunku" in row_vals and
                "Nazwa" in row_vals and
                any(k in row_vals for k in (
                    "Ilość całkowita", "Ilość", "Ilość (BOM)", 
                    "Ilość BOM", "Ilość (zam.)", "Ilość zam."
                ))
            )
        
        max_r = ws.max_row or 0
        
        # CZYTAJ WSZYSTKO DO PAMIĘCI (szybkie)
        print(f"🔍 [iter_zbiorczy] Rozpoczynam pętlę przez {max_r} wierszy...")
        for r in range(1, max_r + 1):
            # Progress co 50 wierszy
            if r % 50 == 0:
                print(f"  📊 Wiersz: {r}/{max_r}, rekordów: {len(results)}")
            
            try:
                # Normalizuj wartości w wierszu
                row = [norm(c.value) for c in ws[r]]
                
                # Wykryj sekcję (ELEMENTY ..., PEŁNA ...)
                if row and row[0] and (
                    row[0].upper().startswith("ELEMENTY") or 
                    row[0].upper().startswith("PEŁNA")
                ):
                    # Reset nagłówka dla nowej sekcji
                    header_row = None
                    colmap = {}
                    continue
                
                # Wykryj nagłówek kolumn
                if looks_like_header(row):
                    header_row = r
                    colmap = {v: i + 1 for i, v in enumerate(row) if v}
                    
                    # Aliasy nagłówków ilości (różne wersje Excela)
                    if "Ilość" not in colmap:
                        for _k in ("Ilość (BOM)", "Ilość BOM", "Ilość całkowita"):
                            if _k in colmap:
                                colmap["Ilość"] = colmap[_k]
                                break
                    
                    # Dodatkowo: fallback dla różnych wariantów
                    if "Ilość (BOM)" not in colmap and "Ilość" in colmap:
                        colmap["Ilość (BOM)"] = colmap["Ilość"]
                    
                    # Aliasy dla kolumny modułu (Katalog w BOM, Moduł w eksporcie RM_BAZA)
                    if "Katalog" not in colmap and "Moduł" in colmap:
                        colmap["Katalog"] = colmap["Moduł"]
                    
                    # Aliasy dla kolumny Ilość (zam.) (różne warianty)
                    if "Ilość (zam.)" not in colmap:
                        for _k in ("Ilość zam.", "Ilość zamówiona", "Ilość zamówionych"):
                            if _k in colmap:
                                colmap["Ilość (zam.)"] = colmap[_k]
                                break
                    
                    continue
                
                # Jeśli nie mamy jeszcze nagłówka - pomiń
                if not header_row:
                    continue
                
                # Pomiń całkowicie puste wiersze
                if all(
                    (c is None or str(c).strip() == "") 
                    for c in [ws.cell(r, c).value for c in range(1, 10)]
                ):
                    continue
                
                # Funkcja pomocnicza - pobierz wartość z kolumny
                def get(colname):
                    c = colmap.get(colname)
                    return ws.cell(r, c).value if c else None
                
                # Buduj rekord
                rec = {
                    "Nr rysunku": norm(get("Nr rysunku")),
                    "Nazwa": norm(get("Nazwa")),
                    "Opis": norm(get("Opis")),
                    "Ilość całkowita": norm(
                        get("Ilość całkowita") if "Ilość całkowita" in colmap else get("Ilość")
                    ),
                    "Ilość (zam.)": norm(get("Ilość (zam.)")) if "Ilość (zam.)" in colmap else None,
                    "Typ": norm(get("Typ")),
                    "Materiał": norm(get("Materiał")),
                    "Dostawca": norm(get("Dostawca")),
                    "Pliki 3D": norm(get("Pliki 3D")),
                    "Katalog": norm(get("Katalog")),
                    "Status": norm(get("Status")),
                    "Uwagi": norm(get("Uwagi")),
                }
                
                # Odrzuć powtórzone nagłówki (czasem przy błędnych merge)
                if looks_like_header(list(rec.values())):
                    continue
                
                # Rekord musi mieć przynajmniej nazwę lub numer
                if not rec["Nr rysunku"] and not rec["Nazwa"]:
                    continue
                
                # Dodaj do listy wyników
                results.append(rec)
                
            except Exception as row_err:
                print(f"⚠️  [iter_zbiorczy] Błąd w wierszu {r}: {row_err}")
                continue
        
        print(f"✅ [iter_zbiorczy] Wczytano {len(results)} rekordów")
    
    finally:
        # ZAWSZE zamknij workbook
        if wb is not None:
            try:
                wb.close()
                print(f"📕 [iter_zbiorczy] Workbook zamknięty")
            except Exception as close_err:
                print(f"⚠️  [iter_zbiorczy] Błąd zamykania: {close_err}")
    
    # Zwróć jako generator (dla kompatybilności wstecznej)
    for rec in results:
        yield rec


def excel_import_material_thickness(
    con,  # sqlite3.Connection
    project_id: int,
    excel_path: Path
) -> Tuple[int, int]:
    """
    Importuje Materiał (tekst) i grubość z LOGISTYKA_OUT.xlsx (arkusz ZBIORCZY).
    
    Zasady:
      - materiał: ustawiamy mat_effective_text tylko jeśli pusty w DB i wartość w Excelu niepusta
      - grubość: ustawiamy thickness_mm + thickness_src='CSV' tylko jeśli thickness_src != 'USER'
                 i da się wyciągnąć z materiału (grX,XXmm)
      - Dopasowanie:
          A) jeśli wiersz ma 'Nr rysunku' → po Nr rysunku (po norm)
          B) jeśli 'Nr rysunku' puste (ZNORMALIZOWANE) → po Nazwa (+ opcjonalnie Opis jeśli istnieje w DB)
    
    Args:
        con: Połączenie SQLite z bazą projektu
        project_id: ID projektu (w v10 może być zawsze z project_con, więc opcjonalne)
        excel_path: Ścieżka do LOGISTYKA_OUT.xlsx
    
    Returns:
        (upd_mat, upd_thk) - liczba zaktualizowanych rekordów
    """
    # Mapy z Excela
    by_dn = {}           # drawing_no_norm -> material_text
    by_name_desc = {}    # (name_norm, desc_norm) -> material_text (dla wierszy bez Nr rysunku)
    by_name = {}         # fallback: name_norm -> material_text
    
    # KROK 1: Buduj mapy z Excela
    for rec in iter_zbiorczy_data_rows(excel_path):
        dn = norm(rec.get("Nr rysunku"))
        name = norm(rec.get("Nazwa"))
        desc = norm(rec.get("Opis"))
        mt = norm(rec.get("Materiał"))
        
        if not mt:
            continue
        
        if dn:
            # Ma numer rysunku
            by_dn.setdefault(dn, mt)
        elif name:
            # Brak numeru (ZNORMALIZOWANE) - użyj nazwa+opis
            by_name_desc.setdefault((name, desc), mt)
            # Fallback: jeśli w Excelu brak opisu albo w DB opis będzie NULL
            by_name.setdefault(name, mt)
    
    if not by_dn and not by_name_desc and not by_name:
        # Brak danych do importu
        print("⚠️  Brak danych z materiałem w Excelu!")
        return (0, 0)
    
    print(f"📊 Mapy z Excela:")
    print(f"   by_dn (po nr rysunku): {len(by_dn)} wpisów")
    print(f"   by_name_desc (po nazwa+opis): {len(by_name_desc)} wpisów")
    print(f"   by_name (po nazwie): {len(by_name)} wpisów")
    
    upd_mat = 0
    upd_thk = 0
    matched = 0  # Ile dopasowań
    
    # KROK 2: Pobierz items z DB
    # V10: używamy work_* i src_* (COALESCE)
    rows = con.execute(
        """
        SELECT id,
               COALESCE(NULLIF(work_drawing_no, ''), src_drawing_no) AS drawing_no,
               COALESCE(NULLIF(work_name, ''), src_name) AS name,
               COALESCE(NULLIF(work_desc, ''), src_desc) AS descr,
               mat_effective_text,
               thickness_src
        FROM items
        """,
    ).fetchall()
    
    # KROK 3: Dopasuj i aktualizuj
    for item_id, drawing_no, name, descr, mat_effective, thickness_src in rows:
        key_dn = norm(drawing_no)
        key_name = norm(name)
        
        # Znajdź materiał z Excela
        mt = None
        if key_dn and key_dn in by_dn:
            # Dopasowanie po nr rysunku
            mt = by_dn[key_dn]
        elif (not key_dn) and key_name:
            # Dopasowanie po nazwa+opis (ZNORMALIZOWANE)
            key_desc = norm(descr)
            mt = by_name_desc.get((key_name, key_desc))
            if mt is None:
                # Fallback: po samej nazwie
                mt = by_name.get(key_name)
        
        if not mt:
            # Brak dopasowania
            continue
        
        matched += 1
        
        # AKTUALIZACJA MATERIAŁU
        # V10: Nadpisz mat_effective_text TYLKO jeśli puste
        if not mat_effective or mat_effective.strip() == "":
            con.execute(
                "UPDATE items SET mat_effective_text = ?, updated_at = datetime('now') WHERE id = ?",
                (mt, item_id)
            )
            upd_mat += 1
        
        # AKTUALIZACJA GRUBOŚCI
        # Wyciągnij grubość z materiału (regex "grX,XXmm")
        th = parse_thickness_mm(mt)
        if th is not None and str(thickness_src or "").upper() != "USER":
            con.execute(
                "UPDATE items SET thickness_mm = ?, thickness_src = 'CSV', updated_at = datetime('now') WHERE id = ?",
                (th, item_id)
            )
            upd_thk += 1
    
    print(f"📊 Podsumowanie importu:")
    print(f"   Items w DB: {len(rows)}")
    print(f"   Dopasowań: {matched}")
    print(f"   Zaktualizowano materiał: {upd_mat}")
    print(f"   Zaktualizowano grubość: {upd_thk}")
    
    return upd_mat, upd_thk
