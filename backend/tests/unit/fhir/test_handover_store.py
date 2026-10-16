"""HandoverStore against a mocked FHIR server: idempotent persist, audited transaction, confirmation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from app.domain.errors import ConflictError
from app.domain.handover import ReviewState, SectionReview
from app.fhir.client import FhirClient
from app.fhir.handover_store import HandoverStore
from app.fhir.repository import FhirRepository
from app.fhir.systems import SID_CASE_TASK, SID_SOURCE_DOCUMENT
from app.security.actor import SYSTEM_ACTOR
from tests.conftest import FHIR_BASE
from tests.unit.fhir.test_handover_mapper import PHYSICIAN, handover

NOW = datetime(2026, 10, 21, 6, 5, tzinfo=UTC)
TASK = {
    "resourceType": "Task",
    "id": "5",
    "identifier": [{"system": SID_CASE_TASK, "value": "case-1"}],
    "for": {"reference": "Patient/1"},
    "focus": {"reference": "EpisodeOfCare/2"},
}
DOC = {
    "resourceType": "DocumentReference",
    "id": "10",
    "identifier": [{"system": SID_SOURCE_DOCUMENT, "value": "07_PL_2026-10-02"}],
}


def _bundle(*resources: dict[str, Any]) -> dict[str, Any]:
    return {"resourceType": "Bundle", "entry": [{"resource": r} for r in resources]}


@pytest.fixture
def store(fhir_client: FhirClient) -> HandoverStore:
    return HandoverStore(FhirRepository(fhir_client, SYSTEM_ACTOR, clock=lambda: NOW))


def _audit_mock() -> respx.Route:
    return respx.post(f"{FHIR_BASE}/AuditEvent").mock(
        return_value=httpx.Response(201, headers={"Location": f"{FHIR_BASE}/AuditEvent/99/_history/1"})
    )


@respx.mock
async def test_persist_existing_composition_writes_nothing(store: HandoverStore) -> None:
    existing = {"resourceType": "Composition", "id": "77", "identifier": {"value": "x"}}
    respx.get(f"{FHIR_BASE}/Composition").mock(return_value=httpx.Response(200, json=_bundle(existing)))
    audit = _audit_mock()
    transaction = respx.post(FHIR_BASE)

    result = await store.persist(handover(), device_display="AI", recorded=NOW)

    assert result["id"] == "77"
    assert transaction.call_count == 0
    assert json.loads(audit.calls[0].request.content)["action"] == "R"  # the read of the Composition is audited


@respx.mock
async def test_persist_new_writes_one_audited_transaction(store: HandoverStore) -> None:
    respx.get(f"{FHIR_BASE}/Composition").mock(return_value=httpx.Response(200, json=_bundle()))
    respx.get(f"{FHIR_BASE}/Task").mock(return_value=httpx.Response(200, json=_bundle(TASK)))
    respx.get(f"{FHIR_BASE}/DocumentReference").mock(return_value=httpx.Response(200, json=_bundle(DOC)))
    transaction = respx.post(FHIR_BASE).mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "Bundle",
                "type": "transaction-response",
                "entry": [{"response": {"status": "201 Created", "location": "Composition/77/_history/1"}}],
            },
        )
    )
    stored = {"resourceType": "Composition", "id": "77", "meta": {"versionId": "1"}, "identifier": {"value": "x"}}
    reread = respx.get(f"{FHIR_BASE}/Composition/77").mock(return_value=httpx.Response(200, json=stored))
    audit = _audit_mock()

    result = await store.persist(handover(), device_display="AI", recorded=NOW)

    # the stored copy is returned (resolved references, versionId for If-Match), not the bundle as sent
    assert reread.called
    assert result["meta"]["versionId"] == "1"
    sent = json.loads(transaction.calls[0].request.content)
    assert sent["entry"][0]["resource"]["resourceType"] == "Composition"
    assert all(
        {"system": "https://stafeta.example/fhir/CodeSystem/tag", "code": "stafeta-demo"}
        in e["resource"]["meta"]["tag"]
        for e in sent["entry"]
    )
    # the AuditEvent is part of the same transaction: data and audit commit or fail together
    event = sent["entry"][-1]["resource"]
    assert event["resourceType"] == "AuditEvent"
    assert event["subtype"][0]["code"] == "transaction"
    assert {"what": {"reference": sent["entry"][0]["fullUrl"]}} in event["entity"]
    # the reads of the case context and of the stored Composition are audited separately
    actions = [json.loads(c.request.content)["action"] for c in audit.calls]
    assert actions.count("E") == 1  # Task + DocumentReference search
    assert actions.count("R") == 1  # re-read of the Composition
    # the source document reference was resolved for the Provenance
    assert "DocumentReference/10" in json.dumps(sent)


@respx.mock
async def test_confirm_section_puts_composition_and_posts_provenance(store: HandoverStore) -> None:
    from tests.unit.fhir.test_handover_mapper import CTX, handover_bundle

    composition = {**handover_bundle(handover(), CTX)["entry"][0]["resource"], "id": "77", "meta": {"versionId": "3"}}
    transaction = respx.post(FHIR_BASE).mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "Bundle",
                "type": "transaction-response",
                "entry": [
                    {"response": {"status": "200 OK", "location": "Composition/77/_history/2"}},
                    {"response": {"status": "201 Created", "location": "Provenance/88/_history/1"}},
                ],
            },
        )
    )
    _audit_mock()
    review = SectionReview(state=ReviewState.CONFIRMED, by=PHYSICIAN, at=NOW)

    updated = await store.confirm_section(composition, "8_allergies", review, edited_value=None, previous_hash="h")

    sent = json.loads(transaction.calls[0].request.content)
    assert [e["request"]["method"] for e in sent["entry"]] == ["PUT", "POST", "POST"]
    assert sent["entry"][0]["request"]["url"] == "Composition/77"
    assert sent["entry"][0]["request"]["ifMatch"] == 'W/"3"'
    assert sent["entry"][2]["resource"]["resourceType"] == "AuditEvent"
    assert sent["entry"][1]["resource"]["agent"][0]["who"]["identifier"]["value"] == PHYSICIAN.id
    assert updated["status"] == "preliminary"


async def test_confirm_without_stored_version_is_refused(store: HandoverStore) -> None:
    from tests.unit.fhir.test_handover_mapper import CTX, handover_bundle

    unsaved = {**handover_bundle(handover(), CTX)["entry"][0]["resource"], "id": "77"}  # no meta.versionId
    review = SectionReview(state=ReviewState.CONFIRMED, by=PHYSICIAN, at=NOW)
    with pytest.raises(ConflictError):
        await store.confirm_section(unsaved, "8_allergies", review, edited_value=None, previous_hash="h")
