# ADR-XXXX: Case audit trail, timeline and messages read back from FHIR

- Date: 2026-10-17 · Status: proposed (additive contract change, approved by the repo owner) · Owner: P4 · Issue: #47
- The number is assigned by the merge captain; until then the file is named `XXXX-<slug>.md`.

## Context
The case tabs Audit, Časová osa and Komunikace ran on MSW mocks only. AuditEvents, the feedback `Communication` and
the report-request `CommunicationRequest`s were written but never read back.

## Decision
- **Endpoints (additive):** `GET /api/cases/{id}/audit?limit&offset` → `CaseAuditTrail {case_id, items[], total,
  offset, limit, truncated}`; `GET /api/cases/{id}/timeline` → `CaseTimeline {case_id, as_of, now, events[]}`;
  `GET /api/cases/{id}/messages` → `CaseMessage[]` (`kind` document_request | mdt_feedback, `status` open | fulfilled |
  cancelled | sent, `request` {request_id, status, due, exam_date, result_doc_id}, `delivery` {channel, receipt_id,
  gp_opened_at}).
- **Who:** KOC team of the case only (coordinator, koc_physician, koc_staff) + `authorize_case`; the role is checked
  before any read, so a refused caller causes no audited read. Every successful read is audited (search-type), the
  read of the audit trail included (it names the case Task, Patient, EpisodeOfCare, not every AuditEvent).
- **Nothing new is stored.** Sources: business AuditEvents (type `domain-event`) for case/task events,
  DocumentReference (authored/received), Task fields (`scheduled_at`, `escalated_at`, `result_doc_id`),
  CommunicationRequest.authoredOn, Communication.sent + SMTP Message-ID identifier, first `gp_opened`.
- **Minimisation:** the audit returns codes only (action, operation, record types, outcome, actor display + role).
  `entity.detail` is read only for `event/from/to/task_id/result_doc_id/receipt_id` (never `reason`/`waived`);
  `outcomeDesc` is never returned (only fixed backend prefixes classify `export`, `index`, `launch_pathway`, ...).
- **As-of:** `excluded_from_handover` is computed by the backend with `extraction.lock.as_of_exclusion` against
  `Case.mdt_start`; `null` without an MDT start. The frontend only renders it.
- **Layers:** domain records `domain/activity.py`; mappers `fhir/mappers/activity.py`; reader `fhir/case_records.py`;
  merge `timeline/events.py` (pure); route `api/routes/case_activity.py`.

## Consequences
- Search patterns not yet verified on IRIS: `AuditEvent?entity=a,b,c` (OR, chunks of 20) and `&type=<audit-type>|domain-event`;
  `Communication|CommunicationRequest?subject=Patient/x` filtered by `about` in code. Sorting is in code (no `_sort`):
  the whole trail is read per request (demo scale; `search_all` caps at 50 pages).
- Not in the trail: writes that name only other resources (handover Composition/Provenance).
- AuditEvents of reads use the repository clock (wall time) while domain events use the demo clock, so the audit
  tab mixes both in a demo with a moved clock (follow-up issue).
