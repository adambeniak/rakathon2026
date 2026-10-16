#!/usr/bin/env bash
# PostToolUse hook for Edit|Write: format the touched file. Never blocks (always exit 0).
INPUT=$(cat)
PY=$(command -v python3 || command -v python)
[ -z "$PY" ] && exit 0
FILE_PATH=$(printf '%s' "$INPUT" | "$PY" -c 'import sys,json; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null)
{ [ -z "$FILE_PATH" ] || [ ! -f "$FILE_PATH" ]; } && exit 0
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"

case "$FILE_PATH" in
  *.py)
    (cd "$ROOT/backend" 2>/dev/null && uv run ruff format "$FILE_PATH" >/dev/null 2>&1 && uv run ruff check --fix "$FILE_PATH" >/dev/null 2>&1) ;;
  *.ts|*.tsx|*.css|*.json|*.md)
    case "$FILE_PATH" in
      */frontend/*) (cd "$ROOT/frontend" 2>/dev/null && pnpm exec prettier --write "$FILE_PATH" >/dev/null 2>&1) ;;
    esac ;;
esac
exit 0
