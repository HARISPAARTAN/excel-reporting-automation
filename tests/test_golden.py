"""The demo KPIs against tests/golden/2025-W38.json (written once from a reviewed run with --write)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parent / "golden" / "2025-W38.json"


def golden_payload(summary, resolution) -> dict:
    return {
        "period": str(summary.period),
        "reporting": {
            "this_week": summary.reporting_now,
            "last_week": summary.reporting_previous,
            "expected": summary.expected,
        },
        "findings": [item.code for item in resolution.findings],
        "kpis": {
            kpi.key: {"value": kpi.value, "previous": kpi.previous, "change": kpi.change}
            for kpi in summary.kpis
        },
        "ranking": [row.code for row in summary.ranking],
        "above_threshold": {hit.metric: list(hit.branches) for hit in summary.above_threshold},
    }


def test_demo_kpis_equal_the_golden_file(demo_ctx):
    assert GOLDEN.is_file(), "review the first demo run, then run: uv run python tests/test_golden.py --write"
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = golden_payload(demo_ctx.summary, demo_ctx.resolution)
    assert {key: value for key, value in actual.items() if key != "kpis"} == {
        key: value for key, value in expected.items() if key != "kpis"
    }
    assert list(actual["kpis"]) == list(expected["kpis"])
    for key, entry in expected["kpis"].items():
        for field, value in entry.items():
            assert actual["kpis"][key][field] == pytest.approx(value, rel=1e-9), (key, field)


def _write() -> int:
    from buildreport.config import load_config
    from buildreport.discover import discover
    from buildreport.isoweek import IsoWeek, window
    from buildreport.metrics import compute, summarise
    from buildreport.resolve import resolve, to_records
    from buildreport.template import read_return

    root = GOLDEN.parents[2]
    cfg = load_config(root / "report.yaml")
    period = IsoWeek(2025, 38)
    results = [
        read_return(source, cfg)
        for source in discover(root / "data" / "incoming", cfg.model.input.file_pattern)
    ]
    resolution = resolve(results, cfg, window(period, cfg.model.trend_weeks), period)
    summary = summarise(compute(to_records(resolution.returns, cfg), cfg, period), cfg)
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    payload = golden_payload(summary, resolution)
    GOLDEN.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"wrote {GOLDEN.relative_to(root).as_posix()}")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: python tests/test_golden.py --write")
    raise SystemExit(_write())
