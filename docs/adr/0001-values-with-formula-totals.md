# ADR 0001: Values in cells, formulas only in totals

## Status

Accepted (2026-10-29)

## Context

openpyxl writes formulas but never evaluates them, and it cannot store a computed result next to a formula: a formula cell is written with an empty cached value (`<v />`). A workbook built with formulas in every cell therefore has no cached values until an application recalculates it: a viewer that does not calculate, or a Python reader, shows empty cells, and the figures depend on the program that opens the file. The report should show its figures without depending on the viewer, and the numbers must be testable without Excel.

## Decision

Every figure is computed by the metrics engine and written as a value, with one exception: the totals. Formulas appear only where a reader expects to see how a total is made: the total rows of Branches and Products and the totals of the revenue mix. These formulas are generated from the same metric expressions in `report.yaml` (`expr.py` translates `revenue / transactions` into `IF(G16=0,"",D16/G16)`), so a total and the engine's value come from one definition. The 30 total cells (with the committed configuration) carry the formula and no cached value; the workbook asks the application to calculate in full when it opens the file (`fullCalcOnLoad`, which openpyxl sets by default), so Excel and LibreOffice fill them in. Every other cell holds its value.

## Consequences

- Every cell except the 30 totals shows its figure in every viewer, with or without calculation. A viewer that does not calculate, and a Python reader that asks for cached values (`data_only=True`), see those 30 total cells empty.
- The values are tested against an independent pandas computation (`tests/reference.py`).
- The formulas and the engine could still disagree if the translation had a bug. CI opens the workbook in LibreOffice, which recalculates it, and compares all 30 formula cells with the engine's values (`tools/render_sheets.py --check-recalc`); the rendered previews on the Pages site show the recalculated totals.
- Follow-up for v0.2.0: store the engine's value as the cached result of each of the 30 cells while the archive is re-packed (`reproducible.py`, [ADR 0002](0002-reproducible-workbooks.md)). Then every viewer shows the totals too, and the check can compare the stored values with the recalculated ones.
- Someone editing a branch's figure in the report sees the total row update, but not the Summary, which holds values; the Summary's subtitle names the generation time and the tool, so the report reads as generated, not as a working file.

## Alternatives considered

- Formulas in every cell: rejected, because the values would depend on the opening application and could not be checked in Python.
- Values only, without formulas: rejected, because a total that shows how it is built can be checked in Excel by any reader, and the recalculation check would have nothing to verify.
- A Python formula engine (such as `formulas` or `pycel`): rejected as a second implementation of Excel semantics to trust and maintain.
