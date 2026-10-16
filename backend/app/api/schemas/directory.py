"""Directory schemas (KOC list for the referral form)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.config import JsonDict

_EXAMPLE: JsonDict = {
    "id": "koc2-nemocnice-lipova",
    "name": "KOC 2 – Komplexní onkologické centrum Nemocnice Lipová",
    "city": "Praha 4",
    "coordinator": {"id": "dvorakova-lucie@koc2-nemocnice-lipova", "display": "Koordinátor KOC 2", "phone": None},
}


class CoordinatorContact(BaseModel):
    id: str = Field(description="PractitionerRole business id of the coordinator.")
    display: str = Field(
        description="Role-level label, e.g. 'Koordinátor KOC 2'; the person is named once they accept."
    )
    phone: str | None = Field(None, description="Phone of the workplace, if the directory has one.")


class KocEntry(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [_EXAMPLE]})

    id: str = Field(description="Organization business id; send it as `koc_id` when creating a referral.")
    name: str
    city: str | None = None
    coordinator: CoordinatorContact | None = Field(None, description="Null when the directory lists no coordinator.")
