"""In-memory stand-ins for the IRIS vector store, the embedder and the audit sink."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

import pytest

from app.iris.vector_store import ChunkHit, ChunkRow, as_of_params
from app.retrieval.embeddings import ChunkBudget
from tests.document_fixtures import doc, docs  # noqa: F401 - shared fixtures


class FakeEmbedder:
    """Deterministic 3-dim vectors from a hash; character budget like the APIM provider."""

    model_id = "fake:3"
    dim = 3

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            out.append([h[0] / 255 + 0.01, h[1] / 255 + 0.01, h[2] / 255 + 0.01])
        return out

    def budget(self, prefix: str) -> ChunkBudget:
        return ChunkBudget(800, 100, len)


@dataclass
class FakeStore:
    """Implements the VectorStore methods used by the indexer and the retriever, without IRIS."""

    dim: int = 3
    rows: dict[str, list[ChunkRow]] = field(default_factory=dict)
    vector_order: list[str] | None = None  # doc_ids in the order the vector leg returns them
    text_error: Exception | None = None

    def replace_document(self, doc_ref: str, rows: Sequence[ChunkRow]) -> int:
        self.rows[doc_ref] = list(rows)
        return len(rows)

    def chunk_count(self, doc_ref: str, model: str) -> int:
        return sum(1 for r in self.rows.get(doc_ref, []) if r.model == model)

    def delete_documents(self, doc_refs: Sequence[str]) -> int:
        for ref in doc_refs:
            self.rows.pop(ref, None)
        return len(doc_refs)

    def _visible(self, patient_ref: str, as_of: datetime, model: str) -> list[tuple[int, ChunkRow]]:
        """Same scope rule as SCOPE_WHERE: patient, model, authored before the Prague as-of day, received <= as_of."""
        authored_before, _ = as_of_params(as_of)
        all_rows = [r for rows in self.rows.values() for r in rows]
        return [
            (row_id, r)
            for row_id, r in enumerate(all_rows, 1)
            if r.patient_ref == patient_ref
            and r.model == model
            and r.authored_on.isoformat() < authored_before
            and r.received_at <= as_of
        ]

    @staticmethod
    def _hit(row_id: int, r: ChunkRow, score: float) -> ChunkHit:
        return ChunkHit(
            row_id=row_id,
            doc_ref=r.doc_ref,
            doc_id=r.doc_id,
            title=r.title,
            seq=r.seq,
            authored_on=r.authored_on,
            received_at=r.received_at,
            text=r.text,
            char_start=r.char_start,
            char_end=r.char_end,
            score=score,
        )

    def search(
        self, *, patient_ref: str, vector: Sequence[float], as_of: datetime, k: int, model: str
    ) -> list[ChunkHit]:
        visible = self._visible(patient_ref, as_of, model)
        if self.vector_order is not None:
            rank = {d: i for i, d in enumerate(self.vector_order)}
            visible.sort(key=lambda ir: (rank.get(ir[1].doc_id, 999), ir[1].seq))
        return [self._hit(i, r, 1.0 - n / 100) for n, (i, r) in enumerate(visible[:k])]

    def text_search(self, *, patient_ref: str, query: str, as_of: datetime, k: int, model: str) -> list[ChunkHit]:
        if self.text_error is not None:
            raise self.text_error
        stems = [t.rstrip("*") for t in query.split(" OR ")]
        visible = self._visible(patient_ref, as_of, model)
        hits = [
            self._hit(i, r, 0.0)
            for i, r in visible
            if any(w.startswith(s) for s in stems for w in f"{r.title} {r.text}".casefold().replace("\n", " ").split())
        ]
        return hits[:k]


class FakeAuditor:
    def __init__(self) -> None:
        self.derived: list[tuple[list[str], str]] = []
        self.reads: list[tuple[list[str], str]] = []

    async def audit_derived_write(self, entities: Sequence[str], *, description: str) -> None:
        self.derived.append((list(entities), description))

    async def audit_read(self, entities: Sequence[str], *, subtype: str = "read") -> None:
        self.reads.append((list(entities), subtype))


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def auditor() -> FakeAuditor:
    return FakeAuditor()
