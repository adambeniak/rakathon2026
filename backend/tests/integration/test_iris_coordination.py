"""Pathway launch and task updates against the local IRIS container (`make up-local`; shared servers are skipped).

Not run by `make check`. Confirms what mocks cannot: that IRIS accepts the CarePlan + Task transaction (urn:uuid
references, `If-None-Exist`), the `part-of` search, `If-Match` on PUT and a lost-race conditional create.
Cleans up only its own tagged resources and the AuditEvents that reference them.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime

import httpx
import pytest

from app.domain.case import Case
from app.domain.common import PartyRef, Role
from app.domain.errors import ConflictError
from app.domain.pathway import instantiate
from app.domain.task import TaskStatus
from app.fhir.cases import CaseHeader
from app.fhir.client import FhirClient
from app.fhir.errors import FhirConflictError, FhirNotFoundError
from app.fhir.repository import FhirRepository
from app.fhir.systems import CS_WORKFLOW_ROLE, SID_PRACTITIONER_ROLE, TEST_TAG_CODE
from app.fhir.tasks import PractitionerRoleRef, TaskStore
from app.security.actor import SYSTEM_ACTOR
from app.settings import PRAGUE, Settings
from tests.unit.domain.conftest import PATIENT, load_plan, load_template

pytestmark = pytest.mark.iris


@pytest.fixture
async def live() -> AsyncIterator[tuple[FhirClient, TaskStore, str]]:
    settings = Settings()
    if not settings.iris_password.get_secret_value():
        pytest.skip("IRIS_PASSWORD not set (run with --env-file ../.env)")
    tag_code = f"{TEST_TAG_CODE}-{uuid.uuid4().hex[:8]}"
    async with httpx.AsyncClient(timeout=60) as http:
        client = FhirClient(http, settings.fhir_base_url, settings.iris_user, settings.iris_password)
        yield client, TaskStore(FhirRepository(client, SYSTEM_ACTOR, tag_code=tag_code)), tag_code
        for resource_type in (
            "Provenance",
            "Task",
            "ServiceRequest",
            "CarePlan",
            "PlanDefinition",
            "PractitionerRole",
            "Patient",
        ):
            for resource in await client.search_all(
                resource_type, {"_tag": f"https://stafeta.example/fhir/CodeSystem/tag|{tag_code}"}
            ):
                reference = f"{resource_type}/{resource['id']}"
                for event in await client.search_all("AuditEvent", {"entity": reference}):
                    await client.delete("AuditEvent", str(event["id"]))
                with contextlib.suppress(FhirNotFoundError):
                    await client.delete(resource_type, str(resource["id"]))


async def test_launch_search_update_and_conflict(live: tuple[FhirClient, TaskStore, str]) -> None:
    client, store, tag_code = live
    run = uuid.uuid4().hex[:8]
    repo = FhirRepository(client, SYSTEM_ACTOR, tag_code=tag_code)

    plan = {**load_plan(), "url": f"https://stafeta.example/fhir/PlanDefinition/it-{run}"}
    assert (await repo.ensure_by_url(plan)).created
    assert not (await repo.ensure_by_url(plan)).created
    assert (await store.get_plan_definition(plan["url"]))["url"] == plan["url"]

    patient = await repo.create(
        {"resourceType": "Patient", "identifier": [{"system": "https://stafeta.example/fhir/sid/it", "value": run}]}
    )
    case_task = await repo.create(
        {
            "resourceType": "Task",
            "status": "in-progress",
            "intent": "order",
            "identifier": [{"system": "https://stafeta.example/fhir/sid/case-task", "value": f"it-{run}"}],
            "for": {"reference": patient.reference},
        }
    )
    case = Case.model_validate(
        {
            "id": f"it-{run}",
            "patient": PATIENT,
            "state": "triage",
            "mdt_start": datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE),
        }
    )
    header = CaseHeader(case=case, task_reference=case_task.reference, patient_reference=patient.reference)
    tasks = instantiate(load_template(), case, date(2026, 10, 2))

    physician_role = f"it-{run}@koc2-nemocnice-lipova"
    await repo.create(
        {
            "resourceType": "PractitionerRole",
            "identifier": [{"system": SID_PRACTITIONER_ROLE, "value": physician_role}],
            "code": [{"coding": [{"system": CS_WORKFLOW_ROLE, "code": "koc_physician"}]}],
        }
    )
    created = await repo.create(
        {
            "resourceType": "PractitionerRole",
            "identifier": [{"system": SID_PRACTITIONER_ROLE, "value": physician_role}],
            "code": [{"coding": [{"system": CS_WORKFLOW_ROLE, "code": "koc_physician"}]}],
        }
    )
    indication = PractitionerRoleRef(created.reference, physician_role, "Integration test", Role.KOC_PHYSICIAN)
    coordinator = PartyRef(id="it-coordinator", display="Integration test", role=Role.COORDINATOR)
    recorded = datetime(2026, 10, 2, 9, 0, tzinfo=PRAGUE)

    launched = await store.launch_pathway(
        header, plan, tasks, date(2026, 10, 2), indication=indication, coordinator=coordinator, recorded=recorded
    )

    assert len(launched.task_ids) == 7
    assert await store.care_plan_exists(case.id, plan)
    stored = await store.list_for_case(header.task_reference)  # `part-of` search
    assert stored[0].task.id == f"it-{run}.ct"
    care_plan = await client.read("CarePlan", launched.care_plan_id)
    assert len(care_plan["activity"]) == 7
    assert all(a["reference"]["reference"].startswith("Task/") for a in care_plan["activity"])  # urn:uuid rewritten

    first = stored[0]
    await store.save(first, first.task.model_copy(update={"status": TaskStatus.ACCEPTED}), description="it: accept")
    with pytest.raises(FhirConflictError):  # `first` carries the old version: IRIS must refuse the stale write
        await store.save(first, first.task.model_copy(update={"status": TaskStatus.FAILED}), description="it: stale")

    order = await client.read("ServiceRequest", launched.service_request_ids[tasks[0].id])
    assert order["requester"]["reference"] == indication.fhir_reference
    assert (await client.read("CarePlan", launched.care_plan_id))["author"]["reference"] == indication.fhir_reference
    provenance = await client.read("Provenance", launched.provenance_id)
    assert provenance["agent"][0]["onBehalfOf"]["reference"] == indication.fhir_reference

    with pytest.raises(ConflictError):  # lost race: the conditional creates match (200), so the launch is refused
        await store.launch_pathway(
            header, plan, tasks, date(2026, 10, 2), indication=indication, coordinator=coordinator, recorded=recorded
        )
