"""Handover build: documents -> normalised text -> facts (cached LLM) -> epicrisis (LLM) -> `assemble_handover`.

I/O is limited to the two LLM clients; the caller loads the case and the document bytes (FHIR) and passes them in.
Only documents known at `as_of` are normalised and extracted, so excluded documents never reach the model.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

import structlog

from app.documents.normalize import normalize_bytes
from app.domain.document import SourceDocument
from app.domain.finding import Finding
from app.domain.handover import Handover
from app.domain.patient import Patient
from app.extraction.handover.assemble import assemble_handover, included_facts, split_documents
from app.extraction.handover.epicrisis import generate_epicrisis
from app.extraction.handover.facts import HandoverRules
from app.extraction.pipeline import CompletionClient, extract_case

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
    normalized = {doc_id: normalize_bytes(doc_id, contents[doc_id], doc) for doc_id, doc in included.items()}
    _, facts = await extract_case(normalized, extraction, as_of)
    facts = included_facts(facts, included)
    field4 = await generate_epicrisis(facts, included, epicrisis, case_id=case_id)
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
    )
    log.info(
        "handover_assembled",
        case_id=case_id,
        included=len(handover.included_documents),
        excluded=len(handover.excluded_documents),
        facts=len(facts),
        epicrisis_mode=field4.value.mode if field4.value else None,
    )
    return handover
