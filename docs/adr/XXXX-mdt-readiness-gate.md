# ADR-XXXX: MDT readiness gate on `mark_ready_mdt` — computed on the server, waived only by a physician

- Date: 2026-10-17 · Status: proposed (additive contract change, P1 approves) · Owner: P1 · Issue: #68
- The number is assigned by the merge captain; until then the file is named `XXXX-<slug>.md`.

## Context
- The case machine (ADR-0003) guards `mark_ready_mdt` (kompletni → pripraveno_mdt) with a `Readiness` result from
  `pathway.readiness_gate`; #38 left the event off `POST /cases/{id}/transitions` because nothing supplied that input.
- A client-supplied readiness would bypass the gate. The gate vocabulary is the handover field status enum.

## Decision
- **Server-side only.** `fhir/readiness.py` builds the gate input: required items = `mdt_required_items` of the
  PlanDefinition(s) instantiated by the case's CarePlan(s); status of an item = status of its handover section in the
  persisted Composition for `as_of = case.mdt_start` (the default handover cut-off). The request body has no readiness
  field (`extra="forbid"`).
- **Item → section table** (`READINESS_SECTION`): histology → 14_histology, ct_staging → 12_examinations,
  tumour_markers → 13_labs, comorbidities → 6_comorbidities, performance_status → 9_performance_status,
  mdt_question → 5_mdt_question. The PlanDefinition has no pathway step for performance status, comorbidities or the
  MDT question, so pathway tasks alone cannot feed the gate; the handover is the single source of all six. A physician's hand-filled section counts as `complete`
  (as in the handover view).
- **Fail closed.** No CarePlan, no `mdt_start`, no persisted handover, an unmapped item or a missing section all mean
  "missing" / refusal (409 `guard_failed`). No LLM call happens inside a transition: the handover must have been opened
  (assembled and persisted) before the case can be marked ready.
- **Waivers.** `waivers: [{item, reason}]` on `mark_ready_mdt` only. The signer and role are the acting user's, never
  client values; only `koc_physician` (the machine's role check comes first, so others get `forbidden_role`). Every
  waiver that actually lifts a blocker is written as a `Provenance` (activity `waive-readiness`) in the same
  transaction as the Task update and the `AuditEvent` (whose payload lists `waived`). A waiver for an item that is not
  blocking is ignored; an unknown item, a blank reason or a duplicate is 422.
- `reopen` (reason required) is enabled on the same endpoint; it needs no extra input.

## Consequences
- Contract: additive (`TransitionRequest.waivers`, `ReadinessWaiver`); P3 runs `pnpm gen:api`.
- The persisted Composition is a snapshot: documents received after it was persisted do not change the gate until the
  handover is re-assembled for the same `as_of` (existing idempotent-persist behaviour). Not solved here.
- New extension `readiness-item` and activity code `waive-readiness` are listed in `docs/fhir-mapping.md`.
