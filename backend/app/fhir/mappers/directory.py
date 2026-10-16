"""Organization, Practitioner, PractitionerRole <-> domain (`app.domain.directory`)."""

from __future__ import annotations

from typing import Any

from app.domain.common import PartyRef, Role
from app.domain.directory import Organization, OrganizationKind, Practitioner, PractitionerRole
from app.domain.patient import Address
from app.fhir.client import Resource
from app.fhir.systems import (
    CS_ORGANIZATION_KIND,
    CS_WORKFLOW_ROLE,
    CZ_ICP,
    CZ_INSURER_CODE,
    ORGANIZATION_TYPE,
    SID_ORGANIZATION,
    SID_PRACTITIONER,
    SID_PRACTITIONER_ROLE,
)

# Our organisation kinds -> http://terminology.hl7.org/CodeSystem/organization-type
_HL7_ORGANIZATION_TYPE = {
    OrganizationKind.GP_PRACTICE: "prov",
    OrganizationKind.KOC: "prov",
    OrganizationKind.LABORATORY: "prov",
    OrganizationKind.OUTPATIENT: "prov",
    OrganizationKind.IMAGING: "prov",
    OrganizationKind.INSURER: "pay",
}


def organization_to_fhir(org: Organization) -> Resource:
    identifiers = [{"system": SID_ORGANIZATION, "value": org.id}]
    if org.icp:
        identifiers.append({"system": CZ_ICP, "value": org.icp})
    if org.insurer_code:
        identifiers.append({"system": CZ_INSURER_CODE, "value": org.insurer_code})
    resource: Resource = {
        "resourceType": "Organization",
        "identifier": identifiers,
        "active": True,
        "type": [
            {"coding": [{"system": ORGANIZATION_TYPE, "code": _HL7_ORGANIZATION_TYPE[org.kind]}]},
            {"coding": [{"system": CS_ORGANIZATION_KIND, "code": org.kind.value}]},
        ],
        "name": org.name,
    }
    if org.phone:
        resource["telecom"] = [{"system": "phone", "value": org.phone, "use": "work"}]
    if org.address:
        resource["address"] = [
            {
                "use": "work",
                "text": org.address.text,
                "line": [org.address.line],
                "postalCode": org.address.postal_code,
                "city": org.address.city,
                "country": org.address.country,
            }
        ]
    return resource


def practitioner_to_fhir(practitioner: Practitioner) -> Resource:
    name: dict[str, Any] = {
        "use": "official",
        "text": practitioner.display_name,
        "family": practitioner.family,
        "given": [practitioner.given],
    }
    if practitioner.prefix:
        name["prefix"] = list(practitioner.prefix)
    if practitioner.suffix:
        name["suffix"] = list(practitioner.suffix)
    return {
        "resourceType": "Practitioner",
        "identifier": [{"system": SID_PRACTITIONER, "value": practitioner.id}],
        "active": True,
        "name": [name],
    }


def practitioner_role_to_fhir(
    role: PractitionerRole,
    *,
    practitioner_reference: str,
    practitioner_display: str,
    organization_reference: str,
    organization_display: str,
) -> Resource:
    return {
        "resourceType": "PractitionerRole",
        "identifier": [{"system": SID_PRACTITIONER_ROLE, "value": role.id}],
        "active": True,
        "practitioner": {"reference": practitioner_reference, "display": practitioner_display},
        "organization": {"reference": organization_reference, "display": organization_display},
        "code": [{"coding": [{"system": CS_WORKFLOW_ROLE, "code": role.role.value}]}],
        "specialty": [{"text": role.specialty}],
    }


def party_reference(party: PartyRef, fhir_reference: str) -> Resource:
    """A Reference that carries the business id and display, so readers need no extra lookup."""
    reference: Resource = {
        "reference": fhir_reference,
        "identifier": {"system": SID_PRACTITIONER_ROLE, "value": party.id},
    }
    if party.display:  # FHIR JSON forbids empty strings
        reference["display"] = party.display
    return reference


def role_from_codeable_concepts(concepts: list[dict[str, Any]]) -> Role | None:
    for concept in concepts:
        for coding in concept.get("coding", []):
            if coding.get("system") == CS_WORKFLOW_ROLE:
                return Role(coding["code"])
    return None


def _identifier(resource: Resource, system: str) -> str | None:
    return next((str(i["value"]) for i in resource.get("identifier", []) if i.get("system") == system), None)


def organization_from_fhir(resource: Resource) -> Organization:
    if resource.get("resourceType") != "Organization":
        raise ValueError("expected an Organization resource")
    slug = _identifier(resource, SID_ORGANIZATION)
    if slug is None:
        raise ValueError("Organization has no business identifier")
    kind = next(
        (
            OrganizationKind(c["code"])
            for t in resource.get("type", [])
            for c in t.get("coding", [])
            if c.get("system") == CS_ORGANIZATION_KIND
        ),
        None,
    )
    if kind is None:
        raise ValueError("Organization has no organization-kind")
    addresses = resource.get("address") or []
    phone = next((str(t["value"]) for t in resource.get("telecom", []) if t.get("system") == "phone"), None)
    return Organization(
        id=slug,
        name=str(resource.get("name", "")),
        kind=kind,
        address=_address(addresses[0]) if addresses else None,
        phone=phone,
        icp=_identifier(resource, CZ_ICP),
        insurer_code=_identifier(resource, CZ_INSURER_CODE),
    )


def _address(address: dict[str, Any]) -> Address:
    return Address(
        line=", ".join(address.get("line", [])),
        postal_code=address.get("postalCode", ""),
        city=address.get("city", ""),
        country=address.get("country", "CZ"),
    )


def practitioner_role_from_fhir(resource: Resource) -> tuple[PractitionerRole, str]:
    """The domain role plus the practitioner's display name (titles included) as written on the resource."""
    if resource.get("resourceType") != "PractitionerRole":
        raise ValueError("expected a PractitionerRole resource")
    role_id = _identifier(resource, SID_PRACTITIONER_ROLE)
    if role_id is None:
        raise ValueError("PractitionerRole has no business identifier")
    practitioner_id, _, organization_id = role_id.partition("@")
    role = role_from_codeable_concepts(resource.get("code", []))
    if role is None:
        raise ValueError("PractitionerRole has no workflow-role")
    specialty = next((str(s["text"]) for s in resource.get("specialty", []) if s.get("text")), "")
    return (
        PractitionerRole(
            id=role_id,
            practitioner_id=practitioner_id,
            organization_id=organization_id,
            role=role,
            specialty=specialty,
        ),
        str(resource.get("practitioner", {}).get("display", "")),
    )
