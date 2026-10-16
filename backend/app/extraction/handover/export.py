"""Copyable Markdown of a handover: one block per section, status, each value with its source, citations."""

from __future__ import annotations

from typing import Final

from app.domain.handover import Handover, HandoverFieldBase, HandoverFields, HandoverItem, HandoverStatus
from app.extraction.handover.facts import cz_date

STATUS_CS: Final = {
    HandoverStatus.COMPLETE: "kompletní",
    HandoverStatus.PARTIAL: "částečné",
    HandoverStatus.MISSING: "chybí",
    HandoverStatus.STALE: "neaktuální",
    HandoverStatus.NEEDS_CLARIFICATION: "k upřesnění",
    HandoverStatus.COMPLETE_WITH_CONFLICT: "kompletní, s nesouladem",
    HandoverStatus.GENERATED_WITH_CITATIONS: "návrh AI s citacemi",
}
ROLE_CS: Final = {
    "gp": "praktický lékař",
    "coordinator": "koordinátor KOC",
    "koc_physician": "ošetřující lékař KOC",
    "koc_staff": "personál KOC",
    "external_workplace": "externí pracoviště",
    "patient": "pacient",
    "reviewer": "revizní lékař",
    "system": "systém",
}
DRAFT_HEADER: Final = (
    "Předávka sestavena automaticky z dokumentace (AI); oddíly nepotvrzené lékařem jsou návrh. "
    "Každá hodnota je doložena citací ze zdrojového dokumentu."
)


def to_markdown(handover: Handover) -> str:
    as_of = handover.as_of
    lines = [
        f"# Předávka k MDT – stav k {cz_date(as_of.date())} {as_of:%H:%M}",
        "",
        DRAFT_HEADER,
        "",
        f"Zahrnuté dokumenty: {len(handover.included_documents)}.",
    ]
    for excluded in handover.excluded_documents:
        lines.append(f"Nezahrnuto: {excluded.doc_id} ({excluded.reason}).")
    for number, (name, info) in enumerate(HandoverFields.model_fields.items(), start=1):
        field: HandoverFieldBase = getattr(handover.fields, name)
        lines += ["", f"## {number}. {info.description} — {STATUS_CS[field.status]}{_review(field)}", ""]
        if name == "epicrisis":
            lines += _epicrisis(handover)
        else:
            lines += [_item(item) for item in field.items]
        for item in field.missing_items:
            lines.append(f"- Chybí: {item.item} – {item.reason} (doplní: {ROLE_CS[item.suggested_owner]})")
        if field.conflicts:
            lines.append(f"- Nesoulad: {', '.join(field.conflicts)}")
        if field.note:
            lines.append(f"- Poznámka: {field.note}")
        if name != "epicrisis":
            lines += [f"> [{ev.doc_id}] „{ev.quote}“" for ev in field.evidence]
    return "\n".join(lines) + "\n"


def _review(field: HandoverFieldBase) -> str:
    if field.review is None or field.review.state == "draft":
        return " (návrh, nepotvrzeno)"
    return " (potvrzeno lékařem)" if field.review.state == "confirmed" else " (potvrzeno jako chybějící)"


def _item(item: HandoverItem) -> str:
    value = _number(item.value) if isinstance(item.value, float) else item.value
    parts = [f"{item.label}: " if item.label else "", str(value), f" {item.unit}" if item.unit else ""]
    if item.clinical_date:
        parts.append(f" ({cz_date(item.clinical_date)})")
    docs = sorted({ev.doc_id for ev in item.evidence})
    if docs:
        parts.append(f" [{', '.join(docs)}]")
    return "- " + "".join(parts)


def _number(value: float) -> str:
    """Full precision, Czech decimal comma (never rounded or in exponent notation)."""
    return str(int(value)) if value.is_integer() else repr(value).replace(".", ",")


def _epicrisis(handover: Handover) -> list[str]:
    """Text with the draft label, then a legend: each citation marker -> document and verbatim quote."""
    field = handover.fields.epicrisis
    value = field.value
    if value is None:
        return []
    lines = [f"*{value.label}*", "", value.text, "", "Citace:"]
    for sentence, item in zip(value.sentences, field.items, strict=False):
        for alias, ev in zip(sentence.aliases, item.evidence, strict=False):
            lines.append(f"- {alias} → [{ev.doc_id}] „{ev.quote}“")
    return lines
