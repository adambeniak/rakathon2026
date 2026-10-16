#!/usr/bin/env bash
# SessionStart hook: stdout is added to Claude's context. Keep it short.
ROOT="${CLAUDE_PROJECT_DIR:-.}"
echo "Branch: $(git -C "$ROOT" branch --show-current 2>/dev/null)"
if [ -f "$ROOT/docs/HANDOFF.md" ]; then
  echo "Latest handoff notes (docs/HANDOFF.md, last 12 lines):"
  tail -n 12 "$ROOT/docs/HANDOFF.md"
fi
exit 0
