"""Evidence-locked fact extraction from source documents (owner: P2).

Every fact carries verbatim evidence (`app.domain.evidence.Evidence`) or it is rejected (ADR-0002). LLM calls only
via `app.extraction.llm` (single client, retry, cache, JSON-schema output). No clinical advice.
"""
