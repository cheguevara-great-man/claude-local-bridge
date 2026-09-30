[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Vps,
    [int]$VpsSshPort = 22
)

$ErrorActionPreference = "Stop"
$Ssh = (Get-Command ssh.exe -ErrorAction Stop).Source
$SshKeygen = (Get-Command ssh-keygen.exe -ErrorAction Stop).Source
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Key = Join-Path $HOME ".ssh\id_ed25519"
$Pub = "$Key.pub"

if (-not (Test-Path $Key)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Key) | Out-Null
    & $SshKeygen -t ed25519 -N '""' -f $Key | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "ssh-keygen failed with exit code $LASTEXITCODE"
    }
}

Write-Host "One-time SSH key bootstrap for $Vps"
Write-Host "Enter the VPS password when ssh asks for it. The password is not stored by this script."

if (-not (Test-Path $Python)) {
    & (Join-Path $PSScriptRoot "install.ps1")
}

if ($Vps -notmatch '^(?<user>[^@]+)@(?<host>.+)$') {
    throw "Vps must be in user@host form."
}

& $Python (Join-Path $PSScriptRoot "bootstrap-ssh-key.py") --host $Matches.host --user $Matches.user --port $VpsSshPort
if ($LASTEXITCODE -ne 0) {
    throw "SSH key bootstrap failed with exit code $LASTEXITCODE"
}

& $Ssh -T -p $VpsSshPort -o BatchMode=yes -o ConnectTimeout=8 $Vps "printf 'SSH_KEY_OK\n'"
if ($LASTEXITCODE -ne 0) {
    throw "The key was copied, but passwordless SSH verification failed."
}

Write-Host "Passwordless SSH is ready."
