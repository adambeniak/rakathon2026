"""Demo clock schemas (only served when STAFETA_DEMO_MODE=1)."""

from __future__ import annotations

from datetime import date, datetime, time

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.domain.errors import InvalidInputError
from app.settings import PRAGUE

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


def parse_target(value: str) -> datetime:
    """`to` of the advance call: YYYY-MM-DD means 09:00 Prague that day (the demo script's convention), a timestamp
    without offset is Prague time."""
    try:
        parsed = (
            datetime.combine(date.fromisoformat(value), time(9, 0), tzinfo=PRAGUE)
            if len(value) == 10
            else datetime.fromisoformat(value)
        )
    except ValueError as exc:
        raise InvalidInputError("to must be YYYY-MM-DD or an ISO 8601 timestamp") from exc
    parsed = parsed if parsed.tzinfo else parsed.replace(tzinfo=PRAGUE)
    if not MIN_YEAR <= parsed.year <= MAX_YEAR:
        raise InvalidInputError(f"to must be between {MIN_YEAR} and {MAX_YEAR}")
    return parsed


class AdvancedStep(BaseModel):
    task_id: str
    events: list[str] = Field(description="Task-machine events applied, in order (e.g. order_confirmed, accept, …).")


class SkippedStep(BaseModel):
    task_id: str
    reason: str = Field(description="Czech, e.g. the result document is not uploaded for the patient yet.")


class DemoAdvanced(DemoClock):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "now": "2026-10-16T09:00:00+02:00",
                    "overridden": True,
                    "applied": [{"task_id": "c1.ct", "events": ["order_confirmed", "accept", "start", "performed"]}],
                    "skipped": [],
                    "escalated": ["c1.histology"],
                }
            ]
        }
    )

    applied: list[AdvancedStep] = Field(description="Story steps replayed by this call; empty when it was repeated.")
    skipped: list[SkippedStep]
    escalated: list[str] = Field(description="Tasks the watchdog escalated at the new time (once each).")
