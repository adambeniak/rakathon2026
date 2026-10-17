from __future__ import annotations

import pytest

from app.api.schemas.coordination import CreateTaskRequest, TransitionRequest
from app.api.services.coordination import MAX_TASKS_PER_CASE, CoordinationService
from app.domain.common import Role
from app.domain.errors import ForbiddenError, InvalidInputError
from app.security.actor import SYSTEM_ACTOR
from tests.directory_fixtures import demo_directory
from tests.unit.api.test_coordination import (
    CASE_ID,
    COORDINATOR,
    FakeProvider,
    FakeReader,
    FakeStore,
    Harness,
    at,
    harness,  # noqa: F401 - fixture
)


async def test_the_technical_system_actor_cannot_move_tasks() -> None:
    service = CoordinationService(
        FakeReader(at("2026-10-21T08:00:00")),  # type: ignore[arg-type]
        FakeStore(),  # type: ignore[arg-type]
        lambda: at("2026-10-02T09:00:00"),
        FakeProvider(),  # type: ignore[arg-type]
    )
    with pytest.raises(ForbiddenError):
        await service.transition("c1.ct", TransitionRequest(event="deliver_result", document_id="doc-1"), SYSTEM_ACTOR)


async def test_a_case_has_a_bounded_number_of_tasks(harness: Harness) -> None:  # noqa: F811
    harness.launch()
    store = harness.store
    template = next(iter(store.resources.values()))
    for i in range(MAX_TASKS_PER_CASE - len(store.resources)):
        store.resources[f"c1.filler-{i}"] = {**template, "id": f"f{i}"}
    service = CoordinationService(
        FakeReader(at("2026-10-21T08:00:00")),  # type: ignore[arg-type]
        store,  # type: ignore[arg-type]
        lambda: at("2026-10-02T09:00:00"),
        FakeProvider(),  # type: ignore[arg-type]
    )
    coordinator = demo_directory().role("dvorakova-lucie@koc2-nemocnice-lipova")
    assert coordinator is not None
    with pytest.raises(InvalidInputError, match="nejvýše"):
        await service.create_task(
            CASE_ID, CreateTaskRequest(title="Další", owner_role=Role.KOC_PHYSICIAN), coordinator.party()
        )


@pytest.mark.parametrize(
    "url",
    ["https://a.example/p,https://b.example/p", "https://a.example/p|x", "ftp://a.example/p", "https://a.example/ p"],
)
def test_plan_url_cannot_widen_the_search(harness: Harness, url: str) -> None:  # noqa: F811
    assert harness.launch(headers=COORDINATOR, plan_url=url).status_code == 422


def test_dependency_ids_are_validated(harness: Harness) -> None:  # noqa: F811
    body = {"title": "Doplnit ECOG", "owner_role": "koc_physician", "depends_on": ["bad id|x"]}
    assert harness.client.post(f"/api/cases/{CASE_ID}/tasks", json=body, headers=COORDINATOR).status_code == 422
