<!-- WHO: P3 (frontend) · TOOL: Claude Code (Sonnet 5.5 or Opus) with frontend-design plugin installed · MODE: PLAN · WHEN: F1 start (16:45), in parallel with F1-1 -->

ROLE
You are a senior frontend engineer and product designer building clinical software for busy Czech care coordinators
and physicians. You care about clarity under time pressure, accessibility and a calm, trustworthy visual language.

READ FIRST
AGENTS.md, CLAUDE.md, .claude/rules/frontend.md, .claude/skills/demo-flow/SKILL.md,
.claude/skills/czech-clinical-docs/SKILL.md, contracts/ (may still be a draft), data/golden/expected_handover_2026-10-21.json.
Use the `frontend-design` skill for the visual direction.

GOAL
Create `frontend/` — a React + TypeScript (strict) + Vite app shell with the design system, navigation and mocked data
for all demo screens, so features can be filled in tonight without waiting for the backend.

IN SCOPE
1. Tooling: pnpm, Vite, React, TypeScript strict, Tailwind, shadcn/ui, TanStack Query, TanStack Router (or React Router —
   pick one, justify in one line), zod, date-fns (cs), MSW, vitest + Testing Library, ESLint + Prettier,
   Playwright (config only; P4 writes tests in `frontend/e2e`). Scripts: dev, build, lint, typecheck, test, gen:api
   (openapi-typescript + openapi-fetch from ../contracts/openapi.json).
2. Design system: tokens (colour, spacing, type scale), status semantics fixed by the rules file
   (Chybí, Nesouhlasí, Zastaralé, Ověřeno lékařem, Návrh AI — icon + text), components: AppShell (header with role
   switcher and simulated "today" date), CaseStateBadge (8 states), BatonHolder ("Na tahu: …" + deadline),
   EvidenceChip (doc name, date, quote popover), StatusPill, EmptyState, Skeleton, Timeline primitive.
3. Routes registered per feature (`src/features/<feature>/route.tsx`, auto-collected):
   - `/referral/new` (GP: drag & drop, pre-filled summary, KOC picker, consent, submit — no long form)
   - `/inbox` (coordinator queue: columns Nový / Aktivní / Odložený, sub-status text, deadline, baton holder)
   - `/cases/:id` (case detail: header with state + baton + T1/T2/T3 placeholders; tabs Přehled, Dokumenty,
     Handover, Úkoly, Časová osa, Komunikace, Audit)
   - `/cases/:id/handover` (15 sections, each with status, values, evidence chips, "Potvrdit sekci", copy button)
   - `/cases/:id/mdt` (as-of date picker, readiness gate, MDT record preview)
   - `/gp` (GP portal: my referred patients, state, what is missing, MDT result with "Potvrdit přijetí")
   - `/reviewer` (insurer reviewer: minimal summary)
4. MSW handlers with realistic fictitious data taken from the golden file (Alena Procházková), so every screen
   renders meaningful content now. Mock data lives in `src/mocks/fixtures/`.
5. i18n: Czech strings per feature in `src/i18n/cs/<feature>.ts`.
6. Accessibility basics: landmarks, focus styles, keyboard navigation, labelled controls.

OUT OF SCOPE
Real API wiring (after `contracts/openapi.json` stabilises), backend, E2E tests.

CONSTRAINTS
- Only touch `frontend/` (except `frontend/e2e/`, owned by P4). Do not edit contracts.
- One primary action per screen. The coordinator must see state, baton holder, next deadline and missing/conflict
  counts within 3 seconds on the case header.
- Open ONE PR `fe/shell`.

PLAN FIRST
Show: the visual direction (2–3 sentences + palette + type choices), component list, route map, mock data plan.
Wait for approval.

ACCEPTANCE
- [ ] `pnpm dev` renders all routes with mock data; `pnpm build`, `pnpm lint`, `pnpm typecheck`, `pnpm test` pass
- [ ] Screenshots of inbox, case detail and handover attached to the PR (use Playwright MCP)
- [ ] No English UI strings; dates in Czech format
