# Brief: the Cedarline weekly report

Cedarline Bakeries is a fictional bakery chain with twelve branches around Dublin, invented for this demo; its e-mail domain is the reserved `cedarline.example`. Rebuilt from memory as a demo. The original client's name and data are not used.

## The job post

> We are a bakery chain with twelve branches around Dublin. Every Monday each branch manager e-mails head office an Excel file for the past week: sales by product group, waste, labour hours and the number of transactions. The template is fixed, but in practice sheets get renamed, columns get added, and files arrive twice or carry the wrong week. We need a Python script that collects the files from a folder, checks them, builds one formatted weekly report with KPIs, week-on-week changes, a branch ranking and charts, and e-mails it to head office every Monday morning without anyone opening Excel.

## Goal

A command-line tool that reads the twelve weekly branch workbooks, checks them against the template, tolerates the usual deviations with a list of findings, and writes one formatted weekly Excel report (key figures with week-on-week change, branch ranking, three native Excel charts, conditional formatting, an Excel table, print setup), a run manifest and an e-mail. It runs on a schedule every Monday.

## Who works with it

| Role | What they do |
|---|---|
| Branch managers (12) | fill the weekly template and e-mail it; the files reach the input folder, for example through a synced shared drive |
| Head office operations | reads the report and the e-mail on Monday morning |
| Finance (copy) | follows labour and waste on the sheets Branches and Products |
| Reporting administrator | maintains `report.yaml`, the scheduler and the SMTP settings, and follows up findings with the branches ([handover](handover.md)) |
| Scheduler | runs `build-report run --period last` every Monday: Task Scheduler, cron or GitHub Actions ([scheduling](scheduling.md)) |

## In scope

- Reading template version 3 and its usual deviations; validation with findings; week and duplicate resolution.
- Ten metrics defined as expressions in `report.yaml`; week-on-week change; branch ranking; thresholds.
- The five-sheet report, the run manifest and the e-mail, as an `.eml` preview or sent through SMTP.
- A seeded fixture generator with a demo deviation profile; the weekly GitHub Actions run that publishes the report on the Pages site with LibreOffice previews.
- Task Scheduler and cron examples, tests, documentation and release v0.1.0.

## Out of scope

- Fetching attachments from a mailbox (IMAP, Graph): the files arrive in a folder.
- Per-branch reports, targets and budgets, macros or VBA, other currencies than EUR, weeks other than ISO weeks.
- A formula engine in Python: openpyxl writes formulas but never evaluates them, so cells hold computed values and only the totals are formulas ([ADR 0001](adr/0001-values-with-formula-totals.md)).
- Uploading files on the Pages site, and any SMTP account or secret in CI (the weekly run uses dry-run).

## Acceptance

- `uv run build-report run --period 2025-W38 --input data/incoming --out reports --notify dry-run` exits with code 0 and exactly six warnings; with `--strict` it exits with code 3 and writes no workbook.
- Every metric equals an independent pandas computation; LibreOffice recalculates every total to the tool's value.
- Two runs with the same inputs and `SOURCE_DATE_EPOCH` give byte-identical outputs.
- The weekly run publishes the report and its previews without anyone starting it.
