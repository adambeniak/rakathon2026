# ADR-005: Referral intake, report requests and the mock actor

- Date: 2026-10-16 · Status: accepted · Owner: P4 (workflow)

## Context
Demo steps 1–2: the GP refers without a long form (prefill from the letter), the coordinator takes the case over and
requests the reports the letter lists but nobody attached. Several places needed a decision the brief left open.

## Decision
- **Prefill is a draft, nothing is persisted.** `POST /api/referrals/prefill` returns `Evidenced` values (verbatim quote or
  `missing`). The sex is not in the letter: it is derived from the RČ month and marked `derived` (the GP confirms it). The
  consent checkbox is never pre-ticked; statements from the letter are listed verbatim and stored on `Consent` as
  `consent-statement` extensions, not interpreted.
- **`POST /api/referrals` is stateless**: the browser re-sends the letter with the confirmed values (multipart `letter`,
  `attachments`, JSON `payload`). One transaction Bundle creates Patient (existing patient found by RČ is reused, never
  overwritten), RelatedPerson, Coverage, EpisodeOfCare, DocumentReference(s), ServiceRequest, case Task, Consent, a
  `Provenance` (GP confirmed the AI-assisted prefill; edited/added field *names*, `not-compared` if extraction was
  unavailable) and a business AuditEvent. A patient with an open EpisodeOfCare gets 409.
- **Priority and consent are what the GP confirmed**: `ReferralSubmission.priority` (never assumed urgent; the form preselects it
  only when the letter asks for urgency) and `consent_statements` (each must occur verbatim in the letter; negated or restricting
  statements are kept in the prefill). Only the coordinator links a report to a request; a same-day report from another
  workplace is `possibly_attached`, not `attached`.
- **Baton holder before anyone accepts** is a concrete PractitionerRole of the KOC (first coordinator) with a role-level
  display "Koordinátor KOC 2", as the seed does for the MDT chair. `contracts/case-states.md` stays unchanged: the holder is
  still a concrete role record; on `accept` it becomes the accepting person.
- **Report request = CommunicationRequest + Task `request-report`** with a deliberately small lifecycle
  (`requested/objednano` → `completed/vysledek_dorucen`, `domain/document_request.py`). The examination task machine is for
  ordering and performing steps; asking a workplace for an existing report does not need `potvrzeno/provedeno`.
  Due = end of the second working day (Europe/Prague).
- **One click**: `POST …/document-requests` creates the requests and, while the case is in `triage`, fires
  `request_documents` in the same transaction.
- **`podklady_kompletni` is the machine event `docs_received`**. Fulfilling the last open request of a case in
  `ceka_na_podklady` fires it as `system` in the same transaction; the upload response carries `case_event`.
- **Triage proposals** come from the examinations listed in the section "PROVEDENÁ VYŠETŘENÍ (VÝSLEDKY K DISPOZICI …)"
  of the letter only (not every `examination` fact), resolved to workplaces by directory rules (workplace name, else the named
  physician); unresolved ones stay empty for the coordinator. Proposals are recomputed from the stored letter on each call
  (a cache hit in demo mode); persisting derived facts belongs to the handover work.
- **Mock login, fail closed** (`security.actor.current_actor`, the one shared actor dependency): `X-Demo-Role` carries a `Role`
  value and is honoured only when `STAFETA_DEMO_MODE=1`; it is validated against the enum (`system`/`patient` cannot be chosen)
  and mapped to a seeded person of that role from the directory. Missing header in demo mode = coordinator. Outside demo
  mode every request is 401; there is no environment-name based fallback. Real authentication (#4) replaces this function and
  keeps its signature.
- **Upload limit before parsing**: `BodyLimitMiddleware` rejects by `Content-Length` and caps streamed bytes (413 problem+json,
  Czech); `Settings.upload_max_bytes` (default 10 MB). The prefill call is audited (`AuditEvent` action E, subtype `extract`,
  no entity: nothing is persisted).
- **Duplicate open case** answers 409 with a neutral Czech message; only the target KOC's episodes are considered.
- **Case Task round-trips all machine-owned fields** (baton role, resume fields, MDT start, flags) as extensions; the
  postponed flag is `Task.status = on-hold`. Writes use `If-Match` on the version that was read (412 → 409).
- **Case membership** (`authorize_case`): the referring GP, or staff of the managing KOC; `system` always. Applies to transitions,
  requests, proposals and uploads. Reads of the older `GET /api/cases*` are not filtered yet (issue #16); EpisodeOfCare.status is not synced yet (issue #15).
- **Case summary** carries `postponed`, `bucket`, `suspected_diagnosis` (+ evidence), `koc`, `referring_gp`; `counts` is null until the
  handover service exists (null, not 0).
- Events whose guards need data without an endpoint yet (`mark_ready_mdt`, `record_mdt_conclusion`, `send_feedback`,
  `delivery_confirmed`, `close`) answer 422 on `/transitions`.

## Consequences
- The UI gets stable 409 problem types with a machine `code`, and a one-click triage flow.
- Notifications returned by the machines are not persisted yet (`notify/` is empty); only audit events are.
- KOC 1 has no coordinator in the seed: referring to it is a 422 (`koc_without_coordinator`).
- New CodeSystems/extensions are listed in `docs/fhir-mapping.md`.

## Review follow-ups
- Case ids are `rakathon-<year>-<family>-<6 hex>` (collision-resistant without a reservation step); patient, contact and coverage are created
  with `ifNoneExist`. A report may be fulfilled while the case is postponed (the state stays; `docs_received` is fired after resume).
  Every upload PUTs the case Task with `If-Match`. Provenance also records cleared fields and diagnosis-code edits. The authored date is
  never taken from the receipt date. `CaseReader.load` audits its read.
- FHIR R4 `CommunicationRequest` has no `intent` element (that arrived in R5), so none is written.
