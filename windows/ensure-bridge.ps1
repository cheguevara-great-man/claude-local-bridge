[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Vps,
    [int]$VpsSshPort = 22,
    [int]$LocalPort = 8765,
    [int]$RemotePort = 18765,
    [Parameter(Mandatory = $true)]
    [string]$ClaudeCommand,
    [switch]$SkipTunnel
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StateDir = Join-Path $ProjectRoot ".state"
New-Item -ItemType Directory -Path $StateDir -Force | Out-Null

function Test-LocalPort([int]$Port) {
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $client.Connect("127.0.0.1", $Port)
        $client.Dispose()
        return $true
    } catch {
        return $false
    }
}

if (-not (Test-LocalPort $LocalPort)) {
    $toolScript = Join-Path $PSScriptRoot "start-tool-server.ps1"
    $toolOut = Join-Path $StateDir "tool-server.out.log"
    $toolErr = Join-Path $StateDir "tool-server.err.log"
    $toolArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$toolScript`"", "-LocalPort", "$LocalPort", "-ClaudeCommand", "`"$ClaudeCommand`"")
    Start-Process powershell.exe -ArgumentList $toolArgs -WindowStyle Hidden -RedirectStandardOutput $toolOut -RedirectStandardError $toolErr | Out-Null

    for ($i = 0; $i -lt 40; $i++) {
        if (Test-LocalPort $LocalPort) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not (Test-LocalPort $LocalPort)) {
        throw "Local Claude MCP server did not start on 127.0.0.1:$LocalPort. See $toolErr"
    }
}

if ($SkipTunnel) {
    return
}

$tunnelScript = Join-Path $PSScriptRoot "start-tunnel.ps1"
$tunnelOut = Join-Path $StateDir "tunnel.out.log"
$tunnelErr = Join-Path $StateDir "tunnel.err.log"
$tunnelArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$tunnelScript`"", "-Vps", $Vps, "-VpsSshPort", "$VpsSshPort", "-LocalPort", "$LocalPort", "-RemotePort", "$RemotePort")
Start-Process powershell.exe -ArgumentList $tunnelArgs -WindowStyle Hidden -RedirectStandardOutput $tunnelOut -RedirectStandardError $tunnelErr | Out-Null
