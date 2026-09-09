# -*- mode: python ; coding: utf-8 -*-
#
# Build RM_BAZA. UZUPELNIONY O MODULY LADOWANE LENIWIE (07.09.2026).
#
# ⚠️ RM_BAZA importuje CALA integracje z Subiektem WEWNATRZ FUNKCJI
# ("import subiekt_panel" w metodzie, nie na gorze pliku) — swiadomie, zeby
# start aplikacji nie placil za moduly, ktorych wiekszosc userow nie otworzy.
# PyInstaller analizuje importy STATYCZNIE, wiec takiego modulu NIE WIDZI
# i nie pakuje go do .exe. Efekt: build konczy sie sukcesem, aplikacja startuje,
# a dopiero klikniecie "SUBIEKT" wywala ModuleNotFoundError — u usera, nie
# u budujacego (bo ten ma obok pliki .py).
#
# Lista ponizej to DOMKNIECIE zaleznosci: 20 modulow importowanych leniwie
# przez RM_BAZA + wszystko, co one same importuja. Wyliczone przez analize AST,
# nie recznie — przy dokladaniu nowego okna trzeba ja odswiezyc.

hiddenimports_lokalne = [
    "client_version",   # bramka wersji + heartbeat sesji (import top-level, ale dla pewnosci)
    # ── integracja z Subiektem (okna otwierane z panelu SUBIEKT) ──
    "subiekt_panel",
    "subiekt_stany",
    "subiekt_zamowienia",
    "subiekt_magazyn_gui",
    "subiekt_dokumenty_gui",
    "subiekt_dostawcy_gui",
    "subiekt_asortyment_gui",
    "subiekt_scalanie_gui",
    "subiekt_polaczenie_gui",
    "subiekt_pozycja_gui",
    "subiekt_projekt",
    "subiekt_wyslij_zd",
    # ── warstwa danych Subiekta (uzywana przez powyzsze) ──
    "subiekt_bridge",
    "subiekt_konfig",
    "subiekt_asortyment",
    "subiekt_dostawcy",
    "subiekt_mapowania",
    "subiekt_podobne",
    "subiekt_scalanie",
    # ── KSeF ──
    "ksef_api_client",
    "ksef_archiwum",
    "ksef_invoice_parser",
    # ── reszta lokalnych, tez ladowana leniwie ──
    "backup_manager",
    "database_manager",
    "dwf_thumb",
    "import_bom",
    "lock_manager_v2",
    "material_calculator",
    "project_manager",
    "rm_kreciolek",
    "rm_manager",
    "rm_panel_plikow",
    "rm_sync_agent",
    "rmpak_calculator",
]

# Zewnetrzne, ktore wchodza tylko przez moduly leniwe — PyInstaller trafia
# na nie dopiero po dodaniu tamtych, ale wymieniamy je wprost, bo czesc
# (tksheet, win32com) ma importy dynamiczne i bywa gubiona.
hiddenimports_zewnetrzne = [
    "tksheet",
    "openpyxl",
    "PIL", "PIL.Image", "PIL.ImageTk",
    "requests",
    "win32com", "win32com.client", "pythoncom", "pywintypes",
]

a = Analysis(
    ['RM_BAZA_v15_MAG_STATS_ORG.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports_lokalne + hiddenimports_zewnetrzne,
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
    name='RM_BAZA_v15_MAG_STATS_ORG',
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
