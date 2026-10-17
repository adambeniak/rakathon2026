from __future__ import annotations

import time

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.api.deps import get_case_reader, get_handover_store
from app.domain.errors import ForbiddenError
from app.fhir.errors import FhirConflictError
from app.main import create_app
from app.settings import Settings
from tests.conftest import FHIR_BASE
from tests.unit.api.fake_handover_store import FakeStore


class RaisingReader:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def list_cases(self) -> list[object]:
        raise self.error


def get_cases_with(settings: Settings, error: Exception) -> httpx.Response:
    app = create_app(settings)
    app.dependency_overrides[get_case_reader] = lambda: RaisingReader(error)
    app.dependency_overrides[get_handover_store] = FakeStore  # the summary also reads the handover store
    with TestClient(app) as client:
        return client.get("/api/cases")


def test_concurrent_change_is_a_409_problem(settings: Settings) -> None:
    response = get_cases_with(settings, FhirConflictError("x", status_code=412))
    assert response.status_code == 409
    assert response.json()["type"].endswith("/conflict")
    assert response.headers["content-type"].startswith("application/problem+json")


def test_forbidden_is_a_403_problem(settings: Settings) -> None:
    response = get_cases_with(settings, ForbiddenError("only the coordinator may launch a pathway"))
    assert response.status_code == 403
    assert response.json()["type"].endswith("/forbidden")


@pytest.mark.parametrize(
    ("enabled", "demo_mode", "expected"),
    [(None, True, True), (None, False, False), (False, True, False), (True, False, True)],
)
def test_watchdog_setting_follows_demo_mode_unless_set(enabled: bool | None, demo_mode: bool, expected: bool) -> None:
    settings = Settings(_env_file=None, stafeta_watchdog_enabled=enabled, stafeta_demo_mode=demo_mode)
    assert settings.watchdog_enabled is expected


def test_watchdog_loop_runs_with_the_app_survives_iris_errors_and_stops(settings: Settings) -> None:
    enabled = settings.model_copy(update={"stafeta_watchdog_enabled": True, "stafeta_watchdog_interval_s": 0.05})
    with respx.mock(assert_all_called=False) as router:
        search = router.get(f"{FHIR_BASE}/Task").mock(return_value=httpx.Response(503, json={}))
        with TestClient(create_app(enabled)):
            deadline = time.monotonic() + 5
            while search.call_count < 2 and time.monotonic() < deadline:
                time.sleep(0.05)
        assert search.call_count >= 2  # a failing round did not kill the loop
        calls_at_shutdown = search.call_count
        time.sleep(0.2)
        assert search.call_count == calls_at_shutdown  # cancelled with the app


def test_watchdog_is_off_in_the_test_settings(settings: Settings) -> None:
    assert settings.watchdog_enabled is False
