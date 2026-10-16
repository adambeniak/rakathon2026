#!/usr/bin/env bash
# PreToolUse hook for Bash: best-effort guard against agents reading secrets.
# Blocks commands that reference .env files (except `--env-file <path>` and .env.example), dump the environment,
# or print make's database. Exit 2 = blocked, reason goes back to Claude.
INPUT=$(cat)
PY=$(command -v python3 || command -v python)
[ -z "$PY" ] && { echo "bash-guard.sh: python not found" >&2; exit 2; }
printf '%s' "$INPUT" | "$PY" -c '
import sys, json, re
try:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
except Exception:
    print("bash-guard.sh: cannot parse hook input", file=sys.stderr); sys.exit(2)
c = re.sub(r"--env-file[ =]\S+", "", cmd)          # passing the file to uv is fine
c = c.replace(".env.example", "")
rules = [
    (r"(^|[\s/\"\x27(=])\.env(\.local)?\b", "references a .env secrets file"),
    (r"(^|[;&|\s])(printenv|env)(\s*($|[;&|]))", "dumps the environment"),
    (r"\bmake\b[^;&|]*\s(-p|--print-data-base)\b", "prints make database"),
    (r"\.iris/password", "reads the IRIS password file"),
]
for pat, why in rules:
    if re.search(pat, c):
        print(f"Blocked by .claude/hooks/bash-guard.sh: command {why}. Ask the human to run it.", file=sys.stderr)
        sys.exit(2)
sys.exit(0)
'
