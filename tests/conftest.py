"""Shared fixtures. Imports from buildreport happen inside the fixtures, so this file works before the modules exist."""

from __future__ import annotations

import importlib.util
import io
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
EPOCH = "1758520800"  # 2025-09-22 06:00 UTC, the Monday after the demo week 2025-W38
STEM = "Cedarline_Weekly_Report_2025-W38"


def load_tool(name: str) -> ModuleType:
    """Import tools/<name>.py (the tools folder is not a package)."""
    path = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"tool_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def tool():
    return load_tool


@pytest.fixture(scope="session")
def cfg():
    from buildreport.config import load_config

    return load_config(ROOT / "report.yaml")


@pytest.fixture(scope="session")
def demo_dir() -> Path:
    return ROOT / "data" / "incoming"


@pytest.fixture(scope="session")
def demo_resolution(cfg, demo_dir):
    from buildreport.discover import discover
    from buildreport.isoweek import IsoWeek, window
    from buildreport.resolve import resolve
    from buildreport.template import read_return

    period = IsoWeek(2025, 38)
    results = [read_return(source, cfg) for source in discover(demo_dir, cfg.model.input.file_pattern)]
    return resolve(results, cfg, window(period, cfg.model.trend_weeks), period)


@pytest.fixture(scope="session")
def demo_records(cfg, demo_resolution):
    from buildreport.resolve import to_records

    return to_records(demo_resolution.returns, cfg)


@pytest.fixture(scope="session")
def demo_result(cfg, demo_records):
    from buildreport.isoweek import IsoWeek
    from buildreport.metrics import compute

    return compute(demo_records, cfg, IsoWeek(2025, 38))


@pytest.fixture(scope="session")
def demo_timestamp():
    from buildreport.reproducible import run_timestamp

    return run_timestamp({"SOURCE_DATE_EPOCH": EPOCH})


@pytest.fixture(scope="session")
def demo_ctx(cfg, demo_resolution, demo_records, demo_result, demo_timestamp):
    from buildreport.metrics import summarise
    from buildreport.workbook import BuildContext

    return BuildContext(
        cfg=cfg,
        result=demo_result,
        summary=summarise(demo_result, cfg),
        resolution=demo_resolution,
        records=demo_records,
        timestamp=demo_timestamp,
        strict=False,
        input_dir="data/incoming",
    )


@pytest.fixture(scope="session")
def demo_workbook_bytes(demo_ctx) -> bytes:
    from buildreport.workbook import render_bytes

    return render_bytes(demo_ctx)


@pytest.fixture()
def demo_wb(demo_workbook_bytes):
    from openpyxl import load_workbook

    return load_workbook(io.BytesIO(demo_workbook_bytes))


@pytest.fixture(scope="session")
def run_cli():
    """Invoke build-report in-process with click's CliRunner and the demo timestamp."""
    from click.testing import CliRunner

    from buildreport.cli import cli

    def invoke(args, env=None):
        merged = {
            "SOURCE_DATE_EPOCH": EPOCH,
            "GITHUB_SERVER_URL": None,
            "GITHUB_REPOSITORY": None,
            "GITHUB_RUN_ID": None,
            "BUILD_REPORT_SMTP_HOST": None,
        }
        merged.update(env or {})
        return CliRunner().invoke(cli, [str(arg) for arg in args], env=merged, catch_exceptions=False)

    return invoke


@pytest.fixture(scope="session")
def demo_run(tmp_path_factory, run_cli, demo_dir):
    """The demo report built once per session with --notify dry-run."""
    out = tmp_path_factory.mktemp("demo-run")
    result = run_cli(
        [
            "run",
            "--period",
            "2025-W38",
            "--input",
            demo_dir,
            "--out",
            out,
            "--config",
            ROOT / "report.yaml",
            "--notify",
            "dry-run",
        ]
    )
    assert result.exit_code == 0, result.output
    return {
        "dir": out,
        "xlsx": out / f"{STEM}.xlsx",
        "eml": out / f"{STEM}.eml",
        "manifest": out / f"{STEM}.manifest.json",
        "result": result,
    }


@pytest.fixture(scope="session")
def base_set(tmp_path_factory, cfg) -> Path:
    """Eight weeks (2025-W31 to W38) of twelve files without deviations."""
    from buildreport.fixtures import generate, write_fixtures
    from buildreport.isoweek import IsoWeek

    out = tmp_path_factory.mktemp("base-set")
    write_fixtures(generate(cfg, IsoWeek(2025, 38), 8, deviations="none"), out)
    return out


@pytest.fixture()
def scenario(tmp_path, base_set) -> Path:
    """A private copy of the base set that a test may change."""
    target = tmp_path / "incoming"
    shutil.copytree(base_set, target)
    return target
