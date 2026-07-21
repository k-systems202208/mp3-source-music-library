from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as music:
    os.environ["MUSIC_LIBRARY_DATA_DIR"] = data
    os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = music
    import server


class ResetOutput:
    def write(self, data: bytes) -> int:
        raise ConnectionResetError(10054, "browser canceled request")


class UnexpectedOutput:
    def write(self, data: bytes) -> int:
        raise OSError(5, "unexpected I/O error")


def handler(range_length: int | None):
    value = object.__new__(server.MusicLibraryHandler)
    value._range_length = range_length
    return value


# Full-file response cancellation must be ignored.
handler(None).copyfile(io.BytesIO(b"abc"), ResetOutput())

# Byte-range response cancellation must also be ignored.
handler(3).copyfile(io.BytesIO(b"abc"), ResetOutput())

# Unexpected storage or programming errors must still be raised.
try:
    handler(3).copyfile(io.BytesIO(b"abc"), UnexpectedOutput())
except OSError as exc:
    assert exc.errno == 5
else:
    raise AssertionError("unexpected OSError was suppressed")

assert server.is_expected_client_disconnect(ConnectionResetError(10054, "reset"))
assert server.is_expected_client_disconnect(BrokenPipeError())
assert not server.is_expected_client_disconnect(OSError(5, "I/O error"))

print("Client disconnect tests passed.")
