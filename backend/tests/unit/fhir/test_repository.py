from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from app.fhir.client import FhirClient
from app.fhir.errors import AuditWriteError
from app.fhir.repository import FhirRepository
from app.fhir.systems import CS_TAG, SID_ORGANIZATION, SID_USER
from app.security.actor import SYSTEM_ACTOR
from tests.conftest import FHIR_BASE

ORG = {
    "resourceType": "Organization",
    "identifier": [{"system": SID_ORGANIZATION, "value": "koc2-nemocnice-lipova"}],
    "name": "KOC 2",
}
NOW = datetime(2026, 10, 16, 16, 0, tzinfo=UTC)


def _bundle(*resources: dict[str, Any]) -> dict[str, Any]:
    return {"resourceType": "Bundle", "entry": [{"resource": r} for r in resources]}


def _body(call: respx.models.Call) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(call.request.content)
    return body


@pytest.fixture
def repo(fhir_client: FhirClient) -> FhirRepository:
    return FhirRepository(fhir_client, SYSTEM_ACTOR, clock=lambda: NOW)


@respx.mock
async def test_ensure_existing_writes_nothing(repo: FhirRepository) -> None:
    respx.get(f"{FHIR_BASE}/Organization").mock(return_value=httpx.Response(200, json=_bundle({**ORG, "id": "7"})))
    posts = respx.post(url__startswith=FHIR_BASE)

    result = await repo.ensure(ORG)

    assert (result.reference, result.created) == ("Organization/7", False)
    assert posts.call_count == 0


@respx.mock
async def test_ensure_new_creates_tagged_resource_and_audit_event(repo: FhirRepository) -> None:
    respx.get(f"{FHIR_BASE}/Organization").mock(return_value=httpx.Response(200, json=_bundle()))
    create = respx.post(f"{FHIR_BASE}/Organization").mock(
        return_value=httpx.Response(201, headers={"Location": f"{FHIR_BASE}/Organization/7/_history/1"})
    )
    audit = respx.post(f"{FHIR_BASE}/AuditEvent").mock(
        return_value=httpx.Response(201, headers={"Location": f"{FHIR_BASE}/AuditEvent/8/_history/1"})
    )

    result = await repo.ensure(ORG)

    assert (result.reference, result.created) == ("Organization/7", True)
    written = _body(create.calls[0])
    assert {"system": CS_TAG, "code": "stafeta-demo"} in written["meta"]["tag"]
    assert create.calls[0].request.headers["If-None-Exist"] == f"identifier={SID_ORGANIZATION}|koc2-nemocnice-lipova"
    assert "meta" not in ORG  # the caller's dict is not mutated
    event = _body(audit.calls[0])
    assert event["action"] == "C"
    assert event["subtype"][0]["code"] == "create"
    assert event["entity"] == [{"what": {"reference": "Organization/7"}}]
    assert event["agent"][0]["who"]["identifier"] == {"system": SID_USER, "value": "system"}
    assert event["recorded"].startswith("2026-10-16T16:00:00")


@respx.mock
async def test_conditional_create_race_does_not_audit(repo: FhirRepository) -> None:
    respx.get(f"{FHIR_BASE}/Organization").mock(return_value=httpx.Response(200, json=_bundle()))
    respx.post(f"{FHIR_BASE}/Organization").mock(
        return_value=httpx.Response(200, headers={"Location": f"{FHIR_BASE}/Organization/7/_history/1"})
    )
    audit = respx.post(f"{FHIR_BASE}/AuditEvent")

    result = await repo.ensure(ORG)

    assert result.created is False
    assert audit.call_count == 0


@respx.mock
async def test_audit_failure_raises_audit_write_error(repo: FhirRepository) -> None:
    respx.post(f"{FHIR_BASE}/Organization").mock(
        return_value=httpx.Response(201, headers={"Location": f"{FHIR_BASE}/Organization/7/_history/1"})
    )
    respx.post(f"{FHIR_BASE}/AuditEvent").mock(return_value=httpx.Response(500))

    with pytest.raises(AuditWriteError):
        await repo.create(ORG)


@respx.mock
async def test_untagged_repository_does_not_stamp_meta(fhir_client: FhirClient) -> None:
    repo = FhirRepository(fhir_client, SYSTEM_ACTOR, tag_code=None, clock=lambda: NOW)
    create = respx.post(f"{FHIR_BASE}/Organization").mock(
        return_value=httpx.Response(201, headers={"Location": f"{FHIR_BASE}/Organization/7"})
    )
    respx.post(f"{FHIR_BASE}/AuditEvent").mock(
        return_value=httpx.Response(201, headers={"Location": f"{FHIR_BASE}/AuditEvent/8"})
    )

    await repo.create(ORG)

    assert "meta" not in _body(create.calls[0])


@respx.mock
async def test_transaction_audits_only_real_writes(repo: FhirRepository) -> None:
    bundle = {
        "resourceType": "Bundle",
        "type": "transaction",
        "entry": [
            {"resource": {"resourceType": "Patient"}, "request": {"method": "POST", "url": "Patient"}},
            {"resource": {"resourceType": "Task"}, "request": {"method": "POST", "url": "Task"}},
            {"resource": {"resourceType": "Task", "id": "3"}, "request": {"method": "PUT", "url": "Task/3"}},
        ],
    }
    respx.post(FHIR_BASE).mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "Bundle",
                "type": "transaction-response",
                "entry": [
                    {"response": {"status": "200", "location": f"{FHIR_BASE}/Patient/1"}},  # matched ifNoneExist
                    {"response": {"status": "201 Created", "location": f"{FHIR_BASE}/Task/2/_history/1"}},
                    {"response": {"status": "200", "location": f"{FHIR_BASE}/Task/3/_history/2"}},
                ],
            },
        )
    )
    audit = respx.post(f"{FHIR_BASE}/AuditEvent").mock(
        return_value=httpx.Response(201, headers={"Location": f"{FHIR_BASE}/AuditEvent/9"})
    )

    await repo.transaction(bundle)

    event = _body(audit.calls[0])
    assert event["action"] == "E"
    assert [e["what"]["reference"] for e in event["entity"]] == ["Task/2", "Task/3"]


@respx.mock
async def test_delete_by_tag_deletes_in_order_with_one_summary_audit(repo: FhirRepository) -> None:
    respx.get(f"{FHIR_BASE}/DocumentReference").mock(
        return_value=httpx.Response(200, json=_bundle({"resourceType": "DocumentReference", "id": "5"}))
    )
    respx.get(f"{FHIR_BASE}/Patient").mock(
        return_value=httpx.Response(200, json=_bundle({"resourceType": "Patient", "id": "3"}))
    )
    deletes = respx.delete(url__startswith=FHIR_BASE).mock(return_value=httpx.Response(204))
    audit = respx.post(f"{FHIR_BASE}/AuditEvent").mock(
        return_value=httpx.Response(201, headers={"Location": f"{FHIR_BASE}/AuditEvent/9"})
    )

    deleted = await repo.delete_by_tag(["DocumentReference", "Patient"], "stafeta-test")

    assert deleted == {"DocumentReference": 1, "Patient": 1}
    assert [str(c.request.url) for c in deletes.calls] == [
        f"{FHIR_BASE}/DocumentReference/5",
        f"{FHIR_BASE}/Patient/3",
    ]
    assert audit.call_count == 1
    assert _body(audit.calls[0])["action"] == "D"


@respx.mock
async def test_audit_read_records_entities(repo: FhirRepository) -> None:
    audit = respx.post(f"{FHIR_BASE}/AuditEvent").mock(
        return_value=httpx.Response(201, headers={"Location": f"{FHIR_BASE}/AuditEvent/9"})
    )

    await repo.audit_read(["Task/1", "Patient/2"], subtype="search-type")

    event = _body(audit.calls[0])
    assert (event["action"], event["subtype"][0]["code"]) == ("R", "search-type")
    assert len(event["entity"]) == 2


async def test_delete_by_tag_never_deletes_the_demo_audit_trail(repo: FhirRepository) -> None:
    with pytest.raises(ValueError, match="never deleted"):
        await repo.delete_by_tag(["AuditEvent", "Patient"], "stafeta-demo")


@respx.mock
async def test_delete_by_tag_audits_every_deleted_resource_in_chunks(repo: FhirRepository) -> None:
    patients = [{"resourceType": "Patient", "id": str(i)} for i in range(150)]
    respx.get(f"{FHIR_BASE}/Patient").mock(return_value=httpx.Response(200, json=_bundle(*patients)))
    respx.delete(url__startswith=FHIR_BASE).mock(return_value=httpx.Response(204))
    audit = respx.post(f"{FHIR_BASE}/AuditEvent").mock(
        return_value=httpx.Response(201, headers={"Location": f"{FHIR_BASE}/AuditEvent/9"})
    )

    await repo.delete_by_tag(["Patient"], "stafeta-demo")

    assert [len(_body(call)["entity"]) for call in audit.calls] == [100, 50]
