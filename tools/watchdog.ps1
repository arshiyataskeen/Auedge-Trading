# AuEdge watchdog: run by Windows Task Scheduler at logon and every 10 minutes.
# Starts the AuEdge server (hidden, no window) if it is not running. Does nothing after "Stop AuEdge"
# (data\stopped.flag) until AuEdge is started again with the AuEdge icon.
$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $root "data\watchdog.log"
if (Test-Path (Join-Path $root "data\stopped.flag")) { exit 0 }
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 0 }
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { exit 0 }      # first-time setup is done by "Start AuEdge.bat"
Start-Process -FilePath $py -ArgumentList "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning" `
  -WorkingDirectory $root -WindowStyle Hidden `
  -RedirectStandardOutput (Join-Path $root "data\server.log") -RedirectStandardError (Join-Path $root "data\server_errors.log")
Add-Content -Path $log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  AuEdge was not running: started it"
# keep the log short
$lines = Get-Content $log -ErrorAction SilentlyContinue
if ($lines.Count -gt 500) { $lines[-300..-1] | Set-Content $log }
