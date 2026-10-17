# ADR-XXXX: A role denial of a state-machine transition answers 403, not 409

- Date: 2026-10-17 · Status: accepted (decided by the orchestrator under the repo owner's delegation, #136) · Owner: P4

## Context
- The state machines refuse a wrong role with `TransitionError("forbidden_role", …)`. `TransitionError` is a
  `ConflictError`, so the API answered `409 …/problems/conflict` for it.
- Every other endpoint answers the same kind of denial ("your role may not do this") with
  `403 …/problems/forbidden` (`ForbiddenError`), e.g. confirming a handover section as the coordinator.
- Clients, and a future audit of denials (#84), could not tell authorisation from state conflicts by status alone
  (found in the dress rehearsal, #136).

## Decision
- A `TransitionError` with `code` = `forbidden_role` maps to **403**, problem type `forbidden`, title
  "Přístup byl odepřen" (the title of every other role denial; the code-specific title is dropped). The body keeps
  `code: forbidden_role` and the machine's Czech `detail`.
- 409 `conflict` stays for state conflicts only: `invalid_transition`, `guard_failed`, `case_postponed`.
- The mapping lives in `app/api/errors.py` (`_domain_status`), so it applies to every route that surfaces a
  `TransitionError`: `POST /cases/{id}/transitions` (case machine), `POST /tasks/{id}/transitions` (task machine,
  which replaces the 409 in ADR coordination-api) and `POST /cases/{id}/document-requests`. The domain is unchanged.
- Contract: additive. 403 is documented on these routes, 409 stays documented for the conflict codes, and
  `contracts/case-states.md` describes the split.

## Consequences
- One status per meaning: 401 not identified, 403 not allowed, 409 not now.
- Clients that treated every refused transition as 409 must also handle 403 (the generated client already types it).
  The UI shows the API's title and detail for both, so no screen depends on the old status.
- No audit of denials exists yet (#84). When it is added, it can key on 403 for all authorisation denials.
