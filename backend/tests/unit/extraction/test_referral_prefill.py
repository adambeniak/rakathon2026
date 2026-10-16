"""Acceptance for the prefill of letter 07, built from the recorded LLM response (cache only, no network)."""

from __future__ import annotations

from datetime import date

import pytest

from app.documents.normalize import NormalizedDoc
from app.domain.birth_number import parse_birth_number
from app.domain.evidence import Fact
from app.domain.patient import Sex
from app.domain.referral import FieldStatus, ReferralPrefill
from app.extraction.llm import CACHE_MODEL, LLMClient
from app.extraction.pipeline import extract_facts
from app.extraction.referral_prefill import build_prefill


@pytest.fixture
async def letter_facts(docs: dict[str, NormalizedDoc]) -> tuple[NormalizedDoc, list[Fact]]:
    letter = docs["07_PL_zadost_KOC2_2026-10-02"]
    result = await extract_facts(letter, LLMClient(model=CACHE_MODEL, cache_only=True))
    return letter, list(result.accepted)


@pytest.fixture
def prefill(letter_facts: tuple[NormalizedDoc, list[Fact]]) -> ReferralPrefill:
    letter, facts = letter_facts
    return build_prefill(facts, doc_id=letter.doc_id, authored_at=letter.authored_date)


def test_identity_values_with_evidence(prefill: ReferralPrefill) -> None:
    assert (prefill.given.value, prefill.family.value) == ("Alena", "Procházková")
    assert prefill.birth_date.value == date(1963, 7, 22)
    assert prefill.age_text.value == "63 let"
    assert prefill.birth_number.value == "635722/1013"
    assert prefill.birth_number_checksum_valid is True
    assert prefill.insurer_code.value == "211"
    assert prefill.address.value is not None
    assert prefill.address.value.city == "Dolní Břežany"
    assert prefill.patient_phone.value == "+420 777 000 541"
    assert prefill.given.evidence[0].quote == "Pacientka: Alena Procházková"


def test_contact_person_diagnosis_and_gp(prefill: ReferralPrefill) -> None:
    contact = prefill.contact_person.value
    assert contact is not None
    assert (contact.name, contact.relation, contact.phone) == ("Petra Horká", "dcera", "+420 777 000 542")
    diagnosis = prefill.suspected_diagnosis.value
    assert diagnosis is not None
    assert diagnosis.code == "C25.0"
    assert "suspektní" in diagnosis.text
    assert prefill.requesting_gp.value == "MUDr. Tomáš Řezníček"


def test_consent_statements_are_quoted_verbatim_and_not_interpreted(prefill: ReferralPrefill) -> None:
    texts = [s.value for s in prefill.consent_statements]

    assert "Souhlasí se sdílením informací s dcerou." in texts
    assert all(s.evidence for s in prefill.consent_statements)


def test_sex_is_derived_from_the_rc_and_says_so(prefill: ReferralPrefill) -> None:
    assert prefill.sex.value is Sex.FEMALE
    assert prefill.sex.derived is True
    assert prefill.sex.evidence == prefill.birth_number.evidence


def test_every_present_value_has_evidence_and_every_missing_has_none(prefill: ReferralPrefill) -> None:
    fields = [
        prefill.given, prefill.family, prefill.sex, prefill.birth_date, prefill.age_text, prefill.birth_number,
        prefill.address, prefill.patient_phone, prefill.insurer_code, prefill.contact_person, prefill.requesting_gp,
        prefill.suspected_diagnosis, prefill.urgency_statement, *prefill.consent_statements,
    ]  # fmt: skip
    for field in fields:
        if field.status is FieldStatus.COMPLETE:
            assert field.value is not None
            assert field.evidence
        else:
            assert field.value is None


def test_a_letter_without_facts_is_all_missing_never_guessed() -> None:
    empty = build_prefill([], doc_id="x", authored_at=None)

    assert empty.family.status is FieldStatus.MISSING
    assert empty.sex.status is FieldStatus.MISSING
    assert empty.suspected_diagnosis.value is None
    assert empty.consent_statements == []


def test_birth_date_not_matching_the_rc_needs_clarification(letter_facts: tuple[NormalizedDoc, list[Fact]]) -> None:
    letter, facts = letter_facts
    tampered = [
        f.model_copy(update={"value": {**f.value, "date": "1964-07-22"}})
        if isinstance(f.value, dict) and f.value.get("kind") == "date"
        else f
        for f in facts
    ]

    prefill = build_prefill(tampered, doc_id=letter.doc_id, authored_at=letter.authored_date)

    assert prefill.birth_date.status is FieldStatus.NEEDS_CLARIFICATION
    assert prefill.birth_number.status is FieldStatus.NEEDS_CLARIFICATION


@pytest.mark.parametrize(
    ("rc", "sex", "born", "checksum"),
    [
        ("635722/1013", Sex.FEMALE, date(1963, 7, 22), True),
        ("6357221013", Sex.FEMALE, date(1963, 7, 22), True),
        ("850101/1236", Sex.MALE, date(1985, 1, 1), None),
        ("055101/1234", Sex.FEMALE, date(2005, 1, 1), None),
    ],
)
def test_birth_number_rules(rc: str, sex: Sex, born: date, checksum: bool | None) -> None:
    info = parse_birth_number(rc)

    assert info is not None
    assert (info.sex, info.birth_date) == (sex, born)
    if checksum is not None:
        assert info.checksum_valid is checksum


def test_not_an_rc() -> None:
    assert parse_birth_number("Za Školou 17") is None
