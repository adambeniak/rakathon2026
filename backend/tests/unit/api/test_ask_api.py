from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_ask_service
from app.main import create_app
from app.retrieval.ask import AskService
from app.settings import Settings
from tests.unit.retrieval.test_ask_lock import BIOPSY, CHUNKS
from tests.unit.retrieval.test_ask_service import ANSWER, FakeAudit, FakeLLM, FakeLocator, FakeRetriever

URL = "/api/cases/rakathon-2026-prochazkova/ask"


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def audit() -> FakeAudit:
    return FakeAudit()


@pytest.fixture
def client(app: FastAPI, audit: FakeAudit) -> Iterator[TestClient]:
    app.dependency_overrides[get_ask_service] = lambda: AskService(
        FakeLocator(), FakeRetriever(CHUNKS), FakeLLM(ANSWER), audit, top_k=8, model="m"
    )
    with TestClient(app) as test_client:
        yield test_client


def test_ask_returns_a_labelled_cited_draft(client: TestClient, audit: FakeAudit) -> None:
    response = client.post(URL, json={"question": "Kdy byla vysazena antikoagulace před biopsií?"})

    assert response.status_code == 200
    body = response.json()
    assert body["label"] == "Návrh AI"
    assert body["status"] == "answered"
    assert body["as_of"] == "2026-10-21T08:00:00+02:00"  # settings.now() = demo MDT start
    assert body["answer_text"].endswith(f"[{BIOPSY}]")
    assert body["sentences"][0]["citations"][0] == {
        "doc_id": BIOPSY,
        "title": "title 09",
        "quote": "Apixaban vysazen 48 h před výkonem",
    }
    assert [s["doc_id"] for s in body["sources"]] == [c.hit.doc_id for c in CHUNKS]
    assert body["dropped_sentences"] == 1
    assert audit.reads


def test_ask_validates_without_echoing_the_question(client: TestClient) -> None:
    response = client.post(URL, json={"question": "x" * 501, "as_of": "2026-10-21T08:00:00"})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "xxxx" not in response.text
    assert {tuple(e["loc"])[-1] for e in response.json()["errors"]} == {"question", "as_of"}  # naive as_of refused


def test_unknown_case_is_404(client: TestClient) -> None:
    response = client.post("/api/cases/nope/ask", json={"question": "Jaký je ECOG?"})
    assert response.status_code == 404


def test_llm_cache_miss_is_503_problem(app: FastAPI, client: TestClient) -> None:
    from app.extraction.llm import CacheMissError

    app.dependency_overrides[get_ask_service] = lambda: AskService(
        FakeLocator(), FakeRetriever(CHUNKS), FakeLLM(error=CacheMissError("miss")), FakeAudit(), top_k=8, model="m"
    )
    response = client.post(URL, json={"question": "Jaký je ECOG?"})

    assert response.status_code == 503
    assert response.json()["type"].endswith("/ai-unavailable")
    assert response.json()["detail"] == "Odpověď AI teď není k dispozici."


def test_ask_is_in_the_contract(app: FastAPI) -> None:
    operation = app.openapi()["paths"]["/api/cases/{case_id}/ask"]["post"]
    assert operation["operationId"] == "cases-ask_case"
    assert "503" in operation["responses"]


class StaticDirectory:
    def __init__(self, directory: object) -> None:
        self.directory = directory

    async def get(self) -> object:
        return self.directory


async def test_only_case_participants_may_ask() -> None:
    from app.api.deps import ParticipantCaseLocator
    from app.domain.case import CaseState
    from app.domain.common import PartyRef, Role
    from app.domain.errors import ForbiddenError
    from tests.unit.workflow.test_request_workflow import COORDINATOR, DIRECTORY, GP, FakeReader, loaded

    case = loaded(CaseState.TRIAGE)
    directory = StaticDirectory(DIRECTORY)
    reviewer = PartyRef(id="reviewer", display="Revizní lékař", role=Role.REVIEWER)

    for actor in (COORDINATOR.party(), GP.party()):  # type: ignore[union-attr]
        locator = ParticipantCaseLocator(FakeReader(case), actor, directory)  # type: ignore[arg-type]
        assert await locator.case_patient("c") == (f"Task/{case.task['id']}", case.task["for"]["reference"])
    with pytest.raises(ForbiddenError):
        await ParticipantCaseLocator(FakeReader(case), reviewer, directory).case_patient("c")  # type: ignore[arg-type]
