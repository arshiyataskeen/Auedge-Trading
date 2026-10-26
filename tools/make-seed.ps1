# Copies the PC's data (track record, candle history, backtests, news/COT caches) into deploy\seed so the
# first Railway start can put it on the permanent volume. Run it right before "railway up".
$root = Split-Path -Parent $PSScriptRoot
$seed = Join-Path $root "deploy\seed"
if (Test-Path $seed) { Remove-Item $seed -Recurse -Force }
New-Item -ItemType Directory -Force $seed | Out-Null
Copy-Item (Join-Path $root "data\*") $seed -Recurse -Force
# PC-only files that must not travel
Get-ChildItem $seed -Recurse -Include *.progress, *.tmp, *.log, stopped.flag, .seeded -Force | Remove-Item -Force
Remove-Item (Join-Path $seed "research") -Recurse -Force -ErrorAction SilentlyContinue
"Seed ready: " + [math]::Round(((Get-ChildItem $seed -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1) + " MB"
