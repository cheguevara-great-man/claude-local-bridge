[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Vps,
    [int]$VpsSshPort = 22,
    [int]$LocalPort = 8765,
    [int]$RemotePort = 18765,
    [int]$ReconnectDelaySeconds = 15
)

$ErrorActionPreference = "Stop"
$Ssh = (Get-Command ssh.exe -ErrorAction Stop).Source

$mutexNameInput = "$Vps|$VpsSshPort|$LocalPort|$RemotePort"
$sha = [System.Security.Cryptography.SHA256]::Create()
try {
    $hashBytes = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($mutexNameInput))
    $hash = ([BitConverter]::ToString($hashBytes) -replace "-", "").Substring(0, 24)
} finally {
    $sha.Dispose()
}
$createdNew = $false
$mutex = [Threading.Mutex]::new($true, "Local\ClaudeLocalBridgeTunnel_$hash", [ref]$createdNew)
if (-not $createdNew) {
    $mutex.Dispose()
    exit 0
}

$sshArgs = @(
    "-N",
    "-T",
    "-p", "$VpsSshPort",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
    "-o", "ExitOnForwardFailure=yes",
    "-o", "ServerAliveInterval=20",
    "-o", "ServerAliveCountMax=3",
    "-R", "127.0.0.1:${RemotePort}:127.0.0.1:${LocalPort}",
    $Vps
)

Write-Host "Forwarding VPS 127.0.0.1:$RemotePort -> Windows 127.0.0.1:$LocalPort"
Write-Host "Press Ctrl+C to stop. The tunnel reconnects automatically after network drops."

while ($true) {
    & $Ssh @sshArgs
    $exitCode = $LASTEXITCODE
    Write-Warning "SSH tunnel exited with code $exitCode. Reconnecting in $ReconnectDelaySeconds seconds..."
    Start-Sleep -Seconds $ReconnectDelaySeconds
}
