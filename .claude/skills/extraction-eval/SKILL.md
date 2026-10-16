---
name: extraction-eval
description: How to evaluate the AI extraction and consistency detector against the golden set (data/golden). Use when changing extraction prompts, schemas, model settings, the merge logic, the consistency rules, or when asked for accuracy numbers for the pitch.
---
# Extraction evaluation

## Golden set
`data/golden/expected_handover_2026-10-21.json` contains, for the demo case as of 2026-10-21:
- `fields`: the 15 handover groups (Handover_obsah) with expected `status`
  (`complete`, `partial`, `missing`, `stale`, `needs_clarification`, `complete_with_conflict`,
  `generated_with_citations`), expected values and verbatim evidence quotes.
- `expected_findings`: 14 findings the consistency detector must raise as of the MDT start (C1–C3, M1–M3, S1,
  D1–D2, T1, X1, X4, Q1, N1); `post_mdt_findings`: X2, X3 — raised only when the MDT conclusion (after as_of) is
  checked against earlier documents.
- `excluded_documents`: reports authored after the MDT (12, 13).
- `timeline` and `intervals_days` for the T1/T2/T3 clock.

Never edit expected values to make a run pass. If you believe the golden set is wrong, open an issue
with the evidence and ask the P2 owner.

## Metrics (all printed by `make eval`, also written to `eval/report.json` at the repo root)
Status enum: complete | partial | missing | stale | needs_clarification | complete_with_conflict | generated_with_citations.

| Metric | Definition | Target |
| --- | --- | --- |
| Evidence validity | share of extracted facts whose quote is found verbatim (whitespace-normalised) in the cited document | 100 % (hard gate) |
| Field status accuracy | expected vs predicted status over the 15 fields | ≥ 14/15 |
| Key value recall | expected atomic values found (labs, meds, dates, codes) | ≥ 95 % |
| Hallucination count | facts with no support in any included document | 0 (hard gate) |
| Finding recall | expected findings raised as of 21. 10. | 14/14 (post-MDT X2, X3 checked separately) |
| Finding precision | raised findings judged valid | ≥ 80 % |
| As-of leakage | facts sourced from excluded documents | 0 (hard gate) |

## How to run
```bash
make eval                       # full run, cached LLM responses by default (STAFETA_LLM_CACHE=1)
STAFETA_LLM_CACHE=0 make eval   # fresh calls to APIM (costs budget; watch 429)
cd backend && uv run --env-file ../.env pytest tests/eval -k field_status -q
```
Cached responses live in `backend/tests/fixtures/llm_cache/` keyed by (model, prompt hash, doc hash).
The demo uses the same cache so a slow or rate-limited APIM never breaks the live demo.

## Adding a new golden case
Create a new JSON next to the existing one with the same schema; quotes must be verbatim. Run
`cd backend && uv run python -m app.extraction.check_golden ../data/golden/<file>` to validate quotes before committing.

## Reporting for the pitch
Use the latest `eval/report.json`; quote numbers exactly with the date and commit hash.
