"""report.yaml: pydantic models (unknown keys forbidden), the validation rules and the compiled metrics."""

from __future__ import annotations

import hashlib
import re
import string
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from buildreport.expr import Node, compile_metrics
from buildreport.isoweek import IsoWeek

REQUIRED_METRICS = (
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
)
COVER_MEASURE = "transactions"
MAX_BRANCHES = 14
MAX_SUMMARY_KPIS = 7

ColumnType = Literal["text", "money", "count", "hours"]
Format = Literal["eur", "eur2", "count", "hours", "pct1"]


class ConfigError(Exception):
    """report.yaml is missing, unreadable or invalid (exit code 2)."""


def normalise(text: str) -> str:
    """Whitespace collapsed and case folded, for labels, headers, sheet names and row keys."""
    return " ".join(text.split()).casefold()


def _first_collision(values: Iterable[str]) -> str | None:
    """The first value that normalises to the same text as an earlier one, as written; None if all differ."""
    seen: set[str] = set()
    for value in values:
        folded = normalise(value)
        if folded in seen:
            return value
        seen.add(folded)
    return None


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Client(_Model):
    name: str
    city: str
    country: str
    currency: Literal["EUR"]


class InputSettings(_Model):
    file_pattern: str

    @field_validator("file_pattern")
    @classmethod
    def _named_groups(cls, value: str) -> str:
        try:
            compiled = re.compile(value)
        except re.error as exc:
            raise ValueError(f"not a regular expression: {exc}") from exc
        missing = {"branch", "week"} - set(compiled.groupindex)
        if missing:
            raise ValueError(
                f"file_pattern needs the named groups branch and week; missing: {', '.join(sorted(missing))}"
            )
        return value


class SheetSpec(_Model):
    name: str
    aliases: tuple[str, ...] = ()

    @field_validator("aliases")
    @classmethod
    def _no_blank_alias(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not alias.strip() for alias in value):
            raise ValueError("aliases must not be blank")
        return value


class CoverLabels(_Model):
    branch_code: str
    branch_name: str
    week: str
    transactions: str
    submitted_at: str
    submitted_by: str
    template_version: str


class CoverSpec(_Model):
    sheet: SheetSpec
    labels: CoverLabels


class KeySpec(_Model):
    header: str
    values: Literal["product_groups", "roles"]


class ColumnSpec(_Model):
    header: str
    type: ColumnType


class TableSpec(_Model):
    sheet: SheetSpec
    key: KeySpec
    columns: dict[str, ColumnSpec]


class TemplateSpec(_Model):
    version: int = Field(ge=1)
    cover: CoverSpec
    sales: TableSpec
    labour: TableSpec

    @model_validator(mode="after")
    def _tables(self) -> TemplateSpec:
        if self.sales.key.values != "product_groups":
            raise ValueError("template.sales.key.values must be product_groups")
        if self.labour.key.values != "roles":
            raise ValueError("template.labour.key.values must be roles")
        keys = [*self.sales.columns, *self.labour.columns]
        if COVER_MEASURE in keys or len(keys) != len(set(keys)):
            raise ValueError(
                "column keys must be unique across sales and labour and must not be 'transactions'"
            )
        for table in (self.sales, self.labour):
            headers = [
                normalise(table.key.header),
                *(normalise(column.header) for column in table.columns.values()),
            ]
            if len(headers) != len(set(headers)):
                raise ValueError(f"headers on sheet {table.sheet.name} must be unique")
        label = _first_collision(self.cover.labels.model_dump().values())
        if label is not None:
            raise ValueError(f"template.cover.labels: duplicate label {label!r}")
        sheets = (self.cover.sheet, self.sales.sheet, self.labour.sheet)
        name = _first_collision(text for sheet in sheets for text in (sheet.name, *sheet.aliases))
        if name is not None:
            raise ValueError(f"template: duplicate sheet name or alias {name!r}")
        return self


class Branch(_Model):
    code: str
    name: str
    format: str


class MetricSpec(_Model):
    label: str
    expr: str
    format: Format
    change: Literal["relative", "points"]
    better: Literal["higher", "lower", "neutral"]


class Ranking(_Model):
    metric: str
    order: Literal["desc", "asc"]


class Threshold(_Model):
    metric: str
    op: Literal[">", ">=", "<", "<="]
    value: float
    style: Literal["bad", "warn"]


class OutputSettings(_Model):
    file_name: str

    @field_validator("file_name")
    @classmethod
    def _only_period(cls, value: str) -> str:
        fields = {field for _, field, _, _ in string.Formatter().parse(value) if field is not None}
        if fields != {"period"}:
            raise ValueError("file_name must contain {period} and no other field")
        if not value.endswith(".xlsx") or "/" in value or "\\" in value:
            raise ValueError("file_name must be a plain .xlsx file name")
        return value


class Address(_Model):
    name: str
    address: str

    @field_validator("address")
    @classmethod
    def _mailbox(cls, value: str) -> str:
        if "@" not in value:
            raise ValueError(f"{value!r} is not an e-mail address")
        return value


class NotifySettings(_Model):
    sender: Address = Field(alias="from")
    subject_prefix: str
    to: tuple[str, ...] = Field(min_length=1)
    cc: tuple[str, ...] = ()

    @field_validator("to", "cc")
    @classmethod
    def _mailboxes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for address in value:
            if "@" not in address:
                raise ValueError(f"{address!r} is not an e-mail address")
        return value


def measure_keys(template: TemplateSpec) -> tuple[str, ...]:
    """Numeric measures in record order: sales columns, labour columns, then transactions from the cover."""
    sales = [key for key, column in template.sales.columns.items() if column.type != "text"]
    labour = [key for key, column in template.labour.columns.items() if column.type != "text"]
    return (*sales, *labour, COVER_MEASURE)


class ReportConfig(_Model):
    version: Literal[1]
    client: Client
    input: InputSettings
    template: TemplateSpec
    branches: tuple[Branch, ...] = Field(min_length=1, max_length=MAX_BRANCHES)
    product_groups: tuple[str, ...] = Field(min_length=1, max_length=12)
    roles: tuple[str, ...] = Field(min_length=1, max_length=6)
    metrics: dict[str, MetricSpec]
    summary_kpis: tuple[str, ...] = Field(min_length=1, max_length=MAX_SUMMARY_KPIS)
    ranking: Ranking
    thresholds: tuple[Threshold, ...] = ()
    trend_weeks: Literal[8]
    strict: bool = False
    output: OutputSettings
    notify: NotifySettings

    @model_validator(mode="after")
    def _rules(self) -> ReportConfig:
        codes = [branch.code for branch in self.branches]
        if len(codes) != len(set(codes)):
            raise ValueError("branch codes must be unique")
        branch_name = _first_collision(branch.name for branch in self.branches)
        if branch_name is not None:
            raise ValueError(f"branches: duplicate name {branch_name!r}")
        for label, values in (("product_groups", self.product_groups), ("roles", self.roles)):
            folded = [normalise(value) for value in values]
            if len(folded) != len(set(folded)):
                raise ValueError(f"{label} must be unique")
        missing = [key for key in REQUIRED_METRICS if key not in self.metrics]
        if missing:
            raise ValueError(
                f"metrics must define {', '.join(missing)} (the sheet layout of v0.1.0 needs them)"
            )
        if [key for key in self.metrics if key in REQUIRED_METRICS] != list(REQUIRED_METRICS):
            raise ValueError(
                f"metrics: required metrics must appear in the order {', '.join(REQUIRED_METRICS)}"
            )
        metric_label = _first_collision(spec.label for spec in self.metrics.values())
        if metric_label is not None:
            raise ValueError(f"metrics: duplicate label {metric_label!r}")
        compile_metrics({key: spec.expr for key, spec in self.metrics.items()}, measure_keys(self.template))
        for key in self.summary_kpis:
            if key not in self.metrics:
                raise ValueError(f"summary_kpis: unknown metric {key}")
        if len(set(self.summary_kpis)) != len(self.summary_kpis):
            raise ValueError("summary_kpis must not repeat a metric")
        if self.ranking.metric not in self.metrics:
            raise ValueError(f"ranking: unknown metric {self.ranking.metric}")
        seen: set[str] = set()
        for threshold in self.thresholds:
            if threshold.metric not in self.metrics:
                raise ValueError(f"thresholds: unknown metric {threshold.metric}")
            if threshold.metric in seen:
                raise ValueError(f"thresholds: {threshold.metric} has more than one threshold")
            seen.add(threshold.metric)
        return self


@dataclass(frozen=True)
class Config:
    path: Path
    sha256: str
    model: ReportConfig
    metrics: dict[str, Node]

    @property
    def branches(self) -> tuple[Branch, ...]:
        return self.model.branches

    @property
    def branch_codes(self) -> tuple[str, ...]:
        return tuple(branch.code for branch in self.model.branches)

    def branch(self, code: str) -> Branch | None:
        return next((branch for branch in self.model.branches if branch.code == code), None)

    @property
    def product_groups(self) -> tuple[str, ...]:
        return self.model.product_groups

    @property
    def roles(self) -> tuple[str, ...]:
        return self.model.roles

    @property
    def sales_measures(self) -> tuple[str, ...]:
        columns = self.model.template.sales.columns
        return tuple(key for key, column in columns.items() if column.type != "text")

    @property
    def labour_measures(self) -> tuple[str, ...]:
        columns = self.model.template.labour.columns
        return tuple(key for key, column in columns.items() if column.type != "text")

    @property
    def measures(self) -> tuple[str, ...]:
        return measure_keys(self.model.template)

    def measure_type(self, measure: str) -> str:
        if measure == COVER_MEASURE:
            return "count"
        columns = {**self.model.template.sales.columns, **self.model.template.labour.columns}
        return columns[measure].type

    def metric(self, key: str) -> MetricSpec:
        return self.model.metrics[key]

    def threshold(self, metric: str) -> Threshold | None:
        return next((item for item in self.model.thresholds if item.metric == metric), None)

    def file_name(self, period: IsoWeek) -> str:
        return self.model.output.file_name.format(period=str(period))

    def stem(self, period: IsoWeek) -> str:
        return self.file_name(period).removesuffix(".xlsx")


class _DuplicateKeyError(yaml.YAMLError):
    def __init__(self, key: object, line: int) -> None:
        super().__init__(f"duplicate key {key!r} on line {line}")


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that refuses a repeated mapping key at any level instead of keeping the last value."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = self.construct_object(key_node, deep=True)
            try:
                repeated = key in seen
            except TypeError:
                continue  # an unhashable key: the parent class reports it
            if repeated:
                raise _DuplicateKeyError(key, key_node.start_mark.line + 1)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _describe(path: Path, error: ValidationError) -> str:
    parts = []
    for item in error.errors():
        where = ".".join(str(part) for part in item["loc"]) or "(top level)"
        parts.append(f"{where}: {item['msg']}")
    return f"{path}: " + "; ".join(parts)


def load_config(path: Path | str) -> Config:
    """Read, validate and compile report.yaml; every problem raises ConfigError."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc.strerror or exc}") from exc
    try:
        data = yaml.load(raw.decode("utf-8"), Loader=_UniqueKeyLoader)
    except _DuplicateKeyError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping")
    try:
        model = ReportConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_describe(path, exc)) from exc
    metrics = compile_metrics(
        {key: spec.expr for key, spec in model.metrics.items()}, measure_keys(model.template)
    )
    return Config(path=path, sha256=hashlib.sha256(raw).hexdigest(), model=model, metrics=metrics)
