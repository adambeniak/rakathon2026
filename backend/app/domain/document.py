"""Source documents of a case. A document is known at as_of only if authored <= as_of AND received <= as_of."""

from __future__ import annotations

from datetime import date

from pydantic import AwareDatetime, Field

from app.domain.common import BUSINESS_ID_PATTERN, DomainModel


class SourceDocument(DomainModel):
    doc_id: str = Field(pattern=BUSINESS_ID_PATTERN, description="File stem, e.g. '11_Histologie_KOC2_2026-10-19'.")
    title: str = Field(description="Short Czech title for lists.")
    type_code: str | None = Field(None, description="LOINC document type, e.g. '11526-1'.")
    authored_at: date = Field(description="Date the report was written (time of day unknown).")
    received_at: AwareDatetime = Field(description="When the KOC received the document.")
    custodian: str | None = Field(None, description="Issuing workplace (display name).")
    author: str | None = Field(None, description="Signing professional (display name).")
    file_name: str | None = None
    content_type: str | None = None
