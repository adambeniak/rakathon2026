# ADR XXXX: handover `finding_ids` and `CaseSummary.baton` (additive)

Status: accepted (repo owner delegated the design; additive contract change) · Issues: #179, #180, #186

## Context
- #179: the MSW mock linked missing / stale / needs_clarification findings to handover sections through `conflicts`,
  the backend only linked contradicting findings. `conflicts` is documented as "findings that contradict the value"
  and feeds the Nesouhlasí counter (`case_counts.py`), the "nesoulad" lines of the MDT record and the export, and the
  carry-over comparison of confirmed sections.
- #180: the queue card picked its action text from the case state alone, so in `zpetna_vazba_odeslana` it said
  "Potvrdit přijetí závěru" also after `delivery_confirmed`, when the coordinator holds the baton to close.

## Decision
1. `HandoverFieldBase.finding_ids`: ids of every finding whose `field` names the section (any kind), plus the
   `conflicts` (a superset of them). `conflicts` keeps its meaning; status logic, counters, MDT record, export and
   carry-over are unchanged. The UI reads `finding_ids` (falls back to `conflicts`) and labels each finding by `kind`.
   The mock sends `conflicts` = contradicting ids only and `finding_ids` = all.
2. `CaseSummary.baton = {role, action}`, computed in `app.domain.case` (`Case.current_baton_role`,
   `Case.next_action`) from the state, the machine's `baton_role`, `delivery_receipt` and the postponed flag.
   `action` ∈ `CaseAction` (accept_case … close_case, await_external, none); the UI maps it to Czech text in
   `i18n/cs/common.ts` (`caseActions`) and never derives it. `gp_opened` does not move the baton
   (contracts/case-states.md), so `gp_opened_at` is not an input.
3. `POST /cases/{id}/tasks` lists 409 (closed case, behaviour from PR #187).

## Consequences
- Live still emits only the C1/C2 date-conflict findings: missing / stale / needs_clarification exist there only as
  section statuses. Emitting them as findings needs messages, severities and MDT-record wording (P2 + clinician);
  tracked separately. With this ADR the contract is ready for them.
