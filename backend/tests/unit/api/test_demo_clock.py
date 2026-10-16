"""Demo clock API: served only in demo mode, audited, one clock for settings and domain."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.deps import get_directory_provider, get_fhir_client, get_iris_pool, get_repository
from app.domain import clock
from app.main import create_app
from app.settings import Settings
from tests.conftest import FHIR_BASE
from tests.directory_fixtures import demo_directory

COORDINATOR = {"X-Demo-Role": "coordinator"}
URL = "/api/demo/clock"


class FakeProvider:
    async def get(self) -> Any:
        return demo_directory()


class FakeRepository:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []

    async def create(self, resource: dict[str, Any]) -> None:
        self.created.append(resource)


def make_client(demo_mode: bool, repository: FakeRepository) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        fhir_base_url=FHIR_BASE,
        iris_password=SecretStr("test-password"),
        log_level="WARNING",
        stafeta_demo_mode=demo_mode,
        stafeta_demo_now="2026-10-02T09:00:00+02:00",
        stafeta_watchdog_enabled=False,
    )
    app = create_app(settings)
    app.dependency_overrides[get_directory_provider] = lambda: FakeProvider()
    app.dependency_overrides[get_fhir_client] = lambda: object()
    app.dependency_overrides[get_iris_pool] = lambda: object()
    app.dependency_overrides[get_repository] = lambda: repository
    with TestClient(app) as client:
        yield client
    clock.set_override(None)


@pytest.fixture
def repository() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def client(repository: FakeRepository) -> Iterator[TestClient]:
    yield from make_client(True, repository)


@pytest.fixture
def client_without_demo_mode(repository: FakeRepository) -> Iterator[TestClient]:
    yield from make_client(False, repository)


def test_get_returns_the_start_value(client: TestClient) -> None:
    response = client.get(URL, headers=COORDINATOR)

    assert response.status_code == 200
    assert response.json() == {"now": "2026-10-02T09:00:00+02:00", "overridden": False}


def test_put_moves_the_one_clock_and_null_resets_it(client: TestClient) -> None:
    moved = client.put(URL, json={"now": "2026-10-16T09:00:00+02:00"}, headers=COORDINATOR)

    assert moved.json() == {"now": "2026-10-16T09:00:00+02:00", "overridden": True}
    assert clock.now().isoformat() == "2026-10-16T09:00:00+02:00"  # the state machines read the same clock
    assert client.get(URL, headers=COORDINATOR).json()["now"] == "2026-10-16T09:00:00+02:00"

    reset = client.put(URL, json={"now": None}, headers=COORDINATOR)

    assert reset.json() == {"now": "2026-10-02T09:00:00+02:00", "overridden": False}


def test_naive_timestamp_is_prague(client: TestClient) -> None:
    response = client.put(URL, json={"now": "2026-10-16T09:00:00"}, headers=COORDINATOR)

    assert response.json()["now"] == "2026-10-16T09:00:00+02:00"


@pytest.mark.parametrize("value", ["9999-12-31T00:00:00+00:00", "0001-01-01T00:00:00+00:00", "2019-12-31T23:00:00"])
def test_implausible_dates_are_422_and_not_audited(client: TestClient, repository: FakeRepository, value: str) -> None:
    assert client.put(URL, json={"now": value}, headers=COORDINATOR).status_code == 422
    assert not clock.is_overridden()
    assert repository.created == []


def test_put_without_now_is_422(client: TestClient) -> None:
    assert client.put(URL, json={}, headers=COORDINATOR).status_code == 422
    assert not clock.is_overridden()


def test_requires_a_person_role(client: TestClient) -> None:
    system = {"X-Demo-Role": "system"}  # `current_actor` refuses roles that stand for no person
    assert client.get(URL, headers=system).status_code == 401
    assert client.put(URL, json={"now": None}, headers=system).status_code == 401


def test_put_writes_an_audit_event_without_patient(client: TestClient, repository: FakeRepository) -> None:
    client.put(URL, json={"now": "2026-10-16T09:00:00+02:00"}, headers=COORDINATOR)

    [audit] = repository.created
    assert audit["resourceType"] == "AuditEvent"
    assert audit["subtype"][0]["code"] == "demo-clock"
    assert audit["outcomeDesc"] == "demo clock set to 2026-10-16T09:00:00+02:00"
    assert "entity" not in audit  # no patient, no clinical content
    assert audit["agent"][0]["type"]["coding"][0]["code"] == "coordinator"


def test_audit_failure_leaves_the_clock_alone(client: TestClient, repository: FakeRepository) -> None:
    async def fail(resource: dict[str, Any]) -> None:
        raise RuntimeError("audit store down")

    repository.create = fail  # type: ignore[method-assign]

    response = client.put(URL, json={"now": "2026-10-16T09:00:00+02:00"}, headers=COORDINATOR)

    assert response.status_code == 500
    assert not clock.is_overridden()


@pytest.mark.parametrize("headers", [COORDINATOR, {}])
def test_404_outside_demo_mode_even_without_login(
    client_without_demo_mode: TestClient, repository: FakeRepository, headers: dict[str, str]
) -> None:
    for response in (
        client_without_demo_mode.get(URL, headers=headers),
        client_without_demo_mode.put(URL, json={"now": "2026-10-16T09:00:00+02:00"}, headers=headers),
    ):
        assert response.status_code == 404
        assert response.headers["content-type"] == "application/problem+json"
    assert not clock.is_overridden()
    assert repository.created == []
