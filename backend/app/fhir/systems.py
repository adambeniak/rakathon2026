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
SID_SOURCE_DOCUMENT: Final = SID + "source-document"
SID_USER: Final = SID + "user"

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

DEMO_TAG_CODE: Final = "stafeta-demo"
TEST_TAG_CODE: Final = "stafeta-test"
TASK_CODE_COORDINATE_CASE: Final = "coordinate-case"

# --- External terminologies ---
LOINC: Final = "http://loinc.org"
V3_ROLE_CODE: Final = "http://terminology.hl7.org/CodeSystem/v3-RoleCode"
COVERAGE_TYPE: Final = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
ORGANIZATION_TYPE: Final = "http://terminology.hl7.org/CodeSystem/organization-type"
AUDIT_EVENT_TYPE: Final = "http://terminology.hl7.org/CodeSystem/audit-event-type"
RESTFUL_INTERACTION: Final = "http://hl7.org/fhir/restful-interaction"
SECURITY_SOURCE_TYPE: Final = "http://terminology.hl7.org/CodeSystem/security-source-type"

DOCX_MEDIA_TYPE: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def tag(code: str = DEMO_TAG_CODE) -> dict[str, str]:
    return {"system": CS_TAG, "code": code}
