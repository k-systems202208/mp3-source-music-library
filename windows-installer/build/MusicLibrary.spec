# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project_root = Path(SPECPATH).parent
src = project_root / "src"
build_dir = project_root / "build"

analysis = Analysis(
    [str(src / "launcher.py")],
    pathex=[str(src)],
    binaries=[],
    datas=[
        (str(src / "music-library-search.html"), "."),
        (str(src / "vendor"), "vendor"),
        (str(project_root / "docs" / "MUTAGEN_LICENSE.txt"), "licenses"),
        (str(project_root / "docs" / "REMOTE_ACCESS_USER.txt"), "."),
        (str(project_root / "docs" / "REMOTE_ACCESS_FAMILY.txt"), "."),
    ],
    hiddenimports=[
        "tkinter",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "tkinter.ttk",
        "sqlite3",
        "remote_access",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="MusicLibrary",
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
    icon=str(build_dir / "music-library.ico"),
    version=str(build_dir / "version_info.txt"),
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MusicLibrary",
)
