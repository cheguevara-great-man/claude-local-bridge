from __future__ import annotations

import argparse
import getpass
from pathlib import Path

import paramiko


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--port", type=int, default=22)
    args = parser.parse_args()

    key_path = Path.home() / ".ssh" / "id_ed25519"
    pub_path = key_path.with_suffix(".pub")
    public_key = pub_path.read_text(encoding="utf-8").strip()

    password = getpass.getpass("VPS SSH password: ")
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        args.host,
        port=args.port,
        username=args.user,
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=15,
        auth_timeout=15,
        banner_timeout=15,
    )

    sftp = client.open_sftp()
    try:
        try:
            sftp.stat(".ssh")
        except FileNotFoundError:
            sftp.mkdir(".ssh", 0o700)
        sftp.chmod(".ssh", 0o700)

        auth_path = ".ssh/authorized_keys"
        try:
            with sftp.open(auth_path, "r") as handle:
                existing = handle.read()
                if isinstance(existing, bytes):
                    existing = existing.decode("utf-8", "replace")
        except FileNotFoundError:
            existing = ""

        lines = [line.strip() for line in existing.splitlines() if line.strip()]
        if public_key not in lines:
            lines.append(public_key)
        with sftp.open(auth_path, "w") as handle:
            handle.write("\n".join(lines) + "\n")
        sftp.chmod(auth_path, 0o600)
    finally:
        sftp.close()
        client.close()

    print("KEY_INSTALLED_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
