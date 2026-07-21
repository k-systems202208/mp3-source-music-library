@echo off
setlocal

echo This installs Inno Setup 6 from the Windows Package Manager.
echo The official package ID is JRSoftware.InnoSetup.
echo.
pause

winget install --id JRSoftware.InnoSetup -e -s winget -i
if errorlevel 1 (
  echo.
  echo Installation did not complete.
  pause
  exit /b 1
)

echo.
echo Inno Setup installation completed.
pause
endlocal
