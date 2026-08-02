from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "2.7.3"
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


assert assigned_string(ROOT / "src" / "paths.py", "APP_VERSION") == EXPECTED_VERSION
assert assigned_string(ROOT / "src" / "launcher.py", "APP_VERSION") == EXPECTED_VERSION
assert assigned_string(ROOT / "src" / "update_check.py", "CURRENT_VERSION") == EXPECTED_VERSION

server_text = (ROOT / "src" / "server.py").read_text(encoding="utf-8")
assert 'server_version = "MusicLibrary/SQLiteAPI2.7.3"' in server_text
assert "SQLiteAPI2.7.2" not in server_text

update_text = (ROOT / "src" / "update_check.py").read_text(encoding="utf-8")
assert 'CURRENT_VERSION = "2.7.3"' in update_text
assert "MusicLibrary-UpdateChecker/2.7.3" in update_text
assert "/releases?per_page=100" in update_text
assert "/releases/latest" not in update_text

# Schema 6 remains current. v2.7.3 must not alter or bypass the v2.7.2 migration backup.
database_text = (ROOT / "src" / "database.py").read_text(encoding="utf-8")
assert "SCHEMA_VERSION = 6" in database_text
assert "user_preferences" in database_text
assert "def create_pre_v272_migration_backup(" in database_text
assert 'release_label="v2.7.2"' in database_text

installer_text = (ROOT / "installer" / "MusicLibrary.iss").read_text(encoding="utf-8-sig")
assert '#define MyAppVersion "2.7.3"' in installer_text
assert f'#define MyAppId "{EXPECTED_APP_ID}"' in installer_text
assert "OutputBaseFilename=MusicLibrary-Setup-{#MyAppVersion}-x64" in installer_text
assert "[UninstallDelete]" not in installer_text

version_info = (ROOT / "build" / "version_info.txt").read_text(encoding="utf-8-sig")
assert "filevers=(2, 7, 3, 0)" in version_info
assert "prodvers=(2, 7, 3, 0)" in version_info
assert "FileVersion', u'2.7.3'" in version_info
assert "ProductVersion', u'2.7.3'" in version_info

manifest = json.loads((ROOT / "src" / "manifest.webmanifest").read_text(encoding="utf-8"))
assert manifest["name"] == "自宅音楽ライブラリ"
assert manifest["display"] == "standalone"
assert manifest["start_url"].startswith("./music-library-search.html")

worker_text = (ROOT / "src" / "service-worker.js").read_text(encoding="utf-8")
assert "music-library-shell-v2.7.3" in worker_text
for excluded in ("/api/", "/music/", "/.artwork-cache/", "/backups/"):
    assert excluded in worker_text

spec_text = (ROOT / "build" / "MusicLibrary.spec").read_text(encoding="utf-8")
for asset in ("manifest.webmanifest", "service-worker.js", "offline.html", "favicon.ico", "pwa-icons"):
    assert asset in spec_text, asset

build_script = (ROOT / "00_build_installer.bat").read_text(encoding="ascii")
required_tests = [
    "verify_package_manifest.py", "test_windows_batch_launchers.py", "build_sanity.py",
    "test_client_disconnects.py", "test_remote_access.py", "test_remote_entry_path.py",
    "test_launcher_stability.py", "test_schema_v5_migration.py", "test_local_owner_auth.py",
    "test_tailscale_identity.py", "test_owner_tailscale_link.py", "test_user_management_ui.py",
    "test_user_playback_state.py", "test_user_favorites.py", "test_favorite_filter.py",
    "test_library_home.py", "test_library_home_layout.py", "test_backup_restore.py",
    "test_update_notification.py", "test_skin_persistence.py", "test_skin_preview.py",
    "test_skin_preview_layout.py", "test_skin_stat_cards.py", "test_skin_user_chip.py",
    "test_pwa_assets.py", "test_pwa_ui_contract.py", "test_pwa_mobile_layout.py",
    "test_pwa_server.py", "test_release_candidate.py",
]
for test_name in required_tests:
    assert test_name in build_script, test_name
assert "MusicLibrary-Setup-2.7.3-x64.exe" in build_script
assert "v2.7.3 RC1" in build_script
assert "BUILD_REPORT_v2.7.3_RC1.txt" in build_script

required_files = [
    ROOT / "RELEASE_NOTES_v2.7.3.md",
    ROOT / "docs" / "INSTALL_INFO.txt",
    ROOT / "docs" / "README_BUILD.txt",
    ROOT / "docs" / "README_USER.txt",
    ROOT / "docs" / "REMOTE_ACCESS_USER.txt",
    ROOT / "docs" / "REMOTE_ACCESS_FAMILY.txt",
    ROOT / "docs" / "MANUAL_TEST_v2.7.3.txt",
    ROOT / "docs" / "GITHUB_RELEASE_2.7.3.txt",
    ROOT / "docs" / "DOCUMENT_VERSION_CHECK_v2.7.3.txt",
    ROOT / "docs" / "RC1_v2.7.3_SCOPE.md",
    ROOT / "docs" / "MOBILE_HOME_v2.7.3_PHASE1.md",
]
assert all(path.exists() for path in required_files)

release_asset_script = (ROOT / "04_prepare_release_assets.ps1").read_text(encoding="utf-8-sig")
assert "[string]$Version = '2.7.3'" in release_asset_script
assert "SHA256SUMS.txt" in release_asset_script

print("Release candidate consistency tests passed.")
