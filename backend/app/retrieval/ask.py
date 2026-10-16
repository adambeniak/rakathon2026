"""Ask the case (owner: P1): hybrid retrieval in IRIS -> LLM answer in Czech from those chunks only -> evidence lock.

The result is a draft labelled "Návrh AI" (AGENTS.md 5). The two fixed answers are rendered here, never by the
LLM: "V dokumentaci k <datum> není uvedeno." and the advice refusal prefix (AGENTS.md 3). Every retrieved
document is audited as read (AGENTS.md 6). Logs carry ids, counts and timings only: never the question (it may
contain PHI) and never document text.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol

import openai
import structlog
from pydantic import ValidationError

from app.domain.errors import ServiceUnavailableError
from app.extraction.llm import LLMClient
from app.extraction.pipeline import CompletionClient
from app.iris.vector_store import VectorStoreUnavailableError
from app.retrieval.ask_lock import DroppedSentence, LockedSentence, lock_answer
from app.retrieval.ask_prompt import ASK_PROMPT_VERSION, ASK_SCHEMA, ASK_SYSTEM_PROMPT, RawAnswer, build_ask_message
from app.retrieval.embeddings import EmbeddingError
from app.retrieval.search import RetrievedChunk
from app.settings import PRAGUE, Settings

log = structlog.get_logger(__name__)

LABEL = "Návrh AI"
DISCLAIMER = "Návrh AI – neověřeno lékařem, ověřte v citovaných dokumentech."
ADVICE_PREFIX = "Aplikace nedoporučuje léčbu; v dokumentaci je uvedeno:"
ADVICE_NOTHING_PREFIX = "Aplikace nedoporučuje léčbu."
# The model found an answer but no sentence survived the evidence lock: never claim the fact is absent.
UNVERIFIED_TEXT = "Odpověď AI se nepodařilo doložit citací; ověřte ve zdrojových dokumentech níže."

# Questions asking what to do or what will happen. Deliberately broad: a false positive only adds the prefix and
# restricts the answer to cited documentation.
ADVICE_CUE = re.compile(
    r"(?<!\w)(doporuč\w*|navrhuj\w*|navrhn\w*|poraď\w*|poradit|dávk\w*|dávkován\w*|prognóz\w*|přežit\w*|šanc\w*"
    r"|léčb\w*|léčit|terapi\w*|chemoterapi\w*|vysadit|nasadit|zahájit|pokračovat|indikovat|zvolit|operab\w*"
    r"|resekab\w*|vyhlídk\w*|zbýv\w*|nejlepš\w*|vhodn\w*|mg|měl[aiy]? by|by\s+měl[aiy]?|měli bychom|má se"
    r"|má smysl|co (dál|dělat|teď))(?!\w)",
    re.IGNORECASE,
)


class AskStatus(StrEnum):
    ANSWERED = "answered"
    NOT_DOCUMENTED = "not_documented"
    NOT_VERIFIED = "not_verified"  # the model answered, but nothing survived the evidence lock
    ADVICE_DECLINED = "advice_declined"


def czech_date(value: date) -> str:
    return f"{value.day}. {value.month}. {value.year}"


def not_documented_text(as_of: datetime) -> str:
    return f"V dokumentaci k {czech_date(as_of.astimezone(PRAGUE).date())} není uvedeno."


def is_advice_question(question: str) -> bool:
    return ADVICE_CUE.search(question) is not None


@dataclass(frozen=True)
class AskResult:
    status: AskStatus
    as_of: datetime
    answer_text: str
    prefix: str | None
    sentences: list[LockedSentence]
    sources: list[RetrievedChunk]
    dropped: list[DroppedSentence]
    model: str
    prompt_version: str
    embedding_model: str
    label: str = LABEL
    disclaimer: str = DISCLAIMER


class CaseLocator(Protocol):
    async def case_patient(self, case_id: str) -> tuple[str, str]:
        """(coordinating Task reference, Patient reference); raises NotFoundError."""
        ...


class Retriever(Protocol):
    @property
    def model_id(self) -> str: ...

    async def search(self, *, patient_ref: str, question: str, as_of: datetime, k: int) -> list[RetrievedChunk]: ...


class ReadAuditor(Protocol):
    async def audit_read(self, entities: Sequence[str]) -> None: ...


def ask_llm_from_settings(settings: Settings, *, persist: bool = False) -> LLMClient:
    """Fast deployment if configured, else the extraction one; own prompt version = own cache keys.

    The API never writes live answers (they contain the user's question) to the cache; only the eval recorder does.
    """
    return LLMClient.from_settings(
        settings, prompt_version=ASK_PROMPT_VERSION, model=settings.llm_model_fast or None, persist=persist
    )


def render(sentences: Sequence[LockedSentence]) -> str:
    out = []
    for s in sentences:
        doc_ids = list(dict.fromkeys(c.doc_id for c in s.citations))
        out.append(f"{s.text} [{', '.join(doc_ids)}]")
    return " ".join(out)


class AskService:
    def __init__(
        self,
        locator: CaseLocator,
        retriever: Retriever,
        llm: CompletionClient,
        auditor: ReadAuditor,
        *,
        top_k: int,
        model: str,
    ) -> None:
        self._locator = locator
        self._retriever = retriever
        self._llm = llm
        self._auditor = auditor
        self._top_k = top_k
        self._model = model

    async def ask(self, case_id: str, question: str, as_of: datetime) -> AskResult:
        started = time.perf_counter()
        task_ref, patient_ref = await self._locator.case_patient(case_id)
        try:
            chunks = await self._retriever.search(
                patient_ref=patient_ref, question=question, as_of=as_of, k=self._top_k
            )
        except (EmbeddingError, VectorStoreUnavailableError) as exc:
            log.error("ask_search_failed", case_id=case_id, error_type=type(exc).__name__)
            raise ServiceUnavailableError("search-unavailable", "Vyhledávání v dokumentaci není dostupné.") from exc
        doc_refs = list(dict.fromkeys(c.hit.doc_ref for c in chunks))
        await self._auditor.audit_read([task_ref, patient_ref, *doc_refs])

        advice = is_advice_question(question)
        answer: RawAnswer | None = None
        if chunks:
            answer = await self._complete(case_id, question, as_of, chunks)
            advice = advice or answer.question_type == "advice"
        claimed = answer is not None and answer.answer_found
        kept, dropped = lock_answer(answer.sentences, chunks) if answer and claimed else ([], [])

        if kept:
            status = AskStatus.ADVICE_DECLINED if advice else AskStatus.ANSWERED
            prefix = ADVICE_PREFIX if advice else None
            body = render(kept)
        elif claimed or dropped:  # the model claims an answer it could not back with a citation: never "není uvedeno"
            status = AskStatus.ADVICE_DECLINED if advice else AskStatus.NOT_VERIFIED
            prefix = ADVICE_NOTHING_PREFIX if advice else None
            body = UNVERIFIED_TEXT
        else:
            status = AskStatus.ADVICE_DECLINED if advice else AskStatus.NOT_DOCUMENTED
            prefix = ADVICE_NOTHING_PREFIX if advice else None
            body = not_documented_text(as_of)
        log.info(
            "ask_answered",
            case_id=case_id,
            status=status.value,
            chunks=len(chunks),
            documents=len(doc_refs),
            sentences=len(kept),
            dropped=dict(Counter(d.reason for d in dropped)),
            ms=round((time.perf_counter() - started) * 1000),
        )
        return AskResult(
            status=status,
            as_of=as_of,
            answer_text=f"{prefix} {body}" if prefix else body,
            prefix=prefix,
            sentences=kept,
            sources=chunks,
            dropped=dropped,
            model=self._model,
            prompt_version=ASK_PROMPT_VERSION,
            embedding_model=self._retriever.model_id,
        )

    async def _complete(
        self, case_id: str, question: str, as_of: datetime, chunks: Sequence[RetrievedChunk]
    ) -> RawAnswer:
        try:
            text = await self._llm.complete_json(
                system=ASK_SYSTEM_PROMPT,
                user=build_ask_message(question, as_of, chunks),
                schema=ASK_SCHEMA,
                doc_id=f"ask:{case_id}",
            )
        except ValueError as exc:  # live mode: the client parses the JSON before returning it (malformed / empty)
            log.error("ask_llm_invalid_response", case_id=case_id, error_type=type(exc).__name__)
            raise ServiceUnavailableError("ai-invalid", "Odpověď AI nemá očekávaný tvar.") from None
        except (RuntimeError, openai.OpenAIError) as exc:  # cache miss, retries exhausted, APIM/content-filter errors
            # Provider messages may quote the prompt (question, document text): log the type only, never chain it.
            log.warning("ask_llm_unavailable", case_id=case_id, error_type=type(exc).__name__)
            raise ServiceUnavailableError("ai-unavailable", "Odpověď AI teď není k dispozici.") from None
        try:
            return RawAnswer.model_validate(json.loads(text))
        except (ValueError, ValidationError) as exc:
            log.error("ask_llm_invalid_response", case_id=case_id, error_type=type(exc).__name__)
            raise ServiceUnavailableError("ai-invalid", "Odpověď AI nemá očekávaný tvar.") from exc
