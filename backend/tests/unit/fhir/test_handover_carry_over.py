"""Carry-over of the physician's decisions between handover snapshots of a case (#122, pure mapping)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.domain.handover import Handover, ReviewState, SectionReview
from app.extraction.handover.review import field_of
from app.fhir.mappers.handover import (
    carried_reviews,
    handover_bundle,
    section_keys,
    stored_review,
    with_section_review,
)
from app.fhir.systems import CS_HANDOVER_STATUS, EXT_HANDOVER_CONFLICTS, EXT_HANDOVER_FIELD_STATUS
from app.settings import PRAGUE
from tests.unit.fhir.test_handover_mapper import CTX, PHYSICIAN, handover

STEP3 = datetime(2026, 10, 20, 14, 0, tzinfo=PRAGUE)
AT = datetime(2026, 10, 20, 14, 30, tzinfo=PRAGUE)


def _snapshot(h: Handover, fhir_id: str, as_of: datetime = STEP3) -> dict[str, Any]:
    """A stored Composition of the same case at another as_of (no review yet)."""
    earlier = h.model_copy(update={"as_of": as_of})
    return {**handover_bundle(earlier, CTX)["entry"][0]["resource"], "id": fhir_id, "meta": {"versionId": "1"}}


def _confirm(
    composition: dict[str, Any], h: Handover, key: str, at: datetime = AT, value_hash: str | None = None
) -> dict[str, Any]:
    review = SectionReview(
        state=ReviewState.CONFIRMED,
        by=PHYSICIAN,
        at=at,
        value_hash=value_hash if value_hash is not None else field_of(h, key).value_hash,
    )
    return with_section_review(composition, key, review, None)


def test_identical_section_is_carried_with_its_physician_and_time() -> None:
    h = handover()
    snapshot = _confirm(_snapshot(h, "50"), h, "8_allergies")

    carried = carried_reviews(h, [snapshot])

    assert [(c.key, c.by, c.at, c.source) for c in carried] == [
        ("8_allergies", PHYSICIAN, AT, "Composition/50/_history/1")
    ]


def test_changed_section_stays_a_draft() -> None:
    h = handover()
    snapshot = _confirm(_snapshot(h, "50"), h, "8_allergies", value_hash="sha-of-the-step-3-content")

    assert carried_reviews(h, [snapshot]) == []


def test_latest_decision_counts_even_when_it_no_longer_matches() -> None:
    h = handover()
    older = _confirm(_snapshot(h, "50"), h, "8_allergies", at=AT)
    newer = _confirm(
        _snapshot(h, "51", STEP3 + timedelta(hours=1)), h, "8_allergies", at=AT + timedelta(hours=1), value_hash="x"
    )

    assert carried_reviews(h, [older, newer]) == []


def test_own_snapshot_other_cases_and_other_compositions_are_ignored() -> None:
    h = handover()
    own = _confirm(_snapshot(h, "50", h.as_of), h, "8_allergies")
    other_case = _confirm(_snapshot(h.model_copy(update={"case_id": "case-10"}), "51"), h, "8_allergies")
    mdt_record = {**_confirm(_snapshot(h, "52"), h, "8_allergies"), "identifier": {"system": "x", "value": "case-1@y"}}

    assert carried_reviews(h, [own, other_case, mdt_record]) == []


def test_bundle_applies_carried_reviews_with_a_carry_over_provenance() -> None:
    h = handover()
    snapshot = _confirm(_snapshot(h, "50"), h, "8_allergies")

    bundle = handover_bundle(h, CTX, carried_reviews(h, [snapshot]))

    composition = bundle["entry"][0]["resource"]
    review = stored_review({**composition, "id": "new"}).sections["8_allergies"]
    assert (review.state, review.by, review.at) == (ReviewState.CONFIRMED, PHYSICIAN, AT)
    assert composition["status"] == "preliminary"
    provenance = [
        e["resource"]
        for e in bundle["entry"]
        if e["resource"]["resourceType"] == "Provenance"
        and e["resource"]["activity"]["coding"][0]["code"] == "carry-over"
    ]
    assert len(provenance) == 1
    assert provenance[0]["target"] == [{"reference": bundle["entry"][0]["fullUrl"]}]
    # nobody confirmed anything now: the Device is the only agent, the physician made the source decision
    assert [a["who"]["identifier"]["value"] for a in provenance[0]["agent"]] == ["stafeta-handover-ai"]
    source = provenance[0]["entity"][0]
    assert (source["role"], source["what"]) == ("source", {"reference": "Composition/50/_history/1"})
    assert source["agent"][0]["who"]["identifier"]["value"] == PHYSICIAN.id
    assert source["agent"][0]["type"]["coding"][0]["code"] == "verifier"


def test_all_sections_carried_make_a_final_composition_attested_by_the_latest_decision() -> None:
    h = handover()
    snapshot = _snapshot(h, "50")
    last = AT
    for i, key in enumerate(section_keys()):
        last = AT + timedelta(minutes=i)
        if field_of(h, key).status == "missing":
            review = SectionReview(
                state=ReviewState.ACCEPTED_MISSING, by=PHYSICIAN, at=last, value_hash=field_of(h, key).value_hash
            )
            snapshot = with_section_review(snapshot, key, review, None)
        else:
            snapshot = _confirm(snapshot, h, key, at=last)
    edited = with_section_review(
        snapshot,
        "8_allergies",
        SectionReview(
            state=ReviewState.CONFIRMED,
            by=PHYSICIAN,
            at=last + timedelta(minutes=1),
            edited=True,
            value_hash=field_of(h, "8_allergies").value_hash,
        ),
        "neguje",
    )

    composition = handover_bundle(h, CTX, carried_reviews(h, [edited]))["entry"][0]["resource"]

    assert composition["status"] == "final"
    assert composition["attester"][0]["time"] == (last + timedelta(minutes=1)).isoformat(timespec="seconds")
    assert stored_review({**composition, "id": "new"}).edited_values == {"8_allergies": "neguje"}


def _with_section_extension(composition: dict[str, Any], key: str, url: str, part: dict[str, Any] | None) -> None:
    """Replace (or with None remove) one extension of a section in place."""
    for section in composition["section"]:
        if section["code"]["coding"][0]["code"] == key:
            kept = [e for e in section["extension"] if e["url"] != url]
            section["extension"] = kept + ([{"url": url, **part}] if part else [])


def test_same_value_but_another_status_stays_a_draft() -> None:
    """Clinical safety: the value is the same but the section turned `stale`; the confirmation does not cover it."""
    h = handover()
    snapshot = _confirm(_snapshot(h, "50"), h, "8_allergies")
    _with_section_extension(
        snapshot,
        "8_allergies",
        EXT_HANDOVER_FIELD_STATUS,
        {"valueCoding": {"system": CS_HANDOVER_STATUS, "code": "stale"}},
    )

    assert carried_reviews(h, [snapshot]) == []


def test_same_value_but_another_conflict_stays_a_draft() -> None:
    h = handover()
    snapshot = _confirm(_snapshot(h, "50"), h, "8_allergies")
    _with_section_extension(snapshot, "8_allergies", EXT_HANDOVER_CONFLICTS, {"valueString": '["C1"]'})

    assert carried_reviews(h, [snapshot]) == []


def test_snapshot_without_stored_conflicts_is_not_comparable() -> None:
    h = handover()
    snapshot = _confirm(_snapshot(h, "50"), h, "8_allergies")
    _with_section_extension(snapshot, "8_allergies", EXT_HANDOVER_CONFLICTS, None)

    assert carried_reviews(h, [snapshot]) == []
