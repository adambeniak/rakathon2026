"""POST /api/cases/{case_id}/documents: a received report; links it to its request and completes that request."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, File, Form, Path, UploadFile

from app.api.deps import ActorDep, CaseReaderDep, DirectoryProviderDep, RequestWorkflowDep, SettingsDep
from app.api.routes.cases import summary_fields
from app.api.schemas.cases import CaseSummary, DocumentSummary
from app.api.schemas.common import problem_responses
from app.api.schemas.workflow import DocumentReceived
from app.api.uploads import read_upload
from app.domain.common import BUSINESS_ID_PATTERN
from app.domain.errors import InvalidInputError

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post(
    "/{case_id}/documents",
    status_code=201,
    response_model=DocumentReceived,
    summary="Upload a received report (DOCX/PDF)",
    description="With `request_id` the report fulfils that request (business status `vysledek_dorucen`); when it was "
    "the "
    "last open request of a case in `ceka_na_podklady`, the case moves to `kompletni` (event `podklady_kompletni`). "
    "`authored_at` defaults to the date in the file name.",
    responses=problem_responses(401, 403, 404, 409, 413, 415, 422, 502, 503),
)
async def upload_document(
    file: Annotated[UploadFile, File(description="DOCX or PDF with a text layer, up to 10 MB.")],
    workflow: RequestWorkflowDep,
    reader: CaseReaderDep,
    provider: DirectoryProviderDep,
    actor: ActorDep,
    settings: SettingsDep,
    case_id: Annotated[str, Path(pattern=BUSINESS_ID_PATTERN, max_length=100)],
    request_id: Annotated[str | None, Form(pattern=BUSINESS_ID_PATTERN, max_length=140)] = None,
    authored_at: Annotated[date | None, Form(description="Date the report was written (ISO).")] = None,
) -> DocumentReceived:
    upload = await read_upload(file, max_bytes=settings.upload_max_bytes)
    authored = authored_at or upload.doc.authored_date
    if authored is None:
        raise InvalidInputError("authored_at is required: the file name carries no date")
    now = settings.now()
    outcome = await workflow.receive_document(
        case_id,
        upload,
        authored_at=authored,
        request_id=request_id,
        actor=actor,
        directory=await provider.get(),
        now=now,
    )
    overview = await reader.overview(case_id)
    case = CaseSummary.model_validate(
        {**summary_fields(overview.case, now.date(), overview.extras), "document_count": overview.document_count}
    )
    return DocumentReceived(
        document=DocumentSummary.model_validate(outcome.document.model_dump(exclude={"file_name", "content_type"})),
        open_requests_remaining=outcome.open_requests_remaining,
        case_event=outcome.case_event,
        case=case,
    )
