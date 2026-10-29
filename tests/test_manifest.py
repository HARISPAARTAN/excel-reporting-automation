import json

from buildreport.manifest import KEYS, Output, build_manifest, ci_info, dumps

VERSIONS = {
    "python": "3.13.0",
    "platform": "Linux",
    "openpyxl": "3.1.5",
    "pydantic": "2.0",
    "PyYAML": "6.0",
    "click": "8.2.0",
}
CI_ENV = {
    "GITHUB_SERVER_URL": "https://github.com",
    "GITHUB_REPOSITORY": "HARISPAARTAN/excel-reporting-automation",
    "GITHUB_RUN_ID": "1234567890",
}


def make(demo_ctx, status="built", exit_code=0, outputs=None, env=None, summary="ctx"):
    return build_manifest(
        status=status,
        exit_code=exit_code,
        cfg=demo_ctx.cfg,
        period=demo_ctx.result.period,
        timestamp=demo_ctx.timestamp,
        strict=False,
        notify="dry-run",
        resolution=demo_ctx.resolution,
        summary=demo_ctx.summary if summary == "ctx" else summary,
        outputs=outputs if outputs is not None else [Output.of("report.xlsx", b"x" * 10)],
        env=env or {},
        versions=VERSIONS,
    )


def test_keys_follow_the_spec_order(demo_ctx):
    manifest = make(demo_ctx)
    assert list(manifest) == [key for key in KEYS if key != "ci"]
    assert list(make(demo_ctx, env=CI_ENV))[-1] == "ci"
    assert KEYS == (
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


def test_run_facts(demo_ctx):
    manifest = make(demo_ctx)
    assert manifest["schema"] == 1 and manifest["status"] == "built" and manifest["exit_code"] == 0
    assert manifest["tool"] == {"name": "build-report", "version": "0.1.0"}
    assert manifest["environment"] == VERSIONS
    assert (manifest["period"], manifest["period_start"], manifest["period_end"]) == (
        "2025-W38",
        "2025-09-15",
        "2025-09-21",
    )
    assert manifest["window"] == [f"2025-W{number}" for number in range(31, 39)]
    assert manifest["generated_at"] == "2025-09-22T06:00:00Z"
    assert manifest["timestamp_source"] == "SOURCE_DATE_EPOCH"
    assert manifest["config"]["sha256"] == demo_ctx.cfg.sha256
    assert manifest["strict"] is False and manifest["notify"] == "dry-run"


def test_inputs_reporting_and_findings(demo_ctx):
    manifest = make(demo_ctx)
    assert len(manifest["inputs"]) == 96
    assert list(manifest["inputs"][0]) == [
        "file",
        "bytes",
        "sha256",
        "branch",
        "week",
        "submitted_at",
        "status",
    ]
    reporting = {item["week"]: item["reporting"] for item in manifest["branches_reporting"]}
    assert reporting["2025-W36"] == 11 and reporting["2025-W38"] == 12
    assert all(item["expected"] == 12 for item in manifest["branches_reporting"])
    assert [item["code"] for item in manifest["findings"]] == [
        item.code for item in demo_ctx.resolution.findings
    ]
    assert {item["severity"] for item in manifest["findings"]} == {"warning"}


def test_kpis_ranking_and_thresholds(demo_ctx):
    manifest = make(demo_ctx)
    assert list(manifest["kpis"]) == list(demo_ctx.cfg.model.summary_kpis)
    for kpi in demo_ctx.summary.kpis:
        entry = manifest["kpis"][kpi.key]
        assert (entry["value"], entry["previous"], entry["change"], entry["change_type"]) == (
            kpi.value,
            kpi.previous,
            kpi.change,
            kpi.change_type,
        )
        assert entry["label"] == kpi.label and entry["format"] == kpi.format and entry["better"] == kpi.better
    assert len(manifest["ranking"]) == 12
    assert list(manifest["ranking"][0]) == [
        "rank",
        "code",
        "name",
        "revenue",
        "change",
        "waste_pct",
        "labour_pct",
    ]
    assert [item["rank"] for item in manifest["ranking"]] == list(range(1, 13))
    hits = {item["metric"]: item for item in manifest["above_threshold"]}
    assert set(hits) == {"waste_pct", "labour_pct"}
    assert (
        hits["waste_pct"]["op"] == ">"
        and hits["waste_pct"]["value"] == 0.06
        and hits["waste_pct"]["style"] == "bad"
    )


def test_outputs_and_ci(demo_ctx):
    output = Output.of("Cedarline_Weekly_Report_2025-W38.xlsx", b"abc")
    assert output.as_dict() == {
        "file": "Cedarline_Weekly_Report_2025-W38.xlsx",
        "bytes": 3,
        "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    }
    assert make(demo_ctx, outputs=[output])["outputs"] == [output.as_dict()]
    assert ci_info(CI_ENV) == {
        "run_url": "https://github.com/HARISPAARTAN/excel-reporting-automation/actions/runs/1234567890"
    }
    assert ci_info({**CI_ENV, "GITHUB_RUN_ID": ""}) is None
    assert ci_info({}) is None


def test_blocked_manifest_has_no_figures(demo_ctx):
    manifest = make(demo_ctx, status="blocked", exit_code=3, outputs=[], summary=None)
    assert manifest["status"] == "blocked" and manifest["exit_code"] == 3
    assert manifest["kpis"] == {} and manifest["ranking"] == [] and manifest["above_threshold"] == []
    assert manifest["outputs"] == [] and len(manifest["inputs"]) == 96


def test_dumps_is_utf8_lf_and_round_trips(demo_ctx):
    manifest = make(demo_ctx)
    data = dumps(manifest)
    assert data.endswith(b"}\n") and b"\r\n" not in data
    assert data.startswith(b'{\n  "schema": 1,\n  "status": "built",')
    assert json.loads(data.decode("utf-8")) == manifest
