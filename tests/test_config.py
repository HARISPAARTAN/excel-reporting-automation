import copy
import re
from pathlib import Path

import pytest
import yaml

from buildreport.config import REQUIRED_METRICS, ConfigError, load_config
from buildreport.isoweek import IsoWeek

ROOT = Path(__file__).resolve().parents[1]
RAW = yaml.safe_load((ROOT / "report.yaml").read_text(encoding="utf-8"))


def write_variant(tmp_path, change):
    data = copy.deepcopy(RAW)
    change(data)
    path = tmp_path / "report.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


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
        (lambda d: d["metrics"].pop("labour_pct"), "labour_pct"),
        (lambda d: d.update(colour="blue"), "Extra inputs are not permitted"),
        (lambda d: d["input"].update(file_pattern=r"^CL-\d{2}.*\.xlsx$"), "named groups branch and week"),
        (
            lambda d: d["branches"].append({"code": "CL-01", "name": "Copy", "format": "Flagship"}),
            "branch codes must be unique",
        ),
        (lambda d: d["metrics"]["revenue"].update(expr="sum(net_sales_eur) ** 2"), "is not allowed"),
        (lambda d: d["metrics"]["revenue"].update(expr="transactions * 2"), "must be defined above revenue"),
        (lambda d: d["output"].update(file_name="{period}_{client}.xlsx"), "{period} and no other field"),
        (lambda d: d["summary_kpis"].__setitem__(6, "profit"), "unknown metric profit"),
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


def test_unreadable_and_malformed_files(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "missing.yaml")
    broken = tmp_path / "broken.yaml"
    broken.write_text("version: [1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(broken)
    listing = tmp_path / "list.yaml"
    listing.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="must contain a mapping"):
        load_config(listing)
