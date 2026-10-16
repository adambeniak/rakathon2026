# Handover (F2-2): open and broken items

State as of 2026-10-16, after PR #14 (`ai/handover-assembly`, incl. review fixes 6c90a08) and PR #19
(`ai/handover-persistence`). **Broken** = wrong or unusable behaviour today. **Open** = known gap or follow-up.
Owners are roles from AGENTS.md.

## Broken (fix before the demo)
| # | What | Where | Owner |
| --- | --- | --- | --- |
| B1 | Confirming a section always returns **403** outside tests. `current_actor()` returns `system`, and only `koc_physician` may confirm. | `app/security/actor.py` (#4), `routes/handover.py` | P4 |
| B2 | A concurrent confirmation returns **502 storage-error** instead of 409. An `If-Match` mismatch (412) becomes `FhirConflictError`, which `_fhir_status` does not map. | `app/api/errors.py` | P1/P4 |
| B3 | A confirmation can apply to content that has since changed. GET re-assembles from the current documents and overlays the stored review by section, so a section confirmed earlier stays "confirmed" even if its assembled value changed. The previous-value hash is stored but never compared. | `review.py` `overlay_review`, `handover_store.py` | P2 |
| B4 | The frontend calls `/handover/sections/{key}/confirm` and `/handover/confirm-all` with its own mock shape. The API has `/sections/{n}/confirm` (n = 1..15), returns `Handover`, and has no confirm-all. | `frontend/src/features/handover/api.ts` | P3 |
| B5 | The demo epicrisis is the code-built **fallback** (a list of facts), not a summary. The `epicrisis-v1` LLM answer is not in the cache. | `tests/fixtures/llm_cache` | human: `STAFETA_LLM_CACHE=0 make eval` |

## Open: evaluation and data quality
| # | What | Owner |
| --- | --- | --- |
| O1 | Field status is 13/15. Fields 7 and 14 need findings C1/C2 from the consistency detector (F3-1). The gate goes to 14/15 afterwards (issue #13). | P2 (F3-1) |
| O2 | Lab rows carry no specimen (blood vs urine share test names, e.g. Leukocyty). Field 13 says so in its note. Needs extraction prompt v2 and a new cache fill. | P2 |
| O3 | Extraction typing: "Zátěž toleruje dobře" is a symptom. The 2019 depressive episode is typed for field 4, so the comorbidities miss it. "t. č. v pracovní neschopnosti" is not extracted. Doc 04 yields duplicate negation pairs. | P2 (prompt v2) |
| O4 | Key value recall miss `12.11` (histology dated 19. 10.): only the header line carries the date. | P2 |
| O5 | The lock and the rules were tuned on the same 13 documents. There is no held-out case, so metrics do not measure generalisation. | P2 |
| O6 | Symptoms (field 11) include July cardiology review-of-systems negations. Field 15 includes old discharge instructions (attributed and dated, but noisy). | P2 |
| O7 | Heuristics that may misfire on other cases: comorbidity merge by one shared word, drug-name stem matching, the "po dobu N dní" ended-course rule, and patient phone choice when no registry phone exists. | P2 |

## Open: persistence, FHIR, security
| # | What | Owner |
| --- | --- | --- |
| O8 | The `fhir-architect` and `security-privacy-reviewer` reviews of PR #19 have not run. | P1 / P4 |
| O9 | `tests/integration/test_iris_handover.py` has never run against IRIS (needs `.env`). | human |
| O10 | Our CodeSystems and extensions (`handover-*`, `evidence-quote`, `previous-value-sha256`, …) are not loaded into IRIS, so validator warnings are possible. | P1 |
| O11 | A physician's edit is stored on the Composition section only. The derived Condition/MedicationStatement/Observation keep the AI value. | P2 / P1 |
| O12 | Provenance has no identifier. Two simultaneous first persists could both write Provenance; the Composition itself is conditional. | P1 |
| O13 | No way to regenerate the Composition after new documents arrive for the same as_of (persist is idempotent and returns the old one). | P2 / P4 |
| O14 | Every GET/export of a persisted handover adds an audit read of the Composition, which grows the audit log quickly with polling UIs. | P4 |

## Open: performance and process
| # | What | Owner |
| --- | --- | --- |
| O15 | GET/POST/confirm re-run normalisation + extraction + epicrisis per request. Fast from the cache; a live LLM run would be slow and cost budget. No caching of the assembled handover. | P2 |
| O16 | `frontend/src/lib/api/schema.d.ts` is not committed; P3 regenerates it with `make contract` when switching off the mocks. | P3 |
| O17 | PR #14 is ~3,000 changed lines (guideline 400). PR #19 adds ~1,300 more. | team |
