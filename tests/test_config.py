import copy
import hashlib
import re
from pathlib import Path

import pytest
import yaml

from buildreport.config import REQUIRED_METRICS, ConfigError, load_config
from buildreport.isoweek import IsoWeek

ROOT = Path(__file__).resolve().parents[1]
RAW = yaml.safe_load((ROOT / "report.yaml").read_text(encoding="utf-8"))
ORDER = ", ".join(REQUIRED_METRICS)


def write_variant(tmp_path, change):
    data = copy.deepcopy(RAW)
    change(data)
    path = tmp_path / "report.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def swap_metrics(data, first, second):
    """Exchange the positions of two metrics, keeping every definition as it is."""
    keys = list(data["metrics"])
    a, b = keys.index(first), keys.index(second)
    keys[a], keys[b] = keys[b], keys[a]
    data["metrics"] = {key: data["metrics"][key] for key in keys}


def extra_metric(label, expr="sum(waste_units)"):
    return {"label": label, "expr": expr, "format": "count", "change": "relative", "better": "lower"}


def test_committed_config_loads(cfg):
    assert cfg.model.client.name == "Cedarline Bakeries"
    assert cfg.branch_codes == tuple(f"CL-{number:02d}" for number in range(1, 13))
    assert cfg.branch("CL-07").name == "Glenvarra"
    assert cfg.branch("CL-13") is None
    assert tuple(cfg.metrics) == REQUIRED_METRICS
    assert cfg.model.summary_kpis[0] == "revenue" and len(cfg.model.summary_kpis) == 7
    assert re.fullmatch(r"[0-9a-f]{64}", cfg.sha256)
    assert cfg.model.notify.sender.address == "reporting@cedarline.example"


def test_measures_and_names(cfg):
    assert cfg.measures == (
        "net_sales_eur",
        "units_sold",
        "waste_units",
        "waste_eur",
        "labour_hours",
        "labour_cost_eur",
        "transactions",
    )
    assert cfg.measure_type("units_sold") == "count"
    assert cfg.measure_type("transactions") == "count"
    assert cfg.measure_type("labour_hours") == "hours"
    assert cfg.file_name(IsoWeek(2025, 38)) == "Cedarline_Weekly_Report_2025-W38.xlsx"
    assert cfg.stem(IsoWeek(2025, 38)) == "Cedarline_Weekly_Report_2025-W38"
    assert cfg.threshold("waste_pct").value == 0.06
    assert cfg.threshold("revenue") is None


def test_file_pattern_accepts_suffixes(cfg):
    pattern = re.compile(cfg.model.input.file_pattern)
    assert pattern.match("CL-10_2025-W37_resend.xlsx").group("branch", "week") == ("CL-10", "2025-W37")
    assert pattern.match("CL-03_2025-W38.xlsx")
    assert pattern.match("CL-03_2025-W38 copy.xlsx")
    assert not pattern.match("CL-3_2025-W38.xlsx")
    assert not pattern.match("CL-03_2025-W38.xls")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.update(colour="blue"), "Extra inputs are not permitted"),
        (
            lambda d: d["notify"]["from"].update(phone="n/a"),
            "notify.from.phone: Extra inputs are not permitted",
        ),
        (
            lambda d: d["template"]["cover"]["labels"].update(room="Room"),
            "template.cover.labels.room: Extra inputs are not permitted",
        ),
        (lambda d: d["input"].update(file_pattern=r"^CL-\d{2}.*\.xlsx$"), "named groups branch and week"),
        (
            lambda d: d["branches"].append({"code": "CL-01", "name": "Copy", "format": "Flagship"}),
            "branch codes must be unique",
        ),
        (lambda d: d["branches"][1].update(name="alderbrook"), "branches: duplicate name 'alderbrook'"),
        (
            lambda d: d["branches"].extend(
                {"code": f"CL-{number}", "name": f"Branch {number}", "format": "Flagship"}
                for number in (13, 14, 15)
            ),
            "branches: Tuple should have at most 14 items after validation, not 15",
        ),
        (lambda d: d["product_groups"].append("Bread"), "product_groups must be unique"),
        (
            lambda d: d["product_groups"].append("  cold   DRINKS and grocery "),
            "product_groups must be unique",
        ),
        (lambda d: d["roles"].append("Counter"), "roles must be unique"),
        (lambda d: d["roles"].append("supervisor"), "roles must be unique"),
        (
            lambda d: d["template"]["sales"]["columns"]["units_sold"].update(header="Net  Sales EUR"),
            "headers on sheet Sales must be unique",
        ),
        (
            lambda d: d["template"]["labour"]["columns"]["labour_hours"].update(header="role"),
            "headers on sheet Labour must be unique",
        ),
        (
            lambda d: d["template"]["cover"]["labels"].update(week="Branch code"),
            "template.cover.labels: duplicate label 'Branch code'",
        ),
        (
            lambda d: d["template"]["cover"]["labels"].update(submitted_by="submitted  AT"),
            "template.cover.labels: duplicate label 'submitted  AT'",
        ),
        (
            lambda d: d["template"]["labour"]["sheet"].update(name="Sales"),
            "template: duplicate sheet name or alias 'Sales'",
        ),
        (
            lambda d: d["template"]["cover"]["sheet"]["aliases"].append("LABOUR"),
            "template: duplicate sheet name or alias 'Labour'",
        ),
        (
            lambda d: d["template"]["sales"]["sheet"]["aliases"].append("Labor*"),
            "template: duplicate sheet name or alias 'Labor*'",
        ),
        (
            lambda d: d["metrics"].pop("units_sold"),
            "metrics must define units_sold (the sheet layout of v0.1.0 needs them)",
        ),
        (
            lambda d: [d["metrics"].pop(key) for key in ("waste_eur", "units_sold")],
            "metrics must define units_sold, waste_eur (the sheet layout of v0.1.0 needs them)",
        ),
        (
            lambda d: swap_metrics(d, "units_sold", "waste_eur"),
            f"metrics: required metrics must appear in the order {ORDER}",
        ),
        (
            lambda d: d["metrics"]["transactions"].update(label="Revenue"),
            "metrics: duplicate label 'Revenue'",
        ),
        (
            lambda d: d["metrics"]["labour_cost"].update(label=" labour   HOURS"),
            "metrics: duplicate label ' labour   HOURS'",
        ),
        (lambda d: d["metrics"]["revenue"].update(expr="sum(net_sales_eur) ** 2"), "is not allowed"),
        (lambda d: d["metrics"]["revenue"].update(expr="transactions * 2"), "must be defined above revenue"),
        (lambda d: d["output"].update(file_name="{period}_{client}.xlsx"), "{period} and no other field"),
        (lambda d: d["summary_kpis"].__setitem__(6, "profit"), "unknown metric profit"),
        (
            lambda d: d["summary_kpis"].append("units_sold"),
            "summary_kpis: Tuple should have at most 7 items after validation, not 8",
        ),
        (lambda d: d["thresholds"][0].update(op="=="), "thresholds.0.op"),
        (lambda d: d.update(trend_weeks=6), "trend_weeks"),
        (lambda d: d["metrics"]["revenue"].update(format="eur3"), "metrics.revenue.format"),
        (lambda d: d["template"]["sales"]["columns"]["units_sold"].update(type="date"), "units_sold.type"),
    ],
)
def test_invalid_configurations_fail(tmp_path, change, message):
    path = write_variant(tmp_path, change)
    with pytest.raises(ConfigError, match=re.escape(message)):
        load_config(path)


def test_extra_metrics_may_be_interleaved_or_appended(tmp_path):
    def change(data):
        metrics = {}
        for key, spec in data["metrics"].items():
            metrics[key] = spec
            if key == "revenue":
                metrics["waste_units_total"] = extra_metric("Waste units")
        metrics["waste_units_doubled"] = extra_metric("Waste units doubled", "waste_units_total * 2")
        data["metrics"] = metrics

    config = load_config(write_variant(tmp_path, change))
    assert tuple(config.metrics)[:3] == ("revenue", "waste_units_total", "transactions")
    assert tuple(config.metrics)[-1] == "waste_units_doubled"
    assert [key for key in config.metrics if key in REQUIRED_METRICS] == list(REQUIRED_METRICS)


REVENUE_AGAIN = (
    "  revenue: {label: Takings, expr: 'sum(net_sales_eur)', format: eur, change: relative, better: higher}\n"
)


@pytest.mark.parametrize(
    ("old", "new", "key", "anchor"),
    [
        ("metrics:\n", "metrics:\n" + REVENUE_AGAIN, "revenue", "  revenue:"),
        ("\nstrict: false\n", "\nstrict: false\nstrict: true\n", "strict", "strict:"),
        ("currency: EUR}", "currency: EUR, city: Cork}", "city", "client:"),
    ],
)
def test_duplicate_yaml_keys_fail(tmp_path, old, new, key, anchor):
    text = (ROOT / "report.yaml").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert text.count(old) == 1
    changed = text.replace(old, new)
    path = tmp_path / "report.yaml"
    path.write_text(changed, encoding="utf-8", newline="\n")
    # The key is reported where it repeats, which is the last line that starts with the anchor.
    line = max(number for number, row in enumerate(changed.splitlines(), 1) if row.startswith(anchor))
    with pytest.raises(ConfigError, match=re.escape(f"{path}: duplicate key {key!r} on line {line}")):
        load_config(path)


def test_unreadable_and_malformed_files(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "missing.yaml")
    broken = tmp_path / "broken.yaml"
    broken.write_text("version: [1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(broken)
    binary = tmp_path / "binary.yaml"
    binary.write_bytes(b"version: \xff\xfe\n")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(binary)


@pytest.mark.parametrize("text", ["", "\n", "# only a comment\n", "just a sentence\n", "- 1\n- 2\n", "42\n"])
def test_a_file_that_is_not_a_mapping_fails(tmp_path, text):
    path = tmp_path / "report.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match=re.escape(f"{path} must contain a mapping")):
        load_config(path)


def test_sha256_is_the_hash_of_the_file_bytes(tmp_path, cfg):
    assert cfg.sha256 == hashlib.sha256((ROOT / "report.yaml").read_bytes()).hexdigest()
    path = write_variant(tmp_path, lambda d: d["client"].update(name="Another Bakery"))
    variant = load_config(path)
    assert variant.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert variant.sha256 != cfg.sha256
