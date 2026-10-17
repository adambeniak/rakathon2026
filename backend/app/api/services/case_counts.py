"""Case summary counters (Chybí / Nesouhlasí / Zastaralé), computed from the handover service.

The numbers are read from the very handover the handover screen shows: assembled at the case's `mdt_start` (or the
demo clock), with the stored review applied (a value the physician filled in is no longer missing). `None` means the
handover could not be built; it is never a false zero.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import structlog

from app.api.deps import LlmClients
from app.api.schemas.cases import CaseCounts
from app.api.services.handover_assembly import assemble_handover, default_cut_off, with_review
from app.domain.case import Case
from app.domain.handover import Handover, HandoverFields, HandoverStatus
from app.fhir.cases import CaseReader
from app.fhir.handover_store import HandoverStore
from app.settings import Settings

log = structlog.get_logger(__name__)

# The list builds one handover per case; keep the load on IRIS and the LLM cache bounded.
MAX_PARALLEL = 4


# The sections the handover screen marks "Chybí": a missing section, or a partial one with sub-items not stated.
# A stale section (its missing current weight) or one that needs clarification has its own badge: not counted twice.
MISSING_BADGE = frozenset({HandoverStatus.MISSING, HandoverStatus.PARTIAL})


def count_handover(handover: Handover) -> CaseCounts | None:
    """Counters as the handover screen shows them.

    missing: sub-items the sources do not state in the sections marked Chybí (a whole section that is missing counts
    once if it names no sub-item); conflict: distinct findings that contradict a value; stale: sections whose value
    is out of date.

    Without a single usable document nothing was assembled (the handover screen shows its empty state): `None`.
    """
    if not handover.included_documents:
        return None
    fields = [getattr(handover.fields, name) for name in HandoverFields.model_fields]
    missing = sum(
        len(f.missing_items) or len(f.missing) or (1 if f.status == HandoverStatus.MISSING else 0)
        for f in fields
        if f.status in MISSING_BADGE
    )
    conflicts = {finding for f in fields for finding in f.conflicts}
    stale = sum(1 for f in fields if f.status == HandoverStatus.STALE)
    return CaseCounts(missing=missing, conflict=len(conflicts), stale=stale)


async def case_counts(
    case: Case, *, reader: CaseReader, store: HandoverStore, settings: Settings, llm: LlmClients
) -> CaseCounts | None:
    cut_off = default_cut_off(case, settings)
    try:
        handover = await assemble_handover(reader, settings, llm, case.id, cut_off)
        reviewed = with_review(handover, await store.find(case.id, cut_off))
    except Exception as exc:  # noqa: BLE001 - a summary must not fail because one handover cannot be built
        log.warning("case_counts_unavailable", case_id=case.id, error=type(exc).__name__)
        return None
    return count_handover(reviewed)


async def counts_for(
    cases: Sequence[Case], *, reader: CaseReader, store: HandoverStore, settings: Settings, llm: LlmClients
) -> list[CaseCounts | None]:
    gate = asyncio.Semaphore(MAX_PARALLEL)

    async def one(case: Case) -> CaseCounts | None:
        async with gate:
            return await case_counts(case, reader=reader, store=store, settings=settings, llm=llm)

    return list(await asyncio.gather(*(one(c) for c in cases)))
