from __future__ import annotations

from datetime import datetime

from app.domain.common import PartyRef, Role
from app.fhir.mappers.feedback import SID_FEEDBACK, SID_MESSAGE_ID, feedback_communication_to_fhir
from app.fhir.mappers.mdt_conclusion import (
    SID_MDT_CONCLUSION,
    is_conclusion_of,
    mdt_conclusion_from_fhir,
    mdt_conclusion_provenance,
    mdt_conclusion_to_fhir,
)
from app.fhir.systems import SID_PRACTITIONER_ROLE
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
    assert resource["encounter"] == {"reference": "EpisodeOfCare/1"}
    assert resource["identifier"]["system"] == SID_MDT_CONCLUSION  # type: ignore[index]
    assert resource["author"][0]["identifier"] == {"system": SID_PRACTITIONER_ROLE, "value": SIGNER.id}  # type: ignore[index]
    [attester] = resource["attester"]  # type: ignore[misc]
    assert attester["mode"] == "professional"
    assert attester["time"] == SIGNED_AT.isoformat()


def test_text_round_trips_exactly_and_the_narrative_is_escaped() -> None:
    resource = _stored()

    record = mdt_conclusion_from_fhir(resource)

    assert record.text == TEXT
    assert record.composition_id == "77"
    assert record.signed_by == SIGNER
    assert record.signed_at == SIGNED_AT
    div = resource["section"][0]["text"]["div"]  # type: ignore[index]
    assert "<b>" not in div
    assert "&lt;b&gt;doporučeno&lt;/b&gt; &amp; dále" in div
    assert "<br/>" in div


def test_conclusions_are_matched_by_case_id_not_by_prefix() -> None:
    resource = _stored()

    assert is_conclusion_of(resource, "c1")
    assert not is_conclusion_of(resource, "c")
    assert not is_conclusion_of({"identifier": {"system": "other", "value": "c1@x"}}, "c1")


def test_provenance_names_who_signed_what_and_when() -> None:
    provenance = mdt_conclusion_provenance(target="urn:uuid:abc", signer=SIGNER, recorded=SIGNED_AT)

    assert provenance["target"] == [{"reference": "urn:uuid:abc"}]
    assert provenance["recorded"] == SIGNED_AT.isoformat()
    assert provenance["agent"][0]["who"]["identifier"]["value"] == SIGNER.id
    assert provenance["agent"][0]["type"]["coding"][0]["code"] == "attester"


def test_feedback_communication_records_the_sent_mail_and_its_receipt() -> None:
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
    )

    assert resource["status"] == "completed"
    assert resource["medium"][0]["coding"][0]["code"] == "EMAILWRIT"
    assert {i["system"]: i["value"] for i in resource["identifier"]}[SID_MESSAGE_ID] == "<m1@stafeta.example>"
    assert resource["identifier"][0]["system"] == SID_FEEDBACK
    assert resource["recipient"] == [{"reference": "PractitionerRole/1"}]
    assert resource["sent"] == SIGNED_AT.isoformat()
