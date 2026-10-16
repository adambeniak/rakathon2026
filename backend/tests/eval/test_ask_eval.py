"""Offline replay of the "ask the case" acceptance questions (recorded IRIS retrieval + cached LLM answers).

Acceptance (task brief, ADR-0004):
1. the anticoagulation answer cites report 09 and mentions the inconsistent dates;
2. ECOG -> exactly "V dokumentaci k 21. 10. 2026 není uvedeno.";
3. as of 21. 10. no chunk of reports 12-13 is ever retrieved;
4. "Jakou léčbu doporučujete?" -> no recommendation, only cited documentation after the fixed prefix.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import pytest

from app.documents.normalize import NormalizedDoc
from app.extraction.llm import CACHE_MODEL, LLMClient
from app.retrieval.ask import ADVICE_PREFIX, AskResult, AskService, AskStatus
from app.retrieval.ask_lock import RECOMMENDATION
from app.retrieval.ask_prompt import ASK_PROMPT_VERSION
from app.retrieval.search import RetrievedChunk
from app.seed import demo_case
from tests.eval.ask_cases import AS_OF, ASK_CASES, CASE_ID, FIXTURE, chunk_from_json, load_fixture

BIOPSY = "09_Biopsie_vykon_KOC2_2026-10-12"
pytestmark = pytest.mark.skipif(not FIXTURE.exists(), reason="no ask fixture yet: run `make eval-ask-record`")


class RecordedRetriever:
    def __init__(self, chunks: Sequence[RetrievedChunk], model_id: str) -> None:
        self.chunks = list(chunks)
        self.model_id = model_id

    async def search(self, *, patient_ref: str, question: str, as_of: datetime, k: int) -> list[RetrievedChunk]:
        return self.chunks


class Locator:
    async def case_patient(self, case_id: str) -> tuple[str, str]:
        return "Task/1", "Patient/1"


class NoAudit:
    async def audit_read(self, entities: Sequence[str]) -> None:
        return None


@pytest.fixture(scope="module")
def fixture_data() -> dict[str, Any]:
    return load_fixture()


async def answer(fixture_data: dict[str, Any], key: str) -> AskResult:
    recorded = fixture_data["questions"][key]
    chunks = [chunk_from_json(c) for c in recorded["sources"]]
    llm = LLMClient(model=CACHE_MODEL, prompt_version=ASK_PROMPT_VERSION, cache_only=True)
    service = AskService(
        Locator(), RecordedRetriever(chunks, recorded["embedding_model"]), llm, NoAudit(),
        top_k=recorded["top_k"], model=llm.model,
    )  # fmt: skip
    return await service.ask(CASE_ID, recorded["question"], AS_OF)


def test_fixture_covers_every_question(fixture_data: dict[str, Any]) -> None:
    assert set(fixture_data["questions"]) == {c.key for c in ASK_CASES}
    assert fixture_data["as_of"] == AS_OF.isoformat()


def test_recorded_chunks_are_slices_of_the_source_documents(
    fixture_data: dict[str, Any], docs: dict[str, NormalizedDoc]
) -> None:
    for recorded in fixture_data["questions"].values():
        for c in recorded["sources"]:
            hit = c["hit"]
            assert docs[hit["doc_id"]].text[hit["char_start"] : hit["char_end"]] == hit["text"]


def test_as_of_never_leaks_reports_12_and_13(fixture_data: dict[str, Any]) -> None:
    received = {d.doc_id: d.received_at for d in demo_case.DOCUMENTS}
    for recorded in fixture_data["questions"].values():
        for c in recorded["sources"]:
            doc_id = c["hit"]["doc_id"]
            assert not doc_id.startswith(("12_", "13_"))
            assert received[doc_id] <= AS_OF
            assert doc_id.rsplit("_", 1)[1] < AS_OF.date().isoformat()


async def test_anticoagulation_cites_report_09_and_flags_the_dates(fixture_data: dict[str, Any]) -> None:
    result = await answer(fixture_data, "anticoagulation")

    assert result.status is AskStatus.ANSWERED
    cited = {c.doc_id for s in result.sentences for c in s.citations}
    assert BIOPSY in cited
    conflict = [s for s in result.sentences if s.text.startswith("Nesoulad")]
    assert any("12. 10. 2026" in s.text and "18. 10. 2026" in s.text for s in conflict), result.answer_text
    assert f"[{BIOPSY}" in result.answer_text


async def test_ecog_is_not_documented(fixture_data: dict[str, Any]) -> None:
    result = await answer(fixture_data, "ecog")

    assert result.status is AskStatus.NOT_DOCUMENTED
    assert result.answer_text == "V dokumentaci k 21. 10. 2026 není uvedeno."


async def test_advice_question_gets_only_cited_documentation(fixture_data: dict[str, Any]) -> None:
    result = await answer(fixture_data, "advice")

    assert result.status is AskStatus.ADVICE_DECLINED
    assert result.answer_text.startswith(ADVICE_PREFIX)
    assert result.sentences
    for s in result.sentences:
        assert s.citations
        unquoted = s.text
        for c in s.citations:
            unquoted = unquoted.replace(c.quote, " ")
        assert RECOMMENDATION.search(unquoted) is None, s.text


async def test_histology_answer_cites_report_11(fixture_data: dict[str, Any]) -> None:
    result = await answer(fixture_data, "histology")

    assert result.status is AskStatus.ANSWERED
    assert "11_Histologie_KOC2_2026-10-19" in {c.doc_id for s in result.sentences for c in s.citations}


async def test_report_after_as_of_is_not_documented(fixture_data: dict[str, Any]) -> None:
    result = await answer(fixture_data, "after_as_of")

    assert result.status is AskStatus.NOT_DOCUMENTED
    assert not any(c.hit.doc_id.startswith("12_") for c in result.sources)


async def test_allergy_written_as_abbreviation_is_found(fixture_data: dict[str, Any]) -> None:
    result = await answer(fixture_data, "allergy")

    assert result.status is AskStatus.ANSWERED
    quotes = [c.quote for s in result.sentences for c in s.citations]
    assert any("neguje" in q for q in quotes), result.answer_text
