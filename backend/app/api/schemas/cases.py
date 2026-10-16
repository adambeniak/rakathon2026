"""Case schemas of the public API (ids are business identifiers, never FHIR logical ids)."""

from __future__ import annotations

from datetime import date

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from pydantic.config import JsonDict

from app.domain.case import CaseState
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
    "missing_count": None,
    "conflict_count": None,
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


class CaseSummary(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [_SUMMARY_EXAMPLE]})

    id: str = Field(description="Case business id, e.g. 'rakathon-2026-prochazkova'.")
    patient: PatientSummary
    state: CaseState
    baton_holder: BatonHolder | None = Field(None, description="'Na tahu' — who must act next on the case.")
    next_deadline: AwareDatetime | None = None
    opened_at: AwareDatetime | None = Field(None, description="When the referral reached the KOC.")
    document_count: int = Field(ge=0, description="All documents of the case (not filtered by as-of).")
    missing_count: int | None = Field(
        None, description="Not computed yet (handover assembly, F2-2): always null for now, UI shows '—'."
    )
    conflict_count: int | None = Field(
        None, description="Not computed yet (consistency detector, F3-1): always null for now, UI shows '—'."
    )


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
                }
            ]
        }
    )

    documents: list[DocumentSummary] = Field(description="Ordered by received time.")
