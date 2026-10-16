from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_case_reader,
    get_directory_provider,
    get_fhir_client,
    get_referral_writer,
    get_repository,
)
from app.documents.ingest import UploadedDocument
from app.domain.case import Case, CaseState
from app.domain.common import PartyRef, Role
from app.fhir.cases import CaseOverview
from app.fhir.directory import Directory
from app.fhir.referrals import ReferralResult
from app.main import create_app
from app.seed import demo_case
from app.settings import PRAGUE, Settings
from tests.directory_fixtures import demo_directory
from tests.document_fixtures import DOCS_DIR

GP = "reznicek-tomas@pl-dolni-brezany"
LETTER = DOCS_DIR / "07_PL_zadost_KOC2_2026-10-02.docx"
PAYLOAD = {
    "given": "Alena",
    "family": "Procházková",
    "sex": "female",
    "birth_date": "1963-07-22",
    "birth_number": "635722/1013",
    "insurer_code": "211",
    "diagnosis_code": "C25.0",
    "diagnosis_text": "suspektní tumor hlavy pankreatu",
    "koc_id": "koc2-nemocnice-lipova",
    "consent_confirmed": True,
    "priority": "urgent",
}


class FakeProvider:
    async def get(self) -> Directory:
        return demo_directory()


class FakeRepository:
    def __init__(self) -> None:
        self.extractions = 0

    async def audit_extract(self) -> None:
        self.extractions += 1


class FakeWriter:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def submit(
        self, submission: Any, letter: UploadedDocument, attachments: Any, **kwargs: Any
    ) -> ReferralResult:
        self.calls.append(
            {"submission": submission, "letter": letter, "prefill": kwargs["prefill"], "actor": kwargs["actor"]}
        )
        return ReferralResult(case_id=demo_case.CASE_ID, warnings=())


class FakeReader:
    async def overview(self, case_id: str) -> CaseOverview:
        case = Case(
            id=case_id,
            patient=demo_case.PATIENT,
            state=CaseState.ODESLANO,
            baton_holder=PartyRef(id=demo_case.COORDINATOR_ROLE, display="Koordinátor KOC 2", role=Role.COORDINATOR),
            opened_at=datetime(2026, 10, 2, 9, 30, tzinfo=PRAGUE),
        )
        return CaseOverview(case=case, document_count=1)


@pytest.fixture
def repository() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def writer() -> FakeWriter:
    return FakeWriter()


@pytest.fixture
def client(settings: Settings, writer: FakeWriter, repository: FakeRepository) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_directory_provider] = lambda: FakeProvider()
    app.dependency_overrides[get_referral_writer] = lambda: writer
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_case_reader] = lambda: FakeReader()
    app.dependency_overrides[get_fhir_client] = lambda: object()
    with TestClient(app) as test_client:
        yield test_client


def _letter() -> dict[str, Any]:
    return {"letter": (LETTER.name, LETTER.read_bytes(), "application/octet-stream")}


def test_prefill_of_letter_07_matches_the_acceptance_values(client: TestClient) -> None:
    response = client.post("/api/referrals/prefill", files=_letter(), headers={"X-Demo-Role": "gp"})

    assert response.status_code == 200
    body = response.json()
    assert (body["given"]["value"], body["family"]["value"]) == ("Alena", "Procházková")
    assert body["age_text"]["value"] == "63 let"
    assert body["insurer_code"]["value"] == "211"
    assert body["insurer_name"].startswith("Zdravotní pojišťovna")
    assert body["suspected_diagnosis"]["value"]["code"] == "C25.0"
    assert body["contact_person"]["value"]["relation"] == "dcera"
    assert body["contact_person"]["value"]["phone"] == "+420 777 000 542"
    assert "Souhlasí se sdílením informací s dcerou." in [s["value"] for s in body["consent_statements"]]
    assert body["requesting_gp_role_id"] == GP
    assert body["sex"]["derived"] is True
    for field in ("given", "family", "birth_date", "insurer_code", "contact_person", "suspected_diagnosis"):
        assert body[field]["evidence"], field


def test_letter_without_a_recorded_response_is_a_503_problem_not_a_trace(client: TestClient) -> None:
    other = DOCS_DIR / "01_Kardiologie_2026-07-20.docx"
    # Same bytes under another name would still hit the cache by text; change the id so the key differs.
    response = client.post(
        "/api/referrals/prefill",
        files={"letter": ("jiny_dokument_2026-10-02.docx", other.read_bytes(), "application/octet-stream")},
    )

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("/extraction-unavailable")
    assert "Traceback" not in response.text


def test_wrong_file_type_is_415(client: TestClient) -> None:
    response = client.post("/api/referrals/prefill", files={"letter": ("a.docx", b"MZ not a document", "text/plain")})

    assert response.status_code == 415


def test_confirmed_referral_creates_the_case(client: TestClient, writer: FakeWriter) -> None:
    response = client.post(
        "/api/referrals",
        files=_letter(),
        data={"payload": json.dumps(PAYLOAD)},
        headers={"X-Demo-Role": "gp"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["case"]["state"] == "odeslano"
    assert body["case"]["baton_holder"]["display"] == "Koordinátor KOC 2"
    [call] = writer.calls
    assert call["submission"].koc_id == "koc2-nemocnice-lipova"
    assert call["prefill"] is not None  # the cached prefill is re-run to record what the GP edited
    assert call["actor"].role is Role.GP


def test_invalid_payload_is_a_422_problem_without_echoing_input(client: TestClient) -> None:
    bad = {**PAYLOAD, "birth_number": "tajne-cislo"}

    response = client.post("/api/referrals", files=_letter(), data={"payload": json.dumps(bad)})

    assert response.status_code == 422
    assert "tajne-cislo" not in response.text
    assert response.json()["errors"][0]["loc"][:2] == ["body", "payload"]


def test_oversize_upload_is_413_in_czech_before_any_parsing(client: TestClient) -> None:
    big = b"PK\x03\x04" + b"0" * (11 * 1024 * 1024)

    declared = client.post("/api/referrals/prefill", files={"letter": ("a.docx", big, "application/octet-stream")})

    assert declared.status_code == 413
    assert declared.headers["content-type"].startswith("application/problem+json")
    assert "příliš velký" in declared.json()["detail"]


def test_streamed_body_without_content_length_is_capped_too(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(12):
            yield b"0" * (1024 * 1024)

    response = client.post(
        "/api/referrals/prefill", content=chunks(), headers={"Content-Type": "multipart/form-data; boundary=x"}
    )

    assert response.status_code == 413
