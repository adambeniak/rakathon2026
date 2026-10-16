import copy

import pytest

from app.domain.common import Role
from app.domain.pathway import Anchor
from app.fhir.mappers.plan_definition import plan_definition_to_template
from tests.unit.domain.conftest import load_plan


def test_maps_steps_rules_and_readiness_items() -> None:
    t = plan_definition_to_template(load_plan())
    steps = {s.id: s for s in t.steps}
    assert next(s.id for s in t.steps) == "ct"
    assert steps["eus-fnb"].after == ("ct",)
    assert set(steps["mdt"].after) == {"ct", "histology", "labs"}
    assert steps["mdt"].owner_role is Role.KOC_PHYSICIAN
    assert steps["ct"].owner_role is Role.EXTERNAL_WORKPLACE
    assert steps["eus-fnb"].owner_role is Role.KOC_PHYSICIAN
    assert steps["ct"].due.anchor is Anchor.START
    assert steps["ct"].due.days == 6
    sla = steps["histology"].sla
    assert sla is not None
    assert sla.step_id == "eus-fnb"
    assert sla.days == 3
    assert sla.workdays
    assert "performance_status" in t.mdt_required_items


def test_rejects_non_plan_definition_and_unsupported_relationship() -> None:
    plan = load_plan()
    with pytest.raises(ValueError, match="PlanDefinition"):
        plan_definition_to_template({"resourceType": "Task"})
    bad = copy.deepcopy(plan)
    bad["action"][1]["relatedAction"][0]["relationship"] = "before-start"
    with pytest.raises(ValueError, match="relationship"):
        plan_definition_to_template(bad)


def test_missing_due_rule_rejected() -> None:
    bad = copy.deepcopy(load_plan())
    bad["action"][0]["extension"] = [e for e in bad["action"][0]["extension"] if not e["url"].endswith("due-rule")]
    with pytest.raises(ValueError, match="due-rule"):
        plan_definition_to_template(bad)
