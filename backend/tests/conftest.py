from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import SecretStr

from app.fhir.client import FhirClient
from app.settings import Settings

FHIR_BASE = "http://fhir.test/fhir/r4"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        fhir_base_url=FHIR_BASE,
        iris_password=SecretStr("test-password"),
        log_level="WARNING",
        stafeta_demo_now="2026-10-21T08:00:00+02:00",
    )


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def fhir_client(http: httpx.AsyncClient) -> FhirClient:
    return FhirClient(http, FHIR_BASE, "_SYSTEM", SecretStr("test-password"), read_attempts=2)
