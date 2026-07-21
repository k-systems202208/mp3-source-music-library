from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import remote_access

assert remote_access.parse_backend_state('{"BackendState":"Running"}') == "Running"
assert remote_access.parse_backend_state('not json') == ""
assert remote_access.parse_serve_url(
    "Available within your tailnet:\nhttps://music-pc.example.ts.net\n"
) == "https://music-pc.example.ts.net"
assert remote_access.build_remote_app_url(
    "https://music-pc.example.ts.net"
) == "https://music-pc.example.ts.net/music-library-search.html"
assert remote_access.build_remote_app_url(
    "https://music-pc.example.ts.net/"
) == "https://music-pc.example.ts.net/music-library-search.html"
assert remote_access.build_remote_app_url(
    "https://music-pc.example.ts.net/music-library-search.html"
) == "https://music-pc.example.ts.net/music-library-search.html"
assert remote_access.parse_consent_url(
    "Visit https://login.tailscale.com/admin/serve?node=abc then retry"
).startswith("https://login.tailscale.com/")
assert remote_access.parse_consent_url(
    "https://music-pc.example.ts.net"
) == ""

print("Remote access parsing tests passed.")
