# ADR-XXXX: Coordination API — indicating physician, chained verbs, demo role header, on-behalf recording

- Date: 2026-10-16 · Status: proposed (contract change, P1 approves) · Owner: P4 (workflow)
- The number is assigned by the merge captain; until then the file is named `XXXX-<slug>.md` (rule for all agents).

## Context
- The coordinator launches the pathway "Karcinom pankreatu – diagnostika" and everyone must see who holds the baton.
- The task machine has seven events; the UI needs five verbs. The API had no notion of an acting role (always `system`).
- External workplaces (CT, laboratory, pathology) do not use Štafeta in the PoC; they report by mail/eHealth.
- The Docker image contains only `backend/`, so the PlanDefinition must come from IRIS, not from a file.
- Launching a pathway creates planned orders (e.g. the invasive EUS-FNB). Choosing the examination set is a clinician's
  decision, so the launch must say which physician indicated it (clinical-safety review, M2).

## Decision
- **Indicating physician (chosen option).** The coordinator may launch the pathway, but the launch body requires
  `indicated_by` = business id of a KOC physician (PractitionerRole with role `koc_physician`). It is stored as
  `CarePlan.author` and `ServiceRequest.requester` of **every** order (one ServiceRequest per step, linked from the
  step Task through `Task.focus`), together with a `Provenance` (agent = the coordinator, `onBehalfOf` = the indicating
  physician) that targets the CarePlan and all ServiceRequests. All of it is written in the launch transaction.
  Without `indicated_by`: **422** "Sada vyšetření vyžaduje indikujícího lékaře KOC."; an unknown id or a person who is
  not a KOC physician is also 422 (Czech texts). The UI pre-fills the physician of the case and the coordinator confirms.
- New endpoints: `POST /api/cases/{id}/pathways`, `GET /api/cases/{id}/board`, `GET /api/cases/{id}/alerts`,
  `POST /api/cases/{id}/tasks`, `POST /api/tasks/{id}/transitions`. Contract in `contracts/openapi.json`.
- Transition verbs `confirm | perform | deliver_result | fail | cancel` chain machine events; the machine is unchanged
  except for the on-behalf rule below.
- Acting role: the one shared `security.current_actor` from `main` — the `X-Demo-Role` header, honoured only when
  `STAFETA_DEMO_MODE=1` (the single demo switch; outside it every request is 401), validated against the `Role` enum and
  mapped to a seeded person of that role from the directory. Default role `coordinator`. External workplaces cannot be
  selected (they do not use Štafeta), which is why the coordinator records their steps. The service also refuses the
  technical `system` actor. Real login replaces the header later (TODO #4).
- Case membership: board, alerts, launch, ad-hoc tasks and task transitions go through `authorize_case` (referring GP or
  staff of the managing KOC), like triage and ask; anyone else gets 403. The indicating physician is resolved through the
  shared directory.
- On-behalf: the coordinator may record `start | performed | result_delivered` for tasks owned by `external_workplace`.
  The AuditEvent agent carries an `on-behalf-of` extension, the task shows `recorded_on_behalf_by`, and recording
  `perform` for a workplace requires a note with the source of the information. A delivered result must reference a
  document of the patient that was received no later than the (demo) current time.
- Baton: the owner of the earliest-due open step the MDT waits for, except that the coordinator holds it while a step
  is not yet ordered (`awaiting_confirmation`) or a prerequisite failed (`dependency_failed`).
- PlanDefinition owner roles are changed so the board is meaningful (external steps → `external_workplace`, physician
  steps → `koc_physician`). The template is seeded by `url` in both seed scenarios and read from IRIS.
- SLA: `GET /alerts` computes overdue tasks at read time; a watchdog (every 60 s in demo mode) persists `escalated_at`
  once and audits it. There is no delivery channel yet (`app.notify`).
- Errors: refused task transitions are 409 problem+json with a machine-readable `code` (`invalid_transition`,
  `forbidden_role`, `guard_failed`) — the same convention as the case transitions on `main`; launch and ad-hoc task
  creation are coordinator-only (403), as is a non-participant of the case; a concurrent update or a lost launch race
  → 409 `conflict`.
- Tests marked `iris` create cases, tasks and care plans: they run against `make up-local` only and are skipped on a
  shared server unless `STAFETA_ALLOW_SHARED_IRIS_TESTS=1` (guard in `tests/conftest.py`).

## Consequences
- Easy: the UI gets one call per screen (board) and five verbs; the demo clock fully determines alerts; every order
  names the physician who requested it and who recorded it for them.
- Launch and ad-hoc task creation are coordinator-only (403).

## Remaining problems (not solved by this change)
- **Demo mode is the only guard of the role header.** `STAFETA_DEMO_MODE` defaults to on, so a deployment that forgets
  `STAFETA_DEMO_MODE=0` trusts the header and every caller can pick a role. The header is not authentication. Case
  membership is enforced, but task ownership is checked by role, not by person, until real login (#4).
- **The physician does not confirm in Štafeta.** The coordinator attests the indication (`Provenance` says "on behalf of");
  nothing proves the physician agreed. A confirmation by the physician (a Provenance signed by them) is a follow-up.
- **"The physician of the case" has no source.** The backend stores no responsible physician per case; the UI pre-fill
  needs one (e.g. a `responsible_physician` on the case, or the MDT chair). Until then the UI must offer a picker.
- **Order status.** A completed Task completes its ServiceRequest and a cancelled one revokes it; a failed step keeps its
  order `active` (R4 has no "failed" request status).
- **Lost race.** A second concurrent launch answers 409, but the `Provenance` has no identifier, so an orphan one can
  remain.
- The full list with proposed fixes and owners is `docs/known-issues.md`.
- **Not verified against a live IRIS:** `If-Match`, `urn:uuid` rewriting inside the transaction, the `part-of` search,
  `ServiceRequest`/`Provenance` acceptance. Verify on `make up-local` with `pytest -m iris` (never on the team ACI).
- `Case.baton_holder` of the case list is not synced from the board; the watchdog must run on one replica only.
- The demo fallback "seeded tasks via `make seed`" is not done: the story scenario seeds no step tasks, so the 16. 10.
  demo needs CT/EUS/labs moved by hand first (otherwise they alert too).
- UI wording (P3): show `objednano` as "Naplánováno dle šablony – čeká na objednání", not "Objednáno"; label
  `required_for_mdt` as "Podmínka připravenosti MDT", never "kritický"; mark demo-template dates "předpoklad dema".
