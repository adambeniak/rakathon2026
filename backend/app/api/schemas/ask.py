"""Schemas of POST /api/cases/{case_id}/ask ("ask the case", ADR-0004)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from pydantic.config import JsonDict

from app.retrieval.ask import AskStatus

_REQUEST_EXAMPLE: JsonDict = {
    "question": "Kdy byla vysazena antikoagulace před biopsií?",
    "as_of": "2026-10-21T08:00:00+02:00",
}
_CITATION_EXAMPLE: JsonDict = {
    "doc_id": "09_Biopsie_vykon_KOC2_2026-10-12",
    "title": "EUS-FNB – protokol o výkonu (KOC 2)",
    "quote": "Apixaban vysazen 48 h před výkonem (poslední dávka 18. 10. 2026 večer).",
}
_RESPONSE_EXAMPLE: JsonDict = {
    "label": "Návrh AI",
    "disclaimer": "Návrh AI – neověřeno lékařem, ověřte v citovaných dokumentech.",
    "status": "answered",
    "as_of": "2026-10-21T08:00:00+02:00",
    "answer_text": "V protokolu o výkonu z 12. 10. 2026 je uvedeno, že apixaban byl vysazen 48 h před výkonem. "
    "[09_Biopsie_vykon_KOC2_2026-10-12]",
    "prefix": None,
    "sentences": [
        {
            "text": "V protokolu o výkonu z 12. 10. 2026 je uvedeno, že apixaban byl vysazen 48 h před výkonem.",
            "citations": [_CITATION_EXAMPLE],
        }
    ],
    "sources": [
        {
            "doc_id": "09_Biopsie_vykon_KOC2_2026-10-12",
            "title": "EUS-FNB – protokol o výkonu (KOC 2)",
            "seq": 1,
            "authored_at": "2026-10-12",
            "received_at": "2026-10-12T11:00:00Z",
            "char_start": 312,
            "char_end": 640,
            "text": "… Apixaban vysazen 48 h před výkonem (poslední dávka 18. 10. 2026 večer). …",
            "rrf_score": 0.0311,
            "vector_rank": 7,
            "text_rank": 2,
            "cosine": 0.47,
        }
    ],
    "dropped_sentences": 0,
    "model": "gpt-6-1-sol-dz-eu",
    "prompt_version": "ask-v2",
    "embedding_model": "local:sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
}


class AskRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [_REQUEST_EXAMPLE]})

    question: str = Field(min_length=3, max_length=500, description="Question in Czech. Never logged.")
    as_of: AwareDatetime | None = Field(
        None, description="Only documents authored before this day and received by this time. Default: demo now."
    )


class AskCitation(BaseModel):
    doc_id: str
    title: str
    quote: str = Field(description="Verbatim span of the cited chunk (= of the normalised source document).")


class AskSentence(BaseModel):
    text: str
    citations: list[AskCitation] = Field(
        min_length=1,
        description="The UI must show these quotes next to the sentence: a word-level lock cannot catch a wrong "
        "meaning, the reader can.",
    )


class AskSource(BaseModel):
    """A retrieved chunk the answer was generated from (IRIS hybrid search), in retrieval order."""

    doc_id: str
    title: str
    seq: int
    authored_at: date
    received_at: AwareDatetime
    char_start: int
    char_end: int
    text: str
    rrf_score: float = Field(description="Reciprocal-rank-fusion score of the vector and full-text legs.")
    vector_rank: int | None = Field(None, description="Rank in the IRIS VECTOR_COSINE leg (1 = best).")
    text_rank: int | None = Field(None, description="Rank in the IRIS iFind full-text leg (1 = best).")
    cosine: float | None = Field(None, description="Cosine similarity from the vector leg.")


class AskResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [_RESPONSE_EXAMPLE]})

    label: Literal["Návrh AI"] = Field(description="AI output is a draft until a clinician confirms it.")
    disclaimer: str = Field(description="Fixed Czech disclaimer, always shown with the answer.")
    status: AskStatus = Field(
        description="answered | not_documented | not_verified (the model answered but no sentence could be "
        "evidence-locked; the sources must be checked) | advice_declined (no advice, only cited documentation)."
    )
    as_of: AwareDatetime
    answer_text: str = Field(description="Ready-to-show Czech text; every sentence ends with [doc_id].")
    prefix: str | None = Field(None, description="Fixed refusal prefix for advice questions.")
    sentences: list[AskSentence]
    sources: list[AskSource]
    dropped_sentences: int = Field(description="Sentences removed by the evidence lock.")
    model: str
    prompt_version: str
    embedding_model: str
