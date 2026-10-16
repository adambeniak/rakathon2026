from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping
from urllib.parse import urlsplit

import httpx
import pytest
from pydantic import SecretStr

from app.fhir.client import FhirClient
from app.settings import Settings

FHIR_BASE = "http://fhir.test/fhir/r4"

# Tests marked `iris` create cases, tasks and care plans: they run against `make up-local` only. A shared (team ACI)
# server is refused unless someone sets STAFETA_ALLOW_SHARED_IRIS_TESTS=1 on purpose.
LOCAL_IRIS_HOSTS = frozenset({"localhost", "127.0.0.1", "iris"})
ALLOW_SHARED_IRIS_ENV = "STAFETA_ALLOW_SHARED_IRIS_TESTS"


def shared_iris_reason(iris_host: str, fhir_base_url: str, environ: Mapping[str, str]) -> str | None:
    """Why an `iris` test must not run against this server, or None when it may."""
    if environ.get(ALLOW_SHARED_IRIS_ENV) == "1":
        return None
    remote = sorted({h for h in (iris_host, urlsplit(fhir_base_url).hostname or "") if h not in LOCAL_IRIS_HOSTS})
    if not remote:
        return None
    return (
        f"refusing to run an `iris` test against a shared server ({', '.join(remote)}): these tests create cases, "
        "tasks and care plans. Run them against the local container (`make up-local`, IRIS_HOST=localhost), "
        f"or set {ALLOW_SHARED_IRIS_ENV}=1 if you really mean it."
    )


def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.get_closest_marker("iris") is None:
        return
    settings = Settings()  # same source the integration tests use
    reason = shared_iris_reason(settings.iris_host, settings.fhir_base_url, os.environ)
    if reason:
        pytest.skip(reason)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        fhir_base_url=FHIR_BASE,
        iris_password=SecretStr("test-password"),
        log_level="WARNING",
        stafeta_demo_mode=True,
        stafeta_demo_now="2026-10-21T08:00:00+02:00",
        stafeta_watchdog_enabled=False,
    )


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def fhir_client(http: httpx.AsyncClient) -> FhirClient:
    return FhirClient(http, FHIR_BASE, "_SYSTEM", SecretStr("test-password"), read_attempts=2)
