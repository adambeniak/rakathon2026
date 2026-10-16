# Security & privacy (starter — expanded in F5-2)

Štafeta processes **fictitious data only**. This page records what the prototype does today and what a hospital
pilot must add. Owner: P1 (infra) + P4 (auth, audit); reviewed by the `security-privacy-reviewer` subagent.

## What the prototype does (F1)
- **Secrets**: only in `.env` (gitignored, never read by agents) and as `SecretStr` in `app/settings.py`. With
  `STAFETA_ENV` other than `local`/`ci`/`test` the backend refuses the default `JWT_SECRET` and wildcard CORS.
- **No PHI in logs**: structlog JSON with IDs, route templates, status and timings; FHIR errors are logged as issue
  codes + FHIRPath only (OperationOutcome diagnostics may quote values); query strings are never logged; httpx/httpcore
  loggers are kept at WARNING; a key-based redaction processor is the safety net.
- **Errors**: RFC 7807 problem+json, no stack traces, validation errors without the submitted input.
- **Audit**: every FHIR write goes through `app/fhir/repository.py` and creates an `AuditEvent` (actor, action,
  entities); reads of case data (`/api/cases*`) create an `AuditEvent` with action R. If the audit write fails the
  request fails (`502 audit-failed`). `make demo-reset` deletes demo data but **never the audit trail**.
- **Network**: docker compose binds backend, mailpit (and the optional local IRIS) to `127.0.0.1` only. The FHIR client
  sends credentials only to the configured FHIR origin (paging links to other origins are refused).
- **Containers**: backend runs as a non-root user; dependencies from the frozen `uv.lock`.
- **CI**: read-only `GITHUB_TOKEN`, no secrets, no `pull_request_target`.

## Accepted risks for the hackathon
- The team IRIS runs on a **public Azure Container Instance over plain HTTP** with basic auth (ports 1972/52773).
  Acceptable only because all data is fictitious; ACI storage is wiped on restart.
- No user authentication yet: the actor is `system` (issue #4); the API must stay on loopback until #4 lands.
  `POST /api/cases/{id}/ask` returns retrieved chunk text (document excerpts). It is gated by case membership
  (`authorize_case`, like triage: referring GP or staff of the managing KOC; a reviewer gets 403) and audited.
- Write + AuditEvent are two calls, not atomic (#9); failed/denied reads are not audited yet (#8).
- Identifiers (RČ) appear in FHIR search query strings between backend and IRIS, and inside the RelatedPerson and
  Coverage identifier values (#7).
- Uploaded documents must be scoped per patient before uploads exist (#6).

## Required before a pilot with real data
1. TLS everywhere; IRIS and backend on private networking (VNet / private endpoints), no public superserver port.
2. Secrets in Azure Key Vault (managed identity), rotated; no shared `_SYSTEM` account — least-privilege IRIS roles.
3. Real authentication (OIDC / SMART on FHIR scopes) and per-case authorisation (role × relationship to the case).
4. Audit retention and immutability policy (who may read audit, how long it is kept), audit of denied access (#8),
   transactional write + audit (AuditEvent in the same transaction Bundle, #9).
5. Identifier searches via `POST _search` over TLS; CZ Core identifier systems instead of demo URIs.
6. DPIA, data-processing agreements (APIM EU data zone), MDR / AI Act position (AI drafts only, clinician confirms).
