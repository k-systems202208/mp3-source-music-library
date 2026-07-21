from __future__ import annotations

import os
import py_compile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

required = [
    SRC / "launcher.py",
    SRC / "remote_access.py",
    SRC / "paths.py",
    SRC / "database.py",
    SRC / "generator.py",
    SRC / "server.py",
    SRC / "music-library-search.html",
    SRC / "vendor" / "mutagen" / "__init__.py",
    ROOT / "build" / "MusicLibrary.spec",
    ROOT / "installer" / "MusicLibrary.iss",
]

missing = [str(path) for path in required if not path.exists()]
if missing:
    raise SystemExit("Missing files:\n" + "\n".join(missing))

for path in SRC.glob("*.py"):
    py_compile.compile(str(path), doraise=True)

with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as music:
    os.environ["MUSIC_LIBRARY_DATA_DIR"] = data
    os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = music
    import sys
    sys.path.insert(0, str(SRC))
    import paths
    assert paths.DATA_ROOT == Path(data).resolve()
    assert paths.MUSIC_ROOT == Path(music).resolve()

print("Build sanity check passed.")
