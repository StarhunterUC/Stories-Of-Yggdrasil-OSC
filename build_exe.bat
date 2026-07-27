@echo off
setlocal
cd /d "%~dp0"

call "Start Stories OSC.bat" --prepare-only
if errorlevel 1 exit /b %errorlevel%

if not exist ".venv\Scripts\python.exe" (
  echo The repository Python environment was not created.
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 exit /b %errorlevel%

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean "Stories Of Yggdrasil OSC.spec"
exit /b %errorlevel%
