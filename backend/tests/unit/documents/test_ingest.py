from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from app.documents.ingest import MAX_UPLOAD_BYTES, doc_id_from_filename, normalize_upload
from app.documents.normalize import normalize
from app.domain.errors import InvalidInputError, PayloadTooLargeError, UnsupportedMediaError
from app.extraction.llm import CACHE_MODEL, cache_key
from app.extraction.prompt import SYSTEM_PROMPT, build_user_message
from app.extraction.values import RESPONSE_SCHEMA
from tests.document_fixtures import DOCS_DIR

LETTER = DOCS_DIR / "07_PL_zadost_KOC2_2026-10-02.docx"


def _minimal_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objects) + 1, xref)
    return out


def test_upload_normalises_to_exactly_the_text_the_llm_cache_was_recorded_with() -> None:
    uploaded = normalize_upload("07_PL_zadost_KOC2_2026-10-02.docx", LETTER.read_bytes())
    from_path = normalize(LETTER)

    assert uploaded.doc.text == from_path.text
    assert uploaded.doc.doc_id == from_path.doc_id
    assert uploaded.doc.authored_date == from_path.authored_date
    key = lambda d: cache_key(CACHE_MODEL, "extract-v1", SYSTEM_PROMPT, RESPONSE_SCHEMA, build_user_message(d))  # noqa: E731
    assert key(uploaded.doc) == key(from_path)


def test_file_name_never_becomes_a_path_or_an_invalid_id() -> None:
    assert doc_id_from_filename("../../etc/passwd.docx") == "passwd"
    assert doc_id_from_filename("07 PL žádost KOC2.docx") == "07_PL_zadost_KOC2"
    assert doc_id_from_filename("???.docx") == "uploaded_document"


def test_pdf_text_layer_is_read() -> None:
    uploaded = normalize_upload("zadost_2026-10-02.pdf", _minimal_pdf("Pacientka: Alena Prochazkova"))

    assert "Alena Prochazkova" in uploaded.doc.text
    assert uploaded.content_type == "application/pdf"
    assert uploaded.doc.authored_date is not None


def test_pdf_without_text_is_refused() -> None:
    with pytest.raises(InvalidInputError):
        normalize_upload("x.pdf", _minimal_pdf(""))


def test_declared_type_is_ignored_wrong_magic_is_refused() -> None:
    with pytest.raises(UnsupportedMediaError):
        normalize_upload("report.docx", b"MZ\x90\x00 not a document")


def test_zip_without_document_xml_is_refused() -> None:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", "hi")

    with pytest.raises(UnsupportedMediaError):
        normalize_upload("x.docx", buffer.getvalue())


def test_zip_bomb_is_refused_by_unpacked_size() -> None:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"0" * (60 * 1024 * 1024))

    assert len(buffer.getvalue()) < MAX_UPLOAD_BYTES
    with pytest.raises(PayloadTooLargeError):
        normalize_upload("x.docx", buffer.getvalue())


def test_oversize_and_empty_uploads_are_refused() -> None:
    with pytest.raises(PayloadTooLargeError):
        normalize_upload("x.pdf", b"%PDF-" + b"0" * MAX_UPLOAD_BYTES)
    with pytest.raises(InvalidInputError):
        normalize_upload("x.pdf", b"")
