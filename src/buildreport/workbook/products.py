"""Sheet Products: product groups this week with a total row, and the revenue mix by branch."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import column_index_from_string, coordinate_from_string

from buildreport.config import Config
from buildreport.expr import change_excel
from buildreport.metrics import MetricsResult, change
from buildreport.workbook import styles
from buildreport.workbook.styles import FormulaCell

if TYPE_CHECKING:
    from buildreport.workbook import BuildContext

SHEET = "Products"
HEADERS = (
    "Product group",
    "Revenue",
    "Share of revenue",
    "Revenue last week",
    "WoW",
    "Units sold",
    "Waste EUR",
    "Waste %",
)
METRIC_COLUMNS = {"revenue": "B", "units_sold": "F", "waste_eur": "G", "waste_pct": "H"}
MIX_TITLE = "Revenue mix by branch (share of branch revenue)"
WIDTHS = {"A": 26, "B": 13, "C": 13, "D": 14, "E": 13, "F": 13, "G": 13, "H": 12}


@dataclass(frozen=True)
class Layout:
    first: int
    last: int
    total: int
    mix_title: int
    mix_header: int
    mix_first: int
    mix_last: int
    last_group_column: str
    mix_total_column: str


def layout(cfg: Config) -> Layout:
    groups = len(cfg.product_groups)
    last = 3 + groups
    total = last + 1
    return Layout(
        first=4,
        last=last,
        total=total,
        mix_title=total + 2,
        mix_header=total + 3,
        mix_first=total + 4,
        mix_last=total + 3 + len(cfg.branches),
        last_group_column=get_column_letter(1 + groups),
        mix_total_column=get_column_letter(2 + groups),
    )


def _position(ref: str) -> tuple[int, int]:
    column, row = coordinate_from_string(ref)
    return row, column_index_from_string(column)


def total_cells(cfg: Config, result: MetricsResult) -> list[FormulaCell]:
    """Row 10 (SUM, share total, change, waste %) and the mix totals in the last mix column."""
    lay = layout(cfg)
    row = lay.total
    period, previous = result.period, result.previous

    def ref(name: str) -> str:
        return f"{METRIC_COLUMNS[name]}{row}"

    cells = []
    for key, column in METRIC_COLUMNS.items():
        formula = styles.metric_formula(cfg.metrics[key], column, lay.first, lay.last, ref)
        if formula is not None:
            cells.append(FormulaCell(SHEET, f"{column}{row}", formula, result.chain_value(period, key)))
    shares = [result.share.get(group) for group in cfg.product_groups]
    share_total = math.fsum(value for value in shares if value is not None)
    cells.append(FormulaCell(SHEET, f"C{row}", f"=SUM(C{lay.first}:C{lay.last})", share_total))
    kind = cfg.metric("revenue").change
    current, before = result.chain_value(period, "revenue"), result.chain_value(previous, "revenue")
    cells.append(FormulaCell(SHEET, f"D{row}", f"=SUM(D{lay.first}:D{lay.last})", before))
    cells.append(
        FormulaCell(
            SHEET, f"E{row}", "=" + change_excel(f"B{row}", f"D{row}", kind), change(current, before, kind)
        )
    )
    for mix_row, branch in enumerate(cfg.branches, start=lay.mix_first):
        parts = [result.mix.get((branch.code, group)) for group in cfg.product_groups]
        cells.append(
            FormulaCell(
                SHEET,
                f"{lay.mix_total_column}{mix_row}",
                f"=SUM(B{mix_row}:{lay.last_group_column}{mix_row})",
                math.fsum(value for value in parts if value is not None),
            )
        )
    return sorted(cells, key=lambda cell: _position(cell.ref))


def write(ws: Any, ctx: BuildContext) -> None:
    cfg, result = ctx.cfg, ctx.result
    period, previous = result.period, result.previous
    lay = layout(cfg)
    revenue = cfg.metric("revenue")
    eur = styles.NUMBER_FORMATS[revenue.format]
    pct = styles.NUMBER_FORMATS["pct1"]
    styles.title(ws, "A1", f"Product groups · week {period}")
    styles.header(ws, 3, 1, HEADERS)
    for row, group in enumerate(cfg.product_groups, start=lay.first):
        current = result.group_value(period, group, "revenue")
        before = result.group_value(previous, group, "revenue")
        ws.cell(row=row, column=1, value=group)
        styles.put(ws, row, 2, current, eur)
        styles.put(ws, row, 3, result.share.get(group), pct)
        styles.put(ws, row, 4, before, eur)
        styles.put(ws, row, 5, change(current, before, revenue.change), styles.CHANGE_FORMATS[revenue.change])
        styles.put(
            ws,
            row,
            6,
            result.group_value(period, group, "units_sold"),
            styles.NUMBER_FORMATS[cfg.metric("units_sold").format],
        )
        styles.put(
            ws,
            row,
            7,
            result.group_value(period, group, "waste_eur"),
            styles.NUMBER_FORMATS[cfg.metric("waste_eur").format],
        )
        styles.put(
            ws,
            row,
            8,
            result.group_value(period, group, "waste_pct"),
            styles.NUMBER_FORMATS[cfg.metric("waste_pct").format],
        )

    ws.cell(row=lay.total, column=1, value="Total")
    total_formats = {
        "B": eur,
        "C": pct,
        "D": eur,
        "E": styles.CHANGE_FORMATS[revenue.change],
        "F": styles.NUMBER_FORMATS[cfg.metric("units_sold").format],
        "G": styles.NUMBER_FORMATS[cfg.metric("waste_eur").format],
        "H": styles.NUMBER_FORMATS[cfg.metric("waste_pct").format],
    }
    for cell in total_cells(cfg, result):
        target = ws[cell.ref]
        target.value = cell.formula
        row_number, _ = _position(cell.ref)
        target.number_format = (
            total_formats[cell.ref.rstrip("0123456789")] if row_number == lay.total else pct
        )
    styles.total_row(ws, lay.total, 1, len(HEADERS))

    ws.cell(row=lay.mix_title, column=1, value=MIX_TITLE).font = styles.BOLD_FONT
    styles.header(ws, lay.mix_header, 1, ["Branch", *cfg.product_groups, "Total"])
    for row, branch in enumerate(cfg.branches, start=lay.mix_first):
        ws.cell(row=row, column=1, value=branch.name)
        for column, group in enumerate(cfg.product_groups, start=2):
            styles.put(ws, row, column, result.mix.get((branch.code, group)), pct)

    ws.conditional_formatting.add(
        f"B{lay.mix_first}:{lay.last_group_column}{lay.mix_last}",
        ColorScaleRule(start_type="min", start_color="FFFFFF", end_type="max", end_color=styles.ACCENT),
    )
    for threshold in cfg.model.thresholds:
        if threshold.metric in METRIC_COLUMNS:
            column = METRIC_COLUMNS[threshold.metric]
            ws.conditional_formatting.add(
                f"{column}{lay.first}:{column}{lay.last}",
                styles.threshold_rule(threshold.op, threshold.value, threshold.style),
            )
    styles.widths(ws, WIDTHS)
    ws.row_dimensions[3].height = 30
    ws.row_dimensions[lay.mix_header].height = 45
    ws.freeze_panes = "B4"
    styles.page(ws, period, landscape=True, fit_height=1)
