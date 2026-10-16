"""`Stafeta.DocChunk`: document chunks with embeddings in an IRIS `VECTOR(DOUBLE, 384)` column (owner: P1).

Schema and indexes: `scripts/bootstrap_iris.py` (`make iris-bootstrap`). SQL, the HNSW/ACORN-1 finding and latency
numbers: `docs/vector-search.md`. Synchronous (DB-API driver): call from async code via `asyncio.to_thread`.

As-of rule (AGENTS.md 4, mirrors `app.extraction.lock.doc_included`): a chunk is visible at `as_of` only if its
document was authored on a day BEFORE the as_of day (Europe/Prague; the time of day of authoring is unknown) AND
received at or before `as_of`. `ReceivedOn` is a timestamp without zone and is always stored in UTC.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from app.iris.db import IrisPool, PoolClosedError, PoolExhaustedError
from app.settings import PRAGUE

MAX_K = 50


class VectorStoreUnavailableError(RuntimeError):
    """IRIS SQL could not answer a search (driver error, connection failure, pool exhausted). No PHI in the message."""


def _driver_errors() -> tuple[type[BaseException], ...]:
    try:
        import iris.dbapi
    except ImportError:  # pragma: no cover - the driver is a dependency; unit tests use fakes either way
        return ()
    return (iris.dbapi.Error,)


# Infrastructure failures only: programming errors (TypeError, ValueError, …) still surface as 500.
DB_ERRORS: tuple[type[BaseException], ...] = (PoolExhaustedError, PoolClosedError, OSError, *_driver_errors())

# Literal SQL only; every value is bound as a parameter.
INSERT_SQL = (
    "INSERT INTO Stafeta.DocChunk (DocRef, DocId, PatientRef, Seq, Title, AuthoredOn, ReceivedOn, Text, CharStart, "
    "CharEnd, EmbeddingModel, Embedding) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, TO_VECTOR(?, DOUBLE))"
)
DELETE_DOC_SQL = "DELETE FROM Stafeta.DocChunk WHERE DocRef = ?"
COUNT_DOC_SQL = "SELECT COUNT(*) FROM Stafeta.DocChunk WHERE DocRef = ? AND EmbeddingModel = ?"


@dataclass(frozen=True)
class ChunkRow:
    """One chunk to store. `text` is the verbatim slice `normalised_document[char_start:char_end]`."""

    doc_ref: str  # "DocumentReference/<server id>"
    doc_id: str  # business id (DocumentReference.identifier), e.g. "09_Biopsie_vykon_KOC2_2026-10-12"
    patient_ref: str  # "Patient/<server id>"
    seq: int
    title: str
    authored_on: date
    received_at: datetime  # timezone-aware
    text: str
    char_start: int
    char_end: int
    embedding: Sequence[float]
    model: str


@dataclass(frozen=True)
class ChunkHit:
    row_id: int  # %ID of the DocChunk row: merges the vector and full-text legs of hybrid search
    doc_ref: str
    doc_id: str
    title: str
    seq: int
    authored_on: date
    received_at: datetime  # UTC, timezone-aware
    text: str
    char_start: int
    char_end: int
    score: float  # cosine similarity (vector leg) or 0.0 (full-text leg); higher is closer


def utc_naive(value: datetime) -> datetime:
    """Aware datetime -> naive UTC for the zone-less `ReceivedOn` column."""
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).replace(tzinfo=None)


def utc_timestamp(value: datetime) -> str:
    """Aware datetime -> 'YYYY-MM-DD HH:MM:SS.ffffff' in UTC (full precision) for `ReceivedOn`."""
    return utc_naive(value).isoformat(sep=" ", timespec="microseconds")


def as_of_params(as_of: datetime) -> tuple[str, str]:
    """(authored-before date, received-until UTC timestamp) for `AuthoredOn < ? AND ReceivedOn <= ?`."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    authored_before = as_of.astimezone(PRAGUE).date()
    # Microseconds on both sides: truncation would let a receipt at 06:00:00.9 pass an as_of of 06:00:00.1.
    return authored_before.isoformat(), utc_timestamp(as_of)


def vector_literal(vector: Sequence[float], dim: int) -> str:
    if len(vector) != dim:
        raise ValueError(f"embedding has {len(vector)} dimensions, the table expects {dim}")
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


# Shared by both legs of hybrid search so the as-of rule cannot drift between them.
SCOPE_WHERE = "PatientRef = ? AND EmbeddingModel = ? AND AuthoredOn < ? AND ReceivedOn <= ?"
_HIT_COLUMNS = "%ID, DocRef, DocId, Title, Seq, AuthoredOn, ReceivedOn, Text, CharStart, CharEnd"


def _top(k: int) -> int:
    if not 1 <= k <= MAX_K:
        raise ValueError(f"k must be between 1 and {MAX_K}")
    return int(k)


def search_sql(k: int) -> str:
    """Top-k chunks of one patient by cosine similarity, as-of filtered.

    IRIS 2026.1 runs this on the HNSW index with the ACORN-1 algorithm (filters evaluated during the graph walk),
    so `TOP k` returns k rows whenever k rows qualify. `TOP` takes an int literal (validated), the rest is bound.
    """
    return (
        f"SELECT TOP {_top(k)} {_HIT_COLUMNS}, VECTOR_COSINE(Embedding, TO_VECTOR(?, DOUBLE)) AS Score "  # noqa: S608 - constants + validated int
        f"FROM Stafeta.DocChunk WHERE {SCOPE_WHERE} ORDER BY Score DESC"
    )


def text_search_sql(k: int) -> str:
    """Chunks whose text or document title match an iFind query (search option 0: words, OR, prefix wildcards)."""
    return (
        f"SELECT TOP {_top(k)} {_HIT_COLUMNS}, 0 AS Score FROM Stafeta.DocChunk "  # noqa: S608 - constants + validated int
        f"WHERE {SCOPE_WHERE} AND (%ID %FIND search_index(DocChunkText, ?, 0) "
        "OR %ID %FIND search_index(DocChunkTitle, ?, 0))"
    )


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _as_utc(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def hit_from_row(row: Sequence[Any]) -> ChunkHit:
    row_id, doc_ref, doc_id, title, seq, authored, received, text, start, end, score = row
    return ChunkHit(
        row_id=int(row_id),
        doc_ref=str(doc_ref),
        doc_id=str(doc_id),
        title=str(title or doc_id),
        seq=int(seq),
        authored_on=_as_date(authored),
        received_at=_as_utc(received),
        text=str(text),
        char_start=int(start),
        char_end=int(end),
        score=float(score),
    )


class VectorStore:
    def __init__(self, pool: IrisPool, *, dim: int = 384) -> None:
        self._pool = pool
        self.dim = dim

    def replace_document(self, doc_ref: str, rows: Sequence[ChunkRow]) -> int:
        """Idempotent per document: delete its chunks and insert the new ones in ONE transaction."""
        if any(r.doc_ref != doc_ref for r in rows):
            raise ValueError("every row must belong to doc_ref")
        params = [
            [
                r.doc_ref,
                r.doc_id,
                r.patient_ref,
                r.seq,
                r.title,
                r.authored_on.isoformat(),
                utc_timestamp(r.received_at),
                r.text,
                r.char_start,
                r.char_end,
                r.model,
                vector_literal(r.embedding, self.dim),
            ]
            for r in rows
        ]
        with self._pool.transaction() as cur:
            cur.execute(DELETE_DOC_SQL, [doc_ref])
            if params:
                cur.executemany(INSERT_SQL, params)
        return len(params)

    def chunk_count(self, doc_ref: str, model: str) -> int:
        with self._pool.cursor() as cur:
            cur.execute(COUNT_DOC_SQL, [doc_ref, model])
            row = cur.fetchone()
            return int(row[0]) if row else 0  # read DataRow values before the cursor closes

    def delete_documents(self, doc_refs: Sequence[str]) -> int:
        """Remove the chunks of deleted documents (demo reset). Returns the number of documents processed."""
        if not doc_refs:
            return 0
        with self._pool.transaction() as cur:
            for doc_ref in doc_refs:
                cur.execute(DELETE_DOC_SQL, [doc_ref])
        return len(doc_refs)

    def search(
        self, *, patient_ref: str, vector: Sequence[float], as_of: datetime, k: int, model: str
    ) -> list[ChunkHit]:
        """Vector leg: top-k by cosine similarity."""
        authored_before, received_until = as_of_params(as_of)
        params = [vector_literal(vector, self.dim), patient_ref, model, authored_before, received_until]
        return self._hits(search_sql(k), params)

    def text_search(self, *, patient_ref: str, query: str, as_of: datetime, k: int, model: str) -> list[ChunkHit]:
        """Full-text leg: chunks matching `query` (built by app.retrieval.search.text_query, never raw input)."""
        authored_before, received_until = as_of_params(as_of)
        return self._hits(text_search_sql(k), [patient_ref, model, authored_before, received_until, query, query])

    def _hits(self, sql: str, params: Sequence[Any]) -> list[ChunkHit]:
        try:
            with self._pool.cursor() as cur:
                cur.execute(sql, params)
                # IRIS DataRow objects become unreadable once the cursor is closed: convert inside the block.
                return [hit_from_row(tuple(r)) for r in cur.fetchall()]
        except DB_ERRORS as exc:
            raise VectorStoreUnavailableError(f"IRIS vector search failed: {type(exc).__name__}") from exc
