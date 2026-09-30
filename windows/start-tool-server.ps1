[CmdletBinding()]
param(
    [int]$LocalPort = 8765,
    [string]$ClaudeCommand = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Bridge runtime is not installed. Run .\windows\install.ps1 first."
}

function Resolve-ClaudeExecutable {
    param([string]$Requested)

    if ($Requested) {
        $explicit = Get-Command $Requested -ErrorAction SilentlyContinue
        if ($explicit) {
            return $explicit.Source
        }
        if (Test-Path $Requested) {
            return (Resolve-Path $Requested).Path
        }
        throw "Claude executable not found: $Requested"
    }

    $onPath = Get-Command claude -ErrorAction SilentlyContinue
    if ($onPath) {
        return $onPath.Source
    }

    $extensionRoots = @(
        (Join-Path $env:USERPROFILE ".vscode\extensions"),
        (Join-Path $env:USERPROFILE ".vscode-insiders\extensions")
    )

    $candidates = foreach ($root in $extensionRoots) {
        if (-not (Test-Path $root)) { continue }
        Get-ChildItem $root -Directory -Filter "anthropic.claude-code-*" -ErrorAction SilentlyContinue |
            ForEach-Object {
                $native = Join-Path $_.FullName "resources\native-binary\claude.exe"
                if (Test-Path $native) {
                    Get-Item $native
                }

                Get-ChildItem (Join-Path $_.FullName "resources\native-binaries") -Recurse -Filter "claude.exe" -File -ErrorAction SilentlyContinue
            }
    }

    $picked = $candidates | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($picked) {
        return $picked.FullName
    }

    throw "Claude Code was not found on PATH or inside the VS Code Claude Code extension."
}

$ClaudePath = Resolve-ClaudeExecutable -Requested $ClaudeCommand

# `claude mcp serve` only needs local tool implementations. These settings keep
# the tool-server process from making normal Claude network calls. The local
# Bash tool still inherits the machine's ordinary network access when invoked.
$env:CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
$env:DISABLE_TELEMETRY = "1"
$env:DISABLE_AUTOUPDATER = "1"
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:9"

$proxyArgs = @(
    "-m", "mcp_proxy",
    "--host=127.0.0.1",
    "--port=$LocalPort",
    "--pass-environment",
    "--"
)

if ($ClaudePath.EndsWith(".cmd", [System.StringComparison]::OrdinalIgnoreCase) -or
    $ClaudePath.EndsWith(".bat", [System.StringComparison]::OrdinalIgnoreCase)) {
    $proxyArgs += @("cmd.exe", "/d", "/s", "/c", "`"$ClaudePath`" mcp serve")
} else {
    $proxyArgs += @($ClaudePath, "mcp", "serve")
}

Write-Host "Starting local Claude Code tool server on http://127.0.0.1:$LocalPort/mcp"
Write-Host "Claude executable: $ClaudePath"
& $Python @proxyArgs
exit $LASTEXITCODE
