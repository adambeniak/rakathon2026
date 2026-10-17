"""GET /api/cases/{case_id}/mdt-record: the MDT record (zápis z jednání MDT) as a DOCX in the MDT_zapis layout.

Always as of the MDT start (`Case.mdt_start`): reports authored or received after it are listed as "po MDT" and never
used. Sections carry their review status (Potvrzeno lékařem / Návrh AI – čeká na potvrzení / Chybí); the conclusion and
the recommendation (sections 6 and 7) are left for the physicians. Only the KOC team of the case may export it.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Path, Query
from fastapi.responses import Response

from app.api.deps import (
    ActorDep,
    CaseReaderDep,
    DirectoryProviderDep,
    HandoverStoreDep,
    LlmClientsDep,
    RepositoryDep,
    SettingsDep,
)
from app.api.routes.handover import _reviewed
from app.api.schemas.common import problem_responses
from app.domain.common import BUSINESS_ID_PATTERN, Role
from app.domain.errors import ForbiddenError, InvalidInputError
from app.fhir.cases import LoadedCase
from app.fhir.directory import Directory
from app.fhir.workflow import authorize_case
from app.outputs.mdt_record import DOCX_MEDIA_TYPE, ReferringDoctor, is_draft, render_mdt_record
from app.settings import PRAGUE

router = APIRouter(prefix="/cases", tags=["handover"])

CASE_ID = Path(pattern=BUSINESS_ID_PATTERN, max_length=100, examples=["rakathon-2026-prochazkova"])
# The record is an internal KOC document: not for the referring GP (who gets the feedback) or the insurer's reviewer.
KOC_ROLES = frozenset({Role.COORDINATOR, Role.KOC_PHYSICIAN, Role.KOC_STAFF})


@router.get(
    "/{case_id}/mdt-record",
    response_class=Response,
    summary="MDT record in the MDT_zapis layout (DOCX), as of the MDT start",
    description="Content only from the handover as of `mdt_start` and its findings; reports created or received after "
    "it are listed as excluded ('po MDT'). Each section is labelled 'Potvrzeno lékařem' (who, when), 'Návrh AI – čeká "
    "na potvrzení lékařem' or 'Chybí', with its notes and missing items; a banner and a page header mark the "
    "document as a draft (and the file name carries NAVRH) while any section is unconfirmed. Sections 6 and 7 "
    "(Závěr, Doporučení MDT) are left for the physicians. KOC team of the case only; every export is audited. "
    "PDF is not available yet.",
    responses={
        200: {
            "content": {DOCX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
            "description": "DOCX document",
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
    actor: ActorDep,
    case_id: str = CASE_ID,
    format: Literal["docx"] = Query("docx", description="Only DOCX for now."),
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
    content = await asyncio.to_thread(render_mdt_record, handover, _referring_doctor(loaded, directory), settings.now())
    # An export is a disclosure of the case: name the same entities as a read, so a search by patient finds it.
    entities = [
        f"Task/{loaded.task['id']}",
        *(str(loaded.task[k]["reference"]) for k in ("for", "focus") if k in loaded.task),
    ]
    await repository.audit_derived_write(entities, description="MDT record exported as DOCX")
    day = mdt_start.astimezone(PRAGUE).date().isoformat()
    filename = f"mdt-zapis-{'NAVRH-' if is_draft(handover) else ''}{day}.docx"
    return Response(
        content,
        media_type=DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _referring_doctor(loaded: LoadedCase, directory: Directory) -> ReferringDoctor | None:
    """The referring GP (Task.requester) with the practice phone from the directory; no e-mail is held."""
    reference = loaded.task.get("requester", {}).get("reference")
    entry = next((r for r in directory.roles if r.ref == reference), None) if reference else None
    if entry is None:
        return None
    practice = directory.org(entry.role.organization_id)
    return ReferringDoctor(name=entry.display, phone=practice.org.phone if practice else None)
