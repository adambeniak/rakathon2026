"""GET /api/cases/{id}/mdt-record: KOC team only, audited, as of the MDT start, DOCX download."""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import datetime

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.api.deps import (
    LlmClients,
    get_case_reader,
    get_directory_provider,
    get_fhir_client,
    get_handover_store,
    get_iris_pool,
    get_llm_clients,
    get_repository,
)
from app.fhir.cases import LoadedCase
from app.fhir.directory import Directory
from app.main import create_app
from app.outputs.mdt_record import DOCX_MEDIA_TYPE
from app.seed import demo_case
from app.settings import PRAGUE, Settings
from tests.directory_fixtures import demo_directory
from tests.unit.api.fake_handover_store import FakeStore
from tests.unit.api.test_api import FakeFhir, FakeLlm, FakePool, FakeReader

URL = "/api/cases/rakathon-2026-prochazkova/mdt-record"
MDT_START = datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)
DIRECTORY = demo_directory()
GP = DIRECTORY.role(demo_case.GP_ROLE)
KOC2 = DIRECTORY.org(demo_case.KOC2)
assert GP
assert KOC2


class CaseReader(FakeReader):
    """The test_api reader, but `load` knows the referring GP and the managing KOC (authorize_case is real)."""

    async def load(self, case_id: str) -> LoadedCase:
        base = await super().load(case_id)
        task = {"id": "5", "requester": {"reference": GP.ref}}  # type: ignore[union-attr]
        episode = {"managingOrganization": {"reference": KOC2.ref}}  # type: ignore[union-attr]
        return LoadedCase(task=task, episode=episode, case=base.case)


class FakeRepository:
    def __init__(self) -> None:
        self.exports: list[tuple[list[str], str]] = []

    async def audit_derived_write(self, entities: list[str], *, description: str) -> None:
        self.exports.append((entities, description))


class FakeProvider:
    async def get(self) -> Directory:
        return DIRECTORY


def _client(settings: Settings, reader: CaseReader, repository: FakeRepository) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_case_reader] = lambda: reader
    app.dependency_overrides[get_directory_provider] = lambda: FakeProvider()
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_fhir_client] = lambda: FakeFhir()
    app.dependency_overrides[get_iris_pool] = lambda: FakePool()
    llm = LlmClients(FakeLlm('{"facts": []}'), FakeLlm(None))
    app.dependency_overrides[get_llm_clients] = lambda: llm
    store = FakeStore()
    app.dependency_overrides[get_handover_store] = lambda: store
    with TestClient(app) as client:
        yield client


@pytest.fixture
def repository() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def client(settings: Settings, repository: FakeRepository) -> Iterator[TestClient]:
    yield from _client(settings, CaseReader(mdt_start=MDT_START), repository)


@pytest.fixture
def client_without_mdt_start(settings: Settings, repository: FakeRepository) -> Iterator[TestClient]:
    yield from _client(settings, CaseReader(mdt_start=None), repository)


@pytest.mark.parametrize("role", ["coordinator", "koc_physician", "koc_staff"])
def test_the_koc_team_downloads_the_record_as_a_docx(client: TestClient, repository: FakeRepository, role: str) -> None:
    response = client.get(URL, headers={"X-Demo-Role": role})

    assert response.status_code == 200
    assert response.headers["content-type"] == DOCX_MEDIA_TYPE
    assert response.headers["content-disposition"] == 'attachment; filename="mdt-zapis-2026-10-21.docx"'
    assert response.headers["cache-control"] == "no-store"
    assert "rakathon" not in response.headers["content-disposition"]  # the case id embeds the surname
    paragraphs = [p.text for p in Document(io.BytesIO(response.content)).paragraphs]
    assert "Zápis k jednání multidisciplinárního týmu (MDT)" in paragraphs
    assert "Stav podkladů k 21. 10. 2026 08:00. Zahrnuto dokumentů: 1, nezahrnuto: 1." in paragraphs
    assert any(p.startswith("– 12_Algeziologie_2026-10-26 – po MDT") for p in paragraphs)  # authored after the MDT
    assert repository.exports[-1] == (["Task/5"], "MDT record exported as DOCX")  # every export is audited


@pytest.mark.parametrize(("role", "status"), [("gp", 403), ("reviewer", 403)])
def test_only_the_koc_team_may_export(client: TestClient, repository: FakeRepository, role: str, status: int) -> None:
    response = client.get(URL, headers={"X-Demo-Role": role})

    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert repository.exports == []


def test_the_record_is_always_as_of_the_mdt_start(client: TestClient) -> None:
    other_day = client.get(URL, params={"as_of": "2026-10-28"}, headers={"X-Demo-Role": "coordinator"})

    document = Document(io.BytesIO(other_day.content))
    assert "Stav podkladů k 21. 10. 2026 08:00." in document.paragraphs[2].text  # a client cut-off is ignored


def test_pdf_is_not_offered(client: TestClient) -> None:
    response = client.get(URL, params={"format": "pdf"}, headers={"X-Demo-Role": "coordinator"})

    assert response.status_code == 422


def test_a_case_without_a_set_mdt_start_has_no_record(
    client_without_mdt_start: TestClient, repository: FakeRepository
) -> None:
    response = client_without_mdt_start.get(URL, headers={"X-Demo-Role": "coordinator"})

    assert response.status_code == 422
    assert repository.exports == []


def test_an_unknown_case_is_404(client: TestClient) -> None:
    response = client.get("/api/cases/unknown-case/mdt-record", headers={"X-Demo-Role": "coordinator"})

    assert response.status_code == 404
