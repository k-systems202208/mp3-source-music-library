@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul

title Music Library - Current Source Preview
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
  echo Run 02_install_python.bat first.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo Music Library - current source preview
echo ============================================================
echo A copied database is used. The live database and MP3 files
echo are not modified by this preview.
echo.

%PYTHON_CMD% "tests\run_current_source_preview.py" %*
set "RESULT=%ERRORLEVEL%"

echo.
if not "%RESULT%"=="0" echo Preview stopped with error code %RESULT%.
pause
exit /b %RESULT%
