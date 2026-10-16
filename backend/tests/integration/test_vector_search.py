"""Stafeta.DocChunk against a live IRIS: `uv run --env-file ../.env pytest -m iris tests/integration`.

Uses its own PatientRef and EmbeddingModel per run (synthetic 384-dim vectors, no model download) and deletes its
rows afterwards, so it never touches the demo case and parallel runs do not interfere.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterator
from datetime import date, datetime, timedelta

import pytest

from app.iris.db import IrisPool
from app.iris.vector_store import ChunkRow, VectorStore
from app.retrieval.search import query_stems, text_query
from app.settings import PRAGUE, Settings

pytestmark = pytest.mark.iris

AS_OF = datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)
DIM = 384


def unit_vector(seed: int) -> list[float]:
    raw = [math.sin(seed * 7.1 + i * 0.37) for i in range(DIM)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


@pytest.fixture
def live_store() -> Iterator[tuple[VectorStore, str, str, list[str]]]:
    settings = Settings()
    if not settings.iris_password.get_secret_value():
        pytest.skip("IRIS_PASSWORD not set (run with --env-file ../.env)")
    pool = IrisPool.from_settings(settings)
    run = uuid.uuid4().hex[:8]
    created: list[str] = []
    store = VectorStore(pool, dim=DIM)
    try:
        yield store, f"Patient/it-{run}", f"it-test:{run}", created
    finally:
        store.delete_documents(created)
        pool.close_all()


def rows(doc_ref: str, patient: str, model: str, *, authored: date, received: datetime, n: int, seed: int,
         title: str = "Synthetic report", text: str = "Syntetický text číslo {i}.") -> list[ChunkRow]:  # fmt: skip
    return [
        ChunkRow(
            doc_ref=doc_ref,
            doc_id=doc_ref.rsplit("/", 1)[1],
            patient_ref=patient,
            seq=i,
            title=title,
            authored_on=authored,
            received_at=received,
            text=text.format(i=i),
            char_start=i * 100,
            char_end=i * 100 + 50,
            embedding=unit_vector(seed + i),
            model=model,
        )
        for i in range(n)
    ]


def test_roundtrip_filters_and_ranks_like_an_exact_scan(live_store: tuple[VectorStore, str, str, list[str]]) -> None:
    store, patient, model, created = live_store
    known = f"DocumentReference/{patient[8:]}-known"
    same_day = f"DocumentReference/{patient[8:]}-sameday"
    late = f"DocumentReference/{patient[8:]}-late"
    created += [known, same_day, late]
    before = AS_OF - timedelta(days=2)
    store.replace_document(known, rows(known, patient, model, authored=before.date(), received=before, n=12, seed=1))
    # Authored on the as-of day (time unknown) -> excluded; received after as_of -> excluded.
    store.replace_document(
        same_day, rows(same_day, patient, model, authored=AS_OF.date(), received=AS_OF, n=3, seed=50)
    )
    store.replace_document(late, rows(late, patient, model, authored=before.date(),
                                      received=AS_OF + timedelta(minutes=1), n=3, seed=80))  # fmt: skip

    query = unit_vector(5)
    hits = store.search(patient_ref=patient, vector=query, as_of=AS_OF, k=8, model=model)

    assert len(hits) == 8  # HNSW + filters (ACORN-1) still returns k rows
    assert {h.doc_ref for h in hits} == {known}
    expected = sorted(range(12), key=lambda i: -cosine(query, unit_vector(1 + i)))[:8]
    assert [h.seq for h in hits] == expected
    assert hits[0].score == pytest.approx(cosine(query, unit_vector(1 + expected[0])), abs=1e-6)
    assert hits[0].received_at == before  # stored in UTC, returned aware


def test_received_exactly_at_as_of_is_visible(live_store: tuple[VectorStore, str, str, list[str]]) -> None:
    store, patient, model, created = live_store
    edge = f"DocumentReference/{patient[8:]}-edge"
    created.append(edge)
    store.replace_document(edge, rows(edge, patient, model, authored=date(2026, 10, 20), received=AS_OF, n=1, seed=3))

    hits = store.search(patient_ref=patient, vector=unit_vector(3), as_of=AS_OF, k=5, model=model)

    assert [h.doc_ref for h in hits] == [edge]


def test_replace_is_idempotent(live_store: tuple[VectorStore, str, str, list[str]]) -> None:
    store, patient, model, created = live_store
    doc = f"DocumentReference/{patient[8:]}-idem"
    created.append(doc)
    batch = rows(doc, patient, model, authored=date(2026, 10, 1), received=AS_OF - timedelta(days=5), n=4, seed=9)

    store.replace_document(doc, batch)
    store.replace_document(doc, batch[:2])

    assert store.chunk_count(doc, model) == 2
    assert store.chunk_count(doc, "other-model") == 0


def test_full_text_leg_matches_czech_prefixes_and_titles(live_store: tuple[VectorStore, str, str, list[str]]) -> None:
    store, patient, model, created = live_store
    biopsy = f"DocumentReference/{patient[8:]}-biopsy"
    histo = f"DocumentReference/{patient[8:]}-histo"
    created += [biopsy, histo]
    before = AS_OF - timedelta(days=3)
    common = {"authored": before.date(), "received": before, "n": 1}
    biopsy_text = "Apixaban vysazen 48 h před výkonem."
    store.replace_document(biopsy, rows(biopsy, patient, model, seed=4, text=biopsy_text, **common))  # type: ignore[arg-type]
    histo_title = "Histologie – bioptický nález"
    histo_text = "Duktální adenokarcinom."
    store.replace_document(histo, rows(histo, patient, model, seed=5, title=histo_title, text=histo_text, **common))  # type: ignore[arg-type]

    def found(question: str) -> set[str]:
        query = text_query(query_stems(question))
        hits = store.text_search(patient_ref=patient, query=query, as_of=AS_OF, k=10, model=model)
        return {h.doc_ref for h in hits}

    assert found("Kdy byla vysazena antikoagulace?") == {biopsy}  # "vysaz*" matches "vysazen"
    assert found("Jaký je výsledek histologie?") == {histo}  # only the title says "Histologie"
    assert found("Jaký je ECOG?") == set()
