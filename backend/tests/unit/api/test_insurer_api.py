"""GET /api/insurer/analytics: reviewer only, simulated cohort, no patient identifiers in the payload."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_directory_provider, get_fhir_client, get_iris_pool
from app.fhir.directory import Directory
from app.main import create_app
from app.settings import Settings
from tests.directory_fixtures import demo_directory

URL = "/api/insurer/analytics"


class FakeProvider:
    async def get(self) -> Directory:
        return demo_directory()


def _client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_directory_provider] = lambda: FakeProvider()
    app.dependency_overrides[get_fhir_client] = lambda: object()
    app.dependency_overrides[get_iris_pool] = lambda: object()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    yield from _client(settings)


def test_reviewer_gets_the_simulated_analytics(client: TestClient) -> None:
    response = client.get(URL, headers={"X-Demo-Role": "reviewer"})

    assert response.status_code == 200
    body = response.json()
    assert body["simulated"] is True
    assert body["disclaimer"].startswith("Simulovaná data")
    assert body["assumptions"]["weights"] == {"speed": 0.5, "cost": 0.3, "target_share": 0.2}
    assert body["assumptions"]["targets"]["ct_order_to_ct_max_days"] == 7
    assert body["assumptions"]["capacity"]["minutes_per_week"] > 0
    assert len(body["hospitals"]) == 4
    assert [h["id"] for h in body["hospitals"]] == body["rankings"]["by_indicator"]
    assert body["hospitals"][0]["badges"] == ["fastest", "lowest_cost"]
    assert body["summary"]["cases"] == len(body["journeys"])
    assert body["summary"]["median_days"]["contact_to_mdt"] == 18.0
    demo = body["journeys"][0]
    assert demo["code"] == "rakathon-2026-prochazkova"
    assert demo["simulated"] is False
    assert [m["key"] for m in demo["milestones"]] == [
        "gp_contacted_coordinator",
        "accepted",
        "ct_done",
        "biopsy_done",
        "mdt",
        "treatment_start",
    ]
    treatment = next(i for i in demo["intervals"] if i["key"] == "mdt_to_treatment")
    assert treatment == {
        "key": "mdt_to_treatment",
        "start": "2026-10-21",
        "end": None,
        "days": None,
        "status": "running",
    }


@pytest.mark.parametrize("role", ["coordinator", "gp", "koc_physician", "koc_staff"])
def test_other_roles_get_403_problem_json(client: TestClient, role: str) -> None:
    response = client.get(URL, headers={"X-Demo-Role": role})

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "revizní" in response.json()["detail"]


def test_without_demo_mode_the_request_is_401(settings: Settings) -> None:
    client = next(_client(settings.model_copy(update={"stafeta_demo_mode": False})))
    response = client.get(URL, headers={"X-Demo-Role": "reviewer"})
    assert response.status_code == 401


def test_payload_carries_no_patient_identifiers(client: TestClient) -> None:
    text = client.get(URL, headers={"X-Demo-Role": "reviewer"}).text

    assert "Procházková" not in text
    assert "Alena" not in text
    assert not re.search(r"\b\d{6}/?\d{3,4}\b", text)  # no rodné číslo
    for forbidden in ("birth", "narozen", "rodne_cislo", "rodné", '"patient', "pacient"):
        assert forbidden not in text.lower()


def test_frontend_mock_fixture_matches_the_backend(client: TestClient) -> None:
    """The MSW fixture is an export of this endpoint: regenerate it when the cohort or the computation changes."""
    fixture = Path(__file__).resolve().parents[4] / "frontend" / "src" / "mocks" / "fixtures" / "insurer.json"
    body = client.get(URL, headers={"X-Demo-Role": "reviewer"}).json()
    assert json.loads(fixture.read_text(encoding="utf-8")) == body
