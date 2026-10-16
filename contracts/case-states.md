# Case states — DRAFT (owner of the logic: P4, issue #2)

Status: draft by P1 for F1. P4 refines guards and side effects in `backend/app/domain/case_machine.py`;
changes to codes or meanings go through an ADR (this file is a shared contract).

Source: VZP brief slide 10 (8 states) and slide 9 (coordinator queue). "At every moment it must be clear where the
case is, who holds the baton and by when the next step is due."

## Representation
- Domain: `app.domain.case.CaseState` (codes below), `Case.baton_holder` (`PartyRef`), `Case.next_deadline`.
- FHIR: coordinating `Task` (`code` = `coordinate-case`) with
  - `businessStatus` = `https://stafeta.example/fhir/CodeSystem/case-state|<code>`
  - `owner` = baton holder (PractitionerRole reference + business identifier + display), `performerType` = workflow role
  - `restriction.period.end` = next deadline; every change writes an `AuditEvent` (and later a `Provenance`).
- API: `CaseSummary.state`, `baton_holder`, `next_deadline` (`GET /api/cases`, `GET /api/cases/{id}`).
- UI labels come from `frontend/src/i18n/cs/` (the Czech labels below are the reference wording).

## States
| # | Code | Czech label | Queue bucket | Typical baton holder |
| --- | --- | --- | --- | --- |
| 1 | `odeslano` | Odesláno | Nový (čeká na převzetí) | Koordinátor KOC |
| 2 | `triage` | V triage | Aktivní | Koordinátor KOC |
| 3 | `ceka_na_podklady` | Čeká na podklady | Aktivní (Odložený while only an external step is pending) | External workplace / Koordinátor KOC |
| 4 | `kompletni` | Kompletní | Aktivní | Lékař KOC (review, readiness gate) |
| 5 | `pripraveno_mdt` | Připraveno k rozhodnutí/MDT | Aktivní | MDT (předseda MDT) |
| 6 | `zaver_mdt` | Závěr KOC/MDT | Aktivní | Koordinátor KOC (send result) |
| 7 | `zpetna_vazba_odeslana` | Zpětná vazba odeslána | Aktivní | PL (confirm receipt) |
| 8 | `uzavreno` | Uzavřeno | — (archive, audit trail kept) | — |

"Odložený" (postponed) is a **flag** on an active case (waiting for an external step), not a ninth state.

## Transitions (draft)
| From | Event | Allowed roles | Guard (draft) | To | Baton holder after | Side effects |
| --- | --- | --- | --- | --- | --- | --- |
| — | `referral_submitted` | gp | consent to share confirmed; patient identified by RČ | `odeslano` | coordinator of target KOC | AuditEvent; notify coordinator |
| `odeslano` | `taken_over` | coordinator | — | `triage` | coordinator | AuditEvent; GP sees "převzato" |
| `triage` | `documents_requested` | coordinator | ≥ 1 missing report requested (CommunicationRequest + Task) | `ceka_na_podklady` | owner of the earliest-due request | AuditEvent; requests sent |
| `triage` | `documents_complete` | coordinator | nothing missing | `kompletni` | KOC physician | AuditEvent |
| `ceka_na_podklady` | `documents_complete` | system, coordinator | all document requests fulfilled | `kompletni` | KOC physician | AuditEvent |
| `kompletni` | `documents_requested` | coordinator, koc_physician | a new missing item found | `ceka_na_podklady` | owner of the request | AuditEvent |
| `kompletni` | `ready_for_mdt` | koc_physician | MDT readiness gate passed, or waived with a reason | `pripraveno_mdt` | MDT chair | AuditEvent (+ waiver reason) |
| `pripraveno_mdt` | `mdt_concluded` | koc_physician (MDT) | MDT record exists and is confirmed by a physician | `zaver_mdt` | coordinator | Composition final; AuditEvent |
| `zaver_mdt` | `feedback_sent` | coordinator | MDT conclusion delivered to the GP (Communication) | `zpetna_vazba_odeslana` | GP | e-mail; delivery proof; reviewer of insurer informed |
| `zpetna_vazba_odeslana` | `receipt_confirmed` | gp, system | read receipt recorded | `uzavreno` | — | AuditEvent |
| any active | `postponed` / `resumed` | coordinator | reason required | (same state, flag on/off) | unchanged | AuditEvent |

Every transition not listed is forbidden → `409 problem+json` (`https://stafeta.example/problems/conflict`).

## Open questions for P4
1. Rejection of a referral ("nepřevzato", wrong KOC or not oncological): a separate terminal state, or `uzavreno` + reason?
2. Who may waive the readiness gate (any KOC physician or only the MDT chair), and must the waiver be visible in the MDT record?
3. Does `documents_complete` fire automatically (system) as soon as the last request is fulfilled, or only after the coordinator confirms?
4. Postponed flag: does it pause SLA/overdue escalation for external steps?
