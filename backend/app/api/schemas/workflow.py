"""Schemas of the case workflow endpoints (transitions, document requests, received reports)."""

from __future__ import annotations

from datetime import date

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.api.schemas.cases import CaseSummary, DocumentSummary
from app.domain.task import TaskBusinessStatus, TaskStatus
from app.domain.triage import RequestProposal


class TransitionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"event": "accept"},
                {"event": "missing_found", "reason": "chybí CT"},
                {"event": "record_mdt_conclusion", "conclusion": "Závěr MDT dle zápisu."},
            ]
        },
    )

    event: str = Field(
        max_length=40,
        description="accept | request_documents | mark_complete | docs_received | missing_found | postpone | resume | "
        "record_mdt_conclusion (koc_physician; stores the text) | send_feedback (coordinator; e-mails the GP and "
        "records the hand-over to the mail relay) | delivery_confirmed (system only: refused for every demo role) | "
        "gp_opened (the referring GP) | close (coordinator). "
        "Other machine events (mark_ready_mdt, reopen) are refused (422) until their endpoints exist.",
    )
    reason: str | None = Field(None, max_length=500, description="Required by missing_found and postpone.")
    resume_on: str | None = Field(None, max_length=200, description="Required by postpone: date or external step.")
    conclusion: str | None = Field(
        None,
        max_length=4000,
        description="Required by record_mdt_conclusion. The signing clinician is the acting user (`confirmed_by`).",
    )
    receipt_id: str | None = Field(None, max_length=200, description="Required by delivery_confirmed.")


class DocumentRequestItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=300, description="What is requested, e.g. the label from the proposal.")
    recipient_org_id: str = Field(max_length=100, description="Directory workplace that holds the report.")
    exam_date: date | None = None


class DocumentRequestsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DocumentRequestItem] = Field(min_length=1, max_length=30)


class DocumentRequestOut(BaseModel):
    id: str = Field(description="Business id of the request task, e.g. 'rakathon-2026-prochazkova-req-1'.")
    label: str
    recipient: str | None = Field(None, description="Workplace display name.")
    exam_date: date | None = None
    due: AwareDatetime | None = Field(None, description="Two working days after the request.")
    status: TaskStatus
    business_status: TaskBusinessStatus | None = None
    result_doc_id: str | None = Field(None, description="The delivered report, once linked.")


class ProposalsOut(BaseModel):
    source_doc_id: str | None = Field(None, description="The referral letter the proposals are quoted from.")
    proposals: list[RequestProposal]


class DocumentRequestsCreated(BaseModel):
    case: CaseSummary
    requests: list[DocumentRequestOut]


class DocumentReceived(BaseModel):
    document: DocumentSummary
    open_requests_remaining: int
    case_event: str | None = Field(
        None, description="'podklady_kompletni' when this report fulfilled the last open request."
    )
    case: CaseSummary
