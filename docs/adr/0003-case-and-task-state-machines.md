# ADR-003: Case and task state machines are explicit, table-driven pure functions

- Date: 2026-10-16 · Status: accepted · Owner: P4 (workflow)

## Context
- The brief demands that at every moment it is clear where the case is, who holds the baton and by when the next step is due.
- "A sent request is not an ordered examination" (FBMI): task progress must be modelled separately from the request.
- Demo timing depends on a simulated clock (`STAFETA_DEMO_NOW`) and Czech working days (28. 10., 17. 11. are holidays).
- Domain logic must be testable without IRIS, FHIR or HTTP (`backend/app/domain` is pure).

## Decision
- `case_machine.py` and `task_machine.py` hold one rule table each (state · event · roles · guard · next state · baton ·
  notifications). Functions take the current model and return a new one plus `DomainEvent`s (audit, notification,
  escalation); persistence and delivery are the caller's job. Anything not in the table raises `TransitionError`
  (subclass of `ConflictError` → 409). Table documented in `contracts/case-states.md`.
- Queue buckets: Nový = only `odeslano`; `triage` and later = Aktivní; Odložený = flag `odlozeny`.
- The machine owns the baton **role** (`Case.baton_role`); the concrete person (`baton_holder`) is assigned by the caller.
  No separate MDT role: the MDT is KOC physicians.
- MDT conclusion: only `koc_physician`, only at/after `mdt_start`, and only with `confirmed_by` (clinician id) — human in the loop.
- Tasks: acceptance requires `order_confirmed` with place and date; `completed` requires a delivered result; start requires
  finished dependencies. Deadline = min(`due`, `sla_due`); escalation fires once, on the first day after the deadline.
- `clock.py` is the only place that reads the time (`STAFETA_DEMO_NOW`); working-day arithmetic lives there too.
- The pathway template is a FHIR `PlanDefinition` (`iris/fhir/plandefinition-pancreas-dx.json`) read as parsed JSON by
  `pathway.instantiate`; all offsets are labelled DEMO ASSUMPTION. The readiness gate (`pathway.readiness_gate`) blocks only
  on `missing`; partial/stale/conflicting items are warnings. Waivers: physician + non-empty reason.

## Consequences
- Easy: exhaustive table-driven tests (every allowed and every forbidden transition), predictable 409s for the UI.
- The API layer must load the PlanDefinition, supply guard facts (`CaseContext`) and persist returned events as AuditEvent.
- `Settings.now()` still has its own env handling; it should delegate to `app.domain.clock` when the API wires the machines.
- New FHIR code systems/extensions (`CodeSystem/pathway-action`, `CodeSystem/stafeta-role`, `StructureDefinition/{due-rule,
  sla-rule,place,owner-role,mdt-required-items}`) need an entry in `docs/fhir-mapping.md`.
