"""C2 from the parsed header lines of a pathology report (#159): no model-extracted date fact needed."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date

from app.consistency import detect_findings
from app.documents.normalize import NormalizedDoc, doc_from_text
from app.domain.handover import HandoverStatus
from app.extraction.handover.headers import parse_headers
from app.extraction.handover.service import build_handover
from tests.unit.consistency.test_date_conflicts import (
    DOC09,
    DOC11,
    ISSUE_QUOTE,
    PROCEDURE_QUOTE,
    SPECIMEN_QUOTE,
    issue,
    quotes,
    specimen,
)
from tests.unit.consistency.test_handover_wiring import FakeLlm, _docx, _raw
from tests.unit.extraction.test_handover_assembly import AS_OF, source

PATHOLOGY = "11526-1"
LAB = "11502-2"


def test_c2_from_the_demo_headers_alone(docs: dict[str, NormalizedDoc]) -> None:
    included = {k: d for k, d in docs.items() if k.startswith(("09", "10", "11"))}
    types = {DOC09: "28570-0", "10_Laborator_KOC2_2026-10-15": LAB, DOC11: PATHOLOGY}
    (c2,) = detect_findings([], parse_headers(included), types)
    assert c2.id == "C2"
    assert c2.field == "14_histology"
    assert c2.docs == [DOC09, DOC11]
    assert quotes(c2) == [SPECIMEN_QUOTE, ISSUE_QUOTE, PROCEDURE_QUOTE]
    assert c2.message == (
        f"Nesoulad mezi „{SPECIMEN_QUOTE}“ a „{ISSUE_QUOTE}“ (dok. 11). "
        f"Pro srovnání: v dok. 09 uvedeno „{PROCEDURE_QUOTE}“."
    )
    for ev in c2.evidence:  # whole header lines, exact spans
        assert ev.char_start is not None
        assert docs[ev.doc_id].text[ev.char_start : ev.char_end] == ev.quote


def test_header_and_fact_give_one_finding(docs: dict[str, NormalizedDoc]) -> None:
    headers = parse_headers({DOC11: docs[DOC11]})
    findings = detect_findings([specimen(), issue()], headers, {DOC11: PATHOLOGY})
    assert [x.id for x in findings] == ["C2"]


def test_lab_report_header_never_raises_a_histology_conflict() -> None:
    lab_id = "10_Lab_2026-10-15"
    text = (
        "Laboratoř A\nUlice 1, 100 00 Praha\nVýsledky laboratorního vyšetření\nOdběr: 20. 10. 2026 7:45\n"
        "Vydáno: 19. 10. 2026\nKREVNÍ OBRAZ"
    )
    headers = parse_headers({lab_id: doc_from_text(lab_id, text, date(2026, 10, 15))})
    assert detect_findings([], headers, {lab_id: LAB}) == []


def test_pathology_title_counts_without_a_document_type() -> None:
    doc_id = "11_Nalez_2026-10-19"
    text = (
        "Ústav patologie\nUlice 1, 100 00 Praha\nBioptický nález\nMateriál: ložisko (odběr 20. 10. 2026)\n"
        "Datum vydání: 19. 10. 2026\nMIKROSKOPICKY"
    )
    headers = parse_headers({doc_id: doc_from_text(doc_id, text, date(2026, 10, 19))})
    (c2,) = detect_findings([], headers, {doc_id: None})
    assert quotes(c2) == ["Materiál: ložisko (odběr 20. 10. 2026)", "Datum vydání: 19. 10. 2026"]


def test_consistent_header_dates_raise_nothing_and_never_hide_a_quoted_conflict() -> None:
    doc_id = DOC11
    text = (
        "Ústav patologie\nUlice 1, 100 00 Praha\nBioptický nález\nMateriál: (odběr 12. 10. 2026)\n"
        "Datum vydání: 19. 10. 2026"
    )
    headers = parse_headers({doc_id: doc_from_text(doc_id, text, date(2026, 10, 19))})
    assert detect_findings([], headers, {doc_id: PATHOLOGY}) == []
    # A conflicting quote elsewhere in the same report is still reported from the facts.
    assert [x.id for x in detect_findings([specimen(), issue()], headers, {doc_id: PATHOLOGY})] == ["C2"]


def test_year_less_header_dates_raise_nothing() -> None:
    text = (
        "Ústav patologie\nUlice 1, 100 00 Praha\nBioptický nález\nMateriál: (odběr 20. 10.)\nDatum vydání: 19. 10. 2026"
    )
    headers = parse_headers({DOC11: doc_from_text(DOC11, text, date(2026, 10, 19))})
    assert detect_findings([], headers, {DOC11: PATHOLOGY}) == []


def test_build_handover_flags_14_and_records_c2_on_field_3_without_extracted_dates(
    doc: Callable[[str], NormalizedDoc],
) -> None:
    """The model returns the morphology but no 'Datum vydání' fact: C2 still marks field 14, and field 3 (which
    shows the same issue date as the verification date) records C2 while keeping its own status."""
    d11 = doc("11")
    pathology = source(DOC11, PATHOLOGY)
    lines = d11.text.split("\n")
    morph = next(line for line in lines if "MKN-O 8500/3" in line)
    raw = [
        _raw("histology", 3, {"kind": "coded", "code": "8500/3", "system": "MKN-O", "text": "adenokarcinom"}, morph),
        _raw("diagnosis", 3, {"kind": "coded", "code": "C25.0", "system": "MKN-10", "text": "tumor"}, morph),
    ]
    handover = asyncio.run(
        build_handover(
            "case-1",
            AS_OF,
            [pathology],
            {DOC11: _docx(*lines)},
            extraction=FakeLlm(raw),
            epicrisis=FakeLlm([]),
        )
    )
    assert [x.id for x in handover.findings] == ["C2"]
    assert handover.fields.histology.conflicts == ["C2"]
    assert handover.fields.histology.status is HandoverStatus.COMPLETE_WITH_CONFLICT
    diagnosis = handover.fields.diagnosis
    assert diagnosis.value is not None
    assert diagnosis.value.verified_histologically_on == date(2026, 10, 19)
    assert diagnosis.conflicts == ["C2"]
    assert diagnosis.status is not HandoverStatus.COMPLETE_WITH_CONFLICT  # related field: id recorded, status kept
