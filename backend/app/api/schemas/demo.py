"""Demo clock schemas (only served when STAFETA_DEMO_MODE=1)."""

from __future__ import annotations

from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

MIN_YEAR, MAX_YEAR = 2020, 2035  # the working-day arithmetic walks day by day: an absurd date would stall the board


class DemoClock(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"now": "2026-10-16T09:00:00+02:00", "overridden": True}]},
    )

    now: AwareDatetime = Field(description="The backend's current time (Europe/Prague) that all deadlines use.")
    overridden: bool = Field(description="True when the clock was moved with PUT; false = start value or wall clock.")


class SetDemoClock(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"now": "2026-10-16T09:00:00+02:00"}, {"now": None}]},
    )

    now: datetime | None = Field(
        description="The time to pin the backend clock to (a timestamp without offset is Europe/Prague); "
        "null resets it to the start value (`STAFETA_DEMO_NOW`) or the wall clock."
    )

    @field_validator("now")
    @classmethod
    def _plausible(cls, value: datetime | None) -> datetime | None:
        if value is not None and not MIN_YEAR <= value.year <= MAX_YEAR:
            raise ValueError(f"now must be between {MIN_YEAR} and {MAX_YEAR}")
        return value
