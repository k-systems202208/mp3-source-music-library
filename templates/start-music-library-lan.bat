@echo off
setlocal
cd /d "%~dp0"
title MP3 Source Music Library - LAN 8765

set "HTML_FILE=music-library-search.html"
set "GENERATOR=generate-library.py"
set "SERVER=serve-library.py"
set "PORT=8765"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"

set "PYTHON_CMD="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
  python --version >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
  echo ERROR: Python 3 was not found.
  pause
  exit /b 1
)

echo Updating SQLite library from MP3 files...
%PYTHON_CMD% "%~dp0%GENERATOR%"
if errorlevel 1 (
  echo ERROR: Library generation failed.
  pause
  exit /b 1
)

set "URL=http://127.0.0.1:%PORT%/%HTML_FILE%"
echo.
echo LAN server will listen on TCP %PORT%.
echo Open http://PC-IP:%PORT%/%HTML_FILE% from another device.
echo Keep this window open.
echo.
start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Milliseconds 1200; Start-Process '%URL%'"
%PYTHON_CMD% "%~dp0%SERVER%" --host 0.0.0.0 --port %PORT%
endlocal
