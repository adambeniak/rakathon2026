"""Time-to-treatment proxies T1/T2/T3 as the API returns them (computed in `app.timeline.intervals`)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.timeline.intervals import Interval, IntervalStatus, TimeToTreatment

_STATUS = (
    "measured = both end points recorded (`days` set); running = started, end not recorded yet; not_started = "
    "neither end point recorded yet; not_recorded = the start was never recorded; inconsistent = the recorded end lies "
    "before the start."
)


class TreatmentInterval(BaseModel):
    days: int | None = Field(None, ge=0, description="Whole calendar days (Europe/Prague); null unless `measured`.")
    status: IntervalStatus = Field(description=_STATUS)
    start: date | None = Field(None, description="Date of the start point, when recorded.")
    end: date | None = Field(None, description="Date of the end point, when recorded.")

    @classmethod
    def of(cls, value: Interval) -> TreatmentInterval:
        return cls(days=value.days, status=value.status, start=value.start, end=value.end)


class TimeToTreatmentIntervals(BaseModel):
    """Proxies, to be labelled so: T1 = první návštěva PL → žádost do KOC, T2 = žádost do KOC → MDT,
    T3 = MDT → onkologické konzilium. Unknown values are null, never estimated."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "t1": {"days": None, "status": "not_recorded", "start": None, "end": "2026-10-02"},
                    "t2": {"days": 19, "status": "measured", "start": "2026-10-02", "end": "2026-10-21"},
                    "t3": {"days": None, "status": "running", "start": "2026-10-21", "end": None},
                }
            ]
        }
    )

    t1: TreatmentInterval = Field(description="První návštěva PL → žádost do KOC (proxy).")
    t2: TreatmentInterval = Field(description="Žádost do KOC → MDT (proxy; the MDT counts once it has been held).")
    t3: TreatmentInterval = Field(description="MDT → onkologické konzilium (proxy).")

    @classmethod
    def of(cls, value: TimeToTreatment) -> TimeToTreatmentIntervals:
        return cls(
            t1=TreatmentInterval.of(value.t1), t2=TreatmentInterval.of(value.t2), t3=TreatmentInterval.of(value.t3)
        )
