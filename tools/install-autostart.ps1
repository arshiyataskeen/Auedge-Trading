# Creates the Windows scheduled task "AuEdge keep running": at logon and every 10 minutes it runs the watchdog,
# which starts AuEdge in the background if it is not running. Remove it with "tools\remove-autostart.ps1".
$root = Split-Path -Parent $PSScriptRoot
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument ('"' + (Join-Path $PSScriptRoot "watchdog.vbs") + '"') -WorkingDirectory $root
$every10 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 10)
$triggers = @($every10)
try { $triggers += New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME" } catch {}
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew
$desc = "Keeps the AuEdge gold analysis app running in the background (starts it at logon and if it stops). " +
        "Use 'Stop AuEdge' to pause it; the AuEdge icon resumes it."
try {
  Register-ScheduledTask -TaskName "AuEdge keep running" -Action $action -Trigger $triggers -Settings $settings `
    -Description $desc -Force -ErrorAction Stop | Out-Null
} catch {
  # A logon trigger can need admin rights; fall back to the 10-minute trigger alone.
  Register-ScheduledTask -TaskName "AuEdge keep running" -Action $action -Trigger $every10 -Settings $settings `
    -Description $desc -Force -ErrorAction Stop | Out-Null
  Write-Output "Registered (every 10 minutes; logon trigger needs admin rights)."
  exit 0
}
Write-Output "Registered (at logon and every 10 minutes)."
