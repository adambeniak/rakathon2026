"""Extraction pipeline: ONE LLM call per document, then the evidence lock, then the as-of filter (owner: P2)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import structlog
from pydantic import ValidationError

from app.documents.normalize import NormalizedDoc
from app.domain.evidence import Fact
from app.extraction.lock import Rejected, evidence_lock, filter_as_of
from app.extraction.prompt import SYSTEM_PROMPT, build_user_message
from app.extraction.values import RESPONSE_SCHEMA, RawFact

log = structlog.get_logger(__name__)


class CompletionClient(Protocol):
    async def complete_json(self, *, system: str, user: str, schema: dict[str, object], doc_id: str) -> str: ...


@dataclass(frozen=True)
class DocExtraction:
    doc_id: str
    raw: tuple[RawFact, ...]
    accepted: tuple[Fact, ...]
    rejected: tuple[Rejected, ...]


def parse_response(text: str) -> tuple[list[RawFact], list[Rejected]]:
    data = json.loads(text)
    raws: list[RawFact] = []
    bad: list[Rejected] = []
    for item in data.get("facts", []):
        try:
            raws.append(RawFact.model_validate(item))
        except ValidationError as e:
            bad.append(Rejected("schema_invalid", None, str(e.errors()[:1])))
    return raws, bad


def lock_all(doc: NormalizedDoc, raws: Sequence[RawFact]) -> tuple[list[Fact], list[Rejected]]:
    accepted: list[Fact] = []
    rejected: list[Rejected] = []
    seen: set[str] = set()
    for raw in raws:
        result = evidence_lock(raw, doc)
        if isinstance(result, Rejected):
            rejected.append(result)
            # IDs and reasons only: never log the quote or the value (PHI).
            log.info("fact_rejected", doc_id=doc.doc_id, fact_type=str(raw.type), reason=result.reason)
        elif result.fact.id not in seen:
            seen.add(result.fact.id)
            accepted.append(result.fact)
    return accepted, rejected


async def extract_facts(doc: NormalizedDoc, client: CompletionClient) -> DocExtraction:
    """ONE LLM call per document, then the evidence lock."""
    text = await client.complete_json(
        system=SYSTEM_PROMPT,
        user=build_user_message(doc),
        schema=RESPONSE_SCHEMA,
        doc_id=doc.doc_id,
    )
    raws, bad = parse_response(text)
    accepted, rejected = lock_all(doc, raws)
    return DocExtraction(doc.doc_id, tuple(raws), tuple(accepted), tuple(bad + rejected))


async def extract_case(
    docs: Mapping[str, NormalizedDoc], client: CompletionClient, as_of: datetime
) -> tuple[list[DocExtraction], list[Fact]]:
    """Extract every document; return per-document results and the facts known at `as_of`.

    Backend path: received_at is required (unknown received time -> document excluded, AGENTS rule 4).
    """
    results = list(await asyncio.gather(*(extract_facts(d, client) for d in docs.values())))
    accepted = [f for r in results for f in r.accepted]
    return results, filter_as_of(accepted, dict(docs), as_of, require_received=True)
