from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.iris.vector_store import ChunkHit
from app.retrieval.indexing import DocumentIndexer
from app.retrieval.search import (
    HybridRetriever,
    fuse,
    query_stems,
    rank_text_hits,
    stem,
    text_query,
)
from app.seed.loader import Scenario, seed
from app.settings import PRAGUE
from tests.unit.retrieval.conftest import FakeAuditor, FakeEmbedder, FakeStore
from tests.unit.seed.test_seed import InMemoryRepository

AS_OF = datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)


def hit(row_id: int, doc_id: str = "d", seq: int = 0, text: str = "") -> ChunkHit:
    return ChunkHit(
        row_id=row_id,
        doc_ref=f"DocumentReference/{doc_id}",
        doc_id=doc_id,
        title="t",
        seq=seq,
        authored_on=date(2026, 10, 1),
        received_at=datetime(2026, 10, 2, tzinfo=UTC),
        text=text,
        char_start=0,
        char_end=len(text),
        score=0.5,
    )


@pytest.mark.parametrize(
    ("word", "expected"),
    [("vysazena", "vysaz"), ("antikoagulace", "antikoa"), ("biopsií", "biop"), ("ECOG", "ecog"), ("léčbu", "léčb")],
)
def test_stem_handles_czech_inflection(word: str, expected: str) -> None:
    assert stem(word) == expected


def test_query_stems_drop_question_words_short_words_and_duplicates() -> None:
    assert query_stems("Kdy byla vysazena antikoagulace před biopsií? Biopsie!") == ["vysaz", "antikoa", "biop"]
    assert query_stems("Jaký je ECOG?") == ["ecog"]
    assert query_stems("Jak je na tom?") == []


def test_section_abbreviations_are_added_for_anamnesis_questions() -> None:
    assert query_stems("Má pacientka nějaké alergie?") == ["něja", "aler", "aa"]
    assert query_stems("Jaké léky užívá?") == ["léky", "fa", "užív"]
    assert "abusus" in query_stems("Kouří pacientka?")


def test_operators_and_quotes_never_reach_ifind() -> None:
    stems = query_stems('apixaban" OR 1=1) AND NOT (ecog* "~ <script> %ID')
    query = text_query(stems)
    assert all(part.endswith("*") and part[:-1].isalpha() for part in query.split(" OR "))
    assert '"' not in query
    assert "(" not in query
    with pytest.raises(ValueError, match="letter-only"):
        text_query(["ok", "bad*"])
    with pytest.raises(ValueError, match="non-empty"):
        text_query([])


def test_rank_text_hits_prefers_rare_stems() -> None:
    stems = ["posle", "dávk", "apixab"]
    common = [hit(i, f"0{i}", text="apixaban 5 mg 1-0-1") for i in range(1, 6)]
    key = hit(9, "09", text="Apixaban vysazen (poslední dávka 18. 10. 2026 večer).")
    noise = hit(10, "10", text="bez nálezu")
    ranked = rank_text_hits(stems, [*common, key, noise])
    assert ranked[0].row_id == 9
    assert noise not in ranked


def test_fuse_is_deterministic_and_guarantees_each_legs_top() -> None:
    vector = [hit(i, f"v{i:02d}") for i in range(1, 31)]
    text = [hit(99, "09", text="x"), *vector[20:23]]  # 09 is first in full text, absent from the vector leg

    fused = fuse(vector, text, 10)

    assert len(fused) == 10
    assert 99 in [r.hit.row_id for r in fused]
    assert fused == fuse(vector, text, 10)
    top = next(r for r in fused if r.hit.row_id == 99)
    assert (top.vector_rank, top.text_rank, top.vector_score) == (None, 1, None)
    assert [r.score for r in fused] == sorted((r.score for r in fused), reverse=True)


async def seeded(store: FakeStore, embedder: FakeEmbedder) -> str:
    repo = InMemoryRepository()
    await seed(repo, Scenario.STORY, indexer=DocumentIndexer(store, embedder, FakeAuditor()))
    return next(f"Patient/{r['id']}" for r in repo.of_type("Patient"))


async def test_hybrid_finds_the_biopsy_chunk_lexically(store: FakeStore, embedder: FakeEmbedder) -> None:
    patient = await seeded(store, embedder)
    store.vector_order = ["07_PL_zadost_KOC2_2026-10-02", "04_PL_epikriza_2026-09-04"]  # vector leg misses 09

    results = await HybridRetriever(store, embedder).search(  # type: ignore[arg-type]
        patient_ref=patient, question="Kdy byla vysazena antikoagulace před biopsií?", as_of=AS_OF, k=8
    )

    assert any("poslední dávka 18. 10. 2026" in r.hit.text for r in results)
    assert not {r.hit.doc_id[:2] for r in results} & {"12", "13"}


async def test_hybrid_degrades_to_vector_only_when_full_text_fails(store: FakeStore, embedder: FakeEmbedder) -> None:
    patient = await seeded(store, embedder)
    store.text_error = RuntimeError("index DocChunkText missing")

    results = await HybridRetriever(store, embedder).search(  # type: ignore[arg-type]
        patient_ref=patient, question="apixaban", as_of=AS_OF, k=5
    )

    assert len(results) == 5
    assert all(r.text_rank is None for r in results)
