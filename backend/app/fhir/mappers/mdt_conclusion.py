"""MDT conclusion <-> FHIR: a final `Composition` (type `composition-type|mdt-conclusion`) + sign-off `Provenance`.

- Composition: identifier `sid/mdt-conclusion|<case>@<signed_at UTC>`, subject = Patient, extension `handover-episode`
  (the shared Composition -> EpisodeOfCare link; `Composition.encounter` allows Encounter only in R4), author and
  professional attester = the signing PractitionerRole (typed logical reference by business id), one section
  `mdt-conclusion-section|conclusion` whose narrative is the escaped text and whose extension `mdt-conclusion-text`
  keeps the exact text for reading it back.
- Provenance: target = the Composition, activity = v3-DocumentCompletion|LA (legally authenticated), agent = the
  signing physician with their workflow role (who, when); written in the same transaction as the sign-off of the case
  Task, so the conclusion cannot be signed without being stored.
Štafeta-local identifier/code systems and extensions are to be listed in docs/fhir-mapping.md (issue #75).
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from app.domain.common import PartyRef, Role
from app.fhir.client import Resource
from app.fhir.systems import (
    CS,
    CS_COMPOSITION_TYPE,
    CS_WORKFLOW_ROLE,
    EXT_HANDOVER_EPISODE,
    PROVENANCE_PARTICIPANT_TYPE,
    SD,
    SID,
    SID_PRACTITIONER_ROLE,
)

SID_MDT_CONCLUSION: Final = SID + "mdt-conclusion"
CS_MDT_CONCLUSION_SECTION: Final = CS + "mdt-conclusion-section"
EXT_MDT_CONCLUSION_TEXT: Final = SD + "mdt-conclusion-text"
V3_DOCUMENT_COMPLETION: Final = "http://terminology.hl7.org/CodeSystem/v3-DocumentCompletion"
TYPE_MDT_CONCLUSION: Final = "mdt-conclusion"
TITLE: Final = "Závěr MDT"


@dataclass(frozen=True)
class MdtConclusionRecord:
    """What the stored Composition says. The signer's role is not stored on it: the service resolves it from the
    directory (`signer_role`), it is never assumed here."""

    composition_id: str
    text: str
    signer_id: str
    signer_display: str
    signed_at: datetime
    signer_role: Role | None = None


def conclusion_business_id(case_id: str, signed_at: datetime) -> str:
    return f"{case_id}@{signed_at.astimezone(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"


def mdt_conclusion_to_fhir(
    case_id: str,
    text: str,
    *,
    patient_reference: str,
    episode_reference: str,
    signer: PartyRef,
    signed_at: datetime,
) -> Resource:
    author = _practitioner_role_reference(signer)
    return {
        "resourceType": "Composition",
        "identifier": {"system": SID_MDT_CONCLUSION, "value": conclusion_business_id(case_id, signed_at)},
        "status": "final",
        "type": {"coding": [{"system": CS_COMPOSITION_TYPE, "code": TYPE_MDT_CONCLUSION, "display": TITLE}]},
        "subject": {"reference": patient_reference},
        "extension": [{"url": EXT_HANDOVER_EPISODE, "valueReference": {"reference": episode_reference}}],
        "date": signed_at.isoformat(),
        "author": [author],
        "title": TITLE,
        "attester": [{"mode": "professional", "time": signed_at.isoformat(), "party": author}],
        "section": [
            {
                "title": TITLE,
                "code": {"coding": [{"system": CS_MDT_CONCLUSION_SECTION, "code": "conclusion"}]},
                "text": {"status": "generated", "div": _narrative(text)},
                "extension": [{"url": EXT_MDT_CONCLUSION_TEXT, "valueString": text}],
            }
        ],
    }


def mdt_conclusion_provenance(*, target: str, signer: PartyRef, recorded: datetime) -> Resource:
    """`target` is the Composition's `urn:uuid` (same transaction) or `Composition/<id>`."""
    return {
        "resourceType": "Provenance",
        "target": [{"reference": target}],
        "recorded": recorded.isoformat(),
        "activity": {"coding": [{"system": V3_DOCUMENT_COMPLETION, "code": "LA", "display": "legally authenticated"}]},
        "agent": [
            {
                "type": {"coding": [{"system": PROVENANCE_PARTICIPANT_TYPE, "code": "attester"}]},
                "role": [{"coding": [{"system": CS_WORKFLOW_ROLE, "code": signer.role.value}]}],
                "who": _practitioner_role_reference(signer),
            }
        ],
    }


def mdt_conclusion_from_fhir(composition: Resource) -> MdtConclusionRecord:
    if composition.get("resourceType") != "Composition":
        raise ValueError("expected a Composition")
    section = next(s for s in composition["section"] if _is_conclusion(s))
    text = next(e["valueString"] for e in section["extension"] if e["url"] == EXT_MDT_CONCLUSION_TEXT)
    author = composition["author"][0]
    identifier = author["identifier"]
    if identifier.get("system") != SID_PRACTITIONER_ROLE:
        raise ValueError("conclusion author is not a PractitionerRole by business id")
    return MdtConclusionRecord(
        composition_id=str(composition["id"]),
        text=text,
        signer_id=identifier["value"],
        signer_display=author.get("display", ""),
        signed_at=datetime.fromisoformat(composition["date"]),
    )


def is_conclusion_of(composition: Resource, case_id: str) -> bool:
    """The business id is `<case>@<UTC instant>`; the instant has no '@', so split on the last one."""
    identifier = composition.get("identifier") or {}
    case_part, separator, _ = str(identifier.get("value", "")).rpartition("@")
    return identifier.get("system") == SID_MDT_CONCLUSION and bool(separator) and case_part == case_id


def latest_conclusion(compositions: list[Resource]) -> Resource:
    """The most recently signed one, compared as instants (ISO strings with different offsets do not sort)."""
    return max(compositions, key=lambda c: datetime.fromisoformat(str(c["date"])))


def _practitioner_role_reference(signer: PartyRef) -> Resource:
    """Logical reference by business id; typed so a validator can check the target, display only when not empty."""
    reference: Resource = {
        "type": "PractitionerRole",
        "identifier": {"system": SID_PRACTITIONER_ROLE, "value": signer.id},
    }
    if signer.display:
        reference["display"] = signer.display
    return reference


def _is_conclusion(section: Resource) -> bool:
    codings = section.get("code", {}).get("coding", [])
    return any(c.get("system") == CS_MDT_CONCLUSION_SECTION and c.get("code") == "conclusion" for c in codings)


def _narrative(text: str) -> str:
    lines = "<br/>".join(html.escape(line) for line in text.splitlines()) or html.escape(text)
    return f'<div xmlns="http://www.w3.org/1999/xhtml"><p>{lines}</p></div>'
