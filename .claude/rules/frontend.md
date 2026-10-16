---
paths:
  - "frontend/**/*.ts"
  - "frontend/**/*.tsx"
  - "frontend/**/*.css"
---
# Frontend rules (React + TypeScript + Vite)
- Feature folders: `src/features/<feature>/{components,api.ts,hooks.ts,types.ts}`. Shared UI only in `src/components/ui` (shadcn).
- API access only through the generated client in `src/lib/api` and TanStack Query hooks. No `fetch` in components.
- Types come from `contracts/openapi.json` (generated `schema.d.ts`). Never hand-write API types.
- UI strings in `src/i18n/cs/<feature>.ts` (one file per feature, aggregated in `index.ts`). Dates with `date-fns` + `cs` locale (`d. M. yyyy`).
- Routes are registered per feature (`src/features/<feature>/route.tsx`) and collected automatically — do not grow one central routes file.
- Status semantics are fixed: Chybí (red), Nesouhlasí (amber), Zastaralé (grey), Ověřeno lékařem (green), Návrh AI (violet). Always icon + text, never colour only.
- Every AI-derived value renders with `<EvidenceChip>` (source document, date, quote on hover/click).
- Accessibility: semantic HTML, labelled inputs, visible focus, keyboard reachable actions; Playwright selectors rely on roles and Czech labels.
- Use the `frontend-design` skill for new screens; keep one primary action per screen.
