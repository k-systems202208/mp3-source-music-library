# v2.7.4 Phase 1: Windows long file path support

## Purpose

Read, index and stream MP3 files whose absolute Windows path is 260 characters or longer without renaming the user's folders or files.

## Design

- Database and browser URLs continue to store normal `Music/...` virtual paths.
- Only Windows filesystem calls receive the extended-length `\\?\` form.
- Local drive paths and UNC paths are handled separately.
- Scanning does not rely on the machine-wide Windows `LongPathsEnabled` policy.
- Mutagen receives an already opened file object, avoiding library-specific filename handling.
- HTTP byte-range playback uses the same long-path-safe open function.
- Existing SQLite schema 6 remains unchanged.

## Phase 1 safety

`01_probe_live_long_paths.bat` is read-only. It reads the current configuration and diagnostics, finds MP3 paths of 260 characters or more, and checks:

- stat and file size
- beginning/end reads and seeking
- ID3 metadata access
- duration fallback
- content-signature generation used by move detection

It does not run the library generator, write the live database, change tags, rename files, or alter artwork.

## Acceptance target

The user's previous diagnostics contained 201 `mp3_read_error` records caused by absolute paths between 260 and 364 characters. Phase 1 passes when all physically present long-path MP3 files are readable and the previous 201 targets are reported as resolved by the probe.
