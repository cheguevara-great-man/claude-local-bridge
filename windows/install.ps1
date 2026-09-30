[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvDir = Join-Path $ProjectRoot ".venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "python is not on PATH. Install Python 3.10+ first."
}

if (-not (Test-Path $Python)) {
    python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "Failed to create Python virtual environment" }
}

& $Python -m pip install --disable-pip-version-check -r (Join-Path $ProjectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Failed to install bridge dependencies" }

Write-Host "Installed bridge runtime into $VenvDir"
Write-Host "Next: .\windows\build-wrapper.ps1, then .\windows\configure-vscode.ps1 -Vps user@your-vps"
