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
    # edytor kartotek + historia — importowane leniwie z RM_BAZA i subiekt_panel;
    # dotad wchodzily do .exe TYLKO posrednio (przez subiekt_projekt), wiec
    # usuniecie tamtego importu wycielo by je po cichu.
    'subiekt_edytor_gui', 'subiekt_historia',
    # dopasowanie znormalizowanych do kartotek (okno z menu SUBIEKT)
    'subiekt_znorm_gui', 'subiekt_znorm_dopasowanie',
    # warstwa danych Subiekta
    'subiekt_bridge', 'subiekt_konfig', 'subiekt_asortyment', 'subiekt_dostawcy',
    'subiekt_mapowania', 'subiekt_podobne', 'subiekt_scalanie',
    # KSeF
    'ksef_api_client', 'ksef_archiwum', 'ksef_invoice_parser',
    # reszta lokalnych, tez leniwa
    'material_calculator', 'rm_kreciolek', 'rm_manager', 'rm_panel_plikow',
    'rm_sync_agent', 'rmpak_calculator',
    # bramka wersji + heartbeat sesji (import top-level; wpis dla pewnosci)
    'client_version',
    # zewnetrzne wchodzace tylko przez powyzsze (importy dynamiczne)
    'requests', 'win32com', 'win32com.client', 'pythoncom', 'pywintypes',
]

# Zrodla modulow leniwych obok .exe — jak pozostale w datas wyzej.
datas += [(f'{m}.py', '.') for m in (
    'subiekt_panel', 'subiekt_stany', 'subiekt_zamowienia', 'subiekt_magazyn_gui',
    'subiekt_dokumenty_gui', 'subiekt_dostawcy_gui', 'subiekt_asortyment_gui',
    'subiekt_scalanie_gui', 'subiekt_polaczenie_gui', 'subiekt_pozycja_gui',
    'subiekt_projekt', 'subiekt_wyslij_zd', 'subiekt_bridge', 'subiekt_konfig',
    'subiekt_edytor_gui', 'subiekt_historia',
    'subiekt_znorm_gui', 'subiekt_znorm_dopasowanie',
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

# ── PUBLIKACJA NA SERWER ─────────────────────────────────────────────────────
# Gotowy .exe leci od razu do Y:/RMPAK_CLIENT — miejsca, z ktorego aktualizuje
# RM_Tray_Organizer i z ktorym bramka wersji (client_version.py) porownuje
# kazdego klienta przy starcie. UWAGA: od tej kopii kazdy user ze starym .exe
# dostanie blokade przy nastepnym uruchomieniu — to jest zamierzone.
#
# copy2, nie copy: bramka porownuje rozmiar+mtime, wiec mtime musi przetrwac.
# Poprzednia wersja z serwera laduje w "backup dd-mm-rrrr" (jak dotychczas
# recznie). Blad publikacji NIE psuje buildu — tylko glosny komunikat.
import shutil as _shutil
from datetime import datetime as _dt
_SERVER_DIR = r"Y:\RMPAK_CLIENT"
_src = _os.path.join(_os.path.abspath(DISTPATH), "RM_BAZA_v15_MAG.exe")
_dst = _os.path.join(_SERVER_DIR, "RM_BAZA_v15_MAG.exe")
try:
    if not _os.path.isdir(_SERVER_DIR):
        raise FileNotFoundError(f"brak katalogu serwera {_SERVER_DIR} (dysk Y: niezmapowany?)")
    if _os.path.exists(_dst):
        _bak = _os.path.join(_SERVER_DIR, "backup " + _dt.now().strftime("%d-%m-%Y"))
        _os.makedirs(_bak, exist_ok=True)
        _shutil.move(_dst, _os.path.join(_bak, "RM_BAZA_v15_MAG.exe"))
        print(f"(spec) Poprzednia wersja z serwera -> {_bak}")
    _shutil.copy2(_src, _dst)
    _s, _d = _os.stat(_src), _os.stat(_dst)
    assert _s.st_size == _d.st_size and abs(_s.st_mtime - _d.st_mtime) < 2, "kopia rozni sie od zrodla"
    print(f"(spec) OPUBLIKOWANO: {_dst}  ({_d.st_size} B, {_dt.fromtimestamp(_d.st_mtime):%Y-%m-%d %H:%M:%S})")
except Exception as _e:
    print("=" * 70)
    print(f"(spec) !!! PUBLIKACJA NA SERWER NIE POWIODLA SIE: {_e}")
    print(f"(spec) !!! Skopiuj recznie: {_src} -> {_dst}")
    print("=" * 70)
