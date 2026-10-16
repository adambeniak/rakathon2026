<!-- WHO: anyone starting a shift or taking over a branch · TOOL: Claude Code · MODE: PLAN -->

I am taking over work after a shift change. Before doing anything:
1. Read `docs/HANDOFF.md` (last 5 entries), `git log --oneline -20 origin/main`, open PRs (`gh pr list`), failing checks
   (`gh pr checks <n>` for PRs in my area), and issues labelled for my role.
2. Summarise in ≤ 10 bullets: what works on main now (run `make check` and the `@smoke` E2E if the stack is up),
   what is in flight, what is broken, what blocks the next gate (see prompts/README.md timeline).
3. Propose my next 3 tasks in priority order with estimated minutes, considering the gate deadline and the demo.
Wait for my choice, then proceed.
