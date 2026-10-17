"""Report header parse (`headers.parse_header`) and its use in fields 3, 12 and 14 (fictitious data only)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import pytest

from app.documents.normalize import NormalizedDoc, doc_from_text
from app.domain.document import SourceDocument
from app.domain.evidence import Evidence, Fact
from app.domain.handover import Handover
from app.extraction.handover.assemble import assemble_handover
from app.extraction.handover.fields import NOT_STATED
from app.extraction.handover.headers import DocumentHeader, parse_header, parse_headers
from app.settings import PRAGUE

AS_OF = datetime(2026, 10, 21, 8, 0, tzinfo=PRAGUE)

# An untyped document whose file name says nothing about its kind (the API path before uploads were typed).
PATHOLOGY_TEXT = """FIKTIVNÍ PACIENTKA – testovací data
KOC Nemocnice Testovací (fiktivní)
Ústav patologie
Testovací 1, 100 00 Praha 10
Bioptický nález
Pacientka: Jana Testová, RČ 000000/0000
Číslo vyšetření: B-2026/00001
Materiál: ložisko (odběr 20. 10. 2026)
Datum vydání: 19. 10. 2026
MIKROSKOPICKY
Duktální adenokarcinom. MKN-O 8500/3."""
PATHOLOGY_ID = "11_Nalez_2026-10-19"


def _all_evidence(header: DocumentHeader) -> list[Evidence]:
    values = (header.examination, header.place, header.report_id)
    return [e for v in values if v for e in v.evidence] + ([header.issued.evidence] if header.issued else [])


def _assert_exact(doc: NormalizedDoc, header: DocumentHeader) -> None:
    for ev in _all_evidence(header):
        assert ev.char_start is not None
        assert doc.text[ev.char_start : ev.char_end] == ev.quote


# ---------------------------------------------------------------- parse on the 13 demo reports


@pytest.mark.parametrize(
    ("prefix", "examination", "place"),
    [
        ("01", "Ambulantní zpráva – kontrolní vyšetření", "Kardiologická ambulance Jesenice"),
        ("03", "RTG hrudníku PA", "Radiologické centrum Modřany"),
        ("05", "Ambulantní zpráva – vstupní vyšetření", "Poliklinika Jižní, Gastroenterologická ambulance"),
        ("06", "UZ břicha", "Poliklinika Jižní, Radiodiagnostické pracoviště"),
        ("08", "CT břicha a hrudníku s k. l., pankreatický protokol", "KOC Nemocnice Severní, Radiologická klinika"),
        ("09", "EUS-FNB", "KOC Nemocnice Lipová, Endoskopické pracoviště, Interní gastroenterologická klinika"),
        ("10", "Výsledky laboratorního vyšetření", "KOC Nemocnice Lipová, Oddělení klinické biochemie a hematologie"),
        ("11", "Bioptický nález", "KOC Nemocnice Lipová, Ústav patologie"),
    ],
)
def test_examination_and_place_from_the_report_header(
    doc: Callable[[str], NormalizedDoc], prefix: str, examination: str, place: str
) -> None:
    d = doc(prefix)
    header = parse_header(d)
    assert header.examination is not None
    assert header.place is not None
    assert (header.examination.text, header.place.text) == (examination, place)
    _assert_exact(d, header)
    # Each value piece is copied from one quoted header line (verbatim, "(fiktivní)" banner dropped).
    assert header.examination.text in header.examination.evidence[0].quote
    for part, ev in zip(header.place.text.split(", "), header.place.evidence, strict=False):
        assert part in ev.quote


def test_report_number_and_issue_date_of_the_pathology_report(doc: Callable[[str], NormalizedDoc]) -> None:
    d = doc("11")
    header = parse_header(d)
    assert header.report_id is not None
    assert header.report_id.text == "B-2026/15921"
    assert header.report_id.evidence[0].quote == "Číslo vyšetření: B-2026/15921"
    assert header.issued is not None
    assert header.issued.date == date(2026, 10, 19)  # "Datum vydání", not the collection date in the material line
    assert header.issued.evidence.quote == "Datum vydání: 19. 10. 2026"
    _assert_exact(d, header)


def test_issue_line_with_two_dates_gives_no_issue_date(doc: Callable[[str], NormalizedDoc]) -> None:
    assert parse_header(doc("02")).issued is None  # "Vydáno: 4. 9. 2026 (kultivace), 1. 9. 2026 (ostatní)"


def test_every_demo_header_quote_is_an_exact_span(docs: dict[str, NormalizedDoc]) -> None:
    for doc_id, header in parse_headers(docs).items():
        _assert_exact(docs[doc_id], header)


def test_no_letterhead_no_values() -> None:
    d = doc_from_text("09_Text_2026-10-12", "Protokol o výkonu – EUS-FNB\nPOPIS\nBez komplikací.")
    header = parse_header(d)
    assert (header.examination, header.place, header.report_id, header.issued) == (None, None, None, None)


def test_section_body_is_never_read_as_header() -> None:
    text = "Pracoviště A\nUlice 1, 100 00 Praha\nZpráva\nPOPIS\nČíslo vyšetření: X-2026/1\nDatum vydání: 1. 1. 2026"
    header = parse_header(doc_from_text("05_Text_2026-09-15", text))
    assert header.report_id is None
    assert header.issued is None


# ---------------------------------------------------------------- fields 12, 14, 3


def _source(doc_id: str, type_code: str | None, custodian: str | None = None, title: str | None = None) -> Any:
    authored = date.fromisoformat(doc_id.rsplit("_", 1)[1])
    return SourceDocument(
        doc_id=doc_id,
        title=title or f"{doc_id}.docx",
        type_code=type_code,
        authored_at=authored,
        received_at=datetime(authored.year, authored.month, authored.day, 12, 0, tzinfo=PRAGUE),
        custodian=custodian,
    )


def _fact(doc: NormalizedDoc, n: int, type_: str, field: int, value: dict[str, Any], quote: str) -> Fact:
    start = doc.text.index(quote)
    ev = Evidence(doc_id=doc.doc_id, quote=quote, char_start=start, char_end=start + len(quote))
    return Fact(
        id=f"h{n}", doc_id=doc.doc_id, type=type_, handover_field=field, value=value, certainty="stated", evidence=[ev]
    )


def _pathology_case(*, with_headers: bool) -> Handover:
    d = doc_from_text(PATHOLOGY_ID, PATHOLOGY_TEXT, date(2026, 10, 19))
    facts = [
        _fact(d, 1, "histology", 14, {"kind": "text", "text": "Duktální adenokarcinom"}, "Duktální adenokarcinom"),
        _fact(d, 2, "histology", 3, {"kind": "coded", "code": "8500/3", "system": "MKN-O", "text": "Duktální "
              "adenokarcinom"}, "Duktální adenokarcinom. MKN-O 8500/3."),
    ]  # fmt: skip
    docs = {PATHOLOGY_ID: _source(PATHOLOGY_ID, None)}
    headers = parse_headers({PATHOLOGY_ID: d}) if with_headers else None
    return assemble_handover("case-h", AS_OF, facts, docs, headers=headers)


def test_histology_number_and_dates_from_the_header_without_a_document_type() -> None:
    h = _pathology_case(with_headers=True)
    histology, diagnosis = h.fields.histology, h.fields.diagnosis
    assert histology.value is not None
    assert histology.value.report_id == "B-2026/00001"
    assert histology.value.issued == date(2026, 10, 19)
    assert diagnosis.value is not None
    assert diagnosis.value.verified_histologically_on == date(2026, 10, 19)
    quotes = {e.quote for e in histology.evidence}
    assert {"Číslo vyšetření: B-2026/00001", "Datum vydání: 19. 10. 2026"} <= quotes
    assert "Datum vydání: 19. 10. 2026" in {e.quote for e in diagnosis.evidence}
    by_label = {i.label: i for i in histology.items}
    assert by_label["Číslo vyšetření"].evidence[0].quote == "Číslo vyšetření: B-2026/00001"
    assert by_label["Datum vydání"].value == "19. 10. 2026"


def test_without_header_or_type_the_histology_dates_stay_empty() -> None:
    h = _pathology_case(with_headers=False)
    assert h.fields.histology.value is not None
    assert (h.fields.histology.value.report_id, h.fields.histology.value.issued) == (None, None)
    assert h.fields.diagnosis.value is not None
    assert h.fields.diagnosis.value.verified_histologically_on is None  # never guessed from an untyped document


def test_untyped_pathology_named_by_its_file_is_treated_as_pathology() -> None:
    doc_id = "11_Histologie_2026-10-19"
    d = doc_from_text(doc_id, "Duktální adenokarcinom. MKN-O 8500/3.", date(2026, 10, 19))
    morph = _fact(d, 3, "histology", 3, {"kind": "coded", "code": "8500/3", "system": "MKN-O", "text": "Duktální "
                  "adenokarcinom"}, "Duktální adenokarcinom. MKN-O 8500/3.")  # fmt: skip
    h = assemble_handover("case-h", AS_OF, [morph], {doc_id: _source(doc_id, None)})
    assert h.fields.diagnosis.value is not None
    assert h.fields.diagnosis.value.verified_histologically_on == date(2026, 10, 19)


def test_examination_rows_from_headers_with_evidence(doc: Callable[[str], NormalizedDoc]) -> None:
    ct, referral = doc("08"), doc("07")
    docs = {
        ct.doc_id: _source(ct.doc_id, "18748-4", custodian="Metadata pracoviště"),
        referral.doc_id: _source(referral.doc_id, "57133-1"),
    }
    h = assemble_handover("case-h", AS_OF, [], docs, headers=parse_headers({ct.doc_id: ct, referral.doc_id: referral}))
    field = h.fields.examinations
    assert field.value is not None
    (row,) = field.value  # the referral letter is not an examination
    assert (row.type, row.place) == (
        "CT břicha a hrudníku s k. l., pankreatický protokol",
        "KOC Nemocnice Severní, Radiologická klinika",
    )
    (item,) = field.items
    assert [e.quote for e in item.evidence] == [
        "Výsledek vyšetření – CT břicha a hrudníku s k. l., pankreatický protokol",
        "KOC Nemocnice Severní (fiktivní)",
        "Radiologická klinika",
    ]
    assert all(e.doc_id == ct.doc_id for e in field.evidence)


def test_examination_row_without_header_falls_back_to_metadata_then_not_stated() -> None:
    a, b = "03_A_2026-09-03", "06_B_2026-09-29"
    docs = {a: _source(a, "18748-4", custodian="Pracoviště z metadat", title="Zpráva A"), b: _source(b, None)}
    rows = assemble_handover("case-h", AS_OF, [], docs).fields.examinations.value
    assert rows is not None
    assert [(r.type, r.place) for r in rows] == [("Zpráva A", "Pracoviště z metadat"), (f"{b}.docx", NOT_STATED)]
