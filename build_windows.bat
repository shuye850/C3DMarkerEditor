@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "BASEPY="
for %%V in (3.11 3.12 3.13) do (
    if not defined BASEPY (
        py -%%V -c "import struct,platform; assert struct.calcsize('P')==8 and platform.machine().lower() in ('amd64','x86_64')" >nul 2>nul
        if not errorlevel 1 set "BASEPY=py -%%V"
    )
)
if not defined BASEPY (
    python -c "import sys,struct,platform; assert (3,11)<=sys.version_info[:2]<(3,14) and struct.calcsize('P')==8 and platform.machine().lower() in ('amd64','x86_64')" >nul 2>nul
    if not errorlevel 1 set "BASEPY=python"
)
if not defined BASEPY (
    echo Install Python 3.11 or 3.12 x64 from https://www.python.org/downloads/windows/
    echo Then run this file again.
    pause
    exit /b 1
)
if not exist ".venv-windows\Scripts\python.exe" (
    %BASEPY% -m venv .venv-windows
    if errorlevel 1 goto failed
)
set "BUILD_PY=%~dp0.venv-windows\Scripts\python.exe"
"%BUILD_PY%" -m pip install --upgrade pip
if errorlevel 1 goto failed
"%BUILD_PY%" -m pip install --only-binary=:all: -r requirements-windows-build.txt
if errorlevel 1 goto failed
"%BUILD_PY%" build_windows.py
if errorlevel 1 goto failed
echo.
echo Ready: dist\C3DMarkerEditor-Windows-x64.zip
echo Send this ZIP to Windows users. They do not need Python.
pause
exit /b 0
:failed
echo.
echo Build failed. Keep the error message above for troubleshooting.
pause
exit /b 1
