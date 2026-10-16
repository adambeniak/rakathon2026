"""Examinations that the GP letter lists as performed ("PROVEDENÁ VYŠETŘENÍ (VÝSLEDKY K DISPOZICI …)").

Only facts located inside that section count: other `examination` facts of the letter describe findings or plans in the
epicrisis, not reports a workplace holds (pure, no I/O).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from app.documents.normalize import NormalizedDoc
from app.domain.evidence import Fact, FactType
from app.domain.triage import ListedExam, fold

_SECTION_MARKER = "vysledky k dispozici"


def _is_heading(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 3 and text == text.upper() and not re.match(r"^\d+\.", text)


def listed_exam_section(doc: NormalizedDoc) -> tuple[int, int] | None:
    """Character range of the block list after the heading that carries the marker, up to the next heading."""
    blocks = list(doc.blocks)
    for index, block in enumerate(blocks):
        if _SECTION_MARKER in fold(block.text):
            end = next((b.start for b in blocks[index + 1 :] if _is_heading(b.text)), len(doc.text))
            return block.end, end
    return None


def listed_exams(doc: NormalizedDoc, facts: Sequence[Fact]) -> list[ListedExam]:
    section = listed_exam_section(doc)
    if section is None:
        return []
    start, end = section
    inside = [
        f
        for f in facts
        if f.type is FactType.EXAMINATION
        and f.evidence[0].char_start is not None
        and start <= f.evidence[0].char_start < end
    ]
    exams: list[ListedExam] = []
    for fact in sorted(inside, key=lambda f: f.evidence[0].char_start or 0):
        text = fact.value.get("text") if isinstance(fact.value, dict) else None
        label = text if isinstance(text, str) and text.strip() else fact.evidence[0].quote
        exams.append(ListedExam(label=label.strip(), exam_date=fact.clinical_date, evidence=fact.evidence))
    return exams
