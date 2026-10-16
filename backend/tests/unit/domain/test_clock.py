from datetime import date, datetime

import pytest

from app.domain import clock


def test_env_pins_clock(monkeypatch):
    monkeypatch.setenv(clock.ENV_VAR, "2026-10-16T09:00:00+02:00")
    assert clock.now() == datetime(2026, 10, 16, 9, 0, tzinfo=clock.TZ)
    assert clock.today() == date(2026, 10, 16)


def test_naive_value_is_prague(monkeypatch):
    monkeypatch.setenv(clock.ENV_VAR, "2026-10-21T08:00:00")
    assert clock.now().utcoffset().total_seconds() == 2 * 3600


def test_invalid_value_raises(monkeypatch):
    monkeypatch.setenv(clock.ENV_VAR, "tomorrow")
    with pytest.raises(ValueError, match="valid ISO"):
        clock.now()


def test_frozen_restores():
    with clock.frozen("2026-10-02T10:00:00"):
        assert clock.today() == date(2026, 10, 2)
    assert clock._override is None


@pytest.mark.parametrize(
    ("start", "n", "expected"),
    [
        (date(2026, 10, 12), 3, date(2026, 10, 15)),  # Mon + 3 → Thu (demo SLA)
        (date(2026, 10, 15), 1, date(2026, 10, 16)),
        (date(2026, 10, 16), 1, date(2026, 10, 19)),  # weekend skipped
        (date(2026, 10, 27), 1, date(2026, 10, 29)),  # 28. 10. skipped
        (date(2026, 11, 16), 1, date(2026, 11, 18)),  # 17. 11. skipped
        (date(2026, 10, 12), 0, date(2026, 10, 12)),
    ],
)
def test_add_workdays(start, n, expected):
    assert clock.add_workdays(start, n) == expected


@pytest.mark.parametrize(
    ("d", "holiday"),
    [
        (date(2026, 10, 28), True),
        (date(2026, 11, 17), True),
        (date(2026, 4, 3), True),  # Good Friday 2026
        (date(2026, 4, 6), True),  # Easter Monday 2026
        (date(2026, 12, 24), True),
        (date(2026, 10, 21), False),
    ],
)
def test_holidays(d, holiday):
    assert clock.is_holiday(d) is holiday


def test_easter_2026():
    assert clock.easter_sunday(2026) == date(2026, 4, 5)


def test_workdays_between():
    assert clock.workdays_between(date(2026, 10, 15), date(2026, 10, 16)) == 1
    assert clock.workdays_between(date(2026, 10, 16), date(2026, 10, 19)) == 1
    assert clock.workdays_between(date(2026, 10, 16), date(2026, 10, 16)) == 0
    assert clock.next_workday(date(2026, 10, 16)) == date(2026, 10, 19)


def test_set_override_moves_and_resets_the_clock(monkeypatch):
    monkeypatch.setenv(clock.ENV_VAR, "2026-10-02T09:00:00+02:00")
    try:
        clock.set_override(datetime.fromisoformat("2026-10-16T09:00:00"))  # naive = Europe/Prague
        assert clock.is_overridden()
        assert clock.now() == datetime(2026, 10, 16, 9, 0, tzinfo=clock.TZ)
        clock.set_override(None)
        assert not clock.is_overridden()
        assert clock.now() == datetime(2026, 10, 2, 9, 0, tzinfo=clock.TZ)  # back to the start value
    finally:
        clock.set_override(None)
