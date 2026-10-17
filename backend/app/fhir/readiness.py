"""Server-side input of the MDT readiness gate (`pathway.readiness_gate`); the client never supplies it.

Required items come from the PlanDefinition of the case's launched pathway(s); the status of each item is the
status of its section in the case's persisted handover (Composition for `as_of` = `mdt_start`). Reading never
assembles a handover (no LLM call inside a transition). Everything that cannot be established counts as `missing`
(fail closed): an unmapped item, a section absent from the Composition, a handover nobody has opened yet.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.domain.common import PartyRef
from app.domain.errors import InvalidInputError
from app.domain.events import TransitionError
from app.domain.pathway import Readiness, Waiver, readiness_gate
from app.fhir.cases import LoadedCase
from app.fhir.client import Resource
from app.fhir.handover_store import HandoverStore
from app.fhir.mappers.handover import stored_review
from app.fhir.mappers.plan_definition import plan_definition_to_template
from app.fhir.repository import FhirRepository
from app.fhir.systems import CS_HANDOVER_SECTION, EXT_HANDOVER_FIELD_STATUS, SID_CAREPLAN

# PlanDefinition readiness item -> handover section whose status decides it. `ct_staging` and `tumour_markers`
# have no section of their own: they are read from the examinations and the laboratory sections.
READINESS_SECTION: Mapping[str, str] = {
    "histology": "14_histology",
    "ct_staging": "12_examinations",
    "tumour_markers": "13_labs",
    "comorbidities": "6_comorbidities",
    "performance_status": "9_performance_status",
    "mdt_question": "5_mdt_question",
}

MISSING = "missing"
COMPLETE = "complete"


@dataclass(frozen=True)
class WaiverRequest:
    """What the client may say about a waiver: the item and the reason. Signer and role are the acting user's."""

    item: str
    reason: str


class ReadinessSource:
    def __init__(self, repository: FhirRepository) -> None:
        self._repo = repository
        self._handovers = HandoverStore(repository)

    async def evaluate(self, loaded: LoadedCase, actor: PartyRef, waivers: Sequence[WaiverRequest] = ()) -> Readiness:
        """The gate result for the case now. Refuses (`guard_failed`) when it cannot be established at all."""
        required = await self._required_items(loaded)
        mdt_start = loaded.case.mdt_start
        if mdt_start is None:
            raise TransitionError("guard_failed", "Není nastaven termín MDT, handover pro MDT nelze určit")
        composition = await self._handovers.find(loaded.case.id, mdt_start)
        if composition is None:
            raise TransitionError(
                "guard_failed", "Handover pro MDT ještě nebyl sestaven; před označením připravenosti jej otevřete"
            )
        items = [w.item for w in waivers]
        if len(set(items)) != len(items):
            raise InvalidInputError("Položku připravenosti lze prominout jen jednou")
        signed = [Waiver(w.item, actor.role, actor.id, w.reason) for w in waivers]
        try:
            return readiness_gate(section_statuses(composition, required), required, signed)
        except ValueError as exc:  # unknown item, blank reason or id, wrong role
            raise InvalidInputError(str(exc)) from exc

    async def _required_items(self, loaded: LoadedCase) -> tuple[str, ...]:
        patient = str(loaded.task["for"]["reference"])
        prefix = f"{loaded.case.id}."
        plans = [
            p
            for p in await self._repo.search("CarePlan", {"subject": patient, "_count": "50"})
            if any(
                i.get("system") == SID_CAREPLAN and str(i.get("value", "")).startswith(prefix)
                for i in p.get("identifier", [])
            )
        ]
        if not plans:
            raise TransitionError(
                "guard_failed", "Pro případ nebyla spuštěna žádná sada vyšetření, připravenost k MDT nelze určit"
            )
        await self._repo.audit_read([f"CarePlan/{p['id']}" for p in plans], subtype="search-type")
        required: list[str] = []
        for care_plan in plans:
            for url in care_plan.get("instantiatesCanonical", []):
                found = await self._repo.search("PlanDefinition", {"url": url})
                if len(found) != 1:
                    raise TransitionError("guard_failed", f"Šablonu sady vyšetření {url!r} nelze najít")
                try:
                    items = plan_definition_to_template(found[0]).mdt_required_items
                except ValueError as exc:
                    raise TransitionError("guard_failed", "Šablonu sady vyšetření nelze použít") from exc
                required += [i for i in items if i not in required]
        if not required:
            raise TransitionError("guard_failed", "Sada vyšetření nedefinuje žádné položky připravenosti k MDT")
        return tuple(required)


def section_statuses(composition: Resource, required: Sequence[str]) -> dict[str, str]:
    """Handover field status per required item; an item without a readable section is left out (= missing).

    A section the physician filled in by hand counts as `complete`, as in the handover view (`overlay_review`).
    """
    stored = stored_review(composition)
    by_section: dict[str, str] = {}
    for section in composition.get("section", []):
        key = next(
            (c["code"] for c in section.get("code", {}).get("coding", []) if c.get("system") == CS_HANDOVER_SECTION),
            None,
        )
        status = next(
            (
                e["valueCoding"]["code"]
                for e in section.get("extension", [])
                if e.get("url") == EXT_HANDOVER_FIELD_STATUS
            ),
            None,
        )
        if key is not None and status is not None:
            by_section[key] = COMPLETE if status == MISSING and key in stored.edited_values else status
    return {
        item: by_section[READINESS_SECTION[item]]
        for item in required
        if item in READINESS_SECTION and READINESS_SECTION[item] in by_section
    }
