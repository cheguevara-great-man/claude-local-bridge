[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Vps,
    [int]$VpsSshPort = 22,
    [int]$LocalPort = 8765,
    [int]$RemotePort = 18765,
    [string]$ClaudeCommand = ""
)

$ErrorActionPreference = "Stop"
$ToolScript = Join-Path $PSScriptRoot "start-tool-server.ps1"
$TunnelScript = Join-Path $PSScriptRoot "start-tunnel.ps1"

if (-not (Test-Path (Join-Path (Split-Path -Parent $PSScriptRoot) ".venv\Scripts\python.exe"))) {
    & (Join-Path $PSScriptRoot "install.ps1")
}

$toolArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$ToolScript`"",
    "-LocalPort", "$LocalPort"
)

if ($ClaudeCommand) {
    $toolArgs += @("-ClaudeCommand", "`"$ClaudeCommand`"")
}

$toolServer = Start-Process -FilePath "powershell.exe" -ArgumentList $toolArgs -PassThru

try {
    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        if ($toolServer.HasExited) {
            throw "Local Claude tool server exited early with code $($toolServer.ExitCode)."
        }
        try {
            $client = [System.Net.Sockets.TcpClient]::new()
            $client.Connect("127.0.0.1", $LocalPort)
            $client.Dispose()
            $ready = $true
            break
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }

    if (-not $ready) {
        throw "Local MCP proxy did not start listening on 127.0.0.1:$LocalPort."
    }

    Write-Host "Local tool server is ready. Starting SSH reverse tunnel..."
    & $TunnelScript -Vps $Vps -VpsSshPort $VpsSshPort -LocalPort $LocalPort -RemotePort $RemotePort
} finally {
    if (-not $toolServer.HasExited) {
        Stop-Process -Id $toolServer.Id -Force -ErrorAction SilentlyContinue
    }
}
