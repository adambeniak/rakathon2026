"""Identifier systems and CodeSystem URIs: the single place for every URI the backend writes to FHIR.

Demo-only systems live under https://stafeta.example/fhir/ and are listed in `docs/fhir-mapping.md`.
"""

from __future__ import annotations

from typing import Final

SID: Final = "https://stafeta.example/fhir/sid/"
CS: Final = "https://stafeta.example/fhir/CodeSystem/"

# --- Business identifiers (identifier.system) ---
SID_ORGANIZATION: Final = SID + "organization"
SID_PRACTITIONER: Final = SID + "practitioner"
SID_PRACTITIONER_ROLE: Final = SID + "practitioner-role"
SID_RELATED_PERSON: Final = SID + "related-person"
SID_COVERAGE: Final = SID + "coverage"
SID_CASE: Final = SID + "case"
SID_CASE_TASK: Final = SID + "case-task"
SID_CASE_STEP: Final = SID + "case-step"  # pathway step / ad-hoc Task, value = domain Task.id
SID_STEP_ORDER: Final = SID + "case-step-order"  # ServiceRequest of a pathway step, value = domain Task.id
SID_CAREPLAN: Final = SID + "careplan"  # value = "<case id>.<plan key>"
SID_SOURCE_DOCUMENT: Final = SID + "source-document"
SID_USER: Final = SID + "user"
SID_SERVICE_REQUEST: Final = SID + "service-request"
SID_CONSENT: Final = SID + "consent"
SID_COMMUNICATION_REQUEST: Final = SID + "communication-request"
SID_REQUEST_TASK: Final = SID + "request-task"
SID_HANDOVER: Final = SID + "handover"
SID_HANDOVER_ENTRY: Final = SID + "handover-entry"
SID_DEVICE: Final = SID + "device"
SID_SMS_NOTIFICATION: Final = SID + "sms-notification"  # Communication (SMS), value = "<task id>:<kind>"
SID_SMS_GATEWAY_MESSAGE: Final = SID + "sms-gateway-message-id"  # Communication (SMS): the gateway's receipt

# CZ Core (hl7.cz/fhir/core 1.0.0) identifier systems.
# Rodné číslo: fixedUri of StructureDefinition cz-rodcis-identifier; value = digits without the slash.
CZ_RODNE_CISLO: Final = "https://ncez.mzcr.cz/fhir/sid/rcis"
CZ_ICP: Final = "https://ncez.mzcr.cz/fhir/sid/icp"
CZ_INSURER_CODE: Final = "https://ncez.mzcr.cz/fhir/sid/kp"

# --- Our CodeSystems ---
CS_TAG: Final = CS + "tag"
CS_CASE_STATE: Final = CS + "case-state"
CS_TASK_CODE: Final = CS + "task-code"
CS_TASK_BUSINESS_STATUS: Final = CS + "task-business-status"
CS_WORKFLOW_ROLE: Final = CS + "workflow-role"
CS_ORGANIZATION_KIND: Final = CS + "organization-kind"
CS_EPISODE_TYPE: Final = CS + "episode-type"
CS_AUDIT_TYPE: Final = CS + "audit-type"
CS_AUDIT_EVENT_CODE: Final = CS + "audit-event-code"
CS_COMMUNICATION_CATEGORY: Final = CS + "communication-category"

SD: Final = "https://stafeta.example/fhir/StructureDefinition/"
EXT_CONSENT_STATEMENT: Final = SD + "consent-statement"
EXT_PREFILL_EDITED: Final = SD + "prefill-edited-fields"
EXT_PREFILL_ADDED: Final = SD + "prefill-added-fields"
EXT_PREFILL_CLEARED: Final = SD + "prefill-cleared-fields"
EXT_PREFILL_COMPARISON: Final = SD + "prefill-comparison"
EXT_REQUEST_LABEL: Final = SD + "request-label"
EXT_REQUEST_EXAM_DATE: Final = SD + "request-exam-date"
EXT_REASON_EVIDENCE: Final = SD + "reason-evidence"
EXT_BATON_ROLE: Final = SD + "baton-role"
EXT_RESUME_BATON_ROLE: Final = SD + "resume-baton-role"
EXT_RESUME_ON: Final = SD + "resume-on"
EXT_MDT_START: Final = SD + "mdt-start"
EXT_CONCLUSION_CONFIRMED: Final = SD + "conclusion-confirmed"
EXT_DELIVERY_RECEIPT: Final = SD + "delivery-receipt"

CS_COMPOSITION_TYPE: Final = CS + "composition-type"
CS_HANDOVER_SECTION: Final = CS + "handover-section"
CS_HANDOVER_STATUS: Final = CS + "handover-field-status"
CS_REVIEW_STATE: Final = CS + "handover-review-state"
CS_PROVENANCE_ACTIVITY: Final = CS + "provenance-activity"

# --- Our extensions (StructureDefinition URLs; not loaded into IRIS, listed in docs/fhir-mapping.md) ---
EXT_HANDOVER_EPISODE: Final = SD + "handover-episode"
EXT_HANDOVER_AS_OF: Final = SD + "handover-as-of"
EXT_HANDOVER_FIELD_STATUS: Final = SD + "handover-field-status"
EXT_HANDOVER_REVIEW: Final = SD + "handover-review"
EXT_HANDOVER_EDITED_VALUE: Final = SD + "handover-edited-value"
EXT_HANDOVER_SECTION: Final = SD + "handover-section"
EXT_HANDOVER_CONFLICTS: Final = SD + "handover-conflicts"
EXT_EVIDENCE_QUOTE: Final = SD + "evidence-quote"
EXT_PREVIOUS_VALUE_HASH: Final = SD + "previous-value-sha256"
EXT_READINESS_ITEM: Final = SD + "readiness-item"  # Provenance (waiver): the MDT readiness item that was waived

# --- Pathway coordination (F2-4) ---
CS_PATHWAY_ACTION: Final = CS + "pathway-action"

EXT_DUE: Final = SD + "due-rule"  # PlanDefinition.action
EXT_SLA: Final = SD + "sla-rule"  # PlanDefinition.action
EXT_PLACE: Final = SD + "place"  # PlanDefinition.action, Task: workplace as text
EXT_OWNER: Final = SD + "owner-role"  # PlanDefinition.action
EXT_READINESS: Final = SD + "mdt-required-items"  # PlanDefinition
EXT_DEPENDS_ON: Final = SD + "depends-on"  # Task: business id of a Task that must finish first (repeats)
EXT_SLA_DUE: Final = SD + "sla-due"  # Task: agreed deadline
EXT_ESCALATED_AT: Final = SD + "escalated-at"  # Task: when the overdue escalation fired
EXT_AD_HOC: Final = SD + "ad-hoc"  # Task: single task outside a pathway
EXT_DEMO_ASSUMPTION: Final = SD + "demo-assumption"  # Task: due date comes from a demo template
EXT_RECORDED_BY: Final = SD + "recorded-on-behalf-by"  # Task: coordinator who recorded progress for a workplace
EXT_ON_BEHALF_OF: Final = SD + "on-behalf-of"  # AuditEvent.agent: workplace the actor recorded a step for

DEMO_TAG_CODE: Final = "stafeta-demo"
TEST_TAG_CODE: Final = "stafeta-test"
TASK_CODE_COORDINATE_CASE: Final = "coordinate-case"
TASK_CODE_REQUEST_REPORT: Final = "request-report"
TASK_CODE_RESULT_DOCUMENT: Final = "result-document"  # Task.output.type

# --- External terminologies ---
LOINC: Final = "http://loinc.org"
ICD10: Final = "http://hl7.org/fhir/sid/icd-10"
CONSENT_SCOPE: Final = "http://terminology.hl7.org/CodeSystem/consentscope"
CONSENT_ACTION: Final = "http://terminology.hl7.org/CodeSystem/consentaction"
PROVENANCE_PARTICIPANT_TYPE: Final = "http://terminology.hl7.org/CodeSystem/provenance-participant-type"
V3_ACT_CODE: Final = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
V3_PARTICIPATION_TYPE: Final = "http://terminology.hl7.org/CodeSystem/v3-ParticipationType"
DATA_OPERATION: Final = "http://terminology.hl7.org/CodeSystem/v3-DataOperation"
ICDO3: Final = "http://terminology.hl7.org/CodeSystem/icd-o-3"
CONDITION_CATEGORY: Final = "http://terminology.hl7.org/CodeSystem/condition-category"
CONDITION_VERIFICATION: Final = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
OBSERVATION_CATEGORY: Final = "http://terminology.hl7.org/CodeSystem/observation-category"
LIST_EMPTY_REASON: Final = "http://terminology.hl7.org/CodeSystem/list-empty-reason"
PROVENANCE_AGENT_TYPE: Final = PROVENANCE_PARTICIPANT_TYPE
UCUM: Final = "http://unitsofmeasure.org"
V3_ROLE_CODE: Final = "http://terminology.hl7.org/CodeSystem/v3-RoleCode"
COVERAGE_TYPE: Final = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
ORGANIZATION_TYPE: Final = "http://terminology.hl7.org/CodeSystem/organization-type"
AUDIT_EVENT_TYPE: Final = "http://terminology.hl7.org/CodeSystem/audit-event-type"
RESTFUL_INTERACTION: Final = "http://hl7.org/fhir/restful-interaction"
V3_DATA_OPERATION: Final = "http://terminology.hl7.org/CodeSystem/v3-DataOperation"
V3_PARTICIPATION_MODE: Final = "http://terminology.hl7.org/CodeSystem/v3-ParticipationMode"
SECURITY_SOURCE_TYPE: Final = "http://terminology.hl7.org/CodeSystem/security-source-type"

DOCX_MEDIA_TYPE: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def tag(code: str = DEMO_TAG_CODE) -> dict[str, str]:
    return {"system": CS_TAG, "code": code}
