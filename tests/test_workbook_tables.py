import math
import re
from dataclasses import replace
from datetime import datetime

import pytest

from buildreport.isoweek import IsoWeek
from buildreport.metrics import compute, summarise
from buildreport.workbook import build, formula_cells
from buildreport.workbook.data import read_records

W38 = IsoWeek(2025, 38)
W37 = IsoWeek(2025, 37)
BRANCH_HEADERS = [
    "Code",
    "Branch",
    "Format",
    "Revenue",
    "Revenue last week",
    "WoW",
    "Transactions",
    "Average basket",
    "Waste EUR",
    "Waste %",
    "Labour hours",
    "Labour cost",
    "Labour % of revenue",
    "Revenue per labour hour",
    "Rank",
    "Rank change",
]
FOOTER = "Cedarline Bakeries · weekly report 2025-W38 · page &P of &N"


def close(actual, expected):
    """openpyxl writes numbers with 16 significant digits, so reloaded values match to about 1e-16."""
    return actual == pytest.approx(expected, rel=1e-12)


def plain(text):
    return text.replace("$", "").replace("'", "").split("!")[-1]


def rules(ws):
    found = set()
    for formatting in ws.conditional_formatting:
        for rule in formatting.rules:
            found.add((str(formatting.sqref), rule.type, rule.operator, tuple(rule.formula or ())))
    return found


def test_branches_rows_and_values(cfg, demo_wb, demo_result, demo_ctx):
    ws = demo_wb["Branches"]
    assert ws["A1"].value == "Branches · week 2025-W38"
    assert [cell.value for cell in ws[3]] == BRANCH_HEADERS
    assert [ws[f"A{row}"].value for row in range(4, 16)] == list(cfg.branch_codes)
    assert close(ws["D4"].value, demo_result.branch_value(W38, "CL-01", "revenue"))
    assert close(ws["E4"].value, demo_result.branch_value(W37, "CL-01", "revenue"))
    assert close(ws["J4"].value, demo_result.branch_value(W38, "CL-01", "waste_pct"))
    ranking = {row.code: row for row in demo_ctx.summary.ranking}
    for row in range(4, 16):
        code = ws[f"A{row}"].value
        assert ws[f"O{row}"].value == ranking[code].rank
        assert ws[f"P{row}"].value == ranking[code].rank_change


def test_branches_total_formulas(demo_wb):
    ws = demo_wb["Branches"]
    assert ws["A16"].value == "Total"
    expected = {
        "D16": "=SUM(D4:D15)",
        "E16": "=SUM(E4:E15)",
        "F16": '=IF(E16=0,"",D16/E16-1)',
        "G16": "=SUM(G4:G15)",
        "H16": '=IF(G16=0,"",D16/G16)',
        "I16": "=SUM(I4:I15)",
        "J16": '=IF(D16=0,"",I16/D16)',
        "K16": "=SUM(K4:K15)",
        "L16": "=SUM(L4:L15)",
        "M16": '=IF(D16=0,"",L16/D16)',
        "N16": '=IF(K16=0,"",D16/K16)',
    }
    assert {ref: ws[ref].value for ref in expected} == expected
    assert ws["D16"].font.b and ws["D16"].border.top.style == "thin"


def test_branches_trend_rows(demo_wb, demo_result):
    ws = demo_wb["Branches"]
    assert ws["A18"].value == "Weekly totals, last 8 weeks"
    assert [ws.cell(row=19, column=column).value for column in range(1, 8)] == [
        "Week",
        "Week start",
        "Revenue",
        "Transactions",
        "Waste %",
        "Labour % of revenue",
        "Branches reporting",
    ]
    assert [ws[f"A{row}"].value for row in range(20, 28)] == [f"2025-W{number}" for number in range(31, 39)]
    assert ws["B20"].value == datetime(2025, 7, 28)
    assert ws["G25"].value == 11 and ws["G27"].value == 12
    assert close(ws["C27"].value, demo_result.chain_value(W38, "revenue"))


def test_branches_page_setup(demo_wb):
    ws = demo_wb["Branches"]
    assert ws.freeze_panes == "C4"
    assert plain(ws.print_area) == "A1:P27"
    assert plain(ws.print_title_rows) == "3:3"
    assert ws.page_setup.orientation == "landscape" and ws.page_setup.paperSize == 9
    assert ws.sheet_properties.pageSetUpPr.fitToPage
    assert (ws.page_setup.fitToWidth, ws.page_setup.fitToHeight) == (1, 1)
    assert ws.sheet_view.showGridLines is False
    assert ws.oddFooter.center.text == FOOTER


def test_branches_conditional_formatting(demo_wb):
    found = rules(demo_wb["Branches"])
    assert ("D4:D15", "dataBar", None, ()) in found
    assert ("F4:F15", "cellIs", "greaterThan", ("0",)) in found
    assert ("F4:F15", "cellIs", "lessThan", ("0",)) in found
    assert ("J4:J15", "cellIs", "greaterThan", ("0.06",)) in found
    assert ("E20:E27", "cellIs", "greaterThan", ("0.06",)) in found
    assert ("M4:M15", "cellIs", "greaterThan", ("0.32",)) in found
    assert ("F20:F27", "cellIs", "greaterThan", ("0.32",)) in found
    assert len(found) == 7


def test_products_rows_and_totals(cfg, demo_wb, demo_result):
    ws = demo_wb["Products"]
    assert ws["A1"].value == "Product groups · week 2025-W38"
    assert [ws[f"A{row}"].value for row in range(4, 10)] == list(cfg.product_groups)
    assert close(ws["B4"].value, demo_result.group_value(W38, "Bread", "revenue"))
    assert close(ws["C4"].value, demo_result.share["Bread"])
    expected = {
        "B10": "=SUM(B4:B9)",
        "C10": "=SUM(C4:C9)",
        "D10": "=SUM(D4:D9)",
        "E10": '=IF(D10=0,"",B10/D10-1)',
        "F10": "=SUM(F4:F9)",
        "G10": "=SUM(G4:G9)",
        "H10": '=IF(B10=0,"",G10/B10)',
    }
    assert {ref: ws[ref].value for ref in expected} == expected


def test_products_mix_table(cfg, demo_wb, demo_result):
    ws = demo_wb["Products"]
    assert ws["A12"].value == "Revenue mix by branch (share of branch revenue)"
    assert [cell.value for cell in ws[13]] == ["Branch", *cfg.product_groups, "Total"]
    assert ws["A14"].value == "Alderbrook" and ws["A25"].value == "Rowanmere"
    assert close(ws["B14"].value, demo_result.mix[("CL-01", "Bread")])
    assert [ws[f"H{row}"].value for row in range(14, 26)] == [f"=SUM(B{row}:G{row})" for row in range(14, 26)]


def test_products_setup_and_formatting(demo_wb):
    ws = demo_wb["Products"]
    assert ws.freeze_panes == "B4"
    assert ws.page_setup.orientation == "landscape"
    assert (ws.page_setup.fitToWidth, ws.page_setup.fitToHeight) == (1, 1)
    found = rules(ws)
    assert ("B14:G25", "colorScale", None, ()) in found
    assert ("H4:H9", "cellIs", "greaterThan", ("0.06",)) in found
    scale = next(
        rule
        for formatting in ws.conditional_formatting
        for rule in formatting.rules
        if rule.type == "colorScale"
    )
    assert [color.rgb[-6:] for color in scale.colorScale.color] == ["FFFFFF", "F2A93B"]


def test_data_table(demo_wb):
    ws = demo_wb["Data"]
    table = ws.tables["tblWeekly"]
    assert table.ref == "A1:H2946"
    assert table.tableStyleInfo.name == "TableStyleMedium2" and table.tableStyleInfo.showRowStripes
    assert [cell.value for cell in ws[1]] == [
        "week",
        "week_start",
        "branch_code",
        "branch_name",
        "category",
        "measure",
        "value",
        "source_file",
    ]
    assert ws.max_row == 2946
    assert [cell.value for cell in ws[2]][:6] == [
        "2025-W31",
        datetime(2025, 7, 28),
        "CL-01",
        "Alderbrook",
        "Bread",
        "net_sales_eur",
    ]
    assert ws["G2"].number_format == "#,##0.00" and ws["B2"].number_format == "yyyy-mm-dd"
    assert ws.freeze_panes == "A2" and ws.sheet_view.showGridLines
    assert plain(ws.print_title_rows) == "1:1"
    assert (ws.page_setup.fitToWidth, ws.page_setup.fitToHeight) == (1, 0)


def test_data_rows_read_back_as_the_records(demo_wb, demo_records):
    assert read_records(demo_wb) == demo_records


def test_formula_cells_match_the_sheets_and_the_engine(cfg, demo_wb, demo_result):
    cells = formula_cells(cfg, demo_result)
    assert len(cells) == 30
    for cell in cells:
        assert demo_wb[cell.sheet][cell.ref].value == cell.formula, cell
    by_ref = {(cell.sheet, cell.ref): cell for cell in cells}
    assert by_ref[("Branches", "D16")].expected == demo_result.chain_value(W38, "revenue")
    assert by_ref[("Branches", "E16")].expected == demo_result.chain_value(W37, "revenue")
    assert by_ref[("Products", "C10")].expected == pytest.approx(1.0)
    for cell in cells:
        match = re.fullmatch(r"=SUM\(([A-Z]+\d+):([A-Z]+\d+)\)", cell.formula)
        if match is None:
            continue
        values = [
            item.value
            for row in demo_wb[cell.sheet][f"{match[1]}:{match[2]}"]
            for item in row
            if isinstance(item.value, (int, float))
        ]
        assert math.fsum(values) == pytest.approx(cell.expected, rel=1e-9), cell


def test_number_formats(demo_wb):
    ws = demo_wb["Branches"]
    assert ws["D4"].number_format == '"€"#,##0'
    assert ws["F4"].number_format == "+0.0%;-0.0%;0.0%"
    assert ws["H4"].number_format == '"€"#,##0.00'
    assert ws["J4"].number_format == "0.0%"
    assert ws["K4"].number_format == "#,##0.0"
    assert ws["P4"].number_format == "+0;-0;0"
    assert demo_wb["Products"]["E4"].number_format == "+0.0%;-0.0%;0.0%"


def test_a_branch_without_a_return_keeps_its_row(cfg, demo_ctx):
    records = [
        record for record in demo_ctx.records if not (record.branch_code == "CL-07" and record.week == W38)
    ]
    result = compute(records, cfg, W38)
    ctx = replace(demo_ctx, records=records, result=result, summary=summarise(result, cfg))
    ws = build(ctx)["Branches"]
    assert ws["A10"].value == "CL-07" and ws["O10"].value == "no return"
    assert ws["D10"].value is None
    assert close(ws["E10"].value, result.branch_value(W37, "CL-07", "revenue"))
    assert ws["G27"].value == 11
