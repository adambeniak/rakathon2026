"""The insurer reviewer's (revizní lékař) minimal case view: no name, birth date, birth number or clinical text."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.api.schemas.intervals import TimeToTreatmentIntervals
from app.domain.case import CaseState

REVIEWER_REF_PATTERN = r"^RV-[0-9A-F]{12}$"


class FeedbackDelivery(StrEnum):
    NOT_SENT = "not_sent"  # the MDT feedback has not been sent to the referring GP yet
    HANDED_OVER = "handed_over"  # the mail relay accepted the feedback e-mail (not proof that it was read)
    OPENED_BY_GP = "opened_by_gp"  # the referring GP opened the conclusion in the portal (audited `gp_opened`)
    UNCONFIRMED = "unconfirmed"  # the case is past the feedback but no delivery receipt is recorded


class ReviewerDelivery(BaseModel):
    status: FeedbackDelivery = Field(
        description="not_sent | handed_over (the relay accepted the e-mail; not proof of reading) | opened_by_gp "
        "(the GP opened the conclusion) | unconfirmed (past the feedback, no receipt recorded)."
    )
    gp_opened_at: AwareDatetime | None = Field(
        None, description="When the referring GP first opened the conclusion; null when no opening is recorded."
    )


class ReviewerCase(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "ref": "RV-3F9A2C1B7D40",
                    "initials": "A. P.",
                    "birth_year": 1963,
                    "insurer_code": "211",
                    "diagnosis_group": "C25",
                    "state": "zpetna_vazba_odeslana",
                    "referred_on": "2026-10-02",
                    "intervals": {
                        "t1": {"days": None, "status": "not_recorded", "start": None, "end": "2026-10-02"},
                        "t2": {"days": 19, "status": "measured", "start": "2026-10-02", "end": "2026-10-21"},
                        "t3": {"days": None, "status": "running", "start": "2026-10-21", "end": None},
                    },
                    "delivery": {"status": "handed_over", "gp_opened_at": None},
                }
            ]
        }
    )

    ref: str = Field(
        pattern=REVIEWER_REF_PATTERN,
        description="Stable pseudonym of the case for the reviewer (keyed hash of the case id; the case id itself "
        "contains the surname and is not returned).",
    )
    initials: str = Field(description="Initials of the patient, e.g. 'A. P.'.")
    birth_year: int = Field(description="Year of birth only.")
    insurer_code: str = Field(description="Always the reviewer's own insurer.")
    diagnosis_group: str | None = Field(
        None,
        description="MKN-10 category (three characters, e.g. 'C25') of the suspected diagnosis in the referral, as "
        "written by the GP; no text. Null when the referral has no code.",
    )
    state: CaseState
    referred_on: date | None = Field(None, description="Date the referral reached the KOC (Europe/Prague).")
    intervals: TimeToTreatmentIntervals
    delivery: ReviewerDelivery
