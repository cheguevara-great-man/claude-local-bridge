"""Mirror Claude Code's native transcript_mirror frames into the VS Code store."""

import json
import re
from pathlib import Path, PurePosixPath
from uuid import UUID


def project_key(workspace: str) -> str:
    # Same sanitization and long-path hash used by Claude Code's session store.
    key = re.sub(r"[^a-zA-Z0-9]", "-", workspace)
    if len(key) <= 200:
        return key
    value = 0
    units = workspace.encode("utf-16-le")
    for i in range(0, len(units), 2):
        value = (value * 31 + int.from_bytes(units[i:i + 2], "little")) & 0xffffffff
    if value >= 0x80000000:
        value -= 0x100000000
    value = abs(value)
    suffix = ""
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    while value:
        value, remainder = divmod(value, 36)
        suffix = digits[remainder] + suffix
    return key[:200] + "-" + (suffix or "0")


class HistoryMirror:
    def __init__(self, workspace: str, projects: Path | None = None):
        self.workspace = workspace
        self.directory = (projects or Path.home() / ".claude" / "projects") / project_key(workspace)
        self.seen: dict[Path, set[str]] = {}

    def destination(self, remote_path: str) -> Path:
        parts = PurePosixPath(remote_path).parts
        # Only accept Claude's project transcripts, never arbitrary remote paths.
        try:
            index = parts.index("projects")
            relative = parts[index + 2:]
            session = relative[0].removesuffix(".jsonl")
            UUID(session)
        except (ValueError, IndexError) as exc:
            raise ValueError("invalid transcript path") from exc
        if len(relative) == 1 and relative[0].endswith(".jsonl"):
            return self.directory / relative[0]
        if (len(relative) == 3 and relative[1] == "subagents"
                and re.fullmatch(r"agent-[A-Za-z0-9_-]+\.jsonl", relative[2])):
            return self.directory.joinpath(*relative)
        raise ValueError("unsupported transcript path")

    def adapt(self, entry: dict) -> dict:
        adapted = dict(entry)
        if "cwd" in adapted:
            adapted["cwd"] = self.workspace
        # These conversations belong to the VS Code surface. Otherwise the
        # extension hides remote CLI records as programmatic SDK sessions.
        if "entrypoint" in adapted:
            adapted["entrypoint"] = "claude-vscode"
        return adapted

    def append(self, frame: dict) -> None:
        path = self.destination(frame["filePath"])
        entries = frame["entries"]
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise ValueError("invalid transcript entries")
        if path not in self.seen:
            known = set()
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        uuid = json.loads(line).get("uuid")
                        if uuid:
                            known.add(uuid)
                    except (ValueError, AttributeError):
                        continue
            self.seen[path] = known
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            for entry in entries:
                uuid = entry.get("uuid")
                if uuid and uuid in self.seen[path]:
                    continue
                handle.write(json.dumps(self.adapt(entry), ensure_ascii=False) + "\n")
                if uuid:
                    self.seen[path].add(uuid)


def relay_stdout(source, target, mirror: HistoryMirror) -> bool:
    """Pass protocol bytes unchanged; consume only native mirror frames."""
    received = False
    for line in source:
        received = True
        try:
            frame = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            frame = None
        if isinstance(frame, dict) and frame.get("type") == "transcript_mirror":
            mirror.append(frame)
        else:
            target.write(line)
            target.flush()
    return received
