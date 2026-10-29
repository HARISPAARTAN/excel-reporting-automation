from dataclasses import replace
from datetime import datetime
from pathlib import Path

from buildreport.discover import SourceFile
from buildreport.findings import finding
from buildreport.isoweek import IsoWeek, window
from buildreport.resolve import assign_week, resolve
from buildreport.template import BranchReturn, ReadResult

W38 = IsoWeek(2025, 38)
WINDOW = window(W38, 8)


def fake(
    name,
    code="CL-01",
    cover_week=W38,
    cover_text="default",
    name_week="default",
    submitted=datetime(2025, 9, 22, 8, 7),
    sha="a" * 64,
    errors=(),
):
    name_week = (cover_week if cover_week is not None else W38) if name_week == "default" else name_week
    text = (str(cover_week) if cover_week is not None else None) if cover_text == "default" else cover_text
    source = SourceFile(
        Path(name), name, True, code, str(name_week) if name_week else None, name_week if name_week else None
    )
    findings = tuple(finding(item, name, "test") for item in errors)
    ret = None
    if not errors:
        sales = {"Bread": {"net_sales_eur": 100.0}}
        ret = BranchReturn(name, code, 10, submitted, sales, {"Bakery": {"labour_hours": 1.0}})
    return ReadResult(source, 7000, sha, True, code, text, cover_week, submitted, ret, findings)


def full_set(**overrides):
    """One clean result per branch for every week of the window."""
    results = []
    for week in WINDOW:
        for number in range(1, 13):
            code = f"CL-{number:02d}"
            results.append(
                fake(f"{code}_{week}.xlsx", code=code, cover_week=week, sha=f"{code}{week}".ljust(64, "0"))
            )
    return results


def codes(resolution):
    return [item.code for item in resolution.findings]


def test_cover_week_wins_over_the_name(cfg):
    result = fake("CL-11_2025-W28.xlsx", code="CL-11", cover_week=W38, name_week=IsoWeek(2025, 28))
    week, findings = assign_week(result)
    assert week == W38
    assert [item.code for item in findings] == ["WEEK_NAME_MISMATCH"]
    assert "cover says 2025-W38, file name says 2025-W28" in findings[0].message


def test_blank_cover_week_falls_back_to_the_name(cfg):
    week, findings = assign_week(fake("CL-08_2025-W38.xlsx", code="CL-08", cover_week=None, cover_text=None))
    assert week == W38 and [item.code for item in findings] == ["WEEK_MISSING"]


def test_unparsable_cover_week_falls_back_to_the_name(cfg):
    week, findings = assign_week(
        fake("CL-08_2025-W38.xlsx", code="CL-08", cover_week=None, cover_text="wk 38")
    )
    assert week == W38 and [item.code for item in findings] == ["WEEK_MISSING"]
    assert "'wk 38'" in findings[0].message


def test_no_week_anywhere_is_an_error(cfg):
    result = fake("CL-08 return.xlsx", code="CL-08", cover_week=None, cover_text=None, name_week=None)
    week, findings = assign_week(result)
    assert week is None and [item.code for item in findings] == ["WEEK_INVALID"]


def test_clean_window_has_no_findings(cfg):
    resolution = resolve(full_set(), cfg, WINDOW, W38)
    assert resolution.findings == ()
    assert len(resolution.returns) == 96
    assert all(item.status == "used" for item in resolution.inputs)
    assert resolution.reporting(W38) == 12 and not resolution.excluded_by_error


def test_identical_duplicate_keeps_the_first_by_name(cfg):
    results = full_set()
    original = next(item for item in results if item.source.name == "CL-04_2025-W38.xlsx")
    copy = replace(original, source=replace(original.source, name="CL-04_2025-W38_copy.xlsx"))
    resolution = resolve([*results, copy], cfg, WINDOW, W38)
    assert codes(resolution) == ["DUPLICATE_IDENTICAL"]
    assert resolution.findings[0].file == "CL-04_2025-W38_copy.xlsx"
    statuses = {item.file: item.status for item in resolution.inputs}
    assert statuses["CL-04_2025-W38.xlsx"] == "used" and statuses["CL-04_2025-W38_copy.xlsx"] == "duplicate"


def test_later_submission_replaces_the_earlier(cfg):
    results = [item for item in full_set() if item.source.name != "CL-10_2025-W37.xlsx"]
    week = IsoWeek(2025, 37)
    first = fake("CL-10_2025-W37.xlsx", code="CL-10", cover_week=week, submitted=datetime(2025, 9, 15, 8, 40))
    resend = fake(
        "CL-10_2025-W37_resend.xlsx",
        code="CL-10",
        cover_week=week,
        submitted=datetime(2025, 9, 15, 14, 12),
        sha="b" * 64,
    )
    resolution = resolve([*results, first, resend], cfg, WINDOW, W38)
    assert codes(resolution) == ["DUPLICATE_REPLACED"]
    assert resolution.findings[0].file == "CL-10_2025-W37.xlsx"
    used = next(item for item in resolution.returns if item.ret.branch_code == "CL-10" and item.week == week)
    assert used.ret.file == "CL-10_2025-W37_resend.xlsx"


def test_equal_submission_times_exclude_every_copy(cfg):
    results = [item for item in full_set() if item.source.name != "CL-04_2025-W38.xlsx"]
    one = fake("CL-04_2025-W38.xlsx", code="CL-04", sha="c" * 64)
    two = fake("CL-04_2025-W38_b.xlsx", code="CL-04", sha="d" * 64)
    resolution = resolve([*results, one, two], cfg, WINDOW, W38)
    assert codes(resolution) == ["DUPLICATE_AMBIGUOUS", "DUPLICATE_AMBIGUOUS", "MISSING_BRANCH"]
    assert resolution.excluded_by_error and resolution.reporting(W38) == 11


def test_missing_branch_per_window_week(cfg):
    results = [item for item in full_set() if item.source.name != "CL-12_2025-W36.xlsx"]
    resolution = resolve(results, cfg, WINDOW, W38)
    assert codes(resolution) == ["MISSING_BRANCH"]
    assert resolution.findings[0].file == ""
    assert (
        "CL-12 Rowanmere" in resolution.findings[0].message and "2025-W36" in resolution.findings[0].message
    )
    assert resolution.reporting(IsoWeek(2025, 36)) == 11


def test_window_edges(cfg):
    oldest, before, after = WINDOW[0], WINDOW[0].shift(-1), W38.shift(1)
    extra = [
        fake(f"CL-01_{before}.xlsx", cover_week=before, sha="e" * 64, errors=("VALUE_INVALID",)),
        fake(f"CL-01_{after}.xlsx", cover_week=after, sha="f" * 64),
    ]
    resolution = resolve([*full_set(), *extra], cfg, WINDOW, W38)
    statuses = {item.file: item.status for item in resolution.inputs}
    assert statuses[f"CL-01_{oldest}.xlsx"] == "used"
    assert statuses[f"CL-01_{before}.xlsx"] == "outside window"
    assert statuses[f"CL-01_{after}.xlsx"] == "outside window"
    assert resolution.findings == ()


def test_no_data_for_the_period(cfg):
    results = [item for item in full_set() if item.cover_week != W38]
    resolution = resolve(results, cfg, WINDOW, W38)
    assert codes(resolution)[0] == "NO_DATA"
    assert codes(resolution).count("MISSING_BRANCH") == 12


def test_an_unreadable_file_without_a_name_week_stays_excluded(cfg):
    broken = fake("scan.xlsx", cover_week=None, cover_text=None, name_week=None, errors=("FILE_UNREADABLE",))
    broken = replace(broken, cover_read=False)
    resolution = resolve([*full_set(), broken], cfg, WINDOW, W38)
    assert codes(resolution) == ["FILE_UNREADABLE"]
    assert {item.file: item.status for item in resolution.inputs}["scan.xlsx"] == "excluded"
    assert resolution.excluded_by_error


def test_findings_are_sorted_with_errors_first(cfg):
    results = [item for item in full_set() if item.source.name != "CL-12_2025-W36.xlsx"]
    broken = fake("CL-09_2025-W38_x.xlsx", code="CL-09", sha="9" * 64, errors=("FILE_UNREADABLE",))
    resolution = resolve([*results, broken], cfg, WINDOW, W38)
    assert codes(resolution) == ["FILE_UNREADABLE", "MISSING_BRANCH"]


def test_validate_mode_without_a_period(cfg):
    results = [item for item in full_set() if item.source.name != "CL-12_2025-W36.xlsx"]
    resolution = resolve(results, cfg, None, None)
    assert resolution.findings == ()
    assert len(resolution.returns) == 95


def test_demo_resolution_has_the_six_warnings(demo_resolution):
    found = sorted((item.code, item.file) for item in demo_resolution.findings)
    assert found == [
        ("DUPLICATE_REPLACED", "CL-10_2025-W37.xlsx"),
        ("EXTRA_COLUMN", "CL-05_2025-W38.xlsx"),
        ("MISSING_BRANCH", ""),
        ("SHEET_RENAMED", "CL-03_2025-W38.xlsx"),
        ("WEEK_MISSING", "CL-08_2025-W38.xlsx"),
        ("WEEK_NAME_MISMATCH", "CL-11_2025-W28.xlsx"),
    ]
    statuses = [item.status for item in demo_resolution.inputs]
    assert len(statuses) == 96 and statuses.count("used") == 95 and statuses.count("replaced") == 1
    assert demo_resolution.reporting(W38) == 12 and demo_resolution.reporting(IsoWeek(2025, 36)) == 11


def test_records_are_long_and_sorted(cfg, demo_records):
    assert len(demo_records) == 2945
    first_week = [
        record
        for record in demo_records
        if record.week == IsoWeek(2025, 31) and record.branch_code == "CL-01"
    ]
    assert len(first_week) == 31
    assert [record.measure for record in first_week[:7]] == ["net_sales_eur"] * 6 + ["units_sold"]
    assert [record.category for record in first_week[:6]] == list(cfg.product_groups)
    assert first_week[-1].measure == "transactions" and first_week[-1].category == ""
    keys = [(record.week, record.branch_code) for record in demo_records]
    assert keys == sorted(keys)
