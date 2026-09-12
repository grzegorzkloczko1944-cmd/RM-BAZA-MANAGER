# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['RM_KOD.py'],
    pathex=[],
    binaries=[],
    datas=[('RM_KOD.ico', '.')],
    # ⚠️ hiddenimports, NIE datas.
    #
    # `rm_manager` i `lock_manager_serwer` importują `rm_klient` i siebie
    # nawzajem WEWNĄTRZ FUNKCJI (leniwie), a takiego importu PyInstaller nie
    # widzi — .exe wstawał i padał dopiero przy pierwszym sięgnięciu do bazy.
    # Ten sam błąd co przy module Subiekta w RM_BAZA.
    #
    # `lock_manager_v2` zostaje mimo przejścia na blokady serwerowe: jest
    # awaryjnym powrotem do plików .lock, a waży tyle co nic.
    hiddenimports=[
        'rm_manager',
        'rm_klient',
        'lock_manager_serwer',
        'lock_manager_v2',
        'rm_serwer_operacje',
    ],
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
    [],
    exclude_binaries=True,
    name='RM_KOD',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['RM_KOD.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RM_KOD',
)
