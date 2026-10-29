import zipfile
from datetime import datetime

import pytest

from buildreport.discover import discover
from buildreport.template import read_return

from helpers import W38, codes, read, source, workbook


def test_clean_file_reads_without_findings(cfg, tmp_path):
    result = read(cfg, workbook(cfg), tmp_path)
    assert result.findings == ()
    assert result.cover_read and result.cover_branch == "CL-03" and result.cover_week == W38
    ret = result.ret
    assert ret.branch_code == "CL-03" and ret.file == "CL-03_2025-W38.xlsx"
    assert list(ret.sales) == list(cfg.product_groups)
    assert list(ret.labour) == list(cfg.roles)
    assert set(ret.sales["Bread"]) == {"net_sales_eur", "units_sold", "waste_units", "waste_eur"}
    assert isinstance(ret.transactions, int) and ret.transactions > 0
    assert ret.submitted_at == datetime(2025, 9, 22, 8, 21)


def test_renamed_sheet_is_found_by_alias(cfg, tmp_path):
    book = workbook(cfg)
    book["Sales"].title = "Sales wk38"
    result = read(cfg, book, tmp_path)
    assert codes(result) == ["SHEET_RENAMED"]
    assert "'Sales wk38'" in result.findings[0].message
    assert result.ret is not None


def test_exact_sheet_name_ignores_case(cfg, tmp_path):
    book = workbook(cfg)
    sheet = book["Labour"]
    sheet.title = "Hours"  # openpyxl appends a digit when a new title matches an existing one without case
    sheet.title = "LABOUR"
    assert read(cfg, book, tmp_path).findings == ()


def test_two_alias_matches_are_an_error(cfg, tmp_path):
    book = workbook(cfg)
    book["Sales"].title = "Sales A"
    book.copy_worksheet(book["Sales A"]).title = "Sales B"
    result = read(cfg, book, tmp_path)
    assert codes(result) == ["SHEET_MISSING"]
    assert result.ret is None


def test_missing_sheet_is_an_error(cfg, tmp_path):
    book = workbook(cfg)
    del book["Labour"]
    result = read(cfg, book, tmp_path)
    assert codes(result) == ["SHEET_MISSING"]
    assert result.ret is None


def test_extra_column_is_ignored_with_a_warning(cfg, tmp_path):
    book = workbook(cfg)
    sheet = book["Sales"]
    sheet.insert_cols(4)
    sheet["D1"] = "Notes"
    sheet["D2"] = "oven fault"
    result = read(cfg, book, tmp_path, "CL-03_2025-W38_notes.xlsx")
    clean = read(cfg, workbook(cfg), tmp_path)
    assert codes(result) == ["EXTRA_COLUMN"]
    assert result.ret.sales == clean.ret.sales


def test_columns_match_by_header_in_any_order(cfg, tmp_path):
    book = workbook(cfg)
    sheet = book["Labour"]
    for row in sheet.iter_rows():
        row[1].value, row[2].value = row[2].value, row[1].value
    sheet["B1"] = "  cost   eur "
    result = read(cfg, book, tmp_path)
    clean = read(cfg, workbook(cfg), tmp_path, "CL-03_2025-W38_clean.xlsx")
    assert result.findings == ()
    assert result.ret.labour == clean.ret.labour


def test_missing_column_is_an_error(cfg, tmp_path):
    book = workbook(cfg)
    book["Sales"]["E1"] = "Waste value"
    result = read(cfg, book, tmp_path)
    assert codes(result) == ["COLUMN_MISSING", "EXTRA_COLUMN"]
    assert result.ret is None


def test_unknown_row_is_an_error(cfg, tmp_path):
    book = workbook(cfg)
    book["Sales"]["A7"] = "Croissants"
    result = read(cfg, book, tmp_path)
    assert codes(result) == ["ROW_UNKNOWN", "ROW_MISSING"]
    assert result.ret is None


def test_missing_row_counts_as_zero(cfg, tmp_path):
    book = workbook(cfg)
    book["Sales"].delete_rows(6)
    result = read(cfg, book, tmp_path)
    assert codes(result) == ["ROW_MISSING"]
    assert result.ret.sales["Hot Drinks"] == {
        "net_sales_eur": 0.0,
        "units_sold": 0.0,
        "waste_units": 0.0,
        "waste_eur": 0.0,
    }


def test_total_and_blank_rows_are_ignored(cfg, tmp_path):
    book = workbook(cfg)
    book["Sales"]["A9"] = "TOTAL"
    book["Sales"]["B9"] = 99999.0
    result = read(cfg, book, tmp_path)
    assert result.findings == ()


@pytest.mark.parametrize(
    ("cell", "value", "fragment"),
    [
        ("B2", "1.234,50", "text '1.234,50' in a numeric cell"),
        ("C3", -4, "negative value -4"),
        ("E4", None, "blank"),
        ("C5", 12.5, "12.5 is not a whole number"),
    ],
)
def test_invalid_values(cfg, tmp_path, cell, value, fragment):
    book = workbook(cfg)
    book["Sales"][cell] = value
    result = read(cfg, book, tmp_path)
    assert codes(result) == ["VALUE_INVALID"]
    assert fragment in result.findings[0].message
    assert result.ret is None


def test_duplicate_row_is_an_error(cfg, tmp_path):
    book = workbook(cfg)
    book["Labour"]["A4"] = "Counter"
    result = read(cfg, book, tmp_path)
    assert codes(result) == ["VALUE_INVALID", "ROW_MISSING"]


@pytest.mark.parametrize(
    ("code", "name", "fragment"),
    [
        ("CL-13", "CL-13_2025-W38.xlsx", "not in report.yaml"),
        ("CL-04", "CL-03_2025-W38.xlsx", "cover says CL-04, the file name says CL-03"),
        (None, "CL-03_2025-W38.xlsx", "blank"),
    ],
)
def test_branch_code_problems(cfg, tmp_path, code, name, fragment):
    book = workbook(cfg)
    book["Cover"]["B3"] = code
    result = read(cfg, book, tmp_path, name)
    assert codes(result) == ["BRANCH_INVALID"]
    assert fragment in result.findings[0].message
    assert result.ret is None


def test_template_version_other_than_3_is_a_warning(cfg, tmp_path):
    book = workbook(cfg)
    book["Cover"]["B9"] = 2
    result = read(cfg, book, tmp_path)
    assert codes(result) == ["TEMPLATE_VERSION"]
    assert result.ret is not None


@pytest.mark.parametrize("payload", [b"not a workbook", "zip"])
def test_unreadable_files(cfg, tmp_path, payload):
    path = tmp_path / "CL-09_2025-W38.xlsx"
    if payload == "zip":
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("hello.txt", "no workbook parts")
    else:
        path.write_bytes(payload)
    result = read_return(source(cfg, path), cfg)
    assert codes(result) == ["FILE_UNREADABLE"]
    assert not result.cover_read and result.ret is None


def test_file_name_off_pattern_takes_identity_from_the_cover(cfg, tmp_path):
    result = read(cfg, workbook(cfg), tmp_path, "Corravale week 38.xlsx")
    assert codes(result) == ["FILE_NAME"]
    assert result.ret.branch_code == "CL-03" and result.cover_week == W38


def test_file_name_with_an_invalid_week(cfg, tmp_path):
    result = read(cfg, workbook(cfg), tmp_path, "CL-03_2025-W53.xlsx")
    assert codes(result) == ["FILE_NAME"]
    assert "'2025-W53'" in result.findings[0].message


@pytest.mark.parametrize(
    ("cell", "value", "fragment"),
    [
        ("B6", "1,204", "Transactions on the cover: text '1,204'"),
        ("B7", None, "Submitted at on the cover: blank"),
    ],
)
def test_invalid_cover_values(cfg, tmp_path, cell, value, fragment):
    book = workbook(cfg)
    book["Cover"][cell] = value
    result = read(cfg, book, tmp_path)
    assert codes(result) == ["VALUE_INVALID"]
    assert fragment in result.findings[0].message


def test_cover_week_text_is_kept_for_the_resolver(cfg, tmp_path):
    book = workbook(cfg)
    book["Cover"]["B5"] = "week 38"
    result = read(cfg, book, tmp_path)
    assert result.findings == ()
    assert result.cover_week_text == "week 38" and result.cover_week is None
    book["Cover"]["B5"] = None
    blank = read(cfg, book, tmp_path, "CL-03_2025-W38_b.xlsx")
    assert blank.cover_week_text is None and blank.cover_week is None


def test_discover_sorts_and_skips_other_files(cfg, tmp_path):
    for name in [
        "CL-02_2025-W38.xlsx",
        "CL-01_2025-W38.xlsx",
        "~$CL-01_2025-W38.xlsx",
        "notes.txt",
        "Corravale.XLSX",
    ]:
        (tmp_path / name).write_bytes(b"x")
    found = discover(tmp_path, cfg.model.input.file_pattern)
    assert [item.name for item in found] == ["CL-01_2025-W38.xlsx", "CL-02_2025-W38.xlsx", "Corravale.XLSX"]
    assert found[0].matches and found[0].branch == "CL-01" and found[0].week == W38
    assert not found[2].matches and found[2].branch is None


def test_demo_set_reader_findings(cfg, demo_dir):
    results = [read_return(item, cfg) for item in discover(demo_dir, cfg.model.input.file_pattern)]
    found = sorted((item.code, item.file) for result in results for item in result.findings)
    assert found == [("EXTRA_COLUMN", "CL-05_2025-W38.xlsx"), ("SHEET_RENAMED", "CL-03_2025-W38.xlsx")]
    assert len(results) == 96
    assert all(result.ret is not None for result in results)
