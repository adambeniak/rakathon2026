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


class CaseAction(StrEnum):
    """Next step on the case as a whole, for the queue card ("Na tahu: … – <action>"). Labels live in the UI i18n."""

    ACCEPT_CASE = "accept_case"
    TRIAGE = "triage"
    COMPLETE_DOCUMENTS = "complete_documents"
    REVIEW_HANDOVER = "review_handover"
    HOLD_MDT = "hold_mdt"
    SEND_FEEDBACK = "send_feedback"
    CONFIRM_RECEIPT = "confirm_receipt"
    CLOSE_CASE = "close_case"
    AWAIT_EXTERNAL = "await_external"
    NONE = "none"


# Baton role after entering each state (contracts/case-states.md); used only when a stored case lacks `baton_role`.
_DEFAULT_BATON_ROLE: dict[CaseState, Role | None] = {
    CaseState.ODESLANO: Role.COORDINATOR,
    CaseState.TRIAGE: Role.COORDINATOR,
    CaseState.CEKA_NA_PODKLADY: Role.COORDINATOR,
    CaseState.KOMPLETNI: Role.KOC_PHYSICIAN,
    CaseState.PRIPRAVENO_MDT: Role.KOC_PHYSICIAN,
    CaseState.ZAVER_MDT: Role.COORDINATOR,
    CaseState.ZPETNA_VAZBA_ODESLANA: Role.GP,
    CaseState.UZAVRENO: None,
}

_STATE_ACTION: dict[CaseState, CaseAction] = {
    CaseState.ODESLANO: CaseAction.ACCEPT_CASE,
    CaseState.TRIAGE: CaseAction.TRIAGE,
    CaseState.CEKA_NA_PODKLADY: CaseAction.COMPLETE_DOCUMENTS,
    CaseState.KOMPLETNI: CaseAction.REVIEW_HANDOVER,
    CaseState.PRIPRAVENO_MDT: CaseAction.HOLD_MDT,
    CaseState.ZAVER_MDT: CaseAction.SEND_FEEDBACK,
    CaseState.ZPETNA_VAZBA_ODESLANA: CaseAction.CONFIRM_RECEIPT,
    CaseState.UZAVRENO: CaseAction.NONE,
}


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

    @property
    def current_baton_role(self) -> Role | None:
        """The machine's `baton_role`; for a stored case without it, the role after entering the state."""
        if self.state is CaseState.UZAVRENO:
            return None
        if self.baton_role is not None:
            return self.baton_role
        if self.state is CaseState.ZPETNA_VAZBA_ODESLANA and self.delivery_receipt:
            return Role.COORDINATOR
        return _DEFAULT_BATON_ROLE[self.state]

    @property
    def next_action(self) -> CaseAction:
        """What the baton role does next. In `zpetna_vazba_odeslana` the baton moves from the GP to the coordinator
        once delivery is confirmed (`delivery_confirmed`), whose next step is `close`; the GP opening the feedback
        (`gp_opened`) does not move it."""
        if self.state is CaseState.UZAVRENO:
            return CaseAction.NONE
        if self.odlozeny:
            return CaseAction.AWAIT_EXTERNAL
        if self.state is CaseState.ZPETNA_VAZBA_ODESLANA and self.current_baton_role is Role.COORDINATOR:
            return CaseAction.CLOSE_CASE
        return _STATE_ACTION[self.state]
