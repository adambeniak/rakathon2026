# Štafeta frontend

React + TypeScript (strict) + Vite + Tailwind + TanStack Query. The API client is generated from
`../contracts/openapi.json`; UI strings are Czech and live in `src/i18n/cs/<feature>.ts`.

## Two modes

| Mode               | Command                                     | Who answers `/api/*`                                                                                  |
| ------------------ | ------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| **Live** (default) | `make up` in the repo root, then `pnpm dev` | the real backend, via the Vite proxy `/api → http://127.0.0.1:8000` (override with `VITE_API_TARGET`) |
| **Offline**        | `VITE_MOCKS=1 pnpm dev`                     | MSW in the browser (`src/mocks`), no backend needed                                                   |

Tests (`pnpm test`) always run against MSW (`src/mocks/server.ts`), as does Playwright (`playwright.config.ts`).
The mocks are never started unless `VITE_MOCKS=1`.

## API layer (`src/lib/api`)

- `client.ts` — the generated `openapi-fetch` client. Middleware sets `X-Demo-Role` from `toApiRole()`
  (`role.ts`: UI `physician` → backend `koc_physician`) and turns every non-2xx response into a typed `ApiProblem`
  (`problem.ts`: `status`, `title`, `detail`). The demo date `?today=` is sent only in offline mode and tests.
- `query.ts` — `useApiQuery` / `useApiMutation`: zod parse at the boundary, errors are `ApiProblem`s
  (show `problemTitle(error)`). Query keys: `queryKey(feature, ...scope)`.
- `http.ts` — temporary client for endpoints that are not in the contract yet; remaining callers are listed in its header.
- `schema.d.ts` — generated, never edited by hand: `make contract` (backend change) or `pnpm gen:api`.

## Commands

`pnpm dev` · `pnpm lint` · `pnpm typecheck` · `pnpm test --run` · `pnpm gen:api` · from the repo root: `make check`.
