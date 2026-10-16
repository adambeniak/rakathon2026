"""OpenAI-compatible client for the Azure APIM gateway, with retry, concurrency limit and disk cache.

STAFETA_LLM_CACHE=1 (default): cache only, a miss raises CacheMiss and nothing touches the network.
STAFETA_LLM_CACHE=0: cache hit is used, a miss calls APIM and writes the cache.
STAFETA_LLM_REFRESH=1 (with CACHE=0): ignore existing entries and overwrite them.
The cache never stores headers or keys; entries contain only fictitious demo data.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("stafeta.llm")

DEFAULT_CACHE_DIR = Path(__file__).parent / "tests" / "fixtures" / "llm_cache"
MAX_RETRIES = 4
MAX_CONCURRENCY = 2


class CacheMiss(RuntimeError):
    pass


class RetryableError(RuntimeError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def cache_key(model: str, prompt_version: str, system: str, schema: dict[str, object], user: str) -> str:
    h = hashlib.sha256()
    for part in (model, prompt_version, system, json.dumps(schema, sort_keys=True, ensure_ascii=False), user):
        h.update(part.encode())
        h.update(b"\x00")
    return h.hexdigest()


# Transport = one raw call returning (response_text, usage). Raises RetryableError for 429/5xx/timeouts.
Transport = Callable[[str, str, dict[str, object], bool], Awaitable[tuple[str, dict[str, Any]]]]


class LLMClient:
    def __init__(
        self,
        *,
        model: str,
        prompt_version: str,
        transport: Transport | None = None,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        cache_only: bool | None = None,
        refresh: bool | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.model = model
        self.prompt_version = prompt_version
        self.cache_dir = cache_dir
        self.cache_only = os.environ.get("STAFETA_LLM_CACHE", "1") != "0" if cache_only is None else cache_only
        self.refresh = os.environ.get("STAFETA_LLM_REFRESH") == "1" if refresh is None else refresh
        self._transport = transport
        self._sem = asyncio.Semaphore(MAX_CONCURRENCY)
        self._sleep = sleep
        self.use_temperature = True

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    async def complete_json(self, *, system: str, user: str, schema: dict[str, object], doc_id: str) -> str:
        key = cache_key(self.model, self.prompt_version, system, schema, user)
        path = self._path(key)
        if path.exists() and not (self.refresh and not self.cache_only):
            return str(json.loads(path.read_text(encoding="utf-8"))["response_text"])
        if self.cache_only:
            raise CacheMiss(f"no cached response for {doc_id} ({key[:12]}); run with STAFETA_LLM_CACHE=0")
        if self._transport is None:
            self._transport = apim_transport(self)
        async with self._sem:
            text, usage = await self._with_retry(system, user, schema, doc_id)
        json.loads(text)  # fail loudly before caching garbage
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        entry = {
            "key": key,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "doc_id": doc_id,
            "created": datetime.now(UTC).isoformat(timespec="seconds"),
            "usage": usage,
            "response_text": text,
        }
        path.write_text(json.dumps(entry, ensure_ascii=False, indent=1), encoding="utf-8")
        return text

    async def _with_retry(
        self, system: str, user: str, schema: dict[str, object], doc_id: str
    ) -> tuple[str, dict[str, Any]]:
        assert self._transport is not None
        attempt = 0
        while True:
            try:
                return await self._transport(system, user, schema, self.use_temperature)
            except RetryableError as e:
                if attempt >= MAX_RETRIES:
                    raise
                delay = e.retry_after if e.retry_after is not None else 2.0 * 2**attempt
                delay += random.uniform(0, 0.5)
                log.warning("llm retry", extra={"doc_id": doc_id, "attempt": attempt + 1, "delay": round(delay, 1)})
                attempt += 1
                await self._sleep(delay)


def apim_transport(client: LLMClient) -> Transport:
    """Real transport via the openai SDK pointed at APIM (header `api-key`)."""
    import openai  # lazy: offline tests do not need the SDK

    base_url = os.environ["APIM_BASE_URL"]
    api_key = os.environ["APIM_API_KEY"]
    sdk = openai.AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
        default_headers={"api-key": api_key},
        max_retries=0,
        timeout=240.0,
    )

    async def call(
        system: str, user: str, schema: dict[str, object], use_temperature: bool
    ) -> tuple[str, dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "model": client.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "facts", "strict": True, "schema": schema},
            },
            "max_completion_tokens": 32000,
        }
        if use_temperature:
            kwargs["temperature"] = 0
        try:
            resp = await sdk.chat.completions.create(**kwargs)
        except openai.BadRequestError as e:
            if use_temperature and "temperature" in str(e).lower():
                log.warning("deployment rejects temperature; retrying without it")
                client.use_temperature = False
                return await call(system, user, schema, False)
            raise
        except openai.RateLimitError as e:
            ra = e.response.headers.get("retry-after")
            raise RetryableError("429", float(ra) if ra and ra.replace(".", "").isdigit() else None) from e
        except openai.InternalServerError as e:
            raise RetryableError(f"{e.status_code}") from e
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            raise RetryableError(type(e).__name__) from e
        choice = resp.choices[0]
        if choice.finish_reason == "length":
            raise RuntimeError("LLM output truncated (finish_reason=length)")
        usage = resp.usage.model_dump() if resp.usage else {}
        return choice.message.content or "", usage

    return call
