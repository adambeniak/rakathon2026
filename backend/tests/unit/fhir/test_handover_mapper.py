"""Handover <-> Composition/Provenance mapping (pure, no I/O)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from app.domain.common import PartyRef, Role
from app.domain.handover import Handover, HandoverItem, ReviewState, SectionReview
from app.extraction.handover.assemble import assemble_handover
from app.fhir.mappers.handover import (
    FhirContext,
    confirmation_provenance,
    handover_bundle,
    handover_business_id,
    section_keys,
    stored_review,
    with_section_review,
)
from app.fhir.systems import (
    CS_HANDOVER_SECTION,
    EXT_EVIDENCE_QUOTE,
    EXT_HANDOVER_FIELD_STATUS,
    LIST_EMPTY_REASON,
    LOINC,
    SID_HANDOVER,
)
from app.settings import PRAGUE
from tests.unit.extraction.test_handover_assembly import (
    AS_OF,
    CARDIO,
    DOCS,
    GASTRO,
    LAB,
    PATHOLOGY,
    REFERRAL,
    coded,
    fact,
    med,
    qty,
    text,
)

RECORDED = datetime(2026, 10, 21, 8, 5, tzinfo=PRAGUE)
CTX = FhirContext(
    patient="Patient/1",
    episode="EpisodeOfCare/2",
    documents={d: f"DocumentReference/{i}" for i, d in enumerate(DOCS, start=10)},
    device_display="Štafeta AI · test",
    recorded=RECORDED,
)
PHYSICIAN = PartyRef(id="markova-lenka@koc2-nemocnice-lipova", display="MUDr. Lenka Marková", role=Role.KOC_PHYSICIAN)


def handover() -> Handover:
    facts = [
        fact(REFERRAL, "diagnosis", 3, coded("C25.0", "MKN-10", "suspektní tumor"), certainty="suspected"),
        fact(PATHOLOGY, "diagnosis", 3, coded("8500/3", "MKN-O", "Duktální adenokarcinom pankreatu")),
        fact(CARDIO, "comorbidity", 6, coded("I10", "MKN-10", "Arteriální hypertenze")),
        fact(REFERRAL, "medication", 7, med("apixaban", "5 mg", "1-0-1")),
        fact(CARDIO, "vital_sign", 10, qty("hmotnost", 69), unit="kg"),
        fact(GASTRO, "vital_sign", 10, qty("Výška", 165), unit="cm"),
        fact(LAB, "lab_result", 13, qty("CA 19-9", 312, "H"), unit="kU/l", clinical_date=date(2026, 10, 15)),
        fact(REFERRAL, "allergy", 8, text("AA: neguje"), quote="AA: neguje"),
    ]
    return assemble_handover("case-1", AS_OF, facts, DOCS)


def _walk(node: Any) -> list[Any]:
    out = [node]
    if isinstance(node, dict):
        for v in node.values():
            out += _walk(v)
    elif isinstance(node, list):
        for v in node:
            out += _walk(v)
    return out


def _composition(bundle: dict[str, Any]) -> dict[str, Any]:
    resource: dict[str, Any] = bundle["entry"][0]["resource"]
    return resource


def test_business_id_is_utc_without_plus() -> None:
    assert handover_business_id("case-1", AS_OF) == "case-1@20261021T0600Z"


def test_bundle_composition_sections_and_conditional_create() -> None:
    bundle = handover_bundle(handover(), CTX)
    assert bundle["type"] == "transaction"
    first = bundle["entry"][0]
    assert first["request"]["ifNoneExist"] == "identifier=" + quote(f"{SID_HANDOVER}|case-1@20261021T0600Z", safe="")
    # entry identifiers contain '#': unencoded it would start a URL fragment and match a truncated value
    assert all("#" not in e["request"].get("ifNoneExist", "") for e in bundle["entry"])
    composition = _composition(bundle)
    assert composition["status"] == "preliminary"
    sections = composition["section"]
    codes = [s["code"]["coding"][0] for s in sections]
    assert [c["code"] for c in codes] == section_keys()
    assert all(c["system"] == CS_HANDOVER_SECTION for c in codes)
    by_key = {s["code"]["coding"][0]["code"]: s for s in sections}
    ps = by_key["9_performance_status"]
    assert ps["emptyReason"]["coding"][0] == {"system": LIST_EMPTY_REASON, "code": "unavailable"}
    assert "entry" not in ps
    status = next(e for e in ps["extension"] if e["url"] == EXT_HANDOVER_FIELD_STATUS)
    assert status["valueCoding"]["code"] == "missing"
    assert by_key["12_examinations"]["entry"][0]["reference"].startswith("DocumentReference/")
    assert all(s["text"]["div"].startswith('<div xmlns="http://www.w3.org/1999/xhtml">') for s in sections)


def test_derived_resources_have_provenance_with_quotes() -> None:
    bundle = handover_bundle(handover(), CTX)
    entries = bundle["entry"]
    kinds = [e["resource"]["resourceType"] for e in entries]
    assert kinds.count("Condition") == 2  # diagnosis + one comorbidity
    assert kinds.count("MedicationStatement") == 1
    weight = next(
        e["resource"]
        for e in entries
        if e["resource"]["resourceType"] == "Observation" and e["resource"]["code"].get("text") == "Hmotnost"
    )
    assert weight["code"]["coding"][0] == {"system": LOINC, "code": "29463-7", "display": "Body weight"}
    diagnosis = next(e["resource"] for e in entries if e["resource"]["resourceType"] == "Condition")
    assert diagnosis["verificationStatus"]["coding"][0]["code"] == "confirmed"
    # every derived resource is followed by its Provenance, citing the DocumentReference and the verbatim quote
    for i, entry in enumerate(entries[2:]):
        if entry["resource"]["resourceType"] in ("Condition", "MedicationStatement", "Observation"):
            provenance = entries[2 + i + 1]["resource"]
            assert provenance["resourceType"] == "Provenance"
            assert provenance["target"] == [{"reference": entry["fullUrl"]}]
            entity = provenance["entity"][0]
            assert entity["what"]["reference"].startswith("DocumentReference/")
            quote = entity["extension"][0]
            assert quote["url"] == EXT_EVIDENCE_QUOTE
            assert quote["extension"][0]["url"] == "quote"


def test_no_empty_arrays_or_strings() -> None:
    for node in _walk(handover_bundle(handover(), CTX)):
        assert node != []
        assert node != ""


def test_review_round_trip_and_final_after_all_sections() -> None:
    composition = {**_composition(handover_bundle(handover(), CTX)), "id": "77"}
    stored = stored_review(composition)
    assert (stored.fhir_id, stored.status) == ("77", "preliminary")
    assert all(r.state == ReviewState.DRAFT for r in stored.sections.values())

    at = datetime(2026, 10, 21, 9, 0, tzinfo=PRAGUE)
    confirmed = SectionReview(state=ReviewState.CONFIRMED, by=PHYSICIAN, at=at)
    updated = with_section_review(composition, "8_allergies", confirmed, None)
    assert stored_review(updated).sections["8_allergies"] == confirmed
    assert updated["status"] == "preliminary"
    assert stored_review(composition).sections["8_allergies"].state == ReviewState.DRAFT  # input not mutated

    for key in section_keys():
        state = ReviewState.ACCEPTED_MISSING if key == "9_performance_status" else ReviewState.CONFIRMED
        edited = {"scale": "ECOG", "value": "1"} if key == "9_performance_status" else None
        review = SectionReview(state=state, by=PHYSICIAN, at=at, edited=edited is not None)
        updated = with_section_review(updated, key, review, edited)
    final = stored_review(updated)
    assert final.status == "final"
    assert updated["attester"][0]["party"]["identifier"]["value"] == PHYSICIAN.id
    assert final.edited_values == {"9_performance_status": {"scale": "ECOG", "value": "1"}}


def test_confirmation_provenance_records_who_and_previous_value() -> None:
    at = datetime(2026, 10, 21, 9, 0, tzinfo=PRAGUE)
    review = SectionReview(state=ReviewState.CONFIRMED, by=PHYSICIAN, at=at, edited=True)
    provenance = confirmation_provenance("Composition/77", "8_allergies", review, "abc", edited=True)
    assert provenance["activity"]["coding"][0]["code"] == "edit"
    assert provenance["agent"][0]["who"]["identifier"]["value"] == PHYSICIAN.id
    assert {"url": "https://stafeta.example/fhir/StructureDefinition/previous-value-sha256", "valueString": "abc"} in (
        provenance["extension"]
    )


def _observation_for(item: HandoverItem, key: str = "10_weight_height") -> dict[str, Any]:
    from app.fhir.mappers.handover import _observation

    return _observation(key, "case-1@x#k.0", item, None, CTX)


def test_vital_sign_needs_numeric_value_and_date_else_exam() -> None:
    dated = _observation_for(HandoverItem(label="Hmotnost", value=65.0, unit="kg", clinical_date=date(2026, 9, 15)))
    assert dated["category"][0]["coding"][0]["code"] == "vital-signs"
    assert dated["valueQuantity"]["value"] == 65.0
    assert "effectiveDateTime" in dated

    undated = _observation_for(HandoverItem(label="Hmotnost", value=65.0, unit="kg"))
    assert undated["category"][0]["coding"][0]["code"] == "exam"
    assert "coding" not in undated["code"]  # no vital-signs LOINC without effective[x]

    text = _observation_for(HandoverItem(label="Hmotnost", value="65 kg", clinical_date=date(2026, 9, 15)))
    assert text["valueString"] == "65 kg"
    assert "valueQuantity" not in text


def test_unlabelled_item_is_named_by_its_section() -> None:
    observation = _observation_for(HandoverItem(value=1.0), key="13_labs")
    assert observation["code"]["text"] == "Laboratoř vč. onkomarkerů"
