#!/usr/bin/env python3
"""
Transformacja rm_manager.py: zamiana surowych sqlite3.connect na _open_rm_connection.

Reguly:
1. sqlite3.connect(xxx, timeout=N) → _open_rm_connection(xxx)
   - dla dowolnej zmiennej: con, pcon, con_master, con_peek, con_debug
   - dla dowolnego timeout: 5.0, 10.0 lub brak
2. Usun nastepna linia jesli to `XXX.row_factory = sqlite3.Row` (juz ustawione w helperze)
3. NIE zamieniaj linii z `uri=True` (specjalny tryb read-only)
4. NIE zamieniaj linii z `isolation_level` (uzywane w RMDatabaseManager)

Raport: wyswietla co zamienil i co pominol.
"""

import re
import sys

INPUT = "/workspaces/BOM/rm_manager.py"
OUTPUT = "/workspaces/BOM/rm_manager.py"

with open(INPUT, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Pattern: <var> = sqlite3.connect(<path_expr>, timeout=<N>)
# Also: <var> = sqlite3.connect(<path_expr>)  (no timeout)
# Skip: lines with uri=True, isolation_level
CONNECT_RE = re.compile(
    r'^(\s*)'                          # indent
    r'(\w+)'                           # variable name
    r'\s*=\s*sqlite3\.connect\('
    r'([^,)]+)'                        # db path expression (first arg)
    r'(?:,\s*timeout\s*=\s*[\d.]+)?'   # optional timeout
    r'\s*\)\s*'                        # close paren
    r'(#.*)?$'                         # optional comment
)

SKIP_PATTERNS = ['uri=True', 'isolation_level', 'check_same_thread']

ROW_FACTORY_RE = re.compile(
    r'^\s*(\w+)\.row_factory\s*=\s*sqlite3\.Row\s*$'
)

new_lines = []
replaced = 0
skipped = 0
row_factory_removed = 0
skip_row_factory_for = None  # var name whose row_factory to remove

i = 0
while i < len(lines):
    line = lines[i]
    
    # Check if we should remove row_factory line
    if skip_row_factory_for:
        m_rf = ROW_FACTORY_RE.match(line)
        if m_rf and m_rf.group(1) == skip_row_factory_for:
            print(f"  🗑️  Linia {i+1}: usunięto {skip_row_factory_for}.row_factory = sqlite3.Row")
            row_factory_removed += 1
            skip_row_factory_for = None
            i += 1
            continue
        # Also handle blank line + row_factory (some functions have empty line between)
        if line.strip() == '':
            # Peek ahead - if next line is row_factory, skip both? No, keep blank line, 
            # only remove row_factory
            pass
        skip_row_factory_for = None
    
    # Check for sqlite3.connect pattern
    if 'sqlite3.connect(' in line:
        # Skip special patterns
        if any(skip in line for skip in SKIP_PATTERNS):
            print(f"  ⏭️  Linia {i+1}: POMINIĘTO (specjalny tryb): {line.rstrip()}")
            skipped += 1
            new_lines.append(line)
            i += 1
            continue
        
        m = CONNECT_RE.match(line)
        if m:
            indent = m.group(1)
            var = m.group(2)
            db_path = m.group(3).strip()
            comment = m.group(4) or ''
            
            # Build replacement
            new_line = f"{indent}{var} = _open_rm_connection({db_path})"
            if comment:
                new_line += f"  {comment}"
            new_line += "\n"
            
            print(f"  ✅ Linia {i+1}: {var} = sqlite3.connect({db_path}) → _open_rm_connection({db_path})")
            new_lines.append(new_line)
            replaced += 1
            skip_row_factory_for = var
            i += 1
            continue
        else:
            # sqlite3.connect found but pattern didn't match - log it
            print(f"  ⚠️  Linia {i+1}: sqlite3.connect znaleziony ale pattern nie pasuje: {line.rstrip()}")
            skipped += 1
    
    new_lines.append(line)
    i += 1

# Write output
with open(OUTPUT, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print(f"\n{'='*60}")
print(f"PODSUMOWANIE:")
print(f"  Zamieniono sqlite3.connect → _open_rm_connection: {replaced}")
print(f"  Usunięto zbędne row_factory: {row_factory_removed}")
print(f"  Pominięto (specjalne): {skipped}")
print(f"{'='*60}")
