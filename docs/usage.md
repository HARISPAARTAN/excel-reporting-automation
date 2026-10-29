# Usage

The tool installs as the command `build-report` (also `python -m buildreport`). From a clone:

```bash
uv sync --locked
uv run build-report --help
```

Every command reads `report.yaml` from the current folder unless `--config` names another file. Log lines go to stderr in the form `LEVEL message`; `validate` prints its findings to stdout.

## Global options

These come before the command name, for example `uv run build-report --log-level DEBUG run --period last`.

| Option | Default | Meaning |
|---|---|---|
| `--log-level DEBUG\|INFO\|WARNING` | `INFO` | how much is logged to stderr; `DEBUG` adds the traceback of an unexpected error |
| `--log-file PATH` | none | also append the log to this file, with a timestamp per line (the scheduled examples in [scheduling](scheduling.md) use one) |
| `--version` | | print `build-report 0.1.0` and exit |
| `-h`, `--help` | | print the help of the tool or of a command |

## Commands

### `run`

Builds the weekly report for one ISO week from the branch workbooks in a folder.

| Option | Default | Meaning |
|---|---|---|
| `--period WEEK` | required | `2025-W38` (`2025W38` is accepted) or `last`, the ISO week before the current UTC week |
| `--input FOLDER` | `data/incoming` | folder with the branch workbooks (not searched recursively; files starting with `~$` are skipped) |
| `--out FOLDER` | `reports` | output folder, created when missing |
| `--config FILE` | `report.yaml` | the report configuration |
| `--strict` | off (`strict: false` in `report.yaml`) | any finding blocks the run: no workbook, no e-mail, exit code 3 |
| `--notify none\|dry-run\|smtp` | `none` | `dry-run` writes the e-mail as an `.eml` file next to the workbook; `smtp` writes the same file and sends it; `none` writes no e-mail and deletes an older `.eml` of the same period |

Outputs in `--out` (period 2025-W38):

| File | Content |
|---|---|
| `Cedarline_Weekly_Report_2025-W38.xlsx` | the report: sheets Summary, Branches, Products, Data and Run info |
| `Cedarline_Weekly_Report_2025-W38.eml` | the e-mail with the workbook attached (`dry-run` and `smtp`) |
| `Cedarline_Weekly_Report_2025-W38.manifest.json` | the run manifest, always written last, also for a blocked run |

A blocked run (exit code 3) writes only the manifest and deletes an older workbook and `.eml` of the same period, so a folder never shows a stale report next to a fresh manifest. Files are written to a temporary name and renamed, so a reader never sees half a file.

The demo week, in a POSIX shell:

```bash
SOURCE_DATE_EPOCH=1758520800 uv run build-report run --period 2025-W38 --input data/incoming --out reports --notify dry-run
```

and in PowerShell:

```powershell
$env:SOURCE_DATE_EPOCH = "1758520800"
uv run build-report run --period 2025-W38 --input data/incoming --out reports --notify dry-run
```

The log of either form:

```text
INFO reading 96 files from data/incoming
WARNING warning  SHEET_RENAMED        CL-03_2025-W38.xlsx  sheet 'Sales wk38' used for Sales (alias 'Sales*')
...
INFO wrote reports/Cedarline_Weekly_Report_2025-W38.xlsx
INFO wrote reports/Cedarline_Weekly_Report_2025-W38.eml
INFO wrote reports/Cedarline_Weekly_Report_2025-W38.manifest.json
INFO 2025-W38: 12 branches reported, 12 expected; 0 errors, 6 warnings; exit code 0
```

On Windows the paths in the log use backslashes.

### `validate`

Checks the workbooks without writing anything.

| Option | Default | Meaning |
|---|---|---|
| `--input FOLDER` | `data/incoming` | folder with the branch workbooks |
| `--period WEEK` | none | also check completeness for this week and its eight-week window (`MISSING_BRANCH`, `NO_DATA`); files outside the window are left out |
| `--config FILE` | `report.yaml` | the report configuration |
| `--strict` | off (`strict: false` in `report.yaml`) | exit code 3 on any finding, not only on errors |
| `--format text\|json` | `text` | `text` prints one line per finding: severity, code, file (`-` for the period) and message; `json` prints a list of objects with the keys `severity`, `code`, `file` and `message` |

```bash
uv run build-report validate --input data/incoming --period 2025-W38
```

```text
warning  SHEET_RENAMED        CL-03_2025-W38.xlsx  sheet 'Sales wk38' used for Sales (alias 'Sales*')
warning  EXTRA_COLUMN         CL-05_2025-W38.xlsx  column 'Notes' on sheet Sales ignored
warning  WEEK_MISSING         CL-08_2025-W38.xlsx  ISO week blank on the cover; 2025-W38 taken from the file name
warning  DUPLICATE_REPLACED   CL-10_2025-W37.xlsx  replaced by CL-10_2025-W37_resend.xlsx (submitted 2025-09-15 14:12, later than 2025-09-15 08:40)
warning  WEEK_NAME_MISMATCH   CL-11_2025-W28.xlsx  cover says 2025-W38, file name says 2025-W28; cover used
warning  MISSING_BRANCH       -  CL-12 Rowanmere: no valid file for 2025-W36; branch left blank
```

stderr ends with `INFO checked 96 files: 0 errors, 6 warnings`; the exit code is 0. Without `--period` the `MISSING_BRANCH` line is not checked and five warnings remain. Findings are sorted errors first, then by file (period findings last), code and message.

### `generate-fixtures`

Writes invented branch workbooks in template version 3, for tests and the demo.

| Option | Default | Meaning |
|---|---|---|
| `--weeks N` | `8` | number of weeks, 1 to 104 |
| `--end-week WEEK` | `last` | the last week written, such as `2025-W38`, or `last` |
| `--out FOLDER` | required | target folder, created when missing |
| `--seed N` | `2207` | seed of the generator; the same seed, weeks and profile give the same content |
| `--deviations none\|demo` | `none` | `demo` adds the six deviations of the [data model](data-model.md#deviations-in-the-demo-set) relative to the end week |
| `--force` | off | overwrite existing files; without it the command stops with exit code 2 before writing anything if a target exists |
| `--config FILE` | `report.yaml` | branches, product groups, roles and labels come from here |

```bash
uv run build-report generate-fixtures --weeks 8 --end-week 2025-W38 --deviations demo --out build/fixtures
```

The committed set in `data/incoming/` is written by `uv run python tools/make_data.py` and checked by `uv run python tools/check_fixtures.py`, which regenerates it in a temporary folder and compares content fingerprints (the workbook content, not the zip bytes).

## Exit codes

| Code | Meaning | Typical cause |
|---|---|---|
| 0 | report built (`run`) or no errors (`validate`) | warnings do not change the code |
| 1 | unexpected error | a bug; run again with `--log-level DEBUG` for the traceback |
| 2 | usage or configuration error | unknown option, invalid week, missing input folder, invalid `report.yaml`, invalid `SOURCE_DATE_EPOCH`, incomplete SMTP settings, existing fixtures without `--force` |
| 3 | blocked | no valid file for the period (`NO_DATA`), or any finding with `--strict`; `validate` also returns 3 when there are errors |
| 4 | report built, sending failed | SMTP refused the login or the connection timed out (30 s); the workbook and the `.eml` are kept |
| 5 | report built, files excluded | at least one file was excluded because of an error; the report covers the other branches. When sending also fails, 4 wins |

## Findings

Errors exclude the file (or block the run for `NO_DATA`); warnings are logged and the file is used.

| Code | Severity | Meaning |
|---|---|---|
| `FILE_UNREADABLE` | error | the file cannot be opened as a workbook |
| `BRANCH_INVALID` | error | the cover branch code is blank, unknown to `report.yaml`, or differs from the file name |
| `SHEET_MISSING` | error | no sheet matches the name or an alias |
| `COLUMN_MISSING` | error | a required column header is missing |
| `ROW_UNKNOWN` | error | a product group or role that `report.yaml` does not list |
| `VALUE_INVALID` | error | text in a numeric cell, a negative number, a blank required value, a repeated header or row, or a missing Submitted at |
| `WEEK_INVALID` | error | no valid ISO week on the cover or in the file name |
| `DUPLICATE_AMBIGUOUS` | error | two different files for the same branch and week with the same Submitted at; every copy is excluded |
| `NO_DATA` | error | no valid file for the period; the run is blocked |
| `FILE_NAME` | warning | the name does not match `input.file_pattern`, or its week is not an ISO week; branch and week come from the cover |
| `TEMPLATE_VERSION` | warning | the cover gives another template version than 3; the file is read as version 3 |
| `SHEET_RENAMED` | warning | a sheet was found through an alias |
| `EXTRA_COLUMN` | warning | an unknown column, ignored |
| `ROW_MISSING` | warning | a product group or role row is missing and counted as zero |
| `WEEK_MISSING` | warning | the cover week is blank or invalid; the week comes from the file name |
| `WEEK_NAME_MISMATCH` | warning | cover and file name give different weeks; the cover wins ([ADR 0003](adr/0003-cover-week-wins.md)) |
| `DUPLICATE_IDENTICAL` | warning | a second file with the same content; the first by name is kept |
| `DUPLICATE_REPLACED` | warning | an earlier submission replaced by a later one for the same branch and week |
| `MISSING_BRANCH` | warning | a branch has no valid file for a week of the window; it is left blank |

A file whose week lies outside the eight-week window is skipped without findings. The manifest lists every input with its status: `used`, `replaced`, `duplicate`, `excluded` or `outside window`.

## Environment variables

| Variable | Used by | Meaning |
|---|---|---|
| `SOURCE_DATE_EPOCH` | `run`, and `last` in every command | seconds since 1970-01-01 UTC; fixes the run timestamp (zip member times, document properties, Run info, manifest), so two runs give identical bytes ([ADR 0002](adr/0002-reproducible-workbooks.md)); unset means the clock |
| `BUILD_REPORT_SMTP_HOST` | `run --notify smtp` | SMTP server; required for `smtp` (exit code 2 when missing) |
| `BUILD_REPORT_SMTP_PORT` | `run --notify smtp` | default 587; use 465 with `ssl` |
| `BUILD_REPORT_SMTP_USER` | `run --notify smtp` | login name; set together with the password, or neither |
| `BUILD_REPORT_SMTP_PASSWORD` | `run --notify smtp` | password of a send-only account; never logged and never written to the manifest |
| `BUILD_REPORT_SMTP_SECURITY` | `run --notify smtp` | `starttls` (default), `ssl` (implicit TLS) or `none`, which is allowed only for `localhost` and `127.0.0.1` |
| `GITHUB_SERVER_URL`, `GITHUB_REPOSITORY`, `GITHUB_RUN_ID` | `run` | set by GitHub Actions; when all three are present the manifest records the run URL under `ci` |

## The e-mail

Subject: `{subject_prefix} {period}: revenue {revenue} ({change} WoW), {n} findings`, with `notify.subject_prefix` from `report.yaml`, the chain revenue in whole euros (in the form `€301,250`), its week-on-week change with one decimal (in the form `+1.4%`) and the number of findings; for the demo week the subject starts with `Cedarline weekly report 2025-W38: revenue` and ends with `WoW), 6 findings`. The message has a plain-text and an HTML part with the summary key figures, the threshold hits, the top-ranked branch, the branches reporting and the finding counts, and the workbook as attachment. Recipients are `notify.to` plus `notify.cc` from `report.yaml`; with `--notify dry-run` nothing leaves the machine.

## The manifest

`<stem>.manifest.json` is JSON with `schema: 1` and the keys `status` (`built` or `blocked`), `exit_code`, `tool`, `environment`, `period`, `period_start`, `period_end`, `window`, `generated_at`, `timestamp_source`, `config` (`path`, `sha256`; the path is shown relative to the working directory, or only as the file name when the file lies outside it), `strict`, `notify`, `inputs` (`file`, `bytes`, `sha256`, `branch`, `week`, `submitted_at`, `status`), `branches_reporting`, `findings`, `kpis`, `ranking`, `above_threshold`, `outputs` (`file`, `bytes`, `sha256`) and, in GitHub Actions, `ci`. The demo page reads the copy in `web/latest/manifest.json`.

## Scheduling

[scheduling.md](scheduling.md) shows the weekly run in GitHub Actions, Windows Task Scheduler and cron.
