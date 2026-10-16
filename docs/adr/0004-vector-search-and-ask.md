# ADR-0004: Hybrid retrieval in IRIS and an evidence-locked "ask the case"

- Date: 2026-10-16 · Status: accepted · Owner: P1 (IRIS)

## Context
- Coordinators need to find facts across 13+ reports by meaning ("kdy byla vysazena antikoagulace?") and get an
  answer with sources, inside the as-of window (AGENTS.md 4), without the AI ever giving clinical advice (AGENTS.md 3).
- IRIS for Health 2026.1 has a native `VECTOR` type, HNSW indexes (filtered with ACORN-1) and iFind full text.
  It runs in 2 GB, so no model may run inside IRIS.
- APIM has no embedding deployment, so embeddings are computed locally:
  `paraphrase-multilingual-MiniLM-L12-v2` via fastembed (ONNX, 384 dims). That model **reads only 128 tokens**,
  which is about 370 characters of Czech prose.
- Measured: with dense vectors alone, the key chunk of report 09 ranked 24th of 84 for the acceptance question.
- A new endpoint changes `contracts/openapi.json` (the task explicitly asks for it).

## Decision
1. **Index.** Every DocumentReference is normalised with the extraction normaliser, then chunked
   paragraph-aware (table rows are never split). Chunks are sized by **tokens of the embedding model**
   (≤ 128 locally; 800/100 characters for a future APIM provider). Each chunk is embedded without a title prefix
   (measured better) and stored in `Stafeta.DocChunk` with DocId, Title, offsets, AuthoredOn,
   ReceivedOn (UTC) and EmbeddingModel.
   - Indexing is idempotent: one delete + insert transaction per document.
   - Hooks: the seed, and `make index` for backfill.
   - Each indexed document gets one AuditEvent.
2. **Retrieve (hybrid, in IRIS).** Both legs share one SQL scope filter: patient, model, authored before the Prague
   as-of day, received ≤ as_of.
   - Vector leg: `VECTOR_COSINE` top 30 on HNSW.
   - Full-text leg: iFind on `Text` and `Title`. Queries are built from Czech prefix stems (`vysaz*`) because IRIS
     has no Czech stemmer, plus anamnesis abbreviations ("alergie" → `aa*`), and are never passed raw user text.
   - Fusion: RRF (k = 60), where each leg's top 3 always survives. Tie order is deterministic.
3. **Answer.** The top 10 chunks, ordered by (doc_id, seq), go to the LLM through `app/extraction/llm.py`
   (prompt `ask-v2`; the API never persists live answers, only the eval recorder does).
   - The model returns sentences with `{doc_id, quote}` citations.
   - **Per-sentence evidence lock:** the quote must be in a retrieved chunk of that document; dates must be in
     the quotes or be a cited document's authored date; other numbers must be in the quotes; no recommendation
     wording (recommendation, necessity, suitability, prognosis, hedging) may appear outside the quotes; the
     sentence must be attributed to the documentation or start with "Nesoulad:" (after a clinical-safety review).
   - Fixed texts are rendered in code, never by the LLM: `V dokumentaci k <datum> není uvedeno.` (only when the
     model found nothing) and, for advice questions (regex or model flag),
     `Aplikace nedoporučuje léčbu; v dokumentaci je uvedeno:`.
   - If the model answered but every sentence was dropped, the status is `not_verified` with "Odpověď AI se
     nepodařilo doložit citací; …". It never says "není uvedeno", which would be a false claim of absence.
   - The output is always labelled `Návrh AI`.
   - Retrieved DocumentReferences are audited as read.
4. **Contract:** `POST /api/cases/{case_id}/ask`. The response includes sources with vector and full-text ranks,
   so the UI can show why a chunk was used.
5. Retrieval inside extraction (brief step 5) is **not** done: the longest report is 3.4k characters, and one call
   per document already fits.

## Consequences
- Easier: semantic + keyword search with as-of filtering in one SQL engine. Answers are auditable, and the
  sources expose ranks and scores.
- Harder: provider switches need `make index FORCE=1` (vectors are filtered by `EmbeddingModel`). The backend
  image grows by ~1 GB (onnxruntime + model baked in). Answers outside the recorded eval need a live LLM
  (`STAFETA_LLM_CACHE=0`).
- Watch: `make eval` replays the acceptance questions offline (`tests/fixtures/ask`); re-record after any change
  to the prompt, chunking or retrieval. `make vector-bench` gives the latency numbers. Live tests:
  `pytest -m iris tests/integration/test_vector_search.py`.
