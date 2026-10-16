"""Latency of the IRIS retrieval layer, for docs/vector-search.md: `make vector-bench` (SCALE=10000 adds a scale run).

Runs against the seeded demo case. Prints p50 / p95 in milliseconds per step; no document text. The scale run
inserts N synthetic 384-dim rows under a throwaway patient and model id, compares HNSW with an exact scan, and
deletes them again.
"""

from __future__ import annotations

import asyncio
import math
import os
import statistics
import time
import uuid
from collections.abc import Callable
from datetime import date, timedelta

from app.iris.db import IrisPool
from app.iris.vector_store import SCOPE_WHERE, ChunkRow, VectorStore, as_of_params, vector_literal
from app.retrieval.embeddings import embedder_from_settings
from app.retrieval.search import HybridRetriever, query_stems, text_query
from app.settings import get_settings
from tests.eval.ask_cases import AS_OF, ASK_CASES

RUNS = 30


def timed(fn: Callable[[], object], runs: int = RUNS) -> tuple[float, float]:
    samples = []
    for _ in range(runs):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    return statistics.median(samples), samples[int(0.95 * (len(samples) - 1))]


def main() -> None:
    settings = get_settings()
    pool = IrisPool.from_settings(settings)
    store = VectorStore(pool, dim=settings.embedding_dim)
    embedder = embedder_from_settings(settings)
    retriever = HybridRetriever(store, embedder)
    model = embedder.model_id
    with pool.cursor() as cur:
        cur.execute("SELECT TOP 1 PatientRef FROM Stafeta.DocChunk WHERE EmbeddingModel = ?", [model])
        row = cur.fetchone()
        patient = str(row[0]) if row else ""
        cur.execute("SELECT COUNT(*) FROM Stafeta.DocChunk WHERE EmbeddingModel = ?", [model])
        total = int(cur.fetchone()[0])  # type: ignore[index]
    question = ASK_CASES[0].question
    vector = embedder.embed([question])[0]
    authored_before, received_until = as_of_params(AS_OF)
    params = [vector_literal(vector, store.dim), patient, model, authored_before, received_until]

    def sql(text: str, values: list[object]) -> Callable[[], object]:
        def run() -> object:
            with pool.cursor() as cur:
                cur.execute(text, values)
                return [tuple(r) for r in cur.fetchall()]

        return run

    columns = "TOP 10 %ID, VECTOR_COSINE(Embedding, TO_VECTOR(?, DOUBLE)) AS Score"
    hnsw = f"SELECT {columns} FROM Stafeta.DocChunk WHERE {SCOPE_WHERE} ORDER BY Score DESC"  # noqa: S608
    exact = f"SELECT {columns} FROM %IGNOREINDEX DocChunkHNSW Stafeta.DocChunk WHERE {SCOPE_WHERE} ORDER BY Score DESC"  # noqa: S608
    assert [r[0] for r in sql(hnsw, params)()] == [r[0] for r in sql(exact, params)()], "HNSW != exact"
    query = text_query(query_stems(question))
    steps: list[tuple[str, Callable[[], object]]] = [
        ("IRIS round trip (SELECT 1)", sql("SELECT 1", [])),
        ("query embedding (local ONNX, uncached)", lambda: embedder._inner.embed([question])),
        ("vector leg, HNSW (ACORN-1 filter)", sql(hnsw, params)),
        ("vector leg, exact scan (%IGNOREINDEX)", sql(exact, params)),
        ("full-text leg (iFind, 2 indexes)", lambda: store.text_search(
            patient_ref=patient, query=query, as_of=AS_OF, k=50, model=model)),
        ("hybrid search end to end (embed + 2 SQL + RRF)", lambda: asyncio.run(retriever.search(
            patient_ref=patient, question=question, as_of=AS_OF, k=settings.ask_top_k))),
    ]  # fmt: skip
    print(f"rows in Stafeta.DocChunk for {model}: {total}")  # noqa: T201
    print(f"{'step':<48} {'p50 ms':>8} {'p95 ms':>8}")  # noqa: T201
    for name, fn in steps:
        fn()  # warm up
        p50, p95 = timed(fn)
        print(f"{name:<48} {p50:>8.1f} {p95:>8.1f}")  # noqa: T201
    scale = int(os.environ.get("SCALE", "0"))
    if scale:
        scale_run(pool, store, scale, sql, hnsw, exact)
    pool.close_all()


def synthetic(seed: int, dim: int) -> list[float]:
    raw = [math.sin(seed * 0.7311 + i * 1.37) + math.cos(seed * 0.0173 * i) for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


def scale_run(
    pool: IrisPool,
    store: VectorStore,
    n: int,
    sql: Callable[[str, list[object]], Callable[[], object]],
    hnsw: str,
    exact: str,
) -> None:
    run = uuid.uuid4().hex[:8]
    patient, model = f"Patient/bench-{run}", f"bench:{run}"
    per_doc = 100
    refs = [f"DocumentReference/bench-{run}-{d}" for d in range(n // per_doc)]
    received = AS_OF - timedelta(days=3)
    started = time.perf_counter()
    try:
        for d, ref in enumerate(refs):
            store.replace_document(ref, [
                ChunkRow(ref, ref.rsplit("/", 1)[1], patient, i, "bench", date(2026, 10, 1), received, "x", 0, 1,
                         synthetic(d * per_doc + i, store.dim), model)
                for i in range(per_doc)
            ])  # fmt: skip
        print(f"\nscale run: inserted {n} rows in {time.perf_counter() - started:.0f} s")  # noqa: T201
        authored_before, received_until = as_of_params(AS_OF)
        params = [vector_literal(synthetic(-1, store.dim), store.dim), patient, model, authored_before, received_until]
        same = [r[0] for r in sql(hnsw, params)()] == [r[0] for r in sql(exact, params)()]  # type: ignore[attr-defined]
        print(f"top-10 identical (HNSW vs exact): {same}")  # noqa: T201
        for name, text in (("vector leg, HNSW (ACORN-1 filter)", hnsw), ("vector leg, exact scan", exact)):
            fn = sql(text, params)
            fn()
            p50, p95 = timed(fn, runs=15)
            print(f"{name + f' @ {n} rows':<48} {p50:>8.1f} {p95:>8.1f}")  # noqa: T201
    finally:
        store.delete_documents(refs)
        print(f"scale run: deleted {len(refs)} synthetic documents")  # noqa: T201


if __name__ == "__main__":
    main()
