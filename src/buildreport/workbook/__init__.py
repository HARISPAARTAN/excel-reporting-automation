"""The weekly report workbook (first version: Branches, Products and Data; Task 10 adds the rest)."""

from __future__ import annotations

from dataclasses import dataclass

from openpyxl import Workbook

from buildreport import __version__
from buildreport.config import Config
from buildreport.metrics import MetricsResult, Summary
from buildreport.reproducible import RunTimestamp, save_workbook_bytes
from buildreport.resolve import Record, Resolution
from buildreport.workbook import branches, data, products
from buildreport.workbook.styles import FormulaCell


@dataclass(frozen=True)
class BuildContext:
    cfg: Config
    result: MetricsResult
    summary: Summary
    resolution: Resolution
    records: list[Record]
    timestamp: RunTimestamp
    strict: bool
    input_dir: str


def build(ctx: BuildContext) -> Workbook:
    book = Workbook()
    sheet = book.active
    sheet.title = branches.SHEET
    branches.write(sheet, ctx)
    products.write(book.create_sheet(products.SHEET), ctx)
    data.write(book.create_sheet(data.SHEET), ctx)
    book.properties.title = f"Cedarline weekly report {ctx.result.period}"
    book.properties.creator = f"build-report {__version__}"
    return book


def formula_cells(cfg: Config, result: MetricsResult) -> list[FormulaCell]:
    return [*branches.total_cells(cfg, result), *products.total_cells(cfg, result)]


def render_bytes(ctx: BuildContext) -> bytes:
    return save_workbook_bytes(build(ctx), ctx.timestamp.value)
