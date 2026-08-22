# Legacy source notice

This repository contains both the current Windows product and older historical source files.

## Current product source of truth

For the current product, use:

`windows-installer/src/`

The release build, Windows launcher, server, database implementation, browser UI, tests, PyInstaller bundle, and installer are all maintained under `windows-installer/`.

The integrated implementation contract is:

`docs/23-reimplementation-detailed-design.md`

## Historical root-level files

Several similarly named files remain at the repository root because they document earlier stages of the project. They are not the source of truth for current product changes.

| Historical root item | Current product source |
|---|---|
| `database.py` | `windows-installer/src/database.py` |
| `generate-library.py` | `windows-installer/src/generator.py` |
| `serve-library.py` | `windows-installer/src/server.py` |
| `music-library-search.html` | `windows-installer/src/music-library-search.html` |
| `templates/` | current UI is bundled from `windows-installer/src/` |
| `vendor/` | `windows-installer/src/vendor/` |

Do not delete these historical files solely because they are obsolete. Do not apply current product fixes to them unless a task explicitly targets legacy history or compatibility.

When documentation and historical root files disagree with the current implementation, verify against `windows-installer/src/` and the current tests.
