"""Case state machine (VZP slide 10): odeslano → triage → ceka_na_podklady ⇄ kompletni →
pripraveno_mdt → zaver_mdt → zpetna_vazba_odeslana → uzavreno, plus the `odlozeny` flag.

Table-driven: every allowed transition is one `_Rule` (state · event · roles · guard · next state ·
baton · notifications). Anything not in the table raises `TransitionError`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from . import clock
from .events import DomainEvent, EventKind, Role, TransitionError
from .pathway import Readiness


class CaseState(StrEnum):
    ODESLANO = "odeslano"
    TRIAGE = "triage"
    CEKA_NA_PODKLADY = "ceka_na_podklady"
    KOMPLETNI = "kompletni"
    PRIPRAVENO_MDT = "pripraveno_mdt"
    ZAVER_MDT = "zaver_mdt"
    ZPETNA_VAZBA_ODESLANA = "zpetna_vazba_odeslana"
    UZAVRENO = "uzavreno"


class Baton(StrEnum):
    """Who is "na tahu"."""

    GP = "gp"
    COORD = "coordinator"
    KOC_DOC = "koc_doctor"
    MDT = "mdt"
    EXTERNAL = "external"  # postponed: waiting for an external step
    NONE = "none"  # closed


class Bucket(StrEnum):
    NOVY = "novy"
    AKTIVNI = "aktivni"
    ODLOZENY = "odlozeny"
    ARCHIV = "archiv"


@dataclass(frozen=True)
class Case:
    id: str
    state: CaseState | None = None  # None = not yet submitted
    baton: Baton = Baton.NONE
    odlozeny: bool = False
    resume_baton: Baton | None = None
    mdt_start: datetime | None = None
    conclusion_confirmed: bool = False
    delivery_receipt: bool = False

    @property
    def bucket(self) -> Bucket | None:
        if self.state is None:
            return None
        if self.state is CaseState.UZAVRENO:
            return Bucket.ARCHIV
        if self.odlozeny:
            return Bucket.ODLOZENY
        if self.state is CaseState.ODESLANO:
            return Bucket.NOVY
        return Bucket.AKTIVNI


@dataclass(frozen=True)
class CaseContext:
    """Facts the caller supplies for guards; the machine does no I/O."""

    consent_confirmed: bool = False
    target_koc: str | None = None
    patient_id: str | None = None
    open_request_tasks: int = 0
    missing_blockers: int = 0
    readiness: Readiness | None = None
    reason: str | None = None
    resume_on: str | None = None  # ISO date or description of the external step
    conclusion: str | None = None
    confirmed_by: str | None = None  # clinician user id; explicit sign-off of the MDT conclusion
    gp_recipient: str | None = None
    receipt_id: str | None = None


@dataclass(frozen=True)
class TransitionResult:
    case: Case
    events: tuple[DomainEvent, ...]


Guard = Callable[[Case, CaseContext, datetime], str | None]


@dataclass(frozen=True)
class _Rule:
    event: str
    from_state: CaseState | None
    roles: frozenset[Role]
    to: CaseState | None  # None = stay in the same state
    baton: Baton | None  # None = keep
    guard: Guard | None = None
    notify: tuple[tuple[tuple[Role, ...], str], ...] = ()
    audit_action: str = "update"
    set_: dict[str, bool] = field(default_factory=dict)


def _nonblank(value: str | None) -> bool:
    return bool(value and value.strip())


def _g_submit(_c: Case, ctx: CaseContext, _n: datetime) -> str | None:
    if not ctx.consent_confirmed:
        return "consent must be confirmed"
    if not _nonblank(ctx.target_koc):
        return "target KOC is required"
    return None if _nonblank(ctx.patient_id) else "patient id is required"


def _g_request_docs(_c: Case, ctx: CaseContext, _n: datetime) -> str | None:
    return None if ctx.open_request_tasks >= 1 else "at least one document request task is required"


def _g_complete(_c: Case, ctx: CaseContext, _n: datetime) -> str | None:
    return None if ctx.missing_blockers == 0 else "required documents are still missing"


def _g_docs_received(_c: Case, ctx: CaseContext, _n: datetime) -> str | None:
    return None if ctx.open_request_tasks == 0 else "document requests are still open"


def _g_reason(_c: Case, ctx: CaseContext, _n: datetime) -> str | None:
    return None if _nonblank(ctx.reason) else "reason is required"


def _g_ready(_c: Case, ctx: CaseContext, _n: datetime) -> str | None:
    r = ctx.readiness
    if r is None:
        return "readiness gate result is required"
    if not r.ready:
        return f"readiness gate not passed, missing: {', '.join(r.missing)}"
    for w in r.waived:  # defence in depth; readiness_gate already validates
        if w.by_role is not Role.KOC_DOC or not _nonblank(w.reason):
            return "invalid waiver"
    return None


def _g_conclusion(case: Case, ctx: CaseContext, now: datetime) -> str | None:
    if case.mdt_start is None:
        return "MDT start is not set"
    if now < case.mdt_start:
        return "MDT has not started yet"
    if not _nonblank(ctx.conclusion):
        return "conclusion is required"
    return None if _nonblank(ctx.confirmed_by) else "conclusion must be confirmed by a clinician"


def _g_feedback(case: Case, ctx: CaseContext, _n: datetime) -> str | None:
    if not case.conclusion_confirmed:
        return "conclusion must be confirmed by a clinician"
    return None if _nonblank(ctx.gp_recipient) else "GP recipient is required"


def _g_receipt(_c: Case, ctx: CaseContext, _n: datetime) -> str | None:
    return None if _nonblank(ctx.receipt_id) else "delivery receipt id is required"


def _g_closed(case: Case, _c: CaseContext, _n: datetime) -> str | None:
    return None if case.delivery_receipt else "delivery has not been confirmed"


def _g_postpone(_c: Case, ctx: CaseContext, _n: datetime) -> str | None:
    if not _nonblank(ctx.reason):
        return "reason is required"
    return None if _nonblank(ctx.resume_on) else "resume_on / external step is required"


def _g_resume(case: Case, _c: CaseContext, _n: datetime) -> str | None:
    return None if case.odlozeny else "case is not postponed"


_C, _D, _M, _G, _S = Role.COORD, Role.KOC_DOC, Role.MDT, Role.GP, Role.SYSTEM
S = CaseState
_POSTPONABLE = (S.TRIAGE, S.CEKA_NA_PODKLADY, S.KOMPLETNI, S.PRIPRAVENO_MDT)

_RULES: tuple[_Rule, ...] = (
    _Rule(
        "submit",
        None,
        frozenset({_G}),
        S.ODESLANO,
        Baton.COORD,
        _g_submit,
        notify=(((_C,), "case.new"),),
        audit_action="create",
    ),
    _Rule(
        "accept",
        S.ODESLANO,
        frozenset({_C}),
        S.TRIAGE,
        Baton.COORD,
        notify=(((_G,), "case.accepted"),),
    ),
    _Rule(
        "request_documents",
        S.TRIAGE,
        frozenset({_C}),
        S.CEKA_NA_PODKLADY,
        Baton.COORD,
        _g_request_docs,
        notify=(((_G,), "case.documents_requested"),),
    ),
    _Rule("mark_complete", S.TRIAGE, frozenset({_C}), S.KOMPLETNI, Baton.KOC_DOC, _g_complete),
    _Rule(
        "docs_received",
        S.CEKA_NA_PODKLADY,
        frozenset({_C, _S}),
        S.KOMPLETNI,
        Baton.KOC_DOC,
        _g_docs_received,
    ),
    _Rule(
        "missing_found",
        S.KOMPLETNI,
        frozenset({_C, _D}),
        S.CEKA_NA_PODKLADY,
        Baton.COORD,
        _g_reason,
    ),
    _Rule(
        "mark_ready_mdt",
        S.KOMPLETNI,
        frozenset({_D}),
        S.PRIPRAVENO_MDT,
        Baton.MDT,
        _g_ready,
        notify=(((_M,), "case.ready_for_mdt"),),
    ),
    _Rule("reopen", S.PRIPRAVENO_MDT, frozenset({_D}), S.KOMPLETNI, Baton.KOC_DOC, _g_reason),
    _Rule(
        "record_mdt_conclusion",
        S.PRIPRAVENO_MDT,
        frozenset({_D, _M}),
        S.ZAVER_MDT,
        Baton.COORD,
        _g_conclusion,
        set_={"conclusion_confirmed": True},
    ),
    _Rule(
        "send_feedback",
        S.ZAVER_MDT,
        frozenset({_C}),
        S.ZPETNA_VAZBA_ODESLANA,
        Baton.GP,
        _g_feedback,
        notify=(((_G,), "feedback.sent"), ((Role.REVIEWER,), "feedback.sent_reviewer")),
    ),
    _Rule(
        "delivery_confirmed",
        S.ZPETNA_VAZBA_ODESLANA,
        frozenset({_S}),
        None,
        Baton.COORD,
        _g_receipt,
        set_={"delivery_receipt": True},
    ),
    _Rule(
        "gp_opened", S.ZPETNA_VAZBA_ODESLANA, frozenset({_G, _S}), None, None, audit_action="read"
    ),
    _Rule("close", S.ZPETNA_VAZBA_ODESLANA, frozenset({_C}), S.UZAVRENO, Baton.NONE, _g_closed),
    *(
        _Rule("postpone", s, frozenset({_C}), None, Baton.EXTERNAL, _g_postpone)
        for s in _POSTPONABLE
    ),
    *(_Rule("resume", s, frozenset({_C}), None, None, _g_resume) for s in _POSTPONABLE),
)

CASE_EVENTS = tuple(dict.fromkeys(r.event for r in _RULES))
_BY_KEY = {(r.event, r.from_state): r for r in _RULES}


def transition(
    case: Case,
    event: str,
    actor: Role,
    ctx: CaseContext | None = None,
    now: datetime | None = None,
) -> TransitionResult:
    ctx = ctx or CaseContext()
    now = now or clock.now()
    rule = _BY_KEY.get((event, case.state))
    if rule is None:
        raise TransitionError(
            "invalid_transition",
            f"event {event!r} not allowed in state {case.state.value if case.state else 'new'!r}",
        )
    if case.odlozeny and event != "resume":
        raise TransitionError("case_postponed", "case is postponed; resume it first")
    if actor not in rule.roles:
        raise TransitionError("forbidden_role", f"role {actor.value!r} may not {event!r}")
    problem = rule.guard(case, ctx, now) if rule.guard else None
    if problem:
        raise TransitionError("guard_failed", problem)

    changes: dict[str, object] = dict(rule.set_)
    if rule.to is not None:
        changes["state"] = rule.to
    if event == "postpone":
        changes.update(odlozeny=True, resume_baton=case.baton, baton=Baton.EXTERNAL)
    elif event == "resume":
        changes.update(odlozeny=False, baton=case.resume_baton or case.baton, resume_baton=None)
    elif rule.baton is not None:
        changes["baton"] = rule.baton
    new = replace(case, **changes)  # type: ignore[arg-type]

    payload: dict[str, object] = {
        "case_id": case.id,
        "event": event,
        "from": case.state.value if case.state else None,
        "to": new.state.value if new.state else None,
        "baton": new.baton.value,
        "bucket": new.bucket.value if new.bucket else None,
        "actor_role": actor.value,
    }
    if ctx.reason:
        payload["reason"] = ctx.reason
    if event == "mark_ready_mdt" and ctx.readiness:
        payload["waived"] = [
            {"item": w.item, "by": w.by, "reason": w.reason} for w in ctx.readiness.waived
        ]
    events = [DomainEvent(EventKind.AUDIT, rule.audit_action, now, payload)]
    events += [
        DomainEvent(EventKind.NOTIFICATION, tpl, now, {"case_id": case.id}, recipients)
        for recipients, tpl in rule.notify
    ]
    return TransitionResult(new, tuple(events))
