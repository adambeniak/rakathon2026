"""SourceDocument <-> DocumentReference.

`DocumentReference.date` = received (instant), `content.attachment.creation` = authored, attachment = base64 data.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import date, datetime

from app.domain.document import SourceDocument
from app.fhir.client import Resource
from app.fhir.systems import DOCX_MEDIA_TYPE, LOINC, SID_SOURCE_DOCUMENT


def document_to_fhir(
    document: SourceDocument,
    content: bytes,
    *,
    patient_reference: str,
    episode_reference: str | None,
    custodian_reference: str | None,
    author_reference: str | None,
) -> Resource:
    attachment = {
        "contentType": document.content_type or DOCX_MEDIA_TYPE,
        "data": base64.b64encode(content).decode("ascii"),
        "size": len(content),
        # FHIR R4 Attachment.hash is defined as SHA-1 (integrity check, not security).
        "hash": base64.b64encode(hashlib.sha1(content, usedforsecurity=False).digest()).decode("ascii"),
        "title": document.file_name or document.doc_id,
        "creation": document.authored_at.isoformat(),
    }
    resource: Resource = {
        "resourceType": "DocumentReference",
        "identifier": [{"system": SID_SOURCE_DOCUMENT, "value": document.doc_id}],
        "status": "current",
        "docStatus": "final",
        "subject": {"reference": patient_reference},
        "date": document.received_at.isoformat(),
        "description": document.title,
        "content": [{"attachment": attachment}],
    }
    if document.type_code:
        resource["type"] = {"coding": [{"system": LOINC, "code": document.type_code}]}
    if author_reference:
        resource["author"] = [{"reference": author_reference, **_display(document.author)}]
    if custodian_reference:
        resource["custodian"] = {"reference": custodian_reference, **_display(document.custodian)}
    if episode_reference:
        resource["context"] = {"encounter": [{"reference": episode_reference}]}
    return resource


def document_from_fhir(resource: Resource) -> SourceDocument:
    if resource.get("resourceType") != "DocumentReference":
        raise ValueError("expected a DocumentReference resource")
    doc_id = next((i["value"] for i in resource.get("identifier", []) if i.get("system") == SID_SOURCE_DOCUMENT), None)
    if doc_id is None:
        raise ValueError("DocumentReference has no source-document identifier")
    attachment = (resource.get("content") or [{}])[0].get("attachment", {})
    loinc = next((c["code"] for c in resource.get("type", {}).get("coding", []) if c.get("system") == LOINC), None)
    authors = resource.get("author") or [{}]
    return SourceDocument(
        doc_id=str(doc_id),
        title=resource.get("description") or str(doc_id),
        type_code=loinc,
        authored_at=_creation_date(str(attachment["creation"])),
        received_at=datetime.fromisoformat(str(resource["date"])),
        custodian=resource.get("custodian", {}).get("display"),
        author=authors[0].get("display"),
        file_name=attachment.get("title"),
        content_type=attachment.get("contentType"),
    )


@dataclass(frozen=True)
class StoredDocument:
    """A DocumentReference as stored in IRIS: metadata, server references and the decoded attachment."""

    source: SourceDocument
    reference: str  # "DocumentReference/<id>"
    patient_reference: str  # "Patient/<id>"
    content: bytes
    content_type: str


def stored_document_from_fhir(resource: Resource) -> StoredDocument:
    source = document_from_fhir(resource)
    subject = str(resource.get("subject", {}).get("reference", ""))
    if not subject.startswith("Patient/"):
        raise ValueError("DocumentReference.subject is not a Patient")
    attachment = (resource.get("content") or [{}])[0].get("attachment", {})
    if "data" not in attachment:
        raise ValueError("DocumentReference has no inline attachment data")
    return StoredDocument(
        source=source,
        reference=f"DocumentReference/{resource['id']}",
        patient_reference=subject,
        content=base64.b64decode(attachment["data"]),
        content_type=str(attachment.get("contentType") or DOCX_MEDIA_TYPE),
    )


def _creation_date(value: str) -> date:
    """`Attachment.creation` is a dateTime; we write a date but accept full timestamps."""
    return date.fromisoformat(value[:10])


def _display(value: str | None) -> dict[str, str]:
    return {"display": value} if value else {}
