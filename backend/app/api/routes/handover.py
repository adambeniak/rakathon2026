"""GET /api/cases/{case_id}/handover (+ /export): the 15-field handover at an as-of timestamp (F2-2)."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from fastapi import APIRouter, Path, Query
from fastapi.responses import PlainTextResponse

from app.api.deps import CaseReaderDep, LlmClientsDep, SettingsDep
from app.api.schemas.common import problem_responses
from app.domain.common import BUSINESS_ID_PATTERN
from app.domain.errors import InvalidInputError
from app.domain.handover import Handover
from app.extraction.handover.export import to_markdown
from app.extraction.handover.facts import HandoverRules
from app.extraction.handover.service import build_handover
from app.settings import PRAGUE, Settings

router = APIRouter(prefix="/cases", tags=["handover"])

# A date-only as_of means the MDT start on that day (demo convention: MDT starts at 08:00 Europe/Prague).
MDT_START_TIME = time(8, 0)
CASE_ID = Path(pattern=BUSINESS_ID_PATTERN, max_length=100, examples=["rakathon-2026-prochazkova"])
AS_OF = Query(
    None,
    max_length=40,
    description="Cut-off: a date (= 08:00 Europe/Prague that day, MDT start) or an ISO timestamp with offset. "
    "Default: the current (demo) time.",
    examples=["2026-10-21", "2026-10-21T08:00:00+02:00"],
)


def parse_as_of(value: str | None, settings: Settings) -> datetime:
    if value is None:
        return settings.now()
    try:
        if len(value) == 10:
            return datetime.combine(date.fromisoformat(value), MDT_START_TIME, tzinfo=PRAGUE)
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InvalidInputError("as_of must be YYYY-MM-DD or an ISO 8601 timestamp with offset") from exc
    if parsed.tzinfo is None:
        raise InvalidInputError("as_of timestamp must include a UTC offset")
    return parsed


async def _handover(
    reader: CaseReaderDep, settings: SettingsDep, llm: LlmClientsDep, case_id: str, as_of: str | None
) -> Handover:
    cut_off = parse_as_of(as_of, settings)
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


@router.get(
    "/{case_id}/handover",
    response_model=Handover,
    summary="Handover (15 fields) as of a timestamp",
    description="Deterministic assembly from evidence-locked facts; every value cites its source. Documents "
    "authored or received after `as_of` are listed in `excluded_documents`. AI parts are drafts ('Návrh AI').",
    responses=problem_responses(404, 422, 500, 502, 503),
)
async def get_handover(
    reader: CaseReaderDep,
    settings: SettingsDep,
    llm: LlmClientsDep,
    case_id: str = CASE_ID,
    as_of: str | None = AS_OF,
) -> Handover:
    return await _handover(reader, settings, llm, case_id, as_of)


@router.get(
    "/{case_id}/handover/export",
    response_class=PlainTextResponse,
    summary="Handover as copyable text (Markdown), one block per section",
    responses={
        200: {"content": {"text/markdown": {"schema": {"type": "string"}}}, "description": "Markdown"},
        **problem_responses(404, 422, 500, 502, 503),
    },
)
async def export_handover(
    reader: CaseReaderDep,
    settings: SettingsDep,
    llm: LlmClientsDep,
    case_id: str = CASE_ID,
    as_of: str | None = AS_OF,
    format: Literal["md"] = Query("md", description="Only Markdown for now."),
) -> PlainTextResponse:
    handover = await _handover(reader, settings, llm, case_id, as_of)
    return PlainTextResponse(to_markdown(handover), media_type="text/markdown; charset=utf-8")
