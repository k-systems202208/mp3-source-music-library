from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

html = (SRC / "music-library-search.html").read_text(encoding="utf-8")
database = (SRC / "database.py").read_text(encoding="utf-8")

# A newly loaded track records one play only after HTMLAudioElement.play()
# succeeds. The per-load flag prevents pause/resume from incrementing again.
match = re.search(
    r"async function playTrack\(track, \{offset = null\} = \{\}\)\{(?P<body>[\s\S]*?)\n  \}\n\n  async function toggleTrackPlayback",
    html,
)
assert match is not None, "playTrack() was not found"
body = match.group("body")
play_index = body.find("await els.audioPlayer.play();")
flag_index = body.find("playCountRecordedForCurrentLoad = true;")
record_index = body.find("void recordTrackPlayed(track);")
assert -1 not in (play_index, flag_index, record_index)
assert play_index < flag_index < record_index
assert "if (!playCountRecordedForCurrentLoad)" in body

# Loading another track resets the guard. An ended track also resets it so a
# new repeat cycle counts as a new playback.
set_track = re.search(
    r"function setPlayerTrack\(track\)\{(?P<body>[\s\S]*?)\n  \}\n\n  async function playTrack",
    html,
)
assert set_track is not None, "setPlayerTrack() was not found"
assert "playCountRecordedForCurrentLoad = false;" in set_track.group("body")
assert "if (els.audioPlayer.ended)" in body

# The API remains the user-specific playback endpoint.
assert "`./api/tracks/${encodeURIComponent(track.id)}/played`" in html

# Anonymous playback is intentionally not persisted. Authenticated playback is
# stored in user_track_state and increments atomically.
assert "def record_user_playback(" in database
assert '"recorded": False' in database
assert "INSERT INTO user_track_state" in database
assert "play_count = user_track_state.play_count + 1" in database

print("Playback-count policy contract tests passed.")
