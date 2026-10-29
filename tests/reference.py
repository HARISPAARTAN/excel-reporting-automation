"""Independent pandas reference for the metrics: fixed formulas, nothing from buildreport.expr or metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

SUMS = {
    "revenue": "net_sales_eur",
    "transactions": "transactions",
    "units_sold": "units_sold",
    "waste_eur": "waste_eur",
    "labour_hours": "labour_hours",
    "labour_cost": "labour_cost_eur",
}
METRICS = [
    "revenue",
    "transactions",
    "avg_basket",
    "units_sold",
    "waste_eur",
    "waste_pct",
    "labour_hours",
    "labour_cost",
    "labour_pct",
    "revenue_per_labour_hour",
]


def frame(records) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "week": [str(record.week) for record in records],
            "branch_code": [record.branch_code for record in records],
            "category": [record.category for record in records],
            "measure": [record.measure for record in records],
            "value": [record.value for record in records],
        }
    )


def _div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator / denominator.where(denominator != 0)


def _metrics(sums: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=sums.index)
    for key, measure in SUMS.items():
        out[key] = sums[measure] if measure in sums.columns else 0.0
    out["avg_basket"] = _div(out["revenue"], out["transactions"])
    out["waste_pct"] = _div(out["waste_eur"], out["revenue"])
    out["labour_pct"] = _div(out["labour_cost"], out["revenue"])
    out["revenue_per_labour_hour"] = _div(out["revenue"], out["labour_hours"])
    return out[METRICS]


def _sums(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return df.pivot_table(index=keys, columns="measure", values="value", aggfunc="sum", fill_value=0.0)


def branch_week(df: pd.DataFrame) -> pd.DataFrame:
    return _metrics(_sums(df, ["week", "branch_code"]))


def group_week(df: pd.DataFrame, groups: list[str]) -> pd.DataFrame:
    return _metrics(_sums(df[df["category"].isin(groups)], ["week", "category"]))


def chain_week(df: pd.DataFrame) -> pd.DataFrame:
    return _metrics(_sums(df, ["week"]))


def relative(current: float, previous: float) -> float:
    if pd.isna(current) or pd.isna(previous) or previous == 0:
        return np.nan
    return (current - previous) / previous


def points(current: float, previous: float) -> float:
    if pd.isna(current) or pd.isna(previous):
        return np.nan
    return (current - previous) * 100


def ranks(branch: pd.DataFrame, week: str, metric: str = "revenue") -> dict[str, int]:
    """Descending, ties by branch code: sort by code, stable sort by value, then rank(method="first")."""
    values = branch.xs(week, level="week")[metric].sort_index()
    ordered = values.sort_values(ascending=False, kind="stable")
    ranked = ordered.rank(method="first", ascending=False)
    return {code: int(rank) for code, rank in ranked.items()}
