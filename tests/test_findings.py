import pytest

from buildreport.findings import Finding, counts, finding, sort_findings


def test_severity_follows_the_code():
    assert finding("SHEET_RENAMED", "CL-03_2025-W38.xlsx", "renamed").severity == "warning"
    assert finding("FILE_UNREADABLE", "CL-09_2025-W38.xlsx", "corrupt").severity == "error"
    assert finding("NO_DATA", "", "no valid file").severity == "error"


def test_unknown_code_is_rejected():
    with pytest.raises(ValueError, match="unknown finding code"):
        finding("SHEET_GONE", "x.xlsx", "?")


def test_severity_must_fit_the_code():
    with pytest.raises(ValueError, match="has severity warning"):
        Finding("error", "SHEET_RENAMED", "x.xlsx", "renamed")


def test_sort_puts_errors_first_and_period_findings_last():
    items = [
        finding("MISSING_BRANCH", "", "CL-12 missing"),
        finding("SHEET_RENAMED", "b.xlsx", "renamed"),
        finding("EXTRA_COLUMN", "a.xlsx", "notes"),
        finding("FILE_UNREADABLE", "c.xlsx", "corrupt"),
        finding("NO_DATA", "", "nothing"),
    ]
    ordered = [(item.code, item.file) for item in sort_findings(items)]
    assert ordered == [
        ("FILE_UNREADABLE", "c.xlsx"),
        ("NO_DATA", ""),
        ("EXTRA_COLUMN", "a.xlsx"),
        ("SHEET_RENAMED", "b.xlsx"),
        ("MISSING_BRANCH", ""),
    ]


def test_counts_and_dict():
    items = [finding("SHEET_RENAMED", "a.xlsx", "x"), finding("WEEK_MISSING", "b.xlsx", "y")]
    assert counts(items) == {"error": 0, "warning": 2}
    assert list(items[0].as_dict()) == ["severity", "code", "file", "message"]


def test_line_format():
    line = finding("WEEK_MISSING", "CL-08_2025-W38.xlsx", "ISO week blank on the cover").line()
    assert line == "warning  WEEK_MISSING         CL-08_2025-W38.xlsx  ISO week blank on the cover"
    assert finding("NO_DATA", "", "no valid file").line().startswith("error    NO_DATA              -  ")
