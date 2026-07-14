@echo off
cd /d "%~dp0"
call "Start Stories OSC.bat" --prepare-only
.venv\Scripts\python.exe -m unittest discover -s tests -v
pause
