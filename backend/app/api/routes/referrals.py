"""Referral intake: prefill from the GP letter (nothing persisted), then the GP's confirmation creates the case."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.api.deps import (
    ActorDep,
    CaseReaderDep,
    DirectoryProviderDep,
    LlmClientDep,
    ReferralWriterDep,
    RepositoryDep,
    SettingsDep,
)
from app.api.routes.cases import summary_fields
from app.api.schemas.cases import CaseSummary
from app.api.schemas.common import problem_responses
from app.api.schemas.referrals import ReferralCreated
from app.api.uploads import read_upload
from app.domain.errors import ExtractionUnavailableError, InvalidInputError
from app.domain.referral import ReferralPrefill, ReferralSubmission
from app.extraction.referral_service import prefill_from_letter
from app.fhir.referrals import enrich_prefill

MAX_ATTACHMENTS = 5

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.post(
    "/prefill",
    response_model=ReferralPrefill,
    summary="Prefill the referral from the GP letter (DOCX/PDF); nothing is stored",
    description="Every value carries the verbatim quote it was read from; a value the letter does not state is "
    "`missing`. The sex is derived from the rodné číslo and marked `derived`. This is a draft for the GP to confirm.",
    responses=problem_responses(401, 413, 415, 422, 502, 503),
)
async def prefill_referral(
    letter: Annotated[UploadFile, File(description="The GP letter, DOCX or PDF with a text layer, up to 10 MB.")],
    llm: LlmClientDep,
    provider: DirectoryProviderDep,
    repository: RepositoryDep,
    _actor: ActorDep,
) -> ReferralPrefill:
    upload = await read_upload(letter)
    await repository.audit_extract()  # before the document leaves for the model
    prefill = await prefill_from_letter(upload, llm)
    return enrich_prefill(prefill, await provider.get())


@router.post(
    "",
    status_code=201,
    response_model=ReferralCreated,
    summary="Confirm the referral: creates the case in ONE FHIR transaction",
    description="Multipart: `letter` (the same file as for the prefill), optional `attachments`, and `payload` = JSON "
    "of `ReferralSubmission` (the prefilled values as confirmed or edited by the GP). The case starts in state "
    "`odeslano` with the KOC coordinator on the baton. Only a GP may call this.",
    responses=problem_responses(401, 403, 409, 413, 415, 422, 502, 503),
)
async def create_referral(
    letter: Annotated[UploadFile, File()],
    payload: Annotated[str, Form(description="JSON of ReferralSubmission", max_length=20_000)],
    writer: ReferralWriterDep,
    repository: RepositoryDep,
    reader: CaseReaderDep,
    provider: DirectoryProviderDep,
    llm: LlmClientDep,
    actor: ActorDep,
    settings: SettingsDep,
    attachments: Annotated[list[UploadFile] | None, File(description="Further reports sent along, optional.")] = None,
) -> ReferralCreated:
    try:
        submission = ReferralSubmission.model_validate_json(payload)
    except ValidationError as exc:
        raise RequestValidationError(
            [{"loc": ("body", "payload", *e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        ) from exc
    if len(attachments or []) > MAX_ATTACHMENTS:
        raise InvalidInputError(f"at most {MAX_ATTACHMENTS} attachments are accepted")
    upload = await read_upload(letter)
    extras = [await read_upload(a) for a in attachments or []]
    directory = await provider.get()
    await repository.audit_extract()
    try:
        prefill = enrich_prefill(await prefill_from_letter(upload, llm), directory)
    except ExtractionUnavailableError:
        prefill = None  # the GP's confirmation stands; Provenance records that the prefill was not compared
    now = settings.now()
    result = await writer.submit(submission, upload, extras, actor=actor, directory=directory, now=now, prefill=prefill)
    overview = await reader.overview(result.case_id)
    case = CaseSummary.model_validate(
        {**summary_fields(overview.case, now.date(), overview.extras), "document_count": overview.document_count}
    )
    return ReferralCreated(case=case, warnings=list(result.warnings))
