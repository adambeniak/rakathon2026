"""Launched pathway -> FHIR CarePlan (instance of a PlanDefinition).

The CarePlan lists the step Tasks as activities. Its business key `<case id>.<plan key>` makes a relaunch of the
same pathway for the same case detectable (plan key = last segment of the PlanDefinition canonical url).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from app.fhir.client import Resource
from app.fhir.systems import SID_CAREPLAN


def plan_key(plan: Mapping[str, Any]) -> str:
    return str(plan["url"]).rstrip("/").rsplit("/", 1)[-1]


def care_plan_identifier(case_id: str, plan: Mapping[str, Any]) -> tuple[str, str]:
    return SID_CAREPLAN, f"{case_id}.{plan_key(plan)}"


def care_plan_to_fhir(
    *,
    case_id: str,
    plan: Mapping[str, Any],
    start_date: date,
    patient_reference: str,
    activity_references: Sequence[str],
    author: Resource,
    created: datetime,
) -> Resource:
    system, value = care_plan_identifier(case_id, plan)
    return {
        "resourceType": "CarePlan",
        "identifier": [{"system": system, "value": value}],
        "instantiatesCanonical": [str(plan["url"])],
        "status": "active",
        "intent": "plan",
        "title": str(plan.get("title", plan_key(plan))),
        "subject": {"reference": patient_reference},
        "author": author,
        "created": created.isoformat(),
        "period": {"start": start_date.isoformat()},
        "activity": [{"reference": {"reference": reference}} for reference in activity_references],
    }
