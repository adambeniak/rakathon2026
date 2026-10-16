# Architecture (one page)

Štafeta is a shared oncology patient case: GP → KOC coordinator → KOC physicians → MDT → back to the GP with proof
of delivery. Fictitious data only. Decisions: [ADR-0001](adr/0001-iris-fhir-system-of-record.md),
[ADR-0002](adr/0002-evidence-locked-extraction.md). FHIR details: [fhir-mapping.md](fhir-mapping.md).

## Components
```
 Browser (React + TS, Vite)                     Azure APIM (OpenAI-compatible, EU data zone)
   │  generated client from contracts/openapi.json        ▲
   ▼                                                      │ app/extraction/llm.py only
 backend/ (FastAPI, Python 3.12)  ────────────────────────┘
   api/        HTTP only: routers (auto-discovered), schemas, RFC 7807 errors
   domain/     Pydantic models + pure logic (state machines, readiness gate) — no I/O
   documents/ extraction/ consistency/ timeline/   AI + data pipeline (evidence-locked)
   retrieval/  embeddings, document indexing, hybrid search, "ask the case" (docs/vector-search.md)
   fhir/       FHIR R4 adapter: client, repository (demo tag + AuditEvent), mappers
   iris/       IRIS SQL via DB-API (≤ 3 pooled connections): vector search, analytics
   outputs/ notify/ security/   MDT record export, e-mail + delivery proof, actor/auth
   │ HTTP (basic auth)              │ superserver 1972
   ▼                                ▼
 InterSystems IRIS for Health (namespace FHIRSERVER)        mailpit (demo inbox, SMTP 1025 / UI 8025)
   FHIR R4 repository /fhir/r4 (JsonAdvSQL) — system of record
   Stafeta.DocChunk (VECTOR + HNSW, iFind) — document chunks for hybrid search (docs/vector-search.md)
   HL7 v2 → FHIR interoperability production (F3-5)
```

## Data flow
1. **Ingest**: referral letter / reports arrive (upload or HL7 v2 MDM/ORU) → `DocumentReference`
   (`date` = received, `attachment.creation` = authored, base64 content), linked to the case `EpisodeOfCare`.
2. **Extract**: `documents` normalises text → `extraction` produces `Fact`s with verbatim `Evidence` → evidence lock
   rejects anything not found in the source (ADR-0002). In parallel `retrieval` chunks and embeds each document into
   `Stafeta.DocChunk`; `POST /api/cases/{id}/ask` answers questions from IRIS hybrid search with per-sentence
   citations and no advice (ADR-0004, `docs/vector-search.md`).
3. **Assemble**: the 15-field handover (`contracts/handover.schema.json`) is assembled for an **as-of** timestamp:
   a document counts only if authored ≤ as_of AND received ≤ as_of. `consistency` adds findings (conflicts,
   missing, stale, SLA breaches) in neutral wording.
4. **Coordinate**: the case state machine (`contracts/case-states.md`) and step `Task`s with owner, place and due
   date; the owner of the case Task is "who holds the baton".
5. **Confirm & close the loop**: a physician confirms sections (`Provenance`), the MDT record becomes a final
   `Composition`, the result goes to the GP (`Communication`, delivery and read receipts as `AuditEvent`).

## Why FHIR at the edge + an internal domain model
- IRIS FHIR is the **system of record** for clinical and workflow resources: standard, auditable, interoperable
  with hospitals (CZ Core, mCODE), and the native target of the HL7 v2 production.
- The UI and the logic need **small, stable, typed shapes** (case summary, 15-field handover, state machine),
  not FHIR JSON. So: `domain/` models ↔ `fhir/mappers/` ↔ FHIR JSON. Nothing outside `app/fhir` builds or parses
  FHIR; the UI never sees FHIR ids (API ids are business identifiers).
- Contracts are generated from code (`make contract`): `openapi.json` from FastAPI, `handover.schema.json` from
  `app/domain/handover.py`. CI fails when a committed contract is stale.

## Cross-cutting rules
- **Audit**: every write and every read of clinical content goes through `app/fhir/repository.py`, which writes an
  `AuditEvent` (actor, action, entities). Writes are tagged `stafeta-demo` in demo mode so `make demo-reset` can wipe them — except AuditEvents, which are never deleted.
- **No PHI in logs**: structlog JSON with IDs, route templates, status and timings only; a redaction processor is
  the safety net. Errors are RFC 7807 `application/problem+json`, never stack traces.
- **IRIS limits**: community edition = 8 connections; the backend uses ≤ 3 DB-API connections and ≤ 4 HTTP
  connections. IRIS runs with 2 GB RAM; embeddings are computed in the backend, never inside IRIS.
- **Environments**: local `make up` = backend + mailpit against the IRIS in `.env` (team ACI); `make up-local` adds
  a local IRIS container (demo fallback). ACI storage is not persistent → `make iris-bootstrap && make seed`.
- **Time**: ISO 8601 with offsets, Europe/Prague; `STAFETA_DEMO_NOW` simulates "now" for the demo.
