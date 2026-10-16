"""Physician review of handover sections (human in the loop): pure helpers used by the API and the FHIR store."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal, cast

from pydantic import JsonValue, TypeAdapter, ValidationError

from app.domain.errors import InvalidInputError
from app.domain.handover import (
    Handover,
    HandoverFieldBase,
    HandoverFields,
    HandoverItem,
    HandoverStatus,
    ReviewState,
    SectionReview,
)

_NAMES = list(HandoverFields.model_fields)


def section_key(number: int) -> str:
    """1..15 -> the field key shared with data/golden, e.g. 9 -> '9_performance_status'."""
    if not 1 <= number <= len(_NAMES):
        raise InvalidInputError(f"section must be 1..{len(_NAMES)}")
    info = HandoverFields.model_fields[_NAMES[number - 1]]
    return info.alias or _NAMES[number - 1]


def _name(key: str) -> str:
    for name, info in HandoverFields.model_fields.items():
        if (info.alias or name) == key:
            return name
    raise InvalidInputError(f"unknown section {key}")


def field_of(handover: Handover, key: str) -> HandoverFieldBase:
    field: HandoverFieldBase = getattr(handover.fields, _name(key))
    return field


def _value_adapter(key: str) -> TypeAdapter[Any]:
    """TypeAdapter of the section's typed `value` (e.g. `PerformanceStatus | None`)."""
    field_cls = cast(type[HandoverFieldBase], HandoverFields.model_fields[_name(key)].annotation)
    return TypeAdapter(cast(Any, field_cls.model_fields["value"].annotation))


def validate_edited_value(key: str, raw: JsonValue) -> JsonValue:
    """The physician's value must fit the field's typed value model (contracts/handover.schema.json)."""
    adapter = _value_adapter(key)
    try:
        value = adapter.validate_python(raw)
    except ValidationError as exc:
        # Locations only: never echo the submitted value (it may contain PHI).
        where = ", ".join(".".join(str(p) for p in e["loc"]) or "value" for e in exc.errors()[:3])
        raise InvalidInputError(f"edited_value does not fit section {key} ({where})") from exc
    if value is None:
        raise InvalidInputError("edited_value must not be null")
    dumped: JsonValue = adapter.dump_python(value, mode="json")
    return dumped


def value_hash(field: HandoverFieldBase) -> str:
    """SHA-256 of the section's value before the confirmation (Provenance: what changed)."""
    data = field.model_dump(mode="json", include={"value"}).get("value")
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


EDITED_LABEL = "Upraveno lékařem"


def _display(raw: JsonValue) -> str:
    return raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)


def overlay_review(
    handover: Handover,
    *,
    composition_id: str,
    status: Literal["preliminary", "final"],
    sections: Mapping[str, SectionReview],
    edited_values: Mapping[str, JsonValue],
) -> Handover:
    """The assembled handover with the stored review state; an edited value replaces the assembled one."""
    updates: dict[str, HandoverFieldBase] = {}
    for name, info in HandoverFields.model_fields.items():
        key = info.alias or name
        field: HandoverFieldBase = getattr(handover.fields, name)
        review = sections.get(key, SectionReview())
        change: dict[str, Any] = {"review": review}
        if review.state != ReviewState.DRAFT and review.value_hash and review.value_hash != field.value_hash:
            # The documents changed the section after it was confirmed: the confirmation no longer covers it.
            change["review"] = SectionReview()
            reopened = "Obsah oddílu se po potvrzení změnil (nové dokumenty); je třeba jej potvrdit znovu."
            change["note"] = f"{field.note} {reopened}" if field.note else reopened
        if key in edited_values:
            # The physician's value replaces the assembled one. Its items no longer carry document evidence (the
            # section-level evidence still lists what was consulted); a previously missing section is now filled.
            raw = edited_values[key]
            change["value"] = _value_adapter(key).validate_python(raw)
            change["items"] = [HandoverItem(label=EDITED_LABEL, value=_display(raw))]
            if field.status == HandoverStatus.MISSING:
                change |= {"status": HandoverStatus.COMPLETE, "missing": [], "missing_items": []}
        updates[name] = field.model_copy(update=change)
    return handover.model_copy(
        update={
            "fields": handover.fields.model_copy(update=updates),
            "composition_id": composition_id,
            "status": status,
        }
    )
