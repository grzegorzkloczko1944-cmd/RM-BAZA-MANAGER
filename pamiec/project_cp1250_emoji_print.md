---
name: project_cp1250_emoji_print
description: print() z emoji wywala UnicodeEncodeError na konsoli cp1250 — fix przez reconfigure stdout na UTF-8 na starcie modułu
metadata: 
  node_type: memory
  type: project
  originSessionId: 82f2a873-9dc2-427e-b90e-cba22eee7c22
---

**Pułapka:** setki `print(...)` z emoji (✅⚠️🔧 itd.) w rm_manager_gui.py i rm_manager.py wywalają `UnicodeEncodeError: 'charmap' codec` gdy aplikacja jest uruchamiana z konsoli w kodowaniu cp1250 (domyślne na polskim Windows). Gdy taki print jest na TOP-LEVEL modułu (np. rm_manager_gui.py:99 "✅ Przeładowano moduł rm_manager"), moduł NIE zaimportuje się wcale — aplikacja nie startuje z konsoli.

**Fix (2026-07-19):** na SAMYM POCZĄTKU rm_manager_gui.py (po `import sys`, przed resztą importów) wymuszenie UTF-8:
```
for _stream in ('stdout','stderr'):
    try: getattr(sys,_stream).reconfigure(encoding='utf-8', errors='replace')
    except Exception: pass
```
try/except bo w trybie --noconsole (.exe windowed) sys.stdout może być None → AttributeError. Rozwiązuje globalnie wszystkie print z emoji, nie trzeba czyścić setek linii.

Wcześniej ta sama pułapka trafiła set_project_status w rm_manager.py — tam owinięto pojedynczy print w try (patrz [[project_stage_start_status_bug]]). Globalny reconfigure w GUI to lepsze, całościowe rozwiązanie.

**Trzecie wystąpienie (10.09.2026) — groźniejszy wariant: print W BLOKU `except`.**
`import_bom.find_assembly_tree_rows` miała `except Exception as e: print(f"⚠️ ...")` + `return []`.
Gdy print wywalał się na cp1250, `UnicodeEncodeError` **uciekał z funkcji zamiast `return []`** —
wołacz dostawał crash zamiast łagodnego „nie da się odczytać". Objaw u usera: „Z pliku"
w edytorze kartotek nie importuje. Kod modułu jest wołany z `.exe` (`console=False`),
gdzie print i tak nie ma gdzie trafić.

**Reguła:** print diagnostyczny **wewnątrz `except`** ZAWSZE w `try/except: pass` — inaczej
diagnostyka wywraca obsługę błędu, którą miała opisać. Globalny `reconfigure` z GUI
nie chroni modułów importowanych osobno ani `.exe` bez konsoli.
