"""Offline check that the golden set and the handover contract (`contracts/handover.schema.json`) agree.

P2 adds the extraction/assembly evaluation next to this file (`make eval`).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel

from app.domain.finding import FindingKind, Severity
from app.domain.handover import HandoverFields, HandoverStatus
from app.settings import REPO_ROOT

GOLDEN: dict[str, Any] = json.loads(
    (REPO_ROOT / "data/golden/expected_handover_2026-10-21.json").read_text(encoding="utf-8")
)
FIELD_MODELS: dict[str, type[BaseModel]] = {
    str(info.alias): info.annotation  # type: ignore[misc]
    for info in HandoverFields.model_fields.values()
}


def _doc_to_doc_id(value: Any) -> Any:
    """The golden file names the document key `doc`; the contract uses `doc_id`."""
    if isinstance(value, dict):
        return {("doc_id" if k == "doc" else k): _doc_to_doc_id(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_doc_to_doc_id(v) for v in value]
    return value


def test_field_keys_match_golden() -> None:
    assert set(GOLDEN["fields"]) == set(FIELD_MODELS)


def test_golden_statuses_are_in_the_enum() -> None:
    assert {f["status"] for f in GOLDEN["fields"].values()} <= {s.value for s in HandoverStatus}


@pytest.mark.parametrize("key", sorted(GOLDEN["fields"]))
def test_golden_values_fit_the_contract(key: str) -> None:
    golden = GOLDEN["fields"][key]
    field = {
        "status": golden["status"],
        "value": golden.get("value", golden.get("key_values")),
        "evidence": golden.get("evidence", []),
        "missing": golden.get("missing", []),
        "conflicts": golden.get("conflicts", []),
    }
    FIELD_MODELS[key].model_validate(_doc_to_doc_id(field))


def test_golden_findings_use_known_kinds_and_severities() -> None:
    findings = GOLDEN["expected_findings"] + GOLDEN["post_mdt_findings"]
    assert {f["kind"] for f in findings} <= {k.value for k in FindingKind}
    assert {f["severity"] for f in findings} <= {s.value for s in Severity}
