"""Triage: which examinations does the referral letter mention that nobody attached yet? (pure, no I/O).

The proposals are quoted from the letter ("v dokumentaci uvedeno…"): a label, the date and the verbatim evidence.
The recipient workplace is resolved from the directory by rule; when it cannot be resolved it stays empty and the
coordinator picks it. Nothing here recommends an examination, it only lists what the letter says exists.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from datetime import date
from enum import StrEnum

from pydantic import Field

from app.domain.common import DomainModel
from app.domain.directory import Organization, OrganizationKind, PractitionerRole
from app.domain.document import SourceDocument
from app.domain.evidence import Evidence

# Words that identify a kind of workplace, not a particular one; an organisation is recognised by what remains.
_GENERIC = frozenset(
    {"s.r.o.", "a.s.", "ordinace", "laborator", "ambulance", "pracoviste", "centrum", "poliklinika", "nemocnice"}
)
_TITLES = re.compile(r"\b(?:mudr|mgr|ing|rndr|doc|bc|ph\.?d|prof)\.?(?=\s|,|$)", re.IGNORECASE)


class ProposalStatus(StrEnum):
    MISSING = "missing"  # mentioned in the letter, no matching document in the case
    ATTACHED = "attached"  # a document with the same date and workplace is already in the case
    POSSIBLY_ATTACHED = "possibly_attached"  # same date only: the coordinator verifies


class ListedExam(DomainModel):
    label: str = Field(description="As written in the letter, without the list number.")
    exam_date: date | None = None
    evidence: list[Evidence] = Field(min_length=1)


class RequestProposal(DomainModel):
    key: str = Field(description="Stable within the letter, e.g. '2026-09-01-1'.")
    label: str
    exam_date: date | None
    status: ProposalStatus
    recipient_org_id: str | None = Field(None, description="Directory workplace; empty when it could not be resolved.")
    recipient_name: str | None = None
    resolved_by: str | None = Field(None, description="'organization' | 'practitioner' | null")
    attached_doc_id: str | None = None
    evidence: list[Evidence]


def fold(text: str) -> str:
    base = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(c for c in base if not unicodedata.combining(c))
    return " ".join(re.sub(r"[(),;:]", " ", plain).split())


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9.]+", fold(text)))


def _organization_in(label: str, organizations: Sequence[Organization]) -> Organization | None:
    haystack = f" {fold(label)} "
    words = _words(label)
    for org in organizations:
        if org.kind in (OrganizationKind.INSURER, OrganizationKind.KOC):
            continue
        if f" {fold(org.name)} " in haystack:
            return org
    for org in organizations:
        if org.kind in (OrganizationKind.INSURER, OrganizationKind.KOC):
            continue
        core = {w for w in _words(org.name) if w not in _GENERIC}
        if core and core <= words:
            return org
    return None


def _practitioner_in(
    label: str, roles: Sequence[tuple[PractitionerRole, str]], organizations: dict[str, Organization]
) -> Organization | None:
    haystack = f" {fold(label)} "
    for role, display in roles:
        name = fold(_TITLES.sub("", display))
        if name and f" {name} " in haystack and role.organization_id in organizations:
            return organizations[role.organization_id]
    return None


def propose_requests(
    exams: Sequence[ListedExam],
    existing: Sequence[SourceDocument],
    organizations: Sequence[Organization],
    roles: Sequence[tuple[PractitionerRole, str]],
) -> list[RequestProposal]:
    by_id = {o.id: o for o in organizations}
    proposals: list[RequestProposal] = []
    for index, exam in enumerate(exams, start=1):
        recipient = _organization_in(exam.label, organizations)
        resolved_by = "organization" if recipient else None
        if recipient is None:
            recipient = _practitioner_in(exam.label, roles, by_id)
            resolved_by = "practitioner" if recipient else None
        same_day = [d for d in existing if exam.exam_date is not None and d.authored_at == exam.exam_date]
        wanted = fold(recipient.name) if recipient else None
        attached = next((d for d in same_day if wanted and d.custodian and fold(d.custodian) == wanted), None)
        possible = same_day[0] if attached is None and same_day else None
        match = attached or possible
        status = (
            ProposalStatus.ATTACHED
            if attached
            else ProposalStatus.POSSIBLY_ATTACHED
            if possible
            else ProposalStatus.MISSING
        )
        proposals.append(
            RequestProposal(
                key=f"{exam.exam_date.isoformat() if exam.exam_date else 'undated'}-{index}",
                label=exam.label,
                exam_date=exam.exam_date,
                status=status,
                recipient_org_id=recipient.id if recipient else None,
                recipient_name=recipient.name if recipient else None,
                resolved_by=resolved_by,
                attached_doc_id=match.doc_id if match else None,
                evidence=exam.evidence,
            )
        )
    return proposals
