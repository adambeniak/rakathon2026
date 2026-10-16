"""Record the "ask the case" eval fixtures live: `make eval-ask-record`.

Needs the seeded + indexed case in IRIS (`make seed`), the local embedding model and APIM (STAFETA_LLM_CACHE=0).
Writes tests/fixtures/ask/retrieval.json and the LLM responses into tests/fixtures/llm_cache. Prints statuses
and counts only.
"""

from __future__ import annotations

import asyncio
import sys

import httpx

from app.fhir.cases import CaseReader
from app.fhir.client import FhirClient
from app.fhir.repository import FhirRepository
from app.fhir.systems import DEMO_TAG_CODE
from app.iris.db import IrisPool
from app.iris.vector_store import VectorStore
from app.retrieval.ask import AskService, ask_llm_from_settings
from app.retrieval.embeddings import embedder_from_settings
from app.retrieval.search import HybridRetriever
from app.security.actor import SYSTEM_ACTOR
from app.settings import get_settings
from tests.eval.ask_cases import AS_OF, ASK_CASES, CASE_ID, FIXTURE, chunk_to_json, write_fixture


async def record() -> int:
    settings = get_settings()
    if settings.stafeta_llm_cache:
        print("set STAFETA_LLM_CACHE=0 to record", file=sys.stderr)  # noqa: T201
        return 2
    pool = IrisPool.from_settings(settings)
    retriever = HybridRetriever(VectorStore(pool, dim=settings.embedding_dim), embedder_from_settings(settings))
    llm = ask_llm_from_settings(settings, persist=True)
    fixture: dict[str, object] = {"case_id": CASE_ID, "as_of": AS_OF.isoformat(), "questions": {}}
    try:
        async with httpx.AsyncClient(timeout=120) as http:
            client = FhirClient(http, settings.fhir_base_url, settings.iris_user, settings.iris_password)
            repo = FhirRepository(client, SYSTEM_ACTOR, tag_code=DEMO_TAG_CODE)
            service = AskService(CaseReader(repo), retriever, llm, repo, top_k=settings.ask_top_k, model=llm.model)
            for case in ASK_CASES:
                result = await service.ask(CASE_ID, case.question, AS_OF)
                fixture["questions"][case.key] = {  # type: ignore[index]
                    "question": case.question,
                    "top_k": settings.ask_top_k,
                    "embedding_model": result.embedding_model,
                    "sources": [chunk_to_json(c) for c in result.sources],
                }
                print(f"{case.key:<16} {result.status.value:<16} sources {len(result.sources):>2}  "  # noqa: T201
                      f"sentences {len(result.sentences)}  dropped {len(result.dropped)}")  # fmt: skip
    finally:
        pool.close_all()
    write_fixture(fixture)
    print(f"wrote {FIXTURE}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(record()))
