# ADR-0002: Evidence-locked extraction — no value without a verbatim quote

- Date: 2026-10-16 · Status: accepted · Owner: P1 (architect), implemented by P2

## Context
- Clinicians must be able to trust every value in the handover and the MDT record; LLMs hallucinate, flip
  negations ("neguje"), mix dates and units.
- The brief says: take data as written, do not infer, mark what is missing (e.g. never derive ECOG from "soběstačná").
- AI may quote, structure and flag inconsistencies, but must not give clinical advice (MDR boundary).
- The golden set (`data/golden`) defines what correct looks like, including which fields are missing or stale.

## Decision
1. Every extracted value is a `Fact` with `evidence: [{doc_id, quote, char_start?, char_end?}]`
   (`app/domain/evidence.py`). `doc_id` is the source file stem.
2. **Evidence lock**: a fact is accepted only if each quote occurs verbatim (after the same whitespace/dash/Unicode
   normalisation as the document text) and numeric values in the fact appear inside the quote. Rejected facts are
   logged by id and reason and never reach the handover.
3. If no source states a value, the field status is `missing` (with a reason and a suggested owner) — never guessed.
   The status enum is shared with the golden file: `complete | partial | missing | stale | needs_clarification |
   complete_with_conflict | generated_with_citations`.
4. Generated text (epicrisis) may only use accepted facts and must cite them per sentence; it stays a draft
   ("Návrh AI") until a physician confirms it, recorded as `Provenance`.
5. The as-of rule applies before extraction results are used: authored ≤ as_of AND received ≤ as_of.

## Consequences
- Easier: hallucination rate is measurable (target 0), every UI value can show its source (`EvidenceChip`),
  reviewers can audit quickly.
- Harder: paraphrased or inferred values are dropped even when "obviously right"; normalisation must be identical on
  both sides; recall depends on prompt quality.
- Watch: `make eval` gates — evidence validity 100 %, hallucinations 0, as-of leakage 0; the golden file uses the
  key `doc` where the contract uses `doc_id` (the eval maps it).
