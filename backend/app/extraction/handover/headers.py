"""Deterministic parse of a report's header lines (no LLM): issuing workplace, report title, report number, issue date.

Czech reports open with a letterhead (institution, department, address), a title line ("Výsledek vyšetření – RTG
hrudníku PA", "Bioptický nález") and labelled lines ("Číslo vyšetření: …", "Datum vydání: …"), all before the first
section heading in capitals ("POPIS", "MAKROSKOPICKY"). Every value is a verbatim substring of one header line and
carries that whole line as its evidence (exact `char_start`/`char_end` in the normalised text). A line the parser
does not recognise yields no value; the field rules then say "v dokumentaci neuvedeno" instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Final

from app.documents.doc_type import PATHOLOGY
from app.documents.normalize import Block, NormalizedDoc, find_dates
from app.domain.evidence import Evidence

MAX_HEADER_BLOCKS: Final = 25
_BANNER: Final = "FIKTIVN"  # demo-data banner line ("FIKTIVNÍ PACIENTKA – testovací data …")
_POSTCODE = re.compile(r"(?<!\d)\d{3} \d{2}(?!\d)")
_LABELLED = re.compile(r"^[^\W\d][^:–]{0,40}:(?:\s|$)")
_PERSON = re.compile(r"\b(?:MUDr|MDDr|Mgr|PhDr|Bc|Ing|doc|prof)\.")
_PATIENT = re.compile(r"^Pacient(?:ka)?\b")
_FICTIVE = re.compile(r"\s*\(fiktivní\)\s*$", re.IGNORECASE)
_DASH: Final = " – "
# Title prefixes that only name the kind of report; the examination is what follows the dash.
_GENERIC_TITLE_PREFIXES: Final = ("výsledek vyšetření", "výsledky vyšetření", "protokol o výkonu")
_CONTACT = re.compile(r"@|https?://|www\.|\btel\b|\bfax\b|\+\d{3}", re.IGNORECASE)
_PATHOLOGY_TITLE = re.compile(r"\b(?:bioptick|histologick)\w*\s+(?:nález|vyšetření)", re.IGNORECASE)
_REPORT_ID = re.compile(r"^Číslo vyšetření:\s*(\S*\d\S*)$")
_ISSUED = re.compile(r"^(?:Datum vydání|Vydáno):\s*(.+)$")
_PROCEDURE = re.compile(r"^Datum výkonu:\s*(.+)$")
# Specimen collection with an explicit year: "Odběr: 15. 10. 2026 7:45", "(odběr 20. 10. 2026)".
_SPECIMEN = re.compile(r"\bodběr:?\s+(?:dne\s+)?(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})", re.IGNORECASE)


@dataclass(frozen=True)
class HeaderValue:
    """A value copied from header lines; each evidence entry is one whole header line."""

    text: str
    evidence: tuple[Evidence, ...]

    @property
    def pathology_title(self) -> bool:
        """The title line names a histological report ("Bioptický nález", "Histologické vyšetření")."""
        return any(_PATHOLOGY_TITLE.search(ev.quote) for ev in self.evidence)


@dataclass(frozen=True)
class HeaderDate:
    date: date
    evidence: Evidence


@dataclass(frozen=True)
class DocumentHeader:
    doc_id: str
    examination: HeaderValue | None = None
    place: HeaderValue | None = None
    report_id: HeaderValue | None = None
    issued: HeaderDate | None = None
    specimen: HeaderDate | None = None
    procedure: HeaderDate | None = None


def is_pathology_report(header: DocumentHeader | None, type_code: str | None) -> bool:
    """Pathology report by its LOINC type in the metadata or by its own title line ("Bioptický nález")."""
    titled = header is not None and header.examination is not None and header.examination.pathology_title
    return type_code == PATHOLOGY or titled


def _single_date(text: str) -> date | None:
    """The one explicit-year date of a labelled line; none for a year-less date or for two dates."""
    dates = find_dates(text)
    return dates[0] if len(dates) == 1 else None


def _evidence(doc_id: str, block: Block) -> Evidence:
    return Evidence(doc_id=doc_id, quote=block.text, char_start=block.start, char_end=block.end)


def _header_blocks(doc: NormalizedDoc) -> list[Block]:
    """Paragraphs before the first table row or capitalised section heading."""
    out: list[Block] = []
    for block in doc.blocks[:MAX_HEADER_BLOCKS]:
        if block.kind != "p" or (block.text.isupper() and len(block.text) > 3):
            break
        out.append(block)
    return out


def _place_part(text: str) -> str | None:
    """Workplace name from a letterhead line; a person's name is dropped ("Gastroenterologická ambulance – MUDr. …")."""
    if _PERSON.search(text):
        head = text.split(_DASH, 1)[0] if _DASH in text else ""
        if not head or _PERSON.search(head):
            return None
        text = head
    text = _FICTIVE.sub("", text).strip()
    return text or None


def _examination(text: str) -> str:
    if _DASH in text:
        prefix, rest = text.split(_DASH, 1)
        if prefix.strip().casefold() in _GENERIC_TITLE_PREFIXES and rest.strip():
            return rest.strip()
    return text


def parse_header(doc: NormalizedDoc) -> DocumentHeader:
    blocks = _header_blocks(doc)
    report_id: HeaderValue | None = None
    issued: HeaderDate | None = None
    specimen: HeaderDate | None = None
    procedure: HeaderDate | None = None
    for block in blocks:
        if report_id is None and (m := _REPORT_ID.match(block.text)):
            report_id = HeaderValue(m.group(1), (_evidence(doc.doc_id, block),))
        # No year hint: a year-less "19. 10." gives no date. Two dates ("Vydáno: 4. 9. 2026 (kultivace),
        # 1. 9. 2026 (ostatní)") name no single issue date.
        if issued is None and (m := _ISSUED.match(block.text)) and (day := _single_date(m.group(1))):
            issued = HeaderDate(day, _evidence(doc.doc_id, block))
        if procedure is None and (m := _PROCEDURE.match(block.text)) and (day := _single_date(m.group(1))):
            procedure = HeaderDate(day, _evidence(doc.doc_id, block))
        if specimen is None and (m := _SPECIMEN.search(block.text)) and (day := _single_date(m.group(1))):
            specimen = HeaderDate(day, _evidence(doc.doc_id, block))

    # Letterhead: lines before the patient line; the address (postcode) separates the workplace from the title.
    letterhead: list[Block] = []
    for block in blocks:
        if _PATIENT.match(block.text):
            break
        if _BANNER in block.text:
            continue
        letterhead.append(block)
    address = next((i for i, b in enumerate(letterhead) if _POSTCODE.search(b.text)), None)
    if address is None:
        return DocumentHeader(doc.doc_id, report_id=report_id, issued=issued, specimen=specimen, procedure=procedure)

    place_parts: list[tuple[str, Block]] = []
    for block in letterhead[:address]:
        if _LABELLED.match(block.text):
            continue
        if (part := _place_part(block.text)) is not None:
            place_parts.append((part, block))
    place = (
        HeaderValue(", ".join(p for p, _ in place_parts), tuple(_evidence(doc.doc_id, b) for _, b in place_parts))
        if place_parts
        else None
    )
    title = next(
        (
            b
            for b in letterhead[address + 1 :]
            if not _LABELLED.match(b.text)
            and not _PERSON.search(b.text)
            and not _POSTCODE.search(b.text)
            and not _CONTACT.search(b.text)
            and any(c.isalpha() for c in b.text)
        ),
        None,
    )
    examination = HeaderValue(_examination(title.text), (_evidence(doc.doc_id, title),)) if title else None
    return DocumentHeader(
        doc.doc_id,
        examination=examination,
        place=place,
        report_id=report_id,
        issued=issued,
        specimen=specimen,
        procedure=procedure,
    )


def parse_headers(docs: dict[str, NormalizedDoc]) -> dict[str, DocumentHeader]:
    return {doc_id: parse_header(doc) for doc_id, doc in docs.items()}
