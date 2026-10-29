# Handover

For the reporting administrator who keeps the weekly report running. Commands run from the repository folder; [usage](usage.md) lists every option, [scheduling](scheduling.md) the three ways to run it every Monday.

## Every Monday

1. The scheduled run starts (06:00 UTC in GitHub Actions, 07:00 local time in the Task Scheduler and cron examples) and builds the report for the previous ISO week.
2. Head office receives the e-mail with the workbook attached (`--notify smtp`), or the `.eml` lies next to the workbook in the output folder (`--notify dry-run`).
3. Look at the last log line or the manifest: `exit_code` 0 means built; any other code is listed in [usage](usage.md#exit-codes). Then read the findings on the sheet Run info and follow up with the branches below.

## Reading findings and what to ask the branch

| Finding | What it means for the report | What to ask or do |
|---|---|---|
| `SHEET_RENAMED`, `EXTRA_COLUMN` | none; the file was read | nothing urgent; remind the branch to keep the template unchanged |
| `WEEK_MISSING` | the week was taken from the file name | ask the branch to fill in the ISO week on the cover |
| `WEEK_NAME_MISMATCH` | the cover week was used | check with the branch which week the figures belong to; if the cover is wrong, ask for a corrected file and run the week again |
| `DUPLICATE_REPLACED` | the later submission was used | confirm that the later file is the correction |
| `DUPLICATE_IDENTICAL` | one copy was used | nothing; the file was sent twice |
| `MISSING_BRANCH` | the branch is blank that week; chain figures cover the others | ask for the missing return, then run the week again |
| `ROW_MISSING` | the missing product group or role counts as zero | ask whether the branch really sold nothing in that group, or forgot the row |
| `FILE_NAME`, `TEMPLATE_VERSION` | the file was read (branch and week from the cover, or as template version 3) | ask the branch to use the current template and the name `CL-NN_YYYY-Www.xlsx` |
| `VALUE_INVALID`, `COLUMN_MISSING`, `ROW_UNKNOWN`, `SHEET_MISSING` | the file is excluded (exit code 5) | send the message from Run info to the branch and ask for a corrected file |
| `BRANCH_INVALID` | the file is excluded | the cover names a branch that `report.yaml` does not know, or a different one than the file name |
| `FILE_UNREADABLE` | the file is excluded | ask the branch to save it again as `.xlsx` |
| `DUPLICATE_AMBIGUOUS` | every copy is excluded | ask which copy is valid, delete the other, run the week again |
| `WEEK_INVALID` | the file is excluded | ask for the ISO week on the cover |
| `NO_DATA` | no report (exit code 3) | no valid file for the week reached the input folder; check the folder and the sync |

To check the folder before the run: `uv run build-report validate --input <folder> --period last`.

## Running a week again

After a corrected file has arrived, run the same command with the week: `uv run build-report run --period 2025-W38 --input <folder> --out <folder> --notify smtp`. The workbook, the `.eml` and the manifest of that week are replaced. In GitHub Actions: `gh workflow run weekly-report.yml -f period=2025-W38`, or Actions → weekly-report → Run workflow with the week.

## Adding or renaming a branch

1. Add the branch to `branches:` in `report.yaml` with a unique code `CL-NN`, its name and format (up to 14 branches; the sheets follow the list).
2. Give the branch manager the template and the file name pattern.
3. Run `uv run build-report validate --period last` to check the configuration (exit code 2 with the reason if it is invalid).

In this demo repository the weekly run generates its data, and the generator knows only the twelve demo branches (`BRANCH_PARAMS` in `src/buildreport/fixtures.py`); a new branch there also needs a line of parameters, otherwise `generate-fixtures` stops with "the generator has no parameters for branch CL-13". The tests pin the committed configuration, so `uv run pytest` shows which expected values change.

## Changing thresholds or recipients

- Thresholds: `thresholds:` in `report.yaml`, one per metric, with `op` (`>`, `>=`, `<`, `<=`), `value` (a share for percentages: `0.06` is 6 %) and `style` (`bad` red, `warn` amber).
- Recipients: `notify.to` and `notify.cc`; the sender is `notify.from`. In this public demo every address uses the reserved domain `cedarline.example`, and `tests/test_content.py` enforces that; a real deployment keeps its `report.yaml` in its own private copy.
- Check the change with `uv run build-report validate --period last`, then with a dry run: `uv run build-report run --period last --input <folder> --out build/check --notify dry-run`, and open the `.eml` in a mail program.

## SMTP setup

The settings come only from environment variables, never from `report.yaml`: `BUILD_REPORT_SMTP_HOST`, `BUILD_REPORT_SMTP_PORT`, `BUILD_REPORT_SMTP_USER`, `BUILD_REPORT_SMTP_PASSWORD` and `BUILD_REPORT_SMTP_SECURITY` ([usage](usage.md#environment-variables)). Use a send-only account whose password can be changed without affecting anyone's mailbox. [scheduling](scheduling.md) shows where to set them on Windows and on a Linux server. A failed send keeps the workbook and the `.eml` and ends with exit code 4; the `.eml` can then be sent by hand from a mail program.

To change the password: set the new value in the same place, then run one dry run and one `--notify smtp` run for the last week.

## A disabled schedule

GitHub disables scheduled workflows in a public repository after 60 days without activity in the repository. The Actions tab then shows a banner on weekly-report. Re-enable it with `gh workflow enable weekly-report.yml`, or Actions → weekly-report → Enable workflow, and start one run by hand to check it: `gh workflow run weekly-report.yml`.

## Where logs and manifests are

| Where it runs | Log | Outputs and manifest |
|---|---|---|
| GitHub Actions | the run log under Actions → weekly-report | the artifact `weekly-report` (90 days) and `web/latest/` in the repository; the Pages site shows the latest |
| Task Scheduler | `D:\Cedarline\Reports\build-report.log`; the task history in Task Scheduler | `D:\Cedarline\Reports` |
| cron | `/var/log/cedarline/build-report.log` | `/srv/cedarline/reports` |

Every manifest (`<stem>.manifest.json`) records the status, the exit code, every input file with its SHA-256 and status, every finding, the key figures and the SHA-256 of every output, so a report can be traced back to the files it was built from.
