# v2.7.4 Phase 2: copied full scan and playback verification

## Scope

Phase 2 validates the production music folder against a copied SQLite database.
The live database is backed up through SQLite's backup API and is never selected
as the scan destination.

## Acceptance rules

- every discovered MP3 is available in the copied database;
- every absolute path of 260 characters or more is available;
- the latest scan contains no error rows;
- all former `mp3_read_error` paths are resolved;
- pre-existing track IDs remain present;
- `users`, `user_identities`, `user_track_state`, and `user_preferences` remain
  byte-for-byte equivalent at the row-data level;
- the live database SHA-256 remains unchanged during the workflow;
- the MP3 path, size, and modification-time fingerprint remains unchanged;
- three representative long-path MP3s pass beginning and midpoint HTTP byte
  range requests through the actual application server.

## Output

Each execution creates `PHASE2_OUTPUT/<timestamp>/` containing:

- `data/library.db` — copied and rescanned database;
- `PHASE2_FULL_SCAN_LOG.txt`;
- `PHASE2_COPIED_SCAN_RESULT.json`;
- `PHASE2_COPIED_SCAN_SUMMARY.txt`;
- `PHASE2_PLAYBACK_SAMPLES.txt`.

The copied data can be opened by `02_preview_scanned_copy.bat`. Any favorite or
play-count changes made in that preview affect only the copied database.
