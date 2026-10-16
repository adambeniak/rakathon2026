#!/usr/bin/env bash
# PreToolUse hook for Edit|Write. Exit 2 blocks the edit and tells Claude why. Fails CLOSED if input can't be parsed.
# Owners can bypass the contracts/golden guard for one session:  STAFETA_ALLOW_SHARED=1 claude
INPUT=$(cat)
PY=$(command -v python3 || command -v python)
[ -z "$PY" ] && { echo "protect-files.sh: python not found, cannot check the edit target" >&2; exit 2; }
FILE_PATH=$(printf '%s' "$INPUT" | "$PY" -c 'import sys,json; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null)
FILE_PATH="${FILE_PATH//\\//}"
[ -z "$FILE_PATH" ] && { echo "protect-files.sh: cannot parse hook input" >&2; exit 2; }

block() { echo "Blocked by .claude/hooks/protect-files.sh: $FILE_PATH — $1" >&2; exit 2; }

case "$FILE_PATH" in
  *.env.example) ;;
  *.env|*.env.local|*/.env.*) block "secrets file; edit it yourself, never via an agent" ;;
  */.iris/*) block "IRIS password files" ;;
  */.git/*) block "git internals" ;;
  */uv.lock|*/pnpm-lock.yaml|*/package-lock.json) block "lockfile; use 'uv add' / 'pnpm add' instead of editing" ;;
  */data/raw/*) block "source documents are read-only" ;;
esac

if [ "${STAFETA_ALLOW_SHARED:-0}" != "1" ]; then
  case "$FILE_PATH" in
    */contracts/*) block "shared contract; only the architect changes it (start Claude with STAFETA_ALLOW_SHARED=1 if this task explicitly requires it, and add an ADR)" ;;
    */data/golden/*) block "golden set; never change expected values to make tests pass" ;;
  esac
fi
exit 0
