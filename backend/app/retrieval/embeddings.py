"""Embedding providers (owner: P1). Synchronous and CPU/network bound: call `embed` via `asyncio.to_thread`.

- `local` (default): fastembed ONNX `paraphrase-multilingual-MiniLM-L12-v2`, 384 dims, on the backend CPU.
  NEVER inside the 2 GB IRIS container. The model reads at most 128 tokens, so its chunk budget is 128 tokens of
  the chunk text (embedded without a title prefix: measured better ranking, docs/vector-search.md).
- `apim`: `EMBEDDING_MODEL` deployment via the APIM gateway with `dimensions=384` (text-embedding-3-*).

Every provider is wrapped in `CachedEmbedder` (bounded LRU keyed by sha256 of model id + text). Stored and query
vectors must come from the same model: `model_id` is written to `Stafeta.DocChunk.EmbeddingModel` and filtered on.
"""

from __future__ import annotations

import hashlib
import random
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import structlog

from app.settings import Settings

if TYPE_CHECKING:
    from tokenizers import Tokenizer

log = structlog.get_logger(__name__)

LOCAL_MAX_TOKENS = 128  # max_seq_length of paraphrase-multilingual-MiniLM-L12-v2
LOCAL_OVERLAP_CHARS = 60
APIM_MAX_CHARS = 800
APIM_OVERLAP_CHARS = 100
APIM_BATCH = 64
MAX_RETRIES = 4


@dataclass(frozen=True)
class ChunkBudget:
    """How `app.documents.chunking.chunk_document` sizes chunks for this embedder."""

    max_size: int
    overlap: int  # characters
    measure: Callable[[str], int]


class Embedder(Protocol):
    @property
    def model_id(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    def budget(self, prefix: str) -> ChunkBudget:
        """Chunk budget for texts embedded as `prefix + chunk`."""
        ...


class EmbeddingError(RuntimeError):
    """The embedding provider failed (model files missing, APIM error)."""


class LocalEmbedder:
    def __init__(self, model_name: str, *, dim: int, cache_dir: Path) -> None:
        self._model_name = model_name
        self._dim = dim
        self._cache_dir = cache_dir
        self._lock = threading.Lock()
        self._model: Any = None
        self._counter: Tokenizer | None = None

    @property
    def model_id(self) -> str:
        return f"local:{self._model_name}"

    @property
    def dim(self) -> int:
        return self._dim

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding
                from tokenizers import Tokenizer

                started = time.perf_counter()
                try:
                    model: Any = TextEmbedding(self._model_name, cache_dir=str(self._cache_dir))
                except Exception as exc:
                    raise EmbeddingError(f"cannot load local embedding model {self._model_name}") from exc
                # Independent copy without truncation, only for counting: the embedding tokenizer stays untouched.
                counter = Tokenizer.from_str(model.model.tokenizer.to_str())
                counter.no_truncation()
                self._counter = counter
                self._model = model
                log.info(
                    "embedding_model_loaded", model=self.model_id, ms=round((time.perf_counter() - started) * 1000)
                )
            return self._model

    def count_tokens(self, text: str) -> int:
        """Tokens incl. the special tokens the model adds, as the model would see them without truncation."""
        self._load()
        assert self._counter is not None  # noqa: S101 - set by _load
        return len(self._counter.encode(text).ids)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = [v.astype(float).tolist() for v in self._load().embed(list(texts), batch_size=32)]
        if vectors and len(vectors[0]) != self._dim:
            raise EmbeddingError(f"{self.model_id} returns {len(vectors[0])} dims, EMBEDDING_DIM is {self._dim}")
        return vectors

    def budget(self, prefix: str) -> ChunkBudget:
        return ChunkBudget(LOCAL_MAX_TOKENS, LOCAL_OVERLAP_CHARS, lambda text: self.count_tokens(prefix + text))


class ApimEmbedder:
    """OpenAI-compatible embeddings through the Azure APIM gateway (header `api-key`), retry on 429/5xx."""

    def __init__(self, settings: Settings, *, sleep: Callable[[float], None] = time.sleep) -> None:
        import openai

        key = settings.apim_api_key.get_secret_value()
        if not settings.apim_base_url or not key or not settings.embedding_model:
            raise EmbeddingError("EMBEDDING_PROVIDER=apim needs APIM_BASE_URL, APIM_API_KEY and EMBEDDING_MODEL")
        self._deployment = settings.embedding_model
        self._dim = settings.embedding_dim
        self._sleep = sleep
        self._client = openai.OpenAI(
            base_url=settings.apim_base_url, api_key=key, default_headers={"api-key": key}, max_retries=0, timeout=60
        )

    @property
    def model_id(self) -> str:
        return f"apim:{self._deployment}:{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), APIM_BATCH):
            out.extend(self._batch(list(texts[start : start + APIM_BATCH])))
        return out

    def _batch(self, texts: list[str]) -> list[list[float]]:
        import openai

        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self._client.embeddings.create(model=self._deployment, input=texts, dimensions=self._dim)
                return [list(d.embedding) for d in sorted(resp.data, key=lambda d: d.index)]
            except (openai.RateLimitError, openai.InternalServerError, openai.APITimeoutError) as exc:
                if attempt == MAX_RETRIES:
                    raise EmbeddingError(f"APIM embeddings failed after {attempt + 1} attempts") from exc
                delay = 2.0 * 2**attempt + random.uniform(0, 0.5)  # noqa: S311 - jitter, not cryptography
                log.warning("embedding_retry", attempt=attempt + 1, delay_s=round(delay, 1), error=type(exc).__name__)
                self._sleep(delay)
            except openai.OpenAIError as exc:
                raise EmbeddingError(f"APIM embeddings failed: {type(exc).__name__}") from exc
        raise AssertionError("unreachable")

    def budget(self, prefix: str) -> ChunkBudget:
        return ChunkBudget(APIM_MAX_CHARS, APIM_OVERLAP_CHARS, len)


class CachedEmbedder:
    """Bounded in-process LRU keyed by sha256(model_id, text); thread-safe."""

    def __init__(self, inner: Embedder, *, max_entries: int = 4096) -> None:
        self._inner = inner
        self._max = max_entries
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    @property
    def dim(self) -> int:
        return self._inner.dim

    def budget(self, prefix: str) -> ChunkBudget:
        return self._inner.budget(prefix)

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.model_id}\x00{text}".encode()).hexdigest()

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        keys = [self._key(t) for t in texts]
        found: dict[str, list[float]] = {}
        with self._lock:
            for k in keys:
                if k in self._cache:
                    self._cache.move_to_end(k)
                    found[k] = self._cache[k]
        missing = list(dict.fromkeys(k for k in keys if k not in found))
        if missing:
            first_text = {k: t for k, t in zip(keys, texts, strict=True)}
            vectors = self._inner.embed([first_text[k] for k in missing])
            with self._lock:
                for k, v in zip(missing, vectors, strict=True):
                    found[k] = v
                    self._cache[k] = v
                    self._cache.move_to_end(k)
                while len(self._cache) > self._max:
                    self._cache.popitem(last=False)
        self.hits += len(keys) - len(missing)
        self.misses += len(missing)
        return [found[k] for k in keys]


def embedder_from_settings(settings: Settings) -> CachedEmbedder:
    inner: Embedder
    if settings.embedding_provider == "apim":
        inner = ApimEmbedder(settings)
    else:
        inner = LocalEmbedder(
            settings.local_embedding_model, dim=settings.embedding_dim, cache_dir=settings.fastembed_cache_path
        )
    return CachedEmbedder(inner)
