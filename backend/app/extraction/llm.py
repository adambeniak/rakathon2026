"""The single LLM client: OpenAI-compatible SDK pointed at the Azure APIM gateway (owner: P2).

Retry with exponential backoff on 429/5xx/timeouts (max 4, honouring Retry-After), at most 2 concurrent calls,
JSON-schema output and a disk cache keyed by sha256(model, prompt version, system prompt, schema, user message).

STAFETA_LLM_CACHE=1 (default): cache only; a miss raises CacheMissError and nothing touches the network.
STAFETA_LLM_CACHE=0: a cache hit is used, a miss calls APIM and writes the cache.
To re-record an entry, delete its file.
The cache never stores headers or keys; entries contain only fictitious demo data.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import structlog
from pydantic import SecretStr

from app.extraction.prompt import PROMPT_VERSION
from app.settings import REPO_ROOT, Settings

log = structlog.get_logger(__name__)

DEFAULT_CACHE_DIR = REPO_ROOT / "backend" / "tests" / "fixtures" / "llm_cache"
# Deployment the committed cache was recorded with; used when LLM_MODEL_EXTRACT is not set (offline CI).
CACHE_MODEL = "gpt-6-1-sol-dz-eu"
MAX_RETRIES = 4
MAX_CONCURRENCY = 2


class CacheMissError(RuntimeError):
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
        prompt_version: str = PROMPT_VERSION,
        cache_only: bool = True,
        transport: Transport | None = None,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        persist: bool = True,
    ) -> None:
        """`persist=False`: live responses are not written to the cache (the API serving user questions)."""
        self.model = model
        self.persist = persist
        self.prompt_version = prompt_version
        self.cache_dir = cache_dir
        self.cache_only = cache_only
        self._transport = transport
        self._sem = asyncio.Semaphore(MAX_CONCURRENCY)
        self._sleep = sleep
        self.use_temperature = True

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        prompt_version: str = PROMPT_VERSION,
        model: str | None = None,
        persist: bool = True,
    ) -> LLMClient:
        """Extraction by default; `app.retrieval.ask` passes its own prompt version (separate cache keys)."""
        model = model or settings.llm_model_extract or CACHE_MODEL
        client = cls(
            model=model,
            prompt_version=prompt_version,
            cache_only=settings.stafeta_llm_cache,
            cache_dir=cache_dir,
            persist=persist,
        )
        if not settings.stafeta_llm_cache:
            client._transport = apim_transport(client, settings.apim_base_url, settings.apim_api_key)
        return client

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    async def complete_json(self, *, system: str, user: str, schema: dict[str, object], doc_id: str) -> str:
        key = cache_key(self.model, self.prompt_version, system, schema, user)
        path = self._path(key)
        if path.exists():
            return str(json.loads(path.read_text(encoding="utf-8"))["response_text"])
        if self.cache_only:
            raise CacheMissError(
                f"no cached response for {doc_id} ({key[:12]}); a human must run `STAFETA_LLM_CACHE=0 make eval`"
            )
        if self._transport is None:
            raise RuntimeError("no LLM transport configured (STAFETA_LLM_CACHE=0 needs APIM settings)")
        async with self._sem:
            text, usage = await self._with_retry(self._transport, system, user, schema, doc_id)
        json.loads(text)  # fail loudly before caching garbage
        if not self.persist:
            return text
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
        self, transport: Transport, system: str, user: str, schema: dict[str, object], doc_id: str
    ) -> tuple[str, dict[str, Any]]:
        attempt = 0
        while True:
            try:
                return await transport(system, user, schema, self.use_temperature)
            except RetryableError as e:
                if attempt >= MAX_RETRIES:
                    raise
                delay = e.retry_after if e.retry_after is not None else 2.0 * 2**attempt
                delay += random.uniform(0, 0.5)  # noqa: S311 - jitter, not cryptography
                log.warning("llm_retry", doc_id=doc_id, attempt=attempt + 1, delay_s=round(delay, 1), error=str(e))
                attempt += 1
                await self._sleep(delay)


def apim_transport(client: LLMClient, base_url: str, api_key: SecretStr) -> Transport:
    """Real transport via the openai SDK pointed at APIM (header `api-key`)."""
    import openai

    if not base_url or not api_key.get_secret_value():
        raise RuntimeError("APIM_BASE_URL and APIM_API_KEY must be set for live LLM calls")
    key = api_key.get_secret_value()
    sdk = openai.AsyncOpenAI(
        base_url=base_url, api_key=key, default_headers={"api-key": key}, max_retries=0, timeout=240.0
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
                log.warning("llm_temperature_rejected", model=client.model)
                client.use_temperature = False
                return await call(system, user, schema, False)
            raise
        except openai.RateLimitError as e:
            ra = e.response.headers.get("retry-after")
            raise RetryableError("429", float(ra) if ra and ra.replace(".", "").isdigit() else None) from e
        except openai.InternalServerError as e:
            raise RetryableError(f"{e.status_code}") from e
        except (openai.APITimeoutError, openai.APIConnectionError) as e:
            if "Name or service not known" in repr(e.__cause__) or "nodename nor servname" in repr(e.__cause__):
                # DNS failure: retrying cannot help; name the host (never the key) and stop.
                host = urlsplit(base_url).hostname
                raise RuntimeError(f"cannot resolve APIM host {host!r}; check APIM_BASE_URL") from e
            raise RetryableError(f"{type(e).__name__}: {e.__cause__!r}"[:200]) from e
        choice = resp.choices[0]
        if choice.finish_reason == "length":
            raise RuntimeError("LLM output truncated (finish_reason=length)")
        usage = resp.usage.model_dump() if resp.usage else {}
        return choice.message.content or "", usage

    return call
