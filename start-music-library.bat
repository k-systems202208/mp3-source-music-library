@echo off
setlocal
cd /d "%~dp0"
title MP3 Source Music Library - SQLite API v2.4

set "HTML_FILE=music-library-search.html"
set "GENERATOR=generate-library.py"
set "SERVER=serve-library.py"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"

if not exist "%HTML_FILE%" (
  echo ERROR: %HTML_FILE% was not found.
  pause
  exit /b 1
)
if not exist "%GENERATOR%" (
  echo ERROR: %GENERATOR% was not found.
  pause
  exit /b 1
)
if not exist "%SERVER%" (
  echo ERROR: %SERVER% was not found.
  pause
  exit /b 1
)

set "PYTHON_CMD="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
  python --version >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
  echo ERROR: Python 3 was not found.
  echo Install Python 3 and enable "Add Python to PATH".
  pause
  exit /b 1
)

echo Updating SQLite library from MP3 files...
%PYTHON_CMD% "%~dp0%GENERATOR%"
if errorlevel 1 (
  echo.
  echo ERROR: Library generation failed.
  echo See the message above and library-diagnostics.csv for details.
  pause
  exit /b 1
)

set "PORT=8000"
for /f "delims=" %%P in ('powershell.exe -NoProfile -Command "$l=[System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback,0);$l.Start();$p=$l.LocalEndpoint.Port;$l.Stop();$p"') do set "PORT=%%P"
set "URL=http://127.0.0.1:%PORT%/%HTML_FILE%"

echo.
echo Music Library SQLite API v2.4 is starting.
echo SQLite: %~dp0library.db
echo URL: %URL%
echo Keep this window open while using the library.
echo Press Ctrl+C or close this window to stop.
echo.
start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Milliseconds 1200; Start-Process '%URL%'"
%PYTHON_CMD% "%~dp0%SERVER%" --host 127.0.0.1 --port %PORT%

if errorlevel 1 (
  echo.
  echo The local server stopped with an error.
  pause
)
endlocal
