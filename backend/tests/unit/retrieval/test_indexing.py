from __future__ import annotations

import base64

import pytest

from app.fhir.client import Resource
from app.fhir.mappers.document import document_to_fhir
from app.retrieval.indexing import DocumentIndexer
from app.seed import demo_case
from app.seed.loader import DEFAULT_DATA_DIR, Scenario, seed
from tests.unit.retrieval.conftest import FakeAuditor, FakeEmbedder, FakeStore
from tests.unit.seed.test_seed import InMemoryRepository

BIOPSY = next(d for d in demo_case.DOCUMENTS if d.doc_id.startswith("09_"))


def biopsy_resource(content_type: str | None = None, content: bytes | None = None) -> Resource:
    from app.domain.document import SourceDocument

    source = SourceDocument(
        doc_id=BIOPSY.doc_id,
        title=BIOPSY.title,
        type_code=BIOPSY.loinc,
        authored_at=BIOPSY.authored_at,
        received_at=BIOPSY.received_at,
        content_type=content_type,
    )
    data = content if content is not None else (DEFAULT_DATA_DIR / BIOPSY.file_name).read_bytes()
    resource = document_to_fhir(
        source,
        data,
        patient_reference="Patient/7",
        episode_reference=None,
        custodian_reference=None,
        author_reference=None,
    )
    return {**resource, "id": "248"}


async def test_index_writes_verbatim_slices_with_metadata_and_audits(
    store: FakeStore, embedder: FakeEmbedder, auditor: FakeAuditor
) -> None:
    result = await DocumentIndexer(store, embedder, auditor).index(biopsy_resource())

    rows = store.rows["DocumentReference/248"]
    assert result.chunks == len(rows) > 1
    assert result.skipped is None
    assert {r.patient_ref for r in rows} == {"Patient/7"}
    assert {r.doc_id for r in rows} == {BIOPSY.doc_id}
    assert {r.model for r in rows} == {"fake:3"}
    assert [r.seq for r in rows] == list(range(len(rows)))
    assert any("poslední dávka 18. 10. 2026 večer" in r.text for r in rows)
    assert embedder.calls[-1] == [r.text for r in rows]  # the chunk text itself is embedded, no title prefix
    assert auditor.derived == [
        (["DocumentReference/248"], f"Stafeta.DocChunk: {len(rows)} chunks embedded with fake:3")
    ]


async def test_second_index_is_skipped_unless_forced(
    store: FakeStore, embedder: FakeEmbedder, auditor: FakeAuditor
) -> None:
    indexer = DocumentIndexer(store, embedder, auditor)
    first = await indexer.index(biopsy_resource())

    again = await indexer.index(biopsy_resource())
    forced = await indexer.index(biopsy_resource(), force=True)

    assert again.skipped == "already indexed"
    assert again.chunks == first.chunks
    assert forced.skipped is None
    assert len(auditor.derived) == 2  # nothing audited for the skipped run


async def test_plain_text_is_indexed_and_other_types_are_skipped(
    store: FakeStore, embedder: FakeEmbedder, auditor: FakeAuditor
) -> None:
    indexer = DocumentIndexer(store, embedder, auditor)
    text = await indexer.index(
        biopsy_resource("text/plain; charset=utf-8", "Apixaban vysazen.\nVýkon bez komplikací.".encode())
    )
    pdf = await indexer.index({**biopsy_resource("application/pdf", b"%PDF"), "id": "249"})

    assert text.chunks == 1
    assert store.rows["DocumentReference/248"][0].text == "Apixaban vysazen.\nVýkon bez komplikací."
    assert pdf.skipped == "unsupported content type application/pdf"
    assert "DocumentReference/249" not in store.rows


def test_dimension_mismatch_is_refused(embedder: FakeEmbedder, auditor: FakeAuditor) -> None:
    with pytest.raises(ValueError, match="dims"):
        DocumentIndexer(FakeStore(dim=384), embedder, auditor)


async def test_seed_indexes_every_document_once(store: FakeStore, embedder: FakeEmbedder, auditor: FakeAuditor) -> None:
    repo = InMemoryRepository()
    indexer = DocumentIndexer(store, embedder, auditor)

    first = await seed(repo, Scenario.STORY, indexer=indexer)
    second = await seed(repo, Scenario.STORY, indexer=indexer)

    assert len(store.rows) == 13
    assert first.chunks_indexed == sum(len(rows) for rows in store.rows.values())
    assert second.chunks_indexed == 0
    doc_refs = {r["id"] for r in repo.of_type("DocumentReference")}
    assert {ref.split("/")[1] for ref in store.rows} == doc_refs


def test_attachment_round_trip_matches_disk() -> None:
    resource = biopsy_resource()
    data = base64.b64decode(resource["content"][0]["attachment"]["data"])
    assert data == (DEFAULT_DATA_DIR / BIOPSY.file_name).read_bytes()
