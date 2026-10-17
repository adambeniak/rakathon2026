"""GET /api/cases and GET /api/cases/{case_id}: case overview for the coordinator queue and the case header."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Path

from app.api.deps import CaseReaderDep, HandoverStoreDep, LlmClientsDep, SettingsDep
from app.api.schemas.cases import (
    BatonHolder,
    CaseCounts,
    CaseDetail,
    CaseSummary,
    DocumentSummary,
    EvidenceRef,
    PatientSummary,
    ReferringGp,
    SuspectedDiagnosis,
)
from app.api.schemas.common import problem_responses
from app.api.services.case_counts import case_counts, counts_for
from app.domain.case import Case
from app.domain.common import BUSINESS_ID_PATTERN
from app.fhir.cases import CaseExtras

router = APIRouter(prefix="/cases", tags=["cases"])


def summary_fields(
    case: Case, today: date, extras: CaseExtras | None = None, counts: CaseCounts | None = None
) -> dict[str, object]:
    extras = extras or CaseExtras()
    patient = case.patient
    return {
        "id": case.id,
        "patient": PatientSummary(
            display_name=patient.display_name,
            birth_date=patient.birth_date,
            age_years=patient.age_on(today),
            sex=patient.sex,
            insurer_code=patient.insurer_code,
        ),
        "state": case.state,
        "baton_holder": BatonHolder(**case.baton_holder.model_dump()) if case.baton_holder else None,
        "next_deadline": case.next_deadline,
        "opened_at": case.opened_at,
        "postponed": case.odlozeny,
        "bucket": case.bucket,
        "suspected_diagnosis": SuspectedDiagnosis(
            code=extras.diagnosis_code,
            text=extras.diagnosis_text,
            evidence=[EvidenceRef(doc_id=e.doc_id, quote=e.quote) for e in extras.diagnosis_evidence],
        )
        if extras.diagnosis_text
        else None,
        "koc": extras.koc_name,
        "referring_gp": ReferringGp(name=extras.gp_name, practice=extras.gp_practice) if extras.gp_name else None,
        "counts": counts,
        # The same numbers under their older names; null when the handover cannot be built.
        "missing_count": counts.missing if counts else None,
        "conflict_count": counts.conflict if counts else None,
    }


@router.get(
    "",
    response_model=list[CaseSummary],
    summary="List cases",
    responses=problem_responses(500, 502, 503),
)
async def list_cases(
    reader: CaseReaderDep, settings: SettingsDep, store: HandoverStoreDep, llm: LlmClientsDep
) -> list[CaseSummary]:
    today = settings.now().date()
    overviews = await reader.list_cases()
    counts = await counts_for([o.case for o in overviews], reader=reader, store=store, settings=settings, llm=llm)
    return [
        CaseSummary.model_validate({**summary_fields(o.case, today, o.extras, c), "document_count": o.document_count})
        for o, c in zip(overviews, counts, strict=True)
    ]


@router.get(
    "/{case_id}",
    response_model=CaseDetail,
    summary="Case detail with its documents",
    responses=problem_responses(404, 422, 500, 502, 503),
)
async def get_case(
    reader: CaseReaderDep,
    settings: SettingsDep,
    store: HandoverStoreDep,
    llm: LlmClientsDep,
    case_id: str = Path(pattern=BUSINESS_ID_PATTERN, max_length=100, examples=["rakathon-2026-prochazkova"]),
) -> CaseDetail:
    view = await reader.get_case(case_id)
    documents = [
        DocumentSummary.model_validate(d.model_dump(exclude={"file_name", "content_type"})) for d in view.documents
    ]
    counts = await case_counts(view.case, reader=reader, store=store, settings=settings, llm=llm)
    return CaseDetail.model_validate(
        {
            **summary_fields(view.case, settings.now().date(), view.extras, counts),
            "document_count": len(documents),
            "documents": documents,
        }
    )
