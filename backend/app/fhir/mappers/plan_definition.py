"""FHIR PlanDefinition (pathway template) → the FHIR-independent `PathwayTemplate` of the domain.

The template JSON lives in `iris/fhir/`. Ordering comes from `relatedAction` (`after-end`); due/SLA rules, place,
owner role and the MDT readiness items are Štafeta extensions (listed in `docs/fhir-mapping.md`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.domain.common import Role
from app.domain.pathway import Anchor, DueRule, PathwayStep, PathwayTemplate

EXT = "https://stafeta.example/fhir/StructureDefinition/"
EXT_DUE = EXT + "due-rule"
EXT_SLA = EXT + "sla-rule"
EXT_PLACE = EXT + "place"
EXT_OWNER = EXT + "owner-role"
EXT_READINESS = EXT + "mdt-required-items"


def _ext(node: Mapping[str, Any], url: str) -> Mapping[str, Any] | None:
    for e in node.get("extension", []):
        if e.get("url") == url:
            found: Mapping[str, Any] = e
            return found
    return None


def _ext_str(node: Mapping[str, Any], url: str) -> str | None:
    e = _ext(node, url)
    value = e.get("valueString") if e else None
    return value if isinstance(value, str) else None


def _rule(node: Mapping[str, Any], url: str) -> DueRule | None:
    """A rule extension has sub-extensions `anchor` (string), `days` (integer), `workdays` (boolean)."""
    e = _ext(node, url)
    if e is None:
        return None
    sub = {s["url"]: next(v for k, v in s.items() if k.startswith("value")) for s in e.get("extension", [])}
    anchor = str(sub["anchor"])
    days = int(sub["days"])
    workdays = bool(sub.get("workdays", False))
    if anchor in (Anchor.START, Anchor.MDT):
        return DueRule(Anchor(anchor), days, workdays)
    if anchor.startswith("action:"):
        return DueRule(Anchor.STEP, days, workdays, step_id=anchor.removeprefix("action:"))
    raise ValueError(f"unknown due-rule anchor {anchor!r}")


def plan_definition_to_template(plan: Mapping[str, Any]) -> PathwayTemplate:
    if plan.get("resourceType") != "PlanDefinition":
        raise ValueError("not a PlanDefinition")
    readiness = _ext(plan, EXT_READINESS)
    if readiness is None:
        raise ValueError("PlanDefinition has no MDT readiness items")
    steps: list[PathwayStep] = []
    for a in plan["action"]:
        after: list[str] = []
        for rel in a.get("relatedAction", []):
            if rel["relationship"] != "after-end":
                raise ValueError(f"unsupported relationship {rel['relationship']!r}")
            after.append(rel["actionId"])
        due = _rule(a, EXT_DUE)
        if due is None:
            raise ValueError(f"action {a['id']!r} has no due-rule")
        owner = _ext_str(a, EXT_OWNER)
        steps.append(
            PathwayStep(
                id=a["id"],
                code=a["code"][0]["coding"][0]["code"],
                title=a["title"],
                owner_role=Role(owner) if owner else Role.COORDINATOR,
                location=_ext_str(a, EXT_PLACE),
                due=due,
                after=tuple(after),
                sla=_rule(a, EXT_SLA),
            )
        )
    return PathwayTemplate(
        id=plan["id"],
        title=plan["title"],
        steps=tuple(steps),
        mdt_required_items=tuple(sub["valueString"] for sub in readiness["extension"]),
    )
