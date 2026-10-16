"""Fact model: strict JSON schema for the LLM + Pydantic models for parsing and the accepted fact."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FactType = Literal[
    "patient_identity",
    "contact",
    "insurer",
    "diagnosis",
    "comorbidity",
    "medication",
    "allergy",
    "performance_status",
    "vital_sign",
    "symptom",
    "examination",
    "lab_result",
    "histology",
    "procedure",
    "consent_or_wish",
    "recommendation_or_plan",
    "referral_request",
    "admin_date",
]
FACT_TYPES: tuple[str, ...] = FactType.__args__  # type: ignore[attr-defined]
Certainty = Literal["stated", "suspected", "negated", "planned"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TextValue(_Strict):
    kind: Literal["text"]
    text: str


class CodedValue(_Strict):
    kind: Literal["coded"]
    code: str | None
    system: Literal["MKN-10", "MKN-O", "other"] | None
    text: str


class QuantityValue(_Strict):
    kind: Literal["quantity"]
    name: str
    number: float | None
    text_value: str | None
    comparator: Literal["<", ">", "<=", ">="] | None
    flag: Literal["H", "L"] | None
    ref_range: str | None


class MedicationValue(_Strict):
    kind: Literal["medication"]
    drug: str
    dose: str | None
    schedule: str | None


class PersonValue(_Strict):
    kind: Literal["person"]
    name: str | None
    relation: str | None
    phone: str | None
    email: str | None
    address: str | None


class DateValue(_Strict):
    kind: Literal["date"]
    label: str
    date: str


FactValue = Annotated[
    TextValue | CodedValue | QuantityValue | MedicationValue | PersonValue | DateValue,
    Field(discriminator="kind"),
]


class RawFact(_Strict):
    """One fact exactly as the LLM returned it."""

    type: FactType
    handover_field: int = Field(ge=1, le=15)
    value: FactValue
    unit: str | None
    clinical_date: str | None
    certainty: Certainty
    quote: str


class Fact(_Strict):
    """A fact that passed the evidence lock. `quote` is always the exact source substring."""

    fact_id: str
    doc_id: str
    type: FactType
    handover_field: int
    value: FactValue
    unit: str | None
    clinical_date: str | None
    certainty: Certainty
    quote: str
    span: tuple[int, int]
    repaired: bool = False


def make_fact_id(doc_id: str, raw: RawFact) -> str:
    """Includes the canonical value: five drugs quoting one FA line stay five facts."""
    payload = json.dumps(
        [doc_id, raw.type, raw.quote, raw.value.model_dump(), raw.unit, raw.clinical_date],
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- type rules

ALLOWED_KINDS: dict[str, frozenset[str]] = {
    "patient_identity": frozenset({"text", "person", "date", "coded"}),
    "contact": frozenset({"person", "text"}),
    "insurer": frozenset({"coded", "text"}),
    "diagnosis": frozenset({"coded", "text"}),
    "comorbidity": frozenset({"coded", "text"}),
    "medication": frozenset({"medication"}),
    "allergy": frozenset({"text", "coded"}),
    "performance_status": frozenset({"quantity", "text"}),
    "vital_sign": frozenset({"quantity"}),
    "symptom": frozenset({"text", "quantity"}),
    "examination": frozenset({"text", "quantity", "coded"}),
    "lab_result": frozenset({"quantity"}),
    "histology": frozenset({"text", "coded", "quantity"}),
    "procedure": frozenset({"text"}),
    "consent_or_wish": frozenset({"text"}),
    "recommendation_or_plan": frozenset({"text", "date", "medication"}),
    "referral_request": frozenset({"text", "coded"}),
    "admin_date": frozenset({"date"}),
}

_ALL_FIELDS = frozenset(range(1, 16))
ALLOWED_FIELDS: dict[str, frozenset[int]] = {
    "patient_identity": frozenset({1}),
    "contact": frozenset({2}),
    "insurer": frozenset({1}),
    "diagnosis": frozenset({3, 6}),
    "comorbidity": frozenset({6}),
    "medication": frozenset({7}),
    "allergy": frozenset({8}),
    "performance_status": frozenset({9}),
    "vital_sign": frozenset({10, 11, 12}),
    "symptom": frozenset({11, 4}),
    "examination": frozenset({12, 6, 10, 14}),
    "lab_result": frozenset({13, 12}),
    "histology": frozenset({14, 3, 12}),
    "procedure": frozenset({12, 15}),
    "consent_or_wish": frozenset({15}),
    "recommendation_or_plan": frozenset({15, 5, 12, 7}),
    "referral_request": frozenset({5, 15, 3}),
    "admin_date": _ALL_FIELDS,
}

HANDOVER_FIELDS: dict[int, str] = {
    1: "Nacionále pacienta (jméno, příjmení, věk, pohlaví, číslo ZP)",
    2: "Kontakty (pacient, kontaktní osoba + tel.)",
    3: "Diagnóza",
    4: "Epikríza",
    5: "Požadavek/otázka na MDT",
    6: "Komorbidity (OA)",
    7: "Léková anamnéza (FA)",
    8: "Alergie (AA)",
    9: "Stav výkonnosti (PS/Karnofsky)",
    10: "Váha a výška",
    11: "Symptomy a jejich počátek",
    12: "Provedená vyšetření (datum, místo, typ, výsledek)",
    13: "Laboratorní výsledky vč. onkomarkerů",
    14: "Histologie",
    15: "Jiná důležitá sdělení vč. přání pacienta",
}


# ---------------------------------------------------------------- JSON schema for the LLM (strict mode)


def _nullable(t: str, **extra: Any) -> dict[str, Any]:
    return {"type": [t, "null"], **extra}


def _obj(kind: str, props: dict[str, Any]) -> dict[str, Any]:
    full = {"kind": {"type": "string", "enum": [kind]}, **props}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": full,
        "required": list(full),
    }


VALUE_SCHEMAS: list[dict[str, Any]] = [
    _obj("text", {"text": {"type": "string"}}),
    _obj(
        "coded",
        {
            "code": _nullable("string"),
            "system": {"type": ["string", "null"], "enum": ["MKN-10", "MKN-O", "other", None]},
            "text": {"type": "string"},
        },
    ),
    _obj(
        "quantity",
        {
            "name": {"type": "string"},
            "number": _nullable("number"),
            "text_value": _nullable("string"),
            "comparator": {"type": ["string", "null"], "enum": ["<", ">", "<=", ">=", None]},
            "flag": {"type": ["string", "null"], "enum": ["H", "L", None]},
            "ref_range": _nullable("string"),
        },
    ),
    _obj(
        "medication",
        {"drug": {"type": "string"}, "dose": _nullable("string"), "schedule": _nullable("string")},
    ),
    _obj(
        "person",
        {
            "name": _nullable("string"),
            "relation": _nullable("string"),
            "phone": _nullable("string"),
            "email": _nullable("string"),
            "address": _nullable("string"),
        },
    ),
    _obj("date", {"label": {"type": "string"}, "date": {"type": "string"}}),
]

_FACT_PROPS: dict[str, Any] = {
    "type": {"type": "string", "enum": list(FACT_TYPES)},
    "handover_field": {"type": "integer"},
    "value": {"anyOf": VALUE_SCHEMAS},
    "unit": _nullable("string"),
    "clinical_date": _nullable("string"),
    "certainty": {"type": "string", "enum": ["stated", "suspected", "negated", "planned"]},
    "quote": {"type": "string"},
}

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": _FACT_PROPS,
                "required": list(_FACT_PROPS),
            },
        }
    },
    "required": ["facts"],
}


def schema_json() -> str:
    """Canonical serialisation; part of the LLM cache key."""
    return json.dumps(RESPONSE_SCHEMA, sort_keys=True, ensure_ascii=False)
