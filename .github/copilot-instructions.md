# Copilot instructions — Štafeta

The canonical rules for all agents are in `/AGENTS.md`. Read and follow them first; they override anything here.

Copilot-specific notes:
- Path-specific rules are in `.github/instructions/*.instructions.md` and mirror `.claude/rules/*.md`.
- Shared skills live in `.claude/skills/` (Copilot reads them): `fhir-iris`, `czech-clinical-docs`,
  `extraction-eval`, `demo-flow`, `hl7v2-iris`. Use them when the task matches their description.
- Cloud agent tasks: work only inside the files listed in the issue's "Allowed files" section. If the task needs
  a change in `contracts/`, `data/golden/` or another owner's folder, stop and comment on the issue instead.
- Before opening the PR run `make check` (and `make eval` for extraction changes) and paste the summary.
- PR title in Conventional Commits; fill the PR template; one PR per issue; keep it small.
- Never add real personal data, never commit secrets, never weaken a test to make it pass.
