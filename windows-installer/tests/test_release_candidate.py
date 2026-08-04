from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "2.7.7"
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
assert 'server_version = "MusicLibrary/SQLiteAPI2.7.7"' in server_text

update_text = (ROOT / "src" / "update_check.py").read_text(encoding="utf-8")
assert 'CURRENT_VERSION = "2.7.7"' in update_text
assert "MusicLibrary-UpdateChecker/2.7.7" in update_text
assert "/releases?per_page=100" in update_text
assert "/releases/latest" not in update_text

# Schema 7 adds per-user playlists while retaining the v2.7.2 and v2.7.5 migration backups.
database_text = (ROOT / "src" / "database.py").read_text(encoding="utf-8")
assert "SCHEMA_VERSION = 7" in database_text
assert "CREATE TABLE IF NOT EXISTS playlists" in database_text
assert "CREATE TABLE IF NOT EXISTS playlist_tracks" in database_text
assert "def create_pre_v272_migration_backup(" in database_text
assert "def create_pre_v275_migration_backup(" in database_text
assert 'release_label="v2.7.5"' in database_text
for name in ("create_user_playlist", "list_user_playlists", "get_user_playlist", "rename_user_playlist", "delete_user_playlist", "add_track_to_user_playlist", "remove_track_from_user_playlist", "reorder_user_playlist_tracks", "duplicate_user_playlist", "set_user_display_name", "set_album_override", "management_diagnostics"):
    assert f"def {name}(" in database_text, name

installer_text = (ROOT / "installer" / "MusicLibrary.iss").read_text(encoding="utf-8-sig")
assert '#define MyAppVersion "2.7.7"' in installer_text
assert f'#define MyAppId "{EXPECTED_APP_ID}"' in installer_text
assert "OutputBaseFilename=MusicLibrary-Setup-{#MyAppVersion}-x64" in installer_text
assert "[UninstallDelete]" not in installer_text

version_info = (ROOT / "build" / "version_info.txt").read_text(encoding="utf-8-sig")
assert "filevers=(2, 7, 7, 0)" in version_info
assert "prodvers=(2, 7, 7, 0)" in version_info
assert "FileVersion', u'2.7.7'" in version_info
assert "ProductVersion', u'2.7.7'" in version_info

manifest = json.loads((ROOT / "src" / "manifest.webmanifest").read_text(encoding="utf-8"))
assert manifest["name"] == "自宅音楽ライブラリ"
assert manifest["display"] == "standalone"
assert manifest["start_url"].startswith("./music-library-search.html")

worker_text = (ROOT / "src" / "service-worker.js").read_text(encoding="utf-8")
assert "music-library-shell-v2.7.7" in worker_text
for excluded in ("/api/", "/music/", "/.artwork-cache/", "/backups/"):
    assert excluded in worker_text

html = (ROOT / "src" / "music-library-search.html").read_text(encoding="utf-8")
for token in ('data-view="playlists"', 'id="playlistPanel"', 'id="playlistCreateButton"', 'data-action="playlist-add"', "PLAYLISTS_API_URL", "loadPlaylists", "reorderPlaylistTrack"):
    assert token in html, token
for token in ('id="profileSection"', 'id="diagnosticsSection"', "duplicateCurrentPlaylist", "startEditAlbum", "playlistDragTrackId"):
    assert token in html, token
for token in ("CURRENT_USER_PROFILE_ROUTE", "ALBUM_CORRECTION_ROUTE", "PLAYLIST_DUPLICATE_ROUTE", "DIAGNOSTICS_ROUTE"):
    assert token in server_text, token
for forbidden in ("v2.7.5 機能プレビュー", "複製DBでプレイリスト機能を確認しています", "PLAYLIST_FEATURE_PREVIEW_MODE"):
    assert forbidden not in html, forbidden
assert "startupUrl.searchParams.delete('playlistPreview')" in html
assert "white-space:nowrap" in html

spec_text = (ROOT / "build" / "MusicLibrary.spec").read_text(encoding="utf-8")
for asset in ("manifest.webmanifest", "service-worker.js", "offline.html", "favicon.ico", "pwa-icons"):
    assert asset in spec_text, asset

long_paths_text = (ROOT / "src" / "long_paths.py").read_text(encoding="utf-8")
generator_text = (ROOT / "src" / "generator.py").read_text(encoding="utf-8")
assert "def windows_extended_path(" in long_paths_text
assert "from long_paths import" in generator_text
assert "from long_paths import" in server_text
assert "window.location.replace(target)" in server_text
assert r'http-equiv=\"refresh\"' in server_text
assert 'self.send_header("Connection", "close")' in server_text

build_script = (ROOT / "00_build_installer.bat").read_text(encoding="ascii")
required_tests = [
    "verify_package_manifest.py", "test_windows_batch_launchers.py", "build_sanity.py",
    "test_client_disconnects.py", "test_remote_access.py", "test_remote_entry_path.py",
    "test_launcher_stability.py", "test_schema_v5_migration.py", "test_local_owner_auth.py",
    "test_startup_auth_handoff.py", "test_tailscale_identity.py", "test_owner_tailscale_link.py",
    "test_user_management_ui.py", "test_user_playback_state.py", "test_user_favorites.py",
    "test_favorite_filter.py", "test_library_home.py", "test_library_home_layout.py",
    "test_backup_restore.py", "test_playlists.py", "test_playlist_production_ui.py", "test_update_notification.py",
    "test_skin_persistence.py", "test_skin_preview.py", "test_skin_preview_layout.py",
    "test_skin_stat_cards.py", "test_skin_user_chip.py", "test_pwa_assets.py",
    "test_pwa_ui_contract.py", "test_pwa_mobile_layout.py", "test_pwa_server.py",
    "test_long_path_support.py", "test_live_long_path_probe.py",
    "test_phase2_copied_full_scan_workflow.py", "test_release_candidate.py",
]
for test_name in required_tests:
    assert test_name in build_script, test_name
assert "MusicLibrary-Setup-2.7.7-x64.exe" in build_script
assert "v2.7.7 Release" in build_script
assert "BUILD_REPORT_v2.7.7.txt" in build_script

required_files = [
    ROOT / "RELEASE_NOTES_v2.7.7.md",
    ROOT / "docs" / "INSTALL_INFO.txt",
    ROOT / "docs" / "README_BUILD.txt",
    ROOT / "docs" / "README_USER.txt",
    ROOT / "docs" / "REMOTE_ACCESS_USER.txt",
    ROOT / "docs" / "REMOTE_ACCESS_FAMILY.txt",
    ROOT / "docs" / "MANUAL_TEST_v2.7.7.txt",
    ROOT / "docs" / "GITHUB_RELEASE_2.7.7.txt",
    ROOT / "docs" / "DOCUMENT_VERSION_CHECK_v2.7.7.txt",
    ROOT / "docs" / "DOCUMENT_INDEX_v2.7.7.md",
    ROOT / "docs" / "RELEASE_SCOPE_v2.7.7.md",
    ROOT / "docs" / "RC1_v2.7.5_SCOPE.md",
    ROOT / "docs" / "RC2_v2.7.5_SCOPE.md",
    ROOT / "docs" / "PLAYLISTS_v2.7.5_PHASE1.md",
]
assert all(path.exists() for path in required_files)

release_asset_script = (ROOT / "04_prepare_release_assets.ps1").read_text(encoding="utf-8-sig")
assert "[string]$Version = '2.7.7'" in release_asset_script
assert "SHA256SUMS.txt" in release_asset_script

print("Release candidate consistency tests passed.")
