<!-- WHO: P1 · TOOL: Claude Code Opus 5.5 (xhigh) · MODE: PLAN · WHEN: F2 (20:00–24:00) -->

ROLE: InterSystems IRIS engineer building the GenAI retrieval layer (this is our core InterSystems Vector Search showcase).

CONTEXT: `Stafeta.DocChunk` exists (bootstrap). Read the fhir-iris and kit-iris-vector-search skills,
backend/app/iris/db.py, backend/app/documents. Community edition: 8 connections, 2 GB RAM.

GOAL: Every received document is chunked and embedded into IRIS; the backend can retrieve evidence by meaning; the
coordinator can ask the case a question and get an answer with citations.

BUILD
1. Embeddings provider interface: `APIM` (if an embedding deployment exists — check with organisers) or `local`
   (fastembed ONNX, `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384 dims, CPU). Same dims as the
   table (`EMBEDDING_DIM`). Cache embeddings by text hash.
2. Ingestion hook: when a DocumentReference is stored, chunk the normalised text (paragraph-aware, ~800 chars,
   100 overlap, never split a table row), insert rows with DocRef, PatientRef, Seq, AuthoredOn, ReceivedOn, Text,
   Embedding via `TO_VECTOR(?, DOUBLE)`. Idempotent (delete + insert per DocRef).
3. `search_chunks(patient_ref, query, as_of, k=5)` with SQL `ORDER BY VECTOR_COSINE(...) DESC`, filtered by
   AuthoredOn/ReceivedOn ≤ as_of. Optional hybrid: add iFind full-text and RRF if time allows (stretch).
4. `POST /api/cases/{id}/ask` {question, as_of} → retrieve top chunks → LLM answers ONLY from them in Czech, each
   sentence cited with [doc_id]; if the answer is not in the chunks reply "V dokumentaci k <datum> není uvedeno."
   Evidence lock: verify cited quotes exist. Label as "Návrh AI".
   Questions asking for advice ("Jakou léčbu doporučujete?", doses, prognosis) get ONLY cited statements from the
   documentation, prefixed "Aplikace nedoporučuje léčbu; v dokumentaci je uvedeno:" — never a recommendation (AGENTS #3).
5. Use retrieval inside extraction for long documents (top chunks per field) — optional, only if it improves eval.
6. `docs/vector-search.md`: schema, index (HNSW or exact), SQL, example queries, latency numbers — for the
   InterSystems judges.

ACCEPTANCE
- [ ] "Kdy byla vysazena antikoagulace před biopsií?" → answer cites report 09 and mentions the inconsistent dates
- [ ] "Jaký je ECOG?" → "V dokumentaci k 21. 10. 2026 není uvedeno."
- [ ] As-of 21. 10. never returns chunks from reports 12–13
- [ ] "Jakou léčbu doporučujete?" returns no recommendation, only cited documentation
- [ ] PR `iris/vector-search`
