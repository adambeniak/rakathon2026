"""Persistence of the handover in IRIS FHIR: Composition + derived resources + Provenance (F2-2, ADR-0004).

All writes go through `FhirRepository` (tagged, audited); reads of the Composition are audited too.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import JsonValue

from app.domain.errors import NotFoundError
from app.domain.handover import Handover, SectionReview
from app.fhir.client import Resource, reference_from_location
from app.fhir.errors import FhirError
from app.fhir.mappers.handover import (
    FhirContext,
    confirmation_provenance,
    handover_bundle,
    handover_business_id,
    with_section_review,
)
from app.fhir.repository import FhirRepository
from app.fhir.systems import SID_CASE_TASK, SID_HANDOVER, SID_SOURCE_DOCUMENT


def _if_match(composition: Resource) -> dict[str, str]:
    """Optimistic locking: a concurrent confirmation of the same Composition fails (412) instead of being lost."""
    version = composition.get("meta", {}).get("versionId")
    return {"ifMatch": f'W/"{version}"'} if version else {}


class HandoverStore:
    def __init__(self, repository: FhirRepository) -> None:
        self._repo = repository

    async def find(self, case_id: str, as_of: datetime) -> Resource | None:
        """The stored Composition for (case, as_of), if any (audited read)."""
        found = await self._repo.find_by_identifier("Composition", SID_HANDOVER, handover_business_id(case_id, as_of))
        if found is not None:
            await self._repo.audit_read([f"Composition/{found['id']}"])
        return found

    async def persist(self, handover: Handover, *, device_display: str, recorded: datetime) -> Resource:
        """Idempotent per (case, as_of): an existing Composition (with its review state) is returned unchanged.

        One transaction (audited by the repository); the Composition is a conditional create, so a concurrent
        persist cannot create a second one.
        """
        existing = await self.find(handover.case_id, handover.as_of)
        if existing is not None:
            return existing
        ctx = await self._context(handover.case_id, device_display, recorded)
        bundle = handover_bundle(handover, ctx)
        response = await self._repo.transaction(bundle)
        location = (response.get("entry") or [{}])[0].get("response", {}).get("location")
        if not location:
            raise FhirError("transaction returned no location for the Composition")
        _, fhir_id = reference_from_location(str(location))
        composition: Resource = {**bundle["entry"][0]["resource"], "id": fhir_id}
        return composition

    async def confirm_section(
        self,
        composition: Resource,
        key: str,
        review: SectionReview,
        *,
        edited_value: JsonValue | None,
        previous_hash: str,
    ) -> Resource:
        """Record a physician's confirmation: section review (+ edited value) and a Provenance, in one transaction.

        The Composition becomes `final` with an attester once every section is confirmed or accepted as missing.
        """
        updated = with_section_review(composition, key, review, edited_value)
        reference = f"Composition/{composition['id']}"
        provenance = confirmation_provenance(reference, key, review, previous_hash, edited=edited_value is not None)
        bundle: Resource = {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": [
                {"resource": updated, "request": {"method": "PUT", "url": reference, **_if_match(composition)}},
                {"resource": provenance, "request": {"method": "POST", "url": "Provenance"}},
            ],
        }
        await self._repo.transaction(bundle)
        return updated

    async def _context(self, case_id: str, device_display: str, recorded: datetime) -> FhirContext:
        task = await self._repo.find_by_identifier("Task", SID_CASE_TASK, case_id)
        if task is None:
            raise NotFoundError("case", case_id)
        patient = str(task.get("for", {}).get("reference", ""))
        episode = str(task.get("focus", {}).get("reference", ""))
        resources = await self._repo.search("DocumentReference", {"encounter": episode, "_count": "100"})
        documents = {
            str(i["value"]): f"DocumentReference/{r['id']}"
            for r in resources
            for i in r.get("identifier", [])
            if i.get("system") == SID_SOURCE_DOCUMENT
        }
        return FhirContext(patient, episode, documents, device_display, recorded)
