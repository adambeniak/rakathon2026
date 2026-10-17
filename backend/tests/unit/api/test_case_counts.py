"""Case summary counters come from the handover service, with the same cut-off as the handover screen."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import (
    LlmClients,
    get_case_reader,
    get_directory_provider,
    get_fhir_client,
    get_handover_store,
    get_iris_pool,
    get_llm_clients,
)
from app.api.services import case_counts as service
from app.api.services.handover_assembly import assemble_handover as original
from app.domain.handover import Handover
from app.fhir.cases import CaseContentsView, CaseDetailView, CaseOverview
from app.main import create_app
from app.settings import PRAGUE, Settings
from tests.unit.api.fake_handover_store import FakeStore
from tests.unit.api.test_api import CASE, DOCUMENT, DemoDirectory, FakeFhir, FakeLlm, FakePool, FakeReader

CASE_URL = f"/api/cases/{CASE.id}"


class CaseReader(FakeReader):
    """The fake reader lists the module-level CASE; these tests need the copy with `mdt_start`."""

    async def list_cases(self) -> list[CaseOverview]:
        return [CaseOverview(case=self.case, document_count=13)]

    async def get_case(self, case_id: str) -> CaseDetailView:
        return CaseDetailView(case=self.case, documents=[DOCUMENT])


class BrokenContents(CaseReader):
    async def get_case_contents(self, case_id: str) -> CaseContentsView:
        raise RuntimeError("IRIS is down")


@pytest.fixture
def make_client(settings: Settings) -> Iterator[Callable[[FakeReader], TestClient]]:
    clients: list[TestClient] = []

    def make(reader: FakeReader) -> TestClient:
        app: FastAPI = create_app(settings)
        app.dependency_overrides[get_case_reader] = lambda: reader
        app.dependency_overrides[get_directory_provider] = DemoDirectory  # the shared current_actor
        app.dependency_overrides[get_fhir_client] = lambda: FakeFhir()
        app.dependency_overrides[get_iris_pool] = lambda: FakePool()
        llm = LlmClients(FakeLlm('{"facts": []}'), FakeLlm(None))
        app.dependency_overrides[get_llm_clients] = lambda: llm
        store = FakeStore()
        app.dependency_overrides[get_handover_store] = lambda: store
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def handover_counts(client: TestClient) -> dict[str, int | None]:
    """What the handover screen shows at the default cut-off, counted by the same rule."""
    handover = Handover.model_validate(client.get(f"{CASE_URL}/handover").json())
    counts = service.count_handover(handover)
    assert counts is not None
    return counts.model_dump()


def test_list_and_detail_carry_the_counts_of_the_handover(make_client: Callable[[FakeReader], TestClient]) -> None:
    client = make_client(CaseReader())
    expected = handover_counts(client)

    [listed] = client.get("/api/cases").json()
    detail = client.get(CASE_URL).json()

    for case in (listed, detail):
        assert case["counts"] == expected
        assert case["missing_count"] == expected["missing"]
        assert case["conflict_count"] == expected["conflict"]
    assert expected["missing"] is not None
    assert expected["missing"] > 0  # nothing is extracted from the fake documents


def test_counts_use_the_mdt_start_of_the_case(
    make_client: Callable[[FakeReader], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[datetime] = []

    async def spy(*args: object, **kwargs: object) -> Handover:
        seen.append(args[-1])  # type: ignore[arg-type]
        return await original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr("app.api.services.case_counts.assemble_handover", spy)
    mdt_start = datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)

    make_client(CaseReader(mdt_start=mdt_start)).get("/api/cases")

    assert seen == [mdt_start]


def test_counts_are_null_not_zero_when_the_handover_cannot_be_built(
    make_client: Callable[[FakeReader], TestClient],
) -> None:
    client = make_client(BrokenContents())

    response = client.get("/api/cases")

    assert response.status_code == 200  # one handover that cannot be built does not fail the list
    [case] = response.json()
    assert case["counts"] is None
    assert case["missing_count"] is None
    assert case["conflict_count"] is None
    assert client.get(CASE_URL).json()["counts"] is None


def test_counts_are_null_when_no_document_is_usable_at_the_cut_off(
    make_client: Callable[[FakeReader], TestClient],
) -> None:
    before_every_document = datetime(2026, 1, 1, tzinfo=PRAGUE)

    [case] = make_client(CaseReader(mdt_start=before_every_document)).get("/api/cases").json()

    assert case["counts"] is None  # nothing was assembled: the screen shows its empty state


def test_a_failing_llm_cache_is_null_counts_not_an_error(settings: Settings) -> None:
    app = create_app(settings)
    app.dependency_overrides[get_case_reader] = lambda: FakeReader()
    app.dependency_overrides[get_directory_provider] = DemoDirectory  # the shared current_actor
    app.dependency_overrides[get_llm_clients] = lambda: LlmClients(FakeLlm(None), FakeLlm(None))
    app.dependency_overrides[get_handover_store] = FakeStore
    with TestClient(app) as client:
        [case] = client.get("/api/cases").json()
    assert case["counts"] is None
