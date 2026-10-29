import io
import zipfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

import pytest

from buildreport.findings import counts
from buildreport.isoweek import IsoWeek
from buildreport.metrics import compute, summarise
from buildreport.reproducible import shown_path
from buildreport.workbook import SHEETS, build, formula_cells

W38 = IsoWeek(2025, 38)
C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
XDR = "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}"
FOOTER = "Cedarline Bakeries · weekly report 2025-W38 · page &P of &N"
KPI_LABELS = [
    "Revenue",
    "Transactions",
    "Average basket",
    "Waste %",
    "Labour % of revenue",
    "Revenue per labour hour",
    "Labour hours",
]


def close(actual, expected):
    return actual == pytest.approx(expected, rel=1e-12)


def plain(text):
    return text.replace("$", "").replace("'", "").split("!")[-1]


def rules(ws):
    found = set()
    for formatting in ws.conditional_formatting:
        for rule in formatting.rules:
            found.add((str(formatting.sqref), rule.type, rule.operator, tuple(rule.formula or ())))
    return found


def chart_xml(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = sorted(name for name in archive.namelist() if name.startswith("xl/charts/chart"))
        return [ElementTree.fromstring(archive.read(name)) for name in names]


def kind(root):
    plot = root.find(f"{C}chart/{C}plotArea")
    return next(child.tag.removeprefix(C) for child in plot if child.tag.endswith("Chart"))


def test_sheet_order_and_properties(demo_wb):
    assert demo_wb.sheetnames == list(SHEETS) == ["Summary", "Branches", "Products", "Data", "Run info"]
    assert demo_wb.active.title == "Summary"
    props = demo_wb.properties
    assert props.title == "Cedarline weekly report 2025-W38"
    assert props.creator == "build-report 0.1.0"
    assert props.created.replace(tzinfo=None) == datetime(2025, 9, 22, 6, 0)
    assert props.modified.replace(tzinfo=None) == datetime(2025, 9, 22, 6, 0)


def test_summary_title_and_subtitle(demo_wb):
    ws = demo_wb["Summary"]
    assert ws["A1"].value == "Cedarline Bakeries · Weekly report 2025-W38"
    assert ws["A1"].font.sz == 16 and ws["A1"].font.b
    assert ws["A2"].value == (
        "15 to 21 September 2025 · 12 branches reported, 12 expected · generated 2025-09-22 06:00 UTC · build-report 0.1.0"
    )


def test_summary_key_figures(demo_wb, demo_ctx):
    ws = demo_wb["Summary"]
    assert [ws.cell(row=4, column=column).value for column in range(2, 6)] == [
        "Metric",
        "This week",
        "Last week",
        "Change",
    ]
    assert [ws[f"B{row}"].value for row in range(5, 12)] == KPI_LABELS
    for row, kpi in zip(range(5, 12), demo_ctx.summary.kpis, strict=True):
        assert close(ws[f"C{row}"].value, kpi.value)
        assert close(ws[f"D{row}"].value, kpi.previous)
        assert close(ws[f"E{row}"].value, kpi.change)
    assert ws["C5"].number_format == '"€"#,##0'
    assert ws["C7"].number_format == '"€"#,##0.00'
    assert ws["C8"].number_format == "0.0%"
    assert ws["E5"].number_format == "+0.0%;-0.0%;0.0%"
    assert ws["E8"].number_format == '+0.0" pp";-0.0" pp";0.0" pp"'


def test_summary_ranking(demo_wb, demo_ctx):
    ws = demo_wb["Summary"]
    assert [ws.cell(row=4, column=column).value for column in range(7, 13)] == [
        "Rank",
        "Branch",
        "Revenue",
        "WoW",
        "Waste %",
        "Labour %",
    ]
    assert [ws[f"G{row}"].value for row in range(5, 17)] == list(range(1, 13))
    for row, entry in zip(range(5, 17), demo_ctx.summary.ranking, strict=True):
        assert ws[f"H{row}"].value == entry.name
        assert close(ws[f"I{row}"].value, entry.revenue)
        assert close(ws[f"K{row}"].value, entry.waste_pct)
    revenues = [ws[f"I{row}"].value for row in range(5, 17)]
    assert revenues == sorted(revenues, reverse=True)


def test_summary_data_notes(demo_wb, demo_ctx):
    ws = demo_wb["Summary"]
    assert ws["B13"].value == "Data notes"
    assert ws["B14"].value == "Branches reported: 12 this week, 12 last week, 12 expected."
    assert ws["B15"].value == "0 errors, 6 warnings; see sheet Run info."
    hits = {hit.metric: hit for hit in demo_ctx.summary.above_threshold}
    waste = ", ".join(hits["waste_pct"].names) or "none"
    labour = ", ".join(hits["labour_pct"].names) or "none"
    assert ws["B16"].value == f"Waste % above 6.0%: {waste}; Labour % of revenue above 32.0%: {labour}"
    assert "B16:E16" in {str(item) for item in ws.merged_cells.ranges}
    assert ws["B16"].alignment.wrap_text
    assert ws["B17"].value is None
    assert ws["B18"].value == "Charts"


def test_summary_page_setup(demo_wb):
    ws = demo_wb["Summary"]
    assert plain(ws.print_area) == "A1:L36"
    assert ws.page_setup.orientation == "landscape" and ws.page_setup.paperSize == 9
    assert (ws.page_setup.fitToWidth, ws.page_setup.fitToHeight) == (1, 1)
    assert ws.print_options.horizontalCentered and ws.print_options.verticalCentered
    assert ws.freeze_panes is None
    assert ws.sheet_properties.tabColor.rgb[-6:] == "F2A93B"
    assert ws.sheet_view.showGridLines is False
    assert ws.oddFooter.center.text == FOOTER
    widths = {column: ws.column_dimensions[column].width for column in "ABCDEFGHIJKL"}
    assert widths == {
        "A": 2,
        "B": 26,
        "C": 14,
        "D": 14,
        "E": 12,
        "F": 3,
        "G": 7,
        "H": 18,
        "I": 14,
        "J": 11,
        "K": 10,
        "L": 10,
    }


def test_summary_conditional_formatting(demo_wb):
    found = rules(demo_wb["Summary"])
    assert ("C8", "cellIs", "greaterThan", ("0.06",)) in found
    assert ("C9", "cellIs", "greaterThan", ("0.32",)) in found
    for cell in ("E5", "E6", "E7", "E10"):
        assert (cell, "cellIs", "greaterThan", ("0",)) in found and (
            cell,
            "cellIs",
            "lessThan",
            ("0",),
        ) in found
    for cell in ("E8", "E9"):
        assert (cell, "cellIs", "greaterThan", ("0",)) in found and (
            cell,
            "cellIs",
            "lessThan",
            ("0",),
        ) in found
    assert not any(item[0] == "E11" for item in found)
    assert ("J5:J16", "cellIs", "greaterThan", ("0",)) in found
    assert ("K5:K16", "cellIs", "greaterThan", ("0.06",)) in found
    assert ("L5:L16", "cellIs", "greaterThan", ("0.32",)) in found
    assert len(found) == 18


def test_change_colours_follow_the_better_direction(demo_wb):
    colours = {}
    for formatting in demo_wb["Summary"].conditional_formatting:
        for rule in formatting.rules:
            if tuple(rule.formula or ()) == ("0",):
                colours[(str(formatting.sqref), rule.operator)] = rule.dxf.font.color.rgb[-6:]
    assert colours[("E5", "greaterThan")] == "15803D" and colours[("E5", "lessThan")] == "B91C1C"
    assert colours[("E8", "greaterThan")] == "B91C1C" and colours[("E8", "lessThan")] == "15803D"


def test_three_charts_with_their_references(demo_wb):
    charts = demo_wb["Summary"]._charts
    assert [type(chart).__name__ for chart in charts] == ["BarChart", "LineChart", "DoughnutChart"]
    refs = [
        (chart.series[0].val.numRef.f.replace("'", ""), chart.series[0].cat.strRef.f.replace("'", ""))
        for chart in charts
    ]
    assert refs == [
        ("Summary!$I$5:$I$16", "Summary!$H$5:$H$16"),
        ("Branches!$C$20:$C$27", "Branches!$A$20:$A$27"),
        ("Products!$B$4:$B$9", "Products!$A$4:$A$9"),
    ]


def test_chart_xml_options(demo_workbook_bytes):
    roots = {kind(root): root for root in chart_xml(demo_workbook_bytes)}
    assert set(roots) == {"barChart", "lineChart", "doughnutChart"}
    titles = {key: "".join(node.text or "" for node in root.iter(f"{A}t")) for key, root in roots.items()}
    assert titles == {
        "barChart": "Revenue by branch, this week",
        "lineChart": "Chain revenue, last 8 weeks",
        "doughnutChart": "Revenue mix by product group",
    }
    bar = roots["barChart"]
    assert bar.find(f".//{C}barDir").get("val") == "bar"
    assert bar.find(f".//{C}grouping").get("val") == "clustered"
    assert bar.find(f".//{C}catAx/{C}scaling/{C}orientation").get("val") == "maxMin"
    assert bar.find(f".//{C}valAx/{C}numFmt").get("formatCode") == '"€"#,##0'
    assert bar.find(f"{C}chart/{C}legend") is None
    line = roots["lineChart"]
    assert line.find(f".//{C}ser/{C}marker/{C}symbol").get("val") == "circle"
    assert line.find(f"{C}chart/{C}legend") is None
    for root in (bar, line):
        axes = root.findall(f".//{C}catAx") + root.findall(f".//{C}valAx")
        assert len(axes) == 2
        assert all(axis.find(f"{C}delete").get("val") in {"0", "false"} for axis in axes)
    doughnut = roots["doughnutChart"]
    assert doughnut.find(f".//{C}holeSize").get("val") == "55"
    assert doughnut.find(f"{C}chart/{C}legend/{C}legendPos").get("val") == "r"
    assert doughnut.find(f".//{C}dLbls/{C}showPercent").get("val") in {"1", "true"}


def test_chart_anchors_and_sizes(demo_workbook_bytes):
    with zipfile.ZipFile(io.BytesIO(demo_workbook_bytes)) as archive:
        drawing = ElementTree.fromstring(archive.read("xl/drawings/drawing1.xml"))
    anchors = []
    for anchor in drawing.findall(f"{XDR}oneCellAnchor"):
        start = anchor.find(f"{XDR}from")
        ext = anchor.find(f"{XDR}ext")
        anchors.append(
            (
                int(start.find(f"{XDR}col").text),
                int(start.find(f"{XDR}row").text),
                int(ext.get("cx")),
                int(ext.get("cy")),
            )
        )
    assert anchors == [(1, 18, 4500000, 3240000), (6, 18, 4500000, 1584000), (6, 27, 4500000, 1584000)]


def test_run_info_key_values(cfg, demo_wb):
    ws = demo_wb["Run info"]
    assert ws["A1"].value == "Run info"
    assert [ws[f"A{row}"].value for row in range(3, 17)] == [
        "Period",
        "Period dates",
        "Generated at",
        "Timestamp source",
        "Tool",
        "Python",
        "openpyxl",
        "pydantic",
        "PyYAML",
        "Configuration file",
        "Configuration SHA-256",
        "Strict mode",
        "Input folder",
        "Thresholds",
    ]
    values = {ws[f"A{row}"].value: ws[f"B{row}"].value for row in range(3, 17)}
    assert values["Period"] == "2025-W38"
    assert values["Period dates"] == "15 to 21 September 2025"
    assert values["Generated at"] == "2025-09-22T06:00:00Z"
    assert values["Timestamp source"] == "SOURCE_DATE_EPOCH"
    assert values["Tool"] == "build-report 0.1.0"
    assert values["openpyxl"] == "3.1.5"
    assert values["Configuration file"] == "report.yaml"
    assert values["Configuration SHA-256"] == cfg.sha256
    assert values["Strict mode"] == "no"
    assert values["Input folder"] == "data/incoming"
    assert values["Thresholds"] == "Waste % > 6.0% (bad); Labour % of revenue > 32.0% (warn)"


def test_run_info_shows_an_absolute_input_folder_relative_to_the_working_directory(cfg, demo_ctx):
    ctx = replace(demo_ctx, input_dir=str(cfg.path.parent / "data" / "incoming"))
    ws = build(ctx)["Run info"]
    values = {ws[f"A{row}"].value: ws[f"B{row}"].value for row in range(3, 17)}
    assert values["Input folder"] == "data/incoming"


def test_shown_path_keeps_only_the_name_outside_the_working_directory(tmp_path):
    assert shown_path(tmp_path / "exports" / "report.yaml") == "report.yaml"
    assert shown_path(tmp_path / "exports" / "incoming") == "incoming"
    assert shown_path(Path.cwd() / "data" / "incoming") == "data/incoming"


def test_run_info_inputs_and_findings(demo_wb, demo_ctx):
    ws = demo_wb["Run info"]
    assert ws["A18"].value == "Input files"
    assert [cell.value for cell in ws[19]][:7] == [
        "File",
        "Branch",
        "Week",
        "Status",
        "Submitted at",
        "Bytes",
        "SHA-256",
    ]
    rows = list(ws.iter_rows(min_row=20, max_row=115, max_col=7, values_only=True))
    assert len(rows) == 96 and rows[0][0] == "CL-01_2025-W31.xlsx"
    statuses = [row[3] for row in rows]
    assert statuses.count("used") == 95 and statuses.count("replaced") == 1
    assert ws["A116"].value is None
    assert ws["A117"].value == "Findings"
    assert [cell.value for cell in ws[118]][:4] == ["Severity", "Code", "File", "Message"]
    findings = list(ws.iter_rows(min_row=119, max_row=124, max_col=4, values_only=True))
    assert findings == [
        (item.severity, item.code, item.file or "-", item.message) for item in demo_ctx.resolution.findings
    ]
    assert ws["A125"].value is None
    found = rules(ws)
    assert ("A119:D124", "expression", None, ('$A119="error"',)) in found
    assert ("A119:D124", "expression", None, ('$A119="warning"',)) in found


def test_run_info_page_setup(demo_wb):
    ws = demo_wb["Run info"]
    assert ws.page_setup.orientation == "portrait"
    assert (ws.page_setup.fitToWidth, ws.page_setup.fitToHeight) == (1, 0)
    assert ws.freeze_panes is None
    assert ws.oddFooter.center.text == FOOTER
    assert all(demo_wb[name].page_setup.paperSize == 9 for name in SHEETS)
    assert [demo_wb[name].sheet_view.showGridLines for name in SHEETS] == [False, False, False, True, False]


def test_formulas_appear_only_in_total_cells(cfg, demo_wb, demo_result):
    found = {
        (ws.title, cell.coordinate)
        for ws in demo_wb.worksheets
        for row in ws.iter_rows()
        for cell in row
        if isinstance(cell.value, str) and cell.value.startswith("=")
    }
    assert found == {(cell.sheet, cell.ref) for cell in formula_cells(cfg, demo_result)}


def test_findings_count_matches_the_summary(demo_ctx):
    assert counts(demo_ctx.resolution.findings) == {"error": 0, "warning": 6}


def test_a_branch_missing_this_week_changes_the_notes(cfg, demo_ctx):
    records = [
        record for record in demo_ctx.records if not (record.branch_code == "CL-07" and record.week == W38)
    ]
    result = compute(records, cfg, W38)
    ctx = replace(demo_ctx, records=records, result=result, summary=summarise(result, cfg))
    ws = build(ctx)["Summary"]
    assert "11 branches reported, 12 expected" in ws["A2"].value
    assert ws["B14"].value == "Branches reported: 11 this week, 12 last week, 12 expected."
    assert ws["B17"].value == "Week-on-week figures compare 11 branches with 12."
    assert ws["G16"].value == "–" and ws["H16"].value == "Glenvarra" and ws["I16"].value is None
