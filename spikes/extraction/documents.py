"""DOCX -> NormalizedDoc: body order, tables as pipe rows, stable char offsets.

The same `normalize_text` is applied to document text and to every LLM quote, so a quote can be
located with a plain substring search on `match_key`.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

# ---------------------------------------------------------------- text normalisation

_CHAR_MAP = str.maketrans(
    {
        "—": "–",  # em dash -> en dash
        "‒": "–",  # figure dash
        "―": "–",  # horizontal bar
        "‐": "-",  # hyphen
        "‑": "-",  # non-breaking hyphen
        " ": " ",  # NBSP
        " ": " ",  # narrow NBSP
        " ": " ",  # figure space
        " ": " ",  # thin space
        "\t": " ",
        "„": '"',
        "“": '"',
        "”": '"',
        "‚": "'",
        "‘": "'",
        "’": "'",
    }
)
_SPACES = re.compile(r" {2,}")


def normalize_text(text: str) -> str:
    """NFC, unified dashes/quotes/spaces, collapsed spaces; line breaks kept, lines stripped.

    Plain ASCII hyphen-minus is never touched (`1-0-1`, `CA 19-9`, `B-2026/15921`).
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("--", "–")
    text = text.translate(_CHAR_MAP)
    lines = [_SPACES.sub(" ", line).strip() for line in text.replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


@dataclass(frozen=True)
class Keyed:
    """Search key derived from a text plus a map from key positions back to text offsets."""

    key: str
    offsets: tuple[int, ...]

    def span(self, key_start: int, key_len: int) -> tuple[int, int]:
        return self.offsets[key_start], self.offsets[key_start + key_len - 1] + 1


def match_key(text: str, *, fold: bool = False) -> Keyed:
    """Collapse every whitespace run (incl. newlines) to one space.

    fold=True additionally applies NFKC per character (`₂` -> `2`, `µ` -> `μ`); used only for
    quote repair and number/unit comparison, never for the stored evidence.
    """
    out: list[str] = []
    offsets: list[int] = []
    pending_space = -1
    for i, ch in enumerate(text):
        if ch.isspace():
            if out and pending_space < 0:
                pending_space = i
            continue
        if pending_space >= 0:
            out.append(" ")
            offsets.append(pending_space)
            pending_space = -1
        piece = unicodedata.normalize("NFKC", ch) if fold else ch
        for p in piece:
            out.append(p)
            offsets.append(i)
    return Keyed("".join(out), tuple(offsets))


# ---------------------------------------------------------------- dates

_DATE = re.compile(r"(?<!\d)(\d{1,2})\.\s*(\d{1,2})\.(?:\s*(\d{4}))?(?![\d])")


def find_dates(text: str, year_hint: int | None = None) -> list[date]:
    """All Czech day.month.[year] dates in text; year-less ones use year_hint (if given)."""
    found: list[date] = []
    for m in _DATE.finditer(text):
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else year_hint
        if year is None:
            continue
        try:
            found.append(date(year, month, day))
        except ValueError:
            continue
    return found


def parse_czech_date(text: str, year_hint: int | None = None) -> date | None:
    """First date in `text` ("20. 7. 2026", "4.11.2026 10:30", "20. 7." + year_hint)."""
    dates = find_dates(text, year_hint)
    return dates[0] if dates else None


# Czech month names in nominative, genitive and locative ("leden", "ledna", "lednu").
_MONTH_FORMS: dict[int, tuple[str, ...]] = {
    1: ("leden", "ledna", "lednu"),
    2: ("únor", "února", "únoru"),
    3: ("březen", "března", "březnu"),
    4: ("duben", "dubna", "dubnu"),
    5: ("květen", "května", "květnu"),
    6: ("červen", "června", "červnu"),
    7: ("červenec", "července", "červenci"),
    8: ("srpen", "srpna", "srpnu"),
    9: ("září",),
    10: ("říjen", "října", "říjnu"),
    11: ("listopad", "listopadu"),
    12: ("prosinec", "prosince", "prosinci"),
}


def find_month_years(text: str) -> set[tuple[int, int]]:
    """(year, month) pairs written as '<month name> <year>' ("poloviny srpna 2026", "leden 2027")."""
    found: set[tuple[int, int]] = set()
    low = text.casefold()
    for month, forms in _MONTH_FORMS.items():
        for form in forms:
            for m in re.finditer(rf"(?<!\w){form}(?!\w)\s+(\d{{4}})", low):
                found.add((int(m.group(1)), month))
    return found


# ---------------------------------------------------------------- document model

HEADER_LABELS = (
    "Datum vyšetření:",
    "Datum výkonu:",
    "Datum vydání:",
    "Datum:",
    "Vydáno:",
    "Odběr:",
)
_SIGNED = re.compile(r"^V .{2,40}? dne (.+)$")
_STEM_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})$")


@dataclass(frozen=True)
class Block:
    kind: str  # "p" | "tr"
    text: str
    start: int
    end: int
    table_header: str | None = None


@dataclass(frozen=True)
class NormalizedDoc:
    doc_id: str
    text: str
    blocks: tuple[Block, ...]
    authored_date: date | None
    header_dates: dict[str, list[date]] = field(default_factory=dict)
    received_date: date | None = None
    warnings: tuple[str, ...] = ()

    def all_header_dates(self) -> set[date]:
        return {d for ds in self.header_dates.values() for d in ds}


def _row_text(row_cells: list[object]) -> str:
    seen: set[int] = set()
    texts: list[str] = []
    for cell in row_cells:
        tc = cell._tc  # type: ignore[attr-defined]
        if id(tc) in seen:  # merged cell repeated by python-docx
            continue
        seen.add(id(tc))
        texts.append(normalize_text(cell.text).replace("\n", " "))  # type: ignore[attr-defined]
    while texts and not texts[-1]:
        texts.pop()
    return " | ".join(texts)


def _raw_blocks(path: Path) -> list[tuple[str, str, str | None]]:
    doc = Document(str(path))
    out: list[tuple[str, str, str | None]] = []
    for el in doc.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = normalize_text(Paragraph(el, doc).text)
            if text:
                out.append(("p", text, None))
        elif tag == "tbl":
            header: str | None = None
            for i, row in enumerate(Table(el, doc).rows):
                text = _row_text(list(row.cells))
                if not text:
                    continue
                if i == 0:
                    header = text
                out.append(("tr", text, header if i else None))
    return out


def build_doc(
    doc_id: str,
    raw_blocks: Sequence[tuple[str, str, str | None]],
    authored_date: date | None,
) -> NormalizedDoc:
    blocks: list[Block] = []
    pos = 0
    for kind, text, header in raw_blocks:
        if blocks:
            pos += 1  # "\n" separator
        blocks.append(Block(kind, text, pos, pos + len(text), header))
        pos += len(text)
    full = "\n".join(b.text for b in blocks)

    year = authored_date.year if authored_date else None
    header_dates: dict[str, list[date]] = {}
    for b in blocks:
        if b.kind != "p":
            continue
        for label in HEADER_LABELS:
            if b.text.startswith(label):
                ds = find_dates(b.text[len(label) :], year)
                if ds:
                    header_dates.setdefault(label, []).extend(ds)
                break
        else:
            m = _SIGNED.match(b.text)
            if m:
                d = parse_czech_date(m.group(1), year)
                if d:
                    header_dates.setdefault("V … dne", []).append(d)
        # Dates inside the material line of pathology reports ("(odběr 20. 10. 2026)") are not header dates.

    warnings: list[str] = []
    if authored_date and header_dates and authored_date not in {d for ds in header_dates.values() for d in ds}:
        warnings.append(f"file-name date {authored_date.isoformat()} not among header dates")
    return NormalizedDoc(doc_id, full, tuple(blocks), authored_date, header_dates, None, tuple(warnings))


def normalize(path: Path) -> NormalizedDoc:
    """Read a DOCX report into a NormalizedDoc. doc_id = file stem; authored date from the file name."""
    stem = path.stem
    m = _STEM_DATE.search(stem)
    authored = date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
    return build_doc(stem, _raw_blocks(path), authored)


def doc_from_text(doc_id: str, text: str, authored_date: date | None = None) -> NormalizedDoc:
    """Build a NormalizedDoc from plain text (tests, synthetic fixtures). One block per line."""
    raw = [("p", line, None) for line in normalize_text(text).split("\n") if line]
    return build_doc(doc_id, raw, authored_date)
