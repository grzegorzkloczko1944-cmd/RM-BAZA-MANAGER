# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('rm_baza_icon.ico', '.'), ('diplodok.png', '.'), ('database_manager.py', '.'), ('lock_manager_v2.py', '.'), ('import_bom.py', '.'), ('project_manager.py', '.'), ('rm_klient.py', '.'), ('rm_serwer_operacje.py', '.'), ('backup_manager.py', '.'), ('dwf_thumb.py', '.')]
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
    # ⚠️ WARSTWA RM_SERWER — importowana LENIWIE (wewnatrz funkcji), wiec
    # analiza statyczna jej nie widzi. Bez tych wpisow .exe zbuduje sie bez
    # bledu i padnie U USERA przy pierwszym odczycie z bazy: master lezy na
    # serwerze i KAZDY odczyt idzie przez rm_klient.
    'rm_klient', 'rm_serwer_operacje', 'project_manager',
    'rmpak_calculator', 'material_calculator',

    # ⚠️ BLOKADY PROJEKTOW przez serwer (12.09.2026). RM_BAZA importuje
    # `lock_manager_baza_serwer` na gorze pliku, ale ten dziedziczy po
    # `lock_manager_serwer`, a wewnatrz siega po `rm_manager` — leniwie,
    # wiec analiza statyczna tego nie lapie. Bez tych wpisow .exe nie ma
    # czym zalozyc locka i padnie przy otwarciu pierwszego projektu.
    # `lock_manager_v2` zostaje jako awaryjny powrot do plikow .lock.
    'lock_manager_baza_serwer', 'lock_manager_serwer', 'lock_manager_v2',
    'rm_manager',

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
    'subiekt_dopasowanie_gui', 'subiekt_dopasowanie',
    # produkcja wlasna RMPAK (PW/RW) + okno zlozen projektu
    'subiekt_produkcja', 'subiekt_zlozenia_gui',
    # formularze dokumentow z Edytora kartotek (10-11.09.2026) — importowane
    # leniwie w subiekt_edytor_gui (przyciski RW/PW/ZD/ZK), wiec statyczna
    # analiza ich NIE WIDZI. subiekt_dokument_form to ich wspolny szkielet.
    'subiekt_dokument_form', 'subiekt_rw_gui', 'subiekt_pw_gui',
    'subiekt_zd_gui', 'subiekt_zk_gui',
    # okno wydania RW ze stanu + raport duplikatow kartotek
    'subiekt_wydanie_gui', 'subiekt_raport_duplikatow',
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
    'subiekt_dopasowanie_gui', 'subiekt_dopasowanie',
    'subiekt_produkcja', 'subiekt_zlozenia_gui',
    'subiekt_dokument_form', 'subiekt_rw_gui', 'subiekt_pw_gui',
    'subiekt_zd_gui', 'subiekt_zk_gui',
    'subiekt_wydanie_gui', 'subiekt_raport_duplikatow',
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

# ── PUBLIKACJA: KATALOG TESTOWY ──────────────────────────────────────────────
# Gotowy .exe leci do Y:\RMPAK_CLIENT\TESTY RM_BAZA, a NIE do Y:\RMPAK_CLIENT.
#
# DLACZEGO NIE NA PRODUKCJE (09-10.09.2026):
# Bramka wersji (client_version.py) porownuje .exe kazdego klienta z plikiem
# lezacym WPROST w Y:\RMPAK_CLIENT. Publikowanie tam po kazdym buildzie
# oznaczaloby, ze wszyscy userzy dostaja monit o aktualizacji po kazdej
# najdrobniejszej zmianie — i 127 MB do pobrania. Katalog testowy jest poza
# zasiegiem bramki, wiec buildy w toku nikogo nie ruszaja.
#
# WYDANIE NA PRODUKCJE JEST SWIADOMYM, RECZNYM KROKIEM:
#     copy /y "Y:\RMPAK_CLIENT\TESTY RM_BAZA\RM_BAZA_v15_MAG.exe" ^
#             "Y:\RMPAK_CLIENT\RM_BAZA_v15_MAG.exe"
# (kopiowac tak, zeby mtime przetrwal — bramka porownuje rozmiar+mtime;
#  Explorer i copy /y to robia, `type >` NIE).
#
# copy2, nie copy: mtime musi przetrwac takze tutaj, inaczej nie da sie
# poznac, ktory build lezy w TESTACH. Poprzedni plik nadpisujemy bez backupu
# — od backupow jest katalog produkcyjny. Blad publikacji NIE psuje buildu.
import shutil as _shutil
from datetime import datetime as _dt
#: ⚠️ WPROST NA PRODUKCJĘ (decyzja 12.09.2026).
#:
#: Wcześniej build lądował w `TESTY RM_BAZA`, żeby bramka wersji nie wołała
#: wszystkich do aktualizacji po każdej drobnej zmianie. Dziś jest odwrotnie:
#: stacje MUSZĄ dostać wersję odciętą od `Y:` — na starej program nie znajdzie
#: ani master.sqlite, ani projektów, bo katalogi na `Y:` są już nieaktywne.
#: Monit o aktualizacji jest tu POŻĄDANY, nie uciążliwy.
_SERVER_DIR = r"Y:\RMPAK_CLIENT"
_src = _os.path.join(_os.path.abspath(DISTPATH), "RM_BAZA_v15_MAG.exe")
_dst = _os.path.join(_SERVER_DIR, "RM_BAZA_v15_MAG.exe")
try:
    _os.makedirs(_SERVER_DIR, exist_ok=True)
    _shutil.copy2(_src, _dst)
    _s, _d = _os.stat(_src), _os.stat(_dst)
    assert _s.st_size == _d.st_size and abs(_s.st_mtime - _d.st_mtime) < 2, "kopia rozni sie od zrodla"
    print(f"(spec) WYSTAWIONE: {_dst}  ({_d.st_size} B, {_dt.fromtimestamp(_d.st_mtime):%Y-%m-%d %H:%M:%S})")
    print("(spec) Stacje dostana monit o aktualizacji przy nastepnym starcie.")
except Exception as _e:
    print("=" * 70)
    print(f"(spec) !!! WYSTAWIENIE NIE POWIODLO SIE: {_e}")
    print(f"(spec) !!! Skopiuj recznie: {_src} -> {_dst}")
    print("=" * 70)
