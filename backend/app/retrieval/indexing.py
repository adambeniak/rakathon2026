"""DocumentReference -> chunks + embeddings in `Stafeta.DocChunk` (owner: P1).

Called by the seed after every stored document, after every upload (referral letter, received report: a background
task scheduled by the route, `index_case_documents`), and by `python -m app.retrieval.reindex` (backfill after an
ACI restart or an embedding-provider switch). Idempotent: one delete+insert transaction per document. Without `force`,
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
from app.documents.ingest import PDF_MEDIA_TYPE, normalize_upload
from app.documents.normalize import NormalizedDoc, doc_from_text, normalize_docx_bytes
from app.domain.errors import DomainError
from app.fhir.audit import AuditSubtype
from app.fhir.client import Resource
from app.fhir.mappers.document import StoredDocument, stored_document_from_fhir
from app.fhir.systems import DOCX_MEDIA_TYPE, SID_SOURCE_DOCUMENT
from app.iris.vector_store import ChunkRow, VectorStore
from app.retrieval.embeddings import Embedder

log = structlog.get_logger(__name__)


class DerivedWriteAuditor(Protocol):
    async def audit_derived_write(self, entities: Sequence[str], *, description: str) -> None: ...


class DocumentRepository(DerivedWriteAuditor, Protocol):
    async def search(self, resource_type: str, params: dict[str, str]) -> list[Resource]: ...

    async def audit_read(self, entities: Sequence[str], *, subtype: AuditSubtype = "read") -> None: ...


class CasePatientLocator(Protocol):
    async def case_patient(self, case_id: str) -> tuple[str, str]: ...


@dataclass(frozen=True)
class IndexResult:
    reference: str
    doc_id: str
    chunks: int
    skipped: str | None = None  # reason when nothing was written


def normalized_document(stored: StoredDocument) -> NormalizedDoc | None:
    """DOCX via the extraction normaliser, PDF via the validated upload path, plain text line by line.

    The authored date comes from FHIR (`Attachment.creation`), not from the file name. Anything else is not indexed.
    """
    source = stored.source
    if stored.content_type == DOCX_MEDIA_TYPE:
        doc = normalize_docx_bytes(source.doc_id, stored.content, source.authored_at)
    elif stored.content_type == PDF_MEDIA_TYPE:
        name = source.file_name or f"{source.doc_id}.pdf"
        doc = normalize_upload(name, stored.content, authored_date=source.authored_at, doc_id=source.doc_id).doc
    elif stored.content_type.startswith("text/plain"):
        doc = doc_from_text(source.doc_id, stored.content.decode("utf-8"), source.authored_at)
    else:
        return None
    return dc_replace(doc, received_at=source.received_at)


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

    async def is_indexed(self, reference: str) -> bool:
        """True if the document has chunks for the current embedding model."""
        return bool(await asyncio.to_thread(self._store.chunk_count, reference, self.model_id))

    async def index(self, resource: Resource, *, force: bool = False) -> IndexResult:
        stored = stored_document_from_fhir(resource)
        doc_id = stored.source.doc_id
        if not force:
            existing = await asyncio.to_thread(self._store.chunk_count, stored.reference, self.model_id)
            if existing:
                return IndexResult(stored.reference, doc_id, existing, skipped="already indexed")
        try:
            doc = normalized_document(stored)
        except DomainError as exc:  # e.g. a PDF without a text layer: nothing to index, and no reason to fail
            log.warning("document_not_indexed", reference=stored.reference, reason=type(exc).__name__)
            return IndexResult(stored.reference, doc_id, 0, skipped=f"unreadable ({type(exc).__name__})")
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


async def index_case_documents(
    case_id: str, locator: CasePatientLocator, repository: DocumentRepository, indexer: DocumentIndexer
) -> int:
    """Index every source document of the case's patient that is not indexed yet. Returns chunks written."""
    _, patient_ref = await locator.case_patient(case_id)
    resources = await repository.search("DocumentReference", {"subject": patient_ref, "_count": "100"})
    sources = [r for r in resources if any(i.get("system") == SID_SOURCE_DOCUMENT for i in r.get("identifier", []))]
    if not sources:
        return 0
    await repository.audit_read([f"DocumentReference/{r['id']}" for r in sources], subtype="search-type")
    written = 0
    for resource in sources:
        result = await indexer.index(resource)
        written += 0 if result.skipped else result.chunks
    return written


async def index_case_in_background(
    case_id: str, locator: CasePatientLocator, repository: DocumentRepository, indexer: DocumentIndexer
) -> None:
    """Background task after an upload: the upload already succeeded, so a failure is logged, never raised."""
    try:
        chunks = await index_case_documents(case_id, locator, repository, indexer)
    except Exception as exc:  # noqa: BLE001 - must not fail silently either: logged with the type, no PHI
        log.error("case_indexing_failed", case_id=case_id, error_type=type(exc).__name__)
        return
    log.info("case_documents_indexed", case_id=case_id, chunks=chunks)
