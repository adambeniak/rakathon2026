"""Patient, RelatedPerson and Coverage <-> domain (`app.domain.patient`)."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.domain.patient import Address, ContactPerson, Patient, Sex
from app.fhir.client import Resource
from app.fhir.systems import (
    COVERAGE_TYPE,
    CZ_INSURER_CODE,
    CZ_RODNE_CISLO,
    SID_COVERAGE,
    SID_RELATED_PERSON,
    V3_ROLE_CODE,
)

# Czech relation words as written in documents -> v3-RoleCode.
RELATION_CODES = {"dcera": "DAU", "syn": "SON", "manžel": "HUSB", "manželka": "WIFE", "matka": "MTH", "otec": "FTH"}


def rc_value(birth_number: str) -> str:
    """Identifier value for rodné číslo: digits only ('635722/1013' -> '6357221013')."""
    return birth_number.replace("/", "")


def format_rc(value: str) -> str:
    return f"{value[:6]}/{value[6:]}" if len(value) in (9, 10) and "/" not in value else value


def patient_to_fhir(patient: Patient, *, general_practitioner: str | None = None) -> Resource:
    resource: Resource = {
        "resourceType": "Patient",
        "identifier": [{"use": "official", "system": CZ_RODNE_CISLO, "value": rc_value(patient.birth_number)}],
        "name": [{"use": "official", "family": patient.family, "given": [patient.given]}],
        "gender": patient.sex.value,
        "birthDate": patient.birth_date.isoformat(),
    }
    telecom = []
    if patient.phone:
        telecom.append({"system": "phone", "value": patient.phone, "use": "mobile"})
    if patient.email:
        telecom.append({"system": "email", "value": patient.email})
    if telecom:
        resource["telecom"] = telecom
    if patient.address:
        resource["address"] = [_address_to_fhir(patient.address)]
    if general_practitioner:
        resource["generalPractitioner"] = [{"reference": general_practitioner}]
    return resource


def patient_from_fhir(resource: Resource, *, insurer_code: str | None = None) -> Patient:
    if resource.get("resourceType") != "Patient":
        raise ValueError("expected a Patient resource")
    name = (resource.get("name") or [{}])[0]
    rc = next((i["value"] for i in resource.get("identifier", []) if i.get("system") == CZ_RODNE_CISLO), None)
    if rc is None:
        raise ValueError("Patient has no rodné číslo identifier")
    telecom = resource.get("telecom", [])
    addresses = resource.get("address") or []
    return Patient(
        given=" ".join(name.get("given", [])),
        family=name.get("family", ""),
        sex=Sex(resource.get("gender", "unknown")),
        birth_date=date.fromisoformat(resource["birthDate"]),
        birth_number=format_rc(str(rc)),
        insurer_code=insurer_code,
        phone=_telecom(telecom, "phone"),
        email=_telecom(telecom, "email"),
        address=_address_from_fhir(addresses[0]) if addresses else None,
    )


def related_person_to_fhir(contact: ContactPerson, *, patient_reference: str, patient: Patient) -> Resource:
    # FHIR JSON forbids empty arrays: optional lists are left out instead.
    given, _, family = contact.name.partition(" ")
    relationship: dict[str, Any] = {"text": contact.relation}
    if code := RELATION_CODES.get(contact.relation):
        relationship["coding"] = [{"system": V3_ROLE_CODE, "code": code}]
    name: dict[str, Any] = {"family": family} if family else {"text": given}
    if family:
        name["given"] = [given]
    resource: Resource = {
        "resourceType": "RelatedPerson",
        "identifier": [{"system": SID_RELATED_PERSON, "value": f"{rc_value(patient.birth_number)}-{contact.relation}"}],
        "active": True,
        "patient": {"reference": patient_reference},
        "relationship": [relationship],
        "name": [name],
    }
    if contact.phone:
        resource["telecom"] = [{"system": "phone", "value": contact.phone}]
    return resource


def coverage_to_fhir(
    *, patient: Patient, patient_reference: str, payor_reference: str, payor_display: str | None = None
) -> Resource:
    if not patient.insurer_code:
        raise ValueError("Coverage needs the patient's insurer code")
    payor: dict[str, Any] = {
        "reference": payor_reference,
        "identifier": {"system": CZ_INSURER_CODE, "value": patient.insurer_code},
    }
    if payor_display:
        payor["display"] = payor_display
    return {
        "resourceType": "Coverage",
        "identifier": [{"system": SID_COVERAGE, "value": f"{patient.insurer_code}-{rc_value(patient.birth_number)}"}],
        "status": "active",
        "type": {"coding": [{"system": COVERAGE_TYPE, "code": "PUBLICPOL", "display": "public healthcare"}]},
        "beneficiary": {"reference": patient_reference},
        "payor": [payor],
    }


def insurer_code_from_coverage(coverage: Resource) -> str | None:
    for payor in coverage.get("payor", []):
        identifier = payor.get("identifier") or {}
        if identifier.get("system") == CZ_INSURER_CODE and identifier.get("value"):
            return str(identifier["value"])
    return None


def _address_to_fhir(address: Address) -> dict[str, Any]:
    return {
        "use": "home",
        "text": address.text,
        "line": [address.line],
        "postalCode": address.postal_code,
        "city": address.city,
        "country": address.country,
    }


def _address_from_fhir(address: dict[str, Any]) -> Address:
    return Address(
        line=", ".join(address.get("line", [])),
        postal_code=address.get("postalCode", ""),
        city=address.get("city", ""),
        country=address.get("country", "CZ"),
    )


def _telecom(telecom: list[dict[str, Any]], system: str) -> str | None:
    return next((str(t["value"]) for t in telecom if t.get("system") == system and t.get("value")), None)
