@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp004_prepare_release_assets.ps1" -Version "2.6.2"
if errorlevel 1 (
  echo.
  echo Release asset preparation failed.
  pause
  exit /b 1
)
pause
endlocal
