# ADR-NNNN: The signed MDT conclusion completes the pathway's MDT step

- Date: 2026-10-17 · Status: proposed · Owner: P4 (mapping of the result: P1)

## Context
- `record_mdt_conclusion` stored the conclusion `Composition` and moved the case, but the pathway step `mdt` stayed
  `requested`/`objednano` (nobody confirms the MDT as an order). Since #133 `close` cancels every open step, so the
  MDT step ended as `cancelled` ("Případ uzavřen") although the meeting took place (#149), and time-to-MDT analytics
  could not read a completed MDT step.
- The task machine reaches `completed` only through `result_delivered`, which needs a result id; from `requested` the
  confirm/accept events allowed only the owner and the coordinator.
- ADR "result report completes step" (#132/PR #170) already walks steps to `vysledek_dorucen` as SYSTEM when a stored
  record proves the result.

## Decision
- **Proof:** the signed conclusion proves the MDT took place. After the sign-off transaction a second, idempotent write
  (`ClosedLoopWorkflow._complete_mdt_step`) walks the open `mdt` step of the case
  (`app.domain.task_results.complete_mdt_step`) through the real task machine as the SYSTEM role, applying only the
  events still missing (`order_confirmed` → `accept` → `start` → `performed` → `result_delivered`). Guards apply:
  a step whose predecessors (CT, histology, labs) are not completed stays as it is.
- **Machine change:** `order_confirmed` and `accept` now also allow SYSTEM (like `start`/`performed`/`result_delivered`
  since #132). `CoordinationService.transition` still refuses a SYSTEM actor, so no user reaches them through the API.
- **Confirmed place and date** of a never-confirmed MDT step: the step's own place (the template has one), else the
  managing KOC's name; date = the case's `mdt_start` (the time the handover is cut at), else the sign-off time.
- **Result:** the conclusion's business id (`sid/mdt-conclusion|<case>@<UTC instant>`), known before the transaction.
  `Task.output` of the `mdt` step is a `valueReference` of type `Composition` by that identifier (other steps keep
  `source-document`); the reader accepts both systems.
- **Failure / reconcile:** the second write never fails the sign-off (a refused guard is logged at info, a failed
  save with the exception). `close` reconciles: an MDT step still open at close is completed with the latest signed
  conclusion in the close transaction instead of being cancelled; only if the machine refuses it is it cancelled.
- **Audit:** the sign-off write is audited by the repository with the signing physician as agent (like #132: who
  triggered the run); at close each machine event is an AuditEvent on the step with the coordinator as agent and
  `actor_role = system` in the payload. The step's named owner does not change.

## Consequences
- After `close` the board shows the MDT step as completed (`Výsledek doručen`), not cancelled; no alert or escalation
  remains for it. No contract change.
- The board card shows the conclusion's business id as the result id (`Výsledek: <case>@<instant>`); a friendlier label
  is a UI follow-up (#184).
- If the MDT was held with an open (waived) predecessor, the guard keeps the MDT step open and `close` still cancels
  it; completing it needs a human decision on waivers in the task machine (#183).
