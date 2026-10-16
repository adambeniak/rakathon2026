"""Hybrid retrieval over `Stafeta.DocChunk` (owner: P1): IRIS vector search + IRIS iFind full text, fused by RRF.

Why hybrid: the small multilingual model alone ranked the key chunk of report 09 ("Apixaban vysazen …") 24th of 84
for "Kdy byla vysazena antikoagulace před biopsií?". Czech inflection is handled on the full-text leg with prefix
wildcards (`vysaz*`), because IRIS iFind has no Czech stemmer. Measurements: docs/vector-search.md.

Both legs use the same patient / model / as-of filter (`app.iris.vector_store.SCOPE_WHERE`).
"""

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import structlog

from app.iris.vector_store import ChunkHit, VectorStore
from app.retrieval.embeddings import Embedder

log = structlog.get_logger(__name__)

RRF_K = 60  # standard reciprocal-rank-fusion constant
GUARANTEED_PER_LEG = 3  # each leg's top 3 always reaches the result (a strong match in one leg only is kept)
VECTOR_CANDIDATES = 30
TEXT_CANDIDATES = 50  # a patient's as-of corpus is ~80 chunks: the OR query is rarely cut
MAX_STEMS = 12

_WORD = re.compile(r"[^\W\d_]+")
# Question and function words that would match almost every chunk (casefolded, >= 4 letters).
STOPWORDS = frozenset(
    {
        "jaký", "jaká", "jaké", "jakou", "jakého", "jakém", "jakým", "jakých", "který", "která", "které", "kterou",
        "kdy", "kde", "proč", "jestli", "zda", "zdali", "byla", "bylo", "byly", "jsou", "není", "nebyl", "nebyla",
        "před", "podle", "mezi", "nebo", "také", "jeho", "její", "jejich", "tento", "tato", "toto", "této", "tohoto",
        "pacient", "pacienta", "pacientka", "pacientky", "pacientce", "pacientku", "pacientkou", "prosím", "můžete",
        "může", "mají", "měla", "uvedeno", "uveden", "uvedena", "dokumentace", "dokumentaci", "všechny", "nějaký",
    }
)  # fmt: skip


# Czech anamnesis sections are written as abbreviations ("AA: neguje"), which neither the embedding model nor a
# stem of the question word can reach. Question stem -> extra full-text terms (czech-clinical-docs glossary).
SECTION_TERMS: dict[str, tuple[str, ...]] = {
    "aler": ("aa",),  # alergie, alergická -> AA (alergologická anamnéza)
    "lék": ("fa",), "léky": ("fa",), "léků": ("fa",), "medik": ("fa",), "farma": ("fa",), "užív": ("fa",),
    "komor": ("oa",), "onem": ("oa",), "anamn": ("oa",),
    "rodin": ("ra",), "sociál": ("sa",), "bydl": ("sa",), "žije": ("sa",),
    "prác": ("pa",), "pracov": ("pa",), "zaměs": ("pa",),
    "kouř": ("abusus",), "kuřá": ("abusus",), "alko": ("abusus",), "abúz": ("abusus",),
}  # fmt: skip


def stem(word: str) -> str:
    """Prefix stem for Czech inflection: 'vysazena' -> 'vysaz', 'antikoagulace' -> 'antikoa', 'ECOG' -> 'ecog'."""
    w = word.casefold()
    return w[: max(4, min(len(w) - 3, 7))]


def query_stems(question: str) -> list[str]:
    """Distinct stems of the content words (+ section abbreviations). Letters only: no iFind operator can get in."""
    stems: list[str] = []
    for word in _WORD.findall(question):
        w = word.casefold()
        if len(w) < 4 or w in STOPWORDS:
            continue
        s = stem(w)
        extra = next((terms for prefix, terms in SECTION_TERMS.items() if w.startswith(prefix)), ())
        for term in (s, *extra):
            if term not in stems:
                stems.append(term)
    return stems[:MAX_STEMS]


def text_query(stems: Sequence[str]) -> str:
    """iFind search string (search option 0): prefix wildcards joined by OR."""
    if not stems or not all(_WORD.fullmatch(s) for s in stems):
        raise ValueError("stems must be non-empty letter-only words")
    return " OR ".join(f"{s}*" for s in stems)


def matched_stems(stems: Sequence[str], text: str) -> set[str]:
    """Stems that prefix-match a word of the chunk (the rule iFind applied to select it)."""
    words = {w.casefold() for w in _WORD.findall(text)}
    return {s for s in stems if any(w.startswith(s) for w in words)}


def rank_text_hits(stems: Sequence[str], hits: Sequence[ChunkHit]) -> list[ChunkHit]:
    """Order full-text candidates by summed IDF of matched stems (rare stems weigh more; df over the candidates)."""
    matches = [(h, matched_stems(stems, f"{h.title}\n{h.text}")) for h in hits]
    df = {s: sum(1 for _, m in matches if s in m) for s in stems}
    n = len(matches)
    scored = [(sum(math.log(1 + n / df[s]) for s in m), h) for h, m in matches if m]
    scored.sort(key=lambda sh: (-round(sh[0], 9), sh[1].doc_id, sh[1].seq))
    return [h for _, h in scored]


@dataclass(frozen=True)
class RetrievedChunk:
    hit: ChunkHit
    score: float  # RRF score, higher is better
    vector_rank: int | None  # 1-based rank in the vector leg, None if not a candidate there
    text_rank: int | None  # 1-based rank in the full-text leg
    vector_score: float | None  # cosine similarity


def fuse(vector_hits: Sequence[ChunkHit], text_hits: Sequence[ChunkHit], k: int) -> list[RetrievedChunk]:
    """Reciprocal rank fusion with a per-leg guarantee; deterministic order (LLM cache keys).

    Plain RRF drops a chunk that is first in one leg but absent from the other (e.g. "poslední dávka apixabanu":
    full-text rank 1, not among the vector candidates). So the top `GUARANTEED_PER_LEG` of each leg are always kept;
    the remaining slots go by RRF score. Ties are broken by (doc_id, seq).
    """
    by_id: dict[int, ChunkHit] = {}
    vector_rank: dict[int, int] = {}
    text_rank: dict[int, int] = {}
    for rank, hit in enumerate(vector_hits, 1):
        by_id.setdefault(hit.row_id, hit)
        vector_rank.setdefault(hit.row_id, rank)
    for rank, hit in enumerate(text_hits, 1):
        by_id.setdefault(hit.row_id, hit)
        text_rank.setdefault(hit.row_id, rank)
    scored: list[RetrievedChunk] = []
    for row_id, hit in by_id.items():
        vr, tr = vector_rank.get(row_id), text_rank.get(row_id)
        score = (1 / (RRF_K + vr) if vr else 0.0) + (1 / (RRF_K + tr) if tr else 0.0)
        vector_score = next((h.score for h in vector_hits if h.row_id == row_id), None)
        scored.append(RetrievedChunk(hit, score, vr, tr, vector_score))
    scored.sort(key=lambda r: (-round(r.score, 12), r.hit.doc_id, r.hit.seq))
    guaranteed = {
        r.hit.row_id
        for r in scored
        if (r.vector_rank or k + 1) <= GUARANTEED_PER_LEG or (r.text_rank or k + 1) <= GUARANTEED_PER_LEG
    }
    kept = [r for r in scored if r.hit.row_id in guaranteed][:k]
    kept += [r for r in scored if r.hit.row_id not in guaranteed][: k - len(kept)]
    return sorted(kept, key=lambda r: (-round(r.score, 12), r.hit.doc_id, r.hit.seq))


class HybridRetriever:
    def __init__(self, store: VectorStore, embedder: Embedder) -> None:
        self._store = store
        self._embedder = embedder

    @property
    def model_id(self) -> str:
        return self._embedder.model_id

    async def search(self, *, patient_ref: str, question: str, as_of: datetime, k: int) -> list[RetrievedChunk]:
        (vector,) = await asyncio.to_thread(self._embedder.embed, [question])
        vector_hits = await asyncio.to_thread(
            lambda: self._store.search(
                patient_ref=patient_ref, vector=vector, as_of=as_of, k=VECTOR_CANDIDATES, model=self.model_id
            )
        )
        return fuse(vector_hits, await self._text_leg(patient_ref, question, as_of), k)

    async def _text_leg(self, patient_ref: str, question: str, as_of: datetime) -> list[ChunkHit]:
        stems = query_stems(question)
        if not stems:
            return []
        query = text_query(stems)
        try:
            candidates = await asyncio.to_thread(
                lambda: self._store.text_search(
                    patient_ref=patient_ref, query=query, as_of=as_of, k=TEXT_CANDIDATES, model=self.model_id
                )
            )
        except Exception as exc:  # noqa: BLE001 - full text is an optional leg (index missing): degrade to vector-only
            log.warning("text_search_failed", error_type=type(exc).__name__)
            return []
        return rank_text_hits(stems, candidates)
