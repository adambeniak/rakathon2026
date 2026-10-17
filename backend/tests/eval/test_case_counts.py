"""The case header counters for the demo case, from the committed LLM cache (`make eval`, no network).

At the MDT start (21. 10. 2026): ECOG, TNM and e-mail are missing, C1/C2 conflict, the weight is stale. The report
12-13 are excluded and nothing is stale once the later reports are included.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from app.api.services.case_counts import count_handover
from app.extraction.handover.epicrisis import EPICRISIS_PROMPT_VERSION
from app.extraction.llm import CacheMissError, LLMClient
from app.settings import PRAGUE, Settings
from tests.eval.handover_eval import build, extract_all

MDT_START = datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)
LATER = datetime(2026, 10, 28, 8, 0, tzinfo=PRAGUE)


@pytest.fixture(scope="module")
def counts() -> dict[datetime, object]:
    settings = Settings()
    extraction = LLMClient.from_settings(settings)
    epicrisis = LLMClient.from_settings(settings, prompt_version=EPICRISIS_PROMPT_VERSION)

    async def run() -> dict[datetime, object]:
        _, facts = await extract_all(extraction)
        return {as_of: count_handover((await build(facts, epicrisis, as_of))[0]) for as_of in (MDT_START, LATER)}

    try:
        return asyncio.run(run())
    except CacheMissError as e:
        pytest.fail(f"LLM cache miss: {e}", pytrace=False)


def test_demo_counts_at_the_mdt_start(counts: dict[datetime, object]) -> None:
    result = counts[MDT_START]
    assert result is not None
    assert result.model_dump() == {"missing": 3, "conflict": 2, "stale": 1}  # type: ignore[attr-defined]


def test_demo_counts_after_the_later_reports(counts: dict[datetime, object]) -> None:
    result = counts[LATER]
    assert result is not None
    assert result.stale == 0  # type: ignore[attr-defined]
