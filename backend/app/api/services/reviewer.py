"""The insurer reviewer's (revizní lékař) scoped view of cases: GDPR minimisation at the API boundary.

Who: only the `reviewer` role, and only cases whose patient is insured by the reviewer's own insurer (the insurer
Organization of the reviewer's PractitionerRole in the directory). A case of another insurer is "not found", so its
existence is not confirmed.

What: a pseudonymous ref instead of the case id (the business id contains the surname), initials and birth year,
the MKN-10 category of the suspected diagnosis (no text), the case state, the referral date, the T1-T3 proxies and the
status of the feedback delivery to the GP. Never the name, birth date, birth number, contact data, documents or any
clinical text.

Audit: the cases are read through `CaseReader`, whose reads are AuditEvents of the acting reviewer.
"""

from __future__ import annotations

import hashlib
import hmac
import re

from pydantic import SecretStr

from app.api.schemas.intervals import TimeToTreatmentIntervals
from app.api.schemas.reviewer import FeedbackDelivery, ReviewerCase, ReviewerDelivery
from app.domain.case import CaseState
from app.domain.clock import TZ
from app.domain.common import PartyRef, Role
from app.domain.errors import ForbiddenError, NotFoundError
from app.fhir.cases import CaseOverview, CaseReader
from app.fhir.directory import Directory
from app.timeline.intervals import case_intervals

# Domain separation: the pseudonym key is derived from the app secret for this one purpose.
_REF_LABEL = b"stafeta/reviewer-case-ref/v1:"
_MKN10_CATEGORY = re.compile(r"^([A-Z]\d{2})")
FEEDBACK_STATES = frozenset({CaseState.ZPETNA_VAZBA_ODESLANA, CaseState.UZAVRENO})


def case_ref(case_id: str, secret: SecretStr) -> str:
    digest = hmac.new(secret.get_secret_value().encode(), _REF_LABEL + case_id.encode(), hashlib.sha256).hexdigest()
    return f"RV-{digest[:12].upper()}"


def initials(given: str, family: str) -> str:
    return " ".join(f"{part[0].upper()}." for part in (given.strip(), family.strip()) if part)


def diagnosis_group(code: str | None) -> str | None:
    match = _MKN10_CATEGORY.match(code.strip().upper()) if code else None
    return match.group(1) if match else None


def reviewer_insurer(actor: PartyRef, directory: Directory) -> str:
    """The insurer code of the acting reviewer; 403 for any other role or a reviewer without an insurer."""
    if actor.role is not Role.REVIEWER:
        raise ForbiddenError("Přehled pro pojišťovnu je určen jen revizním lékařům")
    entry = directory.role(actor.id)
    org = directory.org(entry.role.organization_id) if entry else None
    code = org.org.insurer_code if org else None
    if not code:
        raise ForbiddenError("Revizní lékař není v adresáři přiřazen ke zdravotní pojišťovně")
    return code


def _delivery(overview: CaseOverview) -> ReviewerDelivery:
    case, opened = overview.case, overview.extras.gp_opened_at
    if case.state not in FEEDBACK_STATES:
        status = FeedbackDelivery.NOT_SENT
    elif opened is not None:
        status = FeedbackDelivery.OPENED_BY_GP
    elif case.delivery_receipt:
        status = FeedbackDelivery.HANDED_OVER
    else:
        status = FeedbackDelivery.UNCONFIRMED
    return ReviewerDelivery(status=status, gp_opened_at=opened if case.state in FEEDBACK_STATES else None)


def reviewer_case(overview: CaseOverview, secret: SecretStr) -> ReviewerCase:
    case, patient = overview.case, overview.case.patient
    return ReviewerCase(
        ref=case_ref(case.id, secret),
        initials=initials(patient.given, patient.family),
        birth_year=patient.birth_date.year,
        insurer_code=patient.insurer_code or "",
        diagnosis_group=diagnosis_group(overview.extras.diagnosis_code),
        state=case.state,
        referred_on=case.opened_at.astimezone(TZ).date() if case.opened_at else None,
        intervals=TimeToTreatmentIntervals.of(case_intervals(case)),
        delivery=_delivery(overview),
    )


class ReviewerCases:
    def __init__(self, reader: CaseReader, actor: PartyRef, directory: Directory, secret: SecretStr) -> None:
        self._reader = reader
        self._actor = actor
        self._directory = directory
        self._secret = secret

    async def list(self) -> list[ReviewerCase]:
        insurer = reviewer_insurer(self._actor, self._directory)  # before any read
        overviews = await self._reader.list_cases()
        own = [o for o in overviews if o.case.patient.insurer_code == insurer]
        return sorted(
            (reviewer_case(o, self._secret) for o in own), key=lambda c: (c.referred_on is None, c.referred_on, c.ref)
        )

    async def get(self, ref: str) -> ReviewerCase:
        insurer = reviewer_insurer(self._actor, self._directory)
        overviews = await self._reader.list_cases()
        match = next(
            (
                o
                for o in overviews
                if o.case.patient.insurer_code == insurer and case_ref(o.case.id, self._secret) == ref
            ),
            None,
        )
        if match is None:
            raise NotFoundError("case", ref)
        fresh = await self._reader.overview(match.case.id)  # an audited read of this one case
        return reviewer_case(fresh, self._secret)
