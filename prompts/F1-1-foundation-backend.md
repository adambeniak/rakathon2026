<!-- WHO: P1 (architect) · TOOL: Claude Code, Opus 5.5, /effort xhigh, /advisor fable · MODE: PLAN · WHEN: F1 start (16:45), target merge 18:30 · START WITH: `STAFETA_ALLOW_SHARED=1 claude` (this task creates contracts/) -->

ROLE
You are the lead architect and senior Python engineer of "Štafeta", a hackathon prototype (Rakathon 2026, VZP challenge
"Cesta pacienta bez ztráty informací") that will later be piloted in real Czech hospitals. Build the backend foundation
the other three people will build on in parallel tonight. Quality of structure matters more than features.

READ FIRST
AGENTS.md, CLAUDE.md, .claude/skills/fhir-iris/SKILL.md, .claude/rules/*.md, docs/HANDOFF.md,
data/golden/expected_handover_2026-10-21.json (to understand the target data), scripts/bootstrap_iris.py,
docker-compose.yml, Makefile. Source documents are in data/raw/ (DOCX, fictitious).

GOAL (this prompt only)
A runnable backend skeleton + shared contracts + seed pipeline, so that after merge:
`make up && make iris-bootstrap && make seed` loads the demo case into IRIS FHIR and
`GET /api/cases` returns it.

IN SCOPE
1. `backend/` with uv (Python 3.12), FastAPI app factory, pydantic-settings (`app/settings.py`, env from .env),
   lifespan-managed shared `httpx.AsyncClient`, structured JSON logging without PHI, RFC 7807 error handler,
   health endpoint `/api/health` (checks IRIS FHIR metadata + DB-API connection).
   Pin deps: fastapi, uvicorn, pydantic>=2, pydantic-settings, httpx, intersystems-irispython==5.4.1, python-docx,
   openai, tenacity, structlog; dev: ruff, mypy, pytest, pytest-asyncio, respx.
2. Package layout exactly as in AGENTS.md "Repo map": empty-but-importable modules with a docstring stating the
   owner and purpose: api, domain, documents, extraction, consistency, timeline, fhir, iris, outputs, notify, security.
   Routers are auto-discovered from `app/api/routes/*.py` (each module exposes `router`) — no central list to edit.
3. `app/fhir/`: async FHIR client (base URL + basic auth from settings, `application/fhir+json`, OperationOutcome →
   typed exception), `repository.py` with `create`, `update`, `search`, `transaction(bundle)` and an automatic
   AuditEvent for each write (agent = current user or "system", entity = resource reference). Mappers folder with
   one example mapper (Patient) and a test.
4. `app/iris/db.py`: tiny DB-API connection pool (max 3 connections — community edition allows 8 in total),
   context manager that always closes cursor then connection.
5. `app/domain/`: Pydantic models only (no logic yet) for Case, CaseState (8 states from VZP slide 10:
   odeslano, triage, ceka_na_podklady, kompletni, pripraveno_mdt, zaver_mdt, zpetna_vazba_odeslana, uzavreno),
   Task, TaskBusinessStatus (objednano, potvrzeno, provedeno, vysledek_dorucen), SourceDocument
   (authored_at, received_at), Evidence {doc_id, quote, char_start?, char_end?}, Fact, HandoverField
   (status: complete | partial | missing | stale | needs_clarification | complete_with_conflict |
   generated_with_citations — same enum as data/golden), Finding. P4 owns the
   state-machine logic later — leave TODO markers that reference issue numbers I will create.
6. `app/seed.py` (`python -m app.seed [--reset]`): idempotently creates Organizations (GP practice Dolní Břežany,
   KOC 1 Nemocnice Severní, KOC 2 Nemocnice Lipová, LabJih, Poliklinika Jižní, Radiologické centrum Modřany,
   Kardiologická ambulance Jesenice, insurer 211), Practitioners/PractitionerRoles (names from the documents,
   coordinator Bc. Lucie Dvořáková), the Patient + RelatedPerson + Coverage, and one DocumentReference per DOCX
   in data/raw/Pacient with `date` = simulated received time and `content.attachment.creation` = authored date
   parsed from the file name. Attachment = base64 DOCX. Use conditional create on identifiers so re-runs do not
   duplicate. `--reset` deletes only resources tagged `meta.tag = stafeta-demo`.
7. `contracts/`: `openapi.json` exported by `python -m app.export_openapi` (stable ordering), `handover.schema.json`
   (JSON Schema for the 15-field handover incl. evidence and status, derived from the golden file structure),
   `case-states.md` (states, allowed transitions, who may trigger them — draft for P4 to refine).
8. API: `GET /api/cases`, `GET /api/cases/{id}` (case summary: patient, state, baton holder, next deadline,
   counts of missing/conflict items — return placeholders where logic is not built yet, clearly marked).
9. docker-compose: add `backend` service (port 8000, depends on iris, env_file .env, and `environment:` overriding
   IRIS_HOST=iris and FHIR_BASE_URL=http://iris:52773/fhir/r4 — inside docker `localhost` is the container itself). Makefile targets from AGENTS.md
   must work (`check`, `seed`, `contract`, `eval` may run an empty test suite for now).
10. CI (`.github/workflows/ci.yml` already exists): make it pass for the backend job.
11. Docs: `docs/architecture.md` (one page: components, data flow, why FHIR at the edge + internal model, IRIS roles),
    `docs/fhir-mapping.md` (table from the fhir-iris skill, refined), ADR-001 "IRIS for Health FHIR as system of
    record; domain model in backend", ADR-002 "Evidence-locked extraction".

OUT OF SCOPE (other people do it in parallel — do not touch)
frontend/ (P3), extraction logic (P2 works in backend/app/extraction after your merge), state-machine logic (P4).

CONSTRAINTS
- Follow AGENTS.md non-negotiables. No secrets in code. Fictitious data only.
- Keep IRIS usage within 2 GB RAM and ≤ 3 DB connections from the backend.
- Small, reviewable commits (Conventional Commits). Open ONE PR `be/foundation` when done.
- If an InterSystems API behaves differently than the skills say, stop, show me the error and propose 2 options.

PLAN FIRST
In plan mode produce: final file tree, list of endpoints with request/response models, the FHIR resources the seed
creates (with identifier systems), contract files content outline, risks. Wait for my approval before writing code.

ACCEPTANCE (paste the command outputs in your final message)
- [ ] `make up && make iris-bootstrap && make seed && make seed` (second run creates nothing new)
- [ ] `curl -s localhost:8000/api/health` → IRIS OK
- [ ] `curl -s localhost:8000/api/cases` → 1 case for Alena Procházková with 13 documents
- [ ] `make check` green (it skips frontend/ until P3 merges); `make contract` produces a stable `contracts/openapi.json`
- [ ] PR opened with summary, risks and what P2/P3/P4 can now start on
