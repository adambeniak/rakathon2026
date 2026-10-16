"""Referral resources: ServiceRequest, Consent, Provenance (GP confirmation of the AI prefill)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from app.domain.common import PartyRef
from app.domain.evidence import Evidence
from app.domain.referral import ReferralSubmission
from app.fhir.client import Resource
from app.fhir.mappers.directory import party_reference
from app.fhir.systems import (
    CONSENT_ACTION,
    CONSENT_SCOPE,
    DATA_OPERATION,
    EXT_CONSENT_STATEMENT,
    EXT_PREFILL_ADDED,
    EXT_PREFILL_COMPARISON,
    EXT_PREFILL_EDITED,
    EXT_REASON_EVIDENCE,
    ICD10,
    LOINC,
    PROVENANCE_PARTICIPANT_TYPE,
    SID_CONSENT,
    SID_SERVICE_REQUEST,
    V3_ACT_CODE,
    V3_PARTICIPATION_TYPE,
)


def service_request_to_fhir(
    case_id: str,
    submission: ReferralSubmission,
    *,
    patient_reference: str,
    requester: PartyRef,
    requester_reference: str,
    koc_reference: str,
    letter_reference: str,
    authored_on: datetime,
    diagnosis_evidence: Sequence[Evidence] = (),
) -> Resource:
    """The GP's referral: order to the KOC with the priority the GP confirmed; the diagnosis as the letter states it."""
    reason: Resource = {"text": submission.diagnosis_text}
    if submission.diagnosis_code:
        reason["coding"] = [{"system": ICD10, "code": submission.diagnosis_code}]
    resource: Resource = {
        "resourceType": "ServiceRequest",
        "identifier": [{"system": SID_SERVICE_REQUEST, "value": case_id}],
        "status": "active",
        "intent": "order",
        "priority": submission.priority,
        "code": {"text": "Převzetí do péče KOC"},
        "subject": {"reference": patient_reference},
        "authoredOn": authored_on.isoformat(),
        "requester": party_reference(requester, requester_reference),
        "performer": [{"reference": koc_reference}],
        "reasonCode": [reason],
        "supportingInfo": [{"reference": letter_reference}],
    }
    if diagnosis_evidence:  # only when the GP kept the diagnosis exactly as the letter states it
        resource["extension"] = [
            {
                "url": EXT_REASON_EVIDENCE,
                "extension": [
                    {"url": "doc_id", "valueString": e.doc_id},
                    {"url": "quote", "valueString": e.quote},
                ],
            }
            for e in diagnosis_evidence
        ]
    if submission.note:
        resource["note"] = [{"text": submission.note}]
    return resource


def consent_to_fhir(
    case_id: str,
    *,
    patient_reference: str,
    koc_reference: str,
    letter_reference: str,
    recorded_at: datetime,
    statements: Sequence[str],
) -> Resource:
    """Consent confirmed by the GP in the form. Statements from the letter are kept verbatim, never interpreted."""
    resource: Resource = {
        "resourceType": "Consent",
        "identifier": [{"system": SID_CONSENT, "value": case_id}],
        "status": "active",
        "scope": {"coding": [{"system": CONSENT_SCOPE, "code": "patient-privacy"}]},
        "category": [
            {
                "coding": [
                    {
                        "system": LOINC,
                        "code": "59284-0",
                    }
                ]
            }
        ],
        "patient": {"reference": patient_reference},
        "dateTime": recorded_at.isoformat(),
        "performer": [{"reference": patient_reference}],
        "organization": [{"reference": koc_reference}],
        "sourceReference": {"reference": letter_reference},
        "policyRule": {"coding": [{"system": V3_ACT_CODE, "code": "OPTIN"}]},
        "provision": {
            "type": "permit",
            "actor": [
                {
                    "role": {"coding": [{"system": V3_PARTICIPATION_TYPE, "code": "IRCP"}]},
                    "reference": {"reference": koc_reference},
                }
            ],
            "action": [{"coding": [{"system": CONSENT_ACTION, "code": "disclose"}]}],
        },
    }
    if statements:
        resource["extension"] = [{"url": EXT_CONSENT_STATEMENT, "valueString": text} for text in statements]
    return resource


def provenance_to_fhir(
    *,
    targets: Sequence[str],
    letter_reference: str,
    confirmed_by: PartyRef,
    confirmed_by_reference: str,
    recorded_at: datetime,
    edited: Sequence[str] | None,
    added: Sequence[str] | None,
) -> Resource:
    """The GP confirmed an AI-assisted prefill (AGENTS #5). Field NAMES only: values are not copied here."""
    comparison = "not-compared" if edited is None or added is None else "compared"
    extensions: list[Resource] = [{"url": EXT_PREFILL_COMPARISON, "valueCode": comparison}]
    if edited:
        extensions.append({"url": EXT_PREFILL_EDITED, "valueString": ",".join(edited)})
    if added:
        extensions.append({"url": EXT_PREFILL_ADDED, "valueString": ",".join(added)})
    return {
        "resourceType": "Provenance",
        "target": [{"reference": t} for t in targets],
        "recorded": recorded_at.isoformat(),
        "activity": {"coding": [{"system": DATA_OPERATION, "code": "CREATE"}]},
        "agent": [
            {
                "type": {"coding": [{"system": PROVENANCE_PARTICIPANT_TYPE, "code": "verifier"}]},
                "who": party_reference(confirmed_by, confirmed_by_reference),
            }
        ],
        "entity": [
            {"role": "source", "what": {"reference": letter_reference}},
        ],
        "reason": [{"text": "Návrh předvyplnění z žádanky potvrzen lékařem"}],
        "extension": extensions,
    }


def diagnosis_from_service_request(resource: Resource) -> tuple[str | None, str | None, list[Evidence]]:
    """(code, text, evidence) of the first reasonCode; evidence only if it was stored with the request."""
    reason = (resource.get("reasonCode") or [{}])[0]
    code = next((c.get("code") for c in reason.get("coding", []) if c.get("system") == ICD10), None)
    evidence: list[Evidence] = []
    for extension in resource.get("extension", []):
        if extension.get("url") != EXT_REASON_EVIDENCE:
            continue
        parts = {e.get("url"): e.get("valueString") for e in extension.get("extension", [])}
        if parts.get("doc_id") and parts.get("quote"):
            evidence.append(Evidence(doc_id=str(parts["doc_id"]), quote=str(parts["quote"])))
    return code, reason.get("text"), evidence
