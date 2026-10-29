# ADR 0001: Values in cells, formulas only in totals

## Status

Accepted (2026-10-29)

## Context

openpyxl writes formulas but never evaluates them. A workbook built with formulas in every cell has no cached values until an application recalculates it: the e-mail preview, a phone viewer or a Python reader shows empty cells, and the figures depend on the program that opens the file. The report must show the same numbers everywhere, and the numbers must be testable without Excel.

## Decision

Every figure is computed by the metrics engine and written as a value. Formulas appear only where a reader expects to see how a total is made: the total rows of Branches and Products and the totals of the revenue mix. These formulas are generated from the same metric expressions in `report.yaml` (`expr.py` translates `revenue / transactions` into `IF(G16=0,"",D16/G16)`), so a total and the engine's value come from one definition. The cached value of every formula cell is the engine's value.

## Consequences

- Every viewer shows the figures, also without recalculation.
- The values are tested against an independent pandas computation (`tests/reference.py`).
- A formula could still disagree with its cached value if the translation had a bug. CI opens the workbook in LibreOffice, recalculates it and compares all 30 formula cells with the engine's values (`tools/render_sheets.py --check-recalc`).
- Someone editing a branch's figure in the report sees the total row update, but not the Summary, which holds values; the Summary's subtitle names the generation time and the tool, so the report reads as generated, not as a working file.

## Alternatives considered

- Formulas in every cell: rejected, because the values would depend on the opening application and could not be checked in Python.
- Values only, without formulas: rejected, because a total that shows how it is built can be checked in Excel by any reader, and the recalculation check would have nothing to verify.
- A Python formula engine (such as `formulas` or `pycel`): rejected as a second implementation of Excel semantics to trust and maintain.
