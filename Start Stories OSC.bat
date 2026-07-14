@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
  py -3 bootstrap.py %*
  set "RC=%errorlevel%"
  goto :done
)

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or newer is required for this source build.
  echo The standalone Windows release does not require Python.
  pause
  exit /b 1
)

python bootstrap.py %*
set "RC=%errorlevel%"

:done
if not "%RC%"=="0" pause
exit /b %RC%
