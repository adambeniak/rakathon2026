from __future__ import annotations

import httpx
import pytest
import respx

from app.fhir.client import FhirClient, reference_from_location
from app.fhir.errors import FhirAuthError, FhirError, FhirUnavailableError, FhirValidationError
from tests.conftest import FHIR_BASE

OUTCOME = {
    "resourceType": "OperationOutcome",
    "issue": [
        {
            "severity": "error",
            "code": "invalid",
            "diagnostics": "<HSFHIRErr>WrongJsonType",
            "expression": ["Organization.name"],
        }
    ],
}


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        (f"{FHIR_BASE}/Patient/12/_history/1", ("Patient", "12")),
        (f"{FHIR_BASE}/DocumentReference/5", ("DocumentReference", "5")),
        ("Organization/7", ("Organization", "7")),
    ],
)
def test_reference_from_location(location: str, expected: tuple[str, str]) -> None:
    assert reference_from_location(location) == expected


@respx.mock
async def test_conditional_create_reports_created_and_existing(fhir_client: FhirClient) -> None:
    route = respx.post(f"{FHIR_BASE}/Organization").mock(
        side_effect=[
            httpx.Response(201, headers={"Location": f"{FHIR_BASE}/Organization/1/_history/1"}),
            httpx.Response(200, headers={"Location": f"{FHIR_BASE}/Organization/1/_history/1"}),
        ]
    )
    resource = {"resourceType": "Organization", "name": "X"}

    first = await fhir_client.create(resource, if_none_exist="identifier=s|v")
    second = await fhir_client.create(resource, if_none_exist="identifier=s|v")

    assert (first.reference, first.created) == ("Organization/1", True)
    assert (second.reference, second.created) == ("Organization/1", False)
    request = route.calls[0].request
    assert request.headers["If-None-Exist"] == "identifier=s|v"
    assert request.headers["Content-Type"] == "application/fhir+json"
    assert request.headers["Authorization"].startswith("Basic ")


@respx.mock
async def test_operation_outcome_becomes_typed_error_without_query_string(fhir_client: FhirClient) -> None:
    respx.get(f"{FHIR_BASE}/Patient").mock(return_value=httpx.Response(400, json=OUTCOME))

    with pytest.raises(FhirValidationError) as caught:
        await fhir_client.search("Patient", {"identifier": "https://stafeta.example/fhir/sid/rc|6357221013"})

    assert caught.value.status_code == 400
    assert caught.value.issues[0].code == "invalid"
    assert caught.value.issues[0].expression == ("Organization.name",)
    assert "6357221013" not in str(caught.value)


@respx.mock
async def test_reads_retry_on_unavailable_then_raise(fhir_client: FhirClient) -> None:
    route = respx.get(f"{FHIR_BASE}/metadata").mock(return_value=httpx.Response(503))

    with pytest.raises(FhirUnavailableError):
        await fhir_client.capabilities()

    assert route.call_count == 2  # read_attempts=2 in the fixture


@respx.mock
async def test_transport_error_is_unavailable(fhir_client: FhirClient) -> None:
    respx.get(f"{FHIR_BASE}/Patient/1").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(FhirUnavailableError):
        await fhir_client.read("Patient", "1")


@respx.mock
async def test_writes_are_not_retried(fhir_client: FhirClient) -> None:
    route = respx.post(f"{FHIR_BASE}/Patient").mock(return_value=httpx.Response(503))

    with pytest.raises(FhirUnavailableError):
        await fhir_client.create({"resourceType": "Patient"})

    assert route.call_count == 1


@respx.mock
async def test_auth_error(fhir_client: FhirClient) -> None:
    respx.get(f"{FHIR_BASE}/Patient/1").mock(return_value=httpx.Response(401))

    with pytest.raises(FhirAuthError):
        await fhir_client.read("Patient", "1")


@respx.mock
async def test_search_all_follows_next_links_and_skips_includes(fhir_client: FhirClient) -> None:
    next_url = f"{FHIR_BASE}/Task?page=2"
    respx.get(f"{FHIR_BASE}/Task", params={"code": "x"}).mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "Bundle",
                "link": [{"relation": "next", "url": next_url}],
                "entry": [
                    {"resource": {"resourceType": "Task", "id": "1"}, "search": {"mode": "match"}},
                    {"resource": {"resourceType": "Patient", "id": "9"}, "search": {"mode": "include"}},
                ],
            },
        )
    )
    respx.get(next_url).mock(
        return_value=httpx.Response(
            200, json={"resourceType": "Bundle", "entry": [{"resource": {"resourceType": "Task", "id": "2"}}]}
        )
    )

    tasks = await fhir_client.search_all("Task", {"code": "x"})

    assert [t["id"] for t in tasks] == ["1", "2"]


@respx.mock
async def test_count_uses_summary_count(fhir_client: FhirClient) -> None:
    route = respx.get(f"{FHIR_BASE}/DocumentReference").mock(
        return_value=httpx.Response(200, json={"resourceType": "Bundle", "total": 13})
    )

    assert await fhir_client.count("DocumentReference", {"encounter": "EpisodeOfCare/4"}) == 13
    assert route.calls[0].request.url.params["_summary"] == "count"


@respx.mock
async def test_paging_link_to_another_origin_is_refused(fhir_client: FhirClient) -> None:
    respx.get(f"{FHIR_BASE}/Task").mock(
        return_value=httpx.Response(
            200,
            json={"resourceType": "Bundle", "link": [{"relation": "next", "url": "http://evil.test/fhir/r4/Task?p=2"}]},
        )
    )
    evil = respx.get(url__startswith="http://evil.test")

    with pytest.raises(FhirError, match="different origin"):
        await fhir_client.search_all("Task", {})

    assert evil.call_count == 0
