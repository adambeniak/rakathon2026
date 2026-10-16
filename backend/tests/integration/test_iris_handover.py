"""Handover persistence against a live IRIS: `uv run --env-file ../.env pytest -m iris` (a human runs it).

Creates a throwaway Patient/EpisodeOfCare/Task with this run's tag, persists a small handover, confirms one
section and checks the Composition, the derived resources, the Provenance and the AuditEvents; everything this run
created is deleted afterwards (AuditEvents referencing it included, as in test_iris_fhir.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.domain.handover import ReviewState, SectionReview
from app.fhir.handover_store import HandoverStore
from app.fhir.mappers.handover import stored_review
from app.fhir.systems import SID_CASE_TASK
from tests.integration.test_iris_fhir import LiveFhir, live, live_settings  # noqa: F401 - shared fixtures
from tests.unit.fhir.test_handover_mapper import PHYSICIAN, handover

pytestmark = pytest.mark.iris

# Resources this test may create, dependents first (cleanup order).
CLEANUP = [
    "Provenance",
    "Composition",
    "Observation",
    "MedicationStatement",
    "Condition",
    "Task",
    "EpisodeOfCare",
    "Patient",
]


async def test_persist_is_idempotent_and_confirm_records_provenance(live: LiveFhir) -> None:  # noqa: F811
    case_id = f"case-it-{uuid.uuid4().hex[:8]}"
    patient = await live.repo.create({"resourceType": "Patient", "name": [{"family": "Testová"}]})
    episode = await live.repo.create(
        {"resourceType": "EpisodeOfCare", "status": "active", "patient": {"reference": patient.reference}}
    )
    task = await live.repo.create(
        {
            "resourceType": "Task",
            "identifier": [{"system": SID_CASE_TASK, "value": case_id}],
            "status": "in-progress",
            "intent": "order",
            "for": {"reference": patient.reference},
            "focus": {"reference": episode.reference},
        }
    )
    live.created += [task.reference, episode.reference, patient.reference]
    store = HandoverStore(live.repo)
    now = datetime.now(UTC)
    try:
        h = handover().model_copy(update={"case_id": case_id})
        first = await store.persist(h, device_display="Štafeta AI · it", recorded=now)
        second = await store.persist(h, device_display="Štafeta AI · it", recorded=now)
        assert first["id"] == second["id"]  # idempotent per (case, as_of)

        review = SectionReview(state=ReviewState.ACCEPTED_MISSING, by=PHYSICIAN, at=now)
        await store.confirm_section(first, "9_performance_status", review, edited_value=None, previous_hash="x")
        stored = await store.find(case_id, h.as_of)
        assert stored is not None
        assert stored_review(stored).sections["9_performance_status"].state == ReviewState.ACCEPTED_MISSING
        provenance = await live.repo.search("Provenance", {"target": f"Composition/{first['id']}"})
        assert {p["activity"]["coding"][0]["code"] for p in provenance} >= {"assemble", "accept-missing"}
        events = await live.repo.search("AuditEvent", {"entity": f"Composition/{first['id']}"})
        assert {e["action"] for e in events} >= {"E", "R"}
    finally:
        deleted = await live.repo.delete_by_tag(CLEANUP, live.tag_code)
        assert deleted.get("Composition", 0) <= 1
