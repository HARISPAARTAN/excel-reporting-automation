"""Resolver: week assignment, duplicates, the window, missing branches, and the long records."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from buildreport.config import COVER_MEASURE, Config
from buildreport.findings import Finding, finding, sort_findings
from buildreport.isoweek import IsoWeek
from buildreport.template import BranchReturn, ReadResult

Status = Literal["used", "replaced", "duplicate", "excluded", "outside window"]


@dataclass(frozen=True)
class InputFile:
    file: str
    bytes: int
    sha256: str
    branch: str | None
    week: str | None
    submitted_at: str | None
    status: Status

    def as_dict(self) -> dict[str, object]:
        return {
            "file": self.file,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "branch": self.branch,
            "week": self.week,
            "submitted_at": self.submitted_at,
            "status": self.status,
        }


@dataclass(frozen=True)
class UsedReturn:
    week: IsoWeek
    ret: BranchReturn


@dataclass(frozen=True)
class Resolution:
    inputs: tuple[InputFile, ...]
    returns: tuple[UsedReturn, ...]
    findings: tuple[Finding, ...]
    window: tuple[IsoWeek, ...]

    @property
    def excluded_by_error(self) -> bool:
        return any(item.status == "excluded" for item in self.inputs)

    @property
    def has_errors(self) -> bool:
        return any(item.severity == "error" for item in self.findings)

    def reporting(self, week: IsoWeek) -> int:
        return len({item.ret.branch_code for item in self.returns if item.week == week})


@dataclass(frozen=True)
class Record:
    week: IsoWeek
    branch_code: str
    category: str  # product group, role, or "" for transactions
    measure: str
    value: float
    source_file: str


def assign_week(result: ReadResult) -> tuple[IsoWeek | None, list[Finding]]:
    """The cover week wins; a blank or unparsable cover week falls back to the week in the file name."""
    name_week = result.source.week
    if not result.cover_read:
        return name_week, []
    file = result.source.name
    if result.cover_week is not None:
        if name_week is not None and name_week != result.cover_week:
            message = f"cover says {result.cover_week}, file name says {name_week}; cover used"
            return result.cover_week, [finding("WEEK_NAME_MISMATCH", file, message)]
        return result.cover_week, []
    if name_week is not None:
        if result.cover_week_text is None:
            message = f"ISO week blank on the cover; {name_week} taken from the file name"
        else:
            message = f"cover week {result.cover_week_text!r} is not an ISO week; {name_week} taken from the file name"
        return name_week, [finding("WEEK_MISSING", file, message)]
    return None, [finding("WEEK_INVALID", file, "no valid ISO week on the cover or in the file name")]


def _when(result: ReadResult) -> str | None:
    return result.submitted_at.isoformat(timespec="minutes") if result.submitted_at else None


def resolve(
    results: Sequence[ReadResult],
    cfg: Config,
    window: tuple[IsoWeek, ...] | None,
    period: IsoWeek | None,
) -> Resolution:
    findings: list[Finding] = []
    status: dict[str, Status] = {}
    weeks: dict[str, IsoWeek | None] = {}
    candidates: dict[tuple[str, IsoWeek], list[ReadResult]] = defaultdict(list)
    for result in sorted(results, key=lambda item: item.source.name):
        name = result.source.name
        week, week_findings = assign_week(result)
        weeks[name] = week
        if window is not None and week is not None and week not in window:
            status[name] = "outside window"
            continue
        findings.extend(result.findings)
        findings.extend(week_findings)
        if week is None or result.ret is None or result.has_error:
            status[name] = "excluded"
            continue
        candidates[(result.ret.branch_code, week)].append(result)

    used: list[UsedReturn] = []
    for (code, week), group in sorted(candidates.items(), key=lambda item: (item[0][1], item[0][0])):
        distinct: list[ReadResult] = []
        for result in group:
            twin = next((item for item in distinct if item.sha256 == result.sha256), None)
            if twin is None:
                distinct.append(result)
                continue
            status[result.source.name] = "duplicate"
            message = f"same content as {twin.source.name}; the first by name is kept"
            findings.append(finding("DUPLICATE_IDENTICAL", result.source.name, message))
        if len(distinct) == 1:
            keep = distinct[0]
        else:
            latest = max(item.submitted_at for item in distinct if item.submitted_at is not None)
            newest = [item for item in distinct if item.submitted_at == latest]
            if len(newest) > 1:
                for item in distinct:
                    status[item.source.name] = "excluded"
                    message = (
                        f"{code} {week}: {len(distinct)} different files with the same Submitted at "
                        f"{latest:%Y-%m-%d %H:%M}; all copies excluded"
                    )
                    findings.append(finding("DUPLICATE_AMBIGUOUS", item.source.name, message))
                continue
            keep = newest[0]
            for item in distinct:
                if item is keep:
                    continue
                status[item.source.name] = "replaced"
                message = (
                    f"replaced by {keep.source.name} (submitted {latest:%Y-%m-%d %H:%M}, "
                    f"later than {item.submitted_at:%Y-%m-%d %H:%M})"
                )
                findings.append(finding("DUPLICATE_REPLACED", item.source.name, message))
        status[keep.source.name] = "used"
        assert keep.ret is not None
        used.append(UsedReturn(week, keep.ret))

    if window is not None:
        present = {(item.ret.branch_code, item.week) for item in used}
        for week in window:
            for branch in cfg.branches:
                if (branch.code, week) not in present:
                    message = f"{branch.code} {branch.name}: no valid file for {week}; branch left blank"
                    findings.append(finding("MISSING_BRANCH", "", message))
    if period is not None and not any(item.week == period for item in used):
        findings.append(finding("NO_DATA", "", f"no valid file for {period}; no report can be built"))

    inputs = tuple(
        InputFile(
            file=result.source.name,
            bytes=result.size,
            sha256=result.sha256,
            branch=result.cover_branch or result.source.branch,
            week=str(weeks[result.source.name]) if weeks[result.source.name] else None,
            submitted_at=_when(result),
            status=status[result.source.name],
        )
        for result in sorted(results, key=lambda item: item.source.name)
    )
    return Resolution(inputs, tuple(used), sort_findings(findings), window or ())


def to_records(returns: Sequence[UsedReturn], cfg: Config) -> list[Record]:
    """Long records: 31 per branch-week with the committed configuration, sorted for the Data sheet."""
    records: list[Record] = []
    for item in sorted(returns, key=lambda used: (used.week, used.ret.branch_code)):
        ret = item.ret
        for measure in cfg.sales_measures:
            for group in cfg.product_groups:
                records.append(
                    Record(item.week, ret.branch_code, group, measure, ret.sales[group][measure], ret.file)
                )
        for measure in cfg.labour_measures:
            for role in cfg.roles:
                records.append(
                    Record(item.week, ret.branch_code, role, measure, ret.labour[role][measure], ret.file)
                )
        records.append(
            Record(item.week, ret.branch_code, "", COVER_MEASURE, float(ret.transactions), ret.file)
        )
    return records
