@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python Launcher not found. Install 64-bit Python 3.10+ and try again.
    exit /b 1
)

if not exist ".venv-build\Scripts\python.exe" (
    py -3 -m venv .venv-build
    if errorlevel 1 exit /b 1
)

.venv-build\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 exit /b 1
.venv-build\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
.venv-build\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name iGitty --collect-all PySide6 --distpath dist app.py
if errorlevel 1 exit /b 1

echo.
echo Build complete: %CD%\dist\iGitty.exe
