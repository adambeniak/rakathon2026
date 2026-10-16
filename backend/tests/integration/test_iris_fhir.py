"""Against a live IRIS (local or the shared team ACI): `uv run --env-file ../.env pytest -m iris`.

Each test run uses its own tag (`stafeta-test-<run>`) and cleans up only the resources it created plus the
AuditEvents that reference them, so parallel runs on the shared server never delete each other's data.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
import pytest

from app.fhir.client import FhirClient, Resource
from app.fhir.errors import FhirNotFoundError
from app.fhir.repository import FhirRepository
from app.fhir.systems import SID_ORGANIZATION, TEST_TAG_CODE
from app.iris.db import IrisPool
from app.security.actor import SYSTEM_ACTOR
from app.settings import Settings

pytestmark = pytest.mark.iris


@dataclass
class LiveFhir:
    repo: FhirRepository
    tag_code: str
    created: list[str] = field(default_factory=list)

    def organization(self) -> Resource:
        return {
            "resourceType": "Organization",
            "identifier": [{"system": SID_ORGANIZATION, "value": f"it-{uuid.uuid4().hex[:8]}"}],
            "name": "Integration test organisation",
        }


@pytest.fixture
def live_settings() -> Settings:
    settings = Settings()
    if not settings.iris_password.get_secret_value():
        pytest.skip("IRIS_PASSWORD not set (run with --env-file ../.env)")
    return settings


@pytest.fixture
async def live(live_settings: Settings) -> AsyncIterator[LiveFhir]:
    tag_code = f"{TEST_TAG_CODE}-{uuid.uuid4().hex[:8]}"
    async with httpx.AsyncClient(timeout=60) as http:
        client = FhirClient(http, live_settings.fhir_base_url, live_settings.iris_user, live_settings.iris_password)
        fixture = LiveFhir(FhirRepository(client, SYSTEM_ACTOR, tag_code=tag_code), tag_code)
        try:
            yield fixture
        finally:
            # Test data only: remove this run's resources and every AuditEvent that references them.
            for reference in fixture.created:
                for event in await client.search_all("AuditEvent", {"entity": reference}):
                    await client.delete("AuditEvent", str(event["id"]))
                with contextlib.suppress(FhirNotFoundError):  # already deleted by the test itself
                    await client.delete(*reference.split("/", 1))


async def test_ensure_is_idempotent_and_audited(live: LiveFhir) -> None:
    org = live.organization()

    first = await live.repo.ensure(org)
    live.created.append(first.reference)
    second = await live.repo.ensure(org)

    assert first.created
    assert not second.created
    assert first.reference == second.reference
    events = await live.repo.search("AuditEvent", {"entity": first.reference})
    assert [e["action"] for e in events] == ["C"]


async def test_delete_by_tag_removes_only_this_runs_resources_and_audits_it(live: LiveFhir) -> None:
    created = await live.repo.ensure(live.organization())
    live.created.append(created.reference)

    deleted = await live.repo.delete_by_tag(["Organization"], live.tag_code)

    assert deleted == {"Organization": 1}
    events = await live.repo.search("AuditEvent", {"entity": created.reference})
    assert sorted(e["action"] for e in events) == ["C", "D"]


async def test_metadata_and_sql_ping(live_settings: Settings, live: LiveFhir) -> None:
    capability = await live.repo.client.capabilities()
    assert capability["resourceType"] == "CapabilityStatement"

    pool = IrisPool.from_settings(live_settings)
    try:
        pool.ping()
    finally:
        pool.close_all()
