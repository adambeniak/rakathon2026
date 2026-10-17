from __future__ import annotations

import asyncio

import pytest

from app.domain.handover import Handover
from app.extraction.handover.epicrisis import EPICRISIS_PROMPT_VERSION
from app.extraction.llm import LLMClient
from app.settings import Settings
from tests.eval.handover_eval import AS_OF, build, extract_all


@pytest.fixture(scope="session")
def story_handover() -> Handover:
    """The demo story's handover at the MDT start, from the committed LLM cache (offline, no network)."""
    settings = Settings(_env_file=None)
    extraction = LLMClient.from_settings(settings)
    epicrisis = LLMClient.from_settings(settings, prompt_version=EPICRISIS_PROMPT_VERSION)

    async def run() -> Handover:
        _, facts = await extract_all(extraction)
        handover, _ = await build(facts, epicrisis, AS_OF)
        return handover

    return asyncio.run(run())
