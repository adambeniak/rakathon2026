"""The seeded demo directory as a `Directory`, built through the real mappers (round-trip) with fake logical ids."""

from __future__ import annotations

from app.fhir.directory import Directory, OrgEntry, RoleEntry
from app.fhir.mappers.directory import (
    organization_from_fhir,
    organization_to_fhir,
    practitioner_role_from_fhir,
    practitioner_role_to_fhir,
)
from app.seed import demo_case


def demo_directory() -> Directory:
    orgs: list[OrgEntry] = []
    org_refs: dict[str, str] = {}
    for index, org in enumerate(demo_case.ORGANIZATIONS, start=1):
        resource = {**organization_to_fhir(org), "id": str(index)}
        org_refs[org.id] = f"Organization/{index}"
        orgs.append(OrgEntry(organization_from_fhir(resource), f"Organization/{index}"))
    names = {org.id: org.name for org in demo_case.ORGANIZATIONS}
    roles: list[RoleEntry] = []
    for index, person in enumerate(demo_case.PEOPLE, start=1):
        resource = {
            **practitioner_role_to_fhir(
                person.role,
                practitioner_reference=f"Practitioner/{index}",
                practitioner_display=person.practitioner.display_name,
                organization_reference=org_refs[person.role.organization_id],
                organization_display=names[person.role.organization_id],
            ),
            "id": str(index),
        }
        role, display = practitioner_role_from_fhir(resource)
        roles.append(RoleEntry(role, display, f"PractitionerRole/{index}"))
    return Directory(tuple(orgs), tuple(roles))
