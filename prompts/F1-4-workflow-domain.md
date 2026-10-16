<!-- WHO: P4 (workflow, QA, pitch) · TOOL: Claude Code Sonnet 5.5 (or Copilot GPT-6.1 Sol) · MODE: PLAN · WHEN: F1 (16:45–20:00), in spikes/workflow until P1's skeleton is merged -->

ROLE
You are a senior backend engineer with healthcare workflow experience (care pathways, referrals, task management,
audit). You model processes as explicit, testable state machines.

READ FIRST
AGENTS.md, .claude/skills/demo-flow, .claude/skills/czech-clinical-docs, data/raw/Zadani_ulohy.docx,
docs/challenge-brief.md (VZP slides: queue Nový/Aktivní/Odložený, 8 case states, task sets, "kdo je na tahu").

GOAL
Pure-Python domain logic for the case and its tasks, plus the diagnostic pathway template, in `spikes/workflow/`
(self-contained, inline deps, pytest). After P1's foundation merge, move it to `backend/app/domain/` (new files only:
`case_machine.py`, `task_machine.py`, `pathway.py`, `clock.py`) in PR `wf/domain-logic`.

IN SCOPE
1. Case state machine (states: odeslano → triage → ceka_na_podklady ⇄ kompletni → pripraveno_mdt → zaver_mdt →
   zpetna_vazba_odeslana → uzavreno; plus flags `odlozeny` (postponed) and queue bucket nový/aktivní/odložený).
   Each transition: allowed roles, guard (e.g. pripraveno_mdt only if readiness gate passed or waived by a physician with
   a reason), side effects as returned events (AuditEvent payload, notifications), and who holds the baton afterwards.
2. Task state machine: requested → accepted → in_progress → completed | failed | cancelled, with businessStatus
   objednano → potvrzeno → provedeno → vysledek_dorucen (FBMI principle: "odeslaná žádanka ≠ objednané vyšetření").
   Overdue detection and escalation event (to coordinator) given a due date and the demo clock.
3. Pathway template "Karcinom pankreatu – diagnostika" as a FHIR R4 `PlanDefinition` JSON in
   `iris/fhir/plandefinition-pancreas-dx.json` with actions: CT hrudníku a břicha (pankreatický protokol), EUS-FNB,
   odběry (KO, biochemie, CA 19-9), histologie, algeziologie, psychoonkologie, MDT; `relatedAction` ordering
   (e.g. histology after EUS-FNB; MDT after CT + histology + labs). Default due-date offsets are DEMO ASSUMPTIONS —
   label them so in the JSON (`description`) and in the UI; they are not clinical guidelines.
   `pathway.instantiate(plan, case, start_date) -> list[Task]` with owners and due dates.
4. Demo clock: `clock.now()` honours `STAFETA_DEMO_NOW`; all logic uses it (never datetime.now()).
5. Working-days helper (Czech holidays 28. 10., 17. 11. …) for SLA such as "výsledek do 3 pracovních dnů".
6. Readiness gate for MDT: required items per pathway (histology, CT staging, tumour markers, comorbidities,
   performance status, MDT question) → {ready: bool, missing: [...], waived: [...]}.
7. `docs/demo-script.md`: minute-by-minute 5-minute demo for the 6 steps (from the demo-flow skill), who clicks what,
   what the presenter says (Czech), fallback per step.

OUT OF SCOPE
API endpoints and FHIR persistence (F2-4), UI (P3), E2E (F4-1).

PLAN FIRST
Show the transition tables (state · event · role · guard · next state · baton holder · side effects) and the pathway
actions with dependencies. Wait for approval.

ACCEPTANCE
- [ ] Table-driven unit tests for every allowed and every forbidden transition
- [ ] Instantiating the pathway for 2. 10. 2026 yields tasks whose order and dependencies match the demo story
      (CT 8. 10. in KOC 1, EUS-FNB 12. 10., labs 15. 10., histology 19. 10., MDT 21. 10.)
- [ ] Histology SLA from 12. 10. resolves to Thu 15. 10. and raises an escalation on 16. 10.
- [ ] PR `wf/domain-logic` after P1's merge
