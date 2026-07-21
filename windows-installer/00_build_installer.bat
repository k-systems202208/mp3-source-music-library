@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============================================================
echo Music Library installer build
echo ============================================================
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
  echo Run 02_install_python.bat or install Python 3 manually.
  pause
  exit /b 1
)

if not exist ".venv-build\Scripts\python.exe" (
  echo Creating build environment...
  %PYTHON_CMD% -m venv ".venv-build"
  if errorlevel 1 goto :error
)

call ".venv-build\Scripts\activate.bat"
if errorlevel 1 goto :error

echo Installing build requirements...
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r "build\requirements-build.txt"
if errorlevel 1 goto :error

echo Checking Python source...
python -m compileall -q "src"
if errorlevel 1 goto :error

echo Running source sanity tests...
python "tests\build_sanity.py"
if errorlevel 1 goto :error
python "tests\test_client_disconnects.py"
if errorlevel 1 goto :error
python "tests\test_remote_access.py"
if errorlevel 1 goto :error
python "tests\test_remote_entry_path.py"
if errorlevel 1 goto :error

echo Building application bundle...
if exist "dist\MusicLibrary" rmdir /s /q "dist\MusicLibrary"
python -m PyInstaller --noconfirm --clean --workpath ".build-cache" --distpath "dist" "build\MusicLibrary.spec"
if errorlevel 1 goto :error

if not exist "dist\MusicLibrary\MusicLibrary.exe" (
  echo ERROR: MusicLibrary.exe was not created.
  goto :error
)

echo Testing bundled executable...
if not exist "tests\empty_music" mkdir "tests\empty_music"
if exist "tests\build_data" rmdir /s /q "tests\build_data"
"dist\MusicLibrary\MusicLibrary.exe" --worker --music-root "%CD%\tests\empty_music" --data-root "%CD%\tests\build_data" --scan-only --no-browser
if errorlevel 1 goto :error

set "ISCC="
for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%I"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"

if not defined ISCC (
  echo.
  echo ERROR: Inno Setup was not found.
  echo Run 01_install_inno_setup.bat, then run this build again.
  pause
  exit /b 2
)

echo Compiling Windows installer...
"%ISCC%" /Qp "installer\MusicLibrary.iss"
if errorlevel 1 goto :error

echo.
echo ============================================================
echo BUILD COMPLETED
echo ============================================================
echo Installer output:
echo %CD%\release

echo.
start "" explorer.exe "%CD%\release"
pause
exit /b 0

:error
echo.
echo BUILD FAILED. Review the messages above.
pause
exit /b 1
