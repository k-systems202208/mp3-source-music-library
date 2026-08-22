# Repository editing instructions

## Canonical production source

The current Windows product source of truth is `windows-installer/src/`.

For current product changes, edit files under `windows-installer/` and the current documentation under `docs/`. The root-level Python, HTML, batch, template, and vendor files are historical assets unless a task explicitly targets legacy behavior or history.

In particular, do not use these root-level files as the implementation source for the current product:

- `database.py`
- `generate-library.py`
- `serve-library.py`
- `music-library-search.html`
- `templates/`
- `vendor/`

Use these current equivalents instead:

- database, search, users, playlists: `windows-installer/src/database.py`
- scan/generation: `windows-installer/src/generator.py`
- HTTP/API: `windows-installer/src/server.py`
- browser UI: `windows-installer/src/music-library-search.html`
- bundled dependencies/assets: `windows-installer/src/vendor/` and `windows-installer/src/`
- launcher/build/release: `windows-installer/`

If a root-level historical file and a current file disagree, the current `windows-installer/` implementation wins.

## One-batch workflow

For normal user-driven repository changes, prefer the one-batch workflow in `docs/25-one-batch-workflow.md`. Avoid requiring the user to execute a long sequence of Git commands manually when the workflow can be packaged safely into one `.bat` file. Destructive or irreversible steps must still require explicit confirmation inside the batch.

## v2.7.7 development baseline and test selection

The verified v2.7.7 comparison baseline is documented in `windows-installer/docs/DEVELOPMENT_BASELINE_v2.7.7.md`. Start new work from the latest clean `main`, create a dedicated `feature/`, `fix/`, `maintenance/`, or `docs/` branch, and never commit current development directly to `main`.

Select mandatory tests from `windows-installer/docs/TEST_MATRIX_v2.7.7.md`. For normal code changes, run the affected subsystem tests and the daily regression verification before merge. Before a formal release, run `windows-installer/00_build_installer.bat`.

## Before changing current behavior

1. Read `docs/23-reimplementation-detailed-design.md`.
2. Inspect the exact current source under `windows-installer/src/`.
3. Run the tests related to the changed subsystem.
4. Run `windows-installer/06_verify_next_improvements.bat` for normal regression verification.
5. Before a release, run `windows-installer/00_build_installer.bat`.

Do not delete or modernize legacy root files merely to make them resemble the current source. They are retained as historical assets.
