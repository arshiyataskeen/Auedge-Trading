@echo off
title AuEdge - starting
cd /d "%~dp0"
echo.
echo   AuEdge  ^|  XAU/USD gold analysis
echo   ---------------------------------
echo.

rem ---- First run: set up Python (same as run.bat) ----
if not exist ".venv\Scripts\python.exe" (
  where python >nul 2>nul || (echo Python was not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH". & pause & exit /b 1)
  echo   First start: setting things up, 1-2 minutes, only once...
  python -m venv .venv || goto :fail
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :fail
)

rem ---- Start AuEdge in the background, no window (skip if it is already running) ----
rem "Stop AuEdge" pauses the auto-start; opening AuEdge again resumes it.
if exist "data\stopped.flag" del "data\stopped.flag"
curl.exe -s -o nul http://127.0.0.1:8000/icon.svg
if errorlevel 1 (
  echo   Starting AuEdge...
  wscript.exe "tools\watchdog.vbs"
) else (
  echo   AuEdge is already running.
)
set /a n=0
:waitserver
curl.exe -s -o nul http://127.0.0.1:8000/icon.svg
if not errorlevel 1 goto ready
set /a n+=1
if %n% geq 60 (echo   AuEdge did not start. See data\server_errors.log for the reason. & pause & exit /b 1)
timeout /t 2 /nobreak >nul
goto waitserver

:ready
start "" http://127.0.0.1:8000
echo.
echo   AuEdge is running:  http://127.0.0.1:8000  (opened in your browser)
echo   It keeps running in the background, even with the browser closed.
echo   To stop it, use "Stop AuEdge". This window closes by itself.
timeout /t 8 >nul
exit /b 0

:fail
echo.
echo Setup failed. Check your internet connection and try again.
pause
exit /b 1
