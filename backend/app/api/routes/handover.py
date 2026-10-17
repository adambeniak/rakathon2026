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
from app.api.services.handover_assembly import assemble_handover, default_cut_off, with_review
from app.api.services.reviewer import deny_reviewer
from app.domain.common import BUSINESS_ID_PATTERN, PartyRef, Role
from app.domain.errors import ConflictError, ForbiddenError, InvalidInputError
from app.domain.handover import Handover, HandoverStatus, ReviewState, SectionReview
from app.extraction.handover.epicrisis import EPICRISIS_PROMPT_VERSION
from app.extraction.handover.export import to_markdown
from app.extraction.handover.review import (
    field_of,
    section_key,
    validate_edited_value,
    value_hash,
)
from app.extraction.llm import CACHE_MODEL
from app.extraction.prompt import PROMPT_VERSION
from app.fhir.cases import CaseReader
from app.fhir.handover_store import HandoverStore
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
            raise ValueError(
                f"Hodnota edited_value je příliš dlouhá (maximální počet znaků: {MAX_EDITED_VALUE_CHARS})."
            )
        return value


async def parse_as_of(value: str | None, settings: Settings, reader: CaseReader, case_id: str) -> datetime:
    """Without `as_of` the cut-off is `default_cut_off` (the case's `mdt_start`, else the demo-aware now)."""
    if value is None:
        return default_cut_off((await reader.load(case_id)).case, settings)
    try:
        if len(value) == 10:
            return datetime.combine(date.fromisoformat(value), MDT_START_TIME, tzinfo=PRAGUE)
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise InvalidInputError(
            "Parametr as_of musí mít tvar RRRR-MM-DD nebo časové razítko ISO 8601 s posunem od UTC"
        ) from exc
    if parsed.tzinfo is None:
        raise InvalidInputError("Časové razítko as_of musí obsahovat posun od UTC")
    return parsed


def device_display(settings: Settings) -> str:
    model = settings.llm_model_extract or CACHE_MODEL
    return f"Štafeta AI · {model} · {PROMPT_VERSION}, {EPICRISIS_PROMPT_VERSION}"


async def _reviewed(
    reader: CaseReaderDep,
    settings: SettingsDep,
    llm: LlmClientsDep,
    store: HandoverStore,
    case_id: str,
    as_of: str | None,
) -> Handover:
    cut_off = await parse_as_of(as_of, settings, reader, case_id)
    handover = await assemble_handover(reader, settings, llm, case_id, cut_off)
    return with_review(handover, await store.find(case_id, cut_off))


@router.get(
    "/{case_id}/handover",
    response_model=Handover,
    summary="Handover (15 fields) as of a timestamp",
    description="Deterministic assembly from evidence-locked facts; every value cites its source. Documents "
    "authored or received after `as_of` are listed in `excluded_documents`. AI parts are drafts ('Návrh AI'). "
    "If the handover was persisted, the stored review state and confirmed edits are applied.",
    responses=problem_responses(401, 403, 404, 422, 500, 502, 503),
)
async def get_handover(
    reader: CaseReaderDep,
    settings: SettingsDep,
    llm: LlmClientsDep,
    store: HandoverStoreDep,
    actor: ActorDep,
    case_id: str = CASE_ID,
    as_of: str | None = AS_OF,
) -> Handover:
    deny_reviewer(actor)
    return await _reviewed(reader, settings, llm, store, case_id, as_of)


@router.post(
    "/{case_id}/handover",
    response_model=Handover,
    summary="Persist the handover for review (Composition preliminary + Provenance)",
    description="Idempotent per (case, as_of): an existing Composition and its review state are kept.",
    responses=problem_responses(401, 403, 404, 422, 500, 502, 503),
)
async def persist_handover(
    reader: CaseReaderDep,
    settings: SettingsDep,
    llm: LlmClientsDep,
    store: HandoverStoreDep,
    actor: ActorDep,
    case_id: str = CASE_ID,
    as_of: str | None = AS_OF,
) -> Handover:
    deny_reviewer(actor)
    cut_off = await parse_as_of(as_of, settings, reader, case_id)
    handover = await assemble_handover(reader, settings, llm, case_id, cut_off)
    composition = await store.persist(handover, device_display=device_display(settings), recorded=settings.now())
    return with_review(handover, composition)


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
    cut_off = await parse_as_of(as_of, settings, reader, case_id)
    handover = await assemble_handover(reader, settings, llm, case_id, cut_off)
    composition = await store.persist(handover, device_display=device_display(settings), recorded=settings.now())
    assembled = field_of(handover, key)
    if body.expected_value_hash != assembled.value_hash:
        raise ConflictError(f"Oddíl {key} se od zobrazení změnil; před potvrzením načtěte handover znovu")
    current = field_of(with_review(handover, composition), key)
    missing = current.status == HandoverStatus.MISSING
    if body.accept_missing and body.edited_value is not None:
        raise InvalidInputError("Použijte buď edited_value, nebo accept_missing, ne obojí")
    if body.accept_missing and not missing:
        raise ConflictError(f"Oddíl {key} nechybí; potvrďte jej nebo upravte")
    if missing and not body.accept_missing and body.edited_value is None:
        raise ConflictError(f"Oddíl {key} chybí: pošlete accept_missing nebo edited_value")
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
    return with_review(handover, updated)


def _require_confirming_role(actor: PartyRef) -> None:
    if actor.role not in CONFIRMING_ROLES:
        raise ForbiddenError("Oddíl handoveru může potvrdit jen lékař KOC")


@router.get(
    "/{case_id}/handover/export",
    response_class=PlainTextResponse,
    summary="Handover as copyable text (Markdown), one block per section",
    responses={
        200: {"content": {"text/markdown": {"schema": {"type": "string"}}}, "description": "Markdown"},
        **problem_responses(401, 403, 404, 422, 500, 502, 503),
    },
)
async def export_handover(
    reader: CaseReaderDep,
    settings: SettingsDep,
    llm: LlmClientsDep,
    store: HandoverStoreDep,
    actor: ActorDep,
    case_id: str = CASE_ID,
    as_of: str | None = AS_OF,
    format: Literal["md"] = Query("md", description="Only Markdown for now."),
) -> PlainTextResponse:
    deny_reviewer(actor)
    handover = await _reviewed(reader, settings, llm, store, case_id, as_of)
    return PlainTextResponse(to_markdown(handover), media_type="text/markdown; charset=utf-8")
