"""Acceptance questions for "ask the case" and the recorded retrieval fixture (owner: P1, ADR-0004).

The fixture stores what IRIS hybrid search returned for each question at the MDT start, so the eval replays the
answer pipeline offline: recorded chunks -> cached LLM response (tests/fixtures/llm_cache) -> evidence lock.
Re-record with `make eval-ask-record` (live IRIS + local embeddings + APIM).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.iris.vector_store import ChunkHit
from app.retrieval.search import RetrievedChunk
from app.settings import PRAGUE, REPO_ROOT

CASE_ID = "rakathon-2026-prochazkova"
AS_OF = datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)
FIXTURE = REPO_ROOT / "backend" / "tests" / "fixtures" / "ask" / "retrieval.json"


@dataclass(frozen=True)
class AskCase:
    key: str
    question: str


ASK_CASES = (
    AskCase("anticoagulation", "Kdy byla vysazena antikoagulace před biopsií?"),
    AskCase("ecog", "Jaký je ECOG?"),
    AskCase("advice", "Jakou léčbu doporučujete?"),
    AskCase("histology", "Jaký je výsledek histologie?"),
    AskCase("after_as_of", "Co uvádí algeziologická zpráva?"),  # report 12 arrives on 26. 10.
    AskCase("allergy", "Má pacientka nějaké alergie?"),  # written only as "AA: neguje": must not be "není uvedeno"
)


def chunk_to_json(c: RetrievedChunk) -> dict[str, Any]:
    hit = asdict(c.hit)
    hit["authored_on"] = c.hit.authored_on.isoformat()
    hit["received_at"] = c.hit.received_at.isoformat()
    return {"hit": hit, "score": c.score, "vector_rank": c.vector_rank, "text_rank": c.text_rank,
            "vector_score": c.vector_score}  # fmt: skip


def chunk_from_json(data: dict[str, Any]) -> RetrievedChunk:
    hit = dict(data["hit"])
    hit["authored_on"] = date.fromisoformat(hit["authored_on"])
    hit["received_at"] = datetime.fromisoformat(hit["received_at"])
    return RetrievedChunk(ChunkHit(**hit), data["score"], data["vector_rank"], data["text_rank"], data["vector_score"])


def load_fixture(path: Path = FIXTURE) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def write_fixture(data: dict[str, Any], path: Path = FIXTURE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
