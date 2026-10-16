"""The 15-field handover (Handover_obsah) assembled for a case at an as-of timestamp.

This module is the source of `contracts/handover.schema.json` (`python -m app.export_schemas`). JSON keys of the
fields ("1_patient" … "15_other") and the status enum are shared with `data/golden/expected_handover_*.json`.
Assembly logic is P2's (F2-2); these are the shapes only.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, ConfigDict, Field

from app.domain.common import BUSINESS_ID_PATTERN, DomainModel
from app.domain.evidence import Evidence
from app.domain.finding import Finding
from app.domain.patient import Sex


class HandoverStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"
    STALE = "stale"
    NEEDS_CLARIFICATION = "needs_clarification"
    COMPLETE_WITH_CONFLICT = "complete_with_conflict"
    GENERATED_WITH_CITATIONS = "generated_with_citations"


# --- Field values (typed per field, mirroring data/golden) ---------------------------------------------------------


class PatientIdentity(DomainModel):
    given: str
    family: str
    sex: Sex
    birth_date: dt.date
    age_years: int | None = None
    birth_number: str | None = None
    birth_number_checksum_valid: bool | None = None
    insurer_code: str | None = None
    insurer_name: str | None = Field(None, description="Code-list lookup, not extracted text.")
    address: str | None = None


class ContactPerson(DomainModel):
    name: str
    relation: str
    phone: str | None = None


class Contacts(DomainModel):
    patient_phone: str | None = None
    patient_email: str | None = None
    contact_person: ContactPerson | None = None


class Diagnosis(DomainModel):
    icd10: str | None = Field(None, description="MKN-10 code, e.g. 'C25.0'.")
    text: str
    icdo3_morphology: str | None = Field(None, description="ICD-O-3 morphology, e.g. '8500/3'.")
    verified_histologically_on: dt.date | None = None
    tnm: str | None = None


class CitedSentence(DomainModel):
    text: str
    fact_ids: list[str] = Field(min_length=1)


class Epicrisis(DomainModel):
    text: str = Field(description="AI draft ('Návrh AI') until a physician confirms it.")
    sentences: list[CitedSentence] = Field(default_factory=list, description="Each sentence with its cited facts.")


class Comorbidity(DomainModel):
    text: str
    icd10: str | None = None
    detail: str | None = None


class Medication(DomainModel):
    drug: str
    dose: str | None = None
    schedule: str | None = Field(None, description="As written, e.g. '1-0-1'.")


class PerformanceStatus(DomainModel):
    scale: Literal["ECOG", "Karnofsky"]
    value: str = Field(description="As documented; never inferred (e.g. not from 'soběstačná').")


class WeightMeasurement(DomainModel):
    kg: float
    date: dt.date


class WeightHeight(DomainModel):
    height_cm: float | None = None
    height_date: dt.date | None = None
    weights: list[WeightMeasurement] = Field(default_factory=list)


class Symptoms(DomainModel):
    onset: str | None = Field(None, description="As written, e.g. 'polovina srpna 2026'.")
    items: list[str] = Field(default_factory=list)


class Examination(DomainModel):
    date: dt.date
    place: str
    type: str
    doc_id: str = Field(pattern=BUSINESS_ID_PATTERN, description="Document with the full text.")


class LabResult(DomainModel):
    test: str
    value: float
    unit: str | None = None
    flag: str | None = Field(None, description="As written in the report, e.g. 'H' or 'L'.")
    date: dt.date
    doc_id: str = Field(pattern=BUSINESS_ID_PATTERN)


class Histology(DomainModel):
    report_id: str | None = None
    issued: dt.date | None = None
    ihc: dict[str, str] = Field(default_factory=dict, description="Immunohistochemistry marker -> result as written.")
    perineural_invasion: bool | None = None
    grade: str | None = None


# --- Fields ----------------------------------------------------------------------------------------------------------


class HandoverFieldBase(DomainModel):
    status: HandoverStatus
    evidence: list[Evidence] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list, description="Sub-items not stated in the sources.")
    conflicts: list[str] = Field(default_factory=list, description="Ids of findings that contradict the value.")
    note: str | None = None


class PatientField(HandoverFieldBase):
    value: PatientIdentity | None = None


class ContactsField(HandoverFieldBase):
    value: Contacts | None = None


class DiagnosisField(HandoverFieldBase):
    value: Diagnosis | None = None


class EpicrisisField(HandoverFieldBase):
    value: Epicrisis | None = None


class TextField(HandoverFieldBase):
    value: str | None = None


class ComorbiditiesField(HandoverFieldBase):
    value: list[Comorbidity] | None = None


class MedicationsField(HandoverFieldBase):
    value: list[Medication] | None = None


class PerformanceStatusField(HandoverFieldBase):
    value: PerformanceStatus | None = None


class WeightHeightField(HandoverFieldBase):
    value: WeightHeight | None = None


class SymptomsField(HandoverFieldBase):
    value: Symptoms | None = None


class ExaminationsField(HandoverFieldBase):
    value: list[Examination] | None = None


class LabsField(HandoverFieldBase):
    value: list[LabResult] | None = Field(None, description="Key values incl. tumour markers (golden: key_values).")


class HistologyField(HandoverFieldBase):
    value: Histology | None = None


class TextListField(HandoverFieldBase):
    value: list[str] | None = None


class HandoverFields(DomainModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True, serialize_by_alias=True)

    patient: PatientField = Field(alias="1_patient", description="Nacionále")
    contacts: ContactsField = Field(alias="2_contacts", description="Kontakty")
    diagnosis: DiagnosisField = Field(alias="3_diagnosis", description="Diagnóza")
    epicrisis: EpicrisisField = Field(alias="4_epicrisis", description="Epikríza")
    mdt_question: TextField = Field(alias="5_mdt_question", description="Požadavek / otázka na MDT")
    comorbidities: ComorbiditiesField = Field(alias="6_comorbidities", description="Komorbidity (OA)")
    medications: MedicationsField = Field(alias="7_medications", description="Léková anamnéza (FA)")
    allergies: TextField = Field(alias="8_allergies", description="Alergie (AA)")
    performance_status: PerformanceStatusField = Field(alias="9_performance_status", description="PS / Karnofsky")
    weight_height: WeightHeightField = Field(alias="10_weight_height", description="Váha a výška")
    symptoms: SymptomsField = Field(alias="11_symptoms", description="Symptomy a jejich počátek")
    examinations: ExaminationsField = Field(alias="12_examinations", description="Provedená vyšetření")
    labs: LabsField = Field(alias="13_labs", description="Laboratoř vč. onkomarkerů")
    histology: HistologyField = Field(alias="14_histology", description="Histologie")
    other: TextListField = Field(alias="15_other", description="Jiná důležitá sdělení vč. přání pacienta")


class ExcludedDocument(DomainModel):
    doc_id: str = Field(pattern=BUSINESS_ID_PATTERN)
    reason: str = Field(description="E.g. 'authored after as_of'.")


class Handover(DomainModel):
    """Handover for one case. Documents count only if authored <= as_of AND received <= as_of."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        title="Handover",
        json_schema_extra={"description": __doc__},
    )

    case_id: str = Field(pattern=BUSINESS_ID_PATTERN)
    as_of: AwareDatetime = Field(description="Cut-off timestamp, e.g. MDT start 2026-10-21T08:00:00+02:00.")
    generated_at: AwareDatetime | None = None
    included_documents: list[str] = Field(description="doc_ids used for this handover.")
    excluded_documents: list[ExcludedDocument] = Field(default_factory=list)
    fields: HandoverFields
    findings: list[Finding] = Field(default_factory=list)
