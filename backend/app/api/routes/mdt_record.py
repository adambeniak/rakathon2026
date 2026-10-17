"""GET /api/cases/{case_id}/mdt-record: the MDT record (zápis z jednání MDT) in the MDT_zapis layout, DOCX or PDF.

Always as of the MDT start (`Case.mdt_start`): reports authored or received after it are listed as "po MDT" and never
used. Sections carry their review status (Potvrzeno lékařem / Návrh AI – čeká na potvrzení / Chybí). Once a KOC
physician has signed the MDT conclusion (`record_mdt_conclusion`, at or after the MDT start), section 6 prints it as
signed, with who and when; until then sections 6 and 7 are left for the physicians. The system never writes a
conclusion or a recommendation (docs/adr/XXXX-mdt-record-post-mdt-pdf.md). Only the KOC team of the case may export it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Path, Query
from fastapi.responses import Response

from app.api.deps import (
    ActorDep,
    CaseReaderDep,
    CaseWorkflowDep,
    DirectoryProviderDep,
    HandoverStoreDep,
    LlmClientsDep,
    RepositoryDep,
    SettingsDep,
)
from app.api.routes.handover import _reviewed
from app.api.schemas.common import problem_responses
from app.domain.common import BUSINESS_ID_PATTERN, PartyRef, Role
from app.domain.errors import ForbiddenError, InvalidInputError, NotFoundError
from app.fhir.cases import LoadedCase
from app.fhir.directory import Directory
from app.fhir.workflow import authorize_case
from app.outputs.mdt_record import (
    DOCX_MEDIA_TYPE,
    ReferringDoctor,
    SignedConclusion,
    is_draft,
    render_mdt_record,
)
from app.outputs.mdt_record_pdf import PDF_MEDIA_TYPE, render_mdt_record_pdf
from app.settings import PRAGUE

router = APIRouter(prefix="/cases", tags=["handover"])

CASE_ID = Path(pattern=BUSINESS_ID_PATTERN, max_length=100, examples=["rakathon-2026-prochazkova"])
# The record is an internal KOC document: not for the referring GP (who gets the feedback) or the insurer's reviewer.
KOC_ROLES = frozenset({Role.COORDINATOR, Role.KOC_PHYSICIAN, Role.KOC_STAFF})
RENDERERS = {"docx": (render_mdt_record, DOCX_MEDIA_TYPE), "pdf": (render_mdt_record_pdf, PDF_MEDIA_TYPE)}


@router.get(
    "/{case_id}/mdt-record",
    response_class=Response,
    summary="MDT record in the MDT_zapis layout (DOCX or PDF), as of the MDT start",
    description="Content only from the handover as of `mdt_start` and its findings; reports created or received after "
    "it are listed as excluded ('po MDT'). Each section is labelled 'Potvrzeno lékařem' (who, when), 'Návrh AI – čeká "
    "na potvrzení lékařem' or 'Chybí', with its notes and missing items, and a blocking readiness item waived at "
    "`mark_ready_mdt` is printed next to its section (who, when, reason); a banner and a page header mark the "
    "document as a draft (and the file name carries NAVRH) while any section is unconfirmed. Once a KOC physician "
    "has signed the MDT conclusion (at or after `mdt_start`), section 6 prints its text as signed, labelled "
    "'Potvrzeno lékařem' with who and when, and section 7 points to it; before that sections 6 and 7 (Závěr, "
    "Doporučení MDT) are left for the physicians. The system never writes a conclusion or a recommendation. "
    "`format=pdf` renders the same content as a PDF (fonts embedded). KOC team of the case only; every export is "
    "audited (with the conclusion's Composition when it is printed).",
    responses={
        200: {
            "content": {
                DOCX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}},
                PDF_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}},
            },
            "description": "DOCX or PDF document (by `format`)",
        },
        **problem_responses(401, 403, 404, 422, 500, 502, 503),
    },
)
async def get_mdt_record(
    reader: CaseReaderDep,
    settings: SettingsDep,
    llm: LlmClientsDep,
    store: HandoverStoreDep,
    repository: RepositoryDep,
    provider: DirectoryProviderDep,
    workflow: CaseWorkflowDep,
    actor: ActorDep,
    case_id: str = CASE_ID,
    format: Literal["docx", "pdf"] = Query("docx", description="File format: DOCX (default) or PDF."),
) -> Response:
    if actor.role not in KOC_ROLES:  # checked first: a refused caller causes no audited read of clinical content
        raise ForbiddenError("Zápis z MDT je dostupný jen týmu KOC, který případ vede")
    loaded = await reader.load(case_id)  # audited read
    directory = await provider.get()
    authorize_case(loaded, actor, directory)
    mdt_start = loaded.case.mdt_start
    if mdt_start is None:
        raise InvalidInputError("U případu není nastaven termín MDT")

    handover = await _reviewed(reader, settings, llm, store, case_id, mdt_start.isoformat())
    activity = await reader.activity(loaded.task, loaded.case)  # waived readiness items, printed next to their section
    conclusion, conclusion_ref = await _signed_conclusion(workflow, case_id, actor, directory, mdt_start)
    render, media_type = RENDERERS[format]
    content = await asyncio.to_thread(
        render,
        handover,
        _referring_doctor(loaded, directory),
        settings.now(),
        activity.readiness_waivers,
        conclusion,
    )
    # An export is a disclosure of the case: name the same entities as a read, so a search by patient finds it.
    entities = [
        f"Task/{loaded.task['id']}",
        *(str(loaded.task[k]["reference"]) for k in ("for", "focus") if k in loaded.task),
        *activity.references,
        *([conclusion_ref] if conclusion_ref else []),
    ]
    await repository.audit_derived_write(entities, description=f"MDT record exported as {format.upper()}")
    day = mdt_start.astimezone(PRAGUE).date().isoformat()
    filename = f"mdt-zapis-{'NAVRH-' if is_draft(handover) else ''}{day}.{format}"
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _signed_conclusion(
    workflow: CaseWorkflowDep, case_id: str, actor: PartyRef, directory: Directory, mdt_start: datetime
) -> tuple[SignedConclusion | None, str | None]:
    """The latest signed MDT conclusion of the case (read and audited by the workflow) and its Composition reference.

    Only a conclusion signed at or after the MDT start belongs to this meeting's record: the state machine refuses an
    earlier one, and a conclusion of an earlier meeting (the MDT was moved) is never printed under a later date.
    """
    try:
        record = await workflow.get_conclusion(case_id, actor=actor, directory=directory)
    except NotFoundError:
        return None, None
    if record.signed_at < mdt_start:
        return None, None
    signed = SignedConclusion(text=record.text, signer_display=record.signer_display, signed_at=record.signed_at)
    return signed, f"Composition/{record.composition_id}"


def _referring_doctor(loaded: LoadedCase, directory: Directory) -> ReferringDoctor | None:
    """The referring GP (Task.requester) with the practice phone from the directory; no e-mail is held."""
    reference = loaded.task.get("requester", {}).get("reference")
    entry = next((r for r in directory.roles if r.ref == reference), None) if reference else None
    if entry is None:
        return None
    practice = directory.org(entry.role.organization_id)
    return ReferringDoctor(name=entry.display, phone=practice.org.phone if practice else None)
