"""Metrics engine: branch-week, product-group-week and chain-week scopes, change, ranking and the summary.

sum(m) adds the values of measure m over the scope's records with math.fsum (empty gives 0). Money is never
rounded here; formats only round for display.
"""

from __future__ import annotations

import math
import operator
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from buildreport.config import Config
from buildreport.expr import Node, evaluate
from buildreport.isoweek import IsoWeek, window
from buildreport.resolve import Record

Values = dict[str, float | None]

OP_WORDS = {">": "above", ">=": "at or above", "<": "below", "<=": "at or below"}
_OPS: dict[str, Callable[[float, float], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


def evaluate_scope(metrics: Mapping[str, Node], totals: Mapping[str, float]) -> Values:
    """Every metric in order; later metrics read the values of earlier ones."""
    values: Values = {}
    for key, node in metrics.items():
        values[key] = evaluate(node, lambda measure: totals.get(measure, 0.0), lambda name: values[name])
    return values


def _totals(records: Iterable[Record]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for record in records:
        grouped[record.measure].append(record.value)
    return {measure: math.fsum(items) for measure, items in grouped.items()}


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def change(current: float | None, previous: float | None, kind: str) -> float | None:
    """Relative: (cur - prev) / prev, blank when prev is blank or 0. Points: (cur - prev) x 100."""
    if current is None or previous is None:
        return None
    if kind == "relative":
        return None if previous == 0 else (current - previous) / previous
    return (current - previous) * 100


def rank_branches(values: Mapping[str, float | None], order: str = "desc") -> dict[str, int]:
    """Ranks 1..n without gaps over the branches with a value; ties go to the lower branch code."""
    present: list[tuple[str, float]] = [(code, value) for code, value in values.items() if value is not None]
    if order == "desc":
        present.sort(key=lambda item: (-item[1], item[0]))
    else:
        present.sort(key=lambda item: (item[1], item[0]))
    return {code: index for index, (code, _) in enumerate(present, start=1)}


@dataclass(frozen=True)
class MetricsResult:
    period: IsoWeek
    window: tuple[IsoWeek, ...]
    branch: dict[tuple[IsoWeek, str], Values]  # only branch-weeks with a used return
    group: dict[tuple[IsoWeek, str], Values]
    chain: dict[IsoWeek, Values]
    reporting: dict[IsoWeek, int]
    ranks: dict[IsoWeek, dict[str, int]]  # the period and the week before it
    share: dict[str, float | None]  # product group -> share of chain revenue in the period
    mix: dict[tuple[str, str], float | None]  # (branch, group) -> share of branch revenue in the period

    @property
    def previous(self) -> IsoWeek:
        return self.period.shift(-1)

    def branch_value(self, week: IsoWeek, code: str, metric: str) -> float | None:
        values = self.branch.get((week, code))
        return None if values is None else values.get(metric)

    def group_value(self, week: IsoWeek, group: str, metric: str) -> float | None:
        values = self.group.get((week, group))
        return None if values is None else values.get(metric)

    def chain_value(self, week: IsoWeek, metric: str) -> float | None:
        values = self.chain.get(week)
        return None if values is None else values.get(metric)


def compute(records: Sequence[Record], cfg: Config, period: IsoWeek) -> MetricsResult:
    weeks = window(period, cfg.model.trend_weeks)
    groups = set(cfg.product_groups)
    by_branch: dict[tuple[IsoWeek, str], list[Record]] = defaultdict(list)
    by_group: dict[tuple[IsoWeek, str], list[Record]] = defaultdict(list)
    by_chain: dict[IsoWeek, list[Record]] = defaultdict(list)
    by_branch_group: dict[tuple[str, str], list[Record]] = defaultdict(list)
    for record in records:
        if record.week not in weeks:
            continue
        by_branch[(record.week, record.branch_code)].append(record)
        by_chain[record.week].append(record)
        if record.category in groups:
            by_group[(record.week, record.category)].append(record)
            if record.week == period:
                by_branch_group[(record.branch_code, record.category)].append(record)

    metrics = cfg.metrics
    blank: Values = {key: None for key in metrics}
    branch = {
        key: evaluate_scope(metrics, _totals(items))
        for key, items in sorted(by_branch.items(), key=lambda item: item[0])
    }
    reporting = {week: len({code for scope_week, code in by_branch if scope_week == week}) for week in weeks}
    chain = {
        week: evaluate_scope(metrics, _totals(by_chain[week])) if reporting[week] else dict(blank)
        for week in weeks
    }
    group: dict[tuple[IsoWeek, str], Values] = {}
    for week in weeks:
        for name in cfg.product_groups:
            items = by_group.get((week, name), [])
            group[(week, name)] = evaluate_scope(metrics, _totals(items)) if reporting[week] else dict(blank)

    ranking = cfg.model.ranking
    ranks = {
        week: rank_branches(
            {
                code: values.get(ranking.metric)
                for (scope_week, code), values in branch.items()
                if scope_week == week
            },
            ranking.order,
        )
        for week in (period, period.shift(-1))
    }
    share = {
        name: ratio(group[(period, name)].get("revenue"), chain[period].get("revenue"))
        for name in cfg.product_groups
    }
    mix: dict[tuple[str, str], float | None] = {}
    for code in cfg.branch_codes:
        branch_values = branch.get((period, code))
        for name in cfg.product_groups:
            if branch_values is None:
                mix[(code, name)] = None
                continue
            part = evaluate_scope(metrics, _totals(by_branch_group.get((code, name), [])))
            mix[(code, name)] = ratio(part.get("revenue"), branch_values.get("revenue"))
    return MetricsResult(period, weeks, branch, group, chain, reporting, ranks, share, mix)


@dataclass(frozen=True)
class KpiRow:
    key: str
    label: str
    format: str
    value: float | None
    previous: float | None
    change: float | None
    change_type: str
    better: str


@dataclass(frozen=True)
class RankRow:
    rank: int | None
    code: str
    name: str
    revenue: float | None
    change: float | None
    waste_pct: float | None
    labour_pct: float | None
    rank_change: int | None


@dataclass(frozen=True)
class ThresholdHit:
    metric: str
    label: str
    op: str
    value: float
    style: str
    format: str
    branches: tuple[str, ...]  # codes, in code order
    names: tuple[str, ...]


@dataclass(frozen=True)
class Summary:
    period: IsoWeek
    previous: IsoWeek
    kpis: tuple[KpiRow, ...]
    ranking: tuple[RankRow, ...]  # ranked branches first, then the branches without a return
    above_threshold: tuple[ThresholdHit, ...]
    reporting_now: int
    reporting_previous: int
    expected: int

    @property
    def top(self) -> RankRow | None:
        return self.ranking[0] if self.ranking and self.ranking[0].rank is not None else None


def breaches(value: float | None, op: str, limit: float) -> bool:
    return value is not None and _OPS[op](value, limit)


def summarise(result: MetricsResult, cfg: Config) -> Summary:
    period, previous = result.period, result.previous
    kpis = []
    for key in cfg.model.summary_kpis:
        spec = cfg.metric(key)
        current, before = result.chain_value(period, key), result.chain_value(previous, key)
        kpis.append(
            KpiRow(
                key,
                spec.label,
                spec.format,
                current,
                before,
                change(current, before, spec.change),
                spec.change,
                spec.better,
            )
        )
    ranks_now = result.ranks.get(period, {})
    ranks_before = result.ranks.get(previous, {})
    revenue_change = cfg.metric("revenue").change
    rows = []
    for branch in cfg.branches:
        rank = ranks_now.get(branch.code)
        revenue = result.branch_value(period, branch.code, "revenue")
        earlier = ranks_before.get(branch.code)
        rows.append(
            RankRow(
                rank=rank,
                code=branch.code,
                name=branch.name,
                revenue=revenue,
                change=change(revenue, result.branch_value(previous, branch.code, "revenue"), revenue_change),
                waste_pct=result.branch_value(period, branch.code, "waste_pct"),
                labour_pct=result.branch_value(period, branch.code, "labour_pct"),
                rank_change=None if rank is None or earlier is None else earlier - rank,
            )
        )
    rows.sort(key=lambda row: (row.rank is None, row.rank or 0, row.code))
    hits = []
    for threshold in cfg.model.thresholds:
        spec = cfg.metric(threshold.metric)
        over = [
            branch
            for branch in cfg.branches
            if breaches(
                result.branch_value(period, branch.code, threshold.metric), threshold.op, threshold.value
            )
        ]
        hits.append(
            ThresholdHit(
                metric=threshold.metric,
                label=spec.label,
                op=threshold.op,
                value=threshold.value,
                style=threshold.style,
                format=spec.format,
                branches=tuple(branch.code for branch in over),
                names=tuple(branch.name for branch in over),
            )
        )
    return Summary(
        period=period,
        previous=previous,
        kpis=tuple(kpis),
        ranking=tuple(rows),
        above_threshold=tuple(hits),
        reporting_now=result.reporting.get(period, 0),
        reporting_previous=result.reporting.get(previous, 0),
        expected=len(cfg.branches),
    )


def format_value(value: float | None, fmt: str) -> str:
    """Display text with the workbook's number formats (en dash for blank)."""
    if value is None:
        return "–"
    if fmt == "eur":
        return f"€{value:,.0f}"
    if fmt == "eur2":
        return f"€{value:,.2f}"
    if fmt == "count":
        return f"{value:,.0f}"
    if fmt == "hours":
        return f"{value:,.1f}"
    if fmt == "pct1":
        return f"{value * 100:.1f}%"
    return f"{value}"


def format_change(value: float | None, kind: str) -> str:
    """'+1.2%' for relative changes, '+0.4 pp' for points; '0.0%' when it rounds to zero."""
    if value is None:
        return "–"
    number = value * 100 if kind == "relative" else value
    text = f"{abs(number):.1f}"
    sign = "" if text == "0.0" else ("+" if number > 0 else "-")
    return f"{sign}{text}{'%' if kind == 'relative' else ' pp'}"


def threshold_text(hit: ThresholdHit) -> str:
    names = ", ".join(hit.names) if hit.names else "none"
    return f"{hit.label} {OP_WORDS[hit.op]} {format_value(hit.value, hit.format)}: {names}"


def count_text(count: int, singular: str) -> str:
    return f"{count} {singular}" if count == 1 else f"{count} {singular}s"
