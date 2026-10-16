<!-- WHO: anyone before going to sleep · TOOL: GitHub issue (template "Task") assigned to Copilot cloud agent (GPT-6 Astra for long tasks, GPT-6.1 Sol for normal) — or `claude -p` / Claude Code on the web · WHEN: 23:30 (P3, P4) and 03:30 (P1, P2) -->

Use this as the issue body. One issue = one PR, ≤ 59 min of agent time, files that nobody awake is editing.

---
**Context**
Štafeta (read `AGENTS.md`, `.github/copilot-instructions.md`). This task runs unattended overnight; a human reviews the PR
in the morning. Prefer a smaller correct PR over a large one.

**Task**
<one sentence, imperative — e.g. "Add unit tests for consistency rule R3 (turnaround SLA) covering working days and Czech holidays">

**Allowed files**
- <exact paths/folders — e.g. backend/tests/unit/consistency/test_r3_sla.py, backend/app/consistency/rules/r3_sla.py (bug fixes only)>

**Acceptance criteria**
- [ ] <observable result>
- [ ] `<command>` passes (paste output in the PR)
- [ ] No changes outside Allowed files; no changes to contracts/, data/golden/, lockfiles

**If blocked**
Do not guess. Push what works, open the PR as draft and describe the blocker in the PR description.

---
Good overnight tasks: unit tests for finished modules, Playwright steps for finished screens, MSW fixtures, Czech copy
review in `src/i18n/cs/*`, accessibility fixes, docs (`fhir-mapping.md`, example FHIR instances), HL7 v2 sample messages,
seed data variants, error/empty states. Bad overnight tasks: contracts, state machines, auth, refactors, anything the
demo depends on that nobody can review before 08:00.
