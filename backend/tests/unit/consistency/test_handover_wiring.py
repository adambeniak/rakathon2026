"""build_handover feeds the C1/C2 rules: the findings reach the handover and mark the conflicting field."""

from __future__ import annotations

import asyncio
import io
import json

from docx import Document

from app.domain.handover import HandoverStatus
from app.extraction.handover.service import build_handover
from tests.unit.extraction.test_handover_assembly import AS_OF, source

DOC09 = source("09_Biopsie_vykon_KOC2_2026-10-12")
PROCEDURE_QUOTE = "Datum výkonu: 12. 10. 2026"
DOSE_QUOTE = "Apixaban vysazen 48 h před výkonem (poslední dávka 18. 10. 2026 večer)."


def _docx(*lines: str) -> bytes:
    buffer = io.BytesIO()
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    document.save(buffer)
    return buffer.getvalue()


def _raw(type_: str, field: int, value: dict[str, str | None], quote: str) -> dict[str, object]:
    return {
        "type": type_,
        "handover_field": field,
        "value": value,
        "unit": None,
        "clinical_date": None,
        "certainty": "stated",
        "quote": quote,
    }


class FakeLlm:
    def __init__(self, facts: list[dict[str, object]]) -> None:
        self.facts = facts

    async def complete_json(self, *, system: str, user: str, schema: dict[str, object], doc_id: str) -> str:
        return json.dumps({"facts": self.facts})


def _build(facts: list[dict[str, object]], findings: list[object] | None = None):  # type: ignore[no-untyped-def]
    contents = {DOC09.doc_id: _docx("Protokol o výkonu", PROCEDURE_QUOTE, DOSE_QUOTE)}
    return asyncio.run(
        build_handover(
            "case-1",
            AS_OF,
            [DOC09],
            contents,
            extraction=FakeLlm(facts),
            epicrisis=FakeLlm([]),
            findings=findings or (),
        )
    )


def test_build_handover_attaches_c1_and_marks_field_7() -> None:
    facts = [
        _raw("admin_date", 12, {"kind": "date", "label": "Datum výkonu", "date": "2026-10-12"}, PROCEDURE_QUOTE),
        _raw("medication", 7, {"kind": "medication", "drug": "Apixaban", "dose": None, "schedule": None}, DOSE_QUOTE),
    ]
    handover = _build(facts)
    assert [x.id for x in handover.findings] == ["C1"]
    assert handover.findings[0].field == "7_medications"
    assert handover.fields.medications.conflicts == ["C1"]
    assert handover.fields.medications.status is HandoverStatus.COMPLETE_WITH_CONFLICT


def test_build_handover_without_conflicting_dates_has_no_findings() -> None:
    facts = [_raw("admin_date", 12, {"kind": "date", "label": "Datum výkonu", "date": "2026-10-12"}, PROCEDURE_QUOTE)]
    handover = _build(facts)
    assert handover.findings == []
    assert handover.fields.medications.conflicts == []
