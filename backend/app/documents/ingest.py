"""Uploaded letters and reports -> NormalizedDoc (owner: P2; the HTTP layer only passes bytes).

The declared content type and the file name are never trusted: the format is decided by magic bytes, the size and
archive structure are bounded, and the file name only yields a sanitised document id and an authored date.
"""

from __future__ import annotations

import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date
from io import BytesIO

from pypdf import PdfReader

from app.documents.normalize import NormalizedDoc, build_doc, normalize_docx_bytes, normalize_text, stem_date
from app.domain.common import BUSINESS_ID_PATTERN
from app.domain.errors import InvalidInputError, PayloadTooLargeError, UnsupportedMediaError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
MAX_TEXT_CHARS = 500_000
MAX_ARCHIVE_ENTRIES = 2000
MAX_PDF_PAGES = 50
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MEDIA_TYPE = "application/pdf"

_ID_CHARS = re.compile(r"[^A-Za-z0-9_.@-]+")


@dataclass(frozen=True)
class UploadedDocument:
    doc: NormalizedDoc
    content: bytes
    content_type: str
    file_name: str


def doc_id_from_filename(file_name: str) -> str:
    """'07_PL žádost.docx' -> '07_PL_zadost' style id: the stem, ASCII-safe, matching the business id pattern."""
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", file_name.replace("\\", "/").rsplit("/", 1)[-1])
    folded = _ID_CHARS.sub("_", _ascii(stem)).strip("._-@")[:100]
    return folded if folded and re.match(BUSINESS_ID_PATTERN, folded) else "uploaded_document"


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def sniff_media_type(content: bytes) -> str:
    if content.startswith(b"%PDF-"):
        return PDF_MEDIA_TYPE
    if content.startswith(b"PK\x03\x04"):
        return DOCX_MEDIA_TYPE  # confirmed by `_check_docx_archive`
    raise UnsupportedMediaError("only DOCX and PDF documents are accepted")


def _check_docx_archive(content: bytes) -> None:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
                raise PayloadTooLargeError("document archive is too large when unpacked")
            if "word/document.xml" not in {i.filename for i in infos}:
                raise UnsupportedMediaError("the archive is not a DOCX document")
    except zipfile.BadZipFile as exc:
        raise UnsupportedMediaError("the archive is not a DOCX document") from exc


def _pdf_blocks(content: bytes) -> list[tuple[str, str, str | None]]:
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise InvalidInputError("encrypted PDF documents cannot be read")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise PayloadTooLargeError(f"PDF has more than {MAX_PDF_PAGES} pages")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except (InvalidInputError, PayloadTooLargeError):
        raise
    except Exception as exc:
        raise InvalidInputError("the PDF could not be read") from exc
    if len(text) > MAX_TEXT_CHARS:
        raise PayloadTooLargeError("the PDF text is too long")
    lines = [line for line in normalize_text(text).split("\n") if line]
    if not lines:
        raise InvalidInputError("the PDF has no text layer (scanned documents are not supported)")
    return [("p", line, None) for line in lines]


def normalize_upload(
    file_name: str, content: bytes, *, authored_date: date | None = None, doc_id: str | None = None
) -> UploadedDocument:
    """Validate and normalise an upload. `authored_date` overrides the date in the file name."""
    if not content:
        raise InvalidInputError("the uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise PayloadTooLargeError("Soubor je příliš velký. Maximální velikost jednoho souboru je 10 MB.")
    media_type = sniff_media_type(content)
    resolved_id = doc_id or doc_id_from_filename(file_name)
    authored = authored_date or stem_date(resolved_id)
    if media_type == DOCX_MEDIA_TYPE:
        _check_docx_archive(content)
        try:
            doc = normalize_docx_bytes(resolved_id, content, authored)
        except Exception as exc:
            raise InvalidInputError("the DOCX document could not be read") from exc
    else:
        doc = build_doc(resolved_id, _pdf_blocks(content), authored)
    return UploadedDocument(doc=doc, content=content, content_type=media_type, file_name=file_name[:200])
