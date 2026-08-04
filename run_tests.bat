@echo off
cd /d "%~dp0"
call "Start Stories OSC.bat" --prepare-only
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
if errorlevel 1 exit /b %errorlevel%
.venv\Scripts\python.exe -m pytest -q
pause
