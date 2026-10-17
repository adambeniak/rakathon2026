"""Schema of the stored MDT conclusion."""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.domain.common import Role


class SignedBy(BaseModel):
    id: str = Field(description="PractitionerRole business id of the signing physician.")
    display: str
    role: Role | None = Field(None, description="Role of the signer in the directory; null if unknown.")


class MdtConclusionOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "text": "Závěr MDT dle zápisu.",
                    "signed_by": {
                        "id": "markova-lenka@koc2-nemocnice-lipova",
                        "display": "MUDr. Lenka Marková",
                        "role": "koc_physician",
                    },
                    "signed_at": "2026-10-21T09:30:00+02:00",
                }
            ]
        }
    )

    text: str = Field(description="The conclusion as signed; stored in the MDT conclusion Composition.")
    signed_by: SignedBy
    signed_at: AwareDatetime
