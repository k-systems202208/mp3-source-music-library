@echo off
setlocal
cd /d "%~dp0"
title Music Library SQLite Backup
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

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

%PYTHON_CMD% "%~dp0library-maintenance.py" backup
if errorlevel 1 (
  echo.
  echo ERROR: Backup failed.
) else (
  echo.
  echo Backup completed.
)
pause
endlocal
