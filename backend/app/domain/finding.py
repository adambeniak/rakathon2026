"""Findings of the consistency detector: conflicts, missing or stale data, SLA breaches.

Wording must stay neutral ("v dokumentaci uvedeno…", "nesoulad mezi…", "chybí…") — no clinical advice.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.domain.common import DomainModel
from app.domain.evidence import Evidence


class FindingKind(StrEnum):
    DATE_CONFLICT = "date_conflict"
    SLA_BREACH = "sla_breach"
    MISSING = "missing"
    STALE = "stale"
    MISSING_DOCUMENT = "missing_document"
    TEMPORAL_CUTOFF = "temporal_cutoff"
    METADATA_MISMATCH = "metadata_mismatch"
    INSURER = "insurer"
    NEEDS_CLARIFICATION = "needs_clarification"
    NOT_DOCUMENTED = "not_documented"
    LOST_INFORMATION = "lost_information"
    ROLE_MISMATCH = "role_mismatch"


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Finding(DomainModel):
    id: str = Field(description="Stable id referenced from handover fields, e.g. 'C1'.")
    kind: FindingKind
    severity: Severity
    message: str = Field(description="Neutral Czech description of what is inconsistent or missing.")
    field: str | None = Field(None, description="Affected handover field or path, e.g. '3_diagnosis.tnm'.")
    docs: list[str] = Field(default_factory=list, description="doc_ids involved.")
    evidence: list[Evidence] = Field(default_factory=list)
    suggested_action: str | None = Field(None, description="Workflow action, e.g. 'create_verification_task'.")
