"""Run the extraction on a GP letter: the prefill of the form and the examinations it lists (the only LLM call)."""

from __future__ import annotations

from app.documents.ingest import UploadedDocument
from app.domain.errors import ExtractionUnavailableError
from app.domain.evidence import Fact
from app.domain.referral import ReferralPrefill
from app.domain.triage import ListedExam
from app.extraction.llm import CacheMissError, RetryableError
from app.extraction.pipeline import CompletionClient, extract_facts
from app.extraction.referral_exams import listed_exams
from app.extraction.referral_prefill import build_prefill


async def extract_letter_facts(upload: UploadedDocument, client: CompletionClient) -> list[Fact]:
    try:
        extraction = await extract_facts(upload.doc, client)
    except (CacheMissError, RetryableError) as exc:
        # Messages name the document id and cache key only; nothing from the letter's content.
        raise ExtractionUnavailableError("Žádanku se nyní nepodařilo analyzovat; vyplňte údaje ručně.") from exc
    return list(extraction.accepted)


async def prefill_from_letter(upload: UploadedDocument, client: CompletionClient) -> ReferralPrefill:
    facts = await extract_letter_facts(upload, client)
    return build_prefill(facts, doc_id=upload.doc.doc_id, authored_at=upload.doc.authored_date)


async def exams_from_letter(upload: UploadedDocument, client: CompletionClient) -> list[ListedExam]:
    return listed_exams(upload.doc, await extract_letter_facts(upload, client))
