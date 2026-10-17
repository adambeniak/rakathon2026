"""Handover assembly shared by the handover routes and the case summary counters."""

from __future__ import annotations

from datetime import datetime

from app.api.deps import LlmClients
from app.domain.case import Case
from app.domain.handover import Handover
from app.extraction.handover.facts import HandoverRules
from app.extraction.handover.review import overlay_review
from app.extraction.handover.service import build_handover
from app.fhir.cases import CaseReader
from app.fhir.client import Resource
from app.fhir.mappers.handover import stored_review
from app.settings import Settings


def default_cut_off(case: Case, settings: Settings) -> datetime:
    """Without an explicit `as_of`: the case's `mdt_start` (set at pathway launch), else the demo-aware now.

    A fixed default makes repeated reads and confirmations hit the same Composition (its business id carries as_of).
    """
    return case.mdt_start if case.mdt_start is not None else settings.now()


async def assemble_handover(
    reader: CaseReader, settings: Settings, llm: LlmClients, case_id: str, cut_off: datetime
) -> Handover:
    view = await reader.get_case_contents(case_id)
    return await build_handover(
        case_id,
        cut_off,
        view.documents,
        view.contents,
        extraction=llm.extraction,
        epicrisis=llm.epicrisis,
        patient=view.case.patient,
        rules=HandoverRules(stale_vitals_days=settings.handover_stale_vitals_days),
        generated_at=settings.now(),
    )


def with_review(handover: Handover, composition: Resource | None) -> Handover:
    """The assembled handover with the stored review state and the physician's edited values applied."""
    if composition is None:
        return handover
    stored = stored_review(composition)
    return overlay_review(
        handover,
        composition_id=stored.business_id,
        status=stored.status,
        sections=stored.sections,
        edited_values=stored.edited_values,
    )
