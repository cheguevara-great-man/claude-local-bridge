[CmdletBinding()]
param(
    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$OutputName = "claude-vps-wrapper-history"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $ProjectRoot "wrapper\main.py"
$BinDir = Join-Path $ProjectRoot "bin"
$Output = Join-Path $BinDir "$OutputName.exe"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

New-Item -ItemType Directory -Path $BinDir -Force | Out-Null

if (-not (Test-Path $VenvPython)) {
    & (Join-Path $PSScriptRoot "install.ps1")
}

& $VenvPython -m pip install --quiet --disable-pip-version-check "pyinstaller>=6,<7"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install PyInstaller"
}

$BuildDir = Join-Path $ProjectRoot ".build-wrapper"
& $VenvPython -m PyInstaller --noconfirm --clean --onefile --name $OutputName --distpath $BinDir --workpath $BuildDir --specpath $BuildDir $Source
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Host "Built $Output"
