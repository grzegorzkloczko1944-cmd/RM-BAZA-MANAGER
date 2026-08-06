# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('rm_baza_icon.ico', '.'), ('database_manager.py', '.'), ('lock_manager_v2.py', '.'), ('import_bom.py', '.'), ('project_manager.py', '.'), ('backup_manager.py', '.')]
binaries = []
hiddenimports = ['tksheet', 'openpyxl', 'openpyxl.cell', 'openpyxl.cell.cell', 'openpyxl.styles', 'openpyxl.workbook', 'openpyxl.worksheet', 'openpyxl.utils', 'reportlab', 'reportlab.lib', 'reportlab.lib.pagesizes', 'reportlab.lib.colors', 'reportlab.lib.units', 'reportlab.lib.styles', 'reportlab.lib.enums', 'reportlab.platypus', 'reportlab.pdfbase', 'reportlab.pdfbase.pdfmetrics', 'reportlab.pdfbase.ttfonts', 'pystray', 'PIL', 'PIL.Image', 'PIL.ImageDraw']
tmp_ret = collect_all('reportlab')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tksheet')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pystray')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['RM_BAZA_v15_MAG_STATS_ORG.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RM_BAZA_v15_MAG',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['rm_baza_icon.ico'],
)

# Po zbudowaniu EXE otwórz folder dist w Eksploratorze Windows.
# (kod .spec wykonuje się jako Python; obiekt EXE powyżej buduje plik,
#  więc tutaj build jest już gotowy)
import os as _os
try:
    _os.startfile(_os.path.join(_os.path.abspath(DISTPATH), ''))
except Exception as _e:
    print(f"(spec) Nie udalo sie otworzyc folderu dist: {_e}")
