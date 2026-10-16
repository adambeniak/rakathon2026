"""Reading multipart uploads with a hard size limit (never buffers more than the limit + 1 byte)."""

from __future__ import annotations

from datetime import date

from fastapi import UploadFile

from app.documents.ingest import UploadedDocument, normalize_upload, too_large_message
from app.domain.errors import PayloadTooLargeError


async def read_upload(
    file: UploadFile, *, max_bytes: int, authored_date: date | None = None, doc_id: str | None = None
) -> UploadedDocument:
    """`max_bytes` is `Settings.upload_max_bytes` (the body-size middleware enforces the same limit earlier)."""
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise PayloadTooLargeError(too_large_message(max_bytes))
    return normalize_upload(
        file.filename or "dokument", content, authored_date=authored_date, doc_id=doc_id, max_bytes=max_bytes
    )
