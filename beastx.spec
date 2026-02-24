# beastx.spec
# PyInstaller spec file for Beast X
# Run with: pyinstaller beastx.spec

import sys
from PyInstaller.building.build_main import Analysis, PYZ, EXE

block_cipher = None

a = Analysis(
    ['beastx_app.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'customtkinter',
        'hid',
        # CustomTkinter loads theme files dynamically — include them
        'customtkinter.assets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim unused stdlib modules to keep exe smaller
        'unittest', 'email', 'html', 'http', 'urllib',
        'xml', 'xmlrpc', 'pydoc', 'doctest', 'difflib',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='BeastX',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # compress with UPX if available (smaller exe)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # no terminal window — GUI only
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows: embed an icon if you have one
    # icon='beastx.ico',
)
