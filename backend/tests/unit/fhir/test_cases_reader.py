"""CaseReader against a mocked IRIS, with fixtures built by the real mappers (seed <-> reader contract)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

import pytest
import respx

from app.domain.case import Case, CaseState
from app.domain.common import PartyRef, Role
from app.domain.document import SourceDocument
from app.domain.errors import NotFoundError
from app.domain.patient import Patient, Sex
from app.fhir.cases import CaseReader
from app.fhir.client import FhirClient
from app.fhir.mappers.case import case_task_to_fhir
from app.fhir.mappers.document import document_to_fhir
from app.fhir.mappers.patient import coverage_to_fhir, patient_to_fhir
from app.fhir.repository import FhirRepository
from app.security.actor import SYSTEM_ACTOR
from app.settings import PRAGUE
from tests.conftest import FHIR_BASE

PATIENT = Patient(
    given="Alena",
    family="Procházková",
    sex=Sex.FEMALE,
    birth_date=date(1963, 7, 22),
    birth_number="635722/1013",
    insurer_code="211",
)
CASE = Case(
    id="rakathon-2026-prochazkova",
    patient=PATIENT,
    state=CaseState.PRIPRAVENO_MDT,
    baton_holder=PartyRef(id="hruby-pavel@koc2-nemocnice-lipova", display="MDT GIT", role=Role.KOC_PHYSICIAN),
    next_deadline=datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE),
    opened_at=datetime(2026, 10, 2, 9, 30, tzinfo=PRAGUE),
)
TASK = {
    **case_task_to_fhir(
        CASE,
        episode_reference="EpisodeOfCare/4",
        patient_reference="Patient/3",
        requester_reference="PractitionerRole/1",
        owner_reference="PractitionerRole/2",
    ),
    "id": "5",
}
DOCUMENT = {
    **document_to_fhir(
        SourceDocument(
            doc_id="07_PL_zadost_KOC2_2026-10-02",
            title="PL – žádost",
            authored_at=date(2026, 10, 2),
            received_at=datetime(2026, 10, 2, 9, 30, tzinfo=PRAGUE),
        ),
        b"docx",
        patient_reference="Patient/3",
        episode_reference="EpisodeOfCare/4",
        custodian_reference=None,
        author_reference=None,
    ),
    "id": "9",
}


def _bundle(*resources: dict[str, Any], total: int | None = None) -> dict[str, Any]:
    bundle: dict[str, Any] = {"resourceType": "Bundle", "entry": [{"resource": r} for r in resources]}
    if total is not None:
        bundle["total"] = total
    return bundle


@pytest.fixture
def reader(fhir_client: FhirClient) -> CaseReader:
    return CaseReader(FhirRepository(fhir_client, SYSTEM_ACTOR, clock=lambda: datetime(2026, 10, 16, tzinfo=UTC)))


@pytest.fixture
def iris() -> respx.MockRouter:
    with respx.mock(base_url=FHIR_BASE, assert_all_called=False) as router:
        router.get("/Patient/3").respond(200, json={**patient_to_fhir(PATIENT), "id": "3"})
        coverage = coverage_to_fhir(patient=PATIENT, patient_reference="Patient/3", payor_reference="Organization/8")
        router.get("/Coverage").respond(200, json=_bundle({**coverage, "id": "6"}))
        router.post("/AuditEvent").respond(201, headers={"Location": f"{FHIR_BASE}/AuditEvent/99"})
        # Header facts (appended after the audit route: tests address routes by index).
        router.get("/EpisodeOfCare/4").respond(
            200,
            json={"resourceType": "EpisodeOfCare", "id": "4", "managingOrganization": {"reference": "Organization/8"}},
        )
        router.get("/Organization/8").respond(
            200, json={"resourceType": "Organization", "id": "8", "name": "KOC 2 – Lipová"}
        )
        router.get("/PractitionerRole/1").respond(
            200,
            json={
                "resourceType": "PractitionerRole",
                "id": "1",
                "practitioner": {"display": "MUDr. Tomáš Řezníček"},
                "organization": {"display": "Ordinace PL"},
            },
        )
        yield router


async def test_list_cases_maps_task_patient_coverage_and_counts_documents(
    reader: CaseReader, iris: respx.MockRouter
) -> None:
    iris.get("/Task").respond(200, json=_bundle(TASK))
    count = iris.get("/DocumentReference", params={"_summary": "count"}).respond(200, json=_bundle(total=13))

    [overview] = await reader.list_cases()

    assert overview.case == CASE
    assert overview.document_count == 13
    assert overview.extras.koc_name == "KOC 2 – Lipová"
    assert (overview.extras.gp_name, overview.extras.gp_practice) == ("MUDr. Tomáš Řezníček", "Ordinace PL")
    assert overview.extras.diagnosis_text is None  # the seeded story case has no ServiceRequest
    assert count.calls[0].request.url.params["encounter"] == "EpisodeOfCare/4"
    audit = json.loads(iris.routes[2].calls[0].request.content)
    assert audit["action"] == "E"
    assert {e["what"]["reference"] for e in audit["entity"]} == {"Task/5", "Patient/3", "EpisodeOfCare/4"}


async def test_get_case_lists_documents_and_audits_a_read(reader: CaseReader, iris: respx.MockRouter) -> None:
    iris.get("/Task").respond(200, json=_bundle(TASK))
    iris.get("/DocumentReference").respond(200, json=_bundle(DOCUMENT))

    view = await reader.get_case("rakathon-2026-prochazkova")

    assert view.case.patient.insurer_code == "211"
    assert [d.doc_id for d in view.documents] == ["07_PL_zadost_KOC2_2026-10-02"]
    audit = json.loads(iris.routes[2].calls[0].request.content)
    assert audit["action"] == "R"
    assert "DocumentReference/9" in {e["what"]["reference"] for e in audit["entity"]}


async def test_unknown_case_raises_not_found_without_audit(reader: CaseReader, iris: respx.MockRouter) -> None:
    iris.get("/Task").respond(200, json=_bundle())

    with pytest.raises(NotFoundError):
        await reader.get_case("unknown")

    assert iris.routes[2].call_count == 0


async def test_suspected_diagnosis_comes_with_its_evidence_from_the_service_request(
    reader: CaseReader, iris: respx.MockRouter
) -> None:
    from app.domain.evidence import Evidence
    from app.domain.referral import ReferralSubmission
    from app.fhir.mappers.referral import service_request_to_fhir

    submission = ReferralSubmission(
        given="Alena",
        family="Procházková",
        sex=Sex.FEMALE,
        birth_date=date(1963, 7, 22),
        birth_number="635722/1013",
        diagnosis_code="C25.0",
        diagnosis_text="suspektní tumor hlavy pankreatu",
        koc_id="koc2-nemocnice-lipova",
        consent_confirmed=True,
        priority="urgent",
    )
    request = {
        **service_request_to_fhir(
            "c",
            submission,
            patient_reference="Patient/3",
            requester=PartyRef(id="r@o", display="GP", role=Role.GP),
            requester_reference="PractitionerRole/1",
            koc_reference="Organization/8",
            letter_reference="DocumentReference/9",
            authored_on=datetime(2026, 10, 2, tzinfo=UTC),
            diagnosis_evidence=[Evidence(doc_id="07_PL", quote="Suspektní diagnóza: C25.0")],
        ),
        "id": "30",
    }
    with_request = {**TASK, "basedOn": [{"reference": "ServiceRequest/30"}]}
    iris.get("/Task").respond(200, json=_bundle(with_request))
    iris.get("/ServiceRequest/30").respond(200, json=request)
    iris.get("/DocumentReference", params={"_summary": "count"}).respond(200, json=_bundle(total=1))

    [overview] = await reader.list_cases()

    assert (overview.extras.diagnosis_code, overview.extras.diagnosis_text) == (
        "C25.0",
        "suspektní tumor hlavy pankreatu",
    )
    assert [(e.doc_id, e.quote) for e in overview.extras.diagnosis_evidence] == [("07_PL", "Suspektní diagnóza: C25.0")]


async def test_loading_a_case_for_a_write_audits_the_read(reader: CaseReader, iris: respx.MockRouter) -> None:
    iris.get("/Task").respond(200, json=_bundle(TASK))

    loaded = await reader.load("rakathon-2026-prochazkova")

    assert loaded.case.id == "rakathon-2026-prochazkova"
    audit = json.loads(iris.routes[2].calls[0].request.content)
    assert audit["action"] == "R"
    assert {e["what"]["reference"] for e in audit["entity"]} == {"Task/5", "Patient/3", "EpisodeOfCare/4"}
