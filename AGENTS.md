# AGENTS.md — Štafeta (Rakathon 2026, VZP challenge)

Single source of truth for every AI agent working in this repo (Claude Code, GitHub Copilot, GPT models).
Humans: keep this file under ~200 lines. Put details in `docs/` and link them.

## Mission
Štafeta is a shared oncology patient case that connects the referring GP, the KOC care coordinator,
KOC physicians and the MDT. It ingests clinical documents, extracts a structured handover with
evidence for every value, tracks tasks/owners/deadlines, prepares the MDT record and closes the loop
back to the GP with proof of delivery. Demo case: fictitious patient Alena Procházková, MDT on 2026-10-21.

## Non-negotiables (read before writing any code)
1. **Fictitious data only.** Never add real personal or health data. Never print, log or commit secrets.
   `.env` and `.iris/` are off-limits for agents (hooks block it best-effort — do not try to work around them).
2. **No invented clinical facts.** Every extracted value carries `evidence: [{doc_id, quote}]`.
   The quote must exist verbatim (whitespace-normalised) in the source text, or the value is rejected.
   If the source does not state it, the status is `missing` — never guess (e.g. never infer ECOG from "soběstačná").
3. **No clinical advice from AI.** AI may quote, structure, summarise with citations and flag
   inconsistencies. It must not recommend treatment, doses or diagnoses. Keep wording neutral:
   "v dokumentaci uvedeno…", "nesoulad mezi…", "chybí…".
4. **As-of rule.** `as_of` is a timestamp (demo: MDT start `2026-10-21T08:00:00+02:00`). A handover contains only
   documents authored ≤ as_of AND received ≤ as_of. (Reports 12 and 13 and the MDT conclusion itself are after it.)
5. **Human in the loop.** AI output is a draft until a clinician confirms it. Confirmation and edits
   are recorded as FHIR `Provenance` (who, when, what changed).
6. **Audit everything.** Every write and every read of clinical content creates an `AuditEvent`.
7. **Standards at the edge.** Internal domain model in `backend/app/domain`; FHIR R4 mapping only in
   `backend/app/fhir`. Do not leak FHIR JSON into UI components or domain logic.

## Architecture (short)
- **InterSystems IRIS for Health** = FHIR R4 repository (source of truth for clinical + workflow
  resources), HL7 v2 → FHIR interoperability production, vector search table for document chunks,
  SQL analytics (time to treatment). Details: `docs/architecture.md`, `docs/fhir-mapping.md`.
- **backend/** Python 3.12, FastAPI, Pydantic v2, httpx (async), `intersystems-irispython`,
  OpenAI-compatible SDK pointed at the Azure APIM gateway (EU data zone deployments).
- **frontend/** React + TypeScript (strict) + Vite + Tailwind + shadcn/ui + TanStack Query,
  API client generated from `contracts/openapi.json`, MSW mocks for offline work.
- **mailpit** = demo e-mail inbox for delivery proof.
- Azure: IRIS on ACI (team resource group), backend on Container Apps, frontend on Static Web Apps.

## Commands (run from repo root)
| Task | Command |
| --- | --- |
| Start everything locally | `make up` (docker compose; password in `.iris/password.txt`) |
| Bootstrap IRIS (idempotent) | `make iris-bootstrap` |
| Seed demo case | `make seed` |
| Lint + types + unit tests | `make check` |
| Extraction eval vs golden set | `make eval` |
| Playwright E2E (full demo) | `make e2e` |
| Reset demo to initial state | `make demo-reset` |
| Regenerate API contract + TS client | `make contract` |

If a command does not exist yet, create it in the `Makefile` rather than inventing ad-hoc scripts.

## Repo map and ownership (see `.github/CODEOWNERS`)
| Path | Owner role | Notes |
| --- | --- | --- |
| `contracts/` | P1 architect | Shared. Change only when the task says so; add an ADR in `docs/adr/`. |
| `iris/`, `scripts/`, `docker-compose.yml`, `backend/app/fhir`, `backend/app/iris` | P1 | IRIS, FHIR adapter, infra |
| `backend/app/documents`, `extraction`, `consistency`, `timeline` | P2 | AI + data |
| `frontend/` (except `e2e/`) | P3 | UI/UX |
| `backend/app/domain`, `api`, `outputs`, `notify`, `security`, `frontend/e2e` | P4 | Workflow, QA |
| `data/golden/` | P2 | Do not edit expected values to make tests pass. |

## Conventions
- Code, identifiers, commits, comments: English. UI texts and clinical terms: Czech, UI strings in
  `frontend/src/i18n/cs/<feature>.ts` (one file per feature, aggregated by `index.ts` → fewer merge conflicts).
- Avoid shared hotspots: register routers/routes/i18n per feature in their own files (auto-discovery),
  instead of every task editing one central list.
- Python: ruff (lint + format), mypy strict for `domain/`, `extraction/`, `consistency/`; pydantic models
  for every API payload; async I/O; no global state except settings; structured logging without PHI.
- TypeScript: `strict: true`, no `any`, zod at API boundaries, components small, data fetching only via
  TanStack Query hooks in `features/*/api.ts`.
- Dates: store ISO 8601; display Czech format (`21. 10. 2026`). Time zone Europe/Prague.
- Errors: never swallow. Return RFC 7807 problem+json from the API.
- Prefer boring, explicit code over clever abstractions. Hackathon ≠ excuse for unsafe code.

## FHIR conventions (summary — full table in `docs/fhir-mapping.md`)
Case = `EpisodeOfCare` + coordinating `Task` (businessStatus = case state). Steps = `Task` with
owner, due date (`restriction.period.end`) and `businessStatus`. Plan = `CarePlan` from a
`PlanDefinition`. Documents = `DocumentReference` (`date` = received, `content.attachment.creation`
= authored). Handover and MDT record = `Composition`. AI evidence = `Provenance`.
Messages = `Communication` / `CommunicationRequest`. Consent = `Consent`. Audit = `AuditEvent`.
Profiles to follow where practical: CZ Core (hl7.cz/fhir), mCODE STU4 for cancer condition/staging.
Handover field status enum (shared with `data/golden`): `complete | partial | missing | stale | needs_clarification |
complete_with_conflict | generated_with_citations`.
Use LOINC for labs and document types, ICD-10 (MKN-10) for diagnoses, ICD-O-3 morphology for histology.
Unknown code systems: use `https://stafeta.example/fhir/CodeSystem/<name>` and list them in the mapping doc.

## Definition of done (every task)
- `make check` passes; new logic has tests; UI change has a screenshot in the PR.
- Touching extraction or consistency → `make eval` shows no regression.
- No secrets, no real data, no TODOs without an issue link.
- PR is small (aim < 400 changed lines excl. generated files), title in Conventional Commits.

## Git
- Branch from `main`: `<area>/<short-desc>` (areas: `be`, `fe`, `ai`, `iris`, `wf`, `qa`, `docs`, `infra`, `fix`).
- Conventional Commits: `feat(extraction): add evidence lock`. Squash-merge only.
- Rebase on `main` before opening a PR. Never force-push `main`. Never rewrite someone else's branch.
- Generated files (`contracts/openapi.json`, `frontend/src/lib/api/schema.d.ts`, lockfiles) are never
  hand-merged: on conflict take `main`'s version and regenerate.

## When unsure
Stop and ask instead of guessing when a change would: alter `contracts/`, delete data, change the
case state machine, touch auth, or produce clinical wording. At the end of a long session, append a
short entry to `docs/HANDOFF.md` (what changed, what is next, known issues).
