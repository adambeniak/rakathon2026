"""Evidence-locked facts (ADR-0002): every value points to a verbatim quote in a source document."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field, JsonValue, model_validator

from app.domain.common import BUSINESS_ID_PATTERN, DomainModel


class Evidence(DomainModel):
    """A verbatim (whitespace-normalised) quote from a source document.

    The golden file (`data/golden`) names the document key `doc`; the API and code use `doc_id`.
    """

    doc_id: str = Field(pattern=BUSINESS_ID_PATTERN, description="File stem of the source document.")
    quote: str = Field(min_length=1, description="Must occur verbatim in the normalised document text.")
    char_start: int | None = Field(None, ge=0, description="Offset of the quote in the normalised text.")
    char_end: int | None = Field(None, ge=0)

    @model_validator(mode="after")
    def _offsets_ordered(self) -> Evidence:
        if self.char_start is not None and self.char_end is not None and self.char_end < self.char_start:
            raise ValueError("char_end must not be before char_start")
        return self


class Certainty(StrEnum):
    STATED = "stated"
    SUSPECTED = "suspected"
    NEGATED = "negated"
    PLANNED = "planned"


class FactType(StrEnum):
    PATIENT_IDENTITY = "patient_identity"
    CONTACT = "contact"
    INSURER = "insurer"
    DIAGNOSIS = "diagnosis"
    COMORBIDITY = "comorbidity"
    MEDICATION = "medication"
    ALLERGY = "allergy"
    PERFORMANCE_STATUS = "performance_status"
    VITAL_SIGN = "vital_sign"
    SYMPTOM = "symptom"
    EXAMINATION = "examination"
    LAB_RESULT = "lab_result"
    HISTOLOGY = "histology"
    PROCEDURE = "procedure"
    CONSENT_OR_WISH = "consent_or_wish"
    RECOMMENDATION_OR_PLAN = "recommendation_or_plan"
    REFERRAL_REQUEST = "referral_request"
    ADMIN_DATE = "admin_date"


class Fact(DomainModel):
    """One extracted statement. P2 may refine `value` typing per `type` in `app.extraction`."""

    id: str = Field(description="Stable fact id used in citations, e.g. 'F12'.")
    doc_id: str = Field(pattern=BUSINESS_ID_PATTERN)
    type: FactType
    handover_field: int = Field(ge=1, le=15, description="Target section of the 15-field handover.")
    value: JsonValue
    unit: str | None = None
    clinical_date: date | None = None
    certainty: Certainty
    evidence: list[Evidence] = Field(min_length=1)
