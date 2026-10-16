"""Against a live IRIS (local or the shared team ACI): `uv run --env-file ../.env pytest -m iris`.

Writes only resources tagged `stafeta-test` and deletes them again; never touches `stafeta-demo` data.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

from app.fhir.client import FhirClient
from app.fhir.repository import FhirRepository
from app.fhir.systems import CS_TAG, SID_ORGANIZATION, TEST_TAG_CODE
from app.iris.db import IrisPool
from app.security.actor import SYSTEM_ACTOR
from app.settings import Settings

pytestmark = pytest.mark.iris


@pytest.fixture
def live_settings() -> Settings:
    settings = Settings()
    if not settings.iris_password.get_secret_value():
        pytest.skip("IRIS_PASSWORD not set (run with --env-file ../.env)")
    return settings


@pytest.fixture
async def repo(live_settings: Settings) -> AsyncIterator[FhirRepository]:
    async with httpx.AsyncClient(timeout=60) as http:
        client = FhirClient(http, live_settings.fhir_base_url, live_settings.iris_user, live_settings.iris_password)
        repository = FhirRepository(client, SYSTEM_ACTOR, tag_code=TEST_TAG_CODE)
        try:
            yield repository
        finally:
            await repository.delete_by_tag(["AuditEvent", "Organization"], TEST_TAG_CODE)
            # The summary AuditEvent of the cleanup itself carries the test tag as well: remove it directly.
            for event in await client.search_all("AuditEvent", {"_tag": f"{CS_TAG}|{TEST_TAG_CODE}"}):
                await client.delete("AuditEvent", event["id"])


async def test_ensure_is_idempotent_and_audited(repo: FhirRepository) -> None:
    org = {
        "resourceType": "Organization",
        "identifier": [{"system": SID_ORGANIZATION, "value": f"it-{uuid.uuid4().hex[:8]}"}],
        "name": "Integration test organisation",
    }

    first = await repo.ensure(org)
    second = await repo.ensure(org)

    assert first.created
    assert not second.created
    assert first.reference == second.reference
    events = await repo.search("AuditEvent", {"entity": first.reference})
    assert len(events) == 1
    assert events[0]["action"] == "C"


async def test_metadata_and_sql_ping(live_settings: Settings, repo: FhirRepository) -> None:
    capability = await repo.client.capabilities()
    assert capability["resourceType"] == "CapabilityStatement"

    pool = IrisPool.from_settings(live_settings)
    try:
        pool.ping()
    finally:
        pool.close_all()
