"""DocumentReference -> chunks + embeddings in `Stafeta.DocChunk` (owner: P1).

Called by the seed after every stored document, and by `python -m app.retrieval.reindex` (backfill after an ACI
restart or an embedding-provider switch). Idempotent: one delete+insert transaction per document. Without `force`,
a document that already has chunks for the current model is skipped, so a second seed run writes nothing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import replace as dc_replace
from typing import Protocol

import structlog

from app.documents.chunking import chunk_document
from app.documents.normalize import NormalizedDoc, doc_from_text, normalize_content
from app.fhir.client import Resource
from app.fhir.mappers.document import StoredDocument, stored_document_from_fhir
from app.fhir.systems import DOCX_MEDIA_TYPE
from app.iris.vector_store import ChunkRow, VectorStore
from app.retrieval.embeddings import Embedder

log = structlog.get_logger(__name__)


class DerivedWriteAuditor(Protocol):
    async def audit_derived_write(self, entities: Sequence[str], *, description: str) -> None: ...


@dataclass(frozen=True)
class IndexResult:
    reference: str
    doc_id: str
    chunks: int
    skipped: str | None = None  # reason when nothing was written


def normalized_document(stored: StoredDocument) -> NormalizedDoc | None:
    """DOCX via the same normaliser as extraction; plain text line by line; anything else is not indexed."""
    source = stored.source
    if stored.content_type == DOCX_MEDIA_TYPE:
        return normalize_content(source.doc_id, stored.content, source)
    if stored.content_type.startswith("text/plain"):
        doc = doc_from_text(source.doc_id, stored.content.decode("utf-8"), source.authored_at)
        return dc_replace(doc, received_at=source.received_at)
    return None


class DocumentIndexer:
    def __init__(self, store: VectorStore, embedder: Embedder, auditor: DerivedWriteAuditor) -> None:
        if embedder.dim != store.dim:
            raise ValueError(f"embedder has {embedder.dim} dims, Stafeta.DocChunk has {store.dim}")
        self._store = store
        self._embedder = embedder
        self._auditor = auditor

    @property
    def model_id(self) -> str:
        return self._embedder.model_id

    async def index(self, resource: Resource, *, force: bool = False) -> IndexResult:
        stored = stored_document_from_fhir(resource)
        doc_id = stored.source.doc_id
        if not force:
            existing = await asyncio.to_thread(self._store.chunk_count, stored.reference, self.model_id)
            if existing:
                return IndexResult(stored.reference, doc_id, existing, skipped="already indexed")
        doc = normalized_document(stored)
        if doc is None:
            log.warning("document_not_indexed", reference=stored.reference, content_type=stored.content_type)
            return IndexResult(stored.reference, doc_id, 0, skipped=f"unsupported content type {stored.content_type}")

        rows = await asyncio.to_thread(self._rows, stored, doc)
        written = await asyncio.to_thread(self._store.replace_document, stored.reference, rows)
        await self._auditor.audit_derived_write(
            [stored.reference],
            description=f"Stafeta.DocChunk: {written} chunks embedded with {self.model_id}",
        )
        log.info("document_indexed", reference=stored.reference, chunks=written, model=self.model_id)
        return IndexResult(stored.reference, doc_id, written)

    def _rows(self, stored: StoredDocument, doc: NormalizedDoc) -> list[ChunkRow]:
        """CPU-bound part (tokenising, embedding): runs in a worker thread."""
        source = stored.source
        budget = self._embedder.budget("")
        chunks = chunk_document(doc, max_size=budget.max_size, overlap=budget.overlap, measure=budget.measure)
        vectors = self._embedder.embed([c.text for c in chunks])
        return [
            ChunkRow(
                doc_ref=stored.reference,
                doc_id=source.doc_id,
                patient_ref=stored.patient_reference,
                seq=c.seq,
                title=source.title,
                authored_on=source.authored_at,
                received_at=source.received_at,
                text=c.text,
                char_start=c.char_start,
                char_end=c.char_end,
                embedding=v,
                model=self.model_id,
            )
            for c, v in zip(chunks, vectors, strict=True)
        ]
