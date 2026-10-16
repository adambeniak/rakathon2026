"""build_handover: one unreadable document is reported, never fatal (fake LLM clients, no network)."""

from __future__ import annotations

import asyncio
import io

from docx import Document

from app.extraction.handover.service import build_handover
from app.extraction.llm import CacheMissError
from tests.unit.extraction.test_handover_assembly import AS_OF, CARDIO, GASTRO, REFERRAL


def _docx(text: str) -> bytes:
    buffer = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


class FakeLlm:
    def __init__(self, fail_for: str | None = None) -> None:
        self.fail_for = fail_for

    async def complete_json(self, *, system: str, user: str, schema: dict[str, object], doc_id: str) -> str:
        if doc_id == self.fail_for:
            raise CacheMissError("miss")
        return '{"facts": []}'


def test_missing_content_and_failed_extraction_are_excluded_with_reasons() -> None:
    contents = {REFERRAL.doc_id: _docx("Žádost"), GASTRO.doc_id: _docx("Gastro")}  # CARDIO has no content
    handover = asyncio.run(
        build_handover(
            "case-1",
            AS_OF,
            [REFERRAL, GASTRO, CARDIO],
            contents,
            extraction=FakeLlm(fail_for=GASTRO.doc_id),
            epicrisis=FakeLlm(),
        )
    )
    reasons = {e.doc_id: e.reason for e in handover.excluded_documents}
    assert reasons[CARDIO.doc_id] == "obsah dokumentu není dostupný"
    assert reasons[GASTRO.doc_id] == "extrakce dokumentu není k dispozici"
    assert handover.included_documents == [REFERRAL.doc_id]
