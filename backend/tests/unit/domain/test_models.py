from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.domain.evidence import Evidence
from app.domain.patient import Patient, Sex
from app.export_schemas import handover_schema


@pytest.mark.parametrize(
    ("day", "age"),
    [(date(2026, 7, 21), 62), (date(2026, 7, 22), 63), (date(2026, 10, 21), 63)],
)
def test_patient_age_on(day: date, age: int) -> None:
    patient = Patient(
        given="Alena", family="Procházková", sex=Sex.FEMALE, birth_date=date(1963, 7, 22), birth_number="635722/1013"
    )
    assert patient.age_on(day) == age


def test_evidence_requires_quote_and_ordered_offsets() -> None:
    with pytest.raises(ValidationError):
        Evidence(doc_id="07_PL_zadost_KOC2_2026-10-02", quote="")
    with pytest.raises(ValidationError):
        Evidence(doc_id="07_PL_zadost_KOC2_2026-10-02", quote="AA: neguje", char_start=10, char_end=5)
    with pytest.raises(ValidationError):
        Evidence(doc_id="../etc/passwd", quote="x")


def test_models_are_immutable() -> None:
    evidence = Evidence(doc_id="07_PL_zadost_KOC2_2026-10-02", quote="AA: neguje")
    with pytest.raises(ValidationError):
        evidence.quote = "jiný text"  # type: ignore[misc]


def test_handover_schema_uses_golden_field_keys() -> None:
    schema = handover_schema()
    fields = schema["$defs"]["HandoverFields"]["properties"]  # type: ignore[index]
    assert list(fields)[:3] == ["1_patient", "2_contacts", "3_diagnosis"]
    assert len(fields) == 15
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
