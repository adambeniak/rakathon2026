from __future__ import annotations

import pytest

from tests.conftest import ALLOW_SHARED_IRIS_ENV, shared_iris_reason

TEAM_HOST = "stafeta-team73.swedencentral.azurecontainer.io"


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "iris"])
def test_local_servers_are_allowed(host: str) -> None:
    assert shared_iris_reason(host, f"http://{host}:52773/fhir/r4", {}) is None


@pytest.mark.parametrize(
    ("iris_host", "fhir_url"),
    [
        (TEAM_HOST, f"http://{TEAM_HOST}:52773/fhir/r4"),
        ("localhost", f"http://{TEAM_HOST}:52773/fhir/r4"),  # either half pointing away from local is enough
        (TEAM_HOST, "http://localhost:52773/fhir/r4"),
    ],
)
def test_shared_servers_are_refused_with_a_clear_message(iris_host: str, fhir_url: str) -> None:
    reason = shared_iris_reason(iris_host, fhir_url, {})
    assert reason is not None
    assert "make up-local" in reason
    assert ALLOW_SHARED_IRIS_ENV in reason


def test_explicit_opt_in_allows_a_shared_server() -> None:
    assert shared_iris_reason(TEAM_HOST, f"http://{TEAM_HOST}:52773/fhir/r4", {ALLOW_SHARED_IRIS_ENV: "1"}) is None
    assert (
        shared_iris_reason(TEAM_HOST, f"http://{TEAM_HOST}:52773/fhir/r4", {ALLOW_SHARED_IRIS_ENV: "yes"}) is not None
    )
