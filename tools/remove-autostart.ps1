# Removes the "AuEdge keep running" scheduled task. AuEdge then only runs when started with the AuEdge icon.
Unregister-ScheduledTask -TaskName "AuEdge keep running" -Confirm:$false -ErrorAction SilentlyContinue
Write-Output "Auto-start removed."
