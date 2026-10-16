"""Handover build: documents -> normalised text -> facts (cached LLM) -> epicrisis (LLM) -> `assemble_handover`.

I/O is limited to the two LLM clients; the caller loads the case and the document bytes (FHIR) and passes them in.
Only documents known at `as_of` are normalised and extracted, so excluded documents never reach the model.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import datetime

import structlog

from app.documents.normalize import NormalizedDoc, normalize_bytes
from app.domain.document import SourceDocument
from app.domain.evidence import Fact
from app.domain.finding import Finding
from app.domain.handover import Handover
from app.domain.patient import Patient
from app.extraction.handover.assemble import assemble_handover, included_facts, split_documents
from app.extraction.handover.epicrisis import generate_epicrisis
from app.extraction.handover.facts import HandoverRules
from app.extraction.lock import filter_as_of
from app.extraction.pipeline import CompletionClient, extract_facts

log = structlog.get_logger(__name__)


async def build_handover(
    case_id: str,
    as_of: datetime,
    documents: Sequence[SourceDocument],
    contents: Mapping[str, bytes],
    *,
    extraction: CompletionClient,
    epicrisis: CompletionClient,
    patient: Patient | None = None,
    findings: Sequence[Finding] = (),
    rules: HandoverRules | None = None,
    generated_at: datetime | None = None,
) -> Handover:
    by_id = {d.doc_id: d for d in documents}
    included, _ = split_documents(by_id, as_of)
    unavailable: dict[str, str] = {}
    normalized: dict[str, NormalizedDoc] = {}
    for doc_id, doc in included.items():
        if doc_id not in contents:
            unavailable[doc_id] = "obsah dokumentu není dostupný"
            continue
        normalized[doc_id] = normalize_bytes(doc_id, contents[doc_id], doc)
    results = await asyncio.gather(*(extract_facts(d, extraction) for d in normalized.values()), return_exceptions=True)
    accepted: list[Fact] = []
    for ndoc, result in zip(normalized.values(), results, strict=True):
        if isinstance(result, BaseException):
            if not isinstance(result, Exception):
                raise result
            # One unreadable document must not hide the others; it is listed as excluded with the reason.
            log.warning(
                "handover_document_unavailable", case_id=case_id, doc_id=ndoc.doc_id, error=type(result).__name__
            )
            unavailable[ndoc.doc_id] = "extrakce dokumentu není k dispozici"
            continue
        accepted.extend(result.accepted)
    usable = {k: v for k, v in included.items() if k not in unavailable}
    facts = included_facts(filter_as_of(accepted, normalized, as_of, require_received=True), usable)
    field4 = await generate_epicrisis(facts, usable, epicrisis, case_id=case_id)
    handover = assemble_handover(
        case_id,
        as_of,
        facts,
        by_id,
        patient=patient,
        findings=findings,
        epicrisis=field4,
        rules=rules,
        generated_at=generated_at,
        unavailable=unavailable,
    )
    log.info(
        "handover_assembled",
        unavailable=len(unavailable),
        case_id=case_id,
        included=len(handover.included_documents),
        excluded=len(handover.excluded_documents),
        facts=len(facts),
        epicrisis_mode=field4.value.mode if field4.value else None,
    )
    return handover
