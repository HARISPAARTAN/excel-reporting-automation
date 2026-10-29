# ADR 0002: Reproducible workbooks and e-mails

## Status

Accepted (2026-10-29)

## Context

An `.xlsx` file is a zip archive. openpyxl stamps the current time into every zip member and into the created and modified properties of `docProps/core.xml`, so two runs over the same inputs give different bytes. Different bytes make it impossible to tell a real change from noise: the weekly commit would change every week even without new figures, golden tests could only compare cell values, and a reader cannot confirm that a report was built from given inputs.

## Decision

The run timestamp comes from `SOURCE_DATE_EPOCH` when it is set (the convention of reproducible builds), else from the clock. `reproducible.py` saves the workbook to memory and re-packs the archive: the same member order, every member time set to the run timestamp (clamped to the zip range, even seconds), `create_system` 0, the same file attributes on every member (`-rw-------`), `ZIP_DEFLATED` at level 6, and the created and modified values in `docProps/core.xml` replaced with the run timestamp. The `.eml` takes its `Date` from the run timestamp and derives its MIME boundaries and its Message-ID from the workbook's SHA-256. The manifest records the timestamp and its source.

## Consequences

- Two runs with the same inputs, configuration and `SOURCE_DATE_EPOCH` give identical workbook, `.eml` and manifest bytes; `tests/test_reproducible_run.py` checks this with two separate processes.
- The manifest's SHA-256 values identify a report; the inputs' SHA-256 values identify what it was built from.
- The re-pack depends on openpyxl's archive layout; the pin `openpyxl>=3.1.5,<3.2` and the test catch a change.
- Without `SOURCE_DATE_EPOCH` the output still differs from run to run by the timestamp, as expected.

## Alternatives considered

- A project-specific variable such as `BUILD_REPORT_TIME`: rejected in favour of the established convention.
- Accepting differing bytes and comparing cell values only: rejected, because the weekly commit and the release assets would change without reason.
