#!/usr/bin/env bash
set -euo pipefail

port="${1:-18765}"

if command -v ss >/dev/null 2>&1; then
  ss -ltn "sport = :${port}"
else
  netstat -ltn 2>/dev/null | grep -E "127\\.0\\.0\\.1:${port}[[:space:]]" || true
fi

echo
echo "Expected Claude Code MCP endpoint: http://127.0.0.1:${port}/mcp"
echo "Verify from Claude Code with: claude mcp get windows-local-claude"
