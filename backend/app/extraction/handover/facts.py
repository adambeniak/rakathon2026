"""Helpers over accepted facts for the field rules: typed values, ordering, matching, evidence."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Final

from app.domain.document import SourceDocument
from app.domain.evidence import Certainty, DatePrecision, Evidence, Fact, FactType
from app.domain.handover import HandoverItem, ItemEvidence
from app.extraction.values import (
    CodedValue,
    DateValue,
    FactValue,
    MedicationValue,
    PersonValue,
    QuantityValue,
    TextValue,
    parse_value,
)

# LOINC document types used by the rules (see docs/fhir-mapping.md "External terminologies").
LOINC_LAB_REPORT: Final = "11502-2"
LOINC_IMAGING: Final = "18748-4"
LOINC_REFERRAL_NOTE: Final = "57133-1"
LOINC_PROCEDURE_NOTE: Final = "28570-0"
LOINC_PATHOLOGY: Final = "11526-1"


@dataclass(frozen=True)
class HandoverRules:
    """Configurable assembly rules. Every value is reported in `Handover.rules`."""

    # DEMO RULE (not a clinical guideline): weight older than this at as_of is reported as stale.
    stale_vitals_days: int = 30

    def describe(self) -> dict[str, str]:
        return {"stale_vitals_days": f"{self.stale_vitals_days} (demo pravidlo)"}


@dataclass(frozen=True)
class Context:
    """Included facts and documents of one assembly run (as-of filter already applied)."""

    as_of: datetime
    facts: tuple[Fact, ...]
    docs: Mapping[str, SourceDocument]
    rules: HandoverRules

    def select(
        self,
        types: Iterable[FactType | str],
        *,
        fields: Iterable[int] | None = None,
        certainties: Iterable[Certainty | str] | None = None,
    ) -> list[Fact]:
        wanted = {str(t) for t in types}
        field_set = set(fields) if fields is not None else None
        cert_set = {str(c) for c in certainties} if certainties is not None else None
        return [
            f
            for f in self.facts
            if str(f.type) in wanted
            and (field_set is None or f.handover_field in field_set)
            and (cert_set is None or str(f.certainty) in cert_set)
        ]

    def doc_type(self, fact: Fact) -> str | None:
        return self.docs[fact.doc_id].type_code

    def authored(self, fact: Fact) -> date:
        return self.docs[fact.doc_id].authored_at

    def when(self, fact: Fact) -> date:
        """Clinical date if stated, else the authored date of the source document."""
        return fact.clinical_date or self.authored(fact)

    def order_key(self, fact: Fact) -> tuple[date, date, str, int, str]:
        """Chronological, deterministic: clinical date, document date, document, position in it, id."""
        start = fact.evidence[0].char_start or 0
        return (self.when(fact), self.authored(fact), fact.doc_id, start, fact.id)

    def chronological(self, facts: Iterable[Fact]) -> list[Fact]:
        return sorted(facts, key=self.order_key)

    def latest(self, facts: Iterable[Fact]) -> Fact | None:
        ordered = self.chronological(facts)
        return ordered[-1] if ordered else None


def value_of(fact: Fact) -> FactValue:
    return parse_value(fact.value)


def text_of(fact: Fact) -> str:
    """Human-readable text of a fact value, built only from the value's own (evidence-locked) parts."""
    v = value_of(fact)
    if isinstance(v, TextValue | CodedValue):
        return v.text
    if isinstance(v, MedicationValue):
        return " ".join(p for p in (v.drug, v.dose, v.schedule) if p)
    if isinstance(v, PersonValue):
        return ", ".join(p for p in (v.name, v.relation, v.phone, v.email, v.address) if p)
    if isinstance(v, DateValue):
        return f"{v.label} {v.date}"
    shown = v.text_value if v.text_value is not None else (_number(v.number) if v.number is not None else "")
    unit = f" {fact.unit}" if fact.unit and v.number is not None and v.text_value is None else ""
    return f"{v.name} {v.comparator or ''}{shown}{unit}".strip()


def quantity(fact: Fact) -> QuantityValue | None:
    v = value_of(fact)
    return v if isinstance(v, QuantityValue) else None


def _number(n: float) -> str:
    return str(int(n)) if float(n).is_integer() else str(n).replace(".", ",")


def fold_text(text: str) -> str:
    """Comparison key: NFKC, casefold, punctuation removed, whitespace collapsed."""
    t = unicodedata.normalize("NFKC", text).casefold()
    t = re.sub(r"[^\w\s/-]", " ", t)
    return " ".join(t.split())


def tokens(text: str) -> frozenset[str]:
    return frozenset(w for w in fold_text(text).split() if len(w) >= 3)


def same_stem(a: str, b: str, *, min_prefix: int = 5) -> bool:
    """Czech inflection-tolerant name match: 'ciprofloxacinu' ~ 'ciprofloxacin', 'leukocytóza' ~ 'leukocyty'."""
    x, y = fold_text(a), fold_text(b)
    if x == y:
        return True
    shorter = min(len(x), len(y))
    common = 0
    for cx, cy in zip(x, y, strict=False):
        if cx != cy:
            break
        common += 1
    return common >= min_prefix and common >= shorter - 3


def union_evidence(facts: Iterable[Fact]) -> list[Evidence]:
    seen: set[tuple[str, str, int | None]] = set()
    out: list[Evidence] = []
    for fact in facts:
        for ev in fact.evidence:
            key = (ev.doc_id, ev.quote, ev.char_start)
            if key not in seen:
                seen.add(key)
                out.append(ev)
    return out


def dedupe_by_text(ctx: Context, facts: Sequence[Fact]) -> list[Fact]:
    """Keep the latest fact per folded text, in chronological order of the kept facts."""
    kept: dict[str, Fact] = {}
    for fact in ctx.chronological(facts):
        kept[fold_text(text_of(fact))] = fact
    return ctx.chronological(kept.values())


def item_evidence(docs: Mapping[str, SourceDocument], facts: Iterable[Fact]) -> list[ItemEvidence]:
    """Evidence of the given facts (in order, no duplicates) with the source documents' dates."""
    out: list[ItemEvidence] = []
    for ev in union_evidence(facts):
        doc = docs[ev.doc_id]
        out.append(ItemEvidence(**ev.model_dump(), authored_at=doc.authored_at, received_at=doc.received_at))
    return out


def make_item(
    ctx: Context,
    value: str | float,
    facts: Iterable[Fact],
    *,
    label: str | None = None,
    unit: str | None = None,
    clinical_date: date | None = None,
) -> HandoverItem:
    return HandoverItem(
        label=label, value=value, unit=unit, clinical_date=clinical_date, evidence=item_evidence(ctx.docs, facts)
    )


def cz_date(day: date) -> str:
    return f"{day.day}. {day.month}. {day.year}"


def shown_date(fact: Fact, fallback: date) -> str:
    """Czech date at the precision the source states ('8/2026' for a month), else the fallback (document) date."""
    d = fact.clinical_date
    if d is None:
        return cz_date(fallback)
    if fact.clinical_date_precision == DatePrecision.MONTH:
        return f"{d.month}/{d.year}"
    if fact.clinical_date_precision == DatePrecision.YEAR:
        return str(d.year)
    return cz_date(d)
