<!-- WHO: P2 · TOOL: Claude Code (Opus if available, else Sonnet 5.5) · MODE: PLAN · WHEN: F2 (20:00–24:00) -->

ROLE: Clinical data engineer turning verified facts into a structured, trustworthy handover.

CONTEXT: `backend/app/extraction` produces evidence-locked facts per document (F1-3). Read AGENTS.md, the
extraction-eval skill, data/golden/expected_handover_2026-10-21.json, contracts/handover.schema.json,
docs/fhir-mapping.md.

GOAL: Deterministic assembly of the 15-field handover (Handover_obsah) for a case and an as-of date, with per-field
status, evidence and a cited epicrisis; persisted as a FHIR Composition + Provenance; served by the API.

BUILD
1. `assemble_handover(case_id, as_of) -> Handover` (pure function over facts + document metadata):
   - as_of is a timestamp (MDT start 2026-10-21T08:00+02:00); include only documents with authored ≤ as_of AND received ≤ as_of (report excluded ones with reason)
   - per field merge rules: latest clinical date wins for vitals/labs (keep history), union for comorbidities and
     medications (dedupe by normalised drug name), examinations = one row per document with full text reference
   - status (same enum as data/golden): complete | partial | missing | stale (vitals older than 30 days at as_of —
     configurable, label as demo rule) | needs_clarification (MDT question too generic: no explicit question beyond
     "stanovení dalšího postupu") | complete_with_conflict (value present, a finding contradicts it — set by F3-1) |
     generated_with_citations (the epicrisis)
   - never fill a missing field from inference; `missing` carries a reason and a suggested owner
     (ECOG → ošetřující lékař KOC; e-mail → koordinátor/pacient).
2. Epicrisis (field 4): ONE LLM call that may only use the accepted facts passed in (as JSON with fact IDs); every
   sentence must end with citations like [F12]; post-check: every cited ID exists and every sentence has ≥ 1 citation,
   otherwise regenerate once, then fall back to a bullet list of facts. Label as "Návrh AI".
3. Persist: `Composition` (type: handover, status preliminary, sections = 15 fields, entries reference Observation/
   Condition/MedicationStatement/DocumentReference), `Provenance` per derived resource (entity = source
   DocumentReference, quote in an extension, agent = model Device). Confirmation by a physician:
   `POST /api/cases/{id}/handover/sections/{n}/confirm` (optional edited value) → Provenance with Practitioner +
   section marked confirmed; Composition becomes `final` when all sections are confirmed or explicitly accepted as missing.
4. API: `GET /api/cases/{id}/handover?as_of=2026-10-21` returns the handover JSON (validated against
   contracts/handover.schema.json) incl. `excluded_documents`; `GET .../handover/export?format=md` gives copyable text
   per section.
5. Eval: extend `backend/tests/eval` to compare assembled handover statuses and key values with the golden set.

ACCEPTANCE
- [ ] `make eval` → field status accuracy ≥ 14/15, evidence validity 100 %, as-of leakage 0, hallucinations 0
- [ ] For as_of 2026-10-21 reports 12–13 are listed as excluded; for as_of 2026-10-28 they are included
- [ ] ECOG = missing with owner; weight = stale (65 kg from 15. 9.); MDT question = needs_clarification
- [ ] Epicrisis: every sentence cited; run the `extraction-auditor` and `clinical-safety-reviewer` subagents and fix findings
- [ ] PR `ai/handover-assembly`
