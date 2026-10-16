from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_case_reader,
    get_directory_provider,
    get_fhir_client,
    get_request_workflow,
    get_triage_reader,
)
from app.domain.case import Case, CaseState
from app.domain.common import PartyRef, Role
from app.domain.document import SourceDocument
from app.domain.task import Task, TaskBusinessStatus, TaskStatus
from app.domain.triage import ListedExam, propose_requests
from app.fhir.cases import CaseOverview
from app.fhir.directory import Directory
from app.fhir.triage import ProposalsView
from app.fhir.workflow import ReceivedOutcome, RequestsOutcome, RequestView
from app.main import create_app
from app.seed import demo_case
from app.settings import PRAGUE, Settings
from tests.directory_fixtures import demo_directory
from tests.document_fixtures import DOCS_DIR

COORDINATOR = demo_case.COORDINATOR_ROLE
NOW = datetime(2026, 10, 2, 10, 0, tzinfo=PRAGUE)
CASE_URL = f"/api/cases/{demo_case.CASE_ID}"


def _case(state: CaseState) -> Case:
    return Case(
        id=demo_case.CASE_ID,
        patient=demo_case.PATIENT,
        state=state,
        baton_holder=PartyRef(id=COORDINATOR, display="Bc. Lucie Dvořáková", role=Role.COORDINATOR),
        opened_at=NOW,
    )


class FakeProvider:
    async def get(self) -> Directory:
        return demo_directory()


class FakeReader:
    async def overview(self, case_id: str) -> CaseOverview:
        return CaseOverview(case=_case(CaseState.CEKA_NA_PODKLADY), document_count=2)


class FakeWorkflow:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def create_requests(self, case_id: str, items: list[Any], **kwargs: Any) -> RequestsOutcome:
        self.calls.append(("create", items))
        task = Task(
            id=f"{case_id}-req-1",
            case_id=case_id,
            code="request-report",
            title="Vyžádat výsledek: RTG plic",
            status=TaskStatus.REQUESTED,
            business_status=TaskBusinessStatus.OBJEDNANO,
            due=datetime(2026, 10, 6, 23, 59, tzinfo=PRAGUE),
            location="Radiologické centrum Modřany",
        )
        return RequestsOutcome(_case(CaseState.CEKA_NA_PODKLADY), [RequestView(task, date(2026, 9, 3))])

    async def receive_document(self, case_id: str, upload: Any, **kwargs: Any) -> ReceivedOutcome:
        self.calls.append(("receive", kwargs["request_id"]))
        document = SourceDocument(
            doc_id=upload.doc.doc_id, title=upload.file_name, authored_at=kwargs["authored_at"], received_at=NOW
        )
        return ReceivedOutcome(_case(CaseState.KOMPLETNI), document, 0, "podklady_kompletni")


class FakeTriage:
    async def proposals(self, case_id: str, directory: Directory, actor: Any) -> ProposalsView:
        exam = ListedExam.model_validate(
            {
                "label": "RTG plic 3. 9. 2026 (Radiologické centrum Modřany)",
                "exam_date": date(2026, 9, 3),
                "evidence": [{"doc_id": "07_PL", "quote": "2. RTG plic 3. 9. 2026 (Radiologické centrum Modřany)"}],
            }
        )
        orgs = [o.org for o in directory.orgs]
        return ProposalsView("07_PL", propose_requests([exam], [], orgs, []))


@pytest.fixture
def workflow() -> FakeWorkflow:
    return FakeWorkflow()


@pytest.fixture
def client(settings: Settings, workflow: FakeWorkflow) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_directory_provider] = lambda: FakeProvider()
    app.dependency_overrides[get_request_workflow] = lambda: workflow
    app.dependency_overrides[get_triage_reader] = lambda: FakeTriage()
    app.dependency_overrides[get_case_reader] = lambda: FakeReader()
    app.dependency_overrides[get_fhir_client] = lambda: object()
    with TestClient(app) as test_client:
        yield test_client


def test_proposals_are_quoted_from_the_letter_with_the_workplace(client: TestClient) -> None:
    response = client.get(f"{CASE_URL}/document-requests/proposals", headers={"X-Demo-Role": "coordinator"})

    assert response.status_code == 200
    [proposal] = response.json()["proposals"]
    assert proposal["recipient_org_id"] == "rc-modrany"
    assert proposal["status"] == "missing"
    assert proposal["evidence"][0]["quote"].startswith("2. RTG plic")


def test_creating_requests_returns_the_new_state_and_the_tasks(client: TestClient, workflow: FakeWorkflow) -> None:
    body = {"items": [{"label": "RTG plic", "recipient_org_id": "rc-modrany", "exam_date": "2026-09-03"}]}

    response = client.post(f"{CASE_URL}/document-requests", json=body, headers={"X-Demo-Role": "coordinator"})

    assert response.status_code == 201
    data = response.json()
    assert data["case"]["state"] == "ceka_na_podklady"
    [request] = data["requests"]
    assert (request["label"], request["status"], request["business_status"]) == ("RTG plic", "requested", "objednano")
    assert request["due"].startswith("2026-10-06T23:59")
    assert workflow.calls[0][0] == "create"


def test_empty_request_list_is_rejected(client: TestClient) -> None:
    response = client.post(f"{CASE_URL}/document-requests", json={"items": []}, headers={"X-Demo-Role": "coordinator"})

    assert response.status_code == 422


def test_uploading_the_last_report_reports_the_case_event(client: TestClient, workflow: FakeWorkflow) -> None:
    path = DOCS_DIR / "03_RTG_plic_2026-09-03.docx"

    response = client.post(
        f"{CASE_URL}/documents",
        files={"file": (path.name, path.read_bytes(), "application/octet-stream")},
        data={"request_id": f"{demo_case.CASE_ID}-req-1"},
        headers={"X-Demo-Role": "coordinator"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["case_event"] == "podklady_kompletni"
    assert body["open_requests_remaining"] == 0
    assert body["document"]["doc_id"] == "03_RTG_plic_2026-09-03"
    assert body["document"]["authored_at"] == "2026-09-03"  # from the file name
    assert workflow.calls == [("receive", f"{demo_case.CASE_ID}-req-1")]


def test_file_name_without_a_date_needs_authored_at(client: TestClient) -> None:
    path = DOCS_DIR / "03_RTG_plic_2026-09-03.docx"
    files = {"file": ("rtg.docx", path.read_bytes(), "application/octet-stream")}

    missing = client.post(f"{CASE_URL}/documents", files=files, headers={"X-Demo-Role": "coordinator"})
    given = client.post(
        f"{CASE_URL}/documents", files=files, data={"authored_at": "2026-09-03"}, headers={"X-Demo-Role": "coordinator"}
    )

    assert missing.status_code == 422
    assert given.status_code == 201


def test_invalid_date_in_the_file_name_is_a_422_not_a_500(client: TestClient) -> None:
    path = DOCS_DIR / "03_RTG_plic_2026-09-03.docx"

    response = client.post(
        f"{CASE_URL}/documents",
        files={"file": ("rtg_2026-13-45.docx", path.read_bytes(), "application/octet-stream")},
        headers={"X-Demo-Role": "coordinator"},
    )

    assert response.status_code == 422


def test_the_configured_upload_limit_is_used_not_a_constant(settings: Settings, workflow: FakeWorkflow) -> None:
    small = settings.model_copy(update={"upload_max_bytes": 2048})
    app = create_app(small)
    app.dependency_overrides[get_directory_provider] = lambda: FakeProvider()
    app.dependency_overrides[get_request_workflow] = lambda: workflow
    app.dependency_overrides[get_case_reader] = lambda: FakeReader()
    app.dependency_overrides[get_fhir_client] = lambda: object()
    path = DOCS_DIR / "03_RTG_plic_2026-09-03.docx"
    with TestClient(app) as test_client:
        response = test_client.post(
            f"{CASE_URL}/documents", files={"file": (path.name, path.read_bytes(), "application/octet-stream")}
        )

    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
