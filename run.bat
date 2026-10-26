@echo off
title AuEdge - XAUUSD analysis
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First start: setting things up. This takes 1-2 minutes and only happens once...
  python -m venv .venv || goto :fail
)
echo Checking packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :fail

echo.
echo AuEdge is starting at http://127.0.0.1:8000
echo Keep this window open while you use it. Close it to stop the dashboard.
echo.
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000"
".venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8000
pause
exit /b 0

:fail
echo.
echo Setup failed. Check your internet connection, then double-click run.bat again.
pause
exit /b 1
