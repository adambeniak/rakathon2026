"""Read side of the directory (mCSD-like): Organizations, PractitionerRoles. The directory is small, so it is loaded
whole (two searches) and queried in memory; it holds no clinical content, so reads are not audited."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog

from app.domain.common import PartyRef, Role
from app.domain.directory import Organization, OrganizationKind, PractitionerRole, koc_short_name
from app.fhir.client import FhirClient
from app.fhir.mappers.directory import organization_from_fhir, practitioner_role_from_fhir

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class OrgEntry:
    org: Organization
    ref: str  # 'Organization/12'


@dataclass(frozen=True)
class RoleEntry:
    role: PractitionerRole
    display: str
    ref: str  # 'PractitionerRole/7'

    def party(self, display: str | None = None) -> PartyRef:
        return PartyRef(id=self.role.id, display=display or self.display, role=self.role.role)


@dataclass(frozen=True)
class Directory:
    orgs: tuple[OrgEntry, ...]
    roles: tuple[RoleEntry, ...]

    def org(self, org_id: str) -> OrgEntry | None:
        return next((o for o in self.orgs if o.org.id == org_id), None)

    def role(self, role_id: str) -> RoleEntry | None:
        return next((r for r in self.roles if r.role.id == role_id), None)

    def kocs(self) -> list[OrgEntry]:
        return sorted((o for o in self.orgs if o.org.kind is OrganizationKind.KOC), key=lambda o: o.org.id)

    def roles_at(self, org_id: str, role: Role) -> list[RoleEntry]:
        return sorted(
            (r for r in self.roles if r.role.organization_id == org_id and r.role.role is role), key=lambda r: r.role.id
        )

    def insurer(self, code: str) -> OrgEntry | None:
        return next(
            (o for o in self.orgs if o.org.kind is OrganizationKind.INSURER and o.org.insurer_code == code), None
        )

    def role_holder(self, org_id: str, role: Role) -> PartyRef | None:
        """The KOC's default holder of a role with a role-level display ('Koordinátor KOC 2'), until a person acts."""
        entry = next(iter(self.roles_at(org_id, role)), None)
        org = self.org(org_id)
        label = _ROLE_LABELS.get(role)
        if entry is None or org is None or label is None:
            return None
        return entry.party(f"{label} {koc_short_name(org.org)}")


_ROLE_LABELS = {Role.COORDINATOR: "Koordinátor", Role.KOC_PHYSICIAN: "Lékař"}


class DirectoryReader:
    def __init__(self, client: FhirClient) -> None:
        self._client = client

    async def load(self) -> Directory:
        organizations, roles = await asyncio.gather(
            self._client.search_all("Organization", {"_count": "100"}),
            self._client.search_all("PractitionerRole", {"_count": "100"}),
        )
        org_entries: list[OrgEntry] = []
        for organization in organizations:
            try:
                org_entries.append(OrgEntry(organization_from_fhir(organization), f"Organization/{organization['id']}"))
            except ValueError:  # not one of ours (no business id / kind): not part of the directory
                log.info("directory_skip", resource_type="Organization", id=organization.get("id"))
        role_entries: list[RoleEntry] = []
        for resource in roles:
            try:
                role, display = practitioner_role_from_fhir(resource)
            except ValueError:
                log.info("directory_skip", resource_type="PractitionerRole", id=resource.get("id"))
                continue
            role_entries.append(RoleEntry(role, display, f"PractitionerRole/{resource['id']}"))
        return Directory(tuple(org_entries), tuple(role_entries))


class DirectoryProvider:
    """Per-request memo: the actor lookup and the endpoint share one directory load."""

    def __init__(self, client: FhirClient) -> None:
        self._reader = DirectoryReader(client)
        self._directory: Directory | None = None

    async def get(self) -> Directory:
        if self._directory is None:
            self._directory = await self._reader.load()
        return self._directory
