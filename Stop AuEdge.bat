@echo off
title AuEdge - stopping
echo Stopping AuEdge...
rem Pause the automatic restart until AuEdge is opened again with the AuEdge icon.
cd /d "%~dp0"
if not exist data mkdir data
echo stopped > "data\stopped.flag"
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
taskkill /fi "WINDOWTITLE eq AuEdge server - keep open*" /t /f >nul 2>nul
echo Done. AuEdge will not restart by itself until you open it again with the AuEdge icon.
timeout /t 4 >nul
