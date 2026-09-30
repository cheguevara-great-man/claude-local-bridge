from __future__ import annotations

import os
import json
import secrets
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

from history import HistoryMirror, relay_stdout


CREATE_NO_WINDOW = 0x08000000


def load_config(path: Path) -> dict[str, str]:
    try:
        body = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise RuntimeError(
            f"cannot read {path}: {exc}. Run windows\\configure-vscode.ps1 first"
        ) from exc

    values: dict[str, str] = {}
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def setting(values: dict[str, str], name: str, default: str = "") -> str:
    return os.environ.get(name) or values.get(name) or default


def port(values: dict[str, str], name: str, default: int) -> int:
    value = setting(values, name, str(default))
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a TCP port") from exc
    if not 1 <= parsed <= 65535:
        raise RuntimeError(f"{name} must be between 1 and 65535")
    return parsed


def port_open(value: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", value), timeout=0.15):
            return True
    except OSError:
        return False


def strip_local_mcp_args(args: list[str]) -> list[str]:
    result: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--mcp-config":
            i += 2
            continue
        if args[i] == "--strict-mcp-config":
            i += 1
            continue
        if args[i] == "--tools":
            i += 2
            continue
        if args[i] == "--settings":
            i += 2
            continue
        result.append(args[i])
        i += 1
    return result


def build_remote_command(
    remote_claude: str,
    remote_workdir: str,
    remote_mcp_port: int,
    remote_settings: str,
    original_args: list[str],
    workspace: str = "",
) -> str:
    args = strip_local_mcp_args(original_args)
    stream_json = any(
        arg == "--output-format=stream-json"
        or (arg == "--output-format" and i + 1 < len(args) and args[i + 1] == "stream-json")
        for i, arg in enumerate(args)
    )
    if stream_json and "--session-mirror" not in args:
        args.append("--session-mirror")
    mcp_config = json.dumps({"mcpServers": {"windows-local-claude": {
        "type": "http", "url": f"http://127.0.0.1:{remote_mcp_port}/mcp"
    }}})
    prompt = (
        "The authoritative development workspace is the Windows machine exposed by "
        "the windows-local-claude MCP server. Use its Read, Edit, Write, Glob, Grep, "
        "Bash, and NotebookEdit tools for all project files, Git, builds, tests, "
        "compilers, debuggers, and local development commands. Do not use "
        "windows-local-claude Agent, Skill, WebSearch, WebFetch, Workflow, Cron, or "
        "other reasoning/network tools. The VPS is only the Claude reasoning host. "
        f"The Windows workspace is {workspace}."
    )

    command = ["exec", shlex.quote(remote_claude)]
    command.extend(shlex.quote(arg) for arg in args)
    command.extend(
        [
            "--mcp-config",
            shlex.quote(mcp_config),
            "--strict-mcp-config",
            "--tools",
            "''",
            "--append-system-prompt",
            shlex.quote(prompt),
        ]
    )
    if remote_settings:
        command.extend(["--settings", shlex.quote(remote_settings)])

    if remote_workdir in {"~", "$HOME"}:
        cd_command = 'cd -- "$HOME"'
    else:
        cd_command = f"cd -- {shlex.quote(remote_workdir)}"

    probe = (
        f"ready=; for i in $(seq 1 40); do "
        f"(exec 3<>/dev/tcp/127.0.0.1/{remote_mcp_port}) >/dev/null 2>&1 "
        f"&& ready=1 && break; sleep 0.25; done; "
        f'[ "$ready" = 1 ] || {{ echo '
        f"'claude-local-bridge: reverse MCP tunnel is not ready on "
        f"127.0.0.1:{remote_mcp_port}' >&2; exit 70; }}"
    )
    auth = (
        'token_file="$HOME/.config/claude-local-bridge/oauth_token"; '
        'if [ -r "$token_file" ]; then '
        'export CLAUDE_CODE_OAUTH_TOKEN="$(cat "$token_file")"; fi'
    )
    script = f"{probe}; {auth}; export CLAUDE_CODE_ENTRYPOINT=claude-vscode; {cd_command} && {' '.join(command)}"
    return f"bash -lc {shlex.quote(script)}"


def ensure_bridge(
    bridge_root: Path,
    vps: str,
    ssh_port: int,
    local_port: int,
    remote_port: int,
    local_claude: str,
) -> None:
    script = bridge_root / "windows" / "ensure-bridge.ps1"
    if not script.exists():
        raise RuntimeError(f"missing {script}")

    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        creationflags = CREATE_NO_WINDOW

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Vps",
            vps,
            "-VpsSshPort",
            str(ssh_port),
            "-LocalPort",
            str(local_port),
            "-RemotePort",
            str(remote_port),
            "-ClaudeCommand",
            local_claude,
            "-SkipTunnel",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=None,
        startupinfo=startupinfo,
        creationflags=creationflags,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"local bridge setup failed with exit code {result.returncode}")
    if not port_open(local_port):
        raise RuntimeError(f"local MCP server is not listening on 127.0.0.1:{local_port}")


def run() -> int:
    executable = Path(sys.executable).resolve()
    bin_dir = executable.parent
    bridge_root = bin_dir.parent
    values = load_config(bin_dir / "bridge.conf")

    vps = setting(values, "CLAUDE_VPS_HOST")
    if not vps:
        raise RuntimeError("CLAUDE_VPS_HOST is missing from bin\\bridge.conf")

    ssh_port = port(values, "CLAUDE_VPS_SSH_PORT", 22)
    local_mcp_port = port(values, "CLAUDE_LOCAL_MCP_PORT", 8765)
    remote_mcp_port = port(values, "CLAUDE_VPS_MCP_PORT", 18765)
    ssh_path = setting(
        values, "CLAUDE_VPS_SSH_PATH", r"C:\Windows\System32\OpenSSH\ssh.exe"
    )
    remote_claude = setting(values, "CLAUDE_VPS_REMOTE_CLAUDE", "claude")
    remote_workdir = setting(values, "CLAUDE_VPS_REMOTE_WORKDIR", "~")
    remote_settings = setting(
        values,
        "CLAUDE_VPS_SETTINGS",
        "",
    )

    if len(sys.argv) < 2:
        raise RuntimeError("VS Code did not pass its bundled claude.exe path")
    local_claude = sys.argv[1]
    remote_args = sys.argv[2:]

    ensure_bridge(
        bridge_root,
        vps,
        ssh_port,
        local_mcp_port,
        remote_mcp_port,
        local_claude,
    )
    ssh_base = [
        ssh_path,
        "-T",
        "-p",
        str(ssh_port),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=20",
        "-o",
        "ServerAliveCountMax=3",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "LogLevel=ERROR",
    ]
    mirror = HistoryMirror(str(Path.cwd().resolve()))
    for attempt in range(4):
        # Each chat owns its forwarding port, so opening another chat cannot
        # collide with a still-running or briefly lingering SSH connection.
        session_port = 49152 + secrets.randbelow(16000)
        remote_command = build_remote_command(
            remote_claude, remote_workdir, session_port, remote_settings,
            remote_args, mirror.workspace,
        )
        ssh_args = ssh_base + [
            "-R", f"127.0.0.1:{session_port}:127.0.0.1:{local_mcp_port}",
            vps, remote_command,
        ]
        child = subprocess.Popen(ssh_args, stdin=None, stdout=subprocess.PIPE, stderr=None)
        try:
            assert child.stdout is not None
            received = relay_stdout(child.stdout, sys.stdout.buffer, mirror)
            code = child.wait()
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait()
            if child.stdout:
                child.stdout.close()
        # Once the remote protocol starts, retrying would replay a partially
        # consumed stream and could duplicate commands. Retry only connection setup.
        if code != 255 or received or attempt == 3:
            return code
        time.sleep(5)

    return 1


def main() -> int:
    try:
        return run()
    except Exception as exc:
        print(f"claude-vps-wrapper: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
