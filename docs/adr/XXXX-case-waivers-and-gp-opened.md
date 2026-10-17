# ADR-XXXX: Read back readiness waivers and the GP's opening of the conclusion on the case

- Date: 2026-10-17 · Status: proposed (additive contract change, approved by the repo owner) · Owner: P4 ·
  Issues: #131, #113
- The number is assigned by the merge captain; until then the file is named `XXXX-<slug>.md`.

## Context
- A KOC physician may waive a blocking readiness item on `mark_ready_mdt` (ADR "MDT readiness gate"). The waiver was
  written as `Provenance` + `AuditEvent` only; no API read and the MDT record DOCX did not show it (#131).
- `gp_opened` is an audit-only event (no state change, `case_machine.py`). The coordinator's close warning cannot tell
  whether the GP opened the conclusion (#113).

## Decision
- **Contract (additive, optional).** `CaseSummary.gp_opened_at: date-time | null` (so also on `CaseDetail` and on every
  transition response) and `CaseDetail.readiness_waivers: RecordedReadinessWaiver[]` (default `[]`) with
  `{item, reason, waived_by (display name | null), waived_at}`. The new schema is named `RecordedReadinessWaiver`
  so the request model `ReadinessWaiver` keeps its name in the generated client.
- **Source of truth = what the transition wrote**; nothing new is stored and the write path is unchanged.
  - `gp_opened_at` = the earliest `recorded` of the business AuditEvents
    `AuditEvent?entity=Task/<case task>&subtype=<audit-event-code>|gp_opened`. Null = no opening recorded; the API
    never states "not read".
  - Waivers = `Provenance?target=Task/<case task>` with activity `waive-readiness` (filtered in code: `activity` is not
    an R4 Provenance search parameter), mapped back by `mappers/readiness.waiver_from_provenance`. The stringified
    `waived` detail of the AuditEvent is not parsed.
- **Waivers in force.** Only in `pripraveno_mdt` and later (a reopened case in `kompletni` has none); the latest
  waiver per item; waivers written before the last `reopen` AuditEvent are dropped. Write order uses the server's
  `meta.lastUpdated` because the demo clock stands still (every business time is equal); without it the business
  times are compared in whole seconds.
- **Search gating.** The AuditEvent search runs only in `zpetna_vazba_odeslana` / `uzavreno` for `gp_opened` (the
  machine accepts the event only there), so the case list adds no request for earlier cases; the Provenance search runs
  only for the detail and the MDT record. The subtype filter is repeated in code, since every audited read of the case
  names the same Task.
- **Visibility (minimisation).** Waivers (free-text reason + signer) are read only for the KOC team (coordinator,
  koc_physician, koc_staff) and the system actor; for the GP and the insurer's reviewer `readiness_waivers` is `[]`
  and no Provenance is read. `GET /cases/{id}` itself still has no membership check (pre-existing, see the issue).
- **Audit.** Every waiver Provenance read (also one no longer in force) is named in the caller's audited read
  (`GET /cases/{id}`) or in the MDT-record export AuditEvent. Reading AuditEvents is not itself audited (no clinical content, no recursion).
- **MDT record.** Each waiver is printed next to the item's section: histology / ct_staging / tumour_markers →
  section 5, comorbidities → section 4, performance_status / mdt_question → their appendix C section; an unmapped item
  gets its own appendix C entry. Wording: "Prominuto lékařem (připravenost k MDT – <položka>): <jméno>, <datum čas>,
  důvod: <důvod>" — the reason verbatim, sanitised like every value (birth numbers redacted). No clinical wording is
  added.

## Consequences
- The `subtype` search on AuditEvent is a standard R4 parameter but not yet verified on IRIS (Docker was off); if
  IRIS rejected it, `GET /cases` for a case past the feedback would fail. Verify with `make test-iris-local`.
- The UI does not use the fields yet: the MDT screen and the close warning are a frontend follow-up.
