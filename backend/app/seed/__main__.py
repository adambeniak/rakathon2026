"""CLI: `python -m app.seed [--reset] [--scenario story|demo-start] [--data-dir PATH] [--no-index]`.

`make seed` = story scenario (idempotent). `make demo-reset` = `--reset --scenario demo-start`.
`--reset` deletes ONLY resources tagged `stafeta-demo` (everything the app wrote in demo mode) and the vector-index
rows (`Stafeta.DocChunk`) of the deleted documents. Unless `--no-index`, every seeded document is also chunked and
embedded (skipped when already indexed). Prints counts only — never names or other PHI.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

from app.domain.common import PartyRef, Role
from app.fhir.client import FhirClient
from app.fhir.errors import FhirError
from app.fhir.repository import FhirRepository
from app.fhir.systems import CS_TAG, DEMO_TAG_CODE
from app.iris.db import IrisPool
from app.iris.vector_store import VectorStore
from app.logging_config import configure_logging
from app.retrieval.embeddings import EmbeddingError, embedder_from_settings
from app.retrieval.indexing import DocumentIndexer
from app.seed.loader import DEFAULT_DATA_DIR, RESET_ORDER, Scenario, seed
from app.settings import get_settings

SEED_ACTOR = PartyRef(id="seed", display="Štafeta seed (systém)", role=Role.SYSTEM)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.seed", description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete all resources tagged stafeta-demo first")
    parser.add_argument("--scenario", type=Scenario, choices=list(Scenario), default=Scenario.STORY)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR, help="folder with the 13 DOCX reports")
    parser.add_argument("--no-index", action="store_true", help="do not embed documents into Stafeta.DocChunk")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    configure_logging(settings.log_level, json=settings.log_json)
    timeout = httpx.Timeout(max(settings.http_timeout_s, 60.0), connect=10.0)
    pool = IrisPool.from_settings(settings)
    store = VectorStore(pool, dim=settings.embedding_dim)
    try:
        async with httpx.AsyncClient(timeout=timeout, limits=httpx.Limits(max_connections=2)) as http:
            client = FhirClient(http, settings.fhir_base_url, settings.iris_user, settings.iris_password)
            repo = FhirRepository(client, SEED_ACTOR, tag_code=DEMO_TAG_CODE)
            print(f"FHIR server: {httpx.URL(settings.fhir_base_url).host} · scenario: {args.scenario}")
            if args.reset:
                # Ids only (no content is read): the chunks of these documents are deleted with them.
                documents = await repo.search(
                    "DocumentReference", {"_tag": f"{CS_TAG}|{DEMO_TAG_CODE}", "_count": "100"}
                )
                deleted = await repo.delete_by_tag(RESET_ORDER, DEMO_TAG_CODE)
                summary = ", ".join(f"{t} {n}" for t, n in deleted.items() if n)
                print(f"reset: deleted {summary or 'nothing'}")
                cleaned = await asyncio.to_thread(
                    store.delete_documents, [f"DocumentReference/{d['id']}" for d in documents]
                )
                print(f"reset: removed vector-index rows of {cleaned} documents")
            indexer = None if args.no_index else DocumentIndexer(store, embedder_from_settings(settings), repo)
            report = await seed(repo, args.scenario, data_dir=args.data_dir, indexer=indexer)
    finally:
        pool.close_all()
    for line in report.lines():
        print(line)
    print(f"seed done: {report.total_created} created, {report.chunks_indexed} chunks indexed")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return asyncio.run(run(args))
    except EmbeddingError as exc:
        print(f"seed failed: {exc}", file=sys.stderr)
        return 1
    except FhirError as exc:
        print(f"seed failed: {exc}", file=sys.stderr)
        for issue in exc.issues:  # codes and FHIRPath only: diagnostics may quote values (PHI)
            print(f"  {issue.severity} {issue.code} at {', '.join(issue.expression) or '?'}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
