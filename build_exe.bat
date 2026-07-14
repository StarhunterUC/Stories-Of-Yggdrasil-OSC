@echo off
setlocal
cd /d "%~dp0"
call "Start Stories OSC.bat" --prepare-only
if not exist ".venv\Scripts\python.exe" exit /b 1
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --name "Stories Of Yggdrasil OSC" --icon "assets\stories_osc_icon.ico" --add-data "assets;assets" main.py
pause
