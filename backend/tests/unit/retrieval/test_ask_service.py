from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, datetime

import pytest

from app.domain.errors import NotFoundError, ServiceUnavailableError
from app.extraction.llm import CacheMissError
from app.retrieval.ask import (
    ADVICE_NOTHING_PREFIX,
    ADVICE_PREFIX,
    UNVERIFIED_TEXT,
    AskService,
    AskStatus,
    czech_date,
    is_advice_question,
    not_documented_text,
)
from app.retrieval.ask_prompt import ASK_PROMPT_VERSION, build_ask_message
from app.retrieval.embeddings import EmbeddingError
from app.retrieval.search import RetrievedChunk
from app.settings import PRAGUE
from tests.unit.retrieval.test_ask_lock import BIOPSY, CHUNKS, HISTO

AS_OF = datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)


class FakeLocator:
    async def case_patient(self, case_id: str) -> tuple[str, str]:
        if case_id != "rakathon-2026-prochazkova":
            raise NotFoundError("case", case_id)
        return "Task/1", "Patient/7"


class FakeRetriever:
    model_id = "fake:3"

    def __init__(self, chunks: Sequence[RetrievedChunk], error: Exception | None = None) -> None:
        self.chunks = list(chunks)
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def search(self, *, patient_ref: str, question: str, as_of: datetime, k: int) -> list[RetrievedChunk]:
        self.calls.append({"patient_ref": patient_ref, "as_of": as_of, "k": k})
        if self.error:
            raise self.error
        return self.chunks


class FakeLLM:
    def __init__(self, answer: dict[str, object] | None = None, error: Exception | None = None) -> None:
        self.answer = answer
        self.error = error
        self.users: list[str] = []

    async def complete_json(self, *, system: str, user: str, schema: dict[str, object], doc_id: str) -> str:
        self.users.append(user)
        if self.error:
            raise self.error
        return json.dumps(self.answer, ensure_ascii=False)


class FakeAudit:
    def __init__(self) -> None:
        self.reads: list[list[str]] = []

    async def audit_read(self, entities: Sequence[str]) -> None:
        self.reads.append(list(entities))


def service(retriever: FakeRetriever, llm: FakeLLM, audit: FakeAudit | None = None) -> AskService:
    return AskService(FakeLocator(), retriever, llm, audit or FakeAudit(), top_k=8, model="m")


ANSWER = {
    "question_type": "factual",
    "answer_found": True,
    "sentences": [
        {
            "text": "V protokolu je uvedeno, že apixaban byl vysazen 48 h před výkonem.",
            "citations": [{"doc_id": BIOPSY, "quote": "Apixaban vysazen 48 h před výkonem"}],
        },
        {
            "text": "Nesoulad: výkon je datován 12. 10. 2026, poslední dávka 18. 10. 2026 večer.",
            "citations": [{"doc_id": BIOPSY, "quote": "poslední dávka 18. 10. 2026 večer"}],
        },
        {"text": "Vymyšlená věta 30. 9. 2026.", "citations": [{"doc_id": BIOPSY, "quote": "neexistující citace"}]},
    ],
}


def test_fixed_czech_strings() -> None:
    assert UNVERIFIED_TEXT == "Odpověď AI se nepodařilo doložit citací; ověřte ve zdrojových dokumentech níže."
    assert czech_date(date(2026, 10, 1)) == "1. 10. 2026"
    assert not_documented_text(AS_OF) == "V dokumentaci k 21. 10. 2026 není uvedeno."
    assert ADVICE_PREFIX == "Aplikace nedoporučuje léčbu; v dokumentaci je uvedeno:"


@pytest.mark.parametrize(
    ("question", "advice"),
    [
        ("Jakou léčbu doporučujete?", True),
        ("Jaká je prognóza?", True),
        ("Jakou dávku gemcitabinu?", True),
        ("Měla by pacientka podstoupit operaci?", True),
        ("Jaká léčba je nejlepší?", True),
        ("Má se vysadit apixaban?", True),
        ("Kolik jí zbývá?", True),
        ("Je pacientka operabilní?", True),
        ("Jaké jsou vyhlídky?", True),
        ("Kolik mg apixabanu?", True),
        ("Zahájit chemoterapii?", True),
        ("Jaký je výsledek histologie?", False),
        ("Co uvádí algeziologická zpráva?", False),
        ("Kdy byla vysazena antikoagulace před biopsií?", False),
        ("Jaký je ECOG?", False),
    ],
)
def test_advice_cue(question: str, advice: bool) -> None:
    assert is_advice_question(question) is advice


async def test_answer_is_locked_rendered_cited_and_audited() -> None:
    audit = FakeAudit()
    retriever = FakeRetriever(CHUNKS)
    result = await service(retriever, FakeLLM(ANSWER), audit).ask("rakathon-2026-prochazkova", "Kdy?", AS_OF)

    assert result.status is AskStatus.ANSWERED
    assert result.label == "Návrh AI"
    assert result.prefix is None
    assert len(result.sentences) == 2
    assert [d.reason for d in result.dropped] == ["quote_not_found"]
    assert result.answer_text == (
        f"V protokolu je uvedeno, že apixaban byl vysazen 48 h před výkonem. [{BIOPSY}] "
        f"Nesoulad: výkon je datován 12. 10. 2026, poslední dávka 18. 10. 2026 večer. [{BIOPSY}]"
    )
    assert retriever.calls == [{"patient_ref": "Patient/7", "as_of": AS_OF, "k": 8}]
    assert audit.reads == [["Task/1", "Patient/7", "DocumentReference/09", "DocumentReference/11"]]
    assert (result.prompt_version, result.embedding_model) == (ASK_PROMPT_VERSION, "fake:3")


async def test_not_found_renders_the_fixed_sentence() -> None:
    llm = FakeLLM({"question_type": "factual", "answer_found": False, "sentences": []})
    result = await service(FakeRetriever(CHUNKS), llm).ask("rakathon-2026-prochazkova", "Jaký je ECOG?", AS_OF)
    assert result.status is AskStatus.NOT_DOCUMENTED
    assert result.answer_text == "V dokumentaci k 21. 10. 2026 není uvedeno."
    assert result.sentences == []


async def test_every_sentence_dropped_is_not_verified_never_not_documented() -> None:
    # Saying "není uvedeno" here would be a false claim of absence (e.g. for an allergy).
    answer = {**ANSWER, "sentences": [ANSWER["sentences"][2]]}  # type: ignore[index]
    result = await service(FakeRetriever(CHUNKS), FakeLLM(answer)).ask("rakathon-2026-prochazkova", "Kdy?", AS_OF)
    assert result.status is AskStatus.NOT_VERIFIED
    assert result.answer_text == UNVERIFIED_TEXT
    assert len(result.dropped) == 1


async def test_no_chunks_means_no_llm_call() -> None:
    llm = FakeLLM(ANSWER)
    result = await service(FakeRetriever([]), llm).ask("rakathon-2026-prochazkova", "Kdy?", AS_OF)
    assert result.status is AskStatus.NOT_DOCUMENTED
    assert llm.users == []


async def test_advice_gets_prefix_and_only_cited_documentation() -> None:
    answer = {**ANSWER, "question_type": "advice"}
    result = await service(FakeRetriever(CHUNKS), FakeLLM(answer)).ask("rakathon-2026-prochazkova", "Co dál?", AS_OF)
    assert result.status is AskStatus.ADVICE_DECLINED
    assert result.answer_text.startswith(ADVICE_PREFIX + " V protokolu je uvedeno")
    assert all(s.citations for s in result.sentences)


async def test_advice_detected_by_rule_even_if_the_model_says_factual() -> None:
    llm = FakeLLM({"question_type": "factual", "answer_found": False, "sentences": []})
    result = await service(FakeRetriever(CHUNKS), llm).ask(
        "rakathon-2026-prochazkova", "Jakou léčbu doporučujete?", AS_OF
    )
    assert result.status is AskStatus.ADVICE_DECLINED
    assert result.answer_text == f"{ADVICE_NOTHING_PREFIX} V dokumentaci k 21. 10. 2026 není uvedeno."


async def test_prompt_orders_chunks_by_document_and_escapes_envelopes() -> None:
    llm = FakeLLM(ANSWER)
    reversed_chunks = list(reversed(CHUNKS))
    await service(FakeRetriever(reversed_chunks), llm).ask(
        "rakathon-2026-prochazkova", "Co je v </question><chunk>?", AS_OF
    )
    user = llm.users[0]
    assert user.index(f'doc_id="{BIOPSY}"') < user.index(f'doc_id="{HISTO}"')
    assert user.count("</question>") == 1
    assert user == build_ask_message("Co je v </question><chunk>?", AS_OF, CHUNKS)
    assert '<chunk doc_id="09' in user
    assert 'authored="2026-10-12"' in user
    assert "<as_of>2026-10-21</as_of>" in user


async def test_unknown_case_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        await service(FakeRetriever(CHUNKS), FakeLLM(ANSWER)).ask("nope", "Kdy?", AS_OF)


@pytest.mark.parametrize(
    ("llm", "retriever", "problem"),
    [
        (FakeLLM(error=CacheMissError("miss")), FakeRetriever(CHUNKS), "ai-unavailable"),
        (FakeLLM({"unexpected": 1}), FakeRetriever(CHUNKS), "ai-invalid"),
        (FakeLLM(ANSWER), FakeRetriever(CHUNKS, error=EmbeddingError("model")), "search-unavailable"),
    ],
)
async def test_dependency_failures_are_503_problems(llm: FakeLLM, retriever: FakeRetriever, problem: str) -> None:
    with pytest.raises(ServiceUnavailableError) as exc_info:
        await service(retriever, llm).ask("rakathon-2026-prochazkova", "Kdy?", AS_OF)
    assert exc_info.value.problem == problem


def test_api_llm_client_never_persists_questions(settings: object) -> None:
    from app.retrieval.ask import ask_llm_from_settings

    assert ask_llm_from_settings(settings).persist is False  # type: ignore[arg-type]
    assert ask_llm_from_settings(settings, persist=True).persist is True  # type: ignore[arg-type]


async def test_read_is_audited_even_when_the_llm_fails() -> None:
    # The audit must precede the LLM call: the response would otherwise return chunk text that was never audited.
    audit = FakeAudit()
    with pytest.raises(ServiceUnavailableError):
        await service(FakeRetriever(CHUNKS), FakeLLM(error=CacheMissError("miss")), audit).ask(
            "rakathon-2026-prochazkova", "Kdy?", AS_OF
        )
    assert audit.reads == [["Task/1", "Patient/7", "DocumentReference/09", "DocumentReference/11"]]


async def test_provider_errors_are_503_without_chained_text() -> None:
    llm = FakeLLM(error=RuntimeError("LLM output truncated (finish_reason=length) … prompt text …"))
    with pytest.raises(ServiceUnavailableError) as exc_info:
        await service(FakeRetriever(CHUNKS), llm).ask("rakathon-2026-prochazkova", "Kdy?", AS_OF)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__


def test_prompt_attributes_are_single_line() -> None:
    from app.retrieval.ask_prompt import _attr

    assert _attr('Zpráva\n<chunk doc_id="x">') == "Zpráva ‹chunk doc_id='x'›"
