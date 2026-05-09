# -*- mode: python ; coding: utf-8 -*-

# Dedykowany build dla RM_Tray_Organizer:
# aplikacja używa wyłącznie QtCore/QtGui/QtWidgets,
# więc wykluczamy ciężkie i opcjonalne moduły Qt generujące warningi.

qt_excludes = [
    'PyQt5.Qt3DAnimation',
    'PyQt5.Qt3DCore',
    'PyQt5.Qt3DExtras',
    'PyQt5.Qt3DInput',
    'PyQt5.Qt3DLogic',
    'PyQt5.Qt3DRender',
    'PyQt5.QtMultimedia',
    'PyQt5.QtMultimediaWidgets',
    'PyQt5.QtQml',
    'PyQt5.QtQuick',
    'PyQt5.QtQuickWidgets',
    'PyQt5.QtSql',
    'PyQt5.QtWebChannel',
    'PyQt5.QtWebEngine',
    'PyQt5.QtWebEngineCore',
    'PyQt5.QtWebEngineWidgets',
    'PyQt5.QtWebSockets',
    'PyQt5.QtWebView',
]

a = Analysis(
    ['RM_Tray_Organizer.pyw'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=qt_excludes,
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
    name='RM_Tray_Organizer',
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
)
