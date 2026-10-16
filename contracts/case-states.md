# Case states (owner of the logic: P4; implemented in `backend/app/domain/case_machine.py`)

Status: final for F1 (ADR-003). The table below is implemented 1:1 by `case_machine._RULES` and tested in
`backend/tests/unit/domain/`; changes to codes or meanings go through an ADR (this file is a shared contract).

Source: VZP brief slide 10 (8 states) and slide 9 (coordinator queue). "At every moment it must be clear where the
case is, who holds the baton and by when the next step is due."

## Representation
- Domain: `app.domain.case.CaseState` (codes below), `Case.baton_role` (role that must act, owned by the machine),
  `Case.baton_holder` (`PartyRef`, the concrete person, assigned by the caller; cleared when the role changes),
  `Case.odlozeny` (postponed flag), `Case.bucket` (derived `QueueBucket`), `Case.next_deadline`.
- FHIR: coordinating `Task` (`code` = `coordinate-case`) with
  - `businessStatus` = `https://stafeta.example/fhir/CodeSystem/case-state|<code>`
  - `owner` = baton holder (PractitionerRole reference + business identifier + display), `performerType` = workflow role
  - `restriction.period.end` = next deadline; every change writes an `AuditEvent` (and later a `Provenance`).
- API: `CaseSummary.state`, `baton_holder`, `next_deadline` (`GET /api/cases`, `GET /api/cases/{id}`).
- UI labels come from `frontend/src/i18n/cs/` (the Czech labels below are the reference wording).

## States and queue buckets
| # | Code | Czech label | Queue bucket | Baton role after entering |
| --- | --- | --- | --- | --- |
| 1 | `odeslano` | Odesláno | **Nový** (čeká na převzetí) — the only state in Nový | coordinator |
| 2 | `triage` | V triage | Aktivní | coordinator |
| 3 | `ceka_na_podklady` | Čeká na podklady | Aktivní | coordinator |
| 4 | `kompletni` | Kompletní | Aktivní | koc_physician |
| 5 | `pripraveno_mdt` | Připraveno k rozhodnutí/MDT | Aktivní | koc_physician |
| 6 | `zaver_mdt` | Závěr KOC/MDT | Aktivní | coordinator |
| 7 | `zpetna_vazba_odeslana` | Zpětná vazba odeslána | Aktivní | gp |
| 8 | `uzavreno` | Uzavřeno | Archiv (audit trail kept) | — |

**Odložený** is the flag `odlozeny` on `triage`, `ceka_na_podklady`, `kompletni` or `pripraveno_mdt` (waiting for an
external step); it overrides the bucket and sets the baton role to `external_workplace`. The MDT is a meeting of KOC
physicians, so there is no separate MDT role: MDT-side actions belong to `koc_physician`.

## Transitions
Roles are `app.domain.common.Role` values. Every transition writes an AuditEvent payload (`DomainEvent` kind `audit`;
ids, states and actor role only) and returns notifications as events; persisting them is the caller's job.

| State | Event | Roles | Guard | Next state | Baton after | Side effects |
| --- | --- | --- | --- | --- | --- | --- |
| — | `submit` (`submit_referral`) | gp | consent confirmed; target KOC; patient id | `odeslano` | coordinator | audit(create); notify coordinator `case.new` |
| `odeslano` | `accept` | coordinator | — | `triage` | coordinator | audit; notify GP `case.accepted` |
| `triage` | `request_documents` | coordinator | ≥ 1 open document-request task | `ceka_na_podklady` | coordinator | audit; notify GP `case.documents_requested` |
| `triage` | `mark_complete` | coordinator | no missing blockers | `kompletni` | koc_physician | audit |
| `ceka_na_podklady` | `docs_received` | coordinator, system | no open document-request tasks | `kompletni` | koc_physician | audit |
| `kompletni` | `missing_found` | coordinator, koc_physician | reason | `ceka_na_podklady` | coordinator | audit |
| `kompletni` | `mark_ready_mdt` | koc_physician | readiness gate passed, or every missing item waived by a physician (non-blank clinician id) with a non-empty reason | `pripraveno_mdt` | koc_physician | audit incl. waivers (item, by, reason); notify `case.ready_for_mdt` |
| `pripraveno_mdt` | `reopen` | koc_physician | reason | `kompletni` | koc_physician | audit |
| `pripraveno_mdt` | `record_mdt_conclusion` | koc_physician | `now ≥ mdt_start`; conclusion non-empty; **`confirmed_by` (clinician id) set** | `zaver_mdt` | coordinator | audit incl. `confirmed_by`; sets `conclusion_confirmed` |
| `zaver_mdt` | `send_feedback` | coordinator | `conclusion_confirmed`; GP recipient | `zpetna_vazba_odeslana` | gp | audit; notify GP `feedback.sent`, reviewer `feedback.sent_reviewer` |
| `zpetna_vazba_odeslana` | `delivery_confirmed` | system | receipt id | same | coordinator | audit incl. `receipt_id`; sets `delivery_receipt` |
| `zpetna_vazba_odeslana` | `gp_opened` | gp, system | — | same | unchanged | audit with action `read` (audited read receipt) |
| `zpetna_vazba_odeslana` | `close` | coordinator | `delivery_receipt` | `uzavreno` | — | audit |
| `triage`, `ceka_na_podklady`, `kompletni`, `pripraveno_mdt` | `postpone` | coordinator | reason; `resume_on` / external step | same, `odlozeny=true`, `resume_on` stored | external_workplace | audit incl. reason and `resume_on` |
| same four | `resume` | coordinator | case is postponed | same, `odlozeny=false`, `resume_on` cleared | role before postponing | audit |

While `odlozeny` is true every event except `resume` fails with `case_postponed`. Every transition not listed is
forbidden: `TransitionError` (a `ConflictError`) with `code` ∈ `invalid_transition | forbidden_role | guard_failed |
case_postponed` → `409 problem+json` (`https://stafeta.example/problems/conflict`). `uzavreno` is terminal.

## Task state machine (`task_machine.py`)
`status`: `requested → accepted → in_progress → completed | failed | cancelled`. `business_status` only moves forward:
`objednano → potvrzeno → provedeno → vysledek_dorucen`.

| Event | From status | Roles | Guard | Result |
| --- | --- | --- | --- | --- |
| `order_confirmed` | requested | owner, coordinator | **place and timezone-aware date/time** confirmed | business `potvrzeno`, `scheduled_at` set |
| `accept` | requested | owner, coordinator | business `potvrzeno` (a sent request ≠ an ordered examination) | `accepted` |
| `start` | accepted | owner | all `depends_on` tasks completed | `in_progress` |
| `performed` | in_progress | owner | business `potvrzeno` | business `provedeno` |
| `result_delivered` | in_progress | owner, system | business `provedeno`; result document id | `completed`, `vysledek_dorucen` |
| `fail` | accepted, in_progress | owner, coordinator | reason | `failed`; reason in audit; notify coordinator |
| `cancel` | requested, accepted, in_progress | coordinator | reason | `cancelled`; reason in audit |

**Overdue / escalation:** deadline = earlier of `due` and `sla_due`. Once the deadline *day* is over (Prague), an open
task yields one `escalation` event to the coordinator (`escalated_at` makes it fire once). Histology in the demo:
`due` = 19. 10. (planned result), `sla_due` = 15. 10. (3 working days from 12. 10.) → escalation on Fri 16. 10.
(`basis: sla`). Template due dates are **demo assumptions** (`Task.demo_assumption`), not clinical guidance.
Postponing a case does not pause task escalation (open question 4 → no).

## Decisions on the former open questions
1. Rejection of a referral stays out of scope for F1 (not modelled).
2. Only a physician (`koc_physician`) may waive the readiness gate; the waiver (item, by, reason) is in the audit payload
   and must appear in the MDT record.
3. `docs_received` is a coordinator or system event with an explicit guard; the caller decides when to fire it.
4. The postponed flag does not pause task SLA/escalation.
