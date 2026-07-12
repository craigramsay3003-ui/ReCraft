[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$installer = Join-Path $root "dist\ReCraft-Setup.exe"

if (-not (Test-Path -LiteralPath $installer)) {
    throw "No ReCraft installer was found at $installer. Run scripts\build_release.ps1 first."
}

Write-Host "Launching the latest ReCraft installer: $installer"
Start-Process -FilePath $installer -Wait
