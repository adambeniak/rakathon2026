"""Handover <-> FHIR: `Composition` (15 sections) + derived resources + `Provenance` (F2-2, ADR-0004).

- Composition: identifier `sid/handover|<case>@<as_of UTC>`, status preliminary -> final, type our
  `composition-type|handover`, author = the Štafeta AI Device (logical reference), section per handover field with
  code `handover-section|<key>`, generated narrative, field status + review state as extensions, `emptyReason` when
  the field is missing, entries -> derived resources (Condition, MedicationStatement, Observation) or the source
  DocumentReferences (field 12) / Patient (field 1).
- Provenance per derived resource: entity.what = source DocumentReference, the verbatim quote + char span in the
  `evidence-quote` extension, agent = Device (model + prompt versions). Confirmation by a physician adds a Provenance
  targeting the Composition (agent = PractitionerRole by business identifier, previous value hash).
"""

from __future__ import annotations

import copy
import html
import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import quote

from pydantic import JsonValue

from app.domain.common import PartyRef, Role
from app.domain.handover import (
    Handover,
    HandoverFieldBase,
    HandoverFields,
    HandoverItem,
    HandoverStatus,
    ReviewState,
    SectionReview,
)
from app.fhir.client import Resource
from app.fhir.systems import (
    CONDITION_CATEGORY,
    CONDITION_VERIFICATION,
    CS_COMPOSITION_TYPE,
    CS_HANDOVER_SECTION,
    CS_HANDOVER_STATUS,
    CS_PROVENANCE_ACTIVITY,
    CS_WORKFLOW_ROLE,
    EXT_EVIDENCE_QUOTE,
    EXT_HANDOVER_AS_OF,
    EXT_HANDOVER_EDITED_VALUE,
    EXT_HANDOVER_EPISODE,
    EXT_HANDOVER_FIELD_STATUS,
    EXT_HANDOVER_REVIEW,
    EXT_HANDOVER_SECTION,
    EXT_PREVIOUS_VALUE_HASH,
    ICD10,
    ICDO3,
    LIST_EMPTY_REASON,
    LOINC,
    OBSERVATION_CATEGORY,
    PROVENANCE_AGENT_TYPE,
    SID_DEVICE,
    SID_HANDOVER,
    SID_HANDOVER_ENTRY,
    SID_PRACTITIONER_ROLE,
    SID_SOURCE_DOCUMENT,
    UCUM,
)

MCODE_MORPHOLOGY = "http://hl7.org/fhir/us/mcode/StructureDefinition/mcode-histology-morphology-behavior"
DEVICE_ID = "stafeta-handover-ai"
TITLE = "Předávka k MDT"
# LOINC codes for the vitals of field 10 (other values carry text codes: no invented codings).
VITAL_LOINC = {"Hmotnost": ("29463-7", "Body weight", "kg"), "Výška": ("8302-2", "Body height", "cm")}
INTERPRETATION = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"
REVIEW_DONE = frozenset({ReviewState.CONFIRMED, ReviewState.ACCEPTED_MISSING})


@dataclass(frozen=True)
class FhirContext:
    """References resolved by the store before mapping."""

    patient: str  # "Patient/12"
    episode: str  # "EpisodeOfCare/13"
    documents: Mapping[str, str]  # doc_id -> "DocumentReference/14"
    device_display: str  # "Štafeta AI · <model> · extract-v1, epicrisis-v1"
    recorded: datetime


@dataclass(frozen=True)
class StoredReview:
    """What a stored Composition says about the review (read back for the API)."""

    fhir_id: str
    business_id: str
    status: Literal["preliminary", "final"]
    sections: dict[str, SectionReview]
    edited_values: dict[str, JsonValue]


# ---------------------------------------------------------------- identifiers and helpers


def handover_business_id(case_id: str, as_of: datetime) -> str:
    """Stable per (case, as_of); the instant in UTC so no '+' needs escaping in searches."""
    return f"{case_id}@{as_of.astimezone(UTC):%Y%m%dT%H%MZ}"


SECTION_TITLES: dict[str, str] = {
    info.alias or name: info.description or name for name, info in HandoverFields.model_fields.items()
}


def section_keys() -> list[str]:
    return [info.alias or name for name, info in HandoverFields.model_fields.items()]


def _fields(handover: Handover) -> list[tuple[str, str, HandoverFieldBase]]:
    return [
        (info.alias or name, info.description or name, getattr(handover.fields, name))
        for name, info in HandoverFields.model_fields.items()
    ]


def _identifier_query(system: str, value: str) -> str:
    """`identifier=system|value` with the token URL-encoded: entry ids contain '#', which would start a fragment."""
    return "identifier=" + quote(f"{system}|{value}", safe="")


def _urn(identifier: str) -> str:
    return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, SID_HANDOVER_ENTRY + '|' + identifier)}"


def _device() -> Resource:
    return {"identifier": {"system": SID_DEVICE, "value": DEVICE_ID}}


def practitioner_reference(actor: PartyRef) -> Resource:
    """Logical reference by business identifier (the API knows the PractitionerRole id, not its FHIR id)."""
    return {"identifier": {"system": SID_PRACTITIONER_ROLE, "value": actor.id}, "display": actor.display}


def _narrative(field: HandoverFieldBase) -> Resource:
    lines = [_item_text(i) for i in field.items] or [f"Chybí: {m.item} – {m.reason}" for m in field.missing_items]
    if field.note:
        lines.append(f"Poznámka: {field.note}")
    body = "".join(f"<li>{html.escape(line)}</li>" for line in lines) or "<li>Bez údajů.</li>"
    return {"status": "generated", "div": f'<div xmlns="http://www.w3.org/1999/xhtml"><ul>{body}</ul></div>'}


def _item_text(item: HandoverItem) -> str:
    value = f"{item.value:g}".replace(".", ",") if isinstance(item.value, float) else str(item.value)
    unit = f" {item.unit}" if item.unit else ""
    when = (
        f" ({item.clinical_date.day}. {item.clinical_date.month}. {item.clinical_date.year})"
        if item.clinical_date
        else ""
    )
    return f"{item.label + ': ' if item.label else ''}{value}{unit}{when}"


def _review_extension(review: SectionReview) -> Resource:
    parts: list[Resource] = [{"url": "state", "valueCode": review.state.value}]
    if review.by is not None:
        parts.append({"url": "by", "valueReference": practitioner_reference(review.by)})
        parts.append({"url": "role", "valueCode": review.by.role.value})
    if review.at is not None:
        parts.append({"url": "at", "valueDateTime": review.at.isoformat(timespec="seconds")})
    parts.append({"url": "edited", "valueBoolean": review.edited})
    if review.value_hash:
        parts.append({"url": "value-hash", "valueString": review.value_hash})
    return {"url": EXT_HANDOVER_REVIEW, "extension": parts}


# ---------------------------------------------------------------- derived resources


def _evidence_entities(item: HandoverItem, ctx: FhirContext) -> list[Resource]:
    entities: list[Resource] = []
    for ev in item.evidence:
        reference = ctx.documents.get(ev.doc_id)
        what: Resource = (
            {"reference": reference, "display": ev.doc_id}
            if reference
            else {"identifier": {"system": SID_SOURCE_DOCUMENT, "value": ev.doc_id}, "display": ev.doc_id}
        )
        quote: list[Resource] = [{"url": "quote", "valueString": ev.quote}]
        if ev.char_start is not None and ev.char_end is not None:
            quote += [
                {"url": "charStart", "valueInteger": ev.char_start},
                {"url": "charEnd", "valueInteger": ev.char_end},
            ]
        entities.append(
            {"role": "source", "what": what, "extension": [{"url": EXT_EVIDENCE_QUOTE, "extension": quote}]}
        )
    return entities


def _base(kind: str, identifier: str, ctx: FhirContext) -> Resource:
    return {
        "resourceType": kind,
        "identifier": [{"system": SID_HANDOVER_ENTRY, "value": identifier}],
        "subject": {"reference": ctx.patient},
    }


def _effective(item: HandoverItem) -> Resource:
    return {"effectiveDateTime": item.clinical_date.isoformat()} if item.clinical_date else {}


def _derived(key: str, field: HandoverFieldBase, prefix: str, ctx: FhirContext) -> list[tuple[Resource, HandoverItem]]:
    """(resource, item) pairs for the fields that map to clinical resources; items carry the evidence."""
    out: list[tuple[Resource, HandoverItem]] = []
    value: Any = getattr(field, "value", None)
    if field.status == HandoverStatus.MISSING or value is None:
        return out
    if key == "3_diagnosis" and field.items:
        coding = [{"system": ICD10, "code": value.icd10}] if value.icd10 else []
        condition = _base("Condition", f"{prefix}#{key}", ctx) | {
            "category": [{"coding": [{"system": CONDITION_CATEGORY, "code": "encounter-diagnosis"}]}],
            "verificationStatus": {
                "coding": [
                    {
                        "system": CONDITION_VERIFICATION,
                        "code": "confirmed" if value.verified_histologically_on else "provisional",
                    }
                ]
            },
            "code": {**({"coding": coding} if coding else {}), "text": value.text},
        }
        if value.icdo3_morphology:
            condition["extension"] = [
                {
                    "url": MCODE_MORPHOLOGY,
                    "valueCodeableConcept": {"coding": [{"system": ICDO3, "code": value.icdo3_morphology}]},
                }
            ]
        merged = HandoverItem(value=value.text, evidence=[e for i in field.items for e in i.evidence])
        out.append((condition, merged))
    elif key == "6_comorbidities":
        for i, (row, item) in enumerate(zip(value, field.items, strict=False)):
            coding = [{"system": ICD10, "code": row.icd10}] if row.icd10 else []
            out.append(
                (
                    _base("Condition", f"{prefix}#{key}.{i}", ctx)
                    | {
                        "category": [{"coding": [{"system": CONDITION_CATEGORY, "code": "problem-list-item"}]}],
                        "code": {**({"coding": coding} if coding else {}), "text": row.text},
                    }
                    | ({"note": [{"text": row.detail}]} if row.detail else {}),
                    item,
                )
            )
    elif key == "7_medications":
        for i, (row, item) in enumerate(zip(value, field.items, strict=False)):
            dosage = " ".join(p for p in (row.dose, row.schedule) if p)
            statement = _base("MedicationStatement", f"{prefix}#{key}.{i}", ctx) | {
                "status": "active",
                "medicationCodeableConcept": {"text": row.drug},
                "dateAsserted": ctx.recorded.isoformat(timespec="seconds"),
            }
            if dosage:
                statement["dosage"] = [{"text": dosage}]
            out.append((statement, item))
    elif key in ("10_weight_height", "13_labs", "14_histology"):
        flags = [row.flag for row in value] if key == "13_labs" else []
        for i, item in enumerate(field.items):
            out.append(
                (_observation(key, f"{prefix}#{key}.{i}", item, flags[i] if i < len(flags) else None, ctx), item)
            )
    return out


def _observation(key: str, identifier: str, item: HandoverItem, flag: str | None, ctx: FhirContext) -> Resource:
    numeric = isinstance(item.value, float | int) and not isinstance(item.value, bool)
    loinc = VITAL_LOINC.get(item.label or "") if numeric else None
    # R4 vital-signs profile: a coded numeric value with effective[x]; anything else is a plain exam observation.
    if key == "10_weight_height":
        category = "vital-signs" if loinc is not None and item.clinical_date else "exam"
        if category == "exam":
            loinc = None
    else:
        category = "laboratory"
    observation = (
        _base("Observation", identifier, ctx)
        | {
            "status": "final",
            "category": [{"coding": [{"system": OBSERVATION_CATEGORY, "code": category}]}],
            # R4 strings must not be empty: an unlabelled value is named by its section.
            "code": {"text": item.label or SECTION_TITLES[key]},
        }
        | _effective(item)
    )
    if loinc is not None:
        code, display, unit = loinc
        observation["code"] = {"coding": [{"system": LOINC, "code": code, "display": display}], "text": item.label}
        observation["valueQuantity"] = {"value": item.value, "unit": unit, "system": UCUM, "code": unit}
    elif numeric:
        observation["valueQuantity"] = {"value": item.value, **({"unit": item.unit} if item.unit else {})}
    else:
        observation["valueString"] = str(item.value)
    if flag in ("H", "L"):
        observation["interpretation"] = [{"coding": [{"system": INTERPRETATION, "code": flag}]}]
    return observation


def _provenance(target: str, entities: list[Resource], ctx: FhirContext, activity: str) -> Resource:
    provenance: Resource = {
        "resourceType": "Provenance",
        "target": [{"reference": target}],
        "recorded": ctx.recorded.isoformat(timespec="seconds"),
        "activity": {"coding": [{"system": CS_PROVENANCE_ACTIVITY, "code": activity}]},
        "agent": [
            {
                "type": {"coding": [{"system": PROVENANCE_AGENT_TYPE, "code": "assembler"}]},
                "who": _device() | {"display": ctx.device_display},
            }
        ],
    }
    if entities:
        provenance["entity"] = entities
    return provenance


# ---------------------------------------------------------------- write


def handover_bundle(handover: Handover, ctx: FhirContext) -> Resource:
    """Transaction Bundle: Composition first (conditional create), derived resources, Provenance."""
    business_id = handover_business_id(handover.case_id, handover.as_of)
    entries: list[Resource] = []
    sections: list[Resource] = []
    for key, title, field in _fields(handover):
        refs: list[Resource] = []
        for resource, item in _derived(key, field, business_id, ctx):
            identifier = resource["identifier"][0]["value"]
            urn = _urn(identifier)
            entries.append(
                {
                    "fullUrl": urn,
                    "resource": resource,
                    "request": {
                        "method": "POST",
                        "url": resource["resourceType"],
                        "ifNoneExist": _identifier_query(SID_HANDOVER_ENTRY, identifier),
                    },
                }
            )
            entries.append(
                {
                    "resource": _provenance(urn, _evidence_entities(item, ctx), ctx, "extract"),
                    "request": {"method": "POST", "url": "Provenance"},
                }
            )
            refs.append({"reference": urn})
        if key == "12_examinations" and getattr(field, "value", None):
            refs += [{"reference": ctx.documents[r.doc_id]} for r in field.value if r.doc_id in ctx.documents]  # type: ignore[attr-defined]
        if key == "1_patient" and field.status != HandoverStatus.MISSING:
            refs.append({"reference": ctx.patient})
        sections.append(_section(key, title, field, refs, field.review or SectionReview()))
    composition = _composition(handover, business_id, sections, ctx)
    comp_urn = _urn(business_id)
    included = [
        {"role": "source", "what": {"reference": ctx.documents[d], "display": d}}
        for d in handover.included_documents
        if d in ctx.documents
    ]
    head = [
        {
            "fullUrl": comp_urn,
            "resource": composition,
            "request": {
                "method": "POST",
                "url": "Composition",
                "ifNoneExist": _identifier_query(SID_HANDOVER, business_id),
            },
        },
        {
            "resource": _provenance(comp_urn, included, ctx, "assemble"),
            "request": {"method": "POST", "url": "Provenance"},
        },
    ]
    return {"resourceType": "Bundle", "type": "transaction", "entry": head + entries}


def _section(key: str, title: str, field: HandoverFieldBase, refs: list[Resource], review: SectionReview) -> Resource:
    section: Resource = {
        "title": title,
        "code": {"coding": [{"system": CS_HANDOVER_SECTION, "code": key}]},
        "text": _narrative(field),
        "extension": [
            {
                "url": EXT_HANDOVER_FIELD_STATUS,
                "valueCoding": {"system": CS_HANDOVER_STATUS, "code": field.status.value},
            },
            _review_extension(review),
        ],
    }
    if refs:
        section["entry"] = refs
    elif field.status == HandoverStatus.MISSING:
        section["emptyReason"] = {"coding": [{"system": LIST_EMPTY_REASON, "code": "unavailable"}]}
    return section


def _composition(handover: Handover, business_id: str, sections: list[Resource], ctx: FhirContext) -> Resource:
    date = handover.generated_at or ctx.recorded
    return {
        "resourceType": "Composition",
        "identifier": {"system": SID_HANDOVER, "value": business_id},
        "status": "preliminary",
        "type": {"coding": [{"system": CS_COMPOSITION_TYPE, "code": "handover", "display": TITLE}]},
        "subject": {"reference": ctx.patient},
        "date": date.isoformat(timespec="seconds"),
        "author": [_device() | {"display": ctx.device_display}],
        "title": TITLE,
        "extension": [
            {"url": EXT_HANDOVER_EPISODE, "valueReference": {"reference": ctx.episode}},
            {"url": EXT_HANDOVER_AS_OF, "valueDateTime": handover.as_of.isoformat(timespec="seconds")},
        ],
        "section": sections,
    }


# ---------------------------------------------------------------- review: read back and update


def stored_review(resource: Resource) -> StoredReview:
    if resource.get("resourceType") != "Composition":
        raise ValueError("expected a Composition")
    sections: dict[str, SectionReview] = {}
    edited: dict[str, JsonValue] = {}
    for section in resource.get("section", []):
        key = next(
            (c["code"] for c in section.get("code", {}).get("coding", []) if c.get("system") == CS_HANDOVER_SECTION),
            None,
        )
        if key is None:
            continue
        for ext in section.get("extension", []):
            if ext.get("url") == EXT_HANDOVER_REVIEW:
                sections[key] = _review_from_extension(ext)
            elif ext.get("url") == EXT_HANDOVER_EDITED_VALUE:
                edited[key] = json.loads(ext["valueString"])
    return StoredReview(
        fhir_id=str(resource["id"]),
        business_id=str(resource["identifier"]["value"]),
        status="final" if resource.get("status") == "final" else "preliminary",
        sections=sections,
        edited_values=edited,
    )


def _review_from_extension(ext: Resource) -> SectionReview:
    parts = {p["url"]: p for p in ext.get("extension", [])}
    by = None
    if "by" in parts:
        ref = parts["by"]["valueReference"]
        role = Role(parts["role"]["valueCode"]) if "role" in parts else Role.KOC_PHYSICIAN
        by = PartyRef(id=ref["identifier"]["value"], display=ref.get("display", ""), role=role)
    at = datetime.fromisoformat(parts["at"]["valueDateTime"]) if "at" in parts else None
    return SectionReview(
        state=ReviewState(parts["state"]["valueCode"]) if "state" in parts else ReviewState.DRAFT,
        by=by,
        at=at,
        edited=bool(parts.get("edited", {}).get("valueBoolean", False)),
        value_hash=parts.get("value-hash", {}).get("valueString"),
    )


def with_section_review(
    resource: Resource, key: str, review: SectionReview, edited_value: JsonValue | None
) -> Resource:
    """Copy of the Composition with the section's review (and edited value) replaced; final when all are done."""
    updated: Resource = copy.deepcopy(resource)
    for section in updated.get("section", []):
        codes = [
            c.get("code") for c in section.get("code", {}).get("coding", []) if c.get("system") == CS_HANDOVER_SECTION
        ]
        if key not in codes:
            continue
        kept = [
            e
            for e in section.get("extension", [])
            if e.get("url") not in (EXT_HANDOVER_REVIEW, EXT_HANDOVER_EDITED_VALUE)
        ]
        kept.append(_review_extension(review))
        if edited_value is not None:
            kept.append({"url": EXT_HANDOVER_EDITED_VALUE, "valueString": json.dumps(edited_value, ensure_ascii=False)})
        section["extension"] = kept
        break
    else:
        raise ValueError(f"Composition has no section {key}")
    reviews = stored_review(updated).sections
    if all(reviews.get(k, SectionReview()).state in REVIEW_DONE for k in section_keys()) and review.by and review.at:
        updated["status"] = "final"
        updated["attester"] = [
            {
                "mode": "professional",
                "time": review.at.isoformat(timespec="seconds"),
                "party": practitioner_reference(review.by),
            }
        ]
    return updated


def confirmation_provenance(
    composition_ref: str, key: str, review: SectionReview, previous_hash: str, *, edited: bool
) -> Resource:
    """Provenance of a physician's confirmation/edit of one section (who, when, what changed)."""
    if review.by is None or review.at is None:
        raise ValueError("a confirmation needs the confirming physician and the time")
    activity = "edit" if edited else ("accept-missing" if review.state == ReviewState.ACCEPTED_MISSING else "confirm")
    return {
        "resourceType": "Provenance",
        "target": [{"reference": composition_ref}],
        "recorded": review.at.isoformat(timespec="seconds"),
        "activity": {"coding": [{"system": CS_PROVENANCE_ACTIVITY, "code": activity}]},
        "agent": [
            {
                "type": {"coding": [{"system": PROVENANCE_AGENT_TYPE, "code": "verifier"}]},
                "role": [{"coding": [{"system": CS_WORKFLOW_ROLE, "code": review.by.role.value}]}],
                "who": practitioner_reference(review.by),
            }
        ],
        "extension": [
            {"url": EXT_HANDOVER_SECTION, "valueCode": key},
            {"url": EXT_PREVIOUS_VALUE_HASH, "valueString": previous_hash},
        ],
    }
