"""Demo clock and Czech working-day arithmetic.

All logic must call `now()` / `today()` — never `datetime.now()` directly.
`STAFETA_DEMO_NOW` (ISO 8601; naive values are Europe/Prague) pins the clock for the demo.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Prague")
ENV_VAR = "STAFETA_DEMO_NOW"

_override: datetime | None = None


def _parse(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{ENV_VAR} is not a valid ISO 8601 timestamp: {value!r}") from exc
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)


def now() -> datetime:
    if _override is not None:
        return _override
    raw = os.environ.get(ENV_VAR)
    if raw:
        return _parse(raw)
    return datetime.now(TZ)


def today() -> date:
    return now().date()


@contextmanager
def frozen(value: datetime | str) -> Iterator[None]:
    """Test helper: pin the clock inside a `with` block."""
    global _override
    previous = _override
    _override = _parse(value) if isinstance(value, str) else value
    try:
        yield
    finally:
        _override = previous


# --- working days -----------------------------------------------------------------------------

_FIXED_HOLIDAYS = {
    (1, 1),  # Nový rok / Den obnovy samostatného českého státu
    (5, 1),  # Svátek práce
    (5, 8),  # Den vítězství
    (7, 5),  # Cyril a Metoděj
    (7, 6),  # Jan Hus
    (9, 28),  # Den české státnosti
    (10, 28),  # Vznik Československa
    (11, 17),  # Den boje za svobodu a demokracii
    (12, 24),  # Štědrý den
    (12, 25),
    (12, 26),
}


def easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


def is_holiday(d: date) -> bool:
    if (d.month, d.day) in _FIXED_HOLIDAYS:
        return True
    easter = easter_sunday(d.year)
    return d in (easter - timedelta(days=2), easter + timedelta(days=1))


def is_workday(d: date) -> bool:
    return d.weekday() < 5 and not is_holiday(d)


def next_workday(d: date) -> date:
    """First working day strictly after `d`."""
    return add_workdays(d, 1)


def add_workdays(d: date, n: int) -> date:
    """`d` + n working days (n >= 0). n == 0 returns `d` unchanged."""
    if n < 0:
        raise ValueError("n must be >= 0")
    current = d
    remaining = n
    while remaining:
        current += timedelta(days=1)
        if is_workday(current):
            remaining -= 1
    return current


def workdays_between(start: date, end: date) -> int:
    """Working days in (start, end]; 0 when end <= start."""
    count = 0
    current = start
    while current < end:
        current += timedelta(days=1)
        if is_workday(current):
            count += 1
    return count
