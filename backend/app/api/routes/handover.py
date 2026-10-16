"""Handover API (F2-2): assemble, persist for review, confirm sections, export.

- GET  /api/cases/{case_id}/handover?as_of=   assembled handover (+ stored review state if persisted)
- POST /api/cases/{case_id}/handover?as_of=   assemble and persist (Composition preliminary + Provenance)
- POST /api/cases/{case_id}/handover/sections/{n}/confirm   physician confirms / edits / accepts as missing
- GET  /api/cases/{case_id}/handover/export?format=md
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from typing import Literal

from fastapi import APIRouter, Path, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from app.api.deps import ActorDep, CaseReaderDep, HandoverStoreDep, LlmClientsDep, SettingsDep
from app.api.schemas.common import problem_responses
from app.domain.common import BUSINESS_ID_PATTERN, PartyRef, Role
from app.domain.errors import ConflictError, ForbiddenError, InvalidInputError
from app.domain.handover import Handover, HandoverStatus, ReviewState, SectionReview
from app.extraction.handover.epicrisis import EPICRISIS_PROMPT_VERSION
from app.extraction.handover.export import to_markdown
from app.extraction.handover.facts import HandoverRules
from app.extraction.handover.review import (
    field_of,
    overlay_review,
    section_key,
    validate_edited_value,
    value_hash,
)
from app.extraction.handover.service import build_handover
from app.extraction.llm import CACHE_MODEL
from app.extraction.prompt import PROMPT_VERSION
from app.fhir.client import Resource
from app.fhir.handover_store import HandoverStore
from app.fhir.mappers.handover import stored_review
from app.settings import PRAGUE, Settings

router = APIRouter(prefix="/cases", tags=["handover"])

# A date-only as_of means the MDT start on that day (demo convention: MDT starts at 08:00 Europe/Prague).
MDT_START_TIME = time(8, 0)
# Roles allowed to confirm a handover section (human in the loop, AGENTS rule 5).
CONFIRMING_ROLES = frozenset({Role.KOC_PHYSICIAN})
MAX_EDITED_VALUE_CHARS = 20_000
CASE_ID = Path(pattern=BUSINESS_ID_PATTERN, max_length=100, examples=["rakathon-2026-prochazkova"])
AS_OF = Query(
    None,
    max_length=40,
    description="Cut-off: a date (= 08:00 Europe/Prague that day, MDT start) or an ISO timestamp with offset. "
    "Default: the current (demo) time.",
    examples=["2026-10-21", "2026-10-21T08:00:00+02:00"],
)


class ConfirmSection(BaseModel):
    """Body of a section confirmation. Without fields: the assembled value is confirmed as is."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"expected_value_hash": "<value_hash of the section as shown>"},
                {"expected_value_hash": "<value_hash>", "accept_missing": True},
            ]
        },
    )
    expected_value_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="`value_hash` of the section as the physician saw it; 409 if the content changed since.",
    )

    edited_value: JsonValue | None = Field(
        None, description="Physician's value; must fit the section's value schema (contracts/handover.schema.json)."
    )
    accept_missing: bool = Field(False, description="Confirm that a missing section stays missing for the MDT.")

    @field_validator("edited_value")
    @classmethod
    def _bounded(cls, value: JsonValue | None) -> JsonValue | None:
        if value is not None and len(json.dumps(value, ensure_ascii=False)) > MAX_EDITED_VALUE_CHARS:
            raise ValueError(f"edited_value is longer than {MAX_EDITED_VALUE_CHARS} characters")
        return value


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


def device_display(settings: Settings) -> str:
    model = settings.llm_model_extract or CACHE_MODEL
    return f"Štafeta AI · {model} · {PROMPT_VERSION}, {EPICRISIS_PROMPT_VERSION}"


async def _assemble(
    reader: CaseReaderDep, settings: SettingsDep, llm: LlmClientsDep, case_id: str, cut_off: datetime
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


def _with_review(handover: Handover, composition: Resource | None) -> Handover:
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


async def _reviewed(
    reader: CaseReaderDep,
    settings: SettingsDep,
    llm: LlmClientsDep,
    store: HandoverStore,
    case_id: str,
    as_of: str | None,
) -> Handover:
    cut_off = parse_as_of(as_of, settings)
    handover = await _assemble(reader, settings, llm, case_id, cut_off)
    return _with_review(handover, await store.find(case_id, cut_off))


@router.get(
    "/{case_id}/handover",
    response_model=Handover,
    summary="Handover (15 fields) as of a timestamp",
    description="Deterministic assembly from evidence-locked facts; every value cites its source. Documents "
    "authored or received after `as_of` are listed in `excluded_documents`. AI parts are drafts ('Návrh AI'). "
    "If the handover was persisted, the stored review state and confirmed edits are applied.",
    responses=problem_responses(404, 422, 500, 502, 503),
)
async def get_handover(
    reader: CaseReaderDep,
    settings: SettingsDep,
    llm: LlmClientsDep,
    store: HandoverStoreDep,
    case_id: str = CASE_ID,
    as_of: str | None = AS_OF,
) -> Handover:
    return await _reviewed(reader, settings, llm, store, case_id, as_of)


@router.post(
    "/{case_id}/handover",
    response_model=Handover,
    summary="Persist the handover for review (Composition preliminary + Provenance)",
    description="Idempotent per (case, as_of): an existing Composition and its review state are kept.",
    responses=problem_responses(404, 422, 500, 502, 503),
)
async def persist_handover(
    reader: CaseReaderDep,
    settings: SettingsDep,
    llm: LlmClientsDep,
    store: HandoverStoreDep,
    case_id: str = CASE_ID,
    as_of: str | None = AS_OF,
) -> Handover:
    cut_off = parse_as_of(as_of, settings)
    handover = await _assemble(reader, settings, llm, case_id, cut_off)
    composition = await store.persist(handover, device_display=device_display(settings), recorded=settings.now())
    return _with_review(handover, composition)


@router.post(
    "/{case_id}/handover/sections/{number}/confirm",
    response_model=Handover,
    summary="A KOC physician confirms, edits or accepts as missing one handover section",
    description="Recorded as Provenance (who, when, previous value hash) on the Composition; the Composition becomes "
    "final when all 15 sections are confirmed or accepted as missing. A missing section needs "
    "`accept_missing: true` or an `edited_value`.",
    responses=problem_responses(403, 404, 409, 422, 500, 502, 503),
)
async def confirm_section(
    body: ConfirmSection,
    reader: CaseReaderDep,
    settings: SettingsDep,
    llm: LlmClientsDep,
    store: HandoverStoreDep,
    actor: ActorDep,
    case_id: str = CASE_ID,
    number: int = Path(ge=1, le=15, description="Section 1..15 (Handover_obsah order)."),
    as_of: str | None = AS_OF,
) -> Handover:
    _require_confirming_role(actor)
    key = section_key(number)
    cut_off = parse_as_of(as_of, settings)
    handover = await _assemble(reader, settings, llm, case_id, cut_off)
    composition = await store.persist(handover, device_display=device_display(settings), recorded=settings.now())
    assembled = field_of(handover, key)
    if body.expected_value_hash != assembled.value_hash:
        raise ConflictError(f"section {key} changed since it was shown; reload the handover before confirming")
    current = field_of(_with_review(handover, composition), key)
    missing = current.status == HandoverStatus.MISSING
    if body.accept_missing and body.edited_value is not None:
        raise InvalidInputError("use either edited_value or accept_missing, not both")
    if body.accept_missing and not missing:
        raise ConflictError(f"section {key} is not missing; confirm or edit it instead")
    if missing and not body.accept_missing and body.edited_value is None:
        raise ConflictError(f"section {key} is missing: send accept_missing or an edited_value")
    edited = validate_edited_value(key, body.edited_value) if body.edited_value is not None else None
    review = SectionReview(
        state=ReviewState.ACCEPTED_MISSING if body.accept_missing else ReviewState.CONFIRMED,
        by=actor,
        at=settings.now(),
        edited=edited is not None,
        value_hash=assembled.value_hash,
    )
    updated = await store.confirm_section(
        composition, key, review, edited_value=edited, previous_hash=value_hash(current)
    )
    return _with_review(handover, updated)


def _require_confirming_role(actor: PartyRef) -> None:
    if actor.role not in CONFIRMING_ROLES:
        raise ForbiddenError("only a KOC physician may confirm a handover section")


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
    store: HandoverStoreDep,
    case_id: str = CASE_ID,
    as_of: str | None = AS_OF,
    format: Literal["md"] = Query("md", description="Only Markdown for now."),
) -> PlainTextResponse:
    handover = await _reviewed(reader, settings, llm, store, case_id, as_of)
    return PlainTextResponse(to_markdown(handover), media_type="text/markdown; charset=utf-8")
