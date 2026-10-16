<!-- WHO: P4 · TOOL: Claude Code Sonnet 5.5 + test-engineer subagent + Playwright MCP (or Copilot GPT-6.1 Sol) · MODE: normal · WHEN: F4 (08:00–10:30) -->

ROLE: Senior QA automation engineer (Playwright, TypeScript). The demo must not fail on stage.

CONTEXT: All 6 demo steps exist. Read the demo-flow skill and docs/demo-script.md. Use the `webapp-testing` skill and
Playwright MCP to explore the UI before writing selectors.

GOAL: `make e2e` runs the complete demo (steps 1–6) against `make demo-reset` data with `STAFETA_LLM_CACHE=1`, records
a video usable as the backup demo, and catches regressions until the code freeze.

BUILD
1. `frontend/e2e/demo.spec.ts` — one test, `test.step()` per demo step, role switching via the header, demo clock set
   per step, assertions on what the jury must see (states, "Na tahu", Chybí/Nesouhlasí items, excluded reports 12–13,
   MDT record download, Mailpit e-mail via its API `http://localhost:8025/api/v1/messages`, read receipt in Audit,
   state Uzavřeno, T1/T2/T3 values).
2. Selectors: `getByRole` / `getByLabel` with Czech names; no `waitForTimeout`; generous `expect` timeouts only where
   the LLM cache or IRIS is involved.
3. Config: video `on`, trace `retain-on-failure`, viewport 1440×900, slowMo 250 ms in the `demo-video` project
   (a second project without slowMo for CI).
4. Smoke subset `@smoke` (steps 1, 3, 5), run LOCALLY by the merge captain before/after each merge to main
   (CI has no IRIS/backend stack; do not try to build one in CI today).
5. Fix or file (issue) every defect found; do not weaken assertions.

ACCEPTANCE
- [ ] 3 consecutive green runs locally; video saved to `frontend/e2e/artifacts/demo.webm`
- [ ] `pnpm exec playwright test --grep @smoke` documented in docs/demo-script.md for the merge captain
- [ ] PR `qa/e2e-demo`
