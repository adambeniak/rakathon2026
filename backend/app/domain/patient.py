"""Patient identity as registered in the case (not extracted facts; those live in the handover)."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field

from app.domain.common import DomainModel


class Sex(StrEnum):
    FEMALE = "female"
    MALE = "male"
    OTHER = "other"
    UNKNOWN = "unknown"


class Address(DomainModel):
    line: str
    postal_code: str
    city: str
    country: str = "CZ"

    @property
    def text(self) -> str:
        return f"{self.line}, {self.postal_code} {self.city}"


class ContactPerson(DomainModel):
    name: str
    relation: str = Field(description="As written in the source, e.g. 'dcera'.")
    phone: str | None = None


class Patient(DomainModel):
    given: str
    family: str
    sex: Sex
    birth_date: date
    birth_number: str = Field(pattern=r"^\d{6}/?\d{3,4}$", description="Rodné číslo as written, e.g. '635722/1013'.")
    insurer_code: str | None = Field(None, pattern=r"^\d{3}$", description="Kód zdravotní pojišťovny, e.g. '211'.")
    phone: str | None = None
    email: str | None = None
    address: Address | None = None

    @property
    def display_name(self) -> str:
        return f"{self.given} {self.family}"

    def age_on(self, day: date) -> int:
        had_birthday = (day.month, day.day) >= (self.birth_date.month, self.birth_date.day)
        return day.year - self.birth_date.year - (0 if had_birthday else 1)
