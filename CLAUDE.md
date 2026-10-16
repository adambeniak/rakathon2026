@AGENTS.md

# Claude Code specifics

## How to work in this repo
- Cross-module or architectural change → start in **plan mode** (`Shift+Tab` twice or `/plan`). Do not edit
  until the plan is approved. Plans must list files to touch, contracts affected, tests to add.
- One task per session. `/clear` between unrelated tasks. Use `/compact` with a focus hint when context grows.
- Parallel work → separate worktree per task: `claude -w <task-name>` (branch `worktree-<task-name>`).
- After every meaningful edit run `make check` (hooks already format files). Before finishing a task run
  the relevant tests and paste the summary into the final message.
- Never edit `contracts/`, `data/golden/`, `.env*` or lockfiles unless the task explicitly says so.

## Subagents (`.claude/agents/`) — delegate instead of bloating the main context
| Agent | Use it for |
| --- | --- |
| `fhir-architect` | designing or reviewing any FHIR mapping, profile choice, search query, Bundle |
| `iris-integration` | IRIS setup, ObjectScript, interoperability production, HL7 v2, vector SQL |
| `extraction-auditor` | checking extraction output against source documents and the golden set |
| `clinical-safety-reviewer` | wording, as-of leakage, human-in-the-loop, MDR boundary (before every PR touching AI/UI text) |
| `security-privacy-reviewer` | authz, secrets, logging of PHI, GDPR minimisation, audit coverage |
| `test-engineer` | pytest / vitest / Playwright tests for a finished feature |
| `ux-reviewer` | screenshot-based review of screens via Playwright MCP |

## Skills (`.claude/skills/`) — loaded on demand
`fhir-iris`, `czech-clinical-docs`, `extraction-eval`, `demo-flow`, `hl7v2-iris`.
Also install once per machine: `/plugin install frontend-design@claude-plugins-official` and the
`webapp-testing` skill from `anthropics/skills` (see README).

## Output style
- Final message of a task: what changed (files), how it was verified (commands + result), what is left.
- Czech for any UI copy you write; English for code and docs in `docs/` unless the doc is user-facing.

## Session end
Append to `docs/HANDOFF.md`: date/time, branch, what is done, what is next, open risks. Keep it to 5 lines.
