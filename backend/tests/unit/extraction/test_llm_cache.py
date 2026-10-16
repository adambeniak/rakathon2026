from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app.extraction.llm import MAX_RETRIES, CacheMissError, LLMClient, RetryableError, cache_key

SCHEMA: dict[str, object] = {"type": "object", "b": 1, "a": 2}


def test_cache_key_stable_and_sensitive() -> None:
    k = cache_key("m", "v1", "sys", SCHEMA, "doc")
    assert k == cache_key("m", "v1", "sys", {"a": 2, "type": "object", "b": 1}, "doc")  # key order irrelevant
    assert k != cache_key("m2", "v1", "sys", SCHEMA, "doc")
    assert k != cache_key("m", "v2", "sys", SCHEMA, "doc")
    assert k != cache_key("m", "v1", "sys", SCHEMA, "doc ")


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


async def _no_sleep(_: float) -> None:
    return None


def test_cache_only_miss_raises(tmp_path: Path) -> None:
    async def transport(*_: Any) -> tuple[str, dict[str, Any]]:
        raise AssertionError("network must not be touched")

    c = LLMClient(model="m", prompt_version="v", transport=transport, cache_dir=tmp_path, cache_only=True)
    with pytest.raises(CacheMissError):
        _run(c.complete_json(system="s", user="u", schema=SCHEMA, doc_id="d"))


def test_miss_calls_and_writes_then_cache_only_hits(tmp_path: Path) -> None:
    calls = 0

    async def transport(*_: Any) -> tuple[str, dict[str, Any]]:
        nonlocal calls
        calls += 1
        return '{"facts": []}', {"total_tokens": 1}

    live = LLMClient(model="m", prompt_version="v", transport=transport, cache_dir=tmp_path, cache_only=False)
    assert _run(live.complete_json(system="s", user="u", schema=SCHEMA, doc_id="d")) == '{"facts": []}'
    (entry,) = tmp_path.glob("*.json")
    stored = json.loads(entry.read_text())
    assert stored["doc_id"] == "d"
    assert "api" not in json.dumps(stored).lower().replace("api_", "")
    offline = LLMClient(model="m", prompt_version="v", cache_dir=tmp_path, cache_only=True)
    assert _run(offline.complete_json(system="s", user="u", schema=SCHEMA, doc_id="d")) == '{"facts": []}'
    assert calls == 1


def test_retry_then_success(tmp_path: Path) -> None:
    attempts: list[int] = []
    delays: list[float] = []

    async def sleep(d: float) -> None:
        delays.append(d)

    async def transport(*_: Any) -> tuple[str, dict[str, Any]]:
        attempts.append(1)
        if len(attempts) < 3:
            raise RetryableError("429", retry_after=None)
        return '{"facts": []}', {}

    c = LLMClient(model="m", prompt_version="v", transport=transport, cache_dir=tmp_path, cache_only=False, sleep=sleep)
    _run(c.complete_json(system="s", user="u", schema=SCHEMA, doc_id="d"))
    assert len(attempts) == 3
    assert 2.0 <= delays[0] < 2.6
    assert 4.0 <= delays[1] < 4.6


def test_retry_gives_up_after_max(tmp_path: Path) -> None:
    async def transport(*_: Any) -> tuple[str, dict[str, Any]]:
        raise RetryableError("503")

    c = LLMClient(
        model="m", prompt_version="v", transport=transport, cache_dir=tmp_path, cache_only=False, sleep=_no_sleep
    )
    with pytest.raises(RetryableError):
        _run(c.complete_json(system="s", user="u", schema=SCHEMA, doc_id="d"))
    assert MAX_RETRIES == 4


def test_retry_after_honoured(tmp_path: Path) -> None:
    delays: list[float] = []

    async def sleep(d: float) -> None:
        delays.append(d)

    n = 0

    async def transport(*_: Any) -> tuple[str, dict[str, Any]]:
        nonlocal n
        n += 1
        if n == 1:
            raise RetryableError("429", retry_after=7.0)
        return "{}", {}

    c = LLMClient(model="m", prompt_version="v", transport=transport, cache_dir=tmp_path, cache_only=False, sleep=sleep)
    _run(c.complete_json(system="s", user="u", schema=SCHEMA, doc_id="d"))
    assert 7.0 <= delays[0] < 7.6


def test_concurrency_at_most_two(tmp_path: Path) -> None:
    active = 0
    peak = 0

    async def transport(*_: Any) -> tuple[str, dict[str, Any]]:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return "{}", {}

    async def main() -> None:
        c = LLMClient(model="m", prompt_version="v", transport=transport, cache_dir=tmp_path, cache_only=False)
        await asyncio.gather(*(c.complete_json(system="s", user=f"u{i}", schema=SCHEMA, doc_id="d") for i in range(6)))

    _run(main())
    assert peak == 2


def test_invalid_json_not_cached(tmp_path: Path) -> None:
    async def transport(*_: Any) -> tuple[str, dict[str, Any]]:
        return "not json", {}

    c = LLMClient(model="m", prompt_version="v", transport=transport, cache_dir=tmp_path, cache_only=False)
    with pytest.raises(json.JSONDecodeError):
        _run(c.complete_json(system="s", user="u", schema=SCHEMA, doc_id="d"))
    assert not list(tmp_path.glob("*.json"))


def test_persist_false_answers_live_without_writing_the_cache(tmp_path: Path) -> None:
    async def transport(*_: Any) -> tuple[str, dict[str, Any]]:
        return '{"facts": []}', {}

    api = LLMClient(model="m", prompt_version="v", transport=transport, cache_dir=tmp_path, cache_only=False,
                    persist=False)  # fmt: skip
    assert _run(api.complete_json(system="s", user="question", schema=SCHEMA, doc_id="ask")) == '{"facts": []}'
    assert list(tmp_path.iterdir()) == []
