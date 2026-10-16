from __future__ import annotations

import base64
from datetime import date, datetime

import pytest

from app.domain.case import Case, CaseState
from app.domain.common import PartyRef, Role
from app.domain.document import SourceDocument
from app.domain.patient import Address, ContactPerson, Patient, Sex
from app.fhir.audit import build_audit_event
from app.fhir.mappers.case import case_from_fhir, case_task_to_fhir, episode_of_care_to_fhir
from app.fhir.mappers.directory import practitioner_to_fhir
from app.fhir.mappers.document import document_from_fhir, document_to_fhir
from app.fhir.mappers.patient import (
    coverage_to_fhir,
    format_rc,
    insurer_code_from_coverage,
    patient_from_fhir,
    patient_to_fhir,
    related_person_to_fhir,
)
from app.fhir.systems import CS_CASE_STATE, CZ_RODNE_CISLO, V3_ROLE_CODE
from app.seed.demo_case import PEOPLE
from app.settings import PRAGUE

PATIENT = Patient(
    given="Alena",
    family="Procházková",
    sex=Sex.FEMALE,
    birth_date=date(1963, 7, 22),
    birth_number="635722/1013",
    insurer_code="211",
    phone="+420 777 000 541",
    address=Address(line="Za Školou 17", postal_code="252 41", city="Dolní Břežany"),
)


def test_patient_round_trip() -> None:
    resource = patient_to_fhir(PATIENT, general_practitioner="PractitionerRole/4")

    assert resource["identifier"] == [{"use": "official", "system": CZ_RODNE_CISLO, "value": "6357221013"}]
    assert resource["gender"] == "female"
    assert resource["birthDate"] == "1963-07-22"
    assert resource["address"][0]["text"] == "Za Školou 17, 252 41 Dolní Břežany"
    assert resource["generalPractitioner"] == [{"reference": "PractitionerRole/4"}]
    assert all(t["system"] != "email" for t in resource["telecom"])  # not stated in the documents (golden M3)
    assert patient_from_fhir(resource, insurer_code="211") == PATIENT


def test_patient_from_fhir_requires_birth_number() -> None:
    resource = patient_to_fhir(PATIENT)
    resource["identifier"] = []
    with pytest.raises(ValueError, match="rodné číslo"):
        patient_from_fhir(resource)


@pytest.mark.parametrize(("value", "expected"), [("6357221013", "635722/1013"), ("635722/1013", "635722/1013")])
def test_format_rc(value: str, expected: str) -> None:
    assert format_rc(value) == expected


def test_related_person_and_coverage() -> None:
    daughter = related_person_to_fhir(
        ContactPerson(name="Petra Horká", relation="dcera", phone="+420 777 000 542"),
        patient_reference="Patient/3",
        patient=PATIENT,
    )
    assert daughter["relationship"][0]["coding"] == [{"system": V3_ROLE_CODE, "code": "DAU"}]
    assert daughter["name"] == [{"family": "Horká", "given": ["Petra"]}]

    coverage = coverage_to_fhir(patient=PATIENT, patient_reference="Patient/3", payor_reference="Organization/8")
    assert coverage["beneficiary"] == {"reference": "Patient/3"}
    assert insurer_code_from_coverage(coverage) == "211"


def test_case_round_trip_through_coordinating_task() -> None:
    holder = PartyRef(id="hruby-pavel@koc2-nemocnice-lipova", display="MDT GIT", role=Role.KOC_PHYSICIAN)
    case = Case(
        id="rakathon-2026-prochazkova",
        patient=PATIENT,
        state=CaseState.PRIPRAVENO_MDT,
        baton_holder=holder,
        next_deadline=datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE),
        opened_at=datetime(2026, 10, 2, 9, 30, tzinfo=PRAGUE),
    )

    task = case_task_to_fhir(
        case,
        episode_reference="EpisodeOfCare/5",
        patient_reference="Patient/3",
        requester_reference="PractitionerRole/1",
        owner_reference="PractitionerRole/2",
    )

    assert task["businessStatus"]["coding"][0]["system"] == CS_CASE_STATE
    assert task["owner"]["reference"] == "PractitionerRole/2"
    assert task["restriction"]["period"]["end"] == "2026-10-21T08:00:00+02:00"
    assert case_from_fhir(task, PATIENT) == case


def test_episode_of_care_has_care_manager_and_period() -> None:
    case = Case(id="c-1", patient=PATIENT, state=CaseState.ODESLANO, opened_at=datetime(2026, 10, 2, tzinfo=PRAGUE))
    coordinator = PartyRef(id="dvorakova-lucie@koc2", display="Bc. Lucie Dvořáková", role=Role.COORDINATOR)

    episode = episode_of_care_to_fhir(
        case,
        patient_reference="Patient/3",
        managing_organization_reference="Organization/1",
        care_manager=(coordinator, "PractitionerRole/9"),
    )

    assert episode["status"] == "active"
    assert episode["careManager"]["reference"] == "PractitionerRole/9"
    assert episode["period"] == {"start": "2026-10-02T00:00:00+02:00"}


def test_document_round_trip_keeps_received_and_authored_apart() -> None:
    document = SourceDocument(
        doc_id="11_Histologie_KOC2_2026-10-19",
        title="Histologie",
        type_code="11526-1",
        authored_at=date(2026, 10, 19),
        received_at=datetime(2026, 10, 19, 16, 0, tzinfo=PRAGUE),
        custodian="KOC 2",
        author="MUDr. Radek Pokorný, Ph.D.",
        file_name="11_Histologie_KOC2_2026-10-19.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    resource = document_to_fhir(
        document,
        b"docx-bytes",
        patient_reference="Patient/3",
        episode_reference="EpisodeOfCare/5",
        custodian_reference="Organization/2",
        author_reference="PractitionerRole/7",
    )

    attachment = resource["content"][0]["attachment"]
    assert resource["date"] == "2026-10-19T16:00:00+02:00"
    assert attachment["creation"] == "2026-10-19"
    assert base64.b64decode(attachment["data"]) == b"docx-bytes"
    assert attachment["size"] == len(b"docx-bytes")
    assert resource["context"] == {"encounter": [{"reference": "EpisodeOfCare/5"}]}
    assert document_from_fhir(resource) == document


def test_practitioner_display_name_with_titles() -> None:
    hruby = next(p for p in PEOPLE if p.practitioner.id == "hruby-pavel")
    resource = practitioner_to_fhir(hruby.practitioner)

    assert resource["name"][0]["text"] == "doc. MUDr. Pavel Hrubý, Ph.D."
    assert resource["name"][0]["prefix"] == ["doc.", "MUDr."]


def test_audit_event_requires_aware_time() -> None:
    actor = PartyRef(id="system", display="system", role=Role.SYSTEM)
    with pytest.raises(ValueError, match="timezone-aware"):
        build_audit_event(
            action="R",
            subtype="read",
            actor=actor,
            entities=["Patient/1"],
            recorded=datetime(2026, 10, 16),  # noqa: DTZ001 - naive on purpose
        )


def test_related_person_without_known_relation_or_given_name_has_no_empty_arrays() -> None:
    resource = related_person_to_fhir(
        ContactPerson(name="Horká", relation="sousedka"), patient_reference="Patient/3", patient=PATIENT
    )

    assert resource["relationship"] == [{"text": "sousedka"}]
    assert resource["name"] == [{"text": "Horká"}]
    assert "telecom" not in resource


def test_audit_event_identifies_people_by_practitioner_role() -> None:
    nurse = PartyRef(id="dvorakova-lucie@koc2-nemocnice-lipova", display="Bc. Lucie Dvořáková", role=Role.COORDINATOR)
    event = build_audit_event(
        action="R", subtype="read", actor=nurse, entities=[], recorded=datetime(2026, 10, 16, tzinfo=PRAGUE)
    )

    assert event["agent"][0]["who"]["identifier"]["system"] == "https://stafeta.example/fhir/sid/practitioner-role"
    assert "entity" not in event
