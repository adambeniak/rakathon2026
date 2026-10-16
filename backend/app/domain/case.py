"""The shared oncology case: one patient, one coordinating owner ("who holds the baton"), one state.

Transitions, guards and queue buckets are P4's case state machine (#2); see `contracts/case-states.md`.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field

from app.domain.common import BUSINESS_ID_PATTERN, DomainModel, PartyRef
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


class Case(DomainModel):
    id: str = Field(pattern=BUSINESS_ID_PATTERN, description="Business id, e.g. 'rakathon-2026-prochazkova'.")
    patient: Patient
    state: CaseState
    baton_holder: PartyRef | None = Field(None, description="Who must act next on the case as a whole.")
    next_deadline: AwareDatetime | None = None
    opened_at: AwareDatetime | None = Field(None, description="When the referral reached the KOC.")
    # TODO(#2): transitions, guards, postponed flag and queue bucket (Nový / Aktivní / Odložený) by P4.
