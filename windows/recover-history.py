"""Recover VPS transcripts into the local VS Code history without deleting either copy."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import paramiko

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wrapper"))
from history import HistoryMirror


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--remote-project", default="/root/.claude/projects/-root")
    parser.add_argument("--workspace", default=str(Path.cwd().resolve()))
    args = parser.parse_args()
    key = paramiko.Ed25519Key.from_private_key_file(str(Path.home() / ".ssh/id_ed25519"))
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    for attempt in range(4):
        try:
            client.connect(args.host, port=args.port, username=args.user, pkey=key,
                           look_for_keys=False, allow_agent=False, timeout=10)
            break
        except (OSError, paramiko.SSHException):
            if attempt == 3:
                raise
            time.sleep(5)
    mirror = HistoryMirror(args.workspace)
    try:
        with client.open_sftp() as sftp:
            for info in sftp.listdir_attr(args.remote_project):
                if not info.filename.endswith(".jsonl"):
                    continue
                remote = args.remote_project + "/" + info.filename
                with sftp.open(remote, "rb") as handle:
                    body = handle.read().decode("utf-8")
                entries = []
                for line in body.splitlines():
                    try:
                        entries.append(json.loads(line))
                    except ValueError:
                        # A currently active session may have a partial final line.
                        continue
                mirror.append({"filePath": remote, "entries": entries})
                path = mirror.destination(remote)
                os.utime(path, (info.st_mtime, info.st_mtime))
                print("RECOVERED", info.filename, "records=", len(entries), flush=True)
    finally:
        client.close()
    print("LOCAL_HISTORY", mirror.directory, flush=True)


if __name__ == "__main__":
    main()
