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
        # Read-backs of the workflow records (waivers, gp_opened): empty unless a test says otherwise.
        router.get("/Provenance").respond(200, json=_bundle())
        router.get("/AuditEvent").respond(200, json=_bundle())
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


# --- read-backs: readiness waivers (#131) and gp_opened (#113) ------------------------------------------------------

SIGNER = PartyRef(id="markova-lenka@koc2-nemocnice-lipova", display="MUDr. Lenka Marková", role=Role.KOC_PHYSICIAN)
GP_ACTOR = PartyRef(id="reznicek-tomas@ordinace-reznicek", display="MUDr. Tomáš Řezníček", role=Role.GP)
READY_AT = datetime(2026, 10, 21, 7, 45, tzinfo=PRAGUE)


def _waiver(item: str, reason: str, at: datetime, resource_id: str) -> dict[str, Any]:
    from app.domain.pathway import Waiver
    from app.fhir.mappers.readiness import waiver_provenance

    waiver = Waiver(item, Role.KOC_PHYSICIAN, SIGNER.id, reason)
    return {**waiver_provenance(waiver, target="Task/5", signer=SIGNER, recorded=at), "id": resource_id}


def _domain_event(case: Case, event: str, actor: PartyRef, at: datetime, resource_id: str) -> dict[str, Any]:
    """The business AuditEvent exactly as the workflow writes it for this transition."""
    from app.domain import case_machine
    from app.fhir.audit import build_domain_audit_event

    ctx = case_machine.CaseContext(reason="doplnění podkladů")
    audit = case_machine.transition(case, event, actor.role, ctx, at).events[0]
    return {**build_domain_audit_event(audit, actor=actor, entities=["Task/5"]), "id": resource_id}


def _audited_read(at: datetime) -> dict[str, Any]:
    from app.fhir.audit import build_audit_event

    return {**build_audit_event(action="R", subtype="read", actor=SIGNER, entities=["Task/5"], recorded=at), "id": "70"}


async def test_case_detail_reads_back_the_waivers_in_force(reader: CaseReader, iris: respx.MockRouter) -> None:
    iris.get("/Task").respond(200, json=_bundle(TASK))
    iris.get("/DocumentReference").respond(200, json=_bundle(DOCUMENT))
    other = {"resourceType": "Provenance", "id": "60", "target": [{"reference": "Task/5"}], "recorded": "2026-10-19"}
    reopen_at = datetime(2026, 10, 20, 16, 0, tzinfo=PRAGUE)
    provenance = iris.get("/Provenance").respond(
        200,
        json=_bundle(
            _waiver("comorbidities", "Před znovuotevřením.", datetime(2026, 10, 20, 15, 0, tzinfo=PRAGUE), "61"),
            _waiver("performance_status", "PS doplní lékař osobně na MDT.", READY_AT, "62"),
            other,
        ),
    )
    reopened = CASE.model_copy(update={"state": CaseState.PRIPRAVENO_MDT})
    audit_search = iris.get("/AuditEvent").respond(
        200, json=_bundle(_domain_event(reopened, "reopen", SIGNER, reopen_at, "71"), _audited_read(READY_AT))
    )

    view = await reader.get_case("rakathon-2026-prochazkova")

    [waiver] = view.readiness_waivers  # the comorbidities waiver was recorded before the reopen
    assert (waiver.item, waiver.reason) == ("performance_status", "PS doplní lékař osobně na MDT.")
    assert (waiver.by_id, waiver.by_display) == (SIGNER.id, SIGNER.display)
    assert waiver.at == READY_AT
    assert view.extras.gp_opened_at is None  # pripraveno_mdt: no GP opening can exist yet
    assert provenance.calls[0].request.url.params["target"] == "Task/5"
    params = audit_search.calls[0].request.url.params
    assert params["entity"] == "Task/5"
    assert params["subtype"].endswith("audit-event-code|reopen")
    audit = json.loads(iris.routes[2].calls[0].request.content)
    # every waiver read is audited, also the one no longer in force
    assert {"Provenance/61", "Provenance/62"} <= {e["what"]["reference"] for e in audit["entity"]}


async def test_a_case_not_ready_for_the_mdt_reads_no_waivers(reader: CaseReader, iris: respx.MockRouter) -> None:
    complete = {
        **TASK,
        **case_task_to_fhir(
            CASE.model_copy(update={"state": CaseState.KOMPLETNI}),
            episode_reference="EpisodeOfCare/4",
            patient_reference="Patient/3",
            requester_reference="PractitionerRole/1",
            owner_reference="PractitionerRole/2",
        ),
        "id": "5",
    }
    iris.get("/Task").respond(200, json=_bundle(complete))
    iris.get("/DocumentReference").respond(200, json=_bundle())
    provenance = iris.get("/Provenance").respond(200, json=_bundle(_waiver("histology", "x", READY_AT, "61")))
    audit_search = iris.get("/AuditEvent").respond(200, json=_bundle())

    view = await reader.get_case("rakathon-2026-prochazkova")

    assert view.readiness_waivers == ()
    assert view.extras.gp_opened_at is None
    assert provenance.call_count == 0
    assert audit_search.call_count == 0


async def test_gp_opened_at_is_the_first_audited_gp_opened_event(reader: CaseReader, iris: respx.MockRouter) -> None:
    sent = CASE.model_copy(update={"state": CaseState.ZPETNA_VAZBA_ODESLANA})
    task = {
        **case_task_to_fhir(
            sent,
            episode_reference="EpisodeOfCare/4",
            patient_reference="Patient/3",
            requester_reference="PractitionerRole/1",
            owner_reference="PractitionerRole/2",
        ),
        "id": "5",
    }
    first = datetime(2026, 10, 22, 9, 15, 30, 250000, tzinfo=PRAGUE)
    iris.get("/Task").respond(200, json=_bundle(task))
    iris.get("/DocumentReference", params={"_summary": "count"}).respond(200, json=_bundle(total=13))
    audit_search = iris.get("/AuditEvent").respond(
        200,
        json=_bundle(
            _domain_event(sent, "gp_opened", GP_ACTOR, datetime(2026, 10, 23, 10, 0, tzinfo=PRAGUE), "72"),
            _domain_event(sent, "gp_opened", GP_ACTOR, first, "73"),
            _audited_read(datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)),  # a read naming the Task is not an opening
        ),
    )
    provenance = iris.get("/Provenance").respond(200, json=_bundle())

    [overview] = await reader.list_cases()

    assert overview.extras.gp_opened_at == first
    params = audit_search.calls[0].request.url.params
    assert params["subtype"] == "https://stafeta.example/fhir/CodeSystem/audit-event-code|gp_opened"
    assert provenance.call_count == 0  # the list never reads waivers


async def test_the_list_does_not_search_audit_events_before_the_feedback_is_sent(
    reader: CaseReader, iris: respx.MockRouter
) -> None:
    iris.get("/Task").respond(200, json=_bundle(TASK))
    iris.get("/DocumentReference", params={"_summary": "count"}).respond(200, json=_bundle(total=13))
    audit_search = iris.get("/AuditEvent").respond(200, json=_bundle())

    [overview] = await reader.list_cases()

    assert overview.extras.gp_opened_at is None
    assert audit_search.call_count == 0


async def test_under_a_standing_demo_clock_the_server_write_time_decides(
    reader: CaseReader, iris: respx.MockRouter
) -> None:
    """The demo clock stands still, so every business time is equal; IRIS's meta.lastUpdated still orders writes."""
    iris.get("/Task").respond(200, json=_bundle(TASK))
    iris.get("/DocumentReference").respond(200, json=_bundle())
    before = _waiver("comorbidities", "Před znovuotevřením.", READY_AT, "61")
    before["meta"] = {"lastUpdated": "2026-10-17T09:00:00.100Z"}
    after = _waiver("performance_status", "PS doplní lékař osobně na MDT.", READY_AT, "62")
    after["meta"] = {"lastUpdated": "2026-10-17T09:10:00.100Z"}
    reopen = _domain_event(CASE, "reopen", SIGNER, READY_AT, "71")
    reopen["meta"] = {"lastUpdated": "2026-10-17T09:05:00.000Z"}
    iris.get("/Provenance").respond(200, json=_bundle(after, before))
    iris.get("/AuditEvent").respond(200, json=_bundle(reopen))

    view = await reader.get_case("rakathon-2026-prochazkova")

    assert [w.item for w in view.readiness_waivers] == ["performance_status"]


async def test_outside_the_koc_team_no_waiver_is_read(fhir_client: FhirClient, iris: respx.MockRouter) -> None:
    gp_reader = CaseReader(FhirRepository(fhir_client, GP_ACTOR, clock=lambda: datetime(2026, 10, 16, tzinfo=UTC)))
    iris.get("/Task").respond(200, json=_bundle(TASK))
    iris.get("/DocumentReference").respond(200, json=_bundle())
    provenance = iris.get("/Provenance").respond(200, json=_bundle(_waiver("histology", "x", READY_AT, "61")))

    view = await gp_reader.get_case("rakathon-2026-prochazkova")

    assert view.readiness_waivers == ()
    assert provenance.call_count == 0
