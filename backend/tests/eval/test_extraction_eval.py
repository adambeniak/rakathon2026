"""`make eval`: extraction vs the golden set from the committed LLM cache (STAFETA_LLM_CACHE=1 -> no network).

The report goes to eval/report.json (repo root) and the metric table to the terminal.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import pytest

from app.extraction.llm import CacheMissError, LLMClient
from app.settings import Settings
from tests.eval.extraction_eval import RECALL_TARGET, format_table, run, write_report


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    settings = Settings()
    client = LLMClient.from_settings(settings)
    try:
        rep = asyncio.run(run(client, client.model))
    except CacheMissError as e:  # prompt or normalisation changed: a human must refill the cache
        pytest.fail(f"LLM cache miss: {e}", pytrace=False)
    write_report(rep)
    return rep


def test_print_metrics(report: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    with capsys.disabled():
        sys.stdout.write("\n" + format_table(report) + "\n")


def test_evidence_validity_gate(report: dict[str, Any]) -> None:
    assert report["gates"]["evidence_validity_100"], report["metrics"]


def test_hallucination_gate(report: dict[str, Any]) -> None:
    assert report["gates"]["hallucinations_0"], report["hallucination_details"]


def test_as_of_leakage_gate(report: dict[str, Any]) -> None:
    assert report["gates"]["as_of_leakage_0"], report["metrics"]
    assert report["metrics"]["docs_received_unknown"] == 0  # backend path: received_at always known


def test_key_value_recall(report: dict[str, Any]) -> None:
    assert report["metrics"]["key_value_recall"] >= RECALL_TARGET, report["misses"]


def test_injection_smoke(report: dict[str, Any]) -> None:
    assert report["injection_smoke"]["passed"], report["injection_smoke"]
