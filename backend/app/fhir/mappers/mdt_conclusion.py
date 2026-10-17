"""MDT conclusion <-> FHIR: a final `Composition` (type `composition-type|mdt-conclusion`) + sign-off `Provenance`.

- Composition: identifier `sid/mdt-conclusion|<case>@<signed_at UTC>`, subject = Patient, encounter = EpisodeOfCare
  (the case), author and professional attester = the signing PractitionerRole (logical reference by business id),
  one section `mdt-conclusion-section|conclusion` whose narrative is the escaped text and whose extension
  `mdt-conclusion-text` keeps the exact text for reading it back.
- Provenance: target = the Composition, agent = the signing physician (who, when); written in the same transaction as
  the sign-off of the case Task, so the conclusion cannot be signed without being stored.
Code systems and the extension are Štafeta-local (listed in docs/fhir-mapping.md).
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from app.domain.common import PartyRef, Role
from app.fhir.client import Resource
from app.fhir.mappers.handover import practitioner_reference
from app.fhir.systems import (
    CS,
    CS_COMPOSITION_TYPE,
    CS_PROVENANCE_ACTIVITY,
    PROVENANCE_PARTICIPANT_TYPE,
    SD,
    SID,
    SID_PRACTITIONER_ROLE,
    V3_DATA_OPERATION,
)

SID_MDT_CONCLUSION: Final = SID + "mdt-conclusion"
CS_MDT_CONCLUSION_SECTION: Final = CS + "mdt-conclusion-section"
EXT_MDT_CONCLUSION_TEXT: Final = SD + "mdt-conclusion-text"
TYPE_MDT_CONCLUSION: Final = "mdt-conclusion"
ACTIVITY_SIGNOFF: Final = "mdt-conclusion-signoff"
TITLE: Final = "Závěr MDT"


@dataclass(frozen=True)
class MdtConclusionRecord:
    composition_id: str
    text: str
    signed_by: PartyRef
    signed_at: datetime


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
    author = practitioner_reference(signer)
    return {
        "resourceType": "Composition",
        "identifier": {"system": SID_MDT_CONCLUSION, "value": conclusion_business_id(case_id, signed_at)},
        "status": "final",
        "type": {"coding": [{"system": CS_COMPOSITION_TYPE, "code": TYPE_MDT_CONCLUSION, "display": TITLE}]},
        "subject": {"reference": patient_reference},
        "encounter": {"reference": episode_reference},
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
        "activity": {
            "coding": [
                {"system": V3_DATA_OPERATION, "code": "CREATE"},
                {"system": CS_PROVENANCE_ACTIVITY, "code": ACTIVITY_SIGNOFF},
            ]
        },
        "agent": [
            {
                "type": {"coding": [{"system": PROVENANCE_PARTICIPANT_TYPE, "code": "attester"}]},
                "who": practitioner_reference(signer),
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

    signer = PartyRef(id=identifier["value"], display=author.get("display", ""), role=Role.KOC_PHYSICIAN)
    return MdtConclusionRecord(
        composition_id=str(composition["id"]),
        text=text,
        signed_by=signer,
        signed_at=datetime.fromisoformat(composition["date"]),
    )


def is_conclusion_of(composition: Resource, case_id: str) -> bool:
    identifier = composition.get("identifier") or {}
    value = str(identifier.get("value", ""))
    return identifier.get("system") == SID_MDT_CONCLUSION and value.startswith(f"{case_id}@")


def _is_conclusion(section: Resource) -> bool:
    codings = section.get("code", {}).get("coding", [])
    return any(c.get("system") == CS_MDT_CONCLUSION_SECTION and c.get("code") == "conclusion" for c in codings)


def _narrative(text: str) -> str:
    lines = "<br/>".join(html.escape(line) for line in text.splitlines()) or html.escape(text)
    return f'<div xmlns="http://www.w3.org/1999/xhtml"><p>{lines}</p></div>'
