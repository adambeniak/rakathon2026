"""Diagnostic pathway template (FHIR R4 PlanDefinition JSON) → Tasks, and the MDT readiness gate.

All due-date offsets in the template are DEMO ASSUMPTIONS, not clinical guidelines.
The PlanDefinition is read as plain data; no FHIR library is used here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import clock
from .events import Role
from .task_machine import Task

if TYPE_CHECKING:
    from .case_machine import Case

EXT = "https://stafeta.example/fhir/StructureDefinition/"
EXT_DUE = EXT + "due-rule"
EXT_SLA = EXT + "sla-rule"
EXT_PLACE = EXT + "place"
EXT_OWNER = EXT + "owner-role"
EXT_READINESS = EXT + "mdt-required-items"


def load_plan(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        plan: dict[str, Any] = json.load(fh)
    if plan.get("resourceType") != "PlanDefinition":
        raise ValueError("not a PlanDefinition")
    return plan


def _ext(node: Mapping[str, Any], url: str) -> Mapping[str, Any] | None:
    for e in node.get("extension", []):
        if e.get("url") == url:
            found: Mapping[str, Any] = e
            return found
    return None


def _ext_str(node: Mapping[str, Any], url: str) -> str | None:
    e = _ext(node, url)
    return e.get("valueString") if e else None


def _rule(node: Mapping[str, Any], url: str) -> dict[str, Any] | None:
    """A rule extension stores sub-extensions: anchor (string), days (integer), workdays (bool)."""
    e = _ext(node, url)
    if e is None:
        return None
    out: dict[str, Any] = {}
    for sub in e.get("extension", []):
        key = sub["url"]
        out[key] = next(v for k, v in sub.items() if k.startswith("value"))
    return out


def required_items(plan: Mapping[str, Any]) -> list[str]:
    e = _ext(plan, EXT_READINESS)
    if e is None:
        raise ValueError("plan has no MDT readiness items")
    return [sub["valueString"] for sub in e["extension"]]


def _resolve(
    rule: Mapping[str, Any], start: date, mdt: date | None, resolved: Mapping[str, date]
) -> date:
    anchor = rule["anchor"]
    if anchor == "start":
        base = start
    elif anchor == "mdt":
        if mdt is None:
            raise ValueError("pathway needs case.mdt_start")
        base = mdt
    elif anchor.startswith("action:"):
        ref = anchor.removeprefix("action:")
        if ref not in resolved:
            raise ValueError(f"anchor {ref!r} unresolved (cycle or unknown action)")
        base = resolved[ref]
    else:
        raise ValueError(f"unknown anchor {anchor!r}")
    days = int(rule["days"])
    return clock.add_workdays(base, days) if rule.get("workdays") else base + timedelta(days=days)


def instantiate(plan: Mapping[str, Any], case: Case, start_date: date) -> list[Task]:
    """Tasks for `case` in dependency order (every task comes after all it depends on)."""
    actions: list[Mapping[str, Any]] = list(plan["action"])
    ids = {a["id"] for a in actions}
    deps: dict[str, list[str]] = {}
    for a in actions:
        deps[a["id"]] = []
        for rel in a.get("relatedAction", []):
            ref = rel["actionId"]
            if ref not in ids:
                raise ValueError(f"action {a['id']!r} references unknown action {ref!r}")
            if rel["relationship"] != "after-end":
                raise ValueError(f"unsupported relationship {rel['relationship']!r}")
            deps[a["id"]].append(ref)

    mdt = case.mdt_start.astimezone(clock.TZ).date() if case.mdt_start else None
    order: list[str] = []
    pending = {a["id"]: a for a in actions}
    while pending:
        ready = [i for i in pending if all(d in order for d in deps[i])]
        if not ready:
            raise ValueError(f"dependency cycle among actions: {sorted(pending)}")
        for i in ready:  # stable: follows template order
            order.append(i)
            del pending[i]

    by_id = {a["id"]: a for a in actions}
    due: dict[str, date] = {}
    tasks: list[Task] = []
    for aid in order:
        a = by_id[aid]
        due_rule = _rule(a, EXT_DUE)
        if due_rule is None:
            raise ValueError(f"action {aid!r} has no due-rule")
        # anchors may point to any already-ordered action, even without relatedAction
        due[aid] = _resolve(due_rule, start_date, mdt, due)
        sla_rule = _rule(a, EXT_SLA)
        sla = _resolve(sla_rule, start_date, mdt, due) if sla_rule else None
        owner = _ext_str(a, EXT_OWNER)
        tasks.append(
            Task(
                id=f"{case.id}:{aid}",
                case_id=case.id,
                code=a["code"][0]["coding"][0]["code"],
                title=a["title"],
                owner_role=Role(owner) if owner else Role.COORD,
                place=_ext_str(a, EXT_PLACE),
                due=due[aid],
                depends_on=tuple(f"{case.id}:{d}" for d in deps[aid]),
                sla_due=sla,
                demo_assumption=True,
            )
        )
    return tasks


# --- MDT readiness gate ----------------------------------------------------------------------

# Handover field statuses (shared enum, see AGENTS.md). Only `missing` blocks the gate; the rest
# is surfaced as a warning so a human decides.
BLOCKING = frozenset({"missing"})
SATISFIED = frozenset({"complete", "generated_with_citations"})


@dataclass(frozen=True)
class Waiver:
    item: str
    by_role: Role
    by: str  # user id
    reason: str


@dataclass(frozen=True)
class Readiness:
    ready: bool
    missing: tuple[str, ...]  # blocking and NOT waived
    waived: tuple[Waiver, ...]
    warnings: tuple[str, ...] = ()  # items present but partial/stale/conflicting


def readiness_gate(
    statuses: Mapping[str, str], required: Sequence[str], waivers: Sequence[Waiver] = ()
) -> Readiness:
    """Gate for `pripraveno_mdt`. Items absent from `statuses` count as missing.

    Waivers are valid only from a physician (KOC_DOC) with a non-empty reason; anything else
    raises ValueError. A waiver for an item that is not blocking is ignored.
    """
    for w in waivers:
        if w.item not in required:
            raise ValueError(f"waiver for unknown item {w.item!r}")
        if w.by_role is not Role.KOC_DOC:
            raise ValueError("only a physician may waive a readiness item")
        if not w.reason.strip():
            raise ValueError("waiver needs a reason")
    blocking = [i for i in required if statuses.get(i, "missing") in BLOCKING]
    waived_by_item = {w.item: w for w in waivers}
    missing = tuple(i for i in blocking if i not in waived_by_item)
    waived = tuple(waived_by_item[i] for i in blocking if i in waived_by_item)
    warnings = tuple(i for i in required if i not in blocking and statuses.get(i) not in SATISFIED)
    return Readiness(not missing, missing, waived, warnings)
