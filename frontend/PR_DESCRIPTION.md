## What and why
Adds `frontend/`: React + TS (strict) + Vite shell with design system, navigation and MSW-mocked data for all demo screens (`/referral/new`, `/inbox`, `/cases/:id`, `/cases/:id/handover`, `/cases/:id/mdt`, `/gp`, `/reviewer`), based on the golden file.

## How it was verified
`pnpm lint`, `pnpm typecheck`, `pnpm test` (32 tests incl. axe per route) and `pnpm build` pass. Screenshots: `frontend/docs/screenshots/`.

## Notes
- Router: React Router (routes auto-collected via `import.meta.glob` per feature).
- `contracts/openapi.json` does not exist yet: `pnpm gen:api` exits with a message; API types are a temporary seam in `src/lib/domain.ts`.
- Mocks are on in `pnpm dev`; use `VITE_MOCKS=1` for preview builds.
