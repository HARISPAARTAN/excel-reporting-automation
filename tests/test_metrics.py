import math

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from buildreport.isoweek import IsoWeek
from buildreport.metrics import (
    change,
    compute,
    evaluate_scope,
    format_change,
    format_value,
    rank_branches,
    summarise,
)
from buildreport.resolve import Record

import reference

W38 = IsoWeek(2025, 38)
W37 = IsoWeek(2025, 37)
GROUPS = [
    "Bread",
    "Viennoiserie",
    "Cakes and Pastries",
    "Savoury and Sandwiches",
    "Hot Drinks",
    "Cold Drinks and Grocery",
]
ROLES = ["Bakery", "Counter", "Supervisor"]
PAIRS = (
    [
        (measure, group)
        for measure in ("net_sales_eur", "units_sold", "waste_units", "waste_eur")
        for group in GROUPS
    ]
    + [(measure, role) for measure in ("labour_hours", "labour_cost_eur") for role in ROLES]
    + [("transactions", "")]
)


def same(engine, expected):
    if engine is None:
        return bool(pd.isna(expected))
    return not pd.isna(expected) and math.isclose(engine, float(expected), rel_tol=1e-9, abs_tol=1e-12)


def test_branch_week_metrics_match_pandas(demo_records, demo_result):
    expected = reference.branch_week(reference.frame(demo_records))
    assert len(expected) == 95 and len(demo_result.branch) == 95
    for (week, code), row in expected.iterrows():
        values = demo_result.branch[(IsoWeek.parse(week), code)]
        for metric in reference.METRICS:
            assert same(values[metric], row[metric]), (week, code, metric)


def test_group_week_metrics_match_pandas(cfg, demo_records, demo_result):
    expected = reference.group_week(reference.frame(demo_records), list(cfg.product_groups))
    assert len(expected) == 48
    for (week, group), row in expected.iterrows():
        values = demo_result.group[(IsoWeek.parse(week), group)]
        for metric in reference.METRICS:
            assert same(values[metric], row[metric]), (week, group, metric)


def test_chain_week_metrics_match_pandas(demo_records, demo_result):
    expected = reference.chain_week(reference.frame(demo_records))
    assert len(expected) == 8
    for week, row in expected.iterrows():
        values = demo_result.chain[IsoWeek.parse(week)]
        for metric in reference.METRICS:
            assert same(values[metric], row[metric]), (week, metric)


def test_week_on_week_changes_match_pandas(cfg, demo_records, demo_result):
    df = reference.frame(demo_records)
    chain, branch = reference.chain_week(df), reference.branch_week(df)
    for key in cfg.model.summary_kpis:
        kind = cfg.metric(key).change
        current, previous = chain.loc["2025-W38", key], chain.loc["2025-W37", key]
        expected = (
            reference.relative(current, previous)
            if kind == "relative"
            else reference.points(current, previous)
        )
        engine = change(demo_result.chain_value(W38, key), demo_result.chain_value(W37, key), kind)
        assert same(engine, expected), key
    for code in cfg.branch_codes:
        current, previous = (
            branch.loc[("2025-W38", code), "revenue"],
            branch.loc[("2025-W37", code), "revenue"],
        )
        engine = change(
            demo_result.branch_value(W38, code, "revenue"),
            demo_result.branch_value(W37, code, "revenue"),
            "relative",
        )
        assert same(engine, reference.relative(current, previous)), code


def test_ranks_match_pandas(demo_records, demo_result):
    branch = reference.branch_week(reference.frame(demo_records))
    for week in (W38, W37):
        assert demo_result.ranks[week] == reference.ranks(branch, str(week))


def test_rank_ties_go_to_the_lower_code():
    assert rank_branches({"CL-02": 10.0, "CL-01": 10.0, "CL-03": 5.0, "CL-04": None}) == {
        "CL-01": 1,
        "CL-02": 2,
        "CL-03": 3,
    }
    assert rank_branches({"CL-02": 1.0, "CL-01": 2.0}, "asc") == {"CL-02": 1, "CL-01": 2}


@pytest.mark.parametrize(
    ("current", "previous", "kind", "expected"),
    [
        (110.0, 100.0, "relative", 0.1),
        (110.0, None, "relative", None),
        (110.0, 0.0, "relative", None),
        (0.065, 0.060, "points", 0.5),
        (None, 0.060, "points", None),
    ],
)
def test_change_rules(current, previous, kind, expected):
    result = change(current, previous, kind)
    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


def test_division_by_zero_gives_blank(cfg):
    values = evaluate_scope(cfg.metrics, {"net_sales_eur": 0.0})
    assert values["revenue"] == 0.0
    assert values["waste_pct"] is None and values["avg_basket"] is None


def test_a_branch_without_a_return_is_blank_and_unranked(cfg, demo_records):
    records = [
        record for record in demo_records if not (record.branch_code == "CL-07" and record.week == W38)
    ]
    result = compute(records, cfg, W38)
    assert (W38, "CL-07") not in result.branch
    assert result.reporting[W38] == 11
    summary = summarise(result, cfg)
    last = summary.ranking[-1]
    assert last.code == "CL-07" and last.rank is None and last.revenue is None
    assert [row.rank for row in summary.ranking[:-1]] == list(range(1, 12))
    assert summary.reporting_now == 11 and summary.reporting_previous == 12


RECORDS = st.lists(
    st.tuples(
        st.sampled_from(["CL-01", "CL-02", "CL-03"]),
        st.sampled_from([W37, W38]),
        st.sampled_from(PAIRS),
        st.floats(min_value=0, max_value=50_000, allow_nan=False).map(lambda value: round(value, 2)),
    ),
    min_size=1,
    max_size=40,
)


@settings(max_examples=60, deadline=None)
@given(RECORDS)
def test_engine_matches_pandas_on_generated_records(cfg, rows):
    records = [
        Record(week, code, category, measure, value, "x.xlsx")
        for code, week, (measure, category), value in rows
    ]
    result = compute(records, cfg, W38)
    df = reference.frame(records)
    for (week, code), row in reference.branch_week(df).iterrows():
        for metric in reference.METRICS:
            assert same(result.branch[(IsoWeek.parse(week), code)][metric], row[metric])
    for week, row in reference.chain_week(df).iterrows():
        for metric in reference.METRICS:
            assert same(result.chain[IsoWeek.parse(week)][metric], row[metric])
    for week in (W37, W38):
        revenues = [
            values["revenue"] for (scope_week, _), values in result.branch.items() if scope_week == week
        ]
        if revenues:
            assert math.isclose(
                math.fsum(revenues), result.chain[week]["revenue"], rel_tol=1e-9, abs_tol=1e-9
            )


def test_demo_summary_shape(demo_result, cfg):
    summary = summarise(demo_result, cfg)
    assert [row.label for row in summary.kpis] == [
        "Revenue",
        "Transactions",
        "Average basket",
        "Waste %",
        "Labour % of revenue",
        "Revenue per labour hour",
        "Labour hours",
    ]
    assert (summary.reporting_now, summary.reporting_previous, summary.expected) == (12, 12, 12)
    assert [row.rank for row in summary.ranking] == list(range(1, 13))
    assert summary.top is summary.ranking[0]


def test_threshold_hits_match_pandas(cfg, demo_records, demo_result):
    branch = reference.branch_week(reference.frame(demo_records))
    week = branch.xs("2025-W38", level="week")
    hits = {hit.metric: hit.branches for hit in summarise(demo_result, cfg).above_threshold}
    assert hits["waste_pct"] == tuple(sorted(week.index[week["waste_pct"] > 0.06]))
    assert hits["labour_pct"] == tuple(sorted(week.index[week["labour_pct"] > 0.32]))
    assert len(hits["waste_pct"]) >= 1


@pytest.mark.parametrize(
    ("value", "fmt", "text"),
    [
        (306912.4, "eur", "€306,912"),
        (8.472, "eur2", "€8.47"),
        (34210.0, "count", "34,210"),
        (8123.46, "hours", "8,123.5"),
        (0.0612, "pct1", "6.1%"),
        (None, "eur", "–"),
    ],
)
def test_format_value(value, fmt, text):
    assert format_value(value, fmt) == text


@pytest.mark.parametrize(
    ("value", "kind", "text"),
    [
        (0.0123, "relative", "+1.2%"),
        (-0.004, "relative", "-0.4%"),
        (0.0, "relative", "0.0%"),
        (0.42, "points", "+0.4 pp"),
        (None, "points", "–"),
    ],
)
def test_format_change(value, kind, text):
    assert format_change(value, kind) == text


def test_shares_and_mix_add_up(cfg, demo_result):
    assert math.fsum(demo_result.share[group] for group in cfg.product_groups) == pytest.approx(1.0)
    for code in cfg.branch_codes:
        assert math.fsum(demo_result.mix[(code, group)] for group in cfg.product_groups) == pytest.approx(1.0)
