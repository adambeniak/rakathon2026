"""Shared building blocks of the domain model."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# Business identifiers used in the API and across documents (never FHIR logical ids), e.g. a file stem
# "11_Histologie_KOC2_2026-10-19" or a case id "rakathon-2026-prochazkova".
BUSINESS_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.@-]*$"


class DomainModel(BaseModel):
    """Base for domain models: immutable, no unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Role(StrEnum):
    """Workflow role of a party: decides who may act and in which board lane a task appears."""

    GP = "gp"
    COORDINATOR = "coordinator"
    KOC_PHYSICIAN = "koc_physician"
    KOC_STAFF = "koc_staff"
    EXTERNAL_WORKPLACE = "external_workplace"
    PATIENT = "patient"
    REVIEWER = "reviewer"
    SYSTEM = "system"


class PartyRef(DomainModel):
    """A person or role acting in the workflow (baton holder, task owner, actor of an audit record)."""

    id: str = Field(
        pattern=BUSINESS_ID_PATTERN, description="Business id, e.g. 'dvorakova-lucie@koc2-nemocnice-lipova'."
    )
    display: str
    role: Role
