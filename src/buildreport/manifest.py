"""Run manifest (spec 6.5): one JSON file per run, keys in spec order; the Pages site reads only this file."""

from __future__ import annotations

import builtins
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from buildreport import TOOL_NAME, __version__
from buildreport.config import Config
from buildreport.isoweek import IsoWeek, window
from buildreport.metrics import Summary
from buildreport.reproducible import RunTimestamp, shown_path
from buildreport.resolve import Resolution

SCHEMA = 1
KEYS = (
    "schema",
    "status",
    "exit_code",
    "tool",
    "environment",
    "period",
    "period_start",
    "period_end",
    "window",
    "generated_at",
    "timestamp_source",
    "config",
    "strict",
    "notify",
    "inputs",
    "branches_reporting",
    "findings",
    "kpis",
    "ranking",
    "above_threshold",
    "outputs",
    "ci",
)


@dataclass(frozen=True)
class Output:
    file: str
    bytes: int
    sha256: str

    @classmethod
    def of(cls, name: str, data: builtins.bytes) -> Output:
        return cls(name, len(data), hashlib.sha256(data).hexdigest())

    def as_dict(self) -> dict[str, object]:
        return {"file": self.file, "bytes": self.bytes, "sha256": self.sha256}


def ci_info(env: Mapping[str, str]) -> dict[str, str] | None:
    """The Actions run link, present only when all three GITHUB_* variables are set."""
    server = env.get("GITHUB_SERVER_URL", "").strip().rstrip("/")
    repository = env.get("GITHUB_REPOSITORY", "").strip()
    run_id = env.get("GITHUB_RUN_ID", "").strip()
    if not (server and repository and run_id):
        return None
    return {"run_url": f"{server}/{repository}/actions/runs/{run_id}"}


def _figures(summary: Summary | None) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    if summary is None:
        return {}, [], []
    kpis = {
        kpi.key: {
            "label": kpi.label,
            "format": kpi.format,
            "value": kpi.value,
            "previous": kpi.previous,
            "change": kpi.change,
            "change_type": kpi.change_type,
            "better": kpi.better,
        }
        for kpi in summary.kpis
    }
    ranking = [
        {
            "rank": row.rank,
            "code": row.code,
            "name": row.name,
            "revenue": row.revenue,
            "change": row.change,
            "waste_pct": row.waste_pct,
            "labour_pct": row.labour_pct,
        }
        for row in summary.ranking
    ]
    above = [
        {
            "metric": hit.metric,
            "label": hit.label,
            "op": hit.op,
            "value": hit.value,
            "style": hit.style,
            "format": hit.format,
            "branches": list(hit.branches),
        }
        for hit in summary.above_threshold
    ]
    return kpis, ranking, above


def build_manifest(
    *,
    status: Literal["built", "blocked"],
    exit_code: int,
    cfg: Config,
    period: IsoWeek,
    timestamp: RunTimestamp,
    strict: bool,
    notify: str,
    resolution: Resolution,
    summary: Summary | None,
    outputs: Sequence[Output],
    env: Mapping[str, str],
    versions: Mapping[str, str],
) -> dict[str, Any]:
    weeks = window(period, cfg.model.trend_weeks)
    kpis, ranking, above = _figures(summary)
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "exit_code": exit_code,
        "tool": {"name": TOOL_NAME, "version": __version__},
        "environment": dict(versions),
        "period": str(period),
        "period_start": period.monday.isoformat(),
        "period_end": period.sunday.isoformat(),
        "window": [str(week) for week in weeks],
        "generated_at": timestamp.iso,
        "timestamp_source": timestamp.source,
        "config": {"path": shown_path(cfg.path), "sha256": cfg.sha256},
        "strict": strict,
        "notify": notify,
        "inputs": [item.as_dict() for item in resolution.inputs],
        "branches_reporting": [
            {"week": str(week), "reporting": resolution.reporting(week), "expected": len(cfg.branches)}
            for week in weeks
        ],
        "findings": [item.as_dict() for item in resolution.findings],
        "kpis": kpis,
        "ranking": ranking,
        "above_threshold": above,
        "outputs": [item.as_dict() for item in outputs],
    }
    ci = ci_info(env)
    if ci is not None:
        manifest["ci"] = ci
    return manifest


def dumps(manifest: Mapping[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
