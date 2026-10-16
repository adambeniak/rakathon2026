<!-- WHO: P2 · TOOL: Claude Code Opus 5.5 (P1's seat, or Opus on your plan) · MODE: PLAN · WHEN: F3 (00:00–04:00, "sova" shift) -->

ROLE: Clinical data quality engineer. You build explainable checks that a coordinator and a physician trust.

CONTEXT: Facts (F1-3) and the assembled handover (F2-2) exist. `expected_findings` in the golden file lists 14 findings
as of the MDT start (C1–C3, M1–M3, S1, D1–D2, T1, X1, X4, Q1, N1); `post_mdt_findings` lists X2–X3, raised only when the
MDT conclusion (written after as_of) is checked against earlier documents. Read AGENTS.md, the extraction-eval skill, the domain clock/working-days.

GOAL: `detect_findings(case_id, as_of) -> list[Finding]` that raises every expected finding with evidence and a suggested
action, mostly via deterministic rules, with an LLM only as a second opinion.

RULES (deterministic, each a small module with its own tests)
R1 date order inside a document: drug pause/resume vs procedure date (C1)
R2 specimen collection date ≤ report issue date and = procedure date (C2)
R3 promised turnaround ("do N pracovních dnů") vs actual issue date (C3)
R4 required items per pathway missing (M1 ECOG, M2 TNM, M3 contact e-mails)
R5 stale vitals at as_of (S1)
R6 planned item with passed date and no result document (D1 GP control lab 9. 9.)
R7 referenced-but-not-attached reports (D2)
R8 documents after as_of (T1)
R9 ordering/indicating practitioner ≠ who ordered the task (X1)
R10 information present earlier but contradicted or ignored later (X2 consent to share with daughter)
R11 role mismatch between MDT member role and assigned action (X3) — flag, never judge clinically
R12 identity/insurer consistency across documents (same RČ, name; insurer code → name; X4 info)
R13 MDT question too generic (Q1); R14 "not documented" facts that the MDT relies on (N1 biliary drainage)

LLM SECOND OPINION
One call over the accepted facts (IDs + quotes) asking for contradictions the rules may miss. Output must cite fact IDs;
anything without two citable sources is dropped. Mark these findings `source: ai` with lower severity until confirmed.

OUTPUT MODEL
Finding {id, kind, severity, title_cs, explanation_cs (neutral, no clinical advice), evidence[{doc_id, quote}],
suggested_action {type: verify | request_document | assign_task | exclude, owner_role, due}, status: open | resolved |
dismissed(reason)}. Persist as FHIR `DetectedIssue` (patient, evidence → DocumentReference, mitigation for resolution)
and map to Tasks when the coordinator clicks "Vytvořit úkol".

API: `GET /api/cases/{id}/findings?as_of=`, `POST /api/findings/{id}/resolve|dismiss|create-task`.

ACCEPTANCE
- [ ] `make eval`: finding recall 14/14 as of 21. 10. (+ X2, X3 on the MDT conclusion), precision ≥ 80 %, every finding has ≥ 1 verbatim evidence quote
- [ ] Wording reviewed by `clinical-safety-reviewer` (no advice, neutral Czech)
- [ ] PR `ai/consistency-detector`
