"""ISO 8601 weeks: parse and format YYYY-Www, week bounds, the trend window and the last completed week."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_PATTERN = re.compile(r"^\s*([0-9]{4})-?[Ww]([0-9]{2})\s*$")


def weeks_in_year(year: int) -> int:
    """52 or 53: 28 December always lies in the last ISO week of its year."""
    return date(year, 12, 28).isocalendar()[1]


@dataclass(frozen=True, order=True)
class IsoWeek:
    year: int
    week: int

    def __post_init__(self) -> None:
        if not 1 <= self.week <= weeks_in_year(self.year):
            raise ValueError(f"{self.year}-W{self.week:02d} is not a valid ISO week")

    @classmethod
    def parse(cls, text: str) -> IsoWeek:
        match = _PATTERN.match(text)
        if match is None:
            raise ValueError(f"{text!r} is not an ISO week such as 2025-W38")
        return cls(int(match.group(1)), int(match.group(2)))

    @classmethod
    def from_date(cls, day: date) -> IsoWeek:
        iso = day.isocalendar()
        return cls(iso[0], iso[1])

    @property
    def monday(self) -> date:
        return date.fromisocalendar(self.year, self.week, 1)

    @property
    def sunday(self) -> date:
        return date.fromisocalendar(self.year, self.week, 7)

    def shift(self, weeks: int) -> IsoWeek:
        return IsoWeek.from_date(self.monday + timedelta(weeks=weeks))

    def __str__(self) -> str:
        return f"{self.year}-W{self.week:02d}"


def last_completed(now: datetime) -> IsoWeek:
    """The ISO week before the week that contains ``now``, taken in UTC."""
    if now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return IsoWeek.from_date(now.astimezone(UTC).date()).shift(-1)


def window(end: IsoWeek, weeks: int) -> tuple[IsoWeek, ...]:
    """``weeks`` consecutive ISO weeks ending with ``end``, oldest first."""
    if weeks < 1:
        raise ValueError("a window needs at least one week")
    return tuple(end.shift(-offset) for offset in range(weeks - 1, -1, -1))


def format_range(week: IsoWeek) -> str:
    """English date range of a week, such as '15 to 21 September 2025' (month names from code, not the locale)."""
    first, last = week.monday, week.sunday
    if first.year != last.year:
        return f"{first.day} {MONTHS[first.month - 1]} {first.year} to {last.day} {MONTHS[last.month - 1]} {last.year}"
    if first.month != last.month:
        return f"{first.day} {MONTHS[first.month - 1]} to {last.day} {MONTHS[last.month - 1]} {last.year}"
    return f"{first.day} to {last.day} {MONTHS[last.month - 1]} {last.year}"
