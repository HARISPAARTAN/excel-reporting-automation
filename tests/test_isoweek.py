from datetime import UTC, date, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from buildreport.isoweek import IsoWeek, format_range, last_completed, weeks_in_year, window


def test_parse_and_format():
    assert str(IsoWeek.parse("2025-W38")) == "2025-W38"
    assert IsoWeek.parse("2025W38") == IsoWeek(2025, 38)
    assert IsoWeek.parse(" 2025-w38 ") == IsoWeek(2025, 38)
    assert str(IsoWeek(2026, 1)) == "2026-W01"


def test_week_53_exists_only_in_long_years():
    assert weeks_in_year(2026) == 53
    assert weeks_in_year(2025) == 52
    assert IsoWeek.parse("2026-W53").sunday == date(2027, 1, 3)
    with pytest.raises(ValueError):
        IsoWeek.parse("2025-W53")


def test_week_bounds_and_shift():
    week = IsoWeek(2025, 38)
    assert week.monday == date(2025, 9, 15)
    assert week.sunday == date(2025, 9, 21)
    assert week.shift(1) == IsoWeek(2025, 39)
    assert IsoWeek(2025, 1).shift(-1) == IsoWeek(2024, 52)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2025, 9, 21, 23, 59, tzinfo=UTC), IsoWeek(2025, 37)),  # Sunday evening: W38 still runs
        (datetime(2025, 9, 22, 0, 0, tzinfo=UTC), IsoWeek(2025, 38)),  # Monday midnight
        (datetime.fromtimestamp(1758520800, tz=UTC), IsoWeek(2025, 38)),  # the demo SOURCE_DATE_EPOCH
    ],
)
def test_last_completed_on_sunday_and_monday(now, expected):
    assert last_completed(now) == expected


def test_last_completed_needs_an_aware_datetime():
    with pytest.raises(ValueError):
        last_completed(datetime(2025, 9, 22, 6, 0))


def test_window_is_oldest_first():
    weeks = window(IsoWeek(2025, 38), 8)
    assert [str(week) for week in weeks] == [f"2025-W{number}" for number in range(31, 39)]


def test_window_crosses_the_year():
    assert window(IsoWeek(2026, 2), 3) == (IsoWeek(2025, 52), IsoWeek(2026, 1), IsoWeek(2026, 2))


@pytest.mark.parametrize(
    ("week", "text"),
    [
        (IsoWeek(2025, 38), "15 to 21 September 2025"),
        (IsoWeek(2025, 40), "29 September to 5 October 2025"),
        (IsoWeek(2026, 1), "29 December 2025 to 4 January 2026"),
    ],
)
def test_format_range(week, text):
    assert format_range(week) == text


@pytest.mark.parametrize("text", ["2025-38", "W38", "2025-W3", "2025-W00", "last", ""])
def test_malformed_weeks_are_rejected(text):
    with pytest.raises(ValueError):
        IsoWeek.parse(text)


@given(st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)))
def test_round_trip(day):
    week = IsoWeek.from_date(day)
    assert IsoWeek.parse(str(week)) == week
    assert week.monday <= day <= week.sunday
    assert week.shift(1).shift(-1) == week
