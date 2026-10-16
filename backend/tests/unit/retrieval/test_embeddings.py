from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.retrieval.embeddings import ApimEmbedder, CachedEmbedder, EmbeddingError, LocalEmbedder, embedder_from_settings
from app.settings import Settings
from tests.unit.retrieval.conftest import FakeEmbedder


def test_cache_embeds_each_distinct_text_once(embedder: FakeEmbedder) -> None:
    cached = CachedEmbedder(embedder)

    first = cached.embed(["a", "b", "a"])
    second = cached.embed(["b", "c"])

    assert embedder.calls == [["a", "b"], ["c"]]
    assert first[0] == first[2]
    assert second[0] == first[1]
    assert (cached.hits, cached.misses) == (2, 3)
    assert cached.model_id == "fake:3"


def test_cache_is_bounded(embedder: FakeEmbedder) -> None:
    cached = CachedEmbedder(embedder, max_entries=2)
    cached.embed(["a", "b", "c"])
    cached.embed(["a"])
    assert embedder.calls[-1] == ["a"]  # evicted


def test_apim_provider_needs_its_settings(settings: Settings) -> None:
    with pytest.raises(EmbeddingError, match="EMBEDDING_MODEL"):
        ApimEmbedder(settings.model_copy(update={"embedding_provider": "apim"}))


def test_provider_selection(settings: Settings) -> None:
    local = embedder_from_settings(settings)
    assert local.model_id == "local:sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert local.dim == 384
    apim = embedder_from_settings(
        settings.model_copy(
            update={
                "embedding_provider": "apim",
                "apim_base_url": "https://apim.test/openai",
                "apim_api_key": SecretStr("k"),
                "embedding_model": "emb-dz-eu",
            }
        )
    )
    assert apim.model_id == "apim:emb-dz-eu:384"
    assert apim.budget("").max_size == 800


def test_local_model_load_failure_is_an_embedding_error(tmp_path: object) -> None:
    broken = LocalEmbedder("no/such-model", dim=384, cache_dir=tmp_path)  # type: ignore[arg-type]
    with pytest.raises(EmbeddingError, match="cannot load"):
        broken.embed(["x"])
