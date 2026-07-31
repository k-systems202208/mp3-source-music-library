from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "2.7.0"
EXPECTED_APP_ID = "{{DDF12346-0D38-4D31-A4AF-27B406C91D8A}"


def assigned_string(path: Path, variable: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == variable:
                value = ast.literal_eval(node.value)
                if isinstance(value, str):
                    return value
    raise AssertionError(f"{variable} was not found in {path}")


paths_version = assigned_string(ROOT / "src" / "paths.py", "APP_VERSION")
launcher_version = assigned_string(ROOT / "src" / "launcher.py", "APP_VERSION")
assert paths_version == EXPECTED_VERSION
assert launcher_version == EXPECTED_VERSION

server_text = (ROOT / "src" / "server.py").read_text(encoding="utf-8")
assert 'server_version = "MusicLibrary/SQLiteAPI2.7.0"' in server_text
assert "2.7.0-dev" not in server_text

database_text = (ROOT / "src" / "database.py").read_text(encoding="utf-8")
assert "SCHEMA_VERSION = 5" in database_text
assert "user_track_state" in database_text
assert "library-pre-v2.7.0-" in database_text
assert "def _merge_user_track_state_into_owner(" in database_text
assert "playCountAdded" in database_text
assert "ratingConflictCount" in database_text
assert "評価が異なる曲が" in database_text

installer_text = (
    ROOT / "installer" / "MusicLibrary.iss"
).read_text(encoding="utf-8-sig")
assert '#define MyAppVersion "2.7.0"' in installer_text
assert f'#define MyAppId "{EXPECTED_APP_ID}"' in installer_text
assert "OutputBaseFilename=MusicLibrary-Setup-{#MyAppVersion}-x64" in installer_text
assert "[UninstallDelete]" not in installer_text

version_info = (
    ROOT / "build" / "version_info.txt"
).read_text(encoding="utf-8-sig")
assert "filevers=(2, 7, 0, 0)" in version_info
assert "prodvers=(2, 7, 0, 0)" in version_info
assert "FileVersion', u'2.7.0'" in version_info
assert "ProductVersion', u'2.7.0'" in version_info
assert "CompanyName', u'k-systems202208'" in version_info

build_script = (
    ROOT / "00_build_installer.bat"
).read_text(encoding="ascii")
required_tests = [
    "test_client_disconnects.py",
    "test_remote_access.py",
    "test_remote_entry_path.py",
    "test_launcher_stability.py",
    "test_schema_v5_migration.py",
    "test_local_owner_auth.py",
    "test_tailscale_identity.py",
    "test_owner_tailscale_link.py",
    "test_user_management_ui.py",
    "test_user_playback_state.py",
    "test_user_favorites.py",
    "test_favorite_filter.py",
    "test_release_candidate.py",
]
for test_name in required_tests:
    assert test_name in build_script
assert "PyInstaller" in build_script
assert "ISCC" in build_script
assert "MusicLibrary-Setup-2.7.0-x64.exe" in build_script
assert "Get-FileHash" in build_script
assert "v2.7.0 RC2" in build_script
assert "BUILD_REPORT_v2.7.0_RC2.txt" in build_script

required_files = [
    ROOT / "RELEASE_NOTES_v2.7.0.md",
    ROOT / "docs" / "INSTALL_INFO.txt",
    ROOT / "docs" / "README_BUILD.txt",
    ROOT / "docs" / "README_USER.txt",
    ROOT / "docs" / "REMOTE_ACCESS_USER.txt",
    ROOT / "docs" / "REMOTE_ACCESS_FAMILY.txt",
    ROOT / "docs" / "MANUAL_TEST_v2.7.0.txt",
    ROOT / "docs" / "GITHUB_RELEASE_2.7.0.txt",
    ROOT / "docs" / "OWNER_PERSONAL_STATE_MERGE_RC2.md",
]
assert all(path.exists() for path in required_files)

release_asset_script = (
    ROOT / "04_prepare_release_assets.ps1"
).read_text(encoding="utf-8-sig")
assert "[string]$Version = '2.7.0'" in release_asset_script
assert "SHA256SUMS.txt" in release_asset_script

print("Release candidate consistency tests passed.")
