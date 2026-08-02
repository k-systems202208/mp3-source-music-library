from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="music-library-startup-handoff-"))
os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(IMPORT_ROOT / "data")
os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(IMPORT_ROOT / "music")
(IMPORT_ROOT / "music").mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SRC))

import launcher  # noqa: E402
import server  # noqa: E402

CONTROL_SECRET = "H" * 48
httpd = server.create_server(
    "127.0.0.1",
    0,
    owner_control_secret=CONTROL_SECRET,
)
port = int(httpd.server_address[1])
thread = threading.Thread(target=httpd.serve_forever, daemon=True)
thread.start()

base = f"http://127.0.0.1:{port}"
page_url = base + "/music-library-search.html"
jar = http.cookiejar.CookieJar()
browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

try:
    # Reproduce repeated full application starts: each cycle registers a new
    # one-time token, loads the exchange document, receives the owner cookie,
    # and confirms the authenticated user without relying on an HTTP redirect.
    for index in range(3):
        token = chr(ord("A") + index) * 43
        exchange_url = launcher.request_local_owner_browser_url(
            page_url,
            CONTROL_SECRET,
            token=token,
        )
        started = time.monotonic()
        with browser.open(exchange_url, timeout=5) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers.get("Connection", "").casefold() == "close"
            assert response.headers.get("Content-Type") == "text/html; charset=utf-8"
        assert time.monotonic() - started < 5
        assert "window.location.replace(target)" in body
        assert 'http-equiv="refresh"' in body
        assert token not in body

        with browser.open(base + "/api/current-user", timeout=5) as response:
            current = json.loads(response.read().decode("utf-8"))
        assert current["authenticated"] is True
        assert current["isOwner"] is True
        assert current["provider"] == "local_owner"
finally:
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)

print("Repeated startup owner-authentication handoff tests passed.")
