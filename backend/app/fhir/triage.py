"""Triage proposals for a case: the examinations its referral letter lists that are not attached yet."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date

from app.documents.ingest import normalize_upload
from app.domain.common import PartyRef
from app.domain.errors import NotFoundError
from app.domain.triage import RequestProposal, propose_requests
from app.extraction.pipeline import CompletionClient
from app.extraction.referral_service import exams_from_letter
from app.fhir.cases import CaseReader
from app.fhir.directory import Directory
from app.fhir.mappers.document import document_from_fhir
from app.fhir.repository import FhirRepository
from app.fhir.workflow import authorize_case


@dataclass(frozen=True)
class ProposalsView:
    source_doc_id: str | None
    proposals: list[RequestProposal]


class TriageReader:
    def __init__(self, repository: FhirRepository, reader: CaseReader, llm: CompletionClient) -> None:
        self._repo = repository
        self._reader = reader
        self._llm = llm

    async def proposals(self, case_id: str, directory: Directory, actor: PartyRef) -> ProposalsView:
        loaded = await self._reader.load(case_id)
        authorize_case(loaded, actor, directory)
        based_on = (loaded.task.get("basedOn") or [{}])[0].get("reference", "")
        if not str(based_on).startswith("ServiceRequest/"):
            return ProposalsView(None, [])  # a case without a referral letter (e.g. the seeded story case)
        request = await self._repo.read(*str(based_on).split("/", 1))
        letter_reference = (request.get("supportingInfo") or [{}])[0].get("reference", "")
        if not str(letter_reference).startswith("DocumentReference/"):
            return ProposalsView(None, [])
        letter = await self._repo.read(*str(letter_reference).split("/", 1))
        documents = await self._repo.search(
            "DocumentReference", {"encounter": loaded.task["focus"]["reference"], "_count": "100"}
        )
        await self._repo.audit_read(
            [
                f"Task/{loaded.task['id']}",
                str(based_on),
                str(letter_reference),
                *(f"DocumentReference/{d['id']}" for d in documents),
            ],
            subtype="read",
        )
        existing = [document_from_fhir(d) for d in documents]
        attachment = (letter.get("content") or [{}])[0].get("attachment", {})
        if "data" not in attachment:
            raise NotFoundError("referral letter content", case_id)
        source = document_from_fhir(letter)
        upload = normalize_upload(
            attachment.get("title") or source.doc_id,
            base64.b64decode(attachment["data"]),
            authored_date=date.fromisoformat(str(attachment["creation"])[:10]),
            doc_id=source.doc_id,
        )
        await self._repo.audit_extract()
        exams = await exams_from_letter(upload, self._llm)
        proposals = propose_requests(
            exams, existing, [o.org for o in directory.orgs], [(r.role, r.display) for r in directory.roles]
        )
        return ProposalsView(source.doc_id, proposals)
