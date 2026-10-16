"""CLI: `python -m app.retrieval.reindex [--force]` (= `make index`).

(Re)builds `Stafeta.DocChunk` from every source-document DocumentReference in IRIS FHIR. Without `--force`, documents
already indexed with the current embedding model are skipped. Prints counts and ids only — never document text.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time

import httpx

from app.domain.common import PartyRef, Role
from app.fhir.client import FhirClient
from app.fhir.errors import FhirError
from app.fhir.repository import FhirRepository
from app.fhir.systems import DEMO_TAG_CODE, SID_SOURCE_DOCUMENT
from app.iris.db import IrisPool
from app.iris.vector_store import VectorStore
from app.logging_config import configure_logging
from app.retrieval.embeddings import EmbeddingError, embedder_from_settings
from app.retrieval.indexing import DocumentIndexer
from app.settings import get_settings

INDEX_ACTOR = PartyRef(id="vector-index", display="Štafeta vector index (systém)", role=Role.SYSTEM)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.retrieval.reindex", description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-embed documents that are already indexed")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.log_json)
    pool = IrisPool.from_settings(settings)
    embedder = embedder_from_settings(settings)
    timeout = httpx.Timeout(max(settings.http_timeout_s, 60.0), connect=10.0)
    started = time.perf_counter()
    total = 0
    try:
        async with httpx.AsyncClient(timeout=timeout, limits=httpx.Limits(max_connections=2)) as http:
            client = FhirClient(http, settings.fhir_base_url, settings.iris_user, settings.iris_password)
            tag = DEMO_TAG_CODE if settings.stafeta_demo_mode else None
            repo = FhirRepository(client, INDEX_ACTOR, tag_code=tag)
            indexer = DocumentIndexer(VectorStore(pool, dim=settings.embedding_dim), embedder, repo)
            documents = await repo.search(
                "DocumentReference", {"identifier": f"{SID_SOURCE_DOCUMENT}|", "_count": "100"}
            )
            if documents:
                await repo.audit_read([f"DocumentReference/{d['id']}" for d in documents], subtype="search-type")
            print(f"model: {indexer.model_id} · documents: {len(documents)}")
            for resource in documents:
                result = await indexer.index(resource, force=args.force)
                total += 0 if result.skipped else result.chunks
                note = f"skipped ({result.skipped})" if result.skipped else "indexed"
                print(f"{result.reference:<28} {result.doc_id:<40} {result.chunks:>3} chunks  {note}")
    finally:
        pool.close_all()
    print(f"index done: {total} chunks written in {time.perf_counter() - started:.1f} s")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return asyncio.run(run(args))
    except (FhirError, EmbeddingError) as exc:
        print(f"index failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
