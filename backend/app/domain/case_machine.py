"""Case state machine (VZP slide 10): odeslano → triage → ceka_na_podklady ⇄ kompletni →
pripraveno_mdt → zaver_mdt → zpetna_vazba_odeslana → uzavreno, plus the `odlozeny` flag.

Table-driven: every allowed transition is one `_Rule` (state · event · roles · guard · next state ·
baton · notifications). Anything not in the table raises `TransitionError` (→ 409 problem+json).
The table is documented in `contracts/case-states.md`; keep both in sync.

The machine owns the baton *role* (`Case.baton_role`). The concrete person (`Case.baton_holder`) is
resolved by the caller; a holder whose role no longer matches is cleared.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from app.domain import clock
from app.domain.case import Case, CaseState
from app.domain.common import Role
from app.domain.events import DomainEvent, EventKind, TransitionError
from app.domain.pathway import Readiness
from app.domain.patient import Patient

S = CaseState
_GP, _COORD, _DOC, _SYS = Role.GP, Role.COORDINATOR, Role.KOC_PHYSICIAN, Role.SYSTEM


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


@dataclass(frozen=True)
class GuardFailure:
    """A guard refusal that also names the blocking items (readiness item keys) in structured form."""

    detail: str
    blocking_items: tuple[str, ...]


Guard = Callable[[Case, CaseContext, datetime], str | GuardFailure | None]


@dataclass(frozen=True)
class _Rule:
    event: str
    from_state: CaseState | None  # None only for `submit`, which creates the case
    roles: frozenset[Role]
    to: CaseState | None  # None = stay in the same state
    baton: Role | None  # None = keep
    guard: Guard | None = None
    notify: tuple[tuple[tuple[Role, ...], str], ...] = ()
    audit_action: str = "update"
    set_: dict[str, bool] = field(default_factory=dict)


def _nonblank(value: str | None) -> bool:
    return bool(value and value.strip())


def _g_submit(_c: Case, ctx: CaseContext, _n: datetime) -> str | None:
    if not ctx.consent_confirmed:
        return "Souhlas pacienta musí být potvrzen"
    if not _nonblank(ctx.target_koc):
        return "Je nutné zadat cílové KOC"
    return None if _nonblank(ctx.patient_id) else "Chybí identifikátor pacienta"


def _g_request_docs(_c: Case, ctx: CaseContext, _n: datetime) -> str | None:
    return None if ctx.open_request_tasks >= 1 else "Je nutný alespoň jeden požadavek na podklady"


def _g_complete(_c: Case, ctx: CaseContext, _n: datetime) -> str | None:
    return None if ctx.missing_blockers == 0 else "Požadované podklady stále chybí"


def _g_docs_received(_c: Case, ctx: CaseContext, _n: datetime) -> str | None:
    return None if ctx.open_request_tasks == 0 else "Požadavky na podklady jsou stále otevřené"


def _g_reason(_c: Case, ctx: CaseContext, _n: datetime) -> str | None:
    return None if _nonblank(ctx.reason) else "Důvod je povinný"


def _g_ready(_c: Case, ctx: CaseContext, _n: datetime) -> str | GuardFailure | None:
    r = ctx.readiness
    if r is None:
        return "Chybí výsledek kontroly připravenosti k MDT"
    if not r.ready:
        return GuardFailure(f"Připravenost k MDT není splněna, chybí: {', '.join(r.missing)}", r.missing)
    for w in r.waived:  # defence in depth; readiness_gate already validates
        if w.by_role is not Role.KOC_PHYSICIAN or not _nonblank(w.reason) or not _nonblank(w.by):
            return "Prominutí položky není platné"
    return None


def _g_conclusion(case: Case, ctx: CaseContext, now: datetime) -> str | None:
    if case.mdt_start is None:
        return "Není nastaven termín MDT"
    if now < case.mdt_start:
        return "MDT ještě nezačalo"
    if not _nonblank(ctx.conclusion):
        return "Závěr je povinný"
    return None if _nonblank(ctx.confirmed_by) else "Závěr musí potvrdit lékař"


def _g_feedback(case: Case, ctx: CaseContext, _n: datetime) -> str | None:
    if not case.conclusion_confirmed:
        return "Závěr musí potvrdit lékař"
    return None if _nonblank(ctx.gp_recipient) else "Chybí adresát – praktický lékař"


def _g_receipt(_c: Case, ctx: CaseContext, _n: datetime) -> str | None:
    return None if _nonblank(ctx.receipt_id) else "Chybí identifikátor potvrzení o předání"


def _g_closed(case: Case, _c: CaseContext, _n: datetime) -> str | None:
    return None if case.delivery_receipt else "Předání nebylo potvrzeno"


def _g_postpone(_c: Case, ctx: CaseContext, _n: datetime) -> str | None:
    if not _nonblank(ctx.reason):
        return "Důvod je povinný"
    return None if _nonblank(ctx.resume_on) else "Je nutné uvést datum nebo externí krok, na který se čeká"


def _g_resume(case: Case, _c: CaseContext, _n: datetime) -> str | None:
    return None if case.odlozeny else "Případ není odložen"


_SUBMIT = _Rule(
    "submit", None, frozenset({_GP}), S.ODESLANO, _COORD, _g_submit,
    notify=(((_COORD,), "case.new"),), audit_action="create",
)  # fmt: skip
_POSTPONABLE = (S.TRIAGE, S.CEKA_NA_PODKLADY, S.KOMPLETNI, S.PRIPRAVENO_MDT)

# The MDT is a meeting of KOC physicians (no separate role), so MDT-side actions belong to KOC_PHYSICIAN.
_RULES: tuple[_Rule, ...] = (
    _Rule("accept", S.ODESLANO, frozenset({_COORD}), S.TRIAGE, _COORD, notify=(((_GP,), "case.accepted"),)),
    _Rule(
        "request_documents",
        S.TRIAGE,
        frozenset({_COORD}),
        S.CEKA_NA_PODKLADY,
        _COORD,
        _g_request_docs,
        notify=(((_GP,), "case.documents_requested"),),
    ),
    _Rule("mark_complete", S.TRIAGE, frozenset({_COORD}), S.KOMPLETNI, _DOC, _g_complete),
    _Rule("docs_received", S.CEKA_NA_PODKLADY, frozenset({_COORD, _SYS}), S.KOMPLETNI, _DOC, _g_docs_received),
    _Rule("missing_found", S.KOMPLETNI, frozenset({_COORD, _DOC}), S.CEKA_NA_PODKLADY, _COORD, _g_reason),
    _Rule(
        "mark_ready_mdt",
        S.KOMPLETNI,
        frozenset({_DOC}),
        S.PRIPRAVENO_MDT,
        _DOC,
        _g_ready,
        notify=(((_DOC,), "case.ready_for_mdt"),),
    ),
    _Rule("reopen", S.PRIPRAVENO_MDT, frozenset({_DOC}), S.KOMPLETNI, _DOC, _g_reason),
    _Rule(
        "record_mdt_conclusion",
        S.PRIPRAVENO_MDT,
        frozenset({_DOC}),
        S.ZAVER_MDT,
        _COORD,
        _g_conclusion,
        set_={"conclusion_confirmed": True},
    ),
    _Rule(
        "send_feedback",
        S.ZAVER_MDT,
        frozenset({_COORD}),
        S.ZPETNA_VAZBA_ODESLANA,
        _GP,
        _g_feedback,
        notify=(((_GP,), "feedback.sent"), ((Role.REVIEWER,), "feedback.sent_reviewer")),
    ),
    _Rule(
        "delivery_confirmed",
        S.ZPETNA_VAZBA_ODESLANA,
        frozenset({_SYS}),
        None,
        _COORD,
        _g_receipt,
        set_={"delivery_receipt": True},
    ),
    _Rule("gp_opened", S.ZPETNA_VAZBA_ODESLANA, frozenset({_GP, _SYS}), None, None, audit_action="read"),
    _Rule("close", S.ZPETNA_VAZBA_ODESLANA, frozenset({_COORD}), S.UZAVRENO, None, _g_closed),
    *(_Rule("postpone", s, frozenset({_COORD}), None, Role.EXTERNAL_WORKPLACE, _g_postpone) for s in _POSTPONABLE),
    *(_Rule("resume", s, frozenset({_COORD}), None, None, _g_resume) for s in _POSTPONABLE),
)

CASE_EVENTS = ("submit", *dict.fromkeys(r.event for r in _RULES))
_BY_KEY = {(r.event, r.from_state): r for r in _RULES}


def _fail(code: str, detail: str) -> TransitionError:
    return TransitionError(code, detail)


def _guard_failed(problem: str | GuardFailure) -> TransitionError:
    if isinstance(problem, GuardFailure):
        return TransitionError("guard_failed", problem.detail, problem.blocking_items)
    return TransitionError("guard_failed", problem)


def _events(
    rule: _Rule, old: Case | None, new: Case, actor: Role, ctx: CaseContext, now: datetime
) -> tuple[DomainEvent, ...]:
    payload: dict[str, object] = {
        "case_id": new.id,
        "event": rule.event,
        "from": old.state.value if old else None,
        "to": new.state.value,
        "baton_role": new.baton_role.value if new.baton_role else None,
        "bucket": new.bucket.value,
        "actor_role": actor.value,
    }
    if ctx.reason:
        payload["reason"] = ctx.reason
    if rule.event == "mark_ready_mdt" and ctx.readiness:
        payload["waived"] = [{"item": w.item, "by": w.by, "reason": w.reason} for w in ctx.readiness.waived]
    if rule.event == "record_mdt_conclusion":
        payload["confirmed_by"] = ctx.confirmed_by
    if rule.event == "delivery_confirmed":
        payload["receipt_id"] = ctx.receipt_id
    if rule.event == "postpone":
        payload["resume_on"] = ctx.resume_on
    audit = DomainEvent(EventKind.AUDIT, rule.audit_action, now, payload)
    notes = tuple(
        DomainEvent(EventKind.NOTIFICATION, tpl, now, {"case_id": new.id}, recipients)
        for recipients, tpl in rule.notify
    )
    return (audit, *notes)


def _with_baton(case: Case, changes: dict[str, object], role: Role | None) -> dict[str, object]:
    changes["baton_role"] = role
    holder = case.baton_holder
    if holder is not None and holder.role is not role:
        changes["baton_holder"] = None  # the caller assigns a person who holds the new role
    return changes


def submit_referral(
    case_id: str,
    patient: Patient,
    actor: Role,
    ctx: CaseContext | None = None,
    now: datetime | None = None,
    mdt_start: datetime | None = None,
) -> TransitionResult:
    """The only transition that creates a case: GP sends the referral (state `odeslano`, baton: coordinator)."""
    ctx = ctx or CaseContext()
    now = now or clock.now()
    rule = _SUBMIT
    if actor not in rule.roles:
        raise _fail("forbidden_role", f"Role {actor.value!r} nemůže podat žádost")
    draft = Case(id=case_id, patient=patient, state=S.ODESLANO, opened_at=now, mdt_start=mdt_start)
    problem = rule.guard(draft, ctx, now) if rule.guard else None
    if problem:
        raise _guard_failed(problem)
    new = draft.model_copy(update={"baton_role": _COORD})
    return TransitionResult(new, _events(rule, None, new, actor, ctx, now))


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
        raise _fail("invalid_transition", f"Událost {event!r} není ve stavu {case.state.value!r} povolena")
    if case.odlozeny and event != "resume":
        raise _fail("case_postponed", "Případ je odložen; nejprve jej obnovte")
    if actor not in rule.roles:
        raise _fail("forbidden_role", f"Role {actor.value!r} nemůže provést akci {event!r}")
    problem = rule.guard(case, ctx, now) if rule.guard else None
    if problem:
        raise _guard_failed(problem)

    changes: dict[str, object] = dict(rule.set_)
    if rule.to is not None:
        changes["state"] = rule.to
    if event == "postpone":
        changes.update(odlozeny=True, resume_baton_role=case.baton_role, resume_on=ctx.resume_on)
        _with_baton(case, changes, Role.EXTERNAL_WORKPLACE)
    elif event == "resume":
        changes.update(odlozeny=False, resume_baton_role=None, resume_on=None)
        _with_baton(case, changes, case.resume_baton_role or case.baton_role)
    elif rule.baton is not None:
        _with_baton(case, changes, rule.baton)
    elif rule.to is S.UZAVRENO:
        _with_baton(case, changes, None)
    new = case.model_copy(update=changes)
    return TransitionResult(new, _events(rule, case, new, actor, ctx, now))
