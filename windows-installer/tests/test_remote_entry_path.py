from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import remote_access

assert remote_access.REMOTE_APP_PATH == "/music-library-search.html"
assert remote_access.build_remote_app_url("https://pc.example.ts.net") == (
    "https://pc.example.ts.net/music-library-search.html"
)

server_source = (SRC / "server.py").read_text(encoding="utf-8")
assert 'parsed.path in {"", "/"}' in server_source
assert 'self.send_header("Location", "/music-library-search.html")' in server_source

print("Remote entry-path tests passed.")
