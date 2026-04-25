#!/usr/bin/env python3
"""Naprawa zepsutych emoji w rm_manager_gui.py"""

# Odczytaj plik
with open('rm_manager_gui.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Zamień uszkodzone znaki
content = content.replace('text="� Kopiuj"', 'text="📋 Kopiuj projekt"')
content = content.replace('text="�📊 Segmented Bar"', 'text="📊 Segmented Bar"')

# Zapisz naprawiony plik
with open('rm_manager_gui.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Naprawiono emoji w rm_manager_gui.py")
