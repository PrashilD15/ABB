$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$snapshotPath = Join-Path $PSScriptRoot 'project-backup\data'
$destinationPath = Join-Path $PSScriptRoot 'data'
if (-not (Test-Path -LiteralPath (Join-Path $snapshotPath 'lab.sqlite3'))) {
    throw 'No project data snapshot is present.'
}
if (Test-Path -LiteralPath $destinationPath) {
    throw 'A local data directory already exists. Restore into a fresh clone to avoid overwriting your work.'
}
Copy-Item -LiteralPath $snapshotPath -Destination $destinationPath -Recurse
Write-Host 'Restored drawings, profiles and test history. API credentials are not included.'
Write-Host 'Configure .env, then run .\Start-Lab.ps1 -Setup.'
