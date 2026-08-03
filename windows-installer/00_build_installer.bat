@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "BUILD_LOG=%CD%\release\BUILD_LOG_v2.7.6.txt"
set "BUILD_REPORT=%CD%\release\BUILD_REPORT_v2.7.6.txt"
set "INSTALLER=%CD%\release\MusicLibrary-Setup-2.7.6-x64.exe"
set "HASH_FILE=%CD%\release\MusicLibrary-Setup-2.7.6-x64_SHA256.txt"

if not exist "release" mkdir "release"
> "%BUILD_LOG%" echo Music Library v2.7.6 Release Build Log
>>"%BUILD_LOG%" echo ======================================
>>"%BUILD_LOG%" echo Started: %DATE% %TIME%
>>"%BUILD_LOG%" echo Package: %CD%
>>"%BUILD_LOG%" echo.

echo.
echo ============================================================
echo Music Library v2.7.6 Release installer build
echo ============================================================
echo.
echo This step builds the installer only.
echo Do not install it until the build report has been reviewed.
echo.

set "PYTHON_CMD="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
  python --version >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
  echo ERROR: Python 3 was not found.
  echo ERROR: Python 3 was not found.>>"%BUILD_LOG%"
  echo Run 02_install_python.bat first.
  pause
  exit /b 1
)

echo Verifying package files...
%PYTHON_CMD% "tests\verify_package_manifest.py" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :error

if not exist ".venv-build\Scripts\python.exe" (
  echo Creating build environment...
  %PYTHON_CMD% -m venv ".venv-build" >>"%BUILD_LOG%" 2>&1
  if errorlevel 1 goto :error
)

call ".venv-build\Scripts\activate.bat"
if errorlevel 1 goto :error

echo Installing build requirements...
python -m pip install --upgrade pip >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :error
python -m pip install -r "build\requirements-build.txt" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :error

echo Checking Python source...
python -m compileall -q "src" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :error

call :RUN_TEST "tests\test_windows_batch_launchers.py" "Windows batch launchers"
if errorlevel 1 goto :error
call :RUN_TEST "tests\build_sanity.py" "Build sanity"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_client_disconnects.py" "Client disconnects"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_remote_access.py" "Remote access parsing"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_remote_entry_path.py" "Remote entry path"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_launcher_stability.py" "Launcher stability"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_schema_v5_migration.py" "Schema migration through v7"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_local_owner_auth.py" "Local owner authentication"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_startup_auth_handoff.py" "Repeated startup authentication handoff"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_tailscale_identity.py" "Tailscale identity"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_owner_tailscale_link.py" "Owner and Tailscale linking"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_user_management_ui.py" "User management UI"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_user_playback_state.py" "User playback state"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_user_favorites.py" "User favorites"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_favorite_filter.py" "Favorite filter"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_library_home.py" "Library home"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_library_home_layout.py" "Library home layout"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_backup_restore.py" "Backup and restore"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_playlists.py" "Per-user playlists and schema v7"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_playlist_production_ui.py" "Production playlist UI and mobile tab cleanup"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_update_notification.py" "Update notification including prereleases"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_skin_persistence.py" "Skin persistence and schema v7"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_skin_preview.py" "Skin UI contract"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_skin_preview_layout.py" "Skin responsive layout"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_skin_stat_cards.py" "Skin stat cards"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_skin_user_chip.py" "Skin user chip contrast"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_pwa_assets.py" "PWA assets and cache safety"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_pwa_ui_contract.py" "PWA install guidance"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_pwa_mobile_layout.py" "PWA mobile responsive layout"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_pwa_server.py" "PWA static serving"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_long_path_support.py" "Windows long path support"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_live_long_path_probe.py" "Long path probe workflow"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_phase2_copied_full_scan_workflow.py" "Copied DB full scan workflow"
if errorlevel 1 goto :error
call :RUN_TEST "tests\test_release_candidate.py" "Release candidate consistency"
if errorlevel 1 goto :error

echo Building application bundle...
if exist "dist\MusicLibrary" rmdir /s /q "dist\MusicLibrary"
if exist ".build-cache" rmdir /s /q ".build-cache"
python -m PyInstaller --noconfirm --clean --workpath ".build-cache" --distpath "dist" "build\MusicLibrary.spec" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :error

if not exist "dist\MusicLibrary\MusicLibrary.exe" (
  echo ERROR: MusicLibrary.exe was not created.
  echo ERROR: MusicLibrary.exe was not created.>>"%BUILD_LOG%"
  goto :error
)

echo Checking bundled version...
for /f "delims=" %%V in ('"dist\MusicLibrary\MusicLibrary.exe" --version') do set "BUNDLED_VERSION=%%V"
if not "%BUNDLED_VERSION%"=="2.7.6" (
  echo ERROR: Bundled version is "%BUNDLED_VERSION%"; expected "2.7.6".
  echo ERROR: Bundled version is "%BUNDLED_VERSION%"; expected "2.7.6".>>"%BUILD_LOG%"
  goto :error
)

echo Testing bundled executable with an empty library...
if exist "tests\rc_empty_music" rmdir /s /q "tests\rc_empty_music"
if exist "tests\rc_build_data" rmdir /s /q "tests\rc_build_data"
mkdir "tests\rc_empty_music"
"dist\MusicLibrary\MusicLibrary.exe" --worker --music-root "%CD%\tests\rc_empty_music" --data-root "%CD%\tests\rc_build_data" --scan-only --no-browser >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :error

if not exist "tests\rc_build_data\library.db" (
  echo ERROR: Bundled smoke test did not create library.db.
  echo ERROR: Bundled smoke test did not create library.db.>>"%BUILD_LOG%"
  goto :error
)

set "ISCC="
for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%I"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"

if not defined ISCC (
  echo ERROR: Inno Setup was not found.
  echo ERROR: Inno Setup was not found.>>"%BUILD_LOG%"
  echo Run 01_install_inno_setup.bat first.
  pause
  exit /b 2
)

echo Compiling Windows installer...
if exist "%INSTALLER%" del /q "%INSTALLER%"
"%ISCC%" /Qp "installer\MusicLibrary.iss" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 goto :error

if not exist "%INSTALLER%" (
  echo ERROR: The v2.7.6 installer was not created.
  echo ERROR: The v2.7.6 installer was not created.>>"%BUILD_LOG%"
  goto :error
)

echo Calculating SHA-256...
powershell.exe -NoProfile -Command "$h=(Get-FileHash -Algorithm SHA256 -LiteralPath '%INSTALLER%').Hash.ToLower(); Set-Content -LiteralPath '%HASH_FILE%' -Value ($h + '  MusicLibrary-Setup-2.7.6-x64.exe') -Encoding ascii; Write-Output $h" > "%TEMP%\music-library-v276-hash.txt"
if errorlevel 1 goto :error
set /p "INSTALLER_HASH="<"%TEMP%\music-library-v276-hash.txt"
del /q "%TEMP%\music-library-v276-hash.txt" >nul 2>&1

> "%BUILD_REPORT%" echo Music Library v2.7.6 Release Build Report
>>"%BUILD_REPORT%" echo =======================================
>>"%BUILD_REPORT%" echo Finished: %DATE% %TIME%
>>"%BUILD_REPORT%" echo Installer: MusicLibrary-Setup-2.7.6-x64.exe
>>"%BUILD_REPORT%" echo SHA256: %INSTALLER_HASH%
>>"%BUILD_REPORT%" echo Bundled version: %BUNDLED_VERSION%
>>"%BUILD_REPORT%" echo.
>>"%BUILD_REPORT%" echo All source regression tests passed.
>>"%BUILD_REPORT%" echo Bundled executable smoke test passed.
>>"%BUILD_REPORT%" echo Inno Setup compilation passed.
>>"%BUILD_REPORT%" echo.
>>"%BUILD_REPORT%" echo This release installer has not yet been installed on the live system.

>>"%BUILD_LOG%" echo.
>>"%BUILD_LOG%" echo BUILD COMPLETED
>>"%BUILD_LOG%" echo Installer SHA256: %INSTALLER_HASH%
>>"%BUILD_LOG%" echo Finished: %DATE% %TIME%

echo.
echo ============================================================
echo BUILD COMPLETED
echo ============================================================
echo.
echo Installer:
echo %INSTALLER%
echo.
echo SHA256:
echo %INSTALLER_HASH%
echo.
echo IMPORTANT:
echo Review this release build before publishing.
echo Review BUILD_REPORT_v2.7.6.txt and SHA-256 before publishing.
echo.
if not defined MUSIC_LIBRARY_NONINTERACTIVE start "" explorer.exe "%CD%\release"
if not defined MUSIC_LIBRARY_NONINTERACTIVE pause
exit /b 0

:RUN_TEST
set "TEST_FILE=%~1"
set "TEST_NAME=%~2"
echo [RUN] %TEST_NAME%
>>"%BUILD_LOG%" echo [RUN] %TEST_NAME%
python "%TEST_FILE%" >>"%BUILD_LOG%" 2>&1
if errorlevel 1 (
  echo [FAILED] %TEST_NAME%
  >>"%BUILD_LOG%" echo [FAILED] %TEST_NAME%
  exit /b 1
)
echo [PASS] %TEST_NAME%
>>"%BUILD_LOG%" echo [PASS] %TEST_NAME%
exit /b 0

:error
echo.
echo BUILD FAILED. Review:
echo %BUILD_LOG%
>>"%BUILD_LOG%" echo BUILD FAILED: %DATE% %TIME%
pause
exit /b 1
