"""Findings: problems found in input files or in the period, each with severity, code, file and message."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning"]

ERROR_CODES = frozenset(
    {
        "FILE_UNREADABLE",
        "BRANCH_INVALID",
        "SHEET_MISSING",
        "COLUMN_MISSING",
        "ROW_UNKNOWN",
        "VALUE_INVALID",
        "WEEK_INVALID",
        "DUPLICATE_AMBIGUOUS",
        "NO_DATA",
    }
)
WARNING_CODES = frozenset(
    {
        "FILE_NAME",
        "TEMPLATE_VERSION",
        "SHEET_RENAMED",
        "EXTRA_COLUMN",
        "ROW_MISSING",
        "WEEK_MISSING",
        "WEEK_NAME_MISMATCH",
        "DUPLICATE_IDENTICAL",
        "DUPLICATE_REPLACED",
        "MISSING_BRANCH",
    }
)


@dataclass(frozen=True)
class Finding:
    severity: Severity
    code: str
    file: str
    message: str

    def __post_init__(self) -> None:
        if self.code in ERROR_CODES:
            expected = "error"
        elif self.code in WARNING_CODES:
            expected = "warning"
        else:
            raise ValueError(f"unknown finding code {self.code}")
        if self.severity != expected:
            raise ValueError(f"{self.code} has severity {expected}, not {self.severity}")

    def as_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "code": self.code, "file": self.file, "message": self.message}

    def line(self) -> str:
        return f"{self.severity:<7}  {self.code:<19}  {self.file or '-'}  {self.message}"


def finding(code: str, file: str, message: str) -> Finding:
    severity: Severity = "error" if code in ERROR_CODES else "warning"
    return Finding(severity, code, file, message)


def sort_findings(items: Iterable[Finding]) -> tuple[Finding, ...]:
    """Errors first; within a severity by file (period-level findings last), code and message."""
    return tuple(
        sorted(
            items,
            key=lambda item: (item.severity != "error", item.file == "", item.file, item.code, item.message),
        )
    )


def counts(items: Iterable[Finding]) -> dict[str, int]:
    result = {"error": 0, "warning": 0}
    for item in items:
        result[item.severity] += 1
    return result
