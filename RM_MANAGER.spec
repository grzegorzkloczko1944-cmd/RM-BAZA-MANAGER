# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('rm_manager.py', '.'), ('rm_optimizer.py', '.'), ('lock_manager_v2.py', '.'), ('backup_manager.py', '.'), ('rm_ai_optimizer.py', '.'), ('ai_rules.txt', '.'), ('wat.jpg', '.'), ('rm_manager_icon.ico', '.')]
binaries = []
hiddenimports = ['plotly', 'PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL.ImageDraw', 'PIL.ImageFilter', 'ortools', 'ortools.sat', 'ortools.sat.python', 'ortools.sat.python.cp_model', 'psutil', 'anthropic', 'rm_ai_optimizer', 'matplotlib', 'matplotlib.backends.backend_agg']
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
