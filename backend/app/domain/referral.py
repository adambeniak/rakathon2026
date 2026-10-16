"""The GP referral: the evidenced prefill read from the letter, and what the GP confirms (owner: P4).

AI output is a draft (AGENTS #5): every prefilled value carries the verbatim evidence it was read from, a value the
letter does not state is `missing` (never guessed), and a value computed by rule instead of read (sex from the RČ) is
marked `derived`. Nothing here is persisted until the GP submits the referral.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from app.domain.common import BUSINESS_ID_PATTERN, DomainModel
from app.domain.evidence import Evidence
from app.domain.patient import Address, ContactPerson, Sex


class FieldStatus(StrEnum):
    """Subset of the shared handover field status enum."""

    COMPLETE = "complete"
    MISSING = "missing"
    NEEDS_CLARIFICATION = "needs_clarification"


class Evidenced[T](DomainModel):
    value: T | None = None
    status: FieldStatus
    derived: bool = Field(False, description="Computed by rule from another value (e.g. sex from the RČ), not read.")
    note: str | None = Field(None, description="Neutral remark, e.g. 'datum narození nesouhlasí s rodným číslem'.")
    evidence: list[Evidence] = Field(default_factory=list)


class SuspectedDiagnosis(DomainModel):
    code: str | None = Field(None, description="MKN-10 code exactly as written in the letter, e.g. 'C25.0'.")
    text: str = Field(description="As written, e.g. 'suspektní tumor hlavy pankreatu'.")


class ReferralPrefill(DomainModel):
    """Draft read from the uploaded letter. The GP confirms or edits every field before sending."""

    doc_id: str = Field(pattern=BUSINESS_ID_PATTERN)
    authored_at: date | None = None
    given: Evidenced[str]
    family: Evidenced[str]
    sex: Evidenced[Sex]
    birth_date: Evidenced[date]
    age_text: Evidenced[str] = Field(description="As written in the letter, e.g. '63 let'.")
    birth_number: Evidenced[str]
    birth_number_checksum_valid: bool | None = None
    address: Evidenced[Address]
    patient_phone: Evidenced[str]
    insurer_code: Evidenced[str]
    insurer_name: str | None = Field(None, description="Directory lookup of the code, not extracted text.")
    contact_person: Evidenced[ContactPerson]
    requesting_gp: Evidenced[str] = Field(description="Name of the signing GP as written in the letter.")
    requesting_gp_role_id: str | None = Field(None, description="Directory match of the GP (PractitionerRole id).")
    suspected_diagnosis: Evidenced[SuspectedDiagnosis]
    consent_statements: list[Evidenced[str]] = Field(
        default_factory=list, description="Statements quoted verbatim; the consent checkbox is never pre-ticked."
    )
    urgency_statement: Evidenced[str]


class ReferralSubmission(DomainModel):
    """What the GP confirmed (prefilled values, possibly edited). Sent together with the letter."""

    given: str = Field(min_length=1, max_length=100)
    family: str = Field(min_length=1, max_length=100)
    sex: Sex
    birth_date: date
    birth_number: str = Field(pattern=r"^\d{6}/?\d{3,4}$")
    insurer_code: str | None = Field(None, pattern=r"^\d{3}$")
    phone: str | None = Field(None, max_length=40)
    address: Address | None = None
    contact_person: ContactPerson | None = None
    diagnosis_code: str | None = Field(None, max_length=20)
    diagnosis_text: str = Field(min_length=1, max_length=300)
    koc_id: str = Field(pattern=BUSINESS_ID_PATTERN, max_length=100)
    consent_confirmed: bool
    priority: Literal["routine", "urgent"] = Field(
        description="Confirmed by the GP. The form preselects `urgent` only when the letter asks for it "
        "(`ReferralPrefill.urgency_statement` has a quote); it is never assumed."
    )
    consent_statements: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list,
        max_length=10,
        description="Statements of the letter the GP confirmed; each must occur verbatim in the letter.",
    )
    note: str | None = Field(None, max_length=1000, description="Optional note of the GP to the KOC.")


def compare_with_prefill(prefill: ReferralPrefill, submission: ReferralSubmission) -> tuple[list[str], list[str]]:
    """Names of the fields the GP changed (`edited`) or filled in although the letter had no value (`added`)."""
    rc = prefill.birth_number.value
    diagnosis = prefill.suspected_diagnosis.value
    pairs: list[tuple[str, object, object]] = [
        ("given", prefill.given.value, submission.given),
        ("family", prefill.family.value, submission.family),
        ("sex", prefill.sex.value, submission.sex),
        ("birth_date", prefill.birth_date.value, submission.birth_date),
        ("birth_number", rc.replace("/", "") if rc else None, submission.birth_number.replace("/", "")),
        ("insurer_code", prefill.insurer_code.value, submission.insurer_code),
        ("phone", prefill.patient_phone.value, submission.phone),
        ("address", prefill.address.value, submission.address),
        ("contact_person", prefill.contact_person.value, submission.contact_person),
        ("diagnosis_text", diagnosis.text if diagnosis else None, submission.diagnosis_text),
    ]
    edited: list[str] = []
    added: list[str] = []
    for name, original, confirmed in pairs:
        if confirmed in (None, "") or confirmed == original:
            continue
        (edited if original not in (None, "") else added).append(name)
    return edited, added
