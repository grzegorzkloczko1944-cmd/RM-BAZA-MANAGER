# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('rm_manager.py', '.'), ('rm_optimizer.py', '.'), ('lock_manager_v2.py', '.'), ('backup_manager.py', '.'), ('rm_ai_optimizer.py', '.'), ('db.py', '.'), ('stats_status.py', '.'), ('stats_project_summary.py', '.'), ('project_manager.py', '.'), ('ai_rules.txt', '.'), ('wat.jpg', '.'), ('rm_manager_icon.ico', '.')]
binaries = []
hiddenimports = ['plotly', 'PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL.ImageDraw', 'PIL.ImageFilter', 'ortools', 'ortools.sat', 'ortools.sat.python', 'ortools.sat.python.cp_model', 'psutil', 'anthropic', 'rm_ai_optimizer', 'matplotlib', 'matplotlib.backends.backend_agg', 'db', 'stats_status', 'stats_project_summary', 'project_manager', 'openpyxl', 'openpyxl.styles', 'openpyxl.cell._writer']

# ⚠️ Rozmowa z RM_SERWER — BEZ TEGO .exe PADA przy pierwszym sięgnięciu do bazy.
#
# `rm_klient` jest importowany WYŁĄCZNIE wewnątrz funkcji (rm_manager.py:104,
# rm_manager_gui.py:3161 i 10197), a `lock_manager_serwer` warunkowo — takich
# importów PyInstaller nie widzi. Ze źródeł wszystko działa, .exe wstaje
# i dopiero potem nie ma czym zapytać serwera. Ten sam błąd co kiedyś
# z modułem Subiekta w RM_BAZA.
hiddenimports += ['rm_klient', 'lock_manager_serwer', 'lock_manager_v2',
                  'rm_serwer_operacje',
                  # Logowanie do udzialu kontem technicznym — bez tego user
                  # bez praw sieciowych dostaje okno o poswiadczenia.
                  'udzial_serwera']
tmp_ret = collect_all('anthropic')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('plotly')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('ortools')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('matplotlib')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['rm_manager_gui.py'],
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
    name='RM_MANAGER',
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
    icon=['rm_manager_icon.ico'],
)

# Po zbudowaniu: wystaw .exe na udział i otwórz folder dist.
# (kod .spec wykonuje się jako Python; obiekt EXE powyżej buduje plik,
#  więc tutaj build jest już gotowy)
import os as _os
import shutil as _shutil

#: Skąd stacje biorą nową wersję programu.
WYSTAWKA = r"Y:\RMPAK_CLIENT"

_zrodlo = _os.path.join(_os.path.abspath(DISTPATH), "RM_MANAGER.exe")
_cel = _os.path.join(WYSTAWKA, "RM_MANAGER.exe")
try:
    # Kopiujemy OBOK, potem podmieniamy: `copy2` prosto na cel zeruje plik
    # i dopiero streamuje zawartość (169 MB przez sieć), więc zerwanie SMB
    # w trakcie zostawiłoby na udziale uszkodzony .exe dla wszystkich.
    # `os.replace` jest atomowe w obrębie jednego wolumenu.
    _tmp = _cel + ".nowy"
    _shutil.copy2(_zrodlo, _tmp)
    try:
        _os.replace(_tmp, _cel)
    except PermissionError:
        # ⚠️ Ktoś ma program OTWARTY — Windows trzyma .exe zablokowany.
        # Stara wersja zostaje (działa!), nowa czeka obok pod `.nowy`.
        # Podmiana to jedno przeciągnięcie, gdy user zamknie program.
        print(f"(spec) ⚠️  {_cel} jest UZYWANY — nie podmieniono.")
        print(f"(spec)     Nowa wersja czeka obok: {_tmp}")
        print( "(spec)     Podmien recznie, gdy nikt nie ma programu otwartego.")
    else:
        print(f"(spec) Wystawione na udzial: {_cel}")
except Exception as _e:
    # Brak Y: nie ma prawa wywalic budowania — .exe w dist jest gotowy.
    print(f"(spec) NIE wystawiono na {WYSTAWKA}: {_e}")
    print( "(spec) Skopiuj recznie z dist, gdy udzial wroci.")

try:
    _os.startfile(_os.path.join(_os.path.abspath(DISTPATH), ''))
except Exception as _e:
    print(f"(spec) Nie udalo sie otworzyc folderu dist: {_e}")
