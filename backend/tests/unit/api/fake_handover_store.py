"""In-memory stand-in for `HandoverStore` (API tests): real mapping, no HTTP."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import JsonValue

from app.domain.handover import Handover, SectionReview
from app.fhir.mappers.handover import FhirContext, handover_bundle, handover_business_id, with_section_review


class FakeStore:
    def __init__(self) -> None:
        self.compositions: dict[str, dict[str, Any]] = {}
        self.confirmations: list[tuple[str, SectionReview, JsonValue | None, str]] = []
        self.persist_calls = 0

    async def find(self, case_id: str, as_of: datetime) -> dict[str, Any] | None:
        return self.compositions.get(handover_business_id(case_id, as_of))

    async def persist(self, handover: Handover, *, device_display: str, recorded: datetime) -> dict[str, Any]:
        self.persist_calls += 1
        key = handover_business_id(handover.case_id, handover.as_of)
        if key not in self.compositions:
            ctx = FhirContext("Patient/1", "EpisodeOfCare/2", {}, device_display, recorded)
            resource = handover_bundle(handover, ctx)["entry"][0]["resource"]
            self.compositions[key] = {**resource, "id": str(len(self.compositions) + 1)}
        return self.compositions[key]

    async def confirm_section(
        self,
        composition: dict[str, Any],
        key: str,
        review: SectionReview,
        *,
        edited_value: JsonValue | None,
        previous_hash: str,
    ) -> dict[str, Any]:
        updated = with_section_review(composition, key, review, edited_value)
        self.compositions[updated["identifier"]["value"]] = updated
        self.confirmations.append((key, review, edited_value, previous_hash))
        return updated
