"""Evidence lock and as-of filter (owner: P2, ADR-0002).

Nothing reaches the handover unless `evidence_lock` accepts it. The stored quote is always the exact
substring of the normalised source text (`doc.text[char_start:char_end]`).
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from app.documents.normalize import (
    NormalizedDoc,
    find_dates,
    find_month_years,
    match_key,
    normalize_text,
    parse_czech_date,
)
from app.domain.evidence import Certainty, DatePrecision, Evidence, Fact
from app.extraction.values import (
    ALLOWED_FIELDS,
    ALLOWED_KINDS,
    CodedValue,
    DateValue,
    MedicationValue,
    PersonValue,
    QuantityValue,
    RawFact,
    TextValue,
    make_fact_id,
)
from app.settings import PRAGUE

MAX_QUOTE_LEN = 600
# A negated text fact whose value lacks the negation word is repaired only for quotes up to this length.
MAX_REPAIR_QUOTE_LEN = 40
NEGATED_VALUE_REPAIRED = "negated_value_from_quote"

# Explicit negation words and negated-finding stems only; a generic "ne-" prefix is NOT a cue
# ("nehomogenní", "neostře ohraničené" describe positive findings).
NEGATION_CUE = re.compile(
    r"(?<!\w)(neguj\w*|bez|není|nebyl\w*|negativn\w*|neg\.|nepřítomn\w*|ani|nemá\w*|neměl\w*"
    r"|nezvětšen\w*|neprokázán\w*|nepotvrzen\w*|vyloučen\w*|nedilatovan\w*|nerozšířen\w*|nezmnožen\w*"
    r"|neproveden\w*|nehmatn\w*|afebriln\w*)(?!\w)",
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


def value_numbers(raw: RawFact) -> list[Counter[Decimal]]:
    """Numbers carried by the value, one multiset per field (ISO dates skipped; dates are checked
    separately). Per field, because `{code: "211", text: "ZP 211"}` legitimately repeats a number
    across fields while the quote holds it once."""
    v = raw.value
    out: list[Counter[Decimal]] = []
    if isinstance(v, DateValue):
        return out
    if isinstance(v, QuantityValue) and v.number is not None:
        out.append(Counter({Decimal(repr(v.number)).normalize(): 1}))
    for key, item in v.model_dump().items():
        if key in {"kind", "system", "flag", "comparator", "number"} or not isinstance(item, str):
            continue
        out.append(numbers_in(_ISO_DATE.sub(" ", item)))
    return out


def value_strings(raw: RawFact) -> list[str]:
    """All human-readable strings of the value (for the negation-in-value rule)."""
    skip = {"kind", "system", "flag", "comparator"}
    return [s for k, s in raw.value.model_dump().items() if k not in skip and isinstance(s, str)]


def to_iso(value: str, year_hint: int | None) -> str | None:
    """ISO as given, or a full Czech date literal ("20. 7. 2026") converted deterministically."""
    if _iso_parts(value) is not None:
        return value.strip()
    m = re.fullmatch(r"\s*(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})\s*", value)
    if not m:
        return None
    d = parse_czech_date(value, year_hint)
    return d.isoformat() if d else None


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
        parts = [v.name, v.relation, v.phone, v.email, v.address]
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

    quote_numbers = numbers_in(source_quote)
    for field_numbers in value_numbers(raw):
        missing = field_numbers - quote_numbers
        if missing:
            return Rejected("number_not_in_quote", raw, ", ".join(str(n) for n in missing))

    if raw.unit and fold(raw.unit) not in fq:
        return Rejected("unit_not_in_quote", raw, raw.unit)

    year_hint = doc.authored_date.year if doc.authored_date else None
    notes: list[str] = []
    value = v
    if isinstance(v, DateValue):  # the date IS the value: unsupported -> reject the fact
        iso = to_iso(v.date, year_hint)
        if iso is None:
            return Rejected("date_unparseable", raw, v.date)
        reason = _date_supported(iso, source_quote, doc)
        if reason:
            return Rejected(reason, raw, iso)
        value = v.model_copy(update={"date": iso})
    clinical_date: tuple[date, DatePrecision] | None = None
    if raw.clinical_date is not None:  # an attached date: unsupported -> drop the date, keep the fact
        iso = to_iso(raw.clinical_date, year_hint)
        if iso is None:
            notes.append(f"clinical_date_dropped:unparseable:{raw.clinical_date[:20]}")
        elif _date_supported(iso, source_quote, doc):
            notes.append(f"clinical_date_dropped:unsupported:{iso}")
        else:
            clinical_date = _date_and_precision(iso)

    if raw.type == "performance_status" and not PS_CUE.search(source_quote):
        return Rejected("ps_inferred", raw)
    if raw.certainty == "negated":
        if not NEGATION_CUE.search(source_quote):
            return Rejected("negation_mismatch", raw)
        # Convention: a negated fact's value is the self-contained negative statement ("Bez známek
        # vzdálených metastáz", "AA: neguje"); consumers never compose a negation themselves. A value
        # without the negation word ("Truncus coeliacus") would read as a present finding.
        if not NEGATION_CUE.search(" ".join(value_strings(raw))):
            # Narrow repair: a short single-clause negative statement ("AA: neguje") whose value lost the cue
            # ("AA") becomes the exact source quote, which is self-contained. Longer or multi-clause quotes stay
            # rejected ("bez metastáz, ascites přítomen" would hide a positive finding).
            single_clause = not any(sep in source_quote for sep in ",;")
            if not isinstance(v, TextValue) or len(source_quote) > MAX_REPAIR_QUOTE_LEN or not single_clause:
                return Rejected("negation_not_in_value", raw)
            value = v.model_copy(update={"text": source_quote})
            notes.append(NEGATED_VALUE_REPAIRED)
    if raw.certainty == "stated" and raw.type in CERTAINTY_CHECKED_TYPES and (m := SUSPICION_CUE.search(source_quote)):
        return Rejected("certainty_mismatch", raw, m.group(0))

    fact = Fact(
        id=make_fact_id(doc.doc_id, raw),
        doc_id=doc.doc_id,
        type=raw.type,
        handover_field=raw.handover_field,
        value=value.model_dump(mode="json"),
        unit=raw.unit,
        clinical_date=clinical_date[0] if clinical_date else None,
        clinical_date_precision=clinical_date[1] if clinical_date else None,
        certainty=raw.certainty,
        evidence=[Evidence(doc_id=doc.doc_id, quote=source_quote, char_start=span[0], char_end=span[1])],
        quote_repaired=repaired,
        lock_notes=notes,
    )
    return Accepted(fact)


def _date_and_precision(iso: str) -> tuple[date, DatePrecision]:
    """'2026-08-15' -> day; '2026-08' -> first day + month; '2026' -> first day + year (validated by the lock)."""
    parts = iso.split("-")
    if len(parts) == 3:
        return date.fromisoformat(iso), DatePrecision.DAY
    if len(parts) == 2:
        return date(int(parts[0]), int(parts[1]), 1), DatePrecision.MONTH
    return date(int(parts[0]), 1, 1), DatePrecision.YEAR


def clinical_date_text(fact: Fact) -> str | None:
    """ISO text at the fact's precision ('2026-08' for a month)."""
    if fact.clinical_date is None:
        return None
    if fact.clinical_date_precision == DatePrecision.MONTH:
        return fact.clinical_date.isoformat()[:7]
    if fact.clinical_date_precision == DatePrecision.YEAR:
        return fact.clinical_date.isoformat()[:4]
    return fact.clinical_date.isoformat()


def fact_quote(fact: Fact) -> str:
    return fact.evidence[0].quote


def stated_with_negation_cue(fact: Fact) -> bool:
    """Audit signal: a negation cue in the quote but the fact is not marked negated."""
    return fact.certainty != Certainty.NEGATED and NEGATION_CUE.search(fact_quote(fact)) is not None


# ---------------------------------------------------------------- as-of


def doc_included(doc: NormalizedDoc, as_of: datetime, *, require_received: bool = True) -> bool:
    """AGENTS rule 4: authored <= as_of AND received <= as_of.

    The authored date is date-only and counts as an unknown time on that day, so a document authored on
    the as_of day is excluded (e.g. the MDT conclusion of 21. 10. vs MDT start 08:00). `received_at` is a
    timestamp (seed/FHIR) compared exactly. An unknown received time excludes the document unless
    require_received=False (raw-file tooling only; the backend path always requires it).
    """
    return as_of_exclusion(doc.authored_date, doc.received_at, as_of, require_received=require_received) is None


AsOfExclusion = Literal["authored_unknown", "authored_after_as_of", "received_unknown", "received_after_as_of"]


def as_of_exclusion(
    authored: date | None, received: datetime | None, as_of: datetime, *, require_received: bool = True
) -> AsOfExclusion | None:
    """Why a document is not known at `as_of` (None = included). Semantics: see `doc_included`."""
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    if authored is None:
        return "authored_unknown"
    # The authored date is a Prague calendar day: compare with the as_of day in Prague, whatever offset was given.
    if authored >= as_of.astimezone(PRAGUE).date():
        return "authored_after_as_of"
    if received is None:
        return "received_unknown" if require_received else None
    return "received_after_as_of" if received > as_of else None


def filter_as_of(
    facts: Iterable[Fact], docs: dict[str, NormalizedDoc], as_of: datetime, *, require_received: bool = True
) -> list[Fact]:
    return [
        f for f in facts if f.doc_id in docs and doc_included(docs[f.doc_id], as_of, require_received=require_received)
    ]
