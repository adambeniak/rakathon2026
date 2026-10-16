<!-- WHO: P4 (or a Copilot cloud agent issue with GPT-6.1 Sol if P4 is busy) · TOOL: Claude Code Sonnet 5.5 · MODE: normal · WHEN: F2 after F2-1 -->

ROLE: Backend engineer for care-pathway coordination.

CONTEXT: `backend/app/domain/pathway.py` and `task_machine.py` exist (F1-4); `iris/fhir/plandefinition-pancreas-dx.json`
is the template. Read the demo-flow skill (step 4) and docs/fhir-mapping.md.

GOAL: The coordinator launches the set "Karcinom pankreatu – diagnostika" and everyone sees who holds the baton.

BUILD
1. Seed the PlanDefinition into IRIS (conditional create by `url`). `POST /api/cases/{id}/pathways` {plan_url, start_date}
   → CarePlan + step Tasks (partOf case Task, owner, location = workplace, due, dependencies) in one transaction.
2. `POST /api/tasks/{id}/transitions` {event: confirm | perform | deliver_result | fail | cancel, note?, date?}
   with the task state machine; delivering a result can link a DocumentReference.
3. `GET /api/cases/{id}/board` → lanes by owner role (PL · Koordinátor · Lékař KOC · Externí pracoviště · Pacient),
   each task with state, due date, overdue flag, blocking dependencies, and the single "baton holder" of the case
   (owner of the earliest-due open task on the critical path).
4. SLA watchdog: `GET /api/cases/{id}/alerts` (and a periodic job every minute in demo mode) → overdue tasks and
   promised turnaround breaches, e.g. histology promised "do 3 pracovních dnů" after 12. 10. → escalation on 16. 10.
5. Single tasks: `POST /api/cases/{id}/tasks` for ad-hoc work (e.g. "Doplnit ECOG" assigned to the KOC physician).
6. Contract update via `make contract` (P1 approves) and a note to P3 for the board UI.

ACCEPTANCE
- [ ] With demo clock 2. 10. the pathway yields CT (KOC 1), EUS-FNB, odběry + TM, histologie, algeziologie,
      psychoonkologie, MDT 21. 10. with correct order; the board shows the baton holder
- [ ] Moving the demo clock to 16. 10. raises the histology escalation
- [ ] Unit + API tests; PR `wf/coordination`
