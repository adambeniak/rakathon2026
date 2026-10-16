from __future__ import annotations

import itertools
from collections.abc import Callable

import pytest

from app.documents.chunking import DEFAULT_MAX_CHARS, Chunk, chunk_document
from app.documents.normalize import NormalizedDoc, build_doc, doc_from_text


def words(text: str) -> int:
    """Stand-in for a tokenizer: the local embedder measures tokens, not characters."""
    return len(text.split())


SETTINGS: list[dict[str, object]] = [
    {},  # characters, 800 / 100 (APIM provider)
    {"max_size": 40, "overlap": 60, "measure": words},  # token-like budget (local provider)
]


def chunked(d: NormalizedDoc, kwargs: dict[str, object]) -> list[Chunk]:
    return chunk_document(d, **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("kwargs", SETTINGS)
def test_every_chunk_is_an_exact_slice_of_the_document(
    docs: dict[str, NormalizedDoc], kwargs: dict[str, object]
) -> None:
    for d in docs.values():
        chunks = chunked(d, kwargs)
        assert chunks, d.doc_id
        assert [c.seq for c in chunks] == list(range(len(chunks)))
        for c in chunks:
            assert c.text == d.text[c.char_start : c.char_end]
            assert c.text == c.text.strip()


@pytest.mark.parametrize("kwargs", SETTINGS)
def test_chunks_cover_the_whole_document_in_order(docs: dict[str, NormalizedDoc], kwargs: dict[str, object]) -> None:
    for d in docs.values():
        chunks = chunked(d, kwargs)
        assert chunks[0].char_start == 0
        assert chunks[-1].char_end == len(d.text)
        for prev, nxt in itertools.pairwise(chunks):
            assert prev.char_start < nxt.char_start <= prev.char_end + 1  # no gap except the "\n" separator
            assert nxt.char_end > prev.char_end


@pytest.mark.parametrize("kwargs", SETTINGS)
def test_table_rows_are_never_split(docs: dict[str, NormalizedDoc], kwargs: dict[str, object]) -> None:
    for d in docs.values():
        rows = [b for b in d.blocks if b.kind == "tr"]
        for c in chunked(d, kwargs):
            for r in rows:
                overlaps = r.start < c.char_end and c.char_start < r.end
                if overlaps:
                    assert c.char_start <= r.start, (d.doc_id, r.text)
                    assert r.end <= c.char_end, (d.doc_id, r.text)


def test_real_reports_fit_the_budget(docs: dict[str, NormalizedDoc]) -> None:
    assert max(len(c.text) for d in docs.values() for c in chunk_document(d)) <= DEFAULT_MAX_CHARS
    for d in docs.values():
        rows = {(b.start, b.end) for b in d.blocks if b.kind == "tr"}
        for c in chunk_document(d, max_size=40, overlap=60, measure=words):
            # Only a single table row that is too long on its own may exceed the budget.
            assert words(c.text) <= 40 or (c.char_start, c.char_end) in rows


@pytest.mark.parametrize("kwargs", SETTINGS)
def test_overlap_is_bounded_and_word_aligned(docs: dict[str, NormalizedDoc], kwargs: dict[str, object]) -> None:
    for d in docs.values():
        chunks = chunked(d, kwargs)
        for prev, nxt in itertools.pairwise(chunks):
            shared = prev.char_end - nxt.char_start
            assert shared <= int(kwargs.get("overlap", 100))  # type: ignore[call-overload]
            if shared > 0:
                assert d.text[nxt.char_start - 1] in " \n"


def test_conflicting_dose_sentence_lands_in_one_chunk(doc: Callable[[str], NormalizedDoc]) -> None:
    chunks = chunk_document(doc("09_"), max_size=40, overlap=60, measure=words)
    hit = [c for c in chunks if "poslední dávka 18. 10. 2026 večer" in c.text]
    assert len(hit) == 1


def test_long_paragraph_is_cut_at_sentences_then_words() -> None:
    sentence = "Ložisko hlavy pankreatu je hypoechogenní a nehomogenní. "
    d = doc_from_text("x_2026-10-12", sentence * 20 + "Slovo" * 200)
    chunks = chunk_document(d, max_size=200, overlap=40)
    # A single "word" longer than the budget is never cut mid-word: it becomes one oversized chunk.
    assert [len(c.text) for c in chunks if len(c.text) > 200] == [1000]
    assert all(c.text == d.text[c.char_start : c.char_end] for c in chunks)
    assert chunks[-1].char_end == len(d.text)


def test_oversized_table_row_becomes_its_own_chunk() -> None:
    row = " | ".join(f"buňka {i}" for i in range(80))
    d = build_doc("t_2026-10-12", [("p", "Úvod.", None), ("tr", row, None), ("p", "Závěr.", None)], None)
    chunks = chunk_document(d, max_size=200, overlap=40)
    assert [c.text for c in chunks] == ["Úvod.", row, "Závěr."]


def test_rejects_silly_parameters() -> None:
    d = doc_from_text("x", "text")
    with pytest.raises(ValueError, match="max_size"):
        chunk_document(d, max_size=10)
    with pytest.raises(ValueError, match="overlap"):
        chunk_document(d, max_size=100, overlap=-1)
