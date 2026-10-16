"""POST /api/cases/{case_id}/ask: a question about the case, answered only from its documents, with citations."""

from __future__ import annotations

from fastapi import APIRouter, Path

from app.api.deps import AskServiceDep, SettingsDep
from app.api.schemas.ask import AskCitation, AskRequest, AskResponse, AskSentence, AskSource
from app.api.schemas.common import problem_responses
from app.domain.common import BUSINESS_ID_PATTERN
from app.retrieval.ask import AskResult

router = APIRouter(prefix="/cases", tags=["cases"])


def to_response(result: AskResult) -> AskResponse:
    return AskResponse(
        label="Návrh AI",
        disclaimer=result.disclaimer,
        status=result.status,
        as_of=result.as_of,
        answer_text=result.answer_text,
        prefix=result.prefix,
        sentences=[
            AskSentence(
                text=s.text,
                citations=[AskCitation(doc_id=c.doc_id, title=c.title, quote=c.quote) for c in s.citations],
            )
            for s in result.sentences
        ],
        sources=[
            AskSource(
                doc_id=c.hit.doc_id,
                title=c.hit.title,
                seq=c.hit.seq,
                authored_at=c.hit.authored_on,
                received_at=c.hit.received_at,
                char_start=c.hit.char_start,
                char_end=c.hit.char_end,
                text=c.hit.text,
                rrf_score=round(c.score, 6),
                vector_rank=c.vector_rank,
                text_rank=c.text_rank,
                cosine=round(c.vector_score, 4) if c.vector_score is not None else None,
            )
            for c in result.sources
        ],
        dropped_sentences=len(result.dropped),
        model=result.model,
        prompt_version=result.prompt_version,
        embedding_model=result.embedding_model,
    )


@router.post(
    "/{case_id}/ask",
    response_model=AskResponse,
    summary="Ask the case (AI draft with citations, no advice)",
    description=(
        "Hybrid retrieval in IRIS (VECTOR_COSINE on HNSW + iFind full text, as-of filtered) and an LLM answer in "
        "Czech from the retrieved chunks only. Every sentence is evidence-locked to a verbatim quote; questions "
        "asking for treatment, dose or prognosis get only cited documentation. Fictitious data only."
    ),
    responses=problem_responses(404, 422, 500, 503),
)
async def ask_case(
    body: AskRequest,
    service: AskServiceDep,
    settings: SettingsDep,
    case_id: str = Path(pattern=BUSINESS_ID_PATTERN, max_length=100, examples=["rakathon-2026-prochazkova"]),
) -> AskResponse:
    result = await service.ask(case_id, body.question, body.as_of or settings.now())
    return to_response(result)
