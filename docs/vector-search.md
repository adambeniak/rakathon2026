# Vector search in InterSystems IRIS — "ask the case"

Štafeta stores every received clinical document as chunks with embeddings in **IRIS for Health 2026.1**. It
retrieves evidence with **hybrid SQL search**: `VECTOR_COSINE` on an HNSW index plus iFind full text, fused by
reciprocal rank. On top of that, a coordinator can ask the case a question in Czech and get an answer whose every
sentence is locked to a verbatim quote. Decision record: [ADR-0004](adr/0004-vector-search-and-ask.md).
Fictitious data only.

```
DocumentReference (FHIR, IRIS)                       POST /api/cases/{id}/ask {question, as_of}
   │ seed / make index                                  │
   ▼                                                    ▼
normalise (same as extraction) ─► chunk (≤128 tokens,   embed question (local ONNX, 6 ms)
table rows never split) ─► embed (fastembed, 384 d)       │
   │                                                    ├─► vector leg:   VECTOR_COSINE on HNSW (ACORN-1 filter)
   ▼                                                    ├─► full-text leg: iFind on Text + Title (Czech prefixes)
Stafeta.DocChunk (VECTOR(DOUBLE,384) + HNSW + 2× iFind) │   both legs: same patient / model / as-of WHERE
                                                        ▼
                                          RRF fusion ─► top 10 chunks ─► LLM (APIM, cached) ─► evidence lock
                                                        ─► "Návrh AI" answer + citations + sources (ranks, scores)
```

## Schema (`scripts/bootstrap_iris.py`, idempotent)

```sql
CREATE TABLE Stafeta.DocChunk (
    DocRef VARCHAR(200) NOT NULL,        -- "DocumentReference/248" (audit)
    PatientRef VARCHAR(200),             -- "Patient/222"
    Seq INTEGER NOT NULL,                -- chunk number within the document
    AuthoredOn DATE,                     -- Attachment.creation
    ReceivedOn TIMESTAMP,                -- DocumentReference.date, stored in UTC
    Text VARCHAR(32000),                 -- verbatim slice of the normalised document
    Embedding VECTOR(DOUBLE, 384),
    DocId VARCHAR(100),                  -- business id cited in answers: "09_Biopsie_vykon_KOC2_2026-10-12"
    Title VARCHAR(500),
    CharStart INTEGER, CharEnd INTEGER,  -- Text = normalised_document[CharStart:CharEnd] (UI highlight)
    EmbeddingModel VARCHAR(200)          -- query and stored vectors must come from the same model
)
CREATE INDEX DocChunkPatient ON TABLE Stafeta.DocChunk (PatientRef)
CREATE INDEX DocChunkDocRef  ON TABLE Stafeta.DocChunk (DocRef)
CREATE INDEX DocChunkHNSW    ON TABLE Stafeta.DocChunk (Embedding) AS HNSW(Distance='Cosine')
CREATE INDEX DocChunkText    ON TABLE Stafeta.DocChunk (Text)  AS %iFind.Index.Basic(LANGUAGE='cs', LOWER=1)
CREATE INDEX DocChunkTitle   ON TABLE Stafeta.DocChunk (Title) AS %iFind.Index.Basic(LANGUAGE='cs', LOWER=1)
```

An older table is migrated with `ALTER TABLE … ADD COLUMN`, guarded by `INFORMATION_SCHEMA`. `INDEXOPTION=1`
(stemming) with `LANGUAGE='cs'` crashes on insert in 2026.1 because there is no Czech stemmer, so the backend
sends prefix wildcards instead (below).

## SQL

Insert: one transaction per document (autocommit off), so re-indexing is idempotent:

```sql
DELETE FROM Stafeta.DocChunk WHERE DocRef = ?;
INSERT INTO Stafeta.DocChunk (DocRef, DocId, PatientRef, Seq, Title, AuthoredOn, ReceivedOn, Text, CharStart,
  CharEnd, EmbeddingModel, Embedding) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, TO_VECTOR(?, DOUBLE));  -- executemany
```

The two search legs share one scope filter (`app/iris/vector_store.py:SCOPE_WHERE`):

```sql
-- vector leg
SELECT TOP 30 %ID, DocRef, DocId, Title, Seq, AuthoredOn, ReceivedOn, Text, CharStart, CharEnd,
       VECTOR_COSINE(Embedding, TO_VECTOR(?, DOUBLE)) AS Score
FROM Stafeta.DocChunk
WHERE PatientRef = ? AND EmbeddingModel = ? AND AuthoredOn < ? AND ReceivedOn <= ?
ORDER BY Score DESC

-- full-text leg: ? = 'vysaz* OR antikoa* OR biop*'
SELECT TOP 50 %ID, … FROM Stafeta.DocChunk
WHERE PatientRef = ? AND EmbeddingModel = ? AND AuthoredOn < ? AND ReceivedOn <= ?
  AND (%ID %FIND search_index(DocChunkText, ?, 0) OR %ID %FIND search_index(DocChunkTitle, ?, 0))
```

**As-of rule (AGENTS.md 4).** The filter mirrors `app.extraction.lock.doc_included`:
- `AuthoredOn < as_of day`, using the Europe/Prague date. The rule is strict because the authoring time is unknown:
  the MDT conclusion of 21. 10. must not appear at the MDT start of 21. 10. 08:00. This is deliberately stricter
  than "≤" (the safe direction).
- `ReceivedOn <= as_of`, compared in UTC.
- For as_of `2026-10-21T08:00+02:00`, the bound parameters are `'2026-10-21'` and `'2026-10-21 06:00:00'`.
  Reports 12 (received 26. 10.) and 13 (27. 10.) are therefore never returned, in either leg.

**HNSW with filters: ACORN-1.** `EXPLAIN` on IRIS 2026.1 shows the filtered query reading the HNSW index map with
*"This plan uses the ACORN-1 algorithm for vector search"*: the WHERE predicates are tested during the graph walk,
not after. Measured: filtered `TOP k` returns k rows, and the order is identical to an exact scan
(`%IGNOREINDEX DocChunkHNSW`) and to a Python cosine scan (`tests/integration/test_vector_search.py`).

Analytics example (note `%EXACT`: `GROUP BY` otherwise returns SQLUPPER-collated ids):

```sql
SELECT %EXACT(DocId) AS DocId, COUNT(*) AS Chunks, MIN(ReceivedOn) AS ReceivedUtc
FROM Stafeta.DocChunk WHERE EmbeddingModel = ? GROUP BY %EXACT(DocId) ORDER BY 1
```

## Chunking: why ≤128 tokens

The local model `paraphrase-multilingual-MiniLM-L12-v2` (fastembed ONNX, 384 dims, CPU in the backend, never in
the 2 GB IRIS container) **truncates at 128 tokens**. Its tokenizer gives 2.9 characters per token for Czech prose
and 1.7 for lab tables. With 450-character chunks, 41 of 68 chunks would have been cut. The chunker therefore
measures each chunk with the model's own tokenizer:
- result: 89 chunks for the 13 reports, all ≤ 128 tokens, mean ~270 characters, 60-character word-aligned overlap;
- paragraph-aware: table rows ("tr" blocks) are never split;
- every chunk is an exact slice of the normalised text, so quotes and offsets stay valid.

An APIM `text-embedding-3-*` deployment (`EMBEDDING_PROVIDER=apim`, `dimensions=384`) would use 800/100 characters.
Switch providers with `make index FORCE=1`; rows are filtered by `EmbeddingModel`.

## Why hybrid

Rank of the key chunk of report 09 ("Apixaban vysazen 48 h před výkonem (poslední dávka 18. 10. 2026 večer)")
among 84 as-of chunks:

| Question | dense, title prefix | dense, no prefix | hybrid (shipped) |
| --- | --- | --- | --- |
| Kdy byla vysazena antikoagulace před biopsií? | 24 | 7 | 2 |
| Kdy byl vysazen apixaban před biopsií? | 25 | 6 | 2 |
| vysazení antikoagulace před výkonem | 24 | 33 | 6 |
| poslední dávka apixabanu | 48 | 29 | in top 10 (full-text rank 1) |

How the full-text leg is built and fused:
- **Query terms.** Content words are cut to Czech prefix stems (`vysazena → vysaz*`, `antikoagulace → antikoa*`,
  `biopsií → biop*`). Questions about anamnesis add the section abbreviation the reports use ("alergie" → `aa*`
  for "AA: neguje"). Only letters reach `search_index`, never raw user text.
- **Ranking within the leg.** Candidates are ranked by summed IDF of the matched stems.
- **Fusion.** RRF with k = 60. The top 3 of each leg always survive, so a chunk that is first in full text but
  missing from the vector leg is kept. Ties break deterministically by (doc_id, seq).
- **Fallback.** If iFind is missing, search degrades to vector-only.

## Latency (`make vector-bench`, backend on WSL → IRIS on Azure ACI swedencentral, 30 runs)

| Step | p50 ms | p95 ms |
| --- | --- | --- |
| IRIS round trip (`SELECT 1`) — network baseline | 41.2 | 56.9 |
| Query embedding (local ONNX, uncached) | 5.6 | 6.7 |
| Vector leg, HNSW + ACORN-1 filter (89 rows) | 41.8 | 47.8 |
| Vector leg, exact scan (89 rows) | 41.6 | 46.2 |
| Full-text leg (iFind on Text + Title) | 83.2 | 107.2 |
| Hybrid search end to end (embed + 2 SQL + RRF) | 172.2 | 185.3 |
| Scale run: vector leg, HNSW, 10 000 rows of one patient | 78.6 | 80.2 |
| Scale run: vector leg, exact scan, 10 000 rows | 80.7 | 86.0 |

At demo size both legs cost one network round trip. At 10 000 rows the server time is ~40 ms for both variants,
with identical top 10. HNSW pays off on corpora much larger than one patient's documents. The scale run is
`SCALE=10000 make vector-bench`; its synthetic rows are deleted afterwards. End-to-end `/ask` with a cached LLM
answer takes ~300 ms. The first request also loads the model (~2 s); a live LLM call adds a few seconds.

Indexing all 13 reports (normalise, chunk, embed 89 chunks, 13 transactions): 10–14 s.

## Example queries (as of 21. 10. 2026 08:00, recorded in `backend/tests/fixtures/ask`)

| Question | Status | Answer (abridged) |
| --- | --- | --- |
| Kdy byla vysazena antikoagulace před biopsií? | answered | "V protokolu o výkonu z 12. 10. 2026 je uvedeno vysazení apixabanu 48 h před výkonem s poslední dávkou 18. 10. 2026 večer. [09_…] Nesoulad: … datum výkonu 12. 10. 2026 … poslední dávka 18. 10. 2026 večer. [09_…]" |
| Jaký je ECOG? | not_documented | "V dokumentaci k 21. 10. 2026 není uvedeno." |
| Jakou léčbu doporučujete? | advice_declined | "Aplikace nedoporučuje léčbu; v dokumentaci je uvedeno: V kardiologické zprávě z 20. 7. 2026 je doporučeno … [01_…] …" |
| Jaký je výsledek histologie? | answered | "V bioptickém nálezu z 19. 10. 2026 je uveden duktální adenokarcinom pankreatu … [11_…] Nesoulad: … datum vydání 19. 10. 2026 a datum odběru 20. 10. 2026. [11_…]" |
| Co uvádí algeziologická zpráva? | not_documented | Report 12 arrives on 26. 10.: outside the as-of window. |
| Má pacientka nějaké alergie? | answered | "… je uvedeno, že pacientka alergie neguje. [07_…]" (found through `aa*`) |

## Evidence lock and safety (ADR-0002 applied to answers)

The LLM sees only the retrieved chunks, in (doc_id, seq) order, inside an injection-escaped envelope. It returns
sentences with `{doc_id, quote}`. A sentence is shown only if all of these hold:
- the quote is found in a retrieved chunk of that document;
- every date is in its quotes or is a cited document's authored date;
- every other number is in its quotes;
- outside its quotes, there is no recommendation, necessity, suitability, prognosis or hedging wording;
- the sentence is attributed to the documentation.

The fixed texts are rendered by code, never by the LLM:
- not found: `V dokumentaci k <datum> není uvedeno.`;
- an answer whose sentences were all rejected: "Odpověď AI se nepodařilo doložit citací; …". It never falls back
  to "není uvedeno", which would be a false claim of absence;
- advice questions get the prefix `Aplikace nedoporučuje léčbu; v dokumentaci je uvedeno:`.

Every answer carries the label `Návrh AI` and a disclaimer. Retrieved documents are audited as read (one
AuditEvent per question). The question is never logged, and the API never writes live answers to disk.

## Operations

| Command | What |
| --- | --- |
| `make iris-bootstrap` | table, columns, HNSW + 2 iFind indexes (idempotent) |
| `make seed` | seeds the case and indexes its documents (skips already indexed ones) |
| `make index` / `make index FORCE=1` | backfill / re-embed every DocumentReference |
| `make eval` | offline replay of the ask acceptance questions (+ extraction eval) |
| `make eval-ask-record` | live re-record after changing prompt, chunking or retrieval |
| `make vector-bench` (`SCALE=10000`) | latency table above |
| `uv run --env-file ../.env pytest -m iris tests/integration/test_vector_search.py` | live SQL tests |
