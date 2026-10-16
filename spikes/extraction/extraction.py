"""Evidence-locked fact extraction.

Nothing reaches the handover unless `evidence_lock` accepts it. The stored quote is always the exact
substring of the normalised source text (`doc.text[span[0]:span[1]]`).
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

from pydantic import ValidationError

from documents import NormalizedDoc, find_dates, find_month_years, match_key, normalize_text
from prompt import SYSTEM_PROMPT, build_user_message
from schema import (
    ALLOWED_FIELDS,
    ALLOWED_KINDS,
    RESPONSE_SCHEMA,
    CodedValue,
    DateValue,
    Fact,
    MedicationValue,
    PersonValue,
    QuantityValue,
    RawFact,
    TextValue,
    make_fact_id,
)

log = logging.getLogger("stafeta.extraction")

MAX_QUOTE_LEN = 600

NEGATION_CUE = re.compile(
    r"(?<!\w)(neguj\w*|bez|není|nebyl\w*|negativn\w*|nezvětšen\w*|neprokázán\w*|neg\.|nepřítomn\w*|ani)(?!\w)",
    re.IGNORECASE,
)
PS_CUE = re.compile(r"ECOG|(?<![A-Za-z])PS(?![A-Za-z])|Karnofsk")
SUSPICION_CUE = re.compile(
    r"(?<!\w)(suspekt\w*|susp\.|v\.\s?s\.|vs\.|podezření|suspekce|nelze vyloučit|diferenciálně|DD|k potvrzení"
    r"|pravděpodobn\w*)(?!\w)|\?",
    re.IGNORECASE,
)
# A "stated" fact of these types must not sit on a quote that only suspects it.
CERTAINTY_CHECKED_TYPES = frozenset({"diagnosis", "histology", "comorbidity"})


@dataclass(frozen=True)
class Accepted:
    fact: Fact


@dataclass(frozen=True)
class Rejected:
    reason: str
    raw: RawFact | None
    detail: str = ""


LockResult = Accepted | Rejected


# ---------------------------------------------------------------- helpers


def fold(text: str) -> str:
    """Comparison-only fold: NFKC (₂->2, µ->μ), casefold, whitespace collapsed."""
    return match_key(normalize_text(text), fold=True).key.casefold()


_NUMBER = re.compile(r"(?<![\d,.])\d+(?:[.,]\d+)?(?!\d)")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b")


def numbers_in(text: str) -> Counter[Decimal]:
    """Unsigned numbers (decimal comma or point). `-` is never a minus: `1-0-1` -> 1, 0, 1."""
    out: Counter[Decimal] = Counter()
    for m in _NUMBER.finditer(unicodedata.normalize("NFKC", text)):
        try:
            out[Decimal(m.group(0).replace(",", ".")).normalize()] += 1
        except InvalidOperation:
            continue
    return out


def value_numbers(raw: RawFact) -> Counter[Decimal]:
    """Numbers carried by the value (ISO dates skipped; dates are checked separately)."""
    v = raw.value
    nums: Counter[Decimal] = Counter()
    if isinstance(v, DateValue):
        return nums
    if isinstance(v, QuantityValue) and v.number is not None:
        nums[Decimal(repr(v.number)).normalize()] += 1
    for key, item in v.model_dump().items():
        if key in {"kind", "system", "flag", "comparator", "number"} or not isinstance(item, str):
            continue
        nums.update(numbers_in(_ISO_DATE.sub(" ", item)))
    return nums


def value_texts(raw: RawFact) -> list[str]:
    """Free-text parts of the value that must be a contiguous copy of the quote (no paraphrase)."""
    v = raw.value
    if isinstance(v, TextValue | CodedValue):
        parts: list[str | None] = [v.text]
    elif isinstance(v, QuantityValue):
        parts = [v.text_value]
    elif isinstance(v, MedicationValue):
        parts = [v.dose, v.schedule]
    elif isinstance(v, PersonValue):
        parts = [v.name, v.relation, v.address]
    else:
        parts = []
    return [p for p in parts if p and p.strip(" .,;:")]


def _locate(quote: str, doc: NormalizedDoc) -> tuple[tuple[int, int], bool] | None:
    """Exact (whitespace-normalised) match first; then NFKC repair if it hits exactly one span."""
    q = match_key(normalize_text(quote)).key
    if not q:
        return None
    exact = match_key(doc.text)
    idx = exact.key.find(q)
    if idx >= 0:
        return exact.span(idx, len(q)), False
    qf = match_key(normalize_text(quote), fold=True).key
    folded = match_key(doc.text, fold=True)
    first = folded.key.find(qf)
    if first < 0 or folded.key.find(qf, first + 1) >= 0:
        return None
    return folded.span(first, len(qf)), True


def _iso_parts(value: str) -> tuple[int, int | None, int | None] | None:
    m = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", value.strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), m.group(2), m.group(3)
    try:
        if d is not None:
            date(y, int(mo or 1), int(d))
        elif mo is not None and not 1 <= int(mo) <= 12:
            return None
    except ValueError:
        return None
    return y, int(mo) if mo else None, int(d) if d else None


def _date_supported(iso: str, quote: str, doc: NormalizedDoc) -> str | None:
    """None if supported, else the rejection reason."""
    parts = _iso_parts(iso)
    if parts is None:
        return "date_unparseable"
    y, mo, d = parts
    year_hint = doc.authored_date.year if doc.authored_date else None
    in_quote = set(find_dates(quote, year_hint))
    candidates = in_quote | doc.all_header_dates()
    if d is not None and mo is not None:
        return None if date(y, mo, d) in candidates else "date_unsupported"
    if mo is not None:
        if (y, mo) in find_month_years(quote) or any((c.year, c.month) == (y, mo) for c in candidates):
            return None
        return "date_unsupported"
    if str(y) in quote or any(c.year == y for c in in_quote):
        return None
    return "date_unsupported"


# ---------------------------------------------------------------- evidence lock


def evidence_lock(raw: RawFact, doc: NormalizedDoc) -> LockResult:
    quote = raw.quote.strip()
    if not quote:
        return Rejected("quote_empty", raw)
    if len(quote) > MAX_QUOTE_LEN:
        return Rejected("quote_too_long", raw, str(len(quote)))
    if raw.value.kind not in ALLOWED_KINDS[raw.type]:
        return Rejected("schema_mismatch", raw, f"{raw.type} cannot carry {raw.value.kind}")
    if raw.handover_field not in ALLOWED_FIELDS[raw.type]:
        return Rejected("schema_mismatch", raw, f"{raw.type} not allowed in field {raw.handover_field}")

    located = _locate(quote, doc)
    if located is None:
        return Rejected("quote_not_found", raw)
    span, repaired = located
    source_quote = doc.text[span[0] : span[1]]
    fq = fold(source_quote)

    v = raw.value
    terms: list[str] = []
    if isinstance(v, QuantityValue):
        terms.append(v.name)
    elif isinstance(v, MedicationValue):
        terms.append(v.drug)
    elif isinstance(v, CodedValue) and v.code:
        terms.append(v.code)
    for term in terms:
        if fold(term) not in fq:
            return Rejected("term_not_in_quote", raw, term)
    for text in value_texts(raw):
        if fold(text.strip(" .,;:")) not in fq:
            return Rejected("text_not_in_quote", raw, text[:60])

    missing = value_numbers(raw) - numbers_in(source_quote)
    if missing:
        return Rejected("number_not_in_quote", raw, ", ".join(str(n) for n in missing))

    if raw.unit and fold(raw.unit) not in fq:
        return Rejected("unit_not_in_quote", raw, raw.unit)

    for iso in (raw.clinical_date, v.date if isinstance(v, DateValue) else None):
        if iso is None:
            continue
        reason = _date_supported(iso, source_quote, doc)
        if reason:
            return Rejected(reason, raw, iso)

    if raw.type == "performance_status" and not PS_CUE.search(source_quote):
        return Rejected("ps_inferred", raw)
    if raw.certainty == "negated" and not NEGATION_CUE.search(source_quote):
        return Rejected("negation_mismatch", raw)
    if raw.certainty == "stated" and raw.type in CERTAINTY_CHECKED_TYPES and (m := SUSPICION_CUE.search(source_quote)):
        return Rejected("certainty_mismatch", raw, m.group(0))

    fact = Fact(
        fact_id=make_fact_id(doc.doc_id, raw),
        doc_id=doc.doc_id,
        type=raw.type,
        handover_field=raw.handover_field,
        value=raw.value,
        unit=raw.unit,
        clinical_date=raw.clinical_date,
        certainty=raw.certainty,
        quote=source_quote,
        span=span,
        repaired=repaired,
    )
    return Accepted(fact)


def stated_with_negation_cue(fact: Fact) -> bool:
    """Audit signal: a negation cue in the quote but the fact is not marked negated."""
    return fact.certainty != "negated" and NEGATION_CUE.search(fact.quote) is not None


# ---------------------------------------------------------------- as-of


def doc_included(doc: NormalizedDoc, as_of: datetime, *, require_received: bool = False) -> bool:
    """AGENTS rule 4: authored <= as_of AND received <= as_of.

    Date-only values count as an unknown time on that day, so a document dated on the as_of day is
    excluded (e.g. the MDT conclusion of 21. 10. vs MDT start 08:00). Raw files carry no received date
    (seed/FHIR supplies it); the backend must call this with require_received=True so an unknown
    received date excludes the document.
    """
    if doc.authored_date is None:
        return False
    if doc.received_date is None and require_received:
        return False
    return all(d < as_of.date() for d in (doc.authored_date, doc.received_date) if d is not None)


def filter_as_of(
    facts: Iterable[Fact], docs: dict[str, NormalizedDoc], as_of: datetime, *, require_received: bool = False
) -> list[Fact]:
    return [
        f for f in facts if f.doc_id in docs and doc_included(docs[f.doc_id], as_of, require_received=require_received)
    ]


# ---------------------------------------------------------------- orchestration


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
            log.info(
                "rejected",
                extra={"doc_id": doc.doc_id, "type": raw.type, "reason": result.reason},
            )
        elif result.fact.fact_id not in seen:
            seen.add(result.fact.fact_id)
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
