"""GET /api/cases and GET /api/cases/{case_id}: case overview for the coordinator queue and the case header."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Path, status

from app.api.deps import CaseReaderDep, SettingsDep
from app.api.schemas.cases import BatonHolder, CaseDetail, CaseSummary, DocumentSummary, PatientSummary
from app.api.schemas.common import ProblemDetails
from app.domain.case import Case
from app.domain.common import BUSINESS_ID_PATTERN

router = APIRouter(prefix="/cases", tags=["cases"])

_PROBLEMS: dict[int | str, dict[str, object]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ProblemDetails, "description": "IRIS unavailable"},
}


def _summary_fields(case: Case, today: date) -> dict[str, object]:
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
    }


@router.get("", response_model=list[CaseSummary], summary="List cases", responses=_PROBLEMS)
async def list_cases(reader: CaseReaderDep, settings: SettingsDep) -> list[CaseSummary]:
    today = settings.now().date()
    overviews = await reader.list_cases()
    return [
        CaseSummary.model_validate({**_summary_fields(o.case, today), "document_count": o.document_count})
        for o in overviews
    ]


@router.get(
    "/{case_id}",
    response_model=CaseDetail,
    summary="Case detail with its documents",
    responses={status.HTTP_404_NOT_FOUND: {"model": ProblemDetails, "description": "Unknown case"}, **_PROBLEMS},
)
async def get_case(
    reader: CaseReaderDep,
    settings: SettingsDep,
    case_id: str = Path(pattern=BUSINESS_ID_PATTERN, max_length=100, examples=["rakathon-2026-prochazkova"]),
) -> CaseDetail:
    view = await reader.get_case(case_id)
    documents = [
        DocumentSummary.model_validate(d.model_dump(exclude={"file_name", "content_type"})) for d in view.documents
    ]
    return CaseDetail.model_validate(
        {
            **_summary_fields(view.case, settings.now().date()),
            "document_count": len(documents),
            "documents": documents,
        }
    )
