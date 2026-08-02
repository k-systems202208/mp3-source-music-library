from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "00_build_installer.bat": [b"tests\\verify_package_manifest.py", b"MusicLibrary-Setup-2.7.3-x64.exe"],
    "01_install_inno_setup.bat": [],
    "02_install_python.bat": [],
    "03_prepare_release_assets.bat": [b"04_prepare_release_assets.ps1", b'-Version "2.7.3"'],
}

failures: list[str] = []
for relative, markers in EXPECTED.items():
    path = ROOT / relative
    if not path.is_file():
        failures.append(f"Missing launcher: {relative}")
        continue
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        failures.append(f"UTF-8 BOM is not allowed in Windows batch launcher: {relative}")
    if not data.startswith(b"@echo off\r\n"):
        failures.append(f"Launcher must start with ASCII '@echo off' and CRLF: {relative}")
    bad = sorted({byte for byte in data if byte < 32 and byte not in (10, 13)})
    if bad:
        failures.append(f"Control bytes found in {relative}: {bad}")
    if b"\n" in data.replace(b"\r\n", b""):
        failures.append(f"Bare LF line ending found in {relative}")
    for marker in markers:
        if marker not in data:
            failures.append(f"Expected marker missing from {relative}: {marker!r}")

if failures:
    raise SystemExit("Windows launcher integrity tests failed:\n" + "\n".join(failures))

print("Windows batch launcher integrity tests passed.")
