@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "MUSICLIB_PYTHON=python"
where py >nul 2>nul
if not errorlevel 1 set "MUSICLIB_PYTHON=py -3"

echo [1/5] Checking Python syntax...
%MUSICLIB_PYTHON% -m py_compile src\database.py src\server.py
if errorlevel 1 goto :failed

echo [2/5] Checking JavaScript syntax...
where node >nul 2>nul
if errorlevel 1 goto :node_missing
node -e "const fs=require('fs');const s=fs.readFileSync('src/music-library-search.html','utf8');const m=[...s.matchAll(/<script>([\s\S]*?)<\/script>/g)];if(!m.length)throw new Error('script block not found');m.forEach(x=>new Function(x[1]));"
if errorlevel 1 goto :failed

echo [3/5] Testing playlist improvements...
%MUSICLIB_PYTHON% tests\test_playlists.py
if errorlevel 1 goto :failed

echo [4/5] Testing profile, album, and diagnostics permissions...
%MUSICLIB_PYTHON% tests\test_user_management_ui.py
if errorlevel 1 goto :failed

echo [5/5] Testing home and release regression...
%MUSICLIB_PYTHON% tests\test_library_home.py
if errorlevel 1 goto :failed
%MUSICLIB_PYTHON% tests\test_release_candidate.py
if errorlevel 1 goto :failed

echo.
echo All next-update verification checks passed.
echo Run 05_preview_current_source.bat for visual confirmation.
pause
exit /b 0

:node_missing
echo ERROR: Node.js is required for the JavaScript syntax check.
echo Install Node.js, or run the Python tests individually.
goto :failed

:failed
echo.
echo Verification failed. Review the error above.
pause
exit /b 1
