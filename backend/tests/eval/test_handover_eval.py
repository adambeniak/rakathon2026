"""`make eval`: handover assembly vs the golden set, from the committed LLM cache (no network).

Gates: field status ≥ 14/15 (fields 7 and 14 via the C1/C2 rules), evidence validity 100 %, as-of leakage 0,
hallucinations 0, every epicrisis sentence cited, reports 12-13 excluded at 21. 10. and included at 28. 10.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import pytest

from app.extraction.handover.epicrisis import EPICRISIS_PROMPT_VERSION
from app.extraction.llm import CacheMissError, LLMClient
from app.settings import Settings
from tests.eval.handover_eval import FIELD_STATUS_GATE, format_table, merge_into_report, run


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    settings = Settings()
    extraction = LLMClient.from_settings(settings)
    epicrisis = LLMClient.from_settings(settings, prompt_version=EPICRISIS_PROMPT_VERSION)
    try:
        rep = asyncio.run(run(extraction, epicrisis))
    except CacheMissError as e:  # extraction prompt or normalisation changed: a human must refill the cache
        pytest.fail(f"LLM cache miss: {e}", pytrace=False)
    merge_into_report(rep)
    return rep


def test_print_handover_metrics(report: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    with capsys.disabled():
        sys.stdout.write("\n" + format_table(report) + "\n")


def test_field_status_gate(report: dict[str, Any]) -> None:
    assert report["metrics"]["field_status_correct"] >= FIELD_STATUS_GATE, report["field_status"]


def test_handover_evidence_validity_gate(report: dict[str, Any]) -> None:
    assert report["gates"]["evidence_validity_100"], report["evidence_problems"]


def test_handover_as_of_leakage_gate(report: dict[str, Any]) -> None:
    assert report["gates"]["as_of_leakage_0"], report["leakage_docs"]


def test_handover_hallucination_gate(report: dict[str, Any]) -> None:
    assert report["gates"]["hallucinations_0"], report["hallucination_details"]


def test_epicrisis_every_sentence_cited(report: dict[str, Any]) -> None:
    assert report["gates"]["epicrisis_cited"], report["epicrisis"]


def test_every_value_has_evidence(report: dict[str, Any]) -> None:
    assert report["gates"]["items_with_evidence"], report["item_problems"]


def test_reports_12_13_excluded_then_included(report: dict[str, Any]) -> None:
    assert report["gates"]["as_of_rule"], report["as_of_rule"]


def test_acceptance_statuses(report: dict[str, Any]) -> None:
    fields = report["handover"]["fields"]
    assert fields["9_performance_status"]["status"] == "missing"
    assert fields["9_performance_status"]["missing_items"][0]["suggested_owner"] == "koc_physician"
    assert fields["10_weight_height"]["status"] == "stale"
    assert fields["5_mdt_question"]["status"] == "needs_clarification"
