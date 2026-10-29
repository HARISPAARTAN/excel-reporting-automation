"""build-report: the commands run, validate and generate-fixtures (spec 6), with exit codes 0 to 5."""

from __future__ import annotations

import functools
import json
import logging
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

import click

from buildreport import TOOL_NAME, __version__
from buildreport.config import Config, ConfigError, load_config
from buildreport.discover import discover
from buildreport.findings import Finding, counts
from buildreport.fixtures import DEFAULT_SEED, generate, write_fixtures
from buildreport.isoweek import IsoWeek, last_completed, window
from buildreport.manifest import Output, build_manifest, dumps
from buildreport.metrics import compute, count_text, summarise
from buildreport.notify import (
    NotifyError,
    SmtpConfigError,
    SmtpSettings,
    build_message,
    recipients,
    send,
    smtp_settings,
    to_bytes,
)
from buildreport.reproducible import RunTimestamp, TimestampError, environment, run_timestamp, write_atomic
from buildreport.resolve import Resolution, resolve, to_records
from buildreport.template import ReadResult, read_return
from buildreport.workbook import BuildContext, render_bytes

EXIT_OK = 0
EXIT_UNEXPECTED = 1
EXIT_USAGE = 2
EXIT_BLOCKED = 3
EXIT_NOTIFY = 4
EXIT_EXCLUDED = 5
LAST = "last"

log = logging.getLogger("buildreport")


class UsageProblem(Exception):
    """A usage problem found after option parsing, such as a missing input folder (exit code 2)."""


class PeriodType(click.ParamType):
    """An ISO week such as 2025-W38 (2025W38 accepted), or the word last."""

    name = "period"

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None) -> IsoWeek | str:
        if isinstance(value, IsoWeek):
            return value
        text = str(value).strip()
        if text.lower() == LAST:
            return LAST
        try:
            return IsoWeek.parse(text)
        except ValueError:
            self.fail(f"{value!r} is not an ISO week such as 2025-W38, or last", param, ctx)


PERIOD = PeriodType()


def resolve_period(value: IsoWeek | str, timestamp: RunTimestamp) -> IsoWeek:
    """`last` is the ISO week before the UTC week of the run timestamp (SOURCE_DATE_EPOCH or the clock)."""
    if isinstance(value, IsoWeek):
        return value
    return last_completed(timestamp.value)


def guarded(command: Callable[..., int]) -> Callable[..., None]:
    """Map the command's return value and its exceptions to the exit codes of spec 6."""

    @functools.wraps(command)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        try:
            code = command(*args, **kwargs)
        except (ConfigError, SmtpConfigError, TimestampError, UsageProblem) as exc:
            log.error("%s", exc)
            raise SystemExit(EXIT_USAGE) from None
        except (click.ClickException, click.exceptions.Exit, click.exceptions.Abort):
            raise
        except Exception as exc:
            log.debug("traceback of the unexpected error", exc_info=True)
            log.error("unexpected error: %s: %s", type(exc).__name__, exc)
            raise SystemExit(EXIT_UNEXPECTED) from None
        if code != EXIT_OK:
            raise SystemExit(code)

    return wrapper


def _configure_logging(level: str, log_file: Path | None) -> list[logging.Handler]:
    for handler in list(log.handlers):
        log.removeHandler(handler)
        handler.close()
    log.setLevel(level.upper())
    log.propagate = False
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    handlers: list[logging.Handler] = [stream]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        appended = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        appended.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        handlers.append(appended)
    for handler in handlers:
        log.addHandler(handler)
    return handlers


def _close_logging(handlers: Sequence[logging.Handler]) -> None:
    for handler in handlers:
        log.removeHandler(handler)
        handler.close()


def _read(folder: Path, cfg: Config) -> list[ReadResult]:
    if not folder.is_dir():
        raise UsageProblem(f"input folder {folder} does not exist")
    sources = discover(folder, cfg.model.input.file_pattern)
    log.info("reading %s from %s", count_text(len(sources), "file"), folder)
    return [read_return(source, cfg) for source in sources]


def _log_findings(findings: Sequence[Finding]) -> None:
    for item in findings:
        if item.severity == "error":
            log.error("%s", item.line())
        else:
            log.warning("%s", item.line())


def _tally(findings: Sequence[Finding]) -> str:
    numbers = counts(findings)
    return f"{count_text(numbers['error'], 'error')}, {count_text(numbers['warning'], 'warning')}"


config_option = click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default="report.yaml",
    show_default=True,
    help="The report configuration.",
)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "--version", prog_name=TOOL_NAME, message="%(prog)s %(version)s")
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING"], case_sensitive=False),
    default="INFO",
    show_default=True,
)
@click.option(
    "--log-file",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Also append the log here.",
)
@click.pass_context
def cli(ctx: click.Context, log_level: str, log_file: Path | None) -> None:
    """Check the weekly branch workbooks and build the Cedarline weekly report."""
    handlers = _configure_logging(log_level, log_file)
    ctx.call_on_close(lambda: _close_logging(handlers))


def _manifest(
    *,
    status: str,
    code: int,
    cfg: Config,
    period: IsoWeek,
    timestamp: RunTimestamp,
    strict: bool,
    notify: str,
    resolution: Resolution,
    summary: Any,
    outputs: list[Output],
) -> bytes:
    manifest = build_manifest(
        status=cast(Any, status),
        exit_code=code,
        cfg=cfg,
        period=period,
        timestamp=timestamp,
        strict=strict,
        notify=notify,
        resolution=resolution,
        summary=summary,
        outputs=outputs,
        env=os.environ,
        versions=environment(),
    )
    return dumps(manifest)


@cli.command()
@click.option("--period", type=PERIOD, required=True, help="ISO week such as 2025-W38, or last.")
@click.option(
    "--input",
    "input_dir",
    default="data/incoming",
    show_default=True,
    help="Folder with the branch workbooks.",
)
@click.option(
    "--out", "out_dir", type=click.Path(file_okay=False, path_type=Path), default="reports", show_default=True
)
@config_option
@click.option("--strict", is_flag=True, help="Block on any finding: no workbook, no e-mail, exit 3.")
@click.option("--notify", type=click.Choice(["none", "dry-run", "smtp"]), default="none", show_default=True)
@guarded
def run(
    period: IsoWeek | str, input_dir: str, out_dir: Path, config_path: Path, strict: bool, notify: str
) -> int:
    """Build the weekly report for one ISO week."""
    cfg = load_config(config_path)
    timestamp = run_timestamp()
    week = resolve_period(period, timestamp)
    strict = strict or cfg.model.strict
    settings: SmtpSettings | None = smtp_settings(os.environ) if notify == "smtp" else None
    results = _read(Path(input_dir), cfg)
    resolution = resolve(results, cfg, window(week, cfg.model.trend_weeks), week)
    _log_findings(resolution.findings)
    stem = cfg.stem(week)
    xlsx_path, eml_path, manifest_path = (
        out_dir / f"{stem}{suffix}" for suffix in (".xlsx", ".eml", ".manifest.json")
    )
    common = {"cfg": cfg, "period": week, "timestamp": timestamp, "strict": strict, "notify": notify}

    no_data = any(item.code == "NO_DATA" for item in resolution.findings)
    if no_data or (strict and resolution.findings):
        for stale in (xlsx_path, eml_path):
            stale.unlink(missing_ok=True)
        manifest = _manifest(
            status="blocked", code=EXIT_BLOCKED, resolution=resolution, summary=None, outputs=[], **common
        )
        write_atomic(manifest_path, manifest)
        reason = "no valid file for the period" if no_data else "strict mode stops on any finding"
        tally = _tally(resolution.findings)
        log.error("blocked, no report for %s (%s); %s; manifest %s", week, reason, tally, manifest_path)
        return EXIT_BLOCKED

    records = to_records(resolution.returns, cfg)
    result = compute(records, cfg, week)
    summary = summarise(result, cfg)
    ctx = BuildContext(cfg, result, summary, resolution, records, timestamp, strict, input_dir)
    xlsx = render_bytes(ctx)
    write_atomic(xlsx_path, xlsx)
    log.info("wrote %s", xlsx_path)
    outputs = [Output.of(xlsx_path.name, xlsx)]
    code = EXIT_EXCLUDED if resolution.excluded_by_error else EXIT_OK

    if notify == "none":
        eml_path.unlink(missing_ok=True)
    else:
        message = build_message(ctx, xlsx_path.name, xlsx, cast(Any, notify))
        eml = to_bytes(message)
        write_atomic(eml_path, eml)
        outputs.append(Output.of(eml_path.name, eml))
        log.info("wrote %s", eml_path)
        if settings is not None:
            to_addrs = recipients(cfg)
            try:
                send(message, settings, cfg.model.notify.sender.address, to_addrs)
                log.info("sent the report to %s", count_text(len(to_addrs), "recipient"))
            except NotifyError as exc:
                log.error("%s; the report and the .eml are kept", exc)
                code = EXIT_NOTIFY

    manifest = _manifest(
        status="built", code=code, resolution=resolution, summary=summary, outputs=outputs, **common
    )
    write_atomic(manifest_path, manifest)
    log.info("wrote %s", manifest_path)
    log.info(
        "%s: %s branches reported, %s expected; %s; exit code %s",
        week,
        summary.reporting_now,
        summary.expected,
        _tally(resolution.findings),
        code,
    )
    return code


@cli.command()
@click.option(
    "--input",
    "input_dir",
    default="data/incoming",
    show_default=True,
    help="Folder with the branch workbooks.",
)
@click.option(
    "--period", type=PERIOD, default=None, help="Also check completeness for this week and its window."
)
@config_option
@click.option("--strict", is_flag=True, help="Exit 3 on any finding, not only on errors.")
@click.option(
    "--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True
)
@guarded
def validate(
    input_dir: str, period: IsoWeek | str | None, config_path: Path, strict: bool, output_format: str
) -> int:
    """Check the workbooks and print one line per finding (or a JSON list)."""
    cfg = load_config(config_path)
    strict = strict or cfg.model.strict
    results = _read(Path(input_dir), cfg)
    if period is None:
        resolution = resolve(results, cfg, None, None)
    else:
        week = resolve_period(period, run_timestamp())
        resolution = resolve(results, cfg, window(week, cfg.model.trend_weeks), week)
    findings = resolution.findings
    if output_format == "json":
        click.echo(json.dumps([item.as_dict() for item in findings], indent=2, ensure_ascii=False))
    else:
        for item in findings:
            click.echo(item.line())
    log.info("checked %s: %s", count_text(len(results), "file"), _tally(findings))
    if counts(findings)["error"] or (strict and findings):
        return EXIT_BLOCKED
    return EXIT_OK


@cli.command("generate-fixtures")
@click.option(
    "--weeks", type=click.IntRange(1, 104), default=8, show_default=True, help="Number of weeks (1 to 104)."
)
@click.option(
    "--end-week", type=PERIOD, default=LAST, show_default=True, help="Last week, such as 2025-W38, or last."
)
@click.option("--out", "out_dir", type=click.Path(file_okay=False, path_type=Path), required=True)
@click.option("--seed", type=int, default=DEFAULT_SEED, show_default=True)
@click.option("--deviations", type=click.Choice(["none", "demo"]), default="none", show_default=True)
@click.option("--force", is_flag=True, help="Overwrite existing files.")
@config_option
@guarded
def generate_fixtures(
    weeks: int,
    end_week: IsoWeek | str,
    out_dir: Path,
    seed: int,
    deviations: str,
    force: bool,
    config_path: Path,
) -> int:
    """Write invented branch workbooks for testing and the demo."""
    cfg = load_config(config_path)
    end = resolve_period(end_week, run_timestamp())
    files = generate(cfg, end, weeks, deviations=cast(Any, deviations), seed=seed)
    try:
        write_fixtures(files, out_dir, force=force)
    except FileExistsError as exc:
        raise UsageProblem(str(exc)) from exc
    log.info(
        "wrote %s (%s ending %s, deviations %s) to %s",
        count_text(len(files), "file"),
        count_text(weeks, "week"),
        end,
        deviations,
        out_dir,
    )
    return EXIT_OK


def main() -> None:
    cli(prog_name=TOOL_NAME)
