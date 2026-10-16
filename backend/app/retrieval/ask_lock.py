"""Evidence lock for "ask the case" answers (ADR-0002 applied to free-text sentences, ADR-0004).

A sentence reaches the user only if ALL hold:
1. it cites at least one quote;
2. every quote is found (whitespace-normalised) in a RETRIEVED chunk of the cited document, so nothing outside the
   as-of window and nothing the model did not see can be cited;
3. every date in the sentence appears in its quotes or is the authored date of a cited document;
4. every other number in the sentence appears in its quotes;
5. outside its quotes, the sentence has no recommendation, necessity, suitability, prognosis or hedging wording
   (AGENTS.md 3: the model must not advise or interpret);
6. outside its quotes, the sentence is attributed to the documentation ("je uvedeno", "v protokolu", "uvádí", …)
   or reports an inconsistency ("Nesoulad: …"), so it never reads as the application's own statement.
Rejected sentences are dropped; only the reason is logged, never the text.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.documents.normalize import find_dates, match_key, normalize_text
from app.extraction.lock import numbers_in
from app.retrieval.ask_prompt import RawSentence
from app.retrieval.search import RetrievedChunk

MIN_QUOTE_CHARS = 4
MAX_QUOTE_CHARS = 600

# First/second-person or impersonal recommendations; documented ones are quoted, and quotes are removed first.
RECOMMENDATION = re.compile(
    r"(?<!\w)(doporučuj[ie]\w*|doporučuje se|doporučil[ao]? bych|doporučili bychom|navrhuj[ie]\w*|navrhnul? bych"
    r"|je vhodné|bylo by vhodné|by bylo vhodné|je nutné zahájit|je třeba (zahájit|podat|nasadit|vysadit)"
    r"|měl[aiy]? by|by\s+měl[aiy]?|měli byste|by\s+měli|měla byste|zvažte|zvažujte|nasaďte|vysaďte|podejte"
    r"|pokračujte|indikuji|lze zvážit|ke zvážení|je (potřeba|nutno|nutné|třeba)|vhodn\w*|indikován\w*"
    r"|prognóz\w*|přežit\w*|zřejmě|nejspíš\w*|pravděpodobn\w*)(?!\w)",
    re.IGNORECASE,
)
ATTRIBUTION = re.compile(
    r"^Nesoulad:|(?<!\w)(uveden\w*|uvádí|uvádějí|popsán\w*|popisuje|zaznamenán\w*|zmíněn\w*|konstatuje|žádá"
    r"|doporučil[aiy]?|v\s+(\w+\s+){0,3}(dokumentaci|zprávě|zprávách|protokolu|nálezu|epikríze|závěru|žádosti"
    r"|výsledcích|anamnéze|popisu|záznamu))(?!\w)",
    re.IGNORECASE,
)
_DATE_LITERAL = re.compile(r"(?<!\d)\d{1,2}\.\s*\d{1,2}\.(?:\s*\d{4})?(?!\d)")
_BRACKETED = re.compile(r"\s*\[[^\]]{1,120}\]")


@dataclass(frozen=True)
class LockedCitation:
    doc_id: str
    title: str
    quote: str  # exact substring of the chunk text (and therefore of the normalised document)
    chunk_seq: int


@dataclass(frozen=True)
class LockedSentence:
    text: str
    citations: tuple[LockedCitation, ...]


@dataclass(frozen=True)
class DroppedSentence:
    reason: str


def _locate(quote: str, chunks: Sequence[RetrievedChunk]) -> LockedCitation | None:
    q = match_key(normalize_text(quote)).key
    if len(q.replace(" ", "")) < MIN_QUOTE_CHARS or len(q) > MAX_QUOTE_CHARS:
        return None
    for chunk in chunks:
        keyed = match_key(chunk.hit.text)
        idx = keyed.key.find(q)
        if idx >= 0:
            start, end = keyed.span(idx, len(q))
            return LockedCitation(chunk.hit.doc_id, chunk.hit.title, chunk.hit.text[start:end], chunk.hit.seq)
    return None


def _without_quotes(text: str, quotes: Sequence[str]) -> str:
    key = match_key(normalize_text(text)).key
    for q in quotes:
        key = key.replace(match_key(q).key, " ")
    return key


def lock_sentence(raw: RawSentence, chunks: Sequence[RetrievedChunk]) -> LockedSentence | DroppedSentence:
    text = _BRACKETED.sub("", normalize_text(raw.text)).strip()
    if not text:
        return DroppedSentence("empty")
    if not raw.citations:
        return DroppedSentence("no_citation")
    by_doc: dict[str, list[RetrievedChunk]] = {}
    for chunk in chunks:
        by_doc.setdefault(chunk.hit.doc_id, []).append(chunk)

    citations: list[LockedCitation] = []
    for cit in raw.citations:
        if cit.doc_id not in by_doc:
            return DroppedSentence("doc_not_retrieved")
        located = _locate(cit.quote, by_doc[cit.doc_id])
        if located is None:
            return DroppedSentence("quote_not_found")
        if located not in citations:
            citations.append(located)

    quotes = [cited.quote for cited in citations]
    authored: set[date] = {by_doc[cited.doc_id][0].hit.authored_on for cited in citations}
    allowed_dates = set(authored)
    for cited in citations:
        allowed_dates.update(find_dates(cited.quote, by_doc[cited.doc_id][0].hit.authored_on.year))
    year_hint = min(authored).year
    if any(d not in allowed_dates for d in find_dates(text, year_hint)):
        return DroppedSentence("date_unsupported")

    quote_numbers = set(numbers_in(" ".join(quotes)))
    if any(n not in quote_numbers for n in numbers_in(_DATE_LITERAL.sub(" ", text))):
        return DroppedSentence("number_unsupported")

    unquoted = _without_quotes(text, quotes)
    if RECOMMENDATION.search(unquoted):
        return DroppedSentence("recommendation_wording")
    if not ATTRIBUTION.search(unquoted):
        return DroppedSentence("unattributed")
    return LockedSentence(text, tuple(citations))


def lock_answer(
    sentences: Sequence[RawSentence], chunks: Sequence[RetrievedChunk]
) -> tuple[list[LockedSentence], list[DroppedSentence]]:
    kept: list[LockedSentence] = []
    dropped: list[DroppedSentence] = []
    for raw in sentences:
        result = lock_sentence(raw, chunks)
        if isinstance(result, LockedSentence):
            kept.append(result)
        else:
            dropped.append(result)
    return kept, dropped
