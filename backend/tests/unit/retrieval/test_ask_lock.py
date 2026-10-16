from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from app.iris.vector_store import ChunkHit
from app.retrieval.ask_lock import DroppedSentence, LockedSentence, lock_answer, lock_sentence
from app.retrieval.ask_prompt import RawCitation, RawSentence
from app.retrieval.search import RetrievedChunk

BIOPSY = "09_Biopsie_vykon_KOC2_2026-10-12"
HISTO = "11_Histologie_KOC2_2026-10-19"
LATER = "12_Algeziologie_2026-10-26"


def chunk(doc_id: str, text: str, authored: date, seq: int = 1) -> RetrievedChunk:
    hit = ChunkHit(
        row_id=hash((doc_id, seq)) & 0xFFFF,
        doc_ref=f"DocumentReference/{doc_id[:2]}",
        doc_id=doc_id,
        title=f"title {doc_id[:2]}",
        seq=seq,
        authored_on=authored,
        received_at=datetime(2026, 10, 19, 14, 0, tzinfo=UTC),
        text=text,
        char_start=0,
        char_end=len(text),
        score=0.5,
    )
    return RetrievedChunk(hit, 0.03, 1, 1, 0.5)


CHUNKS = [
    chunk(
        BIOPSY,
        "PŘÍPRAVA\nNalačno od půlnoci. Apixaban vysazen 48 h před výkonem (poslední dávka 18. 10. 2026 večer).",
        date(2026, 10, 12),
    ),
    chunk(HISTO, "Materiál: ložisko hlavy pankreatu, EUS-FNB 22G (odběr 20. 10. 2026)", date(2026, 10, 19)),
]


def sentence(text: str, *citations: tuple[str, str]) -> RawSentence:
    return RawSentence(text=text, citations=[RawCitation(doc_id=d, quote=q) for d, q in citations])


def test_cited_sentence_is_kept_with_the_exact_chunk_span() -> None:
    raw = sentence(
        "V protokolu je uvedeno, že apixaban byl vysazen 48 h před výkonem.",
        (BIOPSY, "Apixaban  vysazen 48 h\npřed výkonem"),  # whitespace differs from the chunk
    )
    result = lock_sentence(raw, CHUNKS)
    assert isinstance(result, LockedSentence)
    assert result.citations[0].quote == "Apixaban vysazen 48 h před výkonem"
    assert result.citations[0].title == "title 09"


def test_conflict_sentence_may_use_the_authored_date_of_a_cited_document() -> None:
    # "12. 10. 2026" sits in another chunk ("Datum výkonu"); it is the authored date of report 09.
    raw = sentence(
        "Nesoulad: výkon je datován 12. 10. 2026, ale poslední dávka je uvedena 18. 10. 2026 večer.",
        (BIOPSY, "poslední dávka 18. 10. 2026 večer"),
    )
    assert isinstance(lock_sentence(raw, CHUNKS), LockedSentence)


def test_multi_document_conflict_sentence() -> None:
    raw = sentence(
        "Nesoulad: odběr je uveden 20. 10. 2026, výkon 12. 10. 2026.",
        (HISTO, "(odběr 20. 10. 2026)"),
        (BIOPSY, "Apixaban vysazen 48 h před výkonem"),
    )
    result = lock_sentence(raw, CHUNKS)
    assert isinstance(result, LockedSentence)
    assert [c.doc_id for c in result.citations] == [HISTO, BIOPSY]


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (
            sentence(
                "Apixaban byl vysazen.",
            ),
            "no_citation",
        ),
        (sentence("Apixaban byl vysazen.", (LATER, "Apixaban vysazen")), "doc_not_retrieved"),
        (sentence("Apixaban byl vysazen.", (BIOPSY, "Apixaban vysazen 72 h")), "quote_not_found"),
        (sentence("Apixaban byl vysazen.", (BIOPSY, "48 h")), "quote_not_found"),  # too short to be evidence
        (sentence("Apixaban byl vysazen 16. 10. 2026.", (BIOPSY, "Apixaban vysazen 48 h")), "date_unsupported"),
        (sentence("Apixaban byl vysazen 72 h předem.", (BIOPSY, "Apixaban vysazen 48 h")), "number_unsupported"),
        (
            sentence("Doporučuji apixaban vysadit 48 h před výkonem.", (BIOPSY, "Apixaban vysazen 48 h")),
            "recommendation_wording",
        ),
        (sentence("Pacientka by měla vysadit apixaban.", (BIOPSY, "Apixaban vysazen")), "recommendation_wording"),
        (sentence("  [09_x] ", (BIOPSY, "Apixaban vysazen")), "empty"),
    ],
)
def test_unsupported_sentences_are_dropped(raw: RawSentence, reason: str) -> None:
    assert lock_sentence(raw, CHUNKS) == DroppedSentence(reason)


CARDIO = "01_Kardiologie_2026-07-20"
CARDIO_CHUNKS = [
    chunk(
        CARDIO,
        "Před plánovaným invazivním výkonem s vysokým rizikem krvácení vysadit apixaban 48 hodin předem.",
        date(2026, 7, 20),
    )
]


@pytest.mark.parametrize(
    "text",
    [
        "Vhodná dávka apixabanu je 48 mg.",
        "Je doporučeno vysadit apixaban 48 hodin předem.",
        "Je potřeba vysadit apixaban 48 hodin předem.",
        "Lze zvážit vysazení apixabanu 48 hodin předem.",
        "Apixaban vysadit 48 hodin předem.",
        "Nález pravděpodobně odpovídá riziku krvácení.",
        "V kardiologické zprávě je uvedeno, že prognóza je nejistá.",
    ],
)
def test_advice_interpretation_and_unattributed_sentences_are_dropped(text: str) -> None:
    raw = sentence(text, (CARDIO, "vysadit apixaban 48 hodin předem"))
    assert isinstance(lock_sentence(raw, CARDIO_CHUNKS), DroppedSentence)


def test_attributed_documented_recommendation_is_kept() -> None:
    raw = sentence(
        "V kardiologické zprávě z 20. 7. 2026 je doporučeno vysadit apixaban 48 hodin předem.",
        (CARDIO, "vysadit apixaban 48 hodin předem"),
    )
    assert isinstance(lock_sentence(raw, CARDIO_CHUNKS), LockedSentence)


def test_documented_recommendation_inside_the_quote_is_allowed() -> None:
    chunks = [chunk("01_Kardiologie_2026-07-20", "Doporučuji vysadit apixaban 48 hodin předem.", date(2026, 7, 20))]
    raw = sentence(
        'Kardiolog uvádí: "Doporučuji vysadit apixaban 48 hodin předem."',
        ("01_Kardiologie_2026-07-20", "Doporučuji vysadit apixaban 48 hodin předem."),
    )
    assert isinstance(lock_sentence(raw, chunks), LockedSentence)


def test_doc_id_markers_written_by_the_model_are_stripped() -> None:
    raw = sentence(
        "V protokolu je uvedeno, že apixaban byl vysazen 48 h. [09_Biopsie_vykon_KOC2_2026-10-12]",
        (BIOPSY, "vysazen 48 h"),
    )
    result = lock_sentence(raw, CHUNKS)
    assert isinstance(result, LockedSentence)
    assert result.text == "V protokolu je uvedeno, že apixaban byl vysazen 48 h."


def test_lock_answer_splits_kept_and_dropped() -> None:
    kept, dropped = lock_answer(
        [sentence("V protokolu je uvedeno, že apixaban byl vysazen.", (BIOPSY, "Apixaban vysazen")), sentence("Bez.")],
        CHUNKS,
    )
    assert len(kept) == 1
    assert dropped == [DroppedSentence("no_citation")]
