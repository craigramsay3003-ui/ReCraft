[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venv = Join-Path $root ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$dist = Join-Path $root "dist"
$build = Join-Path $root "build"
$spec = Join-Path $root "packaging\recraft.spec"
$installerDefinition = Join-Path $root "packaging\installer.iss"

function Invoke-Checked {
    param([Parameter(Mandatory)][string]$FilePath, [Parameter(Mandatory)][string[]]$Arguments)
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed with exit code $LASTEXITCODE`: $FilePath $Arguments" }
}

function Remove-BuildOutput {
    param([Parameter(Mandatory)][string]$Path)
    $full = [System.IO.Path]::GetFullPath($Path)
    $rootPrefix = $root.TrimEnd('\') + '\'
    if (-not $full.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the repository: $full"
    }
    if (Test-Path -LiteralPath $full) { Remove-Item -LiteralPath $full -Recurse -Force }
}

Push-Location $root
try {
    if (-not (Test-Path -LiteralPath $python)) {
        $launcher = Get-Command python -ErrorAction SilentlyContinue
        if (-not $launcher) { throw "Python 3.11 or newer is required to create .venv. Install Python and retry." }
        & $launcher.Source -m venv $venv
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $python)) { throw "Failed to create $venv" }
    }

    Invoke-Checked -FilePath $python -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")
    Invoke-Checked -FilePath $python -Arguments @("-m", "pip", "install", "-e", "${root}[dev,build]")

    Write-Host "Running full test suite..." -ForegroundColor Cyan
    Invoke-Checked -FilePath $python -Arguments @("-m", "pytest")
    $testResult = "Passed"
    $version = (& $python -c "import importlib.metadata; print(importlib.metadata.version('recraft-art'))").Trim()
    if (-not $version) { throw "Could not read the application version from pyproject.toml metadata." }

    Remove-BuildOutput $build
    Remove-BuildOutput $dist
    New-Item -ItemType Directory -Path $dist -Force | Out-Null

    Write-Host "Building PyInstaller application..." -ForegroundColor Cyan
    Invoke-Checked -FilePath $python -Arguments @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", $dist, "--workpath", (Join-Path $build "pyinstaller"), $spec)
    $exe = Join-Path $dist "ReCraft\ReCraft.exe"
    if (-not (Test-Path -LiteralPath $exe)) { throw "PyInstaller completed but the expected executable was not found: $exe" }

    $isccCandidates = @(
        $env:INNO_SETUP_COMPILER,
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    ) | Where-Object { $_ }
    $iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $iscc) {
        $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($command) { $iscc = $command.Source }
    }
    if (-not $iscc) {
        throw "Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php, then rerun this script. The PyInstaller app is available at $exe"
    }

    Write-Host "Building Inno Setup installer..." -ForegroundColor Cyan
    Invoke-Checked -FilePath $iscc -Arguments @("/DAppVersion=$version", "/DProjectRoot=$root", $installerDefinition)
    $installer = Join-Path $dist "ReCraft-Setup.exe"
    if (-not (Test-Path -LiteralPath $installer)) { throw "Inno Setup completed but the installer was not found: $installer" }

    Write-Host "`nReCraft release build complete" -ForegroundColor Green
    Write-Host "Version:    $version"
    Write-Host "Tests:      $testResult"
    Write-Host "Executable: $exe ($([math]::Round((Get-Item $exe).Length / 1MB, 2)) MB)"
    Write-Host "Installer:  $installer ($([math]::Round((Get-Item $installer).Length / 1MB, 2)) MB)"
}
finally {
    Pop-Location
}
