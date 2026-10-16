"""The shared oncology case: one patient, one coordinating owner ("who holds the baton"), one state.

Transitions and guards live in `app.domain.case_machine`; see `contracts/case-states.md`.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field

from app.domain.common import BUSINESS_ID_PATTERN, DomainModel, PartyRef, Role
from app.domain.patient import Patient


class CaseState(StrEnum):
    """The 8 case states from the VZP brief (slide 10). Czech labels live in the UI i18n and the FHIR CodeSystem."""

    ODESLANO = "odeslano"
    TRIAGE = "triage"
    CEKA_NA_PODKLADY = "ceka_na_podklady"
    KOMPLETNI = "kompletni"
    PRIPRAVENO_MDT = "pripraveno_mdt"
    ZAVER_MDT = "zaver_mdt"
    ZPETNA_VAZBA_ODESLANA = "zpetna_vazba_odeslana"
    UZAVRENO = "uzavreno"


class QueueBucket(StrEnum):
    """Coordinator queue (VZP slide 9) plus the archive; derived from state and the `odlozeny` flag."""

    NOVY = "novy"
    AKTIVNI = "aktivni"
    ODLOZENY = "odlozeny"
    ARCHIV = "archiv"


class Case(DomainModel):
    id: str = Field(pattern=BUSINESS_ID_PATTERN, description="Business id, e.g. 'rakathon-2026-prochazkova'.")
    patient: Patient
    state: CaseState
    baton_holder: PartyRef | None = Field(None, description="Who must act next on the case as a whole.")
    next_deadline: AwareDatetime | None = None
    opened_at: AwareDatetime | None = Field(None, description="When the referral reached the KOC.")
    # Workflow fields below are owned by the case state machine (`app.domain.case_machine`); all are additive.
    baton_role: Role | None = Field(None, description="Role that must act next; `baton_holder` is the concrete person.")
    odlozeny: bool = Field(False, description="Postponed: waiting for an external step (queue bucket Odložený).")
    resume_baton_role: Role | None = Field(None, description="Baton role to restore when a postponed case resumes.")
    resume_on: str | None = Field(None, description="While postponed: date or external step the case waits for.")
    mdt_start: AwareDatetime | None = Field(None, description="Start of the MDT meeting; also the as-of instant.")
    conclusion_confirmed: bool = Field(False, description="A clinician signed off the MDT conclusion.")
    delivery_receipt: bool = Field(False, description="Delivery of the feedback to the GP has been confirmed.")

    @property
    def bucket(self) -> QueueBucket:
        if self.state is CaseState.UZAVRENO:
            return QueueBucket.ARCHIV
        if self.odlozeny:
            return QueueBucket.ODLOZENY
        if self.state is CaseState.ODESLANO:
            return QueueBucket.NOVY
        return QueueBucket.AKTIVNI
