# excel-reporting-automation

[![CI](https://github.com/HARISPAARTAN/excel-reporting-automation/actions/workflows/ci.yml/badge.svg)](https://github.com/HARISPAARTAN/excel-reporting-automation/actions/workflows/ci.yml)
[![weekly report](https://github.com/HARISPAARTAN/excel-reporting-automation/actions/workflows/weekly-report.yml/badge.svg)](https://github.com/HARISPAARTAN/excel-reporting-automation/actions/workflows/weekly-report.yml)
[![Pages](https://github.com/HARISPAARTAN/excel-reporting-automation/actions/workflows/pages.yml/badge.svg)](https://github.com/HARISPAARTAN/excel-reporting-automation/actions/workflows/pages.yml)
[![release](https://img.shields.io/github/v/release/HARISPAARTAN/excel-reporting-automation)](https://github.com/HARISPAARTAN/excel-reporting-automation/releases)

Python CLI that turns twelve weekly branch workbooks into one checked, formatted Excel report, built and e-mailed on a schedule. [Deutsch](README.de.md)

## Status

Work towards v0.1.0. Verified on the development machine (Windows 11, Python 3.13, uv): the test suite passes (`uv run pytest`); the demo run under [Getting started](#getting-started) exits with code 0 and the six warnings of the demo set, and with `--strict` it exits with code 3 and writes no workbook; two runs with `SOURCE_DATE_EPOCH=1758520800` give identical bytes. Not verified yet: the CI jobs, the LibreOffice render, the weekly run and the Pages site.

## Client brief

Cedarline Bakeries, a fictional chain of twelve bakeries around Dublin, posted:

> Every Monday each branch manager e-mails head office an Excel file for the past week: sales by product group, waste, labour hours and the number of transactions. The template is fixed, but in practice sheets get renamed, columns get added, and files arrive twice or carry the wrong week. We need a Python script that collects the files from a folder, checks them, builds one formatted weekly report with KPIs, week-on-week changes, a branch ranking and charts, and e-mails it to head office every Monday morning without anyone opening Excel.

Rebuilt from memory as a demo. The original client's name and data are not used.

The full brief, the roles and the acceptance criteria are in [docs/brief.md](docs/brief.md).

## Live demo

[harispaartan.github.io/excel-reporting-automation](https://harispaartan.github.io/excel-reporting-automation/) shows the latest weekly report: the key figures with their week-on-week change, the branch ranking, the findings of the run, LibreOffice previews of the five sheets, and links to the workbook, the e-mail and a PDF of the sheets. The data is invented and regenerated every week.

![The demo page with the latest weekly report: run card, key figures, branch ranking and findings](docs/screenshots/pages.png)

![The Summary sheet of the 2025-W38 demo report, rendered by LibreOffice in CI](docs/screenshots/summary.png)

The other sheets of the demo report, rendered the same way: [Branches](docs/screenshots/branches.png), [Products](docs/screenshots/products.png), [Data](docs/screenshots/data.png) (first 40 rows) and [Run info](docs/screenshots/run-info.png).

## What it does

- **Template checks with findings.** Each workbook is checked against template version 3. Renamed sheets, extra columns, a missing or contradictory week, duplicate submissions and missing branches are resolved by fixed rules and reported as findings with a code; files with errors are excluded, the others are used. `--strict` stops on any finding.
- **Metrics from configuration.** Ten metrics are expressions in [report.yaml](report.yaml), such as `revenue / transactions`, evaluated for every branch, product group and the chain, with week-on-week change, a branch ranking and thresholds.
- **One formatted workbook.** Five sheets (Summary, Branches, Products, Data, Run info) with values in every cell and generated formulas in the total rows, an Excel table with the long records, number formats, A4 print setup and footers.
- **Charts and conditional formatting.** Three native Excel charts (revenue by branch, chain revenue over eight weeks, revenue mix) and rules that colour thresholds, changes and severities in the workbook itself.
- **Notification.** The e-mail with the key figures and the workbook attached is written as an `.eml` file (`--notify dry-run`) or also sent through SMTP (`--notify smtp`), with settings from environment variables only.
- **Scheduling.** A GitHub Actions workflow builds the demo report every Monday and publishes it on the Pages site; [docs/scheduling.md](docs/scheduling.md) has a Task Scheduler definition and a cron line for running it on a company machine.
- **Traceable runs.** Every run writes a manifest with the SHA-256 of every input and output, the findings and the figures; with `SOURCE_DATE_EPOCH` two runs give identical bytes.

## How it works

![How build-report works](docs/architecture.svg)

Discover lists the workbooks in the input folder; the template reader reads each one and records findings; the resolver assigns weeks (the cover wins over the file name), settles duplicates and marks missing branches; the returns become long records, one per branch, week, category and measure; the metrics engine evaluates `report.yaml`; the workbook writer builds the sheets and the reproducible save re-packs the file; the e-mail follows and the manifest is written last. Details: [docs/architecture.md](docs/architecture.md).

## Data model

Every branch sends one workbook per ISO week, `CL-NN_YYYY-Www.xlsx`, with the sheets Cover (branch, week, transactions, submitted at), Sales (six product groups: net sales, units, waste units, waste EUR) and Labour (three roles: hours, cost). The combined data is one long table, `tblWeekly`, with one row per branch, week, category and measure, so branch figures and product-group figures never share a row. The metrics, their formats and the direction of a good change are defined in `report.yaml`. Tables, rules and the six deviations of the demo set: [docs/data-model.md](docs/data-model.md).

## Getting started

Python 3.11 or newer and [uv](https://docs.astral.sh/uv/) are needed.

```bash
git clone https://github.com/HARISPAARTAN/excel-reporting-automation.git
cd excel-reporting-automation
uv sync
uv run build-report validate --input data/incoming --period 2025-W38
uv run build-report run --period 2025-W38 --input data/incoming --out reports --notify dry-run
uv run pytest
```

The run writes `Cedarline_Weekly_Report_2025-W38.xlsx`, `.eml` and `.manifest.json` into `reports/`. Every command and option, the exit codes, the findings and the environment variables: [docs/usage.md](docs/usage.md). Running it every Monday: [docs/scheduling.md](docs/scheduling.md). Keeping it running: [docs/handover.md](docs/handover.md).

## Project layout

```text
report.yaml                 the configuration: template, branches, metrics, thresholds, recipients
src/buildreport/            the package: reader, resolver, metrics engine, workbook writer, manifest, notifier, CLI
data/incoming/              96 invented branch workbooks, 2025-W31 to 2025-W38, with the demo deviations
tests/                      pytest suite, with an independent pandas reference in tests/reference.py
tools/                      demo data, LibreOffice render, Pages publishing, kit sync and repository checks
web/                        the Pages site: index.html, assets/, the vendored portfolio-kit, latest/
docs/                       brief, data model, usage, architecture, scheduling, handover, ADRs
.github/workflows/          ci.yml, weekly-report.yml, pages.yml
```

## Decisions

- [ADR 0001: Values in cells, formulas only in totals](docs/adr/0001-values-with-formula-totals.md)
- [ADR 0002: Reproducible workbooks and e-mails](docs/adr/0002-reproducible-workbooks.md)
- [ADR 0003: The cover week wins over the file name](docs/adr/0003-cover-week-wins.md)
- [ADR 0004: Weekly commit of the report, preview render at deployment](docs/adr/0004-weekly-commit-and-pages-render.md)

## Compared with the original delivery

This rebuild adds what a handover to another team needs:

- a written brief with roles and acceptance criteria;
- findings with codes instead of silent failures, and a manifest for every run;
- tests of every metric against an independent pandas computation, and a LibreOffice recalculation of every formula total in CI;
- reproducible output: identical inputs and timestamp give identical bytes;
- a scheduled CI run that builds and publishes the report every week;
- usage, scheduling and handover documentation and four decision records.

## Licence and data note

MIT, see [LICENSE](LICENSE). The page uses portfolio-kit v0.1.0 (MIT) with the fonts Inter, Space Grotesk and JetBrains Mono under the SIL Open Font License 1.1 ([web/kit/fonts/LICENSES.md](web/kit/fonts/LICENSES.md)). Changes: [CHANGELOG.md](CHANGELOG.md).

Cedarline Bakeries, its branches, people, figures and e-mail addresses are invented; every address uses the reserved domain `cedarline.example`. Rebuilt from memory as a demo. The original client's name and data are not used.
