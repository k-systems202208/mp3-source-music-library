from __future__ import annotations

import os
import secrets
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

with tempfile.TemporaryDirectory(prefix="music-library-pwa-") as temp:
    temp_root = Path(temp)
    data_root = temp_root / "data"
    music_root = temp_root / "music"
    data_root.mkdir()
    music_root.mkdir()
    os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(data_root)
    os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(music_root)
    sys.path.insert(0, str(SRC))

    import server  # noqa: E402

    httpd = server.create_server("127.0.0.1", 0, owner_control_secret="pwa-test-secret-0123456789-abcdef-XYZ")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        cases = (
            ("/manifest.webmanifest", "application/manifest+json"),
            ("/service-worker.js", "text/javascript"),
            ("/offline.html", "text/html"),
            ("/pwa-icons/icon-192.png", "image/png"),
            ("/favicon.ico", "image/"),
        )
        for path, expected_type in cases:
            with urllib.request.urlopen(base + path, timeout=5) as response:
                assert response.status == 200
                assert expected_type in response.headers.get("Content-Type", ""), (path, response.headers)
                assert response.read(32), path

        with urllib.request.urlopen(base + "/service-worker.js", timeout=5) as response:
            assert response.headers.get("Service-Worker-Allowed") == "/"
            assert "no-cache" in response.headers.get("Cache-Control", "")
        with urllib.request.urlopen(base + "/manifest.webmanifest", timeout=5) as response:
            assert "no-cache" in response.headers.get("Cache-Control", "")

        token = secrets.token_urlsafe(24)
        httpd.local_owner_auth.register_one_time_token(token, ttl_seconds=60)
        target = "/music-library-search.html"
        url = base + "/api/local-auth/exchange?" + urllib.parse.urlencode({"token": token, "next": target})

        with urllib.request.urlopen(url, timeout=5) as response:
            handoff = response.read().decode("utf-8")
            assert response.status == 200
            assert response.headers.get("Content-Type") == "text/html; charset=utf-8"
            assert response.headers.get("Connection", "").casefold() == "close"
            assert "window.location.replace(target)" in handoff
            assert 'http-equiv="refresh"' in handoff
            assert target in handoff
            assert token not in handoff
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

print("PWA static serving, MIME, cache-header and safe startup handoff tests passed.")
