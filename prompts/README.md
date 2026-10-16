# Phase prompts

Each file is one prompt to paste into Claude Code (or Copilot agent mode / cloud agent issue).
Header of each file says: **who** runs it, **which tool/model**, **mode** (PLAN = start in plan mode:
`Shift+Tab` until "plan mode on", or `/plan`), and **when**.

Timeline (deadline Sat 17. 10. 14:00, submit by 13:30):

| Phase | Time | Gate |
| --- | --- | --- |
| F0 Setup | Fri 16:00–16:45 | G0: APIM call OK, IRIS reachable, repo with starter kit |
| F1 Foundation | 16:45–20:00 | G1: `make up && make iris-bootstrap && make seed` works, `GET /api/cases` returns the case, FE shell renders all routes on mocks |
| F2 Core slices | 20:00–24:00 | G2: demo steps 1–4 work end to end (no polish) |
| F3 Differentiators | 00:00–08:00 (night shifts) | G3 feature freeze: steps 5–6 + consistency + as-of + T1–T3 |
| F4 Hardening | 08:00–11:30 | Code freeze 11:30: E2E green, eval numbers, reviews done |
| F5 Submission | 11:30–14:00 | Submitted by 13:30, pitch rehearsed twice |

Model guide: Claude Opus 5.5 (effort xhigh, advisor Fable) for PLAN prompts with architecture weight;
Claude Sonnet 5.5 for feature prompts; Copilot GPT-6.1 Sol for complex feature work in VS Code,
GPT-6 Astra for long autonomous cloud-agent issues overnight, GPT-6 Luna for small/repetitive tasks.
