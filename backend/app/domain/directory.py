"""Directory of workplaces and people (mCSD-like): organisations, practitioners and their roles."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.domain.common import BUSINESS_ID_PATTERN, DomainModel, Role
from app.domain.patient import Address


class OrganizationKind(StrEnum):
    GP_PRACTICE = "gp_practice"
    KOC = "koc"
    LABORATORY = "laboratory"
    OUTPATIENT = "outpatient"
    IMAGING = "imaging"
    INSURER = "insurer"


class Organization(DomainModel):
    id: str = Field(pattern=BUSINESS_ID_PATTERN, description="Slug, e.g. 'koc2-nemocnice-lipova'.")
    name: str
    kind: OrganizationKind
    address: Address | None = None
    phone: str | None = None
    icp: str | None = Field(None, description="IČP (identifikační číslo pracoviště) if stated in the documents.")
    insurer_code: str | None = Field(None, pattern=r"^\d{3}$")


class Practitioner(DomainModel):
    id: str = Field(pattern=BUSINESS_ID_PATTERN, description="Slug, e.g. 'reznicek-tomas'.")
    given: str
    family: str
    prefix: tuple[str, ...] = Field((), description="Titles before the name, e.g. ('doc.', 'MUDr.').")
    suffix: tuple[str, ...] = Field((), description="Titles after the name, e.g. ('Ph.D.',).")

    @property
    def display_name(self) -> str:
        before = " ".join(self.prefix)
        after = ", ".join(self.suffix)
        name = f"{before} {self.given} {self.family}".strip()
        return f"{name}, {after}" if after else name


class PractitionerRole(DomainModel):
    id: str = Field(pattern=BUSINESS_ID_PATTERN, description="'<practitioner>@<organization>'.")
    practitioner_id: str
    organization_id: str
    role: Role
    specialty: str = Field(description="As written in the documents, e.g. 'gastroenterolog, endoskopista'.")
