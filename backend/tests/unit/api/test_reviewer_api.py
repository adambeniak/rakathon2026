"""GET /api/reviewer/cases(/{ref}) (#104): the insurer reviewer's minimal, pseudonymous, own-insurer view.

And the other side: GET /api/cases and /api/cases/{id} answer 403 to the reviewer before anything is read.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.deps import (
    LlmClients,
    get_case_reader,
    get_directory_provider,
    get_fhir_client,
    get_handover_store,
    get_iris_pool,
    get_llm_clients,
)
from app.api.services.reviewer import case_ref, diagnosis_category, initials
from app.domain.case import Case, CaseState
from app.domain.errors import NotFoundError
from app.domain.patient import Patient, Sex
from app.fhir.cases import CaseExtras, CaseOverview
from app.main import create_app
from app.settings import PRAGUE, Settings
from tests.unit.api.fake_handover_store import FakeStore
from tests.unit.api.test_api import CASE, DemoDirectory, FakeFhir, FakeLlm, FakePool

REVIEWER = {"X-Demo-Role": "reviewer"}
OPENED = datetime(2026, 10, 22, 9, 15, tzinfo=PRAGUE)
SENT = CASE.model_copy(
    update={
        "state": CaseState.ZPETNA_VAZBA_ODESLANA,
        "mdt_start": datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE),
        "delivery_receipt": True,
    }
)
OTHER_INSURER = Case(
    id="c-kralova",
    patient=Patient(
        given="Marie",
        family="Králová",
        sex=Sex.FEMALE,
        birth_date=date(1971, 3, 9),
        birth_number="715309/2204",
        insurer_code="111",
    ),
    state=CaseState.ODESLANO,
    opened_at=datetime(2026, 10, 16, 10, 0, tzinfo=PRAGUE),
)
NO_INSURER = OTHER_INSURER.model_copy(
    update={"id": "c-bez-pojistovny", "patient": OTHER_INSURER.patient.model_copy(update={"insurer_code": None})}
)
EXTRAS = CaseExtras(
    diagnosis_code="C25.0",
    diagnosis_text="suspektní tumor hlavy pankreatu",
    gp_name="MUDr. Tomáš Řezníček",
    gp_opened_at=OPENED,
)


class ReviewerReader:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.overviews = [
            CaseOverview(case=SENT, document_count=13, extras=EXTRAS),
            CaseOverview(case=OTHER_INSURER, document_count=1, extras=CaseExtras(diagnosis_code="C18.9")),
            CaseOverview(case=NO_INSURER, document_count=1),
        ]

    async def list_cases(self) -> list[CaseOverview]:
        self.calls.append("list_cases")
        return self.overviews

    async def overview(self, case_id: str) -> CaseOverview:
        self.calls.append(f"overview:{case_id}")
        found = next((o for o in self.overviews if o.case.id == case_id), None)
        if found is None:
            raise NotFoundError("case", case_id)
        return found

    async def get_case(self, case_id: str) -> object:
        self.calls.append(f"get_case:{case_id}")
        raise AssertionError("the reviewer must never reach the full case read")


@pytest.fixture
def reader() -> ReviewerReader:
    return ReviewerReader()


@pytest.fixture
def client(settings: Settings, reader: ReviewerReader) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_case_reader] = lambda: reader
    app.dependency_overrides[get_directory_provider] = DemoDirectory
    app.dependency_overrides[get_fhir_client] = lambda: FakeFhir()
    app.dependency_overrides[get_iris_pool] = lambda: FakePool()
    llm = LlmClients(FakeLlm('{"facts": []}'), FakeLlm(None))
    app.dependency_overrides[get_llm_clients] = lambda: llm
    app.dependency_overrides[get_handover_store] = FakeStore
    with TestClient(app) as test_client:
        yield test_client


def test_reviewer_sees_only_own_insurer_cases_minimised(client: TestClient, settings: Settings) -> None:
    response = client.get("/api/reviewer/cases", headers=REVIEWER)

    assert response.status_code == 200
    [case] = response.json()
    assert case == {
        "ref": case_ref(SENT.id, settings.reviewer_pseudonym_key),
        "initials": "A. P.",
        "birth_year": 1963,
        "insurer_code": "211",
        "diagnosis_category": "C25",
        "state": "zpetna_vazba_odeslana",
        "referred_on": "2026-10-02",
        "intervals": {
            "t1": {"days": None, "status": "not_recorded", "start": None, "end": "2026-10-02"},
            "t2": {"days": 19, "status": "measured", "start": "2026-10-02", "end": "2026-10-21"},
            "t3": {"days": None, "status": "running", "start": "2026-10-21", "end": None},
        },
        "delivery": {"status": "opened_by_gp", "gp_opened_on": "2026-10-22"},
    }


def test_reviewer_payload_carries_no_identifying_or_clinical_text(client: TestClient) -> None:
    text = client.get("/api/reviewer/cases", headers=REVIEWER).text

    for leaked in ("Alena", "Procházková", "prochazkova", "1963-07-22", "635722", "pankreatu", "Řezníček", "C25.0"):
        assert leaked not in text


def test_ref_is_a_stable_pseudonym_not_the_case_id(settings: Settings) -> None:
    ref = case_ref(SENT.id, settings.reviewer_pseudonym_key)

    assert re.fullmatch(r"RV-[0-9A-F]{12}", ref)
    assert ref == case_ref(SENT.id, settings.reviewer_pseudonym_key)
    assert ref != case_ref(OTHER_INSURER.id, settings.reviewer_pseudonym_key)


def test_reviewer_detail_by_ref_is_an_audited_single_case_read(
    client: TestClient, reader: ReviewerReader, settings: Settings
) -> None:
    ref = case_ref(SENT.id, settings.reviewer_pseudonym_key)

    response = client.get(f"/api/reviewer/cases/{ref}", headers=REVIEWER)

    assert response.status_code == 200
    assert response.json()["ref"] == ref
    assert reader.calls == ["list_cases", f"overview:{SENT.id}"]


def test_other_insurers_case_is_not_found_for_the_reviewer(client: TestClient, settings: Settings) -> None:
    ref = case_ref(OTHER_INSURER.id, settings.reviewer_pseudonym_key)

    response = client.get(f"/api/reviewer/cases/{ref}", headers=REVIEWER)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


def test_malformed_ref_is_422(client: TestClient) -> None:
    assert client.get("/api/reviewer/cases/rakathon-2026-prochazkova", headers=REVIEWER).status_code == 422


@pytest.mark.parametrize("role", ["coordinator", "koc_physician", "koc_staff", "gp"])
def test_other_roles_get_403_on_the_reviewer_view_before_any_read(
    client: TestClient, reader: ReviewerReader, role: str
) -> None:
    response = client.get("/api/reviewer/cases", headers={"X-Demo-Role": role})

    assert response.status_code == 403
    assert response.json()["detail"] == "Přehled pro pojišťovnu je určen jen revizním lékařům"
    assert reader.calls == []


@pytest.mark.parametrize("path", ["/api/cases", f"/api/cases/{CASE.id}"])
def test_reviewer_gets_403_on_the_full_case_routes_before_any_read(
    client: TestClient, reader: ReviewerReader, path: str
) -> None:
    response = client.get(path, headers=REVIEWER)

    assert response.status_code == 403
    assert response.json()["detail"] == "Revizní lékař má k dispozici jen omezený přehled pro pojišťovnu"
    assert reader.calls == []


@pytest.mark.parametrize(
    ("state", "receipt", "opened", "expected"),
    [
        (CaseState.ZAVER_MDT, False, None, "not_sent"),
        (CaseState.ZPETNA_VAZBA_ODESLANA, True, None, "handed_over"),
        (CaseState.UZAVRENO, True, OPENED, "opened_by_gp"),
        (CaseState.UZAVRENO, False, None, "unconfirmed"),
    ],
)
def test_delivery_status(
    client: TestClient,
    reader: ReviewerReader,
    state: CaseState,
    receipt: bool,
    opened: datetime | None,
    expected: str,
) -> None:
    case = SENT.model_copy(update={"state": state, "delivery_receipt": receipt})
    reader.overviews = [CaseOverview(case=case, document_count=1, extras=CaseExtras(gp_opened_at=opened))]

    [body] = client.get("/api/reviewer/cases", headers=REVIEWER).json()

    assert body["delivery"]["status"] == expected


def test_helpers() -> None:
    assert initials("alena", "Procházková") == "A. P."
    assert diagnosis_category("c25.0") == "C25"
    assert diagnosis_category("C61") == "C61"
    assert diagnosis_category("tumor") is None
    assert diagnosis_category(None) is None


def test_reviewer_responses_are_not_cached(client: TestClient) -> None:
    response = client.get("/api/reviewer/cases", headers=REVIEWER)

    assert response.headers["cache-control"] == "no-store"
    assert "X-Demo-Role" in response.headers["vary"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"/api/cases/{CASE.id}/handover"),
        ("POST", f"/api/cases/{CASE.id}/handover"),
        ("GET", f"/api/cases/{CASE.id}/handover/export"),
    ],
)
def test_reviewer_gets_403_on_the_handover_before_any_read(
    client: TestClient, reader: ReviewerReader, method: str, path: str
) -> None:
    response = client.request(method, path, headers=REVIEWER)

    assert response.status_code == 403
    assert reader.calls == []


def test_pseudonym_key_is_dedicated_or_derived_never_the_raw_token_secret(settings: Settings) -> None:
    derived = settings.reviewer_pseudonym_key.get_secret_value()

    assert derived != settings.jwt_secret.get_secret_value()
    explicit = settings.model_copy(update={"reviewer_ref_key": SecretStr("from-key-vault")})
    assert explicit.reviewer_pseudonym_key.get_secret_value() == "from-key-vault"
