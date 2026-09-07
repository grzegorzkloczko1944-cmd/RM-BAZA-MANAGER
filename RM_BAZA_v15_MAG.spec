# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('rm_baza_icon.ico', '.'), ('database_manager.py', '.'), ('lock_manager_v2.py', '.'), ('import_bom.py', '.'), ('project_manager.py', '.'), ('backup_manager.py', '.'), ('dwf_thumb.py', '.')]
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

# ⚠️ MODULY LADOWANE LENIWIE — PyInstaller ich NIE WIDZI.
#
# RM_BAZA importuje cala integracje z Subiektem wewnatrz funkcji
# ("import subiekt_panel" w metodzie, nie na gorze pliku) — swiadomie, zeby
# start nie placil za okna, ktorych wiekszosc userow nie otworzy. Analiza
# importow jest STATYCZNA, wiec bez tej listy zaden z tych modulow nie trafia
# do .exe: build konczy sie sukcesem, aplikacja startuje, a dopiero klikniecie
# "SUBIEKT" wywala ModuleNotFoundError — U USERA, nie u budujacego, bo ten ma
# obok pliki .py (znalezione 07.09.2026).
#
# Lista to DOMKNIECIE zaleznosci wyliczone z AST: moduly importowane leniwie
# przez RM_BAZA + wszystko, co one same importuja. Przy dokladaniu nowego okna
# TRZEBA ja odswiezyc, inaczej zniknie z .exe po cichu.
hiddenimports += [
    # integracja z Subiektem — okna z panelu SUBIEKT
    'subiekt_panel', 'subiekt_stany', 'subiekt_zamowienia', 'subiekt_magazyn_gui',
    'subiekt_dokumenty_gui', 'subiekt_dostawcy_gui', 'subiekt_asortyment_gui',
    'subiekt_scalanie_gui', 'subiekt_polaczenie_gui', 'subiekt_pozycja_gui',
    'subiekt_projekt', 'subiekt_wyslij_zd',
    # warstwa danych Subiekta
    'subiekt_bridge', 'subiekt_konfig', 'subiekt_asortyment', 'subiekt_dostawcy',
    'subiekt_mapowania', 'subiekt_podobne', 'subiekt_scalanie',
    # KSeF
    'ksef_api_client', 'ksef_archiwum', 'ksef_invoice_parser',
    # reszta lokalnych, tez leniwa
    'material_calculator', 'rm_kreciolek', 'rm_manager', 'rm_panel_plikow',
    'rm_sync_agent', 'rmpak_calculator',
    # zewnetrzne wchodzace tylko przez powyzsze (importy dynamiczne)
    'requests', 'win32com', 'win32com.client', 'pythoncom', 'pywintypes',
]

# Zrodla modulow leniwych obok .exe — jak pozostale w datas wyzej.
datas += [(f'{m}.py', '.') for m in (
    'subiekt_panel', 'subiekt_stany', 'subiekt_zamowienia', 'subiekt_magazyn_gui',
    'subiekt_dokumenty_gui', 'subiekt_dostawcy_gui', 'subiekt_asortyment_gui',
    'subiekt_scalanie_gui', 'subiekt_polaczenie_gui', 'subiekt_pozycja_gui',
    'subiekt_projekt', 'subiekt_wyslij_zd', 'subiekt_bridge', 'subiekt_konfig',
    'subiekt_asortyment', 'subiekt_dostawcy', 'subiekt_mapowania',
    'subiekt_podobne', 'subiekt_scalanie', 'rm_kreciolek',
)]


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
