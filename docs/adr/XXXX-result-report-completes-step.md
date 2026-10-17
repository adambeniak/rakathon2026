# ADR-NNNN: A received result report completes its pathway step; steps carry a named owner when one is known

- Date: 2026-10-17 · Status: proposed · Owner: P4

## Context
- The dress rehearsal (#132) showed the histology step `accepted`/overdue at the MDT although report 11 was in the
  case: an upload only closed *document requests*, never a pathway step; only `/demo/advance` replayed steps.
- In the demo the reports are uploaded (clock 20. 10.) **before** the pathway is launched (clock 2. 10.), and the
  clock then moves to 21. 10. with the switcher (`PUT /demo/clock`, no case id). A hook on the upload alone never
  fires after the step exists.
- Every pathway step had `owner = null` (#137); the board could not say who holds a step.
- The task machine (ADR-0003) allowed SYSTEM only for `result_delivered`, so no automated path could walk an
  accepted step to `vysledek_dorucen`.

## Decision
- **Mapping** (`app.domain.task_results`): a fixed table step code → LOINC type of the upload (the type #145 infers
  from the file name): `histology` → 11526-1, `eus-fnb` → 28570-0, `labs-dx` → 11502-2, `ct-thorax-abdomen` → 18748-4.
  Consultations and the MDT are not mapped (people close them).
- **When a report counts:** the step is `accepted` or `in_progress` (so its date is confirmed); the report was received
  at or before the clock; it was authored on or after the confirmed date (an older CT/lab report of the same type is
  not the result). The earliest received match wins. `requested` steps are never completed this way.
- **How:** the step walks the real task machine (`start` → `performed` → `result_delivered`, only the missing ones) as
  the SYSTEM role; the machine's guards still apply (a step whose predecessors are open stays as it is). `start` and
  `performed` now also allow SYSTEM; the API still refuses a SYSTEM actor, so no user reaches them through it. The
  AuditEvent agent is whoever triggered the run (the uploader, the coordinator advancing the demo, or the watchdog).
- **Triggers** (one function, `deliver_received_results`): `POST /cases/{id}/documents` after the report is stored
  (a failure is logged, the upload stays 201); `POST /demo/advance` after the clock moves and before the escalation
  round; every SLA watchdog round before escalating (catches the demo clock moving past an earlier upload).
- **Owner:** steps of KOC physicians start with the indicating physician as named owner; a practitioner who moves a
  step forward in the step's own role becomes its owner. Recording on behalf (coordinator for an external workplace)
  never sets the owner, so the owner role and the board lane do not change. Steps without a named person render as
  "Vlastník: nepřiřazeno".

## Consequences
- The board, `/alerts` and the handover agree once a result is in the case; no contract change.
- After the 21. 10. switcher the histology flips at the next watchdog round (default 60 s); `POST /demo/advance` to
  21. 10. does it at once.
- A wrongly named upload (wrong LOINC inference) could complete a step; the authored-date guard limits it to reports
  written on/after the examination date. Undoing a wrongly completed step needs a new transition (not in the PoC).
- The upload and the step completion are two writes (not one transaction); a failed step save is retried by the next
  trigger.
