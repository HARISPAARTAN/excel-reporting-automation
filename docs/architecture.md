# Architecture

![How build-report works](architecture.svg)

The tool is one Python package, `buildreport`, with a click command line. A run is a straight pipeline; every step is a module with pure functions where possible, so each one has its own tests.

| Step | Module | Input → output |
|---|---|---|
| Generator | `fixtures.py` | `report.yaml`, end week, seed, profile → branch workbooks (demo and tests only) |
| Discover | `discover.py` | input folder → the `*.xlsx` files sorted by name, with branch and week parsed from `input.file_pattern` |
| Template reader | `template.py` | one workbook → a `BranchReturn` (cover, sales, labour) plus findings; opened with `data_only=True`, numbers never parsed from text |
| Resolver | `resolve.py` | all returns → the week of each file (the cover wins), duplicates settled, missing branches, the eight-week window, the input statuses; then the long records |
| Metrics engine | `expr.py`, `metrics.py` | records + the expressions of `report.yaml` → every metric for each branch, product group and the chain, week-on-week change, ranking, thresholds, summary |
| Workbook writer | `workbook/*.py` | results → the five sheets with values, generated total formulas, three native charts, conditional formatting, the table `tblWeekly`, print setup |
| Reproducible save | `reproducible.py` | the openpyxl workbook → bytes re-packed with the run timestamp |
| Manifest | `manifest.py` | run facts, inputs, findings, figures, outputs → `<stem>.manifest.json` |
| Notifier | `notify.py` | results + workbook → an `EmailMessage`, written as `.eml`, sent through SMTP with `--notify smtp` |
| Command line | `cli.py` | options → the steps above, the log and the exit code |

Module dependencies have no cycles: `isoweek` ← `findings`, `expr` ← `config` ← `discover` ← `template` ← `resolve` ← `metrics` ← `workbook` ← `manifest`, `notify` ← `cli`. `reproducible` and `fixtures` depend only on `isoweek`, `config` and openpyxl. pandas is a test dependency only: `tests/reference.py` computes every metric a second way, from the same records, and the tests compare the two.

## The configuration

`report.yaml` is loaded into pydantic models that reject unknown keys (`config.py`). The metrics are expressions such as `revenue / transactions`, parsed with Python's `ast` module against an allow-list (`sum(measure)`, names of earlier metrics, numbers, `+ - * /`, unary minus, parentheses). The same parse tree is evaluated in Python and translated to Excel formulas for the total rows (`IF(den=0,"",num/den)` for division), so a total in the workbook and the engine's value come from one definition. CI opens the workbook in LibreOffice, recalculates it and compares every one of the 30 formula cells with the value the engine wrote ([ADR 0001](adr/0001-values-with-formula-totals.md)).

## The workbook

| Sheet | Content |
|---|---|
| Summary | title and dates, the seven key figures with last week and change, the branch ranking, data notes, three charts: revenue by branch (bar), chain revenue over eight weeks (line), revenue mix by product group (doughnut) |
| Branches | one row per branch with this week's figures, a total row with formulas, rank and rank change; the eight-week chain trend |
| Products | product groups with a total row; the revenue mix by branch with a colour scale |
| Data | the long records as the Excel table `tblWeekly` |
| Run info | run facts (period, timestamp source, versions, configuration hash, strict mode), every input file with its status and SHA-256, every finding with a severity fill |

Every sheet prints on A4 with a footer; Summary, Branches and Products fit on one page. Thresholds and week-on-week changes are colour-coded with conditional formatting rules, so they stay correct when someone edits a value in Excel.

## Reproducible output

openpyxl stamps the current time into the workbook and into every zip member. `reproducible.py` saves to memory and re-packs the archive: same member order, member times from the run timestamp, fixed file attributes, `ZIP_DEFLATED` at level 6, and the created and modified times in `docProps/core.xml` replaced. The run timestamp is `SOURCE_DATE_EPOCH` when it is set, else the clock. The `.eml` uses MIME boundaries and a Message-ID derived from the workbook's SHA-256. Two runs with the same inputs and timestamp therefore give identical bytes; `tests/test_reproducible_run.py` checks this with two separate processes ([ADR 0002](adr/0002-reproducible-workbooks.md)).

## Weekly run and the Pages site

`weekly-report.yml` runs every Monday at 06:00 UTC and on demand. It generates the eight weeks ending with last week with the demo profile, runs `build-report run --period last --notify dry-run`, uploads the outputs as an artifact, commits the workbook, the `.eml` and the manifest to `web/latest/` as `github-actions[bot]` with `[skip ci]`, and calls `pages.yml` with the new commit. `pages.yml` installs LibreOffice and poppler, renders one PNG per sheet into `web/latest/preview/` and deploys `web/` to GitHub Pages; the preview images are never committed. The page reads `latest/manifest.json` and shows the key figures, the ranking, the findings and the previews ([ADR 0004](adr/0004-weekly-commit-and-pages-render.md)).

## CI

| Job | What it checks |
|---|---|
| lint | ruff, ruff format, mypy (strict on the core modules) |
| test | the test suite on Ubuntu and Windows with Python 3.11, 3.12 and 3.13 |
| render | builds the demo report, renders it with LibreOffice, recalculates every formula cell, checks five one-page previews; uploads the artifact `demo-render` |
| scheduler | registers the Task Scheduler definition on Windows, reads it back and removes it |
| checks | the committed fixtures regenerate identically, `web/kit/` matches portfolio-kit v0.1.0, the term scrub, the page weight and the colour contrast |
