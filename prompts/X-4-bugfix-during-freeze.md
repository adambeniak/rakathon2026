<!-- WHO: owner of the failing area · TOOL: Claude Code Sonnet (Opus for nasty ones) · MODE: normal · WHEN: after 11:30 freeze only for demo-blocking bugs -->

A demo-blocking bug. Fix it with the smallest safe change.
1. Reproduce: write the failing test first (unit or Playwright step) and show it failing.
2. Find the root cause; explain it in 2 sentences. If the fix touches more than ~30 lines or a shared contract, stop and
   propose a workaround for the demo instead (feature flag, fallback to cached data, hiding the control).
3. Fix, run the new test + `make check` + `@smoke` E2E. No refactors, no formatting-only changes, no new dependencies.
4. Branch `fix/<short>`, PR with "demo-blocker" label, request review from one teammate.
