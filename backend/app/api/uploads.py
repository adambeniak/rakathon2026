"""Reading multipart uploads with a hard size limit (never buffers more than the limit + 1 byte)."""

from __future__ import annotations

from fastapi import UploadFile

from app.documents.ingest import MAX_UPLOAD_BYTES, UploadedDocument, normalize_upload
from app.domain.errors import PayloadTooLargeError


async def read_upload(file: UploadFile, **kwargs: object) -> UploadedDocument:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise PayloadTooLargeError("Soubor je příliš velký. Maximální velikost jednoho souboru je 10 MB.")
    return normalize_upload(file.filename or "dokument", content, **kwargs)  # type: ignore[arg-type]
