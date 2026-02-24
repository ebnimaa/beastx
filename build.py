#!/usr/bin/env python3
"""
Beast X — Build Script
=======================
Builds a standalone executable using PyInstaller.

Usage:
    python build.py

Output:
    dist/BeastX.exe       (Windows)
    dist/BeastX           (Linux)
    dist/BeastX.app       (macOS)
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

# ── Check dependencies ────────────────────────────────────────────────────────

def check(pkg):
    try:
        __import__(pkg.replace('-', '_'))
        return True
    except ImportError:
        return False

print("═" * 52)
print("  Beast X — Build")
print("═" * 52)

missing = []
for pkg in ['customtkinter', 'hid', 'PyInstaller']:
    mod = 'PyInstaller' if pkg == 'PyInstaller' else pkg
    if not check(mod):
        missing.append(pkg)

if missing:
    print(f"\n⚠  Missing packages: {', '.join(missing)}")
    print(f"   Run: pip install {' '.join(missing)}\n")
    sys.exit(1)

print("\n✓  Dependencies OK")

# ── Find customtkinter data path (must be bundled) ────────────────────────────

import customtkinter
ctk_path = Path(customtkinter.__file__).parent

# ── Run PyInstaller ───────────────────────────────────────────────────────────

print("✓  Building executable...")

cmd = [
    sys.executable, '-m', 'PyInstaller',
    '--noconfirm',
    '--onefile',                          # single .exe file
    '--windowed',                         # no console window
    '--name', 'BeastX',
    # Bundle customtkinter assets (themes, images)
    '--add-data', f'{ctk_path}{os.pathsep}customtkinter',
    # Hidden imports PyInstaller might miss
    '--hidden-import', 'hid',
    '--hidden-import', 'customtkinter',
    '--hidden-import', '_tkinter',
    # Exclude bloat
    '--exclude-module', 'unittest',
    '--exclude-module', 'email',
    '--exclude-module', 'http',
    '--exclude-module', 'urllib',
    '--exclude-module', 'xml',
    '--exclude-module', 'pydoc',
    # UPX compression if available
    '--upx-dir', shutil.which('upx') and str(Path(shutil.which('upx')).parent) or '.',
    'beastx_app.py',
]

result = subprocess.run(cmd, capture_output=False)

if result.returncode != 0:
    print("\n✗  Build failed. See output above.")
    sys.exit(1)

# ── Done ─────────────────────────────────────────────────────────────────────

dist = Path('dist')
exe_name = 'BeastX.exe' if sys.platform == 'win32' else 'BeastX'
exe_path = dist / exe_name

if exe_path.exists():
    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"\n{'═'*52}")
    print(f"  ✓  Built: {exe_path}  ({size_mb:.1f} MB)")
    print(f"{'═'*52}\n")

    if sys.platform == 'linux':
        print("Linux note:")
        print("  Users need this udev rule to use the mouse without sudo:")
        print("  echo 'SUBSYSTEM==\"hidraw\", ATTRS{idVendor}==\"36a7\",")
        print("         ATTRS{idProduct}==\"a887\", MODE=\"0666\"' \\")
        print("       | sudo tee /etc/udev/rules.d/99-beastx.rules")
        print("  sudo udevadm control --reload-rules && sudo udevadm trigger\n")
    elif sys.platform == 'win32':
        print("Windows note:")
        print("  The exe should work as-is on Windows 10/11.")
        print("  If Windows Defender flags it, add an exclusion for the exe.")
        print("  Distribute as a zip — SmartScreen may warn on first run,")
        print("  user just clicks 'More info → Run anyway'.\n")
    elif sys.platform == 'darwin':
        print("macOS note:")
        print("  Right-click → Open the first time (Gatekeeper bypass).")
        print("  Or: xattr -cr dist/BeastX.app\n")
else:
    print("\n✗  Exe not found after build — check PyInstaller output above.")
    sys.exit(1)
