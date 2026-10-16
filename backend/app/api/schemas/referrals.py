"""Schemas of the referral intake (the prefill and submission models are domain models, see `app.domain.referral`)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.api.schemas.cases import CaseSummary


class ReferralCreated(BaseModel):
    case: CaseSummary = Field(description="The new case: state `odeslano`, baton at the KOC coordinator.")
    warnings: list[str] = Field(
        default_factory=list, description="Non-blocking notes, e.g. 'insurer_not_in_directory' (no Coverage written)."
    )
