import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wrapper"))
from history import HistoryMirror, project_key, relay_stdout
from main import build_remote_command
import shlex


SESSION = "11111111-2222-4333-8444-555555555555"
REMOTE = f"/root/.claude/projects/-root/{SESSION}.jsonl"
WORKSPACE = r"C:\work\demo-project"


class HistoryTests(unittest.TestCase):
    def test_protocol_is_forwarded_and_history_available_before_result(self):
        with tempfile.TemporaryDirectory() as root:
            mirror = HistoryMirror(WORKSPACE, Path(root))
            message = {"type": "user", "uuid": "message-1", "cwd": "/root",
                       "entrypoint": "sdk-cli", "message": {"content": "hello"}}
            frame = {"type": "transcript_mirror", "filePath": REMOTE, "entries": [message]}
            result = b'{"type":"result","result":"ok"}\n'
            class Destination(io.BytesIO):
                def write(self, data):
                    assert mirror.destination(REMOTE).exists()
                    return super().write(data)
            dest = Destination()
            relay_stdout(io.BytesIO(json.dumps(frame).encode() + b"\n" + result), dest, mirror)
            self.assertEqual(dest.getvalue(), result)
            stored = json.loads(mirror.destination(REMOTE).read_text(encoding="utf-8"))
            self.assertEqual(stored["cwd"], WORKSPACE)
            self.assertEqual(stored["entrypoint"], "claude-vscode")
            self.assertEqual(stored["message"], message["message"])

    def test_resume_does_not_duplicate_messages_or_replace_other_sessions(self):
        with tempfile.TemporaryDirectory() as root:
            frame = {"filePath": REMOTE, "entries": [{"uuid": "existing", "type": "user"}]}
            first = HistoryMirror(WORKSPACE, Path(root))
            first.append(frame)
            other = first.directory / "unrelated.jsonl"
            other.write_text("keep me", encoding="utf-8")
            resumed = HistoryMirror(WORKSPACE, Path(root))
            resumed.append(frame)
            self.assertEqual(len(resumed.destination(REMOTE).read_text().splitlines()), 1)
            self.assertEqual(other.read_text(), "keep me")

    def test_untrusted_remote_paths_cannot_escape_local_history(self):
        mirror = HistoryMirror(WORKSPACE)
        for path in ["/etc/passwd", REMOTE + "/../../credentials", "/root/projects/-root/../../oops.jsonl"]:
            with self.assertRaises(ValueError):
                mirror.destination(path)

    def test_project_key_matches_existing_claude_store(self):
        self.assertEqual(project_key(WORKSPACE), "C--work-demo-project")

    def test_vps_default_auth_does_not_require_a_settings_file(self):
        command = build_remote_command("claude", "~", 50001, "", [], WORKSPACE)
        cli = shlex.split(shlex.split(command)[2].split(" && ", 1)[1])
        self.assertNotIn("--settings", cli)

    def test_two_chat_ports_match_their_own_mcp_configs(self):
        for port in [50001, 50002]:
            command = build_remote_command("claude", "~", port, "/root/settings.json",
                                           ["--output-format", "stream-json"], WORKSPACE)
            script = shlex.split(command)[2]
            cli = shlex.split(script.split(" && ", 1)[1])
            config = json.loads(cli[cli.index("--mcp-config") + 1])
            self.assertEqual(config["mcpServers"]["windows-local-claude"]["url"], f"http://127.0.0.1:{port}/mcp")
            self.assertIn("--session-mirror", cli)
            self.assertEqual(cli[cli.index("--tools") + 1], "")


if __name__ == "__main__":
    unittest.main()
