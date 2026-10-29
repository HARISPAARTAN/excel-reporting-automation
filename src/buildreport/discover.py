"""Input discovery: the *.xlsx files of a folder, sorted by name, with branch and week parsed from the name."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from buildreport.isoweek import IsoWeek


@dataclass(frozen=True)
class SourceFile:
    path: Path
    name: str
    matches: bool  # the name matched input.file_pattern
    branch: str | None  # from the name
    week_text: str | None  # from the name, as written
    week: IsoWeek | None  # None when the name carries no valid ISO week


def parse_name(path: Path, pattern: re.Pattern[str]) -> SourceFile:
    match = pattern.match(path.name)
    if match is None:
        return SourceFile(path, path.name, False, None, None, None)
    week_text = match.group("week")
    try:
        week: IsoWeek | None = IsoWeek.parse(week_text)
    except ValueError:
        week = None
    return SourceFile(path, path.name, True, match.group("branch"), week_text, week)


def discover(folder: Path, pattern: str) -> list[SourceFile]:
    """Every *.xlsx in ``folder`` (Excel lock files ~$* skipped), sorted by name."""
    regex = re.compile(pattern)
    paths = [
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() == ".xlsx" and not path.name.startswith("~$")
    ]
    return [parse_name(path, regex) for path in sorted(paths, key=lambda item: item.name)]
