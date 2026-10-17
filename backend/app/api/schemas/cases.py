"""Case schemas of the public API (ids are business identifiers, never FHIR logical ids)."""

from __future__ import annotations

from datetime import date

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from pydantic.config import JsonDict

from app.api.schemas.intervals import TimeToTreatmentIntervals
from app.domain.case import CaseState, QueueBucket
from app.domain.common import Role
from app.domain.patient import Sex

_PATIENT_EXAMPLE: JsonDict = {
    "display_name": "Alena Procházková",
    "birth_date": "1963-07-22",
    "age_years": 63,
    "sex": "female",
    "insurer_code": "211",
}
_SUMMARY_EXAMPLE: JsonDict = {
    "id": "rakathon-2026-prochazkova",
    "patient": _PATIENT_EXAMPLE,
    "state": "pripraveno_mdt",
    "baton_holder": {
        "id": "hruby-pavel@koc2-nemocnice-lipova",
        "display": "MDT GIT – doc. MUDr. Pavel Hrubý, Ph.D.",
        "role": "koc_physician",
    },
    "next_deadline": "2026-10-21T08:00:00+02:00",
    "opened_at": "2026-10-02T09:30:00+02:00",
    "document_count": 13,
    "counts": {"missing": 3, "conflict": 2, "stale": 1},
    "missing_count": 3,
    "conflict_count": 2,
}


class PatientSummary(BaseModel):
    display_name: str
    birth_date: date
    age_years: int = Field(description="Age on the (demo) current date.")
    sex: Sex
    insurer_code: str | None = Field(None, description="Kód zdravotní pojišťovny, e.g. '211' (ZP MV ČR).")


class BatonHolder(BaseModel):
    id: str = Field(description="Business id of the PractitionerRole.")
    display: str
    role: Role


class EvidenceRef(BaseModel):
    doc_id: str
    quote: str = Field(description="Verbatim quote from the source document.")


class SuspectedDiagnosis(BaseModel):
    code: str | None = Field(None, description="MKN-10 code as written in the referral, e.g. 'C25.0'.")
    text: str
    evidence: list[EvidenceRef] = Field(
        description="Where the referral states it; empty when the GP changed the diagnosis after the prefill."
    )


class ReferringGp(BaseModel):
    name: str
    practice: str | None = None


class CaseCounts(BaseModel):
    """Handover counters as the handover screen shows them (sections marked Chybí / Nesouhlasí / Zastaralé)."""

    missing: int | None = None
    conflict: int | None = None
    stale: int | None = None


class CaseSummary(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [_SUMMARY_EXAMPLE]})

    id: str = Field(description="Case business id, e.g. 'rakathon-2026-prochazkova'.")
    patient: PatientSummary
    state: CaseState
    baton_holder: BatonHolder | None = Field(None, description="'Na tahu' — who must act next on the case.")
    next_deadline: AwareDatetime | None = None
    opened_at: AwareDatetime | None = Field(None, description="When the referral reached the KOC.")
    postponed: bool = Field(False, description="Postponed (waiting for an external step): queue column Odložený.")
    bucket: QueueBucket = Field(
        QueueBucket.AKTIVNI, description="Coordinator queue column: novy | aktivni | odlozeny | archiv."
    )
    suspected_diagnosis: SuspectedDiagnosis | None = Field(
        None, description="From the referral (suspected, as written); null when the case has no referral letter."
    )
    koc: str | None = Field(None, description="Name of the managing KOC (Organization).")
    referring_gp: ReferringGp | None = None
    counts: CaseCounts | None = Field(
        None,
        description="Computed from the handover at the case's `mdt_start` (or the demo clock). Null when the handover "
        "cannot be built or has no usable document; never a false zero.",
    )
    document_count: int = Field(ge=0, description="All documents of the case (not filtered by as-of).")
    missing_count: int | None = Field(None, description="Same number as `counts.missing`; null when `counts` is null.")
    conflict_count: int | None = Field(
        None, description="Same number as `counts.conflict`; null when `counts` is null."
    )
    gp_opened_at: AwareDatetime | None = Field(
        None,
        description="When the referring GP first opened the MDT conclusion (the audited `gp_opened` event). Null when "
        "no opening is recorded; null is not proof that the GP has not read it.",
    )


class RecordedReadinessWaiver(BaseModel):
    """A blocking MDT readiness item a KOC physician waived at `mark_ready_mdt` (stored as Provenance)."""

    item: str = Field(
        description="Readiness item of the pathway: histology | ct_staging | tumour_markers | comorbidities | "
        "performance_status | mdt_question."
    )
    reason: str = Field(description="The physician's reason, as entered.")
    waived_by: str | None = Field(None, description="Display name of the signing KOC physician.")
    waived_at: AwareDatetime


class DocumentSummary(BaseModel):
    doc_id: str = Field(description="File stem, the id used in evidence, e.g. '11_Histologie_KOC2_2026-10-19'.")
    title: str
    type_code: str | None = Field(None, description="LOINC document type.")
    authored_at: date
    received_at: AwareDatetime
    custodian: str | None = None
    author: str | None = None


class CaseDetail(CaseSummary):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    **_SUMMARY_EXAMPLE,
                    "documents": [
                        {
                            "doc_id": "07_PL_zadost_KOC2_2026-10-02",
                            "title": "PL – epikríza a žádost o převzetí do péče KOC",
                            "type_code": "57133-1",
                            "authored_at": "2026-10-02",
                            "received_at": "2026-10-02T09:30:00+02:00",
                            "custodian": "Ordinace praktického lékaře – MUDr. Tomáš Řezníček",
                            "author": "MUDr. Tomáš Řezníček",
                        }
                    ],
                    "intervals": {
                        "t1": {"days": None, "status": "not_recorded", "start": None, "end": "2026-10-02"},
                        "t2": {"days": None, "status": "running", "start": "2026-10-02", "end": None},
                        "t3": {"days": None, "status": "not_started", "start": None, "end": None},
                    },
                }
            ]
        }
    )

    documents: list[DocumentSummary] = Field(description="Ordered by received time.")
    readiness_waivers: list[RecordedReadinessWaiver] = Field(
        default_factory=list,
        description="Waivers in force for the MDT readiness (the latest per item; none before the last `reopen`). "
        "Empty while the case is not marked ready for the MDT.",
    )
    intervals: TimeToTreatmentIntervals = Field(
        description="Time-to-treatment proxies T1-T3 (header 'Časové intervaly'); a value is null when an end point "
        "is not recorded, never estimated.",
    )
