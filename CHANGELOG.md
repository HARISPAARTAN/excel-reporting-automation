# Changelog

All notable changes to this project are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## v0.1.0 (unreleased)

First release.

### Added

- `build-report run`: reads the weekly branch workbooks (template version 3), resolves weeks, duplicates and missing branches, computes ten metrics from `report.yaml` and writes the five-sheet report with three native charts and conditional formatting, the run manifest and, with `--notify dry-run` or `smtp`, the e-mail.
- `build-report validate`: the findings as text lines or JSON; `--strict` for any finding.
- `build-report generate-fixtures`: seeded invented workbooks with the `demo` deviation profile; the committed demo set for 2025-W31 to 2025-W38.
- Reproducible outputs with `SOURCE_DATE_EPOCH`; exit codes 0 to 5.
- GitHub Actions: CI (lint, tests on Ubuntu and Windows with Python 3.11 to 3.13, LibreOffice render with recalculation check, Task Scheduler registration, repository checks), the weekly report run every Monday and the Pages deployment.
- The demo page on portfolio-kit v0.1.0; Task Scheduler and cron examples; brief, data model, usage, architecture, scheduling and handover documentation; four ADRs.
