from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.common import PartyRef, Role
from app.fhir.mappers.feedback import SID_FEEDBACK, SID_MESSAGE_ID, feedback_communication_to_fhir
from app.fhir.mappers.mdt_conclusion import (
    SID_MDT_CONCLUSION,
    is_conclusion_of,
    latest_conclusion,
    mdt_conclusion_from_fhir,
    mdt_conclusion_provenance,
    mdt_conclusion_to_fhir,
)
from app.fhir.systems import EXT_HANDOVER_EPISODE, SID_PRACTITIONER_ROLE
from app.settings import PRAGUE

SIGNED_AT = datetime(2026, 10, 21, 9, 30, tzinfo=PRAGUE)
SIGNER = PartyRef(id="markova-lenka@koc2-nemocnice-lipova", display="MUDr. Lenka Marková", role=Role.KOC_PHYSICIAN)
COORDINATOR = PartyRef(id="dvorakova-lucie@koc2-nemocnice-lipova", display="Bc. Lucie Dvořáková", role=Role.COORDINATOR)
TEXT = "Závěr: <b>doporučeno</b> & dále dle zápisu.\nDruhý řádek."


def _stored() -> dict[str, object]:
    resource = mdt_conclusion_to_fhir(
        "c1",
        TEXT,
        patient_reference="Patient/2",
        episode_reference="EpisodeOfCare/1",
        signer=SIGNER,
        signed_at=SIGNED_AT,
    )
    return {**resource, "id": "77"}


def test_conclusion_composition_is_final_signed_and_linked_to_the_case() -> None:
    resource = _stored()

    assert resource["status"] == "final"
    assert resource["subject"] == {"reference": "Patient/2"}
    assert "encounter" not in resource  # Composition.encounter allows Encounter only; the case is an extension
    assert resource["extension"] == [  # type: ignore[comparison-overlap]
        {"url": EXT_HANDOVER_EPISODE, "valueReference": {"reference": "EpisodeOfCare/1"}}
    ]
    assert resource["identifier"]["system"] == SID_MDT_CONCLUSION  # type: ignore[index]
    author = resource["author"][0]  # type: ignore[index]
    assert author == {
        "type": "PractitionerRole",
        "identifier": {"system": SID_PRACTITIONER_ROLE, "value": SIGNER.id},
        "display": SIGNER.display,
    }
    [attester] = resource["attester"]  # type: ignore[misc]
    assert attester["mode"] == "professional"
    assert attester["time"] == SIGNED_AT.isoformat()


def test_an_empty_display_is_left_out_of_the_reference() -> None:
    anonymous = SIGNER.model_copy(update={"display": ""})

    resource = mdt_conclusion_to_fhir(
        "c1",
        TEXT,
        patient_reference="Patient/2",
        episode_reference="EpisodeOfCare/1",
        signer=anonymous,
        signed_at=SIGNED_AT,
    )

    assert "display" not in resource["author"][0]


def test_text_round_trips_exactly_and_the_narrative_is_escaped() -> None:
    resource = _stored()

    record = mdt_conclusion_from_fhir(resource)

    assert record.text == TEXT
    assert record.composition_id == "77"
    assert (record.signer_id, record.signer_display) == (SIGNER.id, SIGNER.display)
    assert record.signer_role is None  # not stored on the Composition: the service resolves it from the directory
    assert record.signed_at == SIGNED_AT
    div = resource["section"][0]["text"]["div"]  # type: ignore[index]
    assert "<b>" not in div
    assert "&lt;b&gt;doporučeno&lt;/b&gt; &amp; dále" in div
    assert "<br/>" in div


def test_conclusions_are_matched_by_the_exact_case_id() -> None:
    resource = _stored()

    assert is_conclusion_of(resource, "c1")
    assert not is_conclusion_of(resource, "c")
    assert not is_conclusion_of({"identifier": {"system": "other", "value": "c1@x"}}, "c1")
    nested = {"identifier": {"system": SID_MDT_CONCLUSION, "value": "foo@bar@20261021T073000000000Z"}}
    assert is_conclusion_of(nested, "foo@bar")
    assert not is_conclusion_of(nested, "foo")  # a prefix of another case's id is not this case


def test_the_latest_conclusion_is_picked_by_instant_not_by_string() -> None:
    summer = {"id": "1", "date": "2026-10-25T02:30:00+02:00"}  # 00:30 UTC
    winter = {"id": "2", "date": "2026-10-25T02:10:00+01:00"}  # 01:10 UTC: later, but sorts earlier as a string

    assert latest_conclusion([summer, winter])["id"] == "2"
    assert latest_conclusion([winter, summer])["id"] == "2"


def test_provenance_names_who_signed_what_when_and_in_which_role() -> None:
    provenance = mdt_conclusion_provenance(target="urn:uuid:abc", signer=SIGNER, recorded=SIGNED_AT)

    assert provenance["target"] == [{"reference": "urn:uuid:abc"}]
    assert provenance["recorded"] == SIGNED_AT.isoformat()
    assert provenance["activity"]["coding"][0]["code"] == "LA"
    [agent] = provenance["agent"]
    assert agent["who"]["identifier"]["value"] == SIGNER.id
    assert agent["who"]["type"] == "PractitionerRole"
    assert agent["type"]["coding"][0]["code"] == "attester"
    assert agent["role"][0]["coding"][0]["code"] == "koc_physician"


def test_feedback_communication_records_the_sent_mail_receipt_and_the_announced_conclusion() -> None:
    resource = feedback_communication_to_fhir(
        "c1",
        patient_reference="Patient/2",
        episode_reference="EpisodeOfCare/1",
        sender=COORDINATOR,
        sender_reference="PractitionerRole/3",
        recipient_reference="PractitionerRole/1",
        sent_at=SIGNED_AT,
        message_id="<m1@stafeta.example>",
        body="Dobrý den",
        conclusion_reference="Composition/77",
    )

    assert resource["status"] == "completed"
    assert resource["medium"][0]["coding"][0] == {
        "system": "http://terminology.hl7.org/CodeSystem/v3-ParticipationMode",
        "code": "EMAILWRIT",
        "display": "email",
    }
    assert {i["system"]: i["value"] for i in resource["identifier"]}[SID_MESSAGE_ID] == "<m1@stafeta.example>"
    assert resource["identifier"][0]["system"] == SID_FEEDBACK
    assert resource["recipient"] == [{"reference": "PractitionerRole/1"}]
    assert resource["about"] == [{"reference": "EpisodeOfCare/1"}, {"reference": "Composition/77"}]
    assert resource["sent"] == SIGNED_AT.isoformat()
    assert "received" not in resource  # relay acceptance is not receipt by the GP


def test_feedback_communication_without_a_conclusion_only_points_at_the_case() -> None:
    resource = feedback_communication_to_fhir(
        "c1",
        patient_reference="Patient/2",
        episode_reference="EpisodeOfCare/1",
        sender=COORDINATOR,
        sender_reference="PractitionerRole/3",
        recipient_reference="PractitionerRole/1",
        sent_at=SIGNED_AT.astimezone(timezone(timedelta(hours=0))),
        message_id="<m1@stafeta.example>",
        body="Dobrý den",
    )

    assert resource["about"] == [{"reference": "EpisodeOfCare/1"}]
