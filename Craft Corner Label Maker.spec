# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build spec for Craft Corner Label Maker.
#
# Hidden imports below are REQUIRED per §12 — keyring.backends.Windows,
# win32ctypes.core, and openpyxl.cell._writer all fail ONLY in the frozen
# build, never in the dev environment, so they are easy to miss until a
# release ships broken. Test the built EXE, not just `python app.py`.

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('data', 'data'),                       # regions + themes + pack_composition
        ('report/templates', 'report/templates'),
        ('server/static', 'server/static'),     # built web UI — without this the app serves nothing
    ],
    hiddenimports=[
        'keyring.backends.Windows',
        'win32ctypes.core',
        'openpyxl.cell._writer',
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan.on',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CraftCornerLabelMaker',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CraftCornerLabelMaker',
)
