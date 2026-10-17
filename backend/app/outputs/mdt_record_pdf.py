"""MDT record (zápis z jednání MDT) as PDF: the DOCX's document model (`mdt_record.build_context`) laid out with
reportlab in the order and with the labels of the sample form `data/raw/MDT_zapis.docx`.

Pure Python: no LibreOffice and no system fonts in the image. Czech glyphs come from the bundled DejaVu Sans
(`fonts/LICENSE.txt`), embedded as a subset. Same content, same sanitising, same review labels, waivers and draft
banner as the DOCX; the draft marker is also printed in the header of every page. Every value is XML-escaped before it
reaches reportlab's paragraph markup, so a value can never change the formatting. A marker drawn after the last
paragraph proves that the whole document was laid out; a PDF without it is never returned.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any, Final
from xml.sax.saxutils import escape

from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.fonts import addMapping  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.lib.styles import ParagraphStyle  # type: ignore[import-untyped]
from reportlab.lib.units import mm  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    CondPageBreak,
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.domain.handover import Handover
from app.domain.pathway import RecordedWaiver
from app.outputs.mdt_record import (
    GREY,
    MdtRecordError,
    ReferringDoctor,
    Rich,
    SignedConclusion,
    build_context,
)

PDF_MEDIA_TYPE: Final = "application/pdf"
FONTS: Final = Path(__file__).parent / "fonts"
REGULAR: Final = "StafetaDejaVuSans"
BOLD: Final = "StafetaDejaVuSans-Bold"

TITLE: Final = "Zápis k jednání multidisciplinárního týmu (MDT)"
# Headings and row labels of the sample form (data/raw/MDT_zapis.docx), same text and order as the DOCX template.
HEADINGS: Final = (
    "1 Základní údaje",
    "2 Členové MDT",
    "3 Diagnóza",
    "4 Komorbidity",
    "5 Výsledky stávajících vyšetření",
    "6 Závěr MDT",
    "7 Doporučení MDT",
)
BASICS_LABELS: Final = (
    "Datum MDT",
    "Pacient:\nJméno a příjmení\nPojišťovna\nTelefon, email\nAdresa\nVáha, výška",
    "Referující lékař:\nJméno a příjmení\nTelefon, email",
)
MEMBERS_HEADER: Final = "Jméno a příjmení"
MEMBERS_EMPTY_ROWS: Final = 5  # the form's empty rows, kept for handwriting at the meeting
DIAGNOSIS_LABELS: Final = ("Název diagnózy", "Kód diagnózy (MKN-10)")
RESULTS_HEADER: Final = ("Datum", "Vyšetření", "Výsledek")
APPENDIX_A: Final = "Příloha A – Nesrovnalosti v dokumentaci (stav k MDT)"
APPENDIX_B: Final = "Příloha B – Dokumenty nezahrnuté do podkladu"
APPENDIX_C: Final = "Příloha C – Další oddíly předávky (mimo formulář MDT zápisu)"

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN: Final = 18 * mm
CONTENT_WIDTH: Final = PAGE_WIDTH - 2 * MARGIN
EMPTY_BOX_HEIGHT: Final = 28 * mm
HEADING_ROOM: Final = 45 * mm  # a heading never ends a page: less room than this left starts a new page
GRID: Final = colors.HexColor("#808080")


@cache
def _register_fonts() -> None:
    """Register the bundled fonts once per process (reportlab keeps a process-wide font registry)."""
    pdfmetrics.registerFont(TTFont(REGULAR, str(FONTS / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(BOLD, str(FONTS / "DejaVuSans-Bold.ttf")))
    # No oblique face is bundled: <i> keeps the regular face (notes are told apart by their grey colour).
    addMapping(REGULAR, 0, 0, REGULAR)
    addMapping(REGULAR, 1, 0, BOLD)
    addMapping(REGULAR, 0, 1, REGULAR)
    addMapping(REGULAR, 1, 1, BOLD)


def _style(name: str, *, size: float = 9.5, bold: bool = False, color: str | None = None, **kw: Any) -> ParagraphStyle:
    return ParagraphStyle(
        name,
        fontName=BOLD if bold else REGULAR,
        fontSize=size,
        leading=size * 1.3,
        textColor=colors.HexColor(f"#{color}") if color else colors.black,
        **kw,
    )


class _Styles:
    def __init__(self) -> None:
        self.title = _style("title", size=15, bold=True, spaceAfter=4 * mm)
        self.heading = _style("heading", size=12, bold=True, spaceBefore=5 * mm, spaceAfter=1.5 * mm)
        self.body = _style("body")
        self.subheading = _style("subheading", spaceBefore=1.5 * mm, keepWithNext=1)
        self.label = _style("label", spaceAfter=1.5 * mm)
        self.cell = _style("cell", size=9)
        self.cell_bold = _style("cell_bold", size=9, bold=True)
        self.bullet = _style("bullet", leftIndent=4 * mm, firstLineIndent=-3 * mm)
        self.footer = _style("footer", size=7.5, color=GREY, spaceBefore=6 * mm)
        self.page = _style("page", size=7.5, color=GREY)


class _EndMarker(Flowable):  # type: ignore[misc]
    """Zero-size flowable after the footer: `drawn` is True only if the layout reached the end of the document."""

    def __init__(self) -> None:
        super().__init__()
        self.width = self.height = 0
        self.drawn = False

    def draw(self) -> None:
        self.drawn = True


def render_mdt_record_pdf(
    handover: Handover,
    referring: ReferringDoctor | None,
    generated_at: datetime,
    waivers: Sequence[RecordedWaiver] = (),
    conclusion: SignedConclusion | None = None,
) -> bytes:
    _register_fonts()
    context = build_context(handover, referring, generated_at, waivers, conclusion)
    styles = _Styles()
    end = _EndMarker()
    story = [*_story(context, styles), end]

    page_banner = _markup(context["page_banner"])

    def on_page(canvas: Canvas, doc: SimpleDocTemplate) -> None:
        canvas.saveState()
        if page_banner:
            banner = Paragraph(page_banner, styles.body)
            _, height = banner.wrap(CONTENT_WIDTH, MARGIN)
            banner.drawOn(canvas, MARGIN, PAGE_HEIGHT - MARGIN / 2 - height / 2)
        number = Paragraph(f"Strana {doc.page}", styles.page)
        number.wrap(CONTENT_WIDTH, MARGIN)
        number.drawOn(canvas, MARGIN, MARGIN / 2)
        canvas.restoreState()

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title="Zápis z jednání MDT",
        author="Štafeta",
        subject="",
        creator="Štafeta",
        invariant=1,  # no wall-clock timestamps or random ids in the file: the same input gives the same bytes
    )
    document.build(story, onFirstPage=on_page, onLaterPages=on_page)
    if not end.drawn:
        raise MdtRecordError("the rendered MDT record PDF is incomplete")
    return buffer.getvalue()


# --- layout ----------------------------------------------------------------------------------------------------------


def _story(c: dict[str, Any], s: _Styles) -> list[Flowable]:
    story: list[Flowable] = [
        Paragraph(escape(TITLE), s.title),
        Paragraph(_markup(c["banner"]), s.body),
        Spacer(0, 1.5 * mm),
        Paragraph(_markup(c["meta"]), s.body),
    ]

    def section(number: int, label: Rich) -> None:
        story.extend([CondPageBreak(HEADING_ROOM), Paragraph(escape(HEADINGS[number - 1]), s.heading)])
        story.append(Paragraph(_markup(label), s.label))

    section(1, c["s1"])
    values = (c["mdt_date"], c["patient_lines"], c["referring_lines"])
    story.append(
        _table([[_cell(label, s.cell), _cell(v, s.cell)] for label, v in zip(BASICS_LABELS, values, strict=True)])
    )

    section(2, c["s2"])
    members = [[_cell(MEMBERS_HEADER, s.cell_bold)], *([_cell("", s.cell)] for _ in range(MEMBERS_EMPTY_ROWS))]
    story.append(_table(members, widths=(CONTENT_WIDTH,), min_height=6 * mm))

    section(3, c["s3"])
    diagnosis = (c["diagnosis_name"], c["diagnosis_code"])
    story.append(
        _table([[_cell(label, s.cell), _cell(v, s.cell)] for label, v in zip(DIAGNOSIS_LABELS, diagnosis, strict=True)])
    )

    section(4, c["s4"])
    story.append(_table([[_cell(c["comorbidities_text"], s.cell)]], widths=(CONTENT_WIDTH,)))

    section(5, c["s5"])
    header = [_cell(h, s.cell_bold) for h in RESULTS_HEADER]
    rows = [[_cell(r["date"], s.cell), _cell(r["exam"], s.cell), _cell(r["result"], s.cell)] for r in c["results"]]
    widths = (22 * mm, 50 * mm, CONTENT_WIDTH - 72 * mm)
    story.append(_table([header, *rows], widths=widths, repeat_rows=1))

    section(6, c["s6"])
    story.append(_table([[_cell(c["conclusion_text"], s.cell)]], widths=(CONTENT_WIDTH,), min_height=EMPTY_BOX_HEIGHT))

    section(7, c["s7"])
    story.append(_table([[_cell("", s.cell)]], widths=(CONTENT_WIDTH,), min_height=EMPTY_BOX_HEIGHT))

    story += [CondPageBreak(HEADING_ROOM), Paragraph(escape(APPENDIX_A), s.heading)]
    story += [Paragraph("– " + _markup(line), s.bullet) for line in c["findings"]]
    story += [CondPageBreak(HEADING_ROOM), Paragraph(escape(APPENDIX_B), s.heading)]
    story += [Paragraph("– " + _markup(line), s.bullet) for line in c["excluded"]]
    story += [CondPageBreak(HEADING_ROOM), Paragraph(escape(APPENDIX_C), s.heading)]
    for appendix in c["appendix"]:
        story.append(Paragraph(_markup(appendix["title"]), s.subheading))
        story += [Paragraph("– " + _markup(line), s.bullet) for line in appendix["lines"]]
    story.append(Paragraph(_markup(c["footer"]), s.footer))
    return story


def _table(
    rows: list[list[Paragraph]],
    *,
    widths: Sequence[float] = (48 * mm, CONTENT_WIDTH - 48 * mm),
    repeat_rows: int = 0,
    min_height: float | None = None,
) -> Table:
    """A grid like the form's; a row taller than a page is split inside the row instead of failing the layout."""
    table = Table(
        rows,
        colWidths=list(widths),
        repeatRows=repeat_rows,
        splitInRow=1,
        minRowHeights=[min_height] * len(rows) if min_height else None,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _cell(value: str | Rich, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_markup(value), style)


def _markup(value: str | Rich) -> str:
    """reportlab paragraph markup of a model value: every text escaped, "\\n" a line break, bold and colour kept."""
    if isinstance(value, str):
        return _escape(value)
    parts = []
    for run in value.runs:
        text = _escape(run.text)
        if run.bold:
            text = f"<b>{text}</b>"
        if run.color:
            text = f'<font color="#{run.color}">{text}</font>'
        parts.append(text)
    return "".join(parts)


def _escape(text: str) -> str:
    return escape(text).replace("\n", "<br/>")
