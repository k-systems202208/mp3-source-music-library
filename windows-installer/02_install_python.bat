@echo off
setlocal

echo This installs 64-bit Python 3.13 from the Windows Package Manager.
echo Python is needed only on the PC that builds the installer.
echo End users do not need Python.
echo.
pause

winget install --id Python.Python.3.13 -e -s winget -i
if errorlevel 1 (
  echo.
  echo Installation did not complete.
  pause
  exit /b 1
)

echo.
echo Python installation completed.
pause
endlocal
