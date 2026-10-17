# ADR-XXXX: `guard_failed` problems name the blocking readiness items in a structured `blocking_items` field

- Date: 2026-10-17 · Status: accepted (additive contract change approved by the repo owner) · Owner: P1

## Context
- A refused `mark_ready_mdt` answers 409 problem+json with `code` = `guard_failed`. The UI needs the blocking
  readiness items to offer the physician's waiver form.
- Until now the items existed only inside the Czech `detail` sentence ("Připravenost k MDT není splněna, chybí: a, b"),
  and the frontend parsed it with a regex (`features/mdt/api.ts` `blockingItems`). When #107 translated the sentence,
  the waiver form silently broke (#135, #141). Any later rewording would break it again (#140).
- The state machine already has the items in structured form (`Readiness.missing`, computed server-side by
  `readiness_gate`; never taken from the client).

## Decision
- `ProblemDetails` gains an optional `blocking_items: list[str] | None`. It is present only on a `guard_failed`
  problem whose guard can name the blocking items structurally — today only `mark_ready_mdt` with an unmet gate. It
  holds the readiness item keys that block and are not waived (English identifiers, e.g. `performance_status`, the
  same keys as the waiver `item` and `GET /cases/{id}/readiness`). It is omitted (never `[]`) on every other problem,
  including `guard_failed` refusals where readiness cannot be established at all.
- Plumbing: `case_machine._g_ready` returns a `GuardFailure(detail, blocking_items)` instead of a bare string;
  `TransitionError` carries the optional `blocking_items`; the API error handler copies it into the problem body.
  Nothing parses the sentence on the server either.
- The Czech `detail` sentence is unchanged and remains text for people only. Programs branch on `type`, `status`,
  `code` and `blocking_items`.
- In the same change the `ProblemDetails` example and the error response descriptions in the contract use the Czech
  texts the API actually sends (#116); a test keeps the descriptions in step with `STATUS_TITLES`.

## Consequences
- The UI can drop the regex and read `blocking_items` (follow-up issue, P3: `features/mdt/api.ts`); until then the
  sentence keeps its exact wording so the old parser still works.
- Rewording `detail` no longer risks breaking the waiver form once the frontend switched.
- Additive only: older clients ignore the field; `make contract` and `pnpm gen:api` regenerate the client types.
- Another guard that wants to name items structurally returns a `GuardFailure`; the item keys must stay stable
  identifiers because the UI maps them to Czech labels (`mdt.items`).
