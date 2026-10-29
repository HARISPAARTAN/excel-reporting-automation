"""Helpers for tests that build small branch workbooks in tmp_path."""

from __future__ import annotations

import re
from pathlib import Path

from buildreport.discover import parse_name
from buildreport.fixtures import build_workbook, make_spec
from buildreport.isoweek import IsoWeek
from buildreport.template import read_return

W38 = IsoWeek(2025, 38)


def workbook(cfg, code="CL-03", week=W38):
    """A clean template workbook (version 3) for one branch and week."""
    return build_workbook(make_spec(cfg, code, week), cfg)


def save(book, folder: Path, name: str) -> Path:
    path = folder / name
    book.save(path)
    return path


def source(cfg, path: Path):
    return parse_name(path, re.compile(cfg.model.input.file_pattern))


def read(cfg, book, folder: Path, name: str = "CL-03_2025-W38.xlsx"):
    return read_return(source(cfg, save(book, folder, name)), cfg)


def codes(result) -> list[str]:
    return [item.code for item in result.findings]
