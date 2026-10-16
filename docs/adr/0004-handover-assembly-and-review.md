# ADR-0004: Deterministic handover assembly with routed missing items and section review

- Date: 2026-10-16 · Status: accepted · Owner: P2 (assembly), P4 (review workflow)

## Context
- F2-2 turns evidence-locked facts (ADR-0002) into the 15-field handover (`contracts/handover.schema.json`).
- A `missing` field must say *why* it is missing and *who* can supply it (e.g. ECOG → ošetřující lékař KOC). The
  contract only had `missing: list[str]`.
- Human in the loop (AGENTS rule 5): each section is a draft until a physician confirms it, or explicitly accepts it as
  missing. The contract had no place for that state.
- The epicrisis is the only LLM-written text in the handover. It must be cited sentence by sentence, and it must
  still work when the LLM or its cache is unavailable.

## Decision
- **Assembly is a pure function**, `app.extraction.handover.assemble.assemble_handover(case_id, as_of, facts,
  documents, *, patient, findings, epicrisis, rules)`.
  - It applies the as-of rule itself (`lock.as_of_exclusion`, same semantics as the extraction filter) and reports
    every excluded document with a Czech reason.
  - Values are copied verbatim from fact values. The only derived values are code-list lookups: sex and checksum from
    the rodné číslo, insurer name, and age at as_of.
  - Configurable rules are reported in `Handover.rules`. The stale-weight threshold (30 days) is a *demo rule*.
  - Consistency findings (F3-1) plug in through `findings`. A conflict-kind finding whose `field` starts with `"<n>_"`
    turns a field that has a value into `complete_with_conflict`. The eval never injects golden-derived findings.
- **Additive contract change** (`app/domain/handover.py`, regenerated with `make contract`):
  - `HandoverFieldBase.missing_items: [MissingItem{item, reason, suggested_owner: Role}]`. `missing` keeps the item keys
    shared with `data/golden`.
  - `HandoverFieldBase.review: SectionReview{state: draft|confirmed|accepted_missing, by, at, edited}`. It is `null`
    until the handover is persisted for review (PR `ai/handover-persistence`).
  - `HandoverFieldBase.items: [HandoverItem{label?, value, unit?, clinical_date?, evidence: [ItemEvidence]}]`, one
    entry per displayed value so the UI can show one evidence chip per value (requested by P3).
    `ItemEvidence` = `Evidence` + `authored_at` + `received_at` of the source document. Section-level `evidence`
    (the union) is kept for backward compatibility. Field 12 rows are document metadata: their items carry no quote,
    and the row's `doc_id` is the reference.
  - `Epicrisis.mode: llm|fallback`, `Epicrisis.label = "Návrh AI – čeká na potvrzení lékařem"`, and
    `CitedSentence.aliases` (the markers in the text, parallel to `fact_ids` and to the sentence item's evidence),
    so every `[F3]` can be traced to its document and quote.
  - `Handover.status: preliminary|final`, `Handover.composition_id`, `Handover.rules`.
  - `HandoverFieldBase.value_hash` (SHA-256 of the assembled value) and `SectionReview.value_hash`: a confirmation
    must send back the hash of what the physician saw (`expected_value_hash`, 409 otherwise); a stored confirmation
    whose hash no longer matches the re-assembled section is reopened as draft (PR #19 review).
- **Epicrisis:**
  - One LLM call over the selected facts, aliased F1…Fn, with its own prompt version (`epicrisis-v1`) and therefore its
    own cache key.
  - Post-check:
    - every sentence ends with a citation
    - cited ids exist and equal `fact_ids`
    - every number in a sentence occurs in a cited fact (quote, value or shown date)
    - no judgement words (recommendation, resectability, causality, prognosis, progression) unless a cited quote
      uses them
    - a sentence citing a suspected fact says so ("suspektní", "podezření", "diferenciálně")
  - On a failed check, one regeneration with the failed checks appended. Then a code-built list of the facts, with
    one cited line each (`mode=fallback`). Each line shows certainty ("suspektní:", "plánováno:") and the date at the
    precision the source states ("8/2026").
- **Attribution:** plans and instructions from the documents are shown as "Uvedeno v dokumentaci (title, date): …",
  so they never read as Štafeta's advice. A medication note points to documented drug plans (e.g. the apixaban pause
  in the EUS-FNB protocol) instead of merging them into the list.
- **Evidence lock repair** (ADR-0002 amendment): a `negated` text fact whose value lost the negation word gets the
  exact source quote as its value. This applies only when the quote carries the negation cue, is ≤ 40 characters and
  is a single clause (no comma or semicolon).
  The fact is noted `negated_value_from_quote` and counted in the eval report.

## Consequences
- Same facts + same as_of → the same handover. The eval measures the assembly without an LLM, except the epicrisis.
- Consumers get actionable missing items without parsing notes. Older clients ignore the new optional fields.
- Field-status accuracy is 13/15 until F3-1 supplies C1/C2 (issue #13 raises the gate to 14/15).
- The live epicrisis needs a human cache fill (`STAFETA_LLM_CACHE=0 make eval`). Until then the API and the eval show
  the cited fallback.
- Persistence (Composition + Provenance) and the confirm endpoint come in the stacked PR; they fill `review`, `status`
  and `composition_id`.
