from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "FILE_MANIFEST_SHA256.txt"

if not MANIFEST.is_file():
    raise SystemExit("FILE_MANIFEST_SHA256.txt was not found.")

failures: list[str] = []
checked = 0
for raw in MANIFEST.read_text(encoding="utf-8-sig").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    digest, separator, relative = line.partition("  ")
    if not separator or len(digest) != 64:
        failures.append(f"Invalid manifest line: {raw}")
        continue
    path = ROOT / relative
    if not path.is_file():
        failures.append(f"Missing: {relative}")
        continue
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual.casefold() != digest.casefold():
        failures.append(f"Hash mismatch: {relative}")
    checked += 1

if failures:
    raise SystemExit("Package manifest verification failed:\n" + "\n".join(failures))

print(f"Package manifest verification passed ({checked} files).")
